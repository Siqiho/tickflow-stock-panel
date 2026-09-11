"""策略回测服务 — 复用 StrategyDef 体系做全周期回测。

核心优化: 向量化 filter_fn，不逐日调用 StrategyEngine.run()。
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Literal

import numpy as np
import polars as pl

from app.backtest.engine import BacktestEngine, MatcherConfig, SimResult
from app.backtest.fundamentals import FUNDAMENTAL_FACTOR_NAMES
from app.backtest.matrix import MatrixCacheProfile
from app.indicators.pipeline import (
    ENRICHED_STORAGE_COLS,
    INDICATOR_COLUMNS,
    LIMIT_SIGNAL_OUTPUTS,
    get_signal_dependencies,
)
from app.strategy.engine import StrategyDef, StrategyEngine
from app.strategy.scoring import effective_scoring, scoring_dependencies, scoring_warmup_bars

logger = logging.getLogger(__name__)

BENCHMARK_SYMBOL = "000001.SH"
_EXECUTION_COLUMNS = frozenset({
    "symbol", "date", "open", "high", "low", "close", "volume",
    "name", "score", "signal_limit_up", "signal_limit_down",
})
_LIMIT_BASE_COLUMNS = frozenset({"raw_close", "raw_high", "raw_low"})
_INSTRUMENT_COLUMNS = frozenset({"name", "total_shares", "float_shares"})


@dataclass(frozen=True)
class FeaturePlan:
    required_features: frozenset[str]
    required_signals: frozenset[str]
    warmup_bars: int


@dataclass(frozen=True)
class ResolvedFeaturePlan:
    base_columns: frozenset[str]
    intermediate_columns: frozenset[str]
    indicator_columns: frozenset[str]
    signal_columns: frozenset[str]
    matrix_columns: frozenset[str]
    instrument_columns: frozenset[str]
    warmup_bars: int
    full_feature_fallback: bool = False
    execution_backend: str = "polars_expr"
    fundamental_columns: frozenset[str] = frozenset()


def _merge_resolved_feature_plans(
    plans: list[ResolvedFeaturePlan],
) -> ResolvedFeaturePlan:
    if not plans:
        raise ValueError("cannot merge an empty feature plan list")
    backends = {plan.execution_backend for plan in plans}
    if backends != {"matrix_native"}:
        raise ValueError("shared MarketDataMatrix preparation only supports matrix_native")

    def _union(field: str) -> frozenset[str]:
        merged: set[str] = set()
        for plan in plans:
            merged.update(getattr(plan, field))
        return frozenset(merged)

    return ResolvedFeaturePlan(
        base_columns=_union("base_columns"),
        intermediate_columns=_union("intermediate_columns"),
        indicator_columns=_union("indicator_columns"),
        signal_columns=_union("signal_columns"),
        matrix_columns=_union("matrix_columns"),
        instrument_columns=_union("instrument_columns"),
        warmup_bars=max(plan.warmup_bars for plan in plans),
        full_feature_fallback=any(plan.full_feature_fallback for plan in plans),
        execution_backend="matrix_native",
        fundamental_columns=_union("fundamental_columns"),
    )


class StrategyDependencyResolver:
    """Resolve all backtest field dependencies once before loading market data."""

    def resolve(
        self,
        strategy: StrategyDef,
        *,
        params: dict,
        basic_filter: dict,
        entry_signals: list[str],
        exit_signals: list[str],
        overrides: dict | None = None,
        minute_fill: bool = False,
        asset_type: str = "stock",
    ) -> ResolvedFeaturePlan:
        overrides = overrides or {}
        basic_filter = _basic_filter_for_asset(basic_filter, asset_type)
        if strategy.execution_backend == "matrix_native":
            return self._resolve_matrix_native(
                strategy,
                params=params,
                basic_filter=basic_filter,
                overrides=overrides,
            )

        required_features = set(strategy.required_features)
        required_signals = {
            _normalize_signal_name(signal)
            for signal in [*entry_signals, *exit_signals]
            if signal
        }
        required_signals.update({"signal_limit_up", "signal_limit_down"})

        scoring = effective_scoring(strategy.meta.get("scoring"), overrides)
        required_features.update(scoring_dependencies(scoring))
        order_by = strategy.meta.get("order_by")
        if order_by and order_by != "score":
            required_features.add(str(order_by))

        required_features.update(_basic_filter_dependencies(basic_filter))
        filter_features, filter_resolved = _filter_dependencies(strategy, params)
        required_features.update(filter_features)
        embedded_signals = {
            feature
            for feature in required_features
            if feature.startswith(("signal_", "csg_"))
        }
        required_signals.update(embedded_signals)
        required_features.difference_update(embedded_signals)

        full_fallback = bool(strategy.filter_history_fn and not strategy.required_features)
        full_fallback = full_fallback or not filter_resolved
        signal_dependencies = get_signal_dependencies()
        if full_fallback:
            logger.warning(
                "strategy %s has dynamic Python dependencies without REQUIRED_FEATURES; "
                "backtest falls back to full feature computation",
                strategy.meta.get("id", "<unknown>"),
            )
            required_features.update(INDICATOR_COLUMNS)
            required_signals.update(signal_dependencies)
            required_signals.update(LIMIT_SIGNAL_OUTPUTS)

        unknown_signals = required_signals - set(signal_dependencies) - set(LIMIT_SIGNAL_OUTPUTS)
        if unknown_signals:
            raise ValueError(f"策略引用了不存在的信号: {sorted(unknown_signals)}")
        for signal in required_signals:
            required_features.update(signal_dependencies.get(signal, ()))

        indicator_columns = frozenset(required_features & set(INDICATOR_COLUMNS))
        base_columns = _resolve_base_columns(required_features | set(_EXECUTION_COLUMNS))
        if required_signals & set(LIMIT_SIGNAL_OUTPUTS):
            base_columns = frozenset(set(base_columns) | set(_LIMIT_BASE_COLUMNS))

        instrument_columns = frozenset(required_features & set(_INSTRUMENT_COLUMNS))
        instrument_columns = frozenset(set(instrument_columns) | {"name"})
        matrix_columns = set(_EXECUTION_COLUMNS) | required_signals
        if minute_fill:
            indicator_columns = frozenset(set(indicator_columns) | {"ma5", "ma10", "ma20"})
            matrix_columns.update({"ma5", "ma10", "ma20"})
            base_columns = frozenset(set(base_columns) | {"close"})

        plan = FeaturePlan(
            required_features=frozenset(required_features),
            required_signals=frozenset(required_signals),
            warmup_bars=max(60, int(strategy.lookback_days or 1), scoring_warmup_bars(scoring)),
        )
        return ResolvedFeaturePlan(
            base_columns=base_columns,
            intermediate_columns=frozenset(),
            indicator_columns=indicator_columns,
            signal_columns=plan.required_signals,
            matrix_columns=frozenset(matrix_columns),
            instrument_columns=instrument_columns,
            warmup_bars=plan.warmup_bars,
            full_feature_fallback=full_fallback,
            execution_backend=strategy.execution_backend,
            fundamental_columns=frozenset(required_features & FUNDAMENTAL_FACTOR_NAMES),
        )

    @staticmethod
    def _resolve_matrix_native(
        strategy: StrategyDef,
        *,
        params: dict,
        basic_filter: dict,
        overrides: dict,
    ) -> ResolvedFeaturePlan:
        if strategy.matrix_strategy is None:
            raise ValueError(
                f"matrix_native strategy {strategy.meta.get('id', '<unknown>')} "
                "must declare MATRIX_STRATEGY"
            )

        required_features = set(strategy.required_features)
        required_features.update(strategy.matrix_strategy.required_fields())
        parameter_fields = getattr(strategy.matrix_strategy, "required_fields_for_params", None)
        parameter_scoring: dict[str, float] = {}
        if callable(parameter_fields):
            parameter_scoring = {str(name): 1.0 for name in parameter_fields(params)}
            required_features.update(scoring_dependencies(parameter_scoring))
        required_features.update(_basic_filter_dependencies(basic_filter))
        scoring = effective_scoring(strategy.meta.get("scoring"), overrides)
        required_features.update(scoring_dependencies(scoring))
        order_by = strategy.meta.get("order_by")
        if order_by and order_by != "score":
            required_features.add(str(order_by))

        base_columns = _resolve_base_columns(required_features | set(_EXECUTION_COLUMNS))
        base_columns = frozenset(set(base_columns) | set(_LIMIT_BASE_COLUMNS))
        instrument_columns = frozenset(required_features & set(_INSTRUMENT_COLUMNS))
        instrument_columns = frozenset(set(instrument_columns) | {"name"})
        warmup_bars = max(
            60,
            int(strategy.matrix_strategy.required_warmup_bars(params)),
            scoring_warmup_bars(scoring),
            scoring_warmup_bars(parameter_scoring),
        )
        matrix_columns = set(base_columns) | set(instrument_columns) | {
            "signal_limit_up",
            "signal_limit_down",
        }
        return ResolvedFeaturePlan(
            base_columns=base_columns,
            intermediate_columns=frozenset(),
            indicator_columns=frozenset(),
            signal_columns=frozenset({"signal_limit_up", "signal_limit_down"}),
            matrix_columns=frozenset(matrix_columns),
            instrument_columns=instrument_columns,
            warmup_bars=warmup_bars,
            full_feature_fallback=False,
            execution_backend="matrix_native",
            fundamental_columns=frozenset(required_features & FUNDAMENTAL_FACTOR_NAMES),
        )


def build_matrix_cache_profile(
    strategy_engine: StrategyEngine,
    asset_type: str,
    *,
    requested_plan: ResolvedFeaturePlan | None = None,
    requested_forward_bars: int = 0,
    max_disk_bytes: int = 512 * 1024 * 1024,
) -> MatrixCacheProfile:
    resolver = StrategyDependencyResolver()
    plans: list[ResolvedFeaturePlan] = []
    if requested_plan is not None:
        plans.append(requested_plan)
    forward_bars = max(0, int(requested_forward_bars))
    common_filter = {
        "enabled": True,
        "amount_min": 0.0,
        "turnover_min": 0.0,
        "market_cap_min": 0.0,
        "float_cap_min": 0.0,
        "exclude_st": True,
    }
    definitions = (
        strategy_engine.strategy_definitions()
        if hasattr(strategy_engine, "strategy_definitions")
        else ()
    )
    for strategy in definitions:
        if strategy.execution_backend != "matrix_native":
            continue
        if asset_type not in strategy.meta.get("asset_types", ["stock"]):
            continue
        if "1d" not in strategy.meta.get("timeframes", ["1d"]):
            continue
        params = StrategyEngine.resolve_params(strategy)
        for item in strategy.meta.get("params", []):
            if not isinstance(item, dict) or not item.get("id"):
                continue
            if item.get("type") in {"int", "float"} and item.get("max") is not None:
                params[str(item["id"])] = item["max"]
        plans.append(resolver.resolve(
            strategy,
            params=params,
            basic_filter={**dict(strategy.basic_filter or {}), **common_filter},
            entry_signals=strategy.entry_signals,
            exit_signals=strategy.exit_signals,
            overrides={},
            minute_fill=False,
            asset_type=asset_type,
        ))
        forward_bars = max(forward_bars, int(strategy.max_hold_days or 0))

    if not plans:
        raise ValueError(f"no matrix-native cache profile available for asset_type={asset_type!r}")
    merged = _merge_resolved_feature_plans(plans)
    fields = frozenset(set(merged.base_columns) | set(merged.instrument_columns) | set(merged.matrix_columns))
    generation_payload = json.dumps(
        {
            "asset_type": asset_type,
            "fields": sorted(fields),
            "warmup_bars": merged.warmup_bars,
            "forward_bars": forward_bars,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    generation = hashlib.blake2b(generation_payload.encode("utf-8"), digest_size=12).hexdigest()
    return MatrixCacheProfile(
        field_columns=fields,
        warmup_bars=merged.warmup_bars,
        forward_bars=forward_bars,
        max_disk_bytes=int(max_disk_bytes),
        generation=generation,
    )


def _normalize_signal_name(signal: str) -> str:
    if signal.startswith(("signal_", "csg_")):
        return signal
    return f"signal_{signal}"


def _filter_dependencies(strategy: StrategyDef, params: dict) -> tuple[set[str], bool]:
    if strategy.filter_history_fn:
        return set(strategy.required_features), bool(strategy.required_features)
    if not strategy.filter_fn:
        return set(), True
    try:
        expr = strategy.filter_fn(pl.DataFrame(), params)
        if expr is None:
            return set(), True
        return set(expr.meta.root_names()), True
    except Exception as exc:
        logger.warning("strategy filter dependency resolution failed: %s", exc)
        return set(strategy.required_features), bool(strategy.required_features)


def _basic_filter_dependencies(config: dict) -> set[str]:
    if not config or not config.get("enabled", True):
        return set()
    dependencies = {"symbol", "close"}
    if any(config.get(key) is not None for key in ("amount_min", "amount_max")):
        dependencies.add("amount")
    if any(config.get(key) is not None for key in ("turnover_min", "turnover_max")):
        dependencies.add("turnover_rate")
    if any(config.get(key) is not None for key in ("market_cap_min", "market_cap_max")):
        dependencies.add("total_shares")
    if any(config.get(key) is not None for key in ("float_cap_min", "float_cap_max")):
        dependencies.add("float_shares")
    if config.get("exclude_st"):
        dependencies.add("name")
    return dependencies


_STOCK_ONLY_FILTER_KEYS = (
    "market_cap_min", "market_cap_max", "float_cap_min", "float_cap_max",
    "turnover_min", "turnover_max", "price_min", "price_max", "boards",
)


def _basic_filter_for_asset(basic_filter: dict, asset_type: str) -> dict:
    if asset_type == "stock" or not basic_filter:
        return basic_filter
    sanitized = dict(basic_filter)
    for key in _STOCK_ONLY_FILTER_KEYS:
        sanitized[key] = None
    return sanitized


def _resolve_base_columns(features: set[str]) -> frozenset[str]:
    storage = set(ENRICHED_STORAGE_COLS)
    base = {"symbol", "date"} | (features & storage)
    close_indicators = set(INDICATOR_COLUMNS) - {
        "atr_14", "amplitude", "kdj_k", "kdj_d", "kdj_j",
        "vol_ma5", "vol_ma10", "vol_ratio_5d",
    }
    if features & close_indicators:
        base.add("close")
    if features & {"atr_14", "amplitude", "kdj_k", "kdj_d", "kdj_j"}:
        base.update({"high", "low", "close"})
    if features & {"vol_ma5", "vol_ma10", "vol_ratio_5d"}:
        base.add("volume")
    base.update({"open", "high", "low", "close", "volume"})
    return frozenset(base & storage)


@dataclass(frozen=True)
class SimulationOptions:
    include_monte_carlo: bool = True
    include_curves: bool = True
    include_trades: bool = True
    include_per_symbol_stats: bool = True
    include_return_distribution: bool = True


@dataclass(frozen=True)
class BacktestResultPolicy:
    required_stats: frozenset[str] | None = None
    include_monte_carlo: bool = True
    include_curves: bool = True
    include_trades: bool = True
    include_per_symbol_stats: bool = True
    include_return_distribution: bool = True
    include_benchmark: bool = True
    include_strategy_info: bool = True

    @classmethod
    def optimizer_trial(cls, objective: str) -> BacktestResultPolicy:
        return cls(
            required_stats=frozenset({str(objective)}),
            include_monte_carlo=str(objective).startswith("mc_maxdd_"),
            include_curves=False,
            include_trades=False,
            include_per_symbol_stats=False,
            include_return_distribution=False,
            include_benchmark=False,
            include_strategy_info=False,
        )

    def simulation_options(self) -> SimulationOptions:
        return SimulationOptions(
            include_monte_carlo=self.include_monte_carlo,
            include_curves=self.include_curves,
            include_trades=self.include_trades,
            include_per_symbol_stats=self.include_per_symbol_stats,
            include_return_distribution=self.include_return_distribution,
        )

    def select_stats(self, stats: dict) -> dict:
        if self.required_stats is None:
            return stats
        diagnostic = {
            "error", "timing_ms", "execution", "selection", "execution_backend",
            "shared_market_data", "shared_market_data_bytes", "shared_prepare_timing_ms",
            "matrix_data_cache_hit", "matrix_compute_cache", "market_matrix_shape",
            "market_matrix_bytes", "panel_rows", "panel_columns", "feature_columns",
            "full_feature_fallback",
        }
        keep = set(self.required_stats) | diagnostic
        return {key: value for key, value in stats.items() if key in keep}


def _factor_attribution_summary(snapshot: pl.DataFrame, trades: list) -> dict | None:
    factor_cols = [c for c in snapshot.columns if c not in ("symbol", "date")]
    if not factor_cols or not trades:
        return None
    normalized = snapshot.with_columns(pl.col("date").cast(pl.Utf8).str.slice(0, 10).alias("date"))
    symbols: list[str] = []
    days: list[str] = []
    pnls: list[float] = []
    for trade in trades:
        day = getattr(trade, "entry_signal_date", None) or getattr(trade, "entry_date", None)
        if day is None:
            continue
        symbols.append(trade.symbol)
        days.append(str(day)[:10])
        pnls.append(float(trade.pnl_pct))
    if not symbols:
        return None
    frame = pl.DataFrame({"symbol": symbols, "date": days, "pnl_pct": pnls})
    joined = frame.join(normalized, on=["symbol", "date"], how="left")
    win = joined.filter(pl.col("pnl_pct") > 0)
    lose = joined.filter(pl.col("pnl_pct") <= 0)
    factors: list[dict] = []
    for col in factor_cols:
        win_vals = win.get_column(col).drop_nulls().cast(pl.Float64)
        lose_vals = lose.get_column(col).drop_nulls().cast(pl.Float64)
        if win_vals.is_empty() and lose_vals.is_empty():
            continue
        factors.append({
            "factor": col,
            "win_mean": round(float(win_vals.mean()), 6) if not win_vals.is_empty() else None,
            "lose_mean": round(float(lose_vals.mean()), 6) if not lose_vals.is_empty() else None,
            "win_n": int(win_vals.len()),
            "lose_n": int(lose_vals.len()),
        })
    if not factors:
        return None
    return {"factors": factors, "n_win": win.height, "n_lose": lose.height}


@dataclass
class StrategyBacktestConfig:
    strategy_id: str
    symbols: list[str] | None
    start: date
    end: date
    params: dict | None = None
    overrides: dict | None = None
    # matching 为向后兼容入口; 显式传 entry_fill/exit_fill 时以二者为准。
    matching: Literal["close_t", "open_t+1"] = "open_t+1"
    entry_fill: Literal["close_t", "open_t+1"] | None = None
    exit_fill: Literal["close_t", "open_t+1"] | None = None
    fees_pct: float = 0.0002
    slippage_bps: float = 5.0
    max_positions: int = 10
    max_exposure_pct: float = 1.0
    initial_capital: float = 1_000_000.0
    position_sizing: Literal["equal", "score_weight"] = "equal"
    mode: Literal["position", "full"] = "position"
    asset_type: str = "stock"
    holding_days: int = 5

    def __post_init__(self) -> None:
        if self.entry_fill is None:
            self.entry_fill = self.matching
        if self.exit_fill is None:
            self.exit_fill = self.matching


@dataclass
class StrategyBacktestResult:
    run_id: str
    config: dict
    stats: dict = field(default_factory=dict)
    equity_curve: list[dict] = field(default_factory=list)
    drawdown_curve: list[dict] = field(default_factory=list)
    benchmark_curve: list[dict] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)
    per_symbol_stats: list[dict] = field(default_factory=list)
    strategy_info: dict = field(default_factory=dict)
    factor_attribution: dict | None = None
    elapsed_ms: float = 0.0
    error: str | None = None


class StrategyBacktestService:
    def __init__(
        self,
        engine: BacktestEngine,
        strategy_engine: StrategyEngine,
    ) -> None:
        self.engine = engine
        self.strategy_engine = strategy_engine

    def run(
        self,
        config: StrategyBacktestConfig,
        progress_cb: "Callable[[dict], None] | None" = None,
        cancel_event: "threading.Event | None" = None,
        *,
        prepared=None,
        result_policy: BacktestResultPolicy | None = None,
    ) -> StrategyBacktestResult:
        del prepared
        result_policy = result_policy or BacktestResultPolicy()
        t0 = time.perf_counter()
        run_id = uuid.uuid4().hex[:10]

        def _err(msg: str) -> StrategyBacktestResult:
            return StrategyBacktestResult(
                run_id=run_id,
                config=self._config_to_dict(config),
                error=msg,
                elapsed_ms=(time.perf_counter() - t0) * 1000,
            )

        # 获取策略定义
        try:
            s = self.strategy_engine.get(config.strategy_id)
        except ValueError as e:
            return _err(str(e))

        params = self._normalize_params(config.params or {}, s)
        overrides = config.overrides or {}
        basic_filter = self._effective_basic_filter(s, overrides)
        entry_signals = self._effective_signals(overrides, "entry_signals", s.entry_signals)
        exit_signals = self._effective_signals(overrides, "exit_signals", s.exit_signals)
        stop_loss = self._override_value(overrides, "stop_loss", s.stop_loss)
        take_profit = self._normalize_pct(
            self._override_value(overrides, "take_profit", getattr(s, "take_profit", None)),
            0.01,
            5.0,
        )
        trailing_stop = self._normalize_pct(
            self._override_value(overrides, "trailing_stop", getattr(s, "trailing_stop", None)),
            0.005,
            0.5,
        )
        trailing_take_profit_activate = self._normalize_pct(
            self._override_value(overrides, "trailing_take_profit_activate", getattr(s, "trailing_take_profit_activate", None)),
            0.01,
            2.0,
        )
        trailing_take_profit_drawdown = self._normalize_pct(
            self._override_value(overrides, "trailing_take_profit_drawdown", getattr(s, "trailing_take_profit_drawdown", None)),
            0.005,
            0.5,
        )
        if trailing_take_profit_activate is not None and trailing_take_profit_drawdown is not None:
            trailing_take_profit_drawdown = min(trailing_take_profit_drawdown, trailing_take_profit_activate)
        max_hold_days = self._override_value(overrides, "max_hold_days", s.max_hold_days)
        score_min, score_max = self._normalize_score_range(
            overrides.get("score_min"),
            overrides.get("score_max"),
        )

        timing_ms: dict[str, float] = {}

        # 加载面板 (含 warmup + 全量指标 + 信号)。warmup 只用于指标/形态计算, 不参与正式交易。
        warmup_days = max(120, int(max(s.lookback_days or 1, 1) * 1.5))
        load_start = config.start - timedelta(days=warmup_days)

        # 全量模式: entries 只在正式区间触发, exits 需要 end 之后的尾部数据继续执行策略卖点。
        # 若策略有 max_hold_days, 用它决定尾部窗口；否则 holding_days 只作为兜底观察上限。
        full_horizon_days = int(max_hold_days or config.holding_days or 5)
        full_horizon_days = max(full_horizon_days, 1)
        load_end = config.end
        if config.mode == "full":
            fwd_buffer = full_horizon_days + 5  # 多取几天, 容错停牌缺口/open_t+1
            load_end = config.end + timedelta(days=fwd_buffer * 2)  # 日历日放宽, 确保覆盖 N 个交易日

        t_load = time.perf_counter()
        panel = self.engine.load_panel(
            config.symbols,
            load_start,
            load_end,
            asset_type=getattr(config, "asset_type", "stock") or "stock",
        )
        timing_ms["load_panel"] = round((time.perf_counter() - t_load) * 1000, 1)
        if panel.is_empty():
            return _err("无数据，请检查日期范围或先运行盘后管道")

        formal_range = self._date_range_mask(panel, config.start, config.end)
        if not formal_range.any():
            return _err("正式回测区间内无数据")

        t_signal = time.perf_counter()

        # basic_filter 只影响买入候选, 不能删除行情 panel, 否则持仓 mark / 卖出 / full forward return 都会失真。
        basic_mask = pl.Series("_basic", [True] * len(panel), dtype=pl.Boolean)
        if basic_filter and basic_filter.get("enabled", True):
            expr = StrategyEngine._basic_filter_expr(panel, basic_filter)
            if expr is not None:
                try:
                    basic_mask = panel.select(expr.alias("_basic"))["_basic"].fill_null(False).cast(pl.Boolean)
                except Exception as e:  # noqa: BLE001
                    logger.warning("basic_filter mask failed: %s", e)
                    return _err(f"基础过滤计算失败: {e}")

        # 策略候选层用于评分归一化；entry_signals 只是买点层, 不参与 score universe。
        candidate_filter_mask = self._build_candidate_filter_mask(panel, s, params)
        candidate_mask = basic_mask & candidate_filter_mask
        panel = self._apply_score(panel, s, overrides, universe_mask=candidate_mask)

        entry_mask = self._build_entry_mask_from_candidate(panel, candidate_mask, s, entry_signals)
        entry_mask = entry_mask & formal_range
        raw_exit_mask = self._build_signal_mask(panel, exit_signals, "_exit")
        exit_mask = raw_exit_mask & (self._date_range_mask(panel, config.start, load_end) if config.mode == "full" else formal_range)
        timing_ms["signals_score"] = round((time.perf_counter() - t_signal) * 1000, 1)

        if not entry_mask.any():
            return _err("在指定区间内未产生买入信号")

        # warmup 之后才交给撮合；full mode 保留 end 之后前瞻段用于 shift(-N)。
        sim_end = load_end if config.mode == "full" else config.end
        sim_range = self._date_range_mask(panel, config.start, sim_end)
        sim_panel = panel.filter(sim_range)
        sim_entry_mask = entry_mask.filter(sim_range)
        sim_exit_mask = exit_mask.filter(sim_range)
        if sim_panel.is_empty():
            return _err("正式回测区间内无数据")

        t_sim = time.perf_counter()
        matcher_config = MatcherConfig(
            matching=config.matching,
            entry_fill=config.entry_fill,
            exit_fill=config.exit_fill,
            fees_pct=config.fees_pct,
            slippage_bps=config.slippage_bps,
            stop_loss_pct=stop_loss,
            take_profit_pct=take_profit,
            trailing_stop_pct=trailing_stop,
            trailing_take_profit_activate_pct=trailing_take_profit_activate,
            trailing_take_profit_drawdown_pct=trailing_take_profit_drawdown,
            max_hold_days=max_hold_days,
            max_positions=config.max_positions,
            max_exposure_pct=config.max_exposure_pct,
            score_min=score_min,
            score_max=score_max,
            initial_capital=config.initial_capital,
            position_sizing=config.position_sizing,
        )
        # 撮合 — full 为全候选独立执行；position 为账户级仓位模拟。
        if config.mode == "full":
            result = self.engine.simulate_independent_candidates(
                sim_panel,
                sim_entry_mask,
                sim_exit_mask,
                matcher_config,
                progress_cb,
                cancel_event,
            )
        else:
            result = self.engine.simulate_portfolio(sim_panel, sim_entry_mask, sim_exit_mask, matcher_config, progress_cb, cancel_event)
        timing_ms["simulate"] = round((time.perf_counter() - t_sim) * 1000, 1)

        # 检查是否被取消
        if cancel_event is not None and cancel_event.is_set():
            return StrategyBacktestResult(
                run_id=run_id,
                config=self._config_to_dict(config),
                error="cancelled",
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
            )

        if result.stats.get("error"):
            return _err(result.stats["error"])

        timing_ms["total"] = round((time.perf_counter() - t0) * 1000, 1)
        result.stats["timing_ms"] = timing_ms
        result.stats["panel_rows"] = int(sim_panel.height)

        benchmark_curve = self._build_benchmark_curve(config.start, config.end)

        # 构建策略信息
        strategy_info = {
            "id": s.meta.get("id", config.strategy_id),
            "name": s.meta.get("name", config.strategy_id),
            "description": s.meta.get("description", ""),
            "entry_signals": entry_signals,
            "exit_signals": exit_signals,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "trailing_stop": trailing_stop,
            "trailing_take_profit_activate": trailing_take_profit_activate,
            "trailing_take_profit_drawdown": trailing_take_profit_drawdown,
            "max_hold_days": max_hold_days,
            "full_horizon_days": full_horizon_days,
            "score_min": score_min,
            "score_max": score_max,
            "source": s.source,
        }

        elapsed = (time.perf_counter() - t0) * 1000

        return StrategyBacktestResult(
            run_id=run_id,
            config=self._config_to_dict(config),
            stats=result_policy.select_stats(result.stats),
            equity_curve=result.equity_curve if result_policy.include_curves else [],
            drawdown_curve=result.drawdown_curve if result_policy.include_curves else [],
            benchmark_curve=benchmark_curve if result_policy.include_benchmark else [],
            trades=[self._trade_to_dict(t) for t in result.trades] if result_policy.include_trades else [],
            per_symbol_stats=result.per_symbol_stats if result_policy.include_per_symbol_stats else [],
            strategy_info=strategy_info if result_policy.include_strategy_info else {},
            elapsed_ms=round(elapsed, 1),
        )

    # ── 全量模拟 (选股能力统计, 不建组合不算净值) ──

    def _run_full_simulation(
        self,
        panel: pl.DataFrame,
        entry_mask: pl.Series,
        holding_days: int,
    ) -> SimResult:
        """对 entry_mask 命中的全部候选, 算持有 N 天后的前瞻收益统计。

        不受 max_positions/资金约束, 反映策略选股能力本身。
        equity_curve 复用为"累计日均超额收益曲线"(基准归零)。
        """
        n = holding_days if holding_days and holding_days > 0 else 5

        df = panel.with_columns([
            entry_mask.cast(pl.Boolean).alias("_is_candidate"),
            (pl.col("close").shift(-n).over("symbol") / pl.col("close") - 1).alias("_fwd_return"),
        ]).filter(
            pl.col("_is_candidate")
            & pl.col("_fwd_return").is_not_null()
            & pl.col("_fwd_return").is_not_nan()
        )

        if df.is_empty():
            return self.engine._empty_result()

        fwd = df["_fwd_return"].to_numpy()
        wins = fwd[fwd > 0]
        losses = fwd[fwd <= 0]
        avg_win = float(wins.mean()) if wins.size else 0.0
        avg_loss = abs(float(losses.mean())) if losses.size else 0.0

        # 按日聚合: 当日候选的平均前瞻收益
        daily = (
            df.group_by("date").agg(
                pl.col("_fwd_return").mean().alias("avg_ret"),
                pl.col("_fwd_return").count().alias("n_cand"),
            ).sort("date")
        )

        # 累计超额曲线: 每日复利平均收益 (基准归零, 故 equity 即累计策略收益)
        equity_curve: list[dict] = []
        equity = 1.0
        peak = 1.0
        drawdown_curve: list[dict] = []
        for row in daily.iter_rows(named=True):
            ret = float(row["avg_ret"] or 0.0)
            equity *= (1 + ret)
            peak = max(peak, equity)
            dd = (equity - peak) / peak if peak > 0 else 0.0
            d_str = str(row["date"])[:10]
            equity_curve.append({
                "date": d_str,
                "value": round(equity, 4),
                "positions": int(row["n_cand"]),
            })
            drawdown_curve.append({"date": d_str, "value": round(dd, 4)})

        # 同期上证收益 (用 benchmark close 算)
        benchmark_curve = self._build_benchmark_curve(
            daily["date"].min(), daily["date"].max()
        )
        benchmark_return = 0.0
        if benchmark_curve:
            closes = [b["close"] for b in benchmark_curve if b.get("close")]
            if len(closes) >= 2 and closes[0] > 0:
                benchmark_return = closes[-1] / closes[0] - 1

        total_return = equity - 1.0
        max_dd = min((d["value"] for d in drawdown_curve), default=0.0)

        # 日收益序列算 Sharpe (年化)
        daily_rets = daily["avg_ret"].to_numpy()
        sharpe = (
            float(daily_rets.mean() / daily_rets.std() * np.sqrt(252))
            if daily_rets.size > 1 and daily_rets.std() > 0 else 0.0
        )

        # 收益分布直方图: 按 [-20%, +20%] 分 21 档 (每档 2%), 超出归入首尾档
        lo, hi, nbins = -0.20, 0.20, 20
        clipped = np.clip(fwd, lo, hi)
        counts, edges = np.histogram(clipped, bins=nbins, range=(lo, hi))
        dist = [
            {
                "range": f"{(edges[i]*100):+.0f}~{(edges[i+1]*100):+.0f}%",
                "count": int(counts[i]),
                "ratio": round(float(counts[i] / fwd.size), 4) if fwd.size else 0.0,
            }
            for i in range(nbins)
        ]

        stats = {
            "mode": "full",
            "n_candidates": int(fwd.size),
            "n_days": int(daily.height),
            "avg_daily_candidates": round(float(daily["n_cand"].mean()), 1),
            "avg_return": round(float(fwd.mean()), 4),
            "median_return": round(float(np.median(fwd)), 4),
            "win_rate": round(float(wins.size / fwd.size), 4) if fwd.size else 0.0,
            "profit_factor": round(avg_win / avg_loss, 2) if avg_loss > 0 else None,
            "best": round(float(fwd.max()), 4),
            "worst": round(float(fwd.min()), 4),
            "total_return": round(float(total_return), 4),
            "max_drawdown": round(float(max_dd), 4),
            "sharpe": round(sharpe, 2),
            "benchmark_return": round(float(benchmark_return), 4),
            "excess": round(float(total_return - benchmark_return), 4),
            "return_distribution": dist,
        }

        return SimResult(
            equity_curve=equity_curve,
            drawdown_curve=drawdown_curve,
            trades=[],
            per_symbol_stats=[],
            stats=stats,
        )

    # ── 向量化信号生成 ──

    @staticmethod
    def _date_range_mask(panel: pl.DataFrame, start: date, end: date) -> pl.Series:
        return panel.select(
            ((pl.col("date") >= start) & (pl.col("date") <= end)).alias("_range")
        )["_range"].fill_null(False).cast(pl.Boolean)

    def _build_candidate_filter_mask(
        self,
        panel: pl.DataFrame,
        s: StrategyDef,
        params: dict,
    ) -> pl.Series:
        """生成策略候选层 mask。filter_history/filter 决定候选池, 不包含 entry_signals。"""
        false_mask = pl.Series("_candidate_filter", [False] * len(panel), dtype=pl.Boolean)
        true_mask = pl.Series("_candidate_filter", [True] * len(panel), dtype=pl.Boolean)

        history_failed = False
        # 优先: filter_history_fn 策略 (涨停/反包等多日形态, 与选股路径共用同一逻辑)
        if s.filter_history_fn:
            try:
                hit_df = s.filter_history_fn(panel, params)
                if hit_df is None or hit_df.is_empty():
                    return false_mask
                # 命中行 (symbol,date) → 转 panel 等长布尔 mask
                hits = hit_df.select(["symbol", "date"]).unique()
                marked = (
                    panel.select(["symbol", "date"])
                    .join(
                        hits.with_columns(pl.lit(True).alias("_hit")),
                        on=["symbol", "date"],
                        how="left",
                    )
                )
                return marked["_hit"].fill_null(False).cast(pl.Boolean)
            except Exception as e:
                history_failed = True
                logger.warning("strategy filter_history_fn failed: %s", e)
                # 失败则回退到 filter_fn (若存在)

        # 策略 filter_fn: 候选层 (filter_history 不可用或失败时)
        if s.filter_fn:
            try:
                expr = s.filter_fn(panel, params)
                if expr is not None:
                    result = panel.select(expr.alias("_candidate_filter"))
                    if not result.is_empty():
                        return result["_candidate_filter"].fill_null(False).cast(pl.Boolean)
            except Exception as e:
                logger.warning("strategy filter_fn failed: %s", e)
                return false_mask

        if history_failed:
            return false_mask

        # 没有策略候选层时, 由 entry_signals 直接决定买点。
        return true_mask

    @staticmethod
    def _build_regime_mask(
        timestamp_labels: tuple[str, ...],
        regime_filter: dict | None,
        data_dir: Path | None,
        *,
        required_start: date | None = None,
        required_end: date | None = None,
    ):
        """构造逐日 T-1 regime mask; 委托本地 regime_alignment, 兼容 908 测试入口。"""
        if not regime_filter:
            return None
        allowed_states = set(regime_filter.get("states") or [])
        min_score = regime_filter.get("min_score")
        if not allowed_states and min_score is None:
            return None
        if data_dir is None:
            raise ValueError("市场环境过滤不可用: 未找到环境数据目录")

        from app.backtest.regime_alignment import build_regime_filter_mask
        from app.services import regime_builder

        regime_df = regime_builder.load_regime_history(data_dir)
        regime_by_date = {
            row["date"]: {
                "state": row.get("state", ""),
                "score": row.get("score", 0),
            }
            for row in regime_df.iter_rows(named=True)
            if row.get("date") is not None
        }
        return build_regime_filter_mask(
            timestamp_labels,
            regime_filter,
            regime_by_date,
            required_start=required_start,
            required_end=required_end,
        )

    def _build_entry_mask_from_candidate(
        self,
        panel: pl.DataFrame,
        candidate_mask: pl.Series,
        s: StrategyDef,
        entry_signals: list[str],
    ) -> pl.Series:
        """向量化生成买入掩码：候选层 AND 买点层；无买点时只用策略候选层。"""
        signal_mask = self._build_signal_mask(panel, entry_signals, "_entry_signal")
        if entry_signals:
            return candidate_mask & signal_mask
        if s.filter_history_fn or s.filter_fn:
            return candidate_mask
        return pl.Series("_entry", [False] * len(panel), dtype=pl.Boolean)

    def _build_entry_mask(
        self,
        panel: pl.DataFrame,
        s: StrategyDef,
        params: dict,
        entry_signals: list[str],
    ) -> pl.Series:
        """兼容旧调用: 候选层 AND 买点层。"""
        candidate_mask = self._build_candidate_filter_mask(panel, s, params)
        return self._build_entry_mask_from_candidate(panel, candidate_mask, s, entry_signals)

    @staticmethod
    def _build_signal_mask(panel: pl.DataFrame, signals: list[str], name: str) -> pl.Series:
        """向量化合并信号列，多个信号 OR。支持内置 signal_ 与自定义 csg_ 前缀。"""
        masks: list[pl.Series] = []
        for sig in signals:
            # csg_ (自定义信号) 直接用；否则按 signal_ 解析
            col = sig if (sig.startswith("signal_") or sig.startswith("csg_")) else f"signal_{sig}"
            if col in panel.columns:
                masks.append(panel[col].fill_null(False).cast(pl.Boolean))

        if not masks:
            return pl.Series(name, [False] * len(panel), dtype=pl.Boolean)

        combined = masks[0]
        for m in masks[1:]:
            combined = combined | m
        return combined

    def _build_benchmark_curve(self, start: date, end: date) -> list[dict]:
        try:
            df = self.engine.repo.get_index_daily(BENCHMARK_SYMBOL, start, end, columns=["date", "close"])
        except Exception as e:
            logger.warning("load benchmark %s failed: %s", BENCHMARK_SYMBOL, e)
            return []

        if df.is_empty() or "close" not in df.columns:
            return []

        df = df.filter(pl.col("close").is_not_null() & (pl.col("close") > 0)).sort("date")
        if df.is_empty():
            return []

        return [
            {
                "date": str(row["date"])[:10],
                "value": round(float(row["close"]), 4),
                "close": round(float(row["close"]), 4),
                "name": "上证指数",
                "symbol": BENCHMARK_SYMBOL,
            }
            for row in df.iter_rows(named=True)
            if row["close"] is not None
        ]

    # ── 工具 ──

    @staticmethod
    def _effective_basic_filter(s: StrategyDef, overrides: dict) -> dict:
        basic_filter = dict(getattr(s, "basic_filter", None) or {})
        override_filter = overrides.get("basic_filter")
        if isinstance(override_filter, dict):
            basic_filter.update(override_filter)
        return basic_filter

    @staticmethod
    def _effective_signals(overrides: dict, key: str, default: list[str]) -> list[str]:
        value = overrides.get(key)
        if isinstance(value, list):
            return [str(v) for v in value if v]
        return list(default or [])

    @staticmethod
    def _override_value(overrides: dict, key: str, default):
        if key in overrides:
            return overrides.get(key)
        return default

    @staticmethod
    def _normalize_pct(value, min_value: float, max_value: float) -> float | None:
        if value is None or value == "":
            return None
        try:
            pct = abs(float(value))
        except (TypeError, ValueError):
            return None
        return min(max(pct, min_value), max_value)

    @staticmethod
    def _normalize_score_range(min_value, max_value) -> tuple[float | None, float | None]:
        def _bound(value) -> float | None:
            if value is None or value == "":
                return None
            try:
                score = float(value)
            except (TypeError, ValueError):
                return None
            if not np.isfinite(score):
                return None
            return min(max(score, 0.0), 100.0)

        score_min = _bound(min_value)
        score_max = _bound(max_value)
        if score_min is not None and score_max is not None and score_min > score_max:
            score_min, score_max = score_max, score_min
        return score_min, score_max

    @staticmethod
    def _normalize_params(params: dict, s: StrategyDef) -> dict:
        normalized = dict(params)
        for param in s.meta.get("params", []):
            pid = param.get("id")
            if not pid:
                continue
            value = normalized.get(pid, param.get("default"))
            p_type = param.get("type")
            if p_type in {"float", "int"}:
                try:
                    num = float(value)
                except (TypeError, ValueError):
                    num = float(param.get("default", 0) or 0)
                if param.get("min") is not None:
                    num = max(num, float(param["min"]))
                if param.get("max") is not None:
                    num = min(num, float(param["max"]))
                normalized[pid] = int(num) if p_type == "int" else num
            elif p_type == "select" and param.get("options"):
                normalized[pid] = value if value in param["options"] else param.get("default")
            elif p_type == "bool":
                if isinstance(value, bool):
                    normalized[pid] = value
                elif isinstance(value, str):
                    normalized[pid] = value.lower() == "true"
                else:
                    normalized[pid] = bool(param.get("default", False))
            else:
                normalized[pid] = value
        return normalized

    @staticmethod
    def _trade_to_dict(t) -> dict:
        return {
            "symbol": t.symbol,
            "name": t.name,
            "entry_date": str(t.entry_date) if isinstance(t.entry_date, date) else str(t.entry_date),
            "exit_date": str(t.exit_date) if isinstance(t.exit_date, date) else str(t.exit_date),
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "pnl_pct": t.pnl_pct,
            "duration": t.duration,
            "exit_reason": t.exit_reason,
            "shares": t.shares,
            "lots": t.lots,
            "position_pct": t.position_pct,
            "entry_value": t.entry_value,
            "exit_value": t.exit_value,
            "pnl_amount": t.pnl_amount,
            "entry_score": getattr(t, "entry_score", None),
            "entry_signal_date": str(t.entry_signal_date) if getattr(t, "entry_signal_date", None) is not None else None,
            "exit_signal_date": str(t.exit_signal_date) if getattr(t, "exit_signal_date", None) is not None else None,
            "blocked_exit_days": getattr(t, "blocked_exit_days", 0),
        }

    @staticmethod
    def _config_to_dict(c: StrategyBacktestConfig) -> dict:
        score_min, score_max = StrategyBacktestService._normalize_score_range(
            (c.overrides or {}).get("score_min"),
            (c.overrides or {}).get("score_max"),
        )
        return {
            "strategy_id": c.strategy_id,
            "symbols": c.symbols,
            "start": str(c.start),
            "end": str(c.end),
            "params": c.params,
            "overrides": c.overrides,
            "score_min": score_min,
            "score_max": score_max,
            "matching": c.matching,
            "entry_fill": c.entry_fill,
            "exit_fill": c.exit_fill,
            "fees_pct": c.fees_pct,
            "slippage_bps": c.slippage_bps,
            "max_positions": c.max_positions,
            "max_exposure_pct": c.max_exposure_pct,
            "initial_capital": c.initial_capital,
            "position_sizing": c.position_sizing,
            "mode": c.mode,
            "asset_type": getattr(c, "asset_type", "stock") or "stock",
            "holding_days": c.holding_days,
        }

    @staticmethod
    def _apply_score(
        panel: pl.DataFrame,
        s: StrategyDef,
        overrides: dict | None,
        universe_mask: pl.Series | None = None,
    ) -> pl.DataFrame:
        scoring = s.meta.get("scoring", {})
        scoring_overrides = (overrides or {}).get("scoring")
        if scoring_overrides:
            scoring = {**scoring, **scoring_overrides}

        work = panel
        has_universe = universe_mask is not None and len(universe_mask) == len(panel)
        if has_universe:
            work = work.with_columns(universe_mask.rename("_score_universe"))

        def _value_in_universe(col: str) -> pl.Expr:
            if has_universe:
                return pl.when(pl.col("_score_universe")).then(pl.col(col)).otherwise(None)
            return pl.col(col)

        def _finish(df: pl.DataFrame) -> pl.DataFrame:
            return df.drop("_score_universe") if "_score_universe" in df.columns else df

        if scoring:
            total_weight = sum(scoring.values())
            if total_weight > 0:
                score_parts: list[pl.Expr] = []
                for col, weight in scoring.items():
                    if col not in work.columns:
                        continue
                    w = weight / total_weight
                    value = _value_in_universe(col)
                    col_min = value.min().over("date")
                    col_max = value.max().over("date")
                    col_range = col_max - col_min
                    normalized = pl.when(col_range > 0).then(
                        (pl.col(col) - col_min) / col_range
                    ).otherwise(pl.lit(0.5))
                    if has_universe:
                        normalized = pl.when(pl.col("_score_universe")).then(normalized).otherwise(0.0)
                    score_parts.append(normalized * w)
                if score_parts:
                    score_expr = score_parts[0]
                    for part in score_parts[1:]:
                        score_expr = score_expr + part
                    return _finish(work.with_columns((score_expr * 100).fill_null(0).alias("score")))

        order_by = s.meta.get("order_by")
        if order_by and order_by != "score" and order_by in work.columns:
            direction = 1 if s.meta.get("descending", True) else -1
            score_expr = pl.col(order_by).fill_null(0) * direction
            if has_universe:
                score_expr = pl.when(pl.col("_score_universe")).then(score_expr).otherwise(0.0)
            return _finish(work.with_columns(score_expr.alias("score")))
        return _finish(work.with_columns(pl.lit(0.0).alias("score")))
