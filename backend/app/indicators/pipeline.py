"""enriched 表计算流水线(§7.5 / §7.7 Step 2)。

存储层 (enriched parquet):
  仅存储基础行情窄表 (14 列), 指标和信号由各服务即时计算。

  存储列: symbol, date, OHLCV(前复权), volume, amount,
          raw_close, raw_high, raw_low, turnover_rate,
          consecutive_limit_ups, consecutive_limit_downs

设计:
  - 100% Polars 表达式(SQL 窗口无法表达递归 EMA)
  - 每只标的独立计算(`.over("symbol")`)
  - 有 adj_factor 时先应用前复权再算指标;无因子时直接用 raw
  - streaming collect 控制内存
"""
from __future__ import annotations

import json
import logging
import shutil
import time
import uuid
from collections.abc import Callable
from pathlib import Path, PurePosixPath

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

from app.config import settings
from app.market_time import cn_today
from app.parquet import scan_enriched_parquet
from app.services.atomic_io import atomic_write_parquet, write_lineage_record
from app.share_capital import apply_historical_float_shares, load_share_history

logger = logging.getLogger(__name__)


# ── 自定义信号缓存 ─────────────────────────────────────
# 从 data/user_data/custom_signals/*.json 加载并编译为 Polars 表达式。
# 模块级缓存：首次调用时加载，invalidate_custom_signals() 后下次重载。
_custom_signal_exprs: dict[str, pl.Expr] | None = None


def _get_custom_signal_exprs() -> dict[str, pl.Expr]:
    """懒加载自定义信号表达式（带模块级缓存）。"""
    global _custom_signal_exprs
    if _custom_signal_exprs is None:
        from app.strategy import custom_signals
        try:
            sigs = custom_signals.load_all(settings.data_dir)
            _custom_signal_exprs = custom_signals.build_expressions(sigs)
        except Exception as e:
            logger.warning("custom signals load failed: %s", e)
            _custom_signal_exprs = {}
    return _custom_signal_exprs


def invalidate_custom_signals() -> None:
    """失效自定义信号缓存（保存/删除信号后调用，下次计算重新加载）。"""
    global _custom_signal_exprs
    _custom_signal_exprs = None


# 偏离值规则使用的滚动窗口 (日)
DEVIATION_WINDOWS: tuple[int, ...] = (3, 10, 30)

# 各板块基准指数 (偏离值规则的「对应指数」, 按交易所官方口径): 优先首选, 缺失时回退
# - 沪主板:   上证A指 → 上证指数
# - 科创板:   科创50 → 上证A指
# - 深主板:   深证A指 → 深证成指
# - 创业板:   创业板综合指数 → 深证A指
# - 北交所:   北证50 → 上证指数
# 本地保留 DEVIATION_WINDOWS / BENCH_KEYS / bench_rt_pct_for; 本阶段补回
# attach_deviation / load_benchmark / 盘中外推, 供 compute_enriched_history_window
# 与 test_abnormal_moves 板块基准段沿同一调用链执行。
_BENCHMARK_PREFERENCE: dict[str, list[str]] = {
    "SH": ["000002.SH", "000001.SH"],
    "STAR": ["000688.SH", "000002.SH"],
    "SZ": ["399107.SZ", "399001.SZ"],
    "GEM": ["399102.SZ", "399107.SZ"],
    "BJ": ["899050.BJ", "000001.SH"],
}
BENCHMARK_INDEX_SYMBOLS: frozenset[str] = frozenset(
    sym for cands in _BENCHMARK_PREFERENCE.values() for sym in cands
)
BENCH_KEYS: tuple[str, ...] = tuple(_BENCHMARK_PREFERENCE)


def _bench_rt_pct_of(index_quotes: pl.DataFrame | None, candidates: list[str]) -> float:
    """从实时指数行情取某交易所首选基准的今日涨跌 (小数制), 缺数据时 0。"""
    if index_quotes is None or index_quotes.is_empty():
        return 0.0
    df = index_quotes.filter(pl.col("symbol").is_in(candidates))
    if df.is_empty():
        return 0.0
    by_sym = {r["symbol"]: r for r in df.iter_rows(named=True)}
    for sym in candidates:
        row = by_sym.get(sym)
        if row is None:
            continue
        for col in ("change_pct", "pct", "pct_change"):
            v = row.get(col)
            if v is not None:
                return float(v) / 100.0
        if row.get("close") is not None and row.get("prev_close") is not None and row["prev_close"]:
            return float(row["close"] / row["prev_close"] - 1)
    return 0.0


def bench_rt_pct_for(index_quotes: pl.DataFrame | None, bench_key: str) -> float:
    """板块基准键的指数今日实时涨跌 (小数制), 供异动总览实时叠加。"""
    return _bench_rt_pct_of(index_quotes, _BENCHMARK_PREFERENCE.get(bench_key, []))


_benchmark_cache: dict[str, tuple[float, pl.DataFrame | None]] = {}
_BENCHMARK_CACHE_TTL = 600.0


def load_benchmark_momentum(data_dir: Path) -> pl.DataFrame | None:
    """读取指数日K, 计算各基准指数的滚动 N 日涨跌幅。

    返回长表: date, bench_key, bench_close, bench_mom3d, bench_mom10d, bench_mom30d。
    bench_key 为板块基准键 (SH/STAR/SZ/GEM/BJ, 见 _BENCHMARK_PREFERENCE)。
    bench_close 供盘中路径外推今日基准动量 (benchmark_momentum_today)。
    无可用指数数据时返回 None (偏离列置 null, 不阻塞主流程)。
    进程内按 data_dir 缓存 (TTL 10 分钟)。
    """
    now = time.monotonic()
    try:
        from app.services.kline_sync import daily_route
        route_token = daily_route()
    except Exception:  # noqa: BLE001
        route_token = "unresolved"
    key = f"{Path(data_dir).resolve()}|{route_token}"
    cached = _benchmark_cache.get(key)
    if cached is not None and now - cached[0] < _BENCHMARK_CACHE_TTL:
        return cached[1]
    if route_token == "unresolved":
        _benchmark_cache[key] = (now, None)
        return None

    frame: pl.DataFrame | None = None
    try:
        from app.services.kline_sync import filter_daily_cache, scan_usable_daily
        wanted: list[str] = []
        bench_of: dict[str, str] = {}
        for bench_key, candidates in _BENCHMARK_PREFERENCE.items():
            for sym in candidates:
                if sym not in bench_of:
                    wanted.append(sym)
                    bench_of[sym] = bench_key
        lf = scan_usable_daily(data_dir, table="kline_index_daily")
        if lf is None:
            _benchmark_cache[key] = (now, None)
            return None
        names = set(lf.collect_schema().names())
        keep = [c for c in ("symbol", "date", "close", "route") if c in names]
        df_idx = filter_daily_cache(
            lf.filter(pl.col("symbol").is_in(wanted))
            .select(keep)
            .sort(["symbol", "date"])
            .collect()
        )
        if df_idx is None:
            df_idx = pl.DataFrame()
        if "route" in df_idx.columns:
            df_idx = df_idx.drop("route")
        if not df_idx.is_empty():
            available = set(df_idx["symbol"].to_list())
            picked = [s for s in wanted if s in available]
            # 每个板块取优先级最高的可用基准; 全缺时回退到任一可用基准。
            # 同一基准可服务多个板块 (如科创50 缺失时科创板回退上证A指)。
            pairs: list[tuple[str, str]] = []
            for bench_key, candidates in _BENCHMARK_PREFERENCE.items():
                hit = next((s for s in candidates if s in available), None)
                if hit is None and picked:
                    hit = picked[0]
                if hit is not None:
                    pairs.append((hit, bench_key))
            df_bench = df_idx.filter(pl.col("symbol").is_in([p[0] for p in pairs]))
            if not df_bench.is_empty():
                df_bench = df_bench.with_columns(
                    pl.col("close").cast(pl.Float64, strict=False)
                ).with_columns([
                    (pl.col("close") / pl.col("close").shift(n).over("symbol") - 1).alias(f"_bm{n}")
                    for n in DEVIATION_WINDOWS
                ]).rename({f"_bm{n}": f"bench_mom{n}d" for n in DEVIATION_WINDOWS})
                key_map = pl.DataFrame({
                    "symbol": [p[0] for p in pairs],
                    "bench_key": [p[1] for p in pairs],
                })
                frame = (
                    df_bench.join(key_map, on="symbol", how="inner")
                    .select(["date", "bench_key", "close",
                             *[f"bench_mom{n}d" for n in DEVIATION_WINDOWS]])
                    .rename({"close": "bench_close"})
                    .unique(subset=["date", "bench_key"])
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("基准指数偏离数据加载失败: %s", exc)
        frame = None

    _benchmark_cache[key] = (now, frame)
    return frame


def _bench_key_expr() -> pl.Expr:
    """symbol → 板块基准键 (SH/STAR/SZ/GEM/BJ), 无法识别时 null。

    北交所按后缀; 沪市按 68 前缀区分科创板; 深市按 30 前缀区分创业板。
    与 abnormal_moves.board_of 的板块判定同口径。
    """
    code = pl.col("symbol").str.slice(0, 6)
    suffix = pl.col("symbol").str.slice(-2).str.to_uppercase()
    return (
        pl.when(suffix == "BJ").then(pl.lit("BJ"))
        .when((suffix == "SH") & code.str.starts_with("68")).then(pl.lit("STAR"))
        .when(suffix == "SH").then(pl.lit("SH"))
        .when((suffix == "SZ") & code.str.starts_with("30")).then(pl.lit("GEM"))
        .when(suffix == "SZ").then(pl.lit("SZ"))
        .otherwise(pl.lit(None, dtype=pl.Utf8))
    )


def attach_deviation_columns(df: pl.DataFrame, data_dir: Path) -> pl.DataFrame:
    """为已含 momentum_Nd 的 enriched 帧附着 deviate_Nd 偏离列 (全量/冷路径)。

    缺失的动量列 (如 momentum_3d 不在指标全集里) 就地按 close 补算,
    与 compute_indicators 在同一帧上的 shift 语义一致。
    基准按板块键匹配, join 不上的行 (新上市/基准缺失) 置 null。
    """
    if df.is_empty():
        return df
    bench = load_benchmark_momentum(data_dir)
    dev_cols = [f"deviate_{n}d" for n in DEVIATION_WINDOWS]
    if bench is None or bench.is_empty():
        return df.with_columns([pl.lit(None, dtype=pl.Float64).alias(c) for c in dev_cols])
    if "close" not in df.columns:
        logger.warning("偏离列附着跳过: 缺少 close 列")
        return df.with_columns([pl.lit(None, dtype=pl.Float64).alias(c) for c in dev_cols])
    missing = [n for n in DEVIATION_WINDOWS if f"momentum_{n}d" not in df.columns]
    if missing:
        df = df.sort(["symbol", "date"]).with_columns([
            (pl.col("close") / pl.col("close").shift(n).over("symbol") - 1).alias(f"momentum_{n}d")
            for n in missing
        ])
    out = (
        df.with_columns(_bench_key_expr().alias("_bench_ex"))
        .join(bench, left_on=["_bench_ex", "date"], right_on=["bench_key", "date"], how="left")
        .with_columns([
            (pl.col(f"momentum_{n}d") - pl.col(f"bench_mom{n}d")).alias(f"deviate_{n}d")
            for n in DEVIATION_WINDOWS
        ])
        .drop(["_bench_ex", "bench_close", *[f"bench_mom{n}d" for n in DEVIATION_WINDOWS]])
    )
    return out


def benchmark_momentum_today(
    data_dir: Path,
    index_quotes: pl.DataFrame | None = None,
) -> pl.DataFrame | None:
    """各板块基准指数的「今日」N 日动量 (盘中实时外推)。

    基准日K parquet 盘中不含今日, 今日基准收盘 = 昨收 × (1 + 实时涨跌)。
    N 日动量 = 今日基准收盘 / N 个交易日前的收盘 - 1; 板块与
    load_benchmark_momentum 的选基逻辑一致 (同一 TTL 缓存帧)。
    返回小表: bench_key, bench_mom3d, bench_mom10d, bench_mom30d。
    无基准数据时 None。
    """
    bench = load_benchmark_momentum(data_dir)
    if bench is None or bench.is_empty():
        return None
    from datetime import date as date_cls

    # Index-monitor dirty rows are stamped with date.today() (UTC on some
    # hosts) while the rest of the book uses Asia/Shanghai cn_today().
    # Exclude either calendar's "today" so realtime change is not stacked.
    cutoff = min(date_cls.today(), cn_today())
    bench = bench.filter(pl.col("date") < cutoff)
    if bench.is_empty():
        return None
    rows: list[dict[str, float | str | None]] = []
    for k in sorted(bench["bench_key"].unique().to_list()):
        sub = bench.filter(pl.col("bench_key") == k).sort("date")
        closes = sub["bench_close"]
        if closes.len() == 0:
            continue
        yesterday_close = closes[-1]
        rt = _bench_rt_pct_of(index_quotes, _BENCHMARK_PREFERENCE.get(k, []))
        row: dict[str, float | str | None] = {
            "bench_key": k,
        }
        for n in DEVIATION_WINDOWS:
            base = closes[-n] if closes.len() >= n else None
            row[f"bench_mom{n}d"] = (
                (yesterday_close * (1.0 + rt)) / base - 1.0
                if base is not None and yesterday_close is not None and base > 0
                else None
            )
        rows.append(row)
    if not rows:
        return None
    schema = {"bench_key": pl.Utf8, **{f"bench_mom{n}d": pl.Float64 for n in DEVIATION_WINDOWS}}
    return pl.DataFrame(rows, schema=schema)


def attach_deviation_columns_today(
    df: pl.DataFrame,
    data_dir: Path,
    index_quotes: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """为盘中单日 enriched 帧附着 deviate_Nd 偏离列 (增量热路径)。

    与 attach_deviation_columns 的区别: 入参是「仅今日」的单日帧, 无法用
    shift 补算动量, 直接使用帧上已有的 momentum_Nd (compute_enriched_today
    产出); 基准动量用 benchmark_momentum_today 的实时外推值。
    缺失动量的窗口 (如全量回退路径无 momentum_3d) 置 null, 不阻塞主流程。
    """
    dev_cols = [f"deviate_{n}d" for n in DEVIATION_WINDOWS]
    if df.is_empty():
        return df
    bench = benchmark_momentum_today(data_dir, index_quotes)
    if bench is None or bench.is_empty():
        return df.with_columns([
            pl.lit(None, dtype=pl.Float64).alias(c) for c in dev_cols if c not in df.columns
        ])
    exprs = [
        (pl.col(f"momentum_{n}d") - pl.col(f"bench_mom{n}d")).alias(f"deviate_{n}d")
        if f"momentum_{n}d" in df.columns
        else pl.lit(None, dtype=pl.Float64).alias(f"deviate_{n}d")
        for n in DEVIATION_WINDOWS
    ]
    return (
        df.with_columns(_bench_key_expr().alias("_bench_ex"))
        .join(bench, left_on="_bench_ex", right_on="bench_key", how="left")
        .with_columns(exprs)
        .drop(["_bench_ex", *[f"bench_mom{n}d" for n in DEVIATION_WINDOWS]])
    )


# enriched parquet 仅存储的列 (14 列)
ENRICHED_STORAGE_COLS = [
    "symbol", "date",
    "open", "high", "low", "close",          # 前复权
    "volume", "amount",
    "raw_close", "raw_high", "raw_low",       # 不复权原始价
    "turnover_rate",                           # 依赖当时的 float_shares, 不可回推
    "consecutive_limit_ups",                   # 递推状态, 需从历史 cum_sum
    "consecutive_limit_downs",
]


# ================================================================
# enriched 完整列清单 (存储 + 运行时计算)
# 供 AI 审查代码时参考: 策略/筛选/回测 可直接使用以下列名。
# 分类: 存储列 → 指标列 → 信号列 → JOIN 列
# ================================================================
ENRICHED_COLUMNS: dict[str, dict[str, str]] = {
    # ── 存储列 (parquet 持久化) ──────────────────────────
    "symbol":                  "股票代码",
    "date":                    "交易日期",
    "open":                    "前复权开盘价",
    "high":                    "前复权最高价",
    "low":                     "前复权最低价",
    "close":                   "前复权收盘价",
    "volume":                  "成交量",
    "amount":                  "成交额",
    "raw_close":               "原始收盘价(未复权)",
    "raw_high":                "原始最高价(未复权)",
    "raw_low":                 "原始最低价(未复权)",
    "turnover_rate":           "换手率",
    "consecutive_limit_ups":   "连板数",
    "consecutive_limit_downs": "连跌数",
    # ── 基础指标 ─────────────────────────────────────────
    "prev_close":              "前收盘价",
    "change_pct":              "日涨跌幅(小数, 如 0.05 = 5%)",
    "change_amount":           "日涨跌额",
    "amplitude":               "日振幅 (最高-最低)/昨收",
    # ── 均线 MA ──────────────────────────────────────────
    "ma5":                     "5日简单均线",
    "ma10":                    "10日简单均线",
    "ma20":                    "20日简单均线",
    "ma30":                    "30日简单均线",
    "ma60":                    "60日简单均线(季线)",
    # ── 指数均线 EMA ─────────────────────────────────────
    "ema5":                    "5日指数均线",
    "ema10":                   "10日指数均线",
    "ema20":                   "20日指数均线",
    "ema30":                   "30日指数均线",
    "ema60":                   "60日指数均线",
    # ── MACD ─────────────────────────────────────────────
    "macd_dif":                "MACD DIF线(快线-慢线)",
    "macd_dea":                "MACD DEA线(信号线)",
    "macd_hist":               "MACD柱状图 (DIF-DEA)×2",
    # ── 布林带 BOLL ──────────────────────────────────────
    "boll_upper":              "布林带上轨 MA20+2σ",
    "boll_lower":              "布林带下轨 MA20-2σ",
    # ── KDJ ──────────────────────────────────────────────
    "kdj_k":                   "KDJ K值",
    "kdj_d":                   "KDJ D值",
    "kdj_j":                   "KDJ J值 (3K-2D)",
    # ── ATR ──────────────────────────────────────────────
    "atr_14":                  "14日平均真实波幅",
    # ── 量价 ─────────────────────────────────────────────
    "vol_ma5":                 "5日成交均量",
    "vol_ma10":                "10日成交均量",
    "vol_ratio_5d":            "量比 (成交量/5日均量)",
    # ── 极值 ─────────────────────────────────────────────
    "high_60d":                "60日最高价",
    "low_60d":                 "60日最低价",
    # ── 动量 ─────────────────────────────────────────────
    "momentum_5d":             "5日动量(涨跌幅小数)",
    "momentum_10d":            "10日动量",
    "momentum_20d":            "20日动量",
    "momentum_30d":            "30日动量",
    "momentum_60d":            "60日动量",
    # ── 波动率 ───────────────────────────────────────────
    "annual_vol_20d":          "20日年化波动率",
    # ── RSI ──────────────────────────────────────────────
    "rsi_6":                   "6日相对强弱指标",
    "rsi_14":                  "14日相对强弱指标",
    "rsi_24":                  "24日相对强弱指标",
    # ── 信号列 (bool) ────────────────────────────────────
    "signal_ma_golden_5_20":   "MA5上穿MA20 (金叉)",
    "signal_ma_dead_5_20":     "MA5下穿MA20 (死叉)",
    "signal_ma_golden_20_60":  "MA20上穿MA60",
    "signal_macd_golden":      "MACD金叉 (DIF上穿DEA)",
    "signal_macd_dead":        "MACD死叉 (DIF下穿DEA)",
    "signal_ma20_breakout":    "收盘突破MA20上方",
    "signal_ma20_breakdown":   "收盘跌破MA20下方",
    "signal_n_day_high":       "创60日新高",
    "signal_n_day_low":        "创60日新低",
    "signal_boll_breakout_upper": "突破布林上轨",
    "signal_boll_breakdown_lower": "跌破布林下轨",
    "signal_volume_surge":     "放量 (量比≥2.0)",
    "signal_limit_up":         "涨停",
    "signal_limit_down":       "跌停",
    "signal_limit_down_recovery": "跌停翘板(跌停后回升)",
    "signal_broken_limit_up":  "炸板(最高触及涨停但收盘未封住)",
    # ── JOIN 列 (由 repository 从 instruments 表补充) ───
    "name":                    "股票名称 (来自 instruments)",
    "total_shares":            "总股本 (来自 instruments)",
    "float_shares":            "流通股本 (来自 instruments)",
}

# 仅供 AI/开发者快速索引: 按类别的列名列表
ENRICHED_COLUMNS_BY_CATEGORY: dict[str, list[str]] = {
    "storage":  [k for k in ENRICHED_COLUMNS if k in ENRICHED_STORAGE_COLS],
    "basic":    ["prev_close", "change_pct", "change_amount", "amplitude"],
    "ma":       ["ma5", "ma10", "ma20", "ma30", "ma60"],
    "ema":      ["ema5", "ema10", "ema20", "ema30", "ema60"],
    "macd":     ["macd_dif", "macd_dea", "macd_hist"],
    "boll":     ["boll_upper", "boll_lower"],
    "kdj":      ["kdj_k", "kdj_d", "kdj_j"],
    "atr":      ["atr_14"],
    "volume":   ["vol_ma5", "vol_ma10", "vol_ratio_5d"],
    "extremes": ["high_60d", "low_60d"],
    "momentum": ["momentum_5d", "momentum_10d", "momentum_20d", "momentum_30d", "momentum_60d"],
    "volatility": ["annual_vol_20d"],
    "rsi":      ["rsi_6", "rsi_14", "rsi_24"],
    "signals":  [k for k in ENRICHED_COLUMNS if k.startswith("signal_")],
    "join":     ["name", "total_shares", "float_shares"],
}

SIGNAL_DEPENDENCIES: dict[str, frozenset[str]] = {
    "signal_ma_golden_5_20": frozenset({"ma5", "ma20"}),
    "signal_ma_dead_5_20": frozenset({"ma5", "ma20"}),
    "signal_ma_golden_20_60": frozenset({"ma20", "ma60"}),
    "signal_macd_golden": frozenset({"macd_dif", "macd_dea"}),
    "signal_macd_dead": frozenset({"macd_dif", "macd_dea"}),
    "signal_ma20_breakout": frozenset({"close", "ma20"}),
    "signal_ma20_breakdown": frozenset({"close", "ma20"}),
    "signal_ma5_breakout": frozenset({"close", "ma5"}),
    "signal_ma5_breakdown": frozenset({"close", "ma5"}),
    "signal_ma10_breakout": frozenset({"close", "ma10"}),
    "signal_ma10_breakdown": frozenset({"close", "ma10"}),
    "signal_n_day_high": frozenset({"close", "high_60d"}),
    "signal_n_day_low": frozenset({"close", "low_60d"}),
    "signal_boll_breakout_upper": frozenset({"close", "boll_upper"}),
    "signal_boll_breakdown_lower": frozenset({"close", "boll_lower"}),
    "signal_volume_surge": frozenset({"vol_ratio_5d"}),
}

LIMIT_SIGNAL_OUTPUTS: frozenset[str] = frozenset({
    "signal_limit_up",
    "signal_limit_down",
    "signal_limit_down_recovery",
    "signal_broken_limit_up",
    "consecutive_limit_ups",
    "consecutive_limit_downs",
    "turnover_rate",
})

INDICATOR_COLUMNS: frozenset[str] = frozenset(
    col
    for category in ("basic", "ma", "ema", "macd", "boll", "kdj", "atr", "volume", "extremes", "momentum", "volatility", "rsi")
    for col in ENRICHED_COLUMNS_BY_CATEGORY[category]
)


def get_signal_dependencies() -> dict[str, frozenset[str]]:
    """内置信号 + 已编译自定义信号的字段依赖。"""
    deps = dict(SIGNAL_DEPENDENCIES)
    try:
        from app.strategy.custom_signals import _expr_root_columns

        for name, expr in _get_custom_signal_exprs().items():
            deps[name] = frozenset(_expr_root_columns(expr))
    except Exception:
        logger.exception("custom signal dependency resolution failed; using builtin map only")
    return deps


def _ema_alpha(span: int) -> float:
    return 2.0 / (span + 1)


def _math_half_up(expr: pl.Expr, decimals: int = 2) -> pl.Expr:
    """交易所四舍五入 (round half up)，替代 Python round()（银行家舍入）。

    round(2.625, 2) = 2.62  ← Python 银行家舍入
    exchange_round(2.625) = 2.63  ← 交易所四舍五入
    """
    factor = 10 ** decimals
    return (expr * factor + 0.5).floor() / factor


def _limit_price(prev: pl.Expr, limit_pct: pl.Expr, up: bool) -> pl.Expr:
    """用「分」为单位的整数算术计算涨跌停价，规避浮点精度问题。

    交易所涨跌停价 = round(prev × (1 ± limit), 2)，标准四舍五入。
    若直接用浮点 prev × (1 ± limit) 会丢精度：
      18.90 × 0.95 = 17.955，浮点存储为 17.954999..., 四舍五入后得 17.95（错）。
    本函数先把 prev 转成整数「分」(round 到分避免输入含厘误差)，
    再用整数系数 105/95、110/90、120/80、130/70 相乘后四舍五入回元，全程不丢精度。
    """
    sign = 1 if up else -1
    # limit_pct ∈ {0.05, 0.10, 0.20, 0.30} → 系数分子 105/95、110/90、120/80、130/70
    num = ((1 + sign * limit_pct) * 100).cast(pl.Int64)  # 105, 110, 120, 130 等
    cents = (prev * 100 + 0.5).floor().cast(pl.Int64)     # 价格转「分」(四舍五入到分)
    # cents × num / 100, 四舍五入到分(加 50)
    return (((cents * num + 50) // 100) / 100)


def _apply_adj_factor(raw: pl.DataFrame, factors: pl.DataFrame) -> pl.DataFrame:
    """对 raw K 线应用前复权 (forward adjustment)。

    adj_factor 结构: symbol, trade_date, ex_factor
    ex_factor 含义: 每次除权事件的 pre/post 比值(个股级,非累积)。

    前复权原理:
      - 保持最新价格不变,将历史价格向下调整以消除除权缺口
      - adjusted = raw × cumprod_at_D / total_cumprod
      - 等价于: adjusted = raw / (该日期之后所有事件的 ex_factor 乘积)
    """
    if factors.is_empty():
        return raw

    # 确保类型一致
    factors = factors.with_columns(
        pl.col("trade_date").cast(pl.Date, strict=False),
        pl.col("ex_factor").cast(pl.Float64, strict=False),
    ).select("symbol", "trade_date", "ex_factor").drop_nulls()

    if factors.is_empty():
        return raw

    # 去重 + 排序 + 累积乘积 (一趟完成)
    factors_sorted = (
        factors.sort(["symbol", "trade_date"])
        .unique(subset=["symbol", "trade_date"])
        .sort(["symbol", "trade_date"])
        .with_columns(
            pl.col("ex_factor").cum_prod().over("symbol").alias("cum_factor"),
        )
    )

    # 每个 symbol 的总累积因子
    total_factors = (
        factors_sorted
        .group_by("symbol")
        .agg(pl.col("cum_factor").last().alias("total_factor"))
    )

    raw_sorted = raw.sort(["symbol", "date"])

    # join_asof backward: 每根 K 线取 <= 其 date 的最新累积因子
    # 同时带 trade_date 列用于判断除权日标记
    df = raw_sorted.join_asof(
        factors_sorted.select("symbol", "trade_date", "cum_factor"),
        left_on="date",
        right_on="trade_date",
        by="symbol",
        strategy="backward",
    )

    # 补充 total_factor + 前复权 + 除权标记,一次 with_columns 完成
    df = df.join(total_factors, on="symbol", how="left")

    is_ex = pl.col("trade_date") == pl.col("date")
    ratio = pl.col("cum_factor").fill_null(1.0) / pl.col("total_factor").fill_null(1.0)
    price_cols = [c for c in ("open", "high", "low", "close") if c in df.columns]

    df = df.with_columns(
        [pl.col(c) * ratio for c in price_cols]
        + [
            is_ex.alias("ex_rights"),
        ]
    ).drop(["trade_date", "cum_factor", "total_factor"])

    return df


# ================================================================
# 技术指标计算 (从 OHLCV 计算)
# ================================================================

def compute_indicators(df: pl.DataFrame) -> pl.DataFrame:
    """从 OHLCV 数据计算全套技术指标。

    输入必须包含: symbol, date, open, high, low, close, volume
    返回添加了所有指标列的 DataFrame。
    """
    if df.is_empty():
        return df

    import time as _time
    _t0 = _time.perf_counter()

    df = df.sort(["symbol", "date"])

    # Pass 1: 均线 + EMA + MACD 基础 + BOLL 基础 + KDJ 基础 + ATR 基础 + 量价 + 极值
    prev_close = pl.col("close").shift(1).over("symbol")
    df = df.with_columns([
        # 前收盘价
        prev_close.alias("prev_close"),
        # MA (最大 MA60)
        pl.col("close").rolling_mean(5).over("symbol").alias("ma5"),
        pl.col("close").rolling_mean(10).over("symbol").alias("ma10"),
        pl.col("close").rolling_mean(20).over("symbol").alias("ma20"),
        pl.col("close").rolling_mean(30).over("symbol").alias("ma30"),
        pl.col("close").rolling_mean(60).over("symbol").alias("ma60"),
        # EMA (不含 ema12/ema26, MACD 内部自算)
        pl.col("close").ewm_mean(alpha=_ema_alpha(5), adjust=False).over("symbol").alias("ema5"),
        pl.col("close").ewm_mean(alpha=_ema_alpha(10), adjust=False).over("symbol").alias("ema10"),
        pl.col("close").ewm_mean(alpha=_ema_alpha(20), adjust=False).over("symbol").alias("ema20"),
        pl.col("close").ewm_mean(alpha=_ema_alpha(30), adjust=False).over("symbol").alias("ema30"),
        pl.col("close").ewm_mean(alpha=_ema_alpha(60), adjust=False).over("symbol").alias("ema60"),
        # MACD base (内部计算, 不存 ema12/ema26)
        pl.col("close").ewm_mean(alpha=_ema_alpha(12), adjust=False).over("symbol").alias("_ema12"),
        pl.col("close").ewm_mean(alpha=_ema_alpha(26), adjust=False).over("symbol").alias("_ema26"),
        # BOLL base
        pl.col("close").rolling_std(20).over("symbol").alias("_boll_std"),
        # KDJ base
        pl.col("low").rolling_min(9).over("symbol").alias("_kdj_ln"),
        pl.col("high").rolling_max(9).over("symbol").alias("_kdj_hn"),
        # ATR base
        pl.max_horizontal(
            pl.col("high") - pl.col("low"),
            (pl.col("high") - prev_close).abs(),
            (pl.col("low") - prev_close).abs(),
        ).alias("_tr"),
        # 量价 base
        pl.col("volume").rolling_mean(5).over("symbol").alias("vol_ma5"),
        pl.col("volume").rolling_mean(10).over("symbol").alias("vol_ma10"),
        pl.col("volume").rolling_mean(5).over("symbol").alias("_vol_ma5"),
        # 极值
        pl.col("close").rolling_max(60).over("symbol").alias("high_60d"),
        pl.col("close").rolling_min(60).over("symbol").alias("low_60d"),
    ])

    # Pass 2: MACD + BOLL (基于 Pass 1 基础列)
    df = df.with_columns([
        (pl.col("_ema12") - pl.col("_ema26")).alias("macd_dif"),
        (pl.col("ma20") + 2 * pl.col("_boll_std")).alias("boll_upper"),
        (pl.col("ma20") - 2 * pl.col("_boll_std")).alias("boll_lower"),
    ]).with_columns(
        pl.col("macd_dif").ewm_mean(alpha=_ema_alpha(9), adjust=False).over("symbol").alias("macd_dea"),
    ).with_columns(
        ((pl.col("macd_dif") - pl.col("macd_dea")) * 2).alias("macd_hist"),
    )

    # Pass 3: KDJ
    _kdj_rsv = (
        100 * (pl.col("close") - pl.col("_kdj_ln"))
        / (pl.col("_kdj_hn") - pl.col("_kdj_ln")).fill_null(1e-12)
    )
    df = df.with_columns([
        _kdj_rsv.ewm_mean(alpha=1.0 / 3, adjust=False).over("symbol").alias("kdj_k"),
    ]).with_columns([
        pl.col("kdj_k").ewm_mean(alpha=1.0 / 3, adjust=False).over("symbol").alias("kdj_d"),
    ]).with_columns([
        (3 * pl.col("kdj_k") - 2 * pl.col("kdj_d")).alias("kdj_j"),
    ])

    # Pass 4: ATR + 量比 + 动量 + 波动 + 涨跌幅 + 涨跌额 + 振幅
    df = df.with_columns(
        pl.col("_tr").ewm_mean(alpha=1.0 / 14, adjust=False).over("symbol").alias("atr_14"),
    ).with_columns(
        (pl.col("volume") / pl.col("_vol_ma5")).alias("vol_ratio_5d"),
    ).with_columns([
        # 动量: 5d/10d/20d/30d/60d
        (pl.col("close") / pl.col("close").shift(5).over("symbol") - 1).alias("momentum_5d"),
        (pl.col("close") / pl.col("close").shift(10).over("symbol") - 1).alias("momentum_10d"),
        (pl.col("close") / pl.col("close").shift(20).over("symbol") - 1).alias("momentum_20d"),
        (pl.col("close") / pl.col("close").shift(30).over("symbol") - 1).alias("momentum_30d"),
        (pl.col("close") / pl.col("close").shift(60).over("symbol") - 1).alias("momentum_60d"),
        # 日涨跌幅
        (pl.col("close") / pl.col("close").shift(1).over("symbol") - 1).alias("change_pct"),
    ]).with_columns(
        # 涨跌额
        (pl.col("close") - pl.col("close").shift(1).over("symbol")).alias("change_amount"),
    ).with_columns(
        # 振幅 = (high - low) / prev_close
        pl.when(pl.col("close").shift(1).over("symbol") > 0)
          .then((pl.col("high") - pl.col("low")) / pl.col("close").shift(1).over("symbol"))
          .otherwise(None)
          .alias("amplitude"),
    ).with_columns(
        # 日涨跌幅 (用于波动率)
        pl.col("close").pct_change().over("symbol").alias("_daily_pct"),
    ).with_columns(
        # 年化波动率
        (pl.col("_daily_pct").rolling_std(20).over("symbol") * (252 ** 0.5))
            .alias("annual_vol_20d"),
    )

    # Pass 5: RSI
    df = df.with_columns(
        pl.col("close").diff().over("symbol").alias("_delta"),
    ).with_columns([
        pl.when(pl.col("_delta") > 0).then(pl.col("_delta")).otherwise(0.0).alias("_gain"),
        pl.when(pl.col("_delta") < 0).then(-pl.col("_delta")).otherwise(0.0).alias("_loss"),
    ])
    for n in (6, 14, 24):
        a = 1.0 / n
        df = df.with_columns([
            pl.col("_gain").ewm_mean(alpha=a, adjust=False).over("symbol").alias(f"_rsi_avg_gain_{n}"),
            pl.col("_loss").ewm_mean(alpha=a, adjust=False).over("symbol").alias(f"_rsi_avg_loss_{n}"),
        ]).with_columns(
            (100 - 100 / (1 + pl.col(f"_rsi_avg_gain_{n}") /
                         pl.when(pl.col(f"_rsi_avg_loss_{n}") == 0)
                           .then(1e-12)
                           .otherwise(pl.col(f"_rsi_avg_loss_{n}"))
                         )).alias(f"rsi_{n}"),
        )

    # Pass 6: 换手率 (需要 float_shares, 后续在 compute_all 中 JOIN instruments 后补充)

    # 清理临时列
    df = df.drop(["_boll_std", "_tr", "_ema12", "_ema26",
                  "_kdj_ln", "_kdj_hn", "_vol_ma5", "_daily_pct",
                  "_delta", "_gain", "_loss",
                  "_rsi_avg_gain_6", "_rsi_avg_loss_6",
                  "_rsi_avg_gain_14", "_rsi_avg_loss_14",
                  "_rsi_avg_gain_24", "_rsi_avg_loss_24"])

    _elapsed = (_time.perf_counter() - _t0) * 1000
    import logging as _logging
    _logging.getLogger(__name__).debug("compute_indicators: %.1fms, %d rows", _elapsed, len(df))

    return df


def compute_signals(df: pl.DataFrame) -> pl.DataFrame:
    """从已有指标列计算原子信号布尔列。

    输入必须包含 compute_indicators() 产出的指标列。
    """
    if df.is_empty():
        return df

    df = df.with_columns([
        ((pl.col("ma5") > pl.col("ma20")) &
         (pl.col("ma5").shift(1).over("symbol") <= pl.col("ma20").shift(1).over("symbol")))
            .alias("signal_ma_golden_5_20"),
        ((pl.col("ma5") < pl.col("ma20")) &
         (pl.col("ma5").shift(1).over("symbol") >= pl.col("ma20").shift(1).over("symbol")))
            .alias("signal_ma_dead_5_20"),
        ((pl.col("ma20") > pl.col("ma60")) &
         (pl.col("ma20").shift(1).over("symbol") <= pl.col("ma60").shift(1).over("symbol")))
            .alias("signal_ma_golden_20_60"),
        ((pl.col("macd_dif") > pl.col("macd_dea")) &
         (pl.col("macd_dif").shift(1).over("symbol") <= pl.col("macd_dea").shift(1).over("symbol")))
            .alias("signal_macd_golden"),
        ((pl.col("macd_dif") < pl.col("macd_dea")) &
         (pl.col("macd_dif").shift(1).over("symbol") >= pl.col("macd_dea").shift(1).over("symbol")))
            .alias("signal_macd_dead"),
        ((pl.col("close") > pl.col("ma20")) &
         (pl.col("close").shift(1).over("symbol") <= pl.col("ma20").shift(1).over("symbol")))
            .alias("signal_ma20_breakout"),
        ((pl.col("close") < pl.col("ma20")) &
         (pl.col("close").shift(1).over("symbol") >= pl.col("ma20").shift(1).over("symbol")))
            .alias("signal_ma20_breakdown"),
        (pl.col("close") >= pl.col("high_60d")).alias("signal_n_day_high"),
        (pl.col("close") <= pl.col("low_60d")).alias("signal_n_day_low"),
        (pl.col("close") > pl.col("boll_upper")).alias("signal_boll_breakout_upper"),
        (pl.col("close") < pl.col("boll_lower")).alias("signal_boll_breakdown_lower"),
        (pl.col("vol_ratio_5d") >= 2.0).alias("signal_volume_surge"),
    ])

    # 自定义信号（用户配置的字段+运算符+值组合，编译为布尔列）。
    # 扩展表数值列先行 join (ext_ 因子列 = 帧上已有列): 信号条件与评分引用
    # 都按列存在性解析。历史多日帧仅注入时序模式 —— 快照代表"最新值",
    # 历史回看注入会引入未来数据 (CONTRIBUTING §5.3)。
    from app.factors import ext_factors
    df = ext_factors.attach_ext_columns(df, include_snapshot=False)
    # 条件引用的注册表因子列先复用评分物化管线补算 (虚拟/自定义/复合均可)。
    from app.strategy import custom_signals
    df = custom_signals.inject(df, _get_custom_signal_exprs())

    return df


def compute_limit_signals(
    df: pl.DataFrame,
    instruments: pl.DataFrame,
    historical_shares: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """计算涨跌停相关信号。

    产出:
      signal_limit_up, consecutive_limit_ups
      signal_limit_down, consecutive_limit_downs
      signal_limit_down_recovery (跌停翘板)
      signal_broken_limit_up (炸板: 最高价触及涨停价但收盘未封住)

    输入必须包含: symbol, date, raw_close, raw_high, open, high, low, close,
                  change_pct, vol_ratio_5d。
    """
    if df.is_empty():
        return df

    # 从 instruments 取 ST 标记 + 流通股本(换手率用)
    inst_cols = ["symbol"]
    if "name" in instruments.columns:
        inst_cols.append("name")
    if "float_shares" in instruments.columns:
        inst_cols.append("float_shares")
    inst_subset = instruments.select(inst_cols).unique(subset=["symbol"])

    if "name" in instruments.columns:
        st_flag = (
            instruments
            .select("symbol", pl.col("name").str.contains("ST").alias("_is_st"))
            .unique(subset=["symbol"])
        )
        inst_subset = inst_subset.join(st_flag, on="symbol", how="left")

    df = df.join(inst_subset, on="symbol", how="left", suffix="_inst")

    if historical_shares is not None and not historical_shares.is_empty():
        df = apply_historical_float_shares(df, historical_shares, today=cn_today())

    # 计算换手率(%) = volume(手) * 10000 / float_shares(股)
    if "float_shares" in df.columns and "volume" in df.columns:
        df = df.with_columns(
            pl.when(pl.col("float_shares") > 0)
              .then(pl.col("volume") * 10000.0 / pl.col("float_shares"))
              .otherwise(None)
              .alias("turnover_rate")
        )
    elif "turnover_rate" not in df.columns:
        df = df.with_columns(pl.lit(None).cast(pl.Float64).alias("turnover_rate"))

    # 前一日参考收盘价（交易所涨跌停基准价）
    # 仅在 adj_factor 发生变化（除权除息 XD/DR）时使用前复权昨收作为交易所参考价;
    # 否则使用原始 raw_close.shift(1) 以避免浮点精度误差。
    _adj_today = pl.col("close") / pl.col("raw_close")
    _adj_yesterday = pl.col("close").shift(1).over("symbol") / pl.col("raw_close").shift(1).over("symbol")
    _adj_changed = (_adj_today - _adj_yesterday).abs() > 1e-6
    df = df.with_columns(
        pl.when(_adj_changed)
        .then(pl.col("close").shift(1).over("symbol"))   # 除权: 使用前复权昨收
        .otherwise(pl.col("raw_close").shift(1).over("symbol"))  # 正常: 使用原始昨收
        .alias("_prev_raw_close")
    )

    # 板块涨跌停比例
    is_chinext = pl.col("symbol").str.starts_with("300") | pl.col("symbol").str.starts_with("301")
    is_star = pl.col("symbol").str.starts_with("688") | pl.col("symbol").str.starts_with("689")
    is_bj = pl.col("symbol").str.ends_with(".BJ")

    df = df.with_columns(
        pl.when(is_chinext).then(0.20)
        .when(is_star).then(0.20)
        .when(is_bj).then(0.30)
        .otherwise(0.10)
        .alias("_board_pct")
    )

    # ST → 5%（覆盖板块默认值）
    if "_is_st" in df.columns:
        df = df.with_columns(
            pl.when(pl.col("_is_st").fill_null(False))
            .then(0.05)
            .otherwise(pl.col("_board_pct"))
            .alias("_limit_pct")
        )
    else:
        df = df.with_columns(pl.col("_board_pct").alias("_limit_pct"))

    # 理论涨停价 = prev_close × (1 + limit_pct)  整数算术，避免浮点误差
    df = df.with_columns(
        _limit_price(pl.col("_prev_raw_close"), pl.col("_limit_pct"), up=True)
        .alias("_theoretical_limit_up")
    )

    # 理论跌停价 = prev_close × (1 - limit_pct)
    df = df.with_columns(
        _limit_price(pl.col("_prev_raw_close"), pl.col("_limit_pct"), up=False)
        .alias("_theoretical_limit_down")
    )

    # ── signal_limit_up ──
    df = df.with_columns(
        pl.when(
            pl.col("_prev_raw_close").is_not_null()
            & (pl.col("_prev_raw_close") > 0)
            & (pl.col("raw_close") > 0)
        ).then(
            (pl.col("raw_close") - pl.col("_theoretical_limit_up")).abs() < 0.005
        ).otherwise(None).cast(pl.Boolean)
        .alias("signal_limit_up")
    )

    # ── consecutive_limit_ups ──
    df = df.with_columns(
        (~pl.col("signal_limit_up").fill_null(False))
        .cast(pl.UInt32)
        .cum_sum()
        .over("symbol")
        .alias("_grp_up")
    ).with_columns(
        pl.col("signal_limit_up")
        .cast(pl.UInt32)
        .cum_sum()
        .over("symbol", "_grp_up")
        .cast(pl.UInt32)
        .alias("consecutive_limit_ups")
    ).with_columns(
        pl.when(pl.col("signal_limit_up").fill_null(False))
        .then(pl.col("consecutive_limit_ups"))
        .otherwise(0)
        .cast(pl.UInt32)
        .alias("consecutive_limit_ups")
    )

    # ── signal_limit_down ──
    df = df.with_columns(
        pl.when(
            pl.col("_prev_raw_close").is_not_null()
            & (pl.col("_prev_raw_close") > 0)
            & (pl.col("raw_close") > 0)
        ).then(
            (pl.col("raw_close") - pl.col("_theoretical_limit_down")).abs() < 0.005
        ).otherwise(None).cast(pl.Boolean)
        .alias("signal_limit_down")
    )

    # ── consecutive_limit_downs ──
    df = df.with_columns(
        (~pl.col("signal_limit_down").fill_null(False))
        .cast(pl.UInt32)
        .cum_sum()
        .over("symbol")
        .alias("_grp_down")
    ).with_columns(
        pl.col("signal_limit_down")
        .cast(pl.UInt32)
        .cum_sum()
        .over("symbol", "_grp_down")
        .cast(pl.UInt32)
        .alias("consecutive_limit_downs")
    ).with_columns(
        pl.when(pl.col("signal_limit_down").fill_null(False))
        .then(pl.col("consecutive_limit_downs"))
        .otherwise(0)
        .cast(pl.UInt32)
        .alias("consecutive_limit_downs")
    )

    # ── signal_limit_down_recovery (跌停翘板) ──
    # 条件: 当日最低价曾触及跌停价 + 最终没有跌停 + 收阳
    df = df.with_columns(
        pl.when(
            pl.col("_prev_raw_close").is_not_null()
            & (pl.col("_prev_raw_close") > 0)
        ).then(
            (~pl.col("signal_limit_down").fill_null(False))              # 最终没跌停
            & (pl.col("low") <= pl.col("_theoretical_limit_down") + 0.005)  # 曾触及跌停
            & (pl.col("close") > pl.col("open"))                          # 收阳
        ).otherwise(None).cast(pl.Boolean)
        .alias("signal_limit_down_recovery")
    )

    # ── signal_broken_limit_up (炸板) ──
    # 条件: 最高价曾触及涨停价 + 最终没有封住涨停
    df = df.with_columns(
        pl.when(
            pl.col("_prev_raw_close").is_not_null()
            & (pl.col("_prev_raw_close") > 0)
            & (pl.col("raw_high") > 0)
        ).then(
            (~pl.col("signal_limit_up").fill_null(False))               # 最终没封住涨停
            & (pl.col("raw_high") >= pl.col("_theoretical_limit_up") - 0.005)  # 曾触及涨停价
        ).otherwise(None).cast(pl.Boolean)
        .alias("signal_broken_limit_up")
    )

    # 清理临时列 + JOIN 引入的 instruments 列 (不存入 enriched)
    cleanup = ["_prev_raw_close", "_board_pct", "_limit_pct",
               "_theoretical_limit_up", "_theoretical_limit_down",
               "_grp_up", "_grp_down"]
    if "_is_st" in df.columns:
        cleanup.append("_is_st")
    # 清理 join 产生的重复列
    for c in df.columns:
        if c.endswith("_inst"):
            cleanup.append(c)
    # name 和 float_shares 只用于计算, 不存入 enriched
    for c in ["name", "float_shares"]:
        if c in df.columns and c != "turnover_rate":
            cleanup.append(c)
    df = df.drop([c for c in cleanup if c in df.columns])

    return df


def compute_all(
    df: pl.DataFrame,
    instruments: pl.DataFrame | None = None,
    historical_shares: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """从 OHLCV 计算全套指标 + 信号。一站式调用。

    输入: symbol, date, open, high, low, close, volume, amount, raw_close
    """
    df = compute_indicators(df)
    df = compute_signals(df)
    if instruments is not None and not instruments.is_empty():
        df = compute_limit_signals(df, instruments, historical_shares=historical_shares)

    # 清理 NaN / Inf
    float_cols = [c for c in df.columns if df[c].dtype.is_float()]
    if float_cols:
        df = df.with_columns([
            pl.when(pl.col(c).is_nan() | pl.col(c).is_infinite())
              .then(None)
              .otherwise(pl.col(c))
              .alias(c)
            for c in float_cols
        ])

    return df


def filter_halt_days(df: pl.DataFrame) -> pl.DataFrame:
    """过滤停牌日。

    停牌日的 open/high 必然为 0 (无集合竞价)。注意 close 可能被数据源
    填充为前收盘价而非 0, 因此不能用 "OHLC 全零" 判断, 否则会漏过这类
    停牌记录 (如 *ST 撤销风险警示的停牌日), 污染 MA/ATR 等指标。旧版实时
    落盘还会先把 open/high=0 填成 close, 对这类历史数据用零成交量和零成交额
    作为兼容判据。
    """
    if df.is_empty() or "open" not in df.columns or "high" not in df.columns:
        return df
    halted = (pl.col("open") == 0) & (pl.col("high") == 0)
    if "volume" in df.columns and "amount" in df.columns:
        halted = halted | ((pl.col("volume") == 0) & (pl.col("amount") == 0))
    return df.filter(~halted)


# ================================================================
# Pipeline: 盘后全量计算 + 写入
# ================================================================

def compute_enriched(
    raw: pl.DataFrame,
    factors: pl.DataFrame | None = None,
    instruments: pl.DataFrame | None = None,
    historical_shares: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """对原始日 K 应用前复权 + 全量计算指标 + 信号, 产出完整 enriched (含全部指标列)。

    输入应包含至少: symbol, date, open, high, low, close, volume (可选 amount)。
    如果提供了 factors, 先应用前复权再算指标。
    如果提供了 instruments, 计算涨跌停信号和换手率。
    """
    if raw.is_empty():
        return raw

    # 过滤停牌日 (会污染指标计算)
    raw = filter_halt_days(raw)

    if raw.is_empty():
        return raw

    # 保留不复权原始价格（涨停/炸板/跌停判断需用不复权价格）
    raw = raw.with_columns(
        pl.col("close").alias("raw_close"),
        pl.col("high").alias("raw_high"),
        pl.col("low").alias("raw_low"),
    )

    # 应用前复权（只改 open/high/low/close，raw_close 不受影响）
    if factors is not None and not factors.is_empty():
        raw = _apply_adj_factor(raw, factors)

    # 排序
    df = raw.sort(["symbol", "date"])

    # 全量计算指标 + 信号
    df = compute_all(df, instruments=instruments, historical_shares=historical_shares)

    return df


def _select_storage_cols(df: pl.DataFrame) -> pl.DataFrame:
    """写入 parquet 前裁剪到存储列 (14 列 + 可选 route)。"""
    cols = [c for c in ENRICHED_STORAGE_COLS if c in df.columns]
    if "route" in df.columns and "route" not in cols:
        cols.append("route")
    return df.select(cols)


def _prepare_enriched_storage(date_df: pl.DataFrame) -> pl.DataFrame | None:
    """Tag enriched storage and refuse unresolved daily writes."""
    from app.services.kline_sync import _tag_daily_route, daily_route

    if daily_route() == "unresolved":
        logger.warning("skip enriched publish for unresolved daily route")
        return None
    return _tag_daily_route(_select_storage_cols(date_df))


def _existing_enriched_for_merge(existing: pl.DataFrame, incoming: pl.DataFrame) -> pl.DataFrame:
    """Keep same-date rows only when they match the current daily route."""
    from app.services.kline_sync import daily_cache_usable, daily_route

    if existing is None or existing.is_empty():
        return incoming.head(0)
    if daily_cache_usable(existing, daily_route()):
        return existing
    logger.info("replace stale enriched partition for route=%s", daily_route())
    return incoming.head(0)


def _usable_daily_paths(data_dir: Path, *, table: str = "kline_daily") -> list[Path]:
    from app.services.kline_sync import usable_daily_partition_paths

    return usable_daily_partition_paths(data_dir, table=table)


def _load_usable_instruments(data_dir: Path) -> pl.DataFrame:
    """Current-route instruments for enriched limit-up / turnover."""
    try:
        from app.services.instrument_sync import read_usable_instruments

        return read_usable_instruments(data_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("instruments 读取失败: %s", exc)
        return pl.DataFrame()


def _canonical_enriched_artifact(value: object, data_dir: Path) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value.strip())
    if path.is_absolute():
        try:
            return path.relative_to(data_dir).as_posix()
        except ValueError:
            return None
    normalized = PurePosixPath(value.strip()).as_posix().lstrip("./")
    return normalized[5:] if normalized.startswith("data/") else normalized


def _known_enriched_lineage_artifacts(data_dir: Path) -> set[str]:
    known: set[str] = set()
    for lineage_id in ("stock_enriched", "kline_daily_enriched"):
        root = data_dir / "lineage" / lineage_id
        if not root.exists():
            continue
        for path in root.rglob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    continue
                if payload.get("unit_version") != "canonical_daily_v1":
                    continue
                target = _canonical_enriched_artifact(
                    payload.get("target_artifact")
                    or payload.get("artifact_path")
                    or payload.get("artifact"),
                    data_dir,
                )
                if target and target.startswith("kline_daily_enriched/"):
                    known.add(target)
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
    return known


def _write_enriched_lineage(
    data_dir: Path,
    out: Path,
    *,
    row_count: int,
    scope: str | None,
    calculation_mode: str,
    quality: str,
) -> None:
    ds = out.parent.name.removeprefix("date=")
    write_lineage_record(
        data_dir,
        "kline_daily_enriched",
        {
            "date": ds,
            "source": "derived_indicators_pipeline",
            "adapter": "app.indicators.pipeline.run_pipeline",
            "unit_version": "canonical_daily_v1",
            "row_count": row_count,
            "scope": scope,
            "calculation_mode": calculation_mode,
            "quality": quality,
            "target_artifact": str(out.relative_to(data_dir)),
        },
    )


def _publish_enriched_partition(
    data_dir: Path,
    out: Path,
    date_df: pl.DataFrame,
    *,
    scope: str | None,
    calculation_mode: str,
) -> None:
    """Atomically publish one enriched partition with matching provenance."""
    if "symbol" in date_df.columns and date_df.height > 0:
        date_df = date_df.unique(subset=["symbol"], keep="last")
        sort_cols = [col for col in ("symbol",) if col in date_df.columns]
        if sort_cols:
            date_df = date_df.sort(sort_cols)
    prepared = _prepare_enriched_storage(date_df)
    if prepared is None:
        return
    date_df = prepared
    atomic_write_parquet(date_df, out)
    _write_enriched_lineage(
        data_dir,
        out,
        row_count=date_df.height,
        scope=scope,
        calculation_mode=calculation_mode,
        quality="healthy",
    )


def _partition_date_str(value: object) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    text = str(value)
    return text[:10] if len(text) >= 10 else text


def fill_enriched_coverage_gap(
    data_dir: Path | None = None,
    target_date: object | None = None,
    warmup_days: int = 90,
) -> int:
    """Merge symbols that exist in same-day kline_daily but not kline_daily_enriched.

    ``new_dates_only`` skips a date once its partition exists, even if that
    partition was written from a partial daily universe. This heals the latest
    (or specified) date without rewriting historical partitions.
    """
    from datetime import date as date_cls
    from datetime import timedelta

    from app.services import preferences as prefs_mod

    d = Path(data_dir or settings.data_dir)
    daily_dir = d / "kline_daily"
    enriched_base = d / "kline_daily_enriched"
    if not daily_dir.exists():
        return 0

    usable_daily = _usable_daily_paths(d, table="kline_daily")
    if target_date is None:
        if not usable_daily:
            return 0
        ds = usable_daily[-1].parent.name.split("=", 1)[1]
    else:
        ds = _partition_date_str(target_date)

    from app.services.kline_sync import read_usable_daily_partition

    daily = read_usable_daily_partition(daily_dir / f"date={ds}")
    if daily.is_empty() or "symbol" not in daily.columns:
        return 0

    out = enriched_base / f"date={ds}" / "part.parquet"
    existing = read_usable_daily_partition(enriched_base / f"date={ds}")
    existing = _existing_enriched_for_merge(existing, daily)
    daily_syms = {str(symbol) for symbol in daily["symbol"].to_list() if symbol}
    enr_syms = (
        {str(symbol) for symbol in existing["symbol"].to_list() if symbol}
        if not existing.is_empty() and "symbol" in existing.columns
        else set()
    )
    missing = sorted(daily_syms - enr_syms)
    if not missing:
        return 0

    target = date_cls.fromisoformat(ds)
    warmup_start = target - timedelta(days=warmup_days)
    cast_options = pl.ScanCastOptions(integer_cast="allow-float")
    if not usable_daily:
        return 0
    raw = (
        pl.scan_parquet([p.as_posix() for p in usable_daily], cast_options=cast_options)
        .filter(
            (pl.col("date") >= warmup_start)
            & (pl.col("date") <= target)
            & pl.col("symbol").is_in(missing)
        )
        .sort(["symbol", "date"])
        .collect()
    )
    if raw.is_empty():
        return 0

    factors = _load_factors(d / "adj_factor" / "all.parquet")
    if not factors.is_empty() and "symbol" in factors.columns:
        factors = factors.filter(pl.col("symbol").is_in(missing))

    instruments = _load_usable_instruments(d)
    if not instruments.is_empty() and "symbol" in instruments.columns:
        instruments = instruments.filter(pl.col("symbol").is_in(missing))

    enriched = compute_enriched(raw, factors=factors, instruments=instruments)
    if enriched.is_empty() or "date" not in enriched.columns:
        return 0

    incoming = _select_storage_cols(
        enriched.filter(
            pl.col("date").map_elements(_partition_date_str, return_dtype=pl.Utf8) == ds
        )
    )
    if incoming.is_empty():
        logger.info("覆盖缺口: %s daily 多 %d 只, 计算后 0 行(可能全是停牌)", ds, len(missing))
        return 0

    prior_syms = enr_syms
    if existing.is_empty():
        merged = incoming.sort(["symbol"])
    else:
        merged = pl.concat([existing, incoming], how="diagonal_relaxed").unique(
            subset=["symbol", "date"],
            keep="last",
        ).sort(["symbol"])
    after_syms = {str(symbol) for symbol in merged["symbol"].to_list() if symbol}
    if prior_syms and not prior_syms.issubset(after_syms):
        raise RuntimeError(f"{ds} enriched coverage fill dropped prior symbols")

    out.parent.mkdir(parents=True, exist_ok=True)
    _publish_enriched_partition(
        d,
        out,
        merged,
        scope=prefs_mod.get_pipeline_universe_scope(),
        calculation_mode="coverage_gap_fill",
    )
    added = incoming.height
    logger.info("覆盖缺口补齐: %s 新增 %d 行, 分区现 %d 行", ds, added, merged.height)
    return added


def _reconcile_enriched_lineage(
    data_dir: Path,
    enriched_base: Path,
    *,
    scope: str | None,
    strict_unreadable: bool,
) -> tuple[int, set[str]]:
    """Backfill missing sidecars so a failed publish can heal on retry."""
    known = _known_enriched_lineage_artifacts(data_dir)
    reconciled = 0
    unreadable_dates: set[str] = set()
    from app.services.kline_sync import usable_daily_partition_files

    for child in sorted(p for p in enriched_base.glob("date=*") if p.is_dir()):
        files = usable_daily_partition_files(child)
        if not files:
            continue
        out = next((path for path in files if path.name == "part.parquet"), files[0])
        artifact = str(out.relative_to(data_dir))
        try:
            metadata = pq.read_metadata(out)
        except (OSError, pa.ArrowInvalid):
            ds = out.parent.name.removeprefix("date=")
            if strict_unreadable:
                raise
            unreadable_dates.add(ds)
            continue
        if artifact in known:
            continue
        _write_enriched_lineage(
            data_dir,
            out,
            row_count=metadata.num_rows,
            scope=scope,
            calculation_mode="lineage_reconcile",
            quality="healthy",
        )
        known.add(artifact)
        reconciled += 1
    return reconciled, unreadable_dates


# ================================================================
# 全量重建流式暂存 + 自适应批次 (#208/#174)
#
# 旧全量模式把所有批次结果累积在内存 date_buffers 直到统一写盘:
# 延长历史后 (5年 × 5500 只 ≈ 800 万行) 「全表驻留 + 单批宽表」双双
# 超出小内存机器上限, 重建必然 OOM。现改为:
#   - 每批结果立即写暂存文件 (enriched 树外的隐藏目录 —— polars/duckdb
#     的 **/*.parquet glob 均会匹配点目录, 树内暂存会被业务读取扫到),
#     最后按日期分块流式合并、逐分区原子替换;
#   - 批次大小按单批目标行数自适应收缩 (指标/信号全部 over("symbol")
#     分组, symbol 级分批不改变计算结果, 只约束单批宽表峰值)。
# 任一时刻峰值内存 = 单批计算 + 单个日期块合并, 与总历史长度无关。
# ================================================================

_STAGING_ROOT = Path(".staging") / "enriched_rebuild"
_STALE_STAGING_MAX_AGE_S = 24 * 3600
_RAM_LARGE_BYTES = 8 * 1024 ** 3      # ≥8GB 视为内存充裕, 批次保持用户设置
_BATCH_TARGET_ROWS = 150_000          # 小内存单批目标行数 (宽表 ~60-80MB)
_BATCH_MIN_SYMBOLS = 50
_MERGE_DATE_CHUNKS = 15               # 最终合并按日期切 15 块流式执行

_ram_bytes_cache: int | None | bool = False  # False = 未探测


def _total_ram_bytes() -> int | None:
    global _ram_bytes_cache
    if _ram_bytes_cache is False:
        try:
            import psutil
            _ram_bytes_cache = psutil.virtual_memory().total
        except Exception:
            _ram_bytes_cache = None
    return _ram_bytes_cache  # type: ignore[return-value]


def _adaptive_sym_batch(default_batch: int, rows_per_symbol: int) -> int:
    """小内存机器按单批目标行数收缩批次; 大内存机器保持原值 (#208)。"""
    if (_total_ram_bytes() or 0) >= _RAM_LARGE_BYTES:
        return default_batch
    return max(
        _BATCH_MIN_SYMBOLS,
        min(default_batch, _BATCH_TARGET_ROWS // max(rows_per_symbol, 1)),
    )


def _sweep_stale_staging(data_dir: Path) -> None:
    """清理崩溃/取消运行残留的暂存目录 (按 mtime 判定, 不碰活跃目录)。"""
    root = data_dir / _STAGING_ROOT
    if not root.exists():
        return
    cutoff = time.time() - _STALE_STAGING_MAX_AGE_S
    for run_dir in root.iterdir():
        try:
            if run_dir.is_dir() and run_dir.stat().st_mtime < cutoff:
                shutil.rmtree(run_dir, ignore_errors=True)
        except OSError:
            pass


def compute_enriched_history_window(
    df_hist: pl.DataFrame,
    data_dir: Path,
    instruments: pl.DataFrame | None = None,
    historical_shares: pl.DataFrame | None = None,
    sym_batch: int | None = None,
) -> pl.DataFrame:
    """按 symbol 分批执行历史窗口计算: 指标 → 偏离列 → 信号 → 涨跌停。

    与整帧顺序执行完全等价 (各步骤均 over("symbol") 分组), 分批只约束
    峰值内存: repository._refresh_enriched 的 300 天窗口在 5500 只、
    210 交易日下整帧宽表 ~1.2GB, 小内存机器启动即 OOM (#208)。
    sym_batch 显式传入时跳过自适应 (测试用)。
    """
    if df_hist.is_empty() or "symbol" not in df_hist.columns:
        return df_hist
    symbols = df_hist["symbol"].unique().sort().to_list()
    if sym_batch is None:
        rows_per_sym = max(1, df_hist.height // max(len(symbols), 1))
        sym_batch = _adaptive_sym_batch(2000, rows_per_sym)
    parts: list[pl.DataFrame] = []
    for bs in range(0, len(symbols), sym_batch):
        batch = symbols[bs:bs + sym_batch]
        part = df_hist.filter(pl.col("symbol").is_in(batch)).sort(["symbol", "date"])
        part = compute_indicators(part)
        part = attach_deviation_columns(part, data_dir)
        part = compute_signals(part)
        if instruments is not None and not instruments.is_empty():
            inst_batch = instruments.filter(pl.col("symbol").is_in(batch))
            shares_batch = (
                historical_shares.filter(pl.col("symbol").is_in(batch))
                if historical_shares is not None and not historical_shares.is_empty()
                else historical_shares
            )
            part = compute_limit_signals(part, inst_batch, historical_shares=shares_batch)
        parts.append(part)
    out = parts[0] if len(parts) == 1 else pl.concat(parts, how="diagonal_relaxed")
    return out.sort(["symbol", "date"])


def run_pipeline(data_dir: Path | None = None,
                 symbols: list[str] | None = None,
                 new_dates_only: bool = False,
                 on_batch_done: Callable[[int, int], None] | None = None) -> int:
    """运行盘后管道:读 kline_daily + adj_factor → 前复权 + 计算存储列 → 写 enriched。

    enriched 表仅存储 14 列基础行情窄表 (OHLCV + raw_close/high/low + turnover_rate + 连板数)。

    模式:
      - 全量 (symbols=None, new_dates_only=False):
          读全部 kline_daily, 全部重写 enriched 分区。
          用于首次同步、往前扩展历史。
      - 向后增量 (new_dates_only=True):
          只读 enriched 中尚不存在的日期分区对应的 daily 数据,
          为所有标的生成新的 enriched 分区;
          若同时传 symbols, 还会对这些个股的全部已有日期做重算
          (因为除权因子链变了,历史数据的复权比例也要更新)。
      - 除权因子增量 (symbols 指定, new_dates_only=False):
          只对指定 symbol 做局部重算并合并回已有 enriched。
          用于无新日K数据、仅除权因子变更的场景。
    返回写入的行数。
    """
    import time as _t
    t0 = _t.perf_counter()

    d = Path(data_dir or settings.data_dir)
    daily_dir = d / "kline_daily"
    enriched_base = d / "kline_daily_enriched"
    factor_path = d / "adj_factor" / "all.parquet"
    from app.services.kline_sync import safe_usable_daily_partition_dates

    if not daily_dir.exists() or not safe_usable_daily_partition_dates(d, table="kline_daily"):
        logger.info("无当前 route 可用日K, 跳过管道")
        return 0

    from app.services import preferences as prefs_mod

    pipeline_scope = prefs_mod.get_pipeline_universe_scope()
    reconciled, unreadable_dates = _reconcile_enriched_lineage(
        d,
        enriched_base,
        scope=pipeline_scope,
        strict_unreadable=bool(symbols and not new_dates_only),
    )
    if reconciled:
        logger.info("enriched lineage reconciled: %d partitions", reconciled)
    if unreadable_dates:
        logger.warning(
            "enriched partitions require rebuild: %s",
            ", ".join(sorted(unreadable_dates)[:20]),
        )

    usable_daily_files = _usable_daily_paths(d, table="kline_daily")
    _cast = pl.ScanCastOptions(integer_cast="allow-float")
    written = 0
    if not usable_daily_files:
        logger.info("无当前 route 可用日K, 跳过管道")
        return 0
    daily_glob = [p.as_posix() for p in usable_daily_files]

    # 加载当前 route instruments (涨跌停+换手率需要)
    instruments = _load_usable_instruments(d)
    historical_shares = load_share_history(d)

    if new_dates_only:
        # ── 向后增量模式 ──
        # 1. 找出当前 route 日K 有但可用 enriched 还没有的日期
        from app.services.kline_sync import safe_usable_daily_partition_dates

        enriched_dates = {
            day.isoformat()
            for day in safe_usable_daily_partition_dates(d, table="kline_daily_enriched")
        }
        enriched_dates -= unreadable_dates

        # 读新增日期的 daily 数据 (所有标的)
        new_date_dirs = sorted(
            p.parent
            for p in usable_daily_files
            if p.parent.name.split("=", 1)[1] not in enriched_dates
        )
        if not new_date_dirs and not symbols:
            written_gap = fill_enriched_coverage_gap(d)
            if written_gap:
                logger.info("增量模式: 无新日期, 覆盖缺口补齐 %d 行", written_gap)
                return written_gap
            logger.info("增量模式: 无新日期, 无需重算")
            return 0

        # 加载复权因子 (全量,因为所有标的都可能需要)
        factors = _load_factors(factor_path)

        # 2. 为新日期计算 enriched (所有标的)
        if new_date_dirs:
            raw_new = pl.scan_parquet(new_date_dirs[0] / "*.parquet", cast_options=_cast)
            for nd in new_date_dirs[1:]:
                raw_new = pl.concat([raw_new, pl.scan_parquet(nd / "*.parquet", cast_options=_cast)], how="diagonal_relaxed")
            raw_new = raw_new.sort(["symbol", "date"]).collect(streaming=True)

            # 增量模式: 只算新日期, 但指标需要历史窗口
            # 读已有 enriched 最近 60 天作为历史前缀
            sym_list = raw_new["symbol"].unique().to_list()
            hist_df = _load_recent_history(enriched_base, sym_list, days=60)

            # 合并历史 + 新数据
            if not hist_df.is_empty():
                # 只取基础行情列做历史前缀
                hist_cols = [c for c in ["symbol", "date", "open", "high", "low", "close",
                                         "volume", "amount", "raw_close", "raw_high", "raw_low"]
                             if c in hist_df.columns]
                raw_full = pl.concat([hist_df.select(hist_cols), raw_new], how="diagonal_relaxed")
            else:
                raw_full = raw_new

            enriched_new = compute_enriched(
                raw_full,
                factors=factors,
                instruments=instruments,
                historical_shares=historical_shares,
            )

            # 只保留新日期的行
            new_date_set = set()
            for nd in new_date_dirs:
                ds = nd.stem.split("=")[1]
                new_date_set.add(ds)
            enriched_new = enriched_new.filter(
                pl.col("date").map_elements(lambda x: x.isoformat(), return_dtype=pl.Utf8).is_in(list(new_date_set))
            )

            t_new = _t.perf_counter()
            logger.info("增量计算: %d 个新日期, %d 行, 耗时 %.2fs",
                        len(new_date_dirs), enriched_new.height, t_new - t0)

            if not enriched_new.is_empty():
                for date_df in enriched_new.partition_by("date"):
                    dt = date_df["date"][0]
                    ds = dt.isoformat() if hasattr(dt, "isoformat") else str(dt)
                    out = enriched_base / f"date={ds}" / "part.parquet"
                    out.parent.mkdir(parents=True, exist_ok=True)
                    date_df = _select_storage_cols(date_df).sort(["symbol"])
                    _publish_enriched_partition(
                        d,
                        out,
                        date_df,
                        scope=pipeline_scope,
                        calculation_mode="new_dates_only",
                    )
                    written += date_df.height
                t_write_new = _t.perf_counter()
                logger.info("增量写入: %.2fs, %d 行", t_write_new - t_new, written)

        # 3. 受除权因子影响的个股: 重算全部已有日期 (累积因子链变了)
        if symbols:
            sym_set = set(symbols)
            raw_sym = pl.scan_parquet(daily_glob, cast_options=_cast).sort(["symbol", "date"])
            raw_sym = raw_sym.filter(pl.col("symbol").is_in(list(sym_set)))
            raw_sym = raw_sym.collect(streaming=True)
            if not raw_sym.is_empty():
                factors_sym = factors.filter(pl.col("symbol").is_in(list(sym_set))) if not factors.is_empty() else factors
                inst_sym = instruments.filter(pl.col("symbol").is_in(list(sym_set))) if not instruments.is_empty() else instruments
                shares_sym = (
                    historical_shares.filter(pl.col("symbol").is_in(list(sym_set)))
                    if not historical_shares.is_empty() else historical_shares
                )
                enriched_sym = compute_enriched(
                    raw_sym,
                    factors=factors_sym,
                    instruments=inst_sym,
                    historical_shares=shares_sym,
                )
                for date_df in enriched_sym.partition_by("date"):
                    dt = date_df["date"][0]
                    ds = dt.isoformat() if hasattr(dt, "isoformat") else str(dt)
                    out = enriched_base / f"date={ds}" / "part.parquet"
                    out.parent.mkdir(parents=True, exist_ok=True)
                    date_df_storage = _select_storage_cols(date_df)
                    if out.exists():
                        existing = _existing_enriched_for_merge(
                            pl.read_parquet(out), date_df_storage,
                        )
                        existing = existing.filter(~pl.col("symbol").is_in(list(sym_set)))
                        date_df_storage = pl.concat([existing, date_df_storage], how="diagonal_relaxed")
                    date_df_storage = date_df_storage.sort(["symbol"])
                    _publish_enriched_partition(
                        d,
                        out,
                        date_df_storage,
                        scope=pipeline_scope,
                        calculation_mode="affected_symbols",
                    )
                    written += date_df.height
                logger.info("除权重算: %d 只, 共写入 %d 行", len(sym_set), written)

        t_done = _t.perf_counter()
        logger.info("增量管道完成: %.2fs, %d 行", t_done - t0, written)
        return written

    # ── 全量 或 除权因子增量 模式 ──
    # 全量走 908 流式暂存, 发布仍走本地 _publish_enriched_partition
    # (原子写 + lineage)。两套路径互斥: 不再内存 date_buffers, 也不在
    # 批循环内提前合并。局部 symbols 仍按日期合并进已有分区。
    mode = f"incremental ({len(symbols)} symbols)" if symbols else "full"
    base = d / "kline_daily_enriched"

    factors = _load_factors(factor_path)
    inst_use = instruments

    import gc

    lf_all = pl.scan_parquet(daily_glob, cast_options=_cast)
    if symbols:
        sym_set = set(symbols)
        lf_all = lf_all.filter(pl.col("symbol").is_in(list(sym_set)))

    all_symbols = (
        lf_all.select("symbol").unique().sort("symbol")
        .collect(streaming=True)["symbol"].to_list()
    )
    if not all_symbols:
        logger.info("无日K数据, 跳过管道")
        return 0

    total_syms = len(all_symbols)

    if not factors.is_empty() and symbols:
        factors = factors.filter(pl.col("symbol").is_in(list(sym_set)))
    if not factors.is_empty():
        logger.info("读取复权因子: %d 行", factors.height)
    if not instruments.is_empty() and symbols:
        inst_use = instruments.filter(pl.col("symbol").is_in(list(sym_set)))

    total_rows = lf_all.select(pl.len()).collect(streaming=True).item()
    rows_per_sym = max(1, -(-int(total_rows) // total_syms))
    SYM_BATCH = _adaptive_sym_batch(prefs_mod.get_enriched_batch_size(), rows_per_sym)
    total_batches = (total_syms + SYM_BATCH - 1) // SYM_BATCH
    logger.info("全量计算: %d 只标的 (%d 行, ~%d 行/只), symbol 分批 %d 只/批, %d 批 [%s]",
                total_syms, total_rows, rows_per_sym, SYM_BATCH, total_batches, mode)

    staging_dir: Path | None = None
    staging_files: list[str] = []
    if not symbols:
        _sweep_stale_staging(d)
        staging_dir = d / _STAGING_ROOT / uuid.uuid4().hex
        staging_dir.mkdir(parents=True, exist_ok=True)

    try:
        for batch_start in range(0, total_syms, SYM_BATCH):
            batch_end = min(batch_start + SYM_BATCH, total_syms)
            batch_syms = all_symbols[batch_start:batch_end]

            lf_batch = pl.scan_parquet(daily_glob, cast_options=_cast)
            lf_batch = lf_batch.filter(pl.col("symbol").is_in(batch_syms))
            raw = lf_batch.sort(["symbol", "date"]).collect(streaming=True)

            if raw.is_empty():
                continue

            batch_factors = (
                factors.filter(pl.col("symbol").is_in(batch_syms))
                if not factors.is_empty() else factors
            )
            batch_inst = (
                inst_use.filter(pl.col("symbol").is_in(batch_syms))
                if not inst_use.is_empty() else inst_use
            )
            batch_shares = (
                historical_shares.filter(pl.col("symbol").is_in(batch_syms))
                if not historical_shares.is_empty() else historical_shares
            )

            enriched = compute_enriched(
                raw,
                factors=batch_factors,
                instruments=batch_inst,
                historical_shares=batch_shares,
            )

            if not enriched.is_empty():
                if symbols:
                    for date_df in enriched.partition_by("date"):
                        dt = date_df["date"][0]
                        ds = dt.isoformat() if hasattr(dt, "isoformat") else str(dt)
                        out = base / f"date={ds}" / "part.parquet"
                        out.parent.mkdir(parents=True, exist_ok=True)
                        date_df_storage = _select_storage_cols(date_df)
                        if out.exists():
                            existing = _existing_enriched_for_merge(
                                pl.read_parquet(out), date_df_storage,
                            )
                            existing = existing.filter(~pl.col("symbol").is_in(batch_syms))
                            date_df_storage = pl.concat(
                                [existing, date_df_storage], how="diagonal_relaxed"
                            )
                        date_df_storage = date_df_storage.sort(["symbol"])
                        _publish_enriched_partition(
                            d,
                            out,
                            date_df_storage,
                            scope=pipeline_scope,
                            calculation_mode="selected_symbols",
                        )
                        written += date_df_storage.height
                else:
                    out = staging_dir / f"batch-{batch_start // SYM_BATCH:04d}.parquet"
                    _select_storage_cols(enriched).sort(["date", "symbol"]).write_parquet(out)
                    staging_files.append(str(out))
                    written += enriched.height

            del raw, enriched, batch_factors, batch_inst, batch_shares
            gc.collect()

            logger.info("symbol 批次 %d/%d (%s ~ %s), 已处理 %d 行",
                         batch_start // SYM_BATCH + 1,
                         total_batches,
                         batch_syms[0], batch_syms[-1], written)

            if on_batch_done:
                on_batch_done(batch_start // SYM_BATCH + 1, total_batches)

        if not symbols and staging_files:
            from app.services.kline_sync import safe_usable_daily_partition_dates

            existing_dates = {
                day.isoformat()
                for day in safe_usable_daily_partition_dates(d, table="kline_daily_enriched")
            }
            unique_dates = sorted(
                scan_enriched_parquet(staging_files).select("date").unique()
                .collect()["date"].to_list()
            )
            rebuilt_dates = {
                ds.isoformat() if hasattr(ds, "isoformat") else str(ds)
                for ds in unique_dates
            }
            missing_dates = existing_dates - rebuilt_dates
            if missing_dates:
                sample = ", ".join(sorted(missing_dates)[:5])
                raise RuntimeError(f"全量重建结果缺少已有日期分区,拒绝覆盖: {sample}")

            base.mkdir(parents=True, exist_ok=True)

            chunk = max(1, -(-len(unique_dates) // _MERGE_DATE_CHUNKS))
            for ci in range(0, len(unique_dates), chunk):
                lo = unique_dates[ci]
                hi = unique_dates[min(ci + chunk, len(unique_dates)) - 1]
                block = (
                    scan_enriched_parquet(staging_files)
                    .filter((pl.col("date") >= lo) & (pl.col("date") <= hi))
                    .sort(["date", "symbol"])
                    .collect(streaming=True)
                )
                for date_df in block.partition_by("date"):
                    ds = date_df["date"][0]
                    ds_str = ds.isoformat() if hasattr(ds, "isoformat") else str(ds)
                    out = base / f"date={ds_str}" / "part.parquet"
                    out.parent.mkdir(parents=True, exist_ok=True)
                    _publish_enriched_partition(
                        d,
                        out,
                        _select_storage_cols(date_df).sort(["symbol"]),
                        scope=pipeline_scope,
                        calculation_mode="full_market",
                    )
            gc.collect()
            logger.info("全量暂存合并完成: %d 个日期分区", len(unique_dates))
    finally:
        if staging_dir is not None:
            shutil.rmtree(staging_dir, ignore_errors=True)

    t_done = _t.perf_counter()
    adj_label = "含复权" if not factors.is_empty() else "无复权"
    logger.info("enriched 完成 [%s]: %.2fs, 共 %d 行, %s",
                mode, t_done - t0, written, adj_label)
    return written


def _load_factors(factor_path: Path) -> pl.DataFrame:
    """加载复权因子文件。"""
    try:
        from app.services.kline_sync import get_adj_factor_df
        asset_type = "etf" if "etf" in factor_path.parent.name else "stock"
        return get_adj_factor_df(factor_path.parent.parent, asset_type=asset_type)
    except Exception as e:  # noqa: BLE001
        logger.warning("复权因子读取失败: %s", e)
        return pl.DataFrame()


def _load_recent_history(enriched_base: Path, symbols: list[str], days: int) -> pl.DataFrame:
    """从已有 enriched parquet 加载最近 N 天的历史数据(用于增量模式的指标计算窗口)。

    只读基础行情列, 作为指标计算的历史前缀。
    """
    from datetime import date, timedelta
    cutoff = date.today() - timedelta(days=days + 30)  # 多读 30 天余量
    cast_options = pl.ScanCastOptions(integer_cast="allow-float")

    try:
        hist_paths = _usable_daily_paths(enriched_base.parent, table="kline_daily_enriched")
        if not hist_paths:
            return pl.DataFrame()
        lf = (
            pl.scan_parquet([p.as_posix() for p in hist_paths], cast_options=cast_options)
            .filter(
                (pl.col("symbol").is_in(symbols))
                & (pl.col("date") >= cutoff)
            )
            .sort(["symbol", "date"])
        )
        schema_names = set(lf.collect_schema().names())
        hist_cols = [c for c in ["symbol", "date", "open", "high", "low", "close",
                                 "volume", "amount", "raw_close", "raw_high", "raw_low"]
                    if c in schema_names]
        if "route" in schema_names:
            hist_cols.append("route")
        from app.services.kline_sync import filter_daily_cache

        hist = filter_daily_cache(lf.select(hist_cols).collect())
        return hist.drop("route") if "route" in hist.columns else hist
    except Exception as e:  # noqa: BLE001
        logger.warning("历史数据加载失败: %s", e)
        return pl.DataFrame()


def compute_enriched_single(daily_for_symbol: pl.DataFrame) -> pl.DataFrame:
    """单股版本 — Free 用户用,拉下来单股 K 后即时计算全部指标+信号返回给前端。"""
    if daily_for_symbol.is_empty():
        return daily_for_symbol

    # 过滤停牌
    daily_for_symbol = filter_halt_days(daily_for_symbol)
    if daily_for_symbol.is_empty():
        return daily_for_symbol

    # 保留 raw_close 用于涨停判断
    daily_for_symbol = daily_for_symbol.with_columns(pl.col("close").alias("raw_close"))

    # 即时计算全套指标 + 信号 (无复权因子, 无 instruments)
    return compute_all(daily_for_symbol)


# ================================================================
# 盘中增量计算: 只算今天 5500 行 (不复算历史)
# ================================================================

def compute_enriched_today(
    live_agg: pl.DataFrame,
    prev_enriched: pl.DataFrame,
    today_ohlcv: pl.DataFrame,
    instruments: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """用昨天的递推状态 + 今天的 OHLCV 增量计算今天的 enriched 数据。

    只处理 ~5500 行, 耗时 ~10-50ms (替代全量 compute_enriched 的 1.5-2s)。

    参数:
        live_agg:       repo.get_live_agg() — 包含所有递推状态 + 窗口聚合
        prev_enriched:  repo.get_enriched_latest() — 昨天的完整 enriched (用于信号交叉判断)
        today_ohlcv:    今天的 OHLCV (symbol, date, open, high, low, close, volume, amount)
        instruments:    维表 (涨跌停/换手率需要)

    返回:
        今天的 enriched DataFrame (~5500 行, 64 列)
    """
    if today_ohlcv.is_empty() or live_agg.is_empty():
        return pl.DataFrame()

    alpha = _ema_alpha

    # ---- JOIN: 今天的 OHLCV + 昨天的递推状态 ----
    df = today_ohlcv.join(live_agg, on="symbol", how="inner")

    # ---- 前复权: 保存原始价 → 调整 OHLCV ----
    df = df.with_columns([
        pl.col("close").alias("raw_close"),
        pl.col("high").alias("raw_high"),
        pl.col("low").alias("raw_low"),
    ])
    if "_adj_factor" in df.columns:
        af = pl.col("_adj_factor").fill_null(1.0)
        df = df.with_columns([
            (pl.col("open") * af).alias("open"),
            (pl.col("high") * af).alias("high"),
            (pl.col("low") * af).alias("low"),
            (pl.col("close") * af).alias("close"),
        ])

    # ---- volume 统一 Float64 ----
    df = df.with_columns(pl.col("volume").cast(pl.Float64))

    # ---- ex_rights: 盘中除权极罕见, 直接 false ----
    df = df.with_columns(pl.lit(False).alias("ex_rights"))

    # ---- 基础涨跌 ----
    # prev_close: 有则直接用 (来自 API quote_extra, raw), 需要乘 adj_factor 对齐复权价
    if "prev_close" not in df.columns:
        prev_close = pl.col("close_right") if "close_right" in df.columns else pl.col("close")
        df = df.with_columns(prev_close.alias("prev_close"))
    elif "_adj_factor" in df.columns:
        # 保存 API 原始前收盘价 (用于涨跌停价计算)
        df = df.with_columns(pl.col("prev_close").alias("_prev_close_raw"))
        # API 返回的 prev_close 是原始价, 乘复权因子对齐复权价 (用于 change_pct)
        df = df.with_columns((pl.col("prev_close") * pl.col("_adj_factor").fill_null(1.0)).alias("prev_close"))

    # change_pct / change_amount / amplitude:
    # Quote snapshot 是百分点 (20.02 = +20.02%); enriched 契约是小数 (0.2002)。
    # |x|>1 视为百分点并换算; 缺列或空值用价差重算。
    computed_pct = pl.col("close") / pl.col("prev_close") - 1
    if "change_pct" not in df.columns:
        df = df.with_columns(computed_pct.alias("change_pct"))
    else:
        raw = pl.col("change_pct")
        normalized = (
            pl.when(raw.is_not_null() & (raw.abs() > 1.0))
            .then(raw / 100.0)
            .otherwise(raw)
        )
        df = df.with_columns(
            pl.when(normalized.is_null()).then(computed_pct).otherwise(normalized).alias("change_pct")
        )
    if "change_amount" not in df.columns:
        df = df.with_columns((pl.col("close") - pl.col("prev_close")).alias("change_amount"))
    computed_amp = (
        pl.when(pl.col("prev_close") > 0)
        .then((pl.col("high") - pl.col("low")) / pl.col("prev_close"))
        .otherwise(None)
    )
    if "amplitude" not in df.columns:
        df = df.with_columns(computed_amp.alias("amplitude"))
    else:
        raw_amp = pl.col("amplitude")
        normalized_amp = (
            pl.when(raw_amp.is_not_null() & (raw_amp.abs() > 1.0))
            .then(raw_amp / 100.0)
            .otherwise(raw_amp)
        )
        df = df.with_columns(
            pl.when(normalized_amp.is_null())
            .then(computed_amp)
            .otherwise(normalized_amp)
            .alias("amplitude")
        )

    # ---- EMA (递推) ----
    df = df.with_columns([
        (alpha(5)  * pl.col("close") + (1 - alpha(5))  * pl.col("ema5")).alias("ema5"),
        (alpha(10) * pl.col("close") + (1 - alpha(10)) * pl.col("ema10")).alias("ema10"),
        (alpha(20) * pl.col("close") + (1 - alpha(20)) * pl.col("ema20")).alias("ema20"),
        (alpha(30) * pl.col("close") + (1 - alpha(30)) * pl.col("ema30")).alias("ema30"),
        (alpha(60) * pl.col("close") + (1 - alpha(60)) * pl.col("ema60")).alias("ema60"),
    ])

    # ---- MACD (递推) ----
    ema12 = alpha(12) * pl.col("close") + (1 - alpha(12)) * pl.col("_ema12")
    ema26 = alpha(26) * pl.col("close") + (1 - alpha(26)) * pl.col("_ema26")
    dif = ema12 - ema26
    dea = alpha(9) * dif + (1 - alpha(9)) * pl.col("macd_dea")
    df = df.with_columns([
        dif.alias("macd_dif"),
        dea.alias("macd_dea"),
        ((dif - dea) * 2).alias("macd_hist"),
    ])

    # ---- MA (用部分和) ----
    df = df.with_columns([
        ((pl.col("_ma5_partial_sum") + pl.col("close")) / 5).alias("ma5"),
        ((pl.col("_ma10_partial_sum") + pl.col("close")) / 10).alias("ma10"),
        ((pl.col("_ma20_partial_sum") + pl.col("close")) / 20).alias("ma20"),
        ((pl.col("_ma30_partial_sum") + pl.col("close")) / 30).alias("ma30"),
        ((pl.col("_ma60_partial_sum") + pl.col("close")) / 60).alias("ma60"),
    ])

    # ---- Bollinger ----
    boll_sum = pl.col("_boll_partial_sum") + pl.col("close")
    boll_sq_sum = pl.col("_boll_partial_sq_sum") + pl.col("close") ** 2
    boll_ma = boll_sum / 20
    boll_var = boll_sq_sum / 20 - boll_ma ** 2
    boll_std = pl.when(boll_var > 0).then(boll_var.sqrt()).otherwise(0.0)
    df = df.with_columns([
        (boll_ma + 2 * boll_std).alias("boll_upper"),
        (boll_ma - 2 * boll_std).alias("boll_lower"),
    ])

    # ---- KDJ (递推) ----
    kdj_ln = pl.min_horizontal(pl.col("_kdj_8d_low"), pl.col("low"))
    kdj_hn = pl.max_horizontal(pl.col("_kdj_8d_high"), pl.col("high"))
    rsv = (pl.col("close") - kdj_ln) / (kdj_hn - kdj_ln).fill_null(1e-12) * 100
    k_today = rsv / 3 + pl.col("kdj_k") * 2 / 3
    d_today = k_today / 3 + pl.col("kdj_d") * 2 / 3
    df = df.with_columns([
        k_today.alias("kdj_k"),
        d_today.alias("kdj_d"),
        (3 * k_today - 2 * d_today).alias("kdj_j"),
    ])

    # ---- ATR (递推) ----
    tr = pl.max_horizontal(
        pl.col("high") - pl.col("low"),
        (pl.col("high") - pl.col("prev_close")).abs(),
        (pl.col("low") - pl.col("prev_close")).abs(),
    )
    df = df.with_columns(
        (tr / 14 + pl.col("atr_14") * 13 / 14).alias("atr_14"),
    )

    # ---- RSI (递推, n=6,14,24) ----
    delta = pl.col("close") - pl.col("prev_close")
    gain = pl.when(delta > 0).then(delta).otherwise(0.0)
    loss = pl.when(delta < 0).then(-delta).otherwise(0.0)
    for n in (6, 14, 24):
        a = 1.0 / n
        avg_gain = (1 - a) * pl.col(f"_rsi_avg_gain_{n}") + a * gain
        avg_loss = (1 - a) * pl.col(f"_rsi_avg_loss_{n}") + a * loss
        df = df.with_columns([
            avg_gain.alias(f"_rsi_avg_gain_{n}"),
            avg_loss.alias(f"_rsi_avg_loss_{n}"),
            (100 - 100 / (1 + avg_gain / pl.when(avg_loss == 0).then(1e-12).otherwise(avg_loss)))
            .alias(f"rsi_{n}"),
        ])

    # ---- 量比 ----
    vol_ma5 = (pl.col("_vol_ma5_partial_sum") + pl.col("volume")) / 5
    vol_ma10 = (pl.col("_vol_ma10_partial_sum") + pl.col("volume")) / 10
    df = df.with_columns([
        vol_ma5.alias("vol_ma5"),
        vol_ma10.alias("vol_ma10"),
        (pl.col("volume") / vol_ma5).alias("vol_ratio_5d"),
    ])

    # ---- 极值 60 日 ----
    df = df.with_columns([
        pl.max_horizontal(pl.col("_high_59d"), pl.col("high")).alias("high_60d"),
        pl.min_horizontal(pl.col("_low_59d"), pl.col("low")).alias("low_60d"),
    ])

    # ---- 动量 (5d/10d/20d/30d/60d) ----
    df = df.with_columns([
        (pl.col("close") / pl.col("_close_5d_ago") - 1).alias("momentum_5d"),
        (pl.col("close") / pl.col("_close_10d_ago") - 1).alias("momentum_10d"),
        (pl.col("close") / pl.col("_close_20d_ago") - 1).alias("momentum_20d"),
        (pl.col("close") / pl.col("_close_30d_ago") - 1).alias("momentum_30d"),
        (pl.col("close") / pl.col("_close_60d_ago") - 1).alias("momentum_60d"),
    ])

    # ---- 年化波动率 20d (递推) ----
    # 用 Welford 简化: sum + sum_sq of 19 historical returns + today's return
    today_ret = pl.col("close") / pl.col("prev_close") - 1
    total_sum = pl.col("_vol_19d_pct_sum").fill_null(0.0) + today_ret
    total_sq_sum = pl.col("_vol_19d_pct_sq_sum").fill_null(0.0) + today_ret ** 2
    vol_mean = total_sum / 20
    vol_var = total_sq_sum / 20 - vol_mean ** 2
    df = df.with_columns(
        pl.when(vol_var > 0)
          .then(vol_var.sqrt() * (252 ** 0.5))
          .otherwise(None)
          .alias("annual_vol_20d"),
    )

    # ---- 信号 (需要昨天的指标值判断交叉) ----
    if not prev_enriched.is_empty():
        sig_prev = prev_enriched.select(
            "symbol",
            pl.col("ma5").alias("_prev_ma5"),
            pl.col("ma20").alias("_prev_ma20"),
            pl.col("ma60").alias("_prev_ma60"),
            pl.col("macd_dif").alias("_prev_dif"),
            pl.col("macd_dea").alias("_prev_dea"),
            pl.col("boll_upper").alias("_prev_boll_upper"),
            pl.col("boll_lower").alias("_prev_boll_lower"),
            pl.col("close").alias("_prev_close_enriched"),
        )
        df = df.join(sig_prev, on="symbol", how="left")

        df = df.with_columns([
            # MA 金叉/死叉
            ((pl.col("ma5") > pl.col("ma20")) & (pl.col("_prev_ma5") <= pl.col("_prev_ma20")))
                .alias("signal_ma_golden_5_20"),
            ((pl.col("ma5") < pl.col("ma20")) & (pl.col("_prev_ma5") >= pl.col("_prev_ma20")))
                .alias("signal_ma_dead_5_20"),
            ((pl.col("ma20") > pl.col("ma60")) & (pl.col("_prev_ma20") <= pl.col("_prev_ma60")))
                .alias("signal_ma_golden_20_60"),
            # MACD 金叉/死叉
            ((pl.col("macd_dif") > pl.col("macd_dea")) & (pl.col("_prev_dif") <= pl.col("_prev_dea")))
                .alias("signal_macd_golden"),
            ((pl.col("macd_dif") < pl.col("macd_dea")) & (pl.col("_prev_dif") >= pl.col("_prev_dea")))
                .alias("signal_macd_dead"),
            # MA20 突破/跌破
            ((pl.col("close") > pl.col("ma20")) & (pl.col("_prev_close_enriched") <= pl.col("_prev_ma20")))
                .alias("signal_ma20_breakout"),
            ((pl.col("close") < pl.col("ma20")) & (pl.col("_prev_close_enriched") >= pl.col("_prev_ma20")))
                .alias("signal_ma20_breakdown"),
            # BOLL 突破
            (pl.col("close") >= pl.col("boll_upper")).alias("signal_boll_breakout_upper"),
            (pl.col("close") <= pl.col("boll_lower")).alias("signal_boll_breakdown_lower"),
        ])

        df = df.drop([
            c for c in df.columns
            if c.startswith("_prev_") and c not in {"_prev_consec_up", "_prev_consec_down"}
        ])

    # N日新高/新低 + 放量
    df = df.with_columns([
        (pl.col("close") >= pl.col("high_60d")).alias("signal_n_day_high"),
        (pl.col("close") <= pl.col("low_60d")).alias("signal_n_day_low"),
        (pl.col("vol_ratio_5d") >= 2.0).alias("signal_volume_surge"),
    ])

    # ---- 涨跌停 + 换手率 + 炸板 + 连板 ----
    if instruments is not None and not instruments.is_empty():
        df = _compute_limit_signals_today(df, instruments)

    # ---- 清理内部列 ----
    drop_cols = [
        "close_right", "high_right", "low_right", "_prev_close_raw",
        "_ma5_partial_sum", "_ma10_partial_sum", "_ma20_partial_sum",
        "_ma30_partial_sum", "_ma60_partial_sum",
        "_boll_partial_sum", "_boll_partial_sq_sum",
        "_high_59d", "_low_59d",
        "_close_5d_ago", "_close_10d_ago", "_close_20d_ago",
        "_close_30d_ago", "_close_60d_ago",
        "_vol_ma5_partial_sum", "_vol_ma10_partial_sum",
        "_kdj_8d_low", "_kdj_8d_high",
        "_window_len",
        "_rsi_avg_gain_6", "_rsi_avg_loss_6",
        "_rsi_avg_gain_14", "_rsi_avg_loss_14",
        "_rsi_avg_gain_24", "_rsi_avg_loss_24",
        "_ema12", "_ema26",
        "_adj_factor",
        "_vol_19d_pct_sum", "_vol_19d_pct_sq_sum",
        "_prev_consec_up", "_prev_consec_down",
    ]
    df = df.drop([c for c in drop_cols if c in df.columns])

    # 自定义信号（日级实时路径同样注入）
    from app.strategy import custom_signals
    df = custom_signals.inject(df, _get_custom_signal_exprs())

    # 清理 NaN / Inf
    float_cols = [c for c in df.columns if df[c].dtype.is_float()]
    if float_cols:
        df = df.with_columns([
            pl.when(pl.col(c).is_nan() | pl.col(c).is_infinite())
              .then(None)
              .otherwise(pl.col(c))
              .alias(c)
            for c in float_cols
        ])

    return df


def _compute_limit_signals_today(df: pl.DataFrame, instruments: pl.DataFrame) -> pl.DataFrame:
    """盘中增量版的涨跌停/换手率/炸板/连板计算。"""
    inst_cols = ["symbol"]
    for c in ["float_shares", "limit_up", "limit_down"]:
        if c in instruments.columns:
            inst_cols.append(c)
    inst_subset = instruments.select(inst_cols).unique(subset=["symbol"])
    if "name" in instruments.columns:
        st_flag = (
            instruments
            .select("symbol", pl.col("name").str.contains("ST").alias("_is_st"))
            .unique(subset=["symbol"])
        )
        inst_subset = inst_subset.join(st_flag, on="symbol", how="left")

    df = df.join(inst_subset, on="symbol", how="left", suffix="_inst")

    # 换手率: API 有则直接用, 无则从 float_shares 计算
    if "turnover_rate" not in df.columns:
        if "float_shares" in df.columns and "volume" in df.columns:
            df = df.with_columns(
                pl.when(pl.col("float_shares") > 0)
                  .then(pl.col("volume") * 10000.0 / pl.col("float_shares"))
                  .otherwise(None)
                  .alias("turnover_rate")
            )

    # 涨跌停 (用 raw_close / raw_high 和前一日原始收盘价)
    # 优先用 API 原始前收盘价, 回退到 close_right, 最后回退到 raw_close
    if "_prev_close_raw" in df.columns:
        if "close_right" in df.columns:
            prev_raw = pl.when(pl.col("_prev_close_raw").is_not_null()).then(pl.col("_prev_close_raw")).otherwise(pl.col("close_right"))
        else:
            prev_raw = pl.col("_prev_close_raw")
    elif "close_right" in df.columns:
        prev_raw = pl.col("close_right")
    else:
        prev_raw = pl.col("raw_close")
    is_chinext = pl.col("symbol").str.starts_with("300") | pl.col("symbol").str.starts_with("301")
    is_star = pl.col("symbol").str.starts_with("688") | pl.col("symbol").str.starts_with("689")
    is_bj = pl.col("symbol").str.ends_with(".BJ")
    limit_pct = (
        pl.when(is_chinext).then(0.20)
        .when(is_star).then(0.20)
        .when(is_bj).then(0.30)
        .otherwise(0.10)
    )
    if "_is_st" in df.columns:
        limit_pct = pl.when(pl.col("_is_st").fill_null(False)).then(0.05).otherwise(limit_pct)
    limit_pct = limit_pct.alias("_limit_pct")

    limit_up_price = _limit_price(prev_raw, limit_pct, up=True)
    limit_down_price = _limit_price(prev_raw, limit_pct, up=False)

    # 生效涨跌停价: 优先用维表权威值 (instruments.limit_up/down, 交易所级别精确价),
    # 维表缺失 (新股上市前 5 日: limit_up 为 null 或哨兵 100000) 回退自算理论价。
    # 哨兵阈值 10000 用于识别 "新股无涨跌停限制" 的占位值 (实际涨停价不可能上万)。
    _SENTINEL = 10000.0
    if "limit_up" in df.columns:
        effective_limit_up = pl.when(
            pl.col("limit_up").is_not_null() & (pl.col("limit_up") < _SENTINEL)
        ).then(pl.col("limit_up")).otherwise(limit_up_price)
    else:
        effective_limit_up = limit_up_price
    if "limit_down" in df.columns:
        effective_limit_down = pl.when(
            pl.col("limit_down").is_not_null() & (pl.col("limit_down") < _SENTINEL)
        ).then(pl.col("limit_down")).otherwise(limit_down_price)
    else:
        effective_limit_down = limit_down_price

    is_limit_up = (
        pl.when((prev_raw > 0) & (pl.col("raw_close") > 0))
          .then(pl.col("raw_close") >= (effective_limit_up - 0.005))
          .otherwise(None).cast(pl.Boolean)
    )
    is_limit_down = (
        pl.when((prev_raw > 0) & (pl.col("raw_close") > 0))
          .then(pl.col("raw_close") <= (effective_limit_down + 0.005))
          .otherwise(None).cast(pl.Boolean)
    )

    df = df.with_columns([
        is_limit_up.alias("signal_limit_up"),
        is_limit_down.alias("signal_limit_down"),
        # 跌停翘板
        pl.when(prev_raw > 0)
          .then(
              (~is_limit_down.fill_null(True))
              & (pl.col("low") <= effective_limit_down + 0.005)
              & (pl.col("close") > pl.col("open"))
          ).otherwise(None).cast(pl.Boolean)
          .alias("signal_limit_down_recovery"),
        # 炸板: 最高价曾触及涨停价 + 最终未封住
        pl.when((prev_raw > 0) & (pl.col("raw_high") > 0))
          .then(
              (~is_limit_up.fill_null(True))
              & (pl.col("raw_high") >= effective_limit_up - 0.005)
          ).otherwise(None).cast(pl.Boolean)
          .alias("signal_broken_limit_up"),
    ])

    # 连板数: 同向 +1, 不同向归零
    # _prev_consec_up / _prev_consec_down 来自 live_agg (昨日 enriched)
    if "_prev_consec_up" not in df.columns:
        df = df.with_columns(pl.lit(0).cast(pl.UInt32).alias("_prev_consec_up"))
    if "_prev_consec_down" not in df.columns:
        df = df.with_columns(pl.lit(0).cast(pl.UInt32).alias("_prev_consec_down"))
    prev_up = pl.col("_prev_consec_up").fill_null(0).cast(pl.UInt32)
    prev_down = pl.col("_prev_consec_down").fill_null(0).cast(pl.UInt32)
    df = df.with_columns([
        pl.when(is_limit_up.fill_null(False))
          .then((prev_up + 1).cast(pl.UInt32))
          .otherwise(pl.lit(0).cast(pl.UInt32))
          .alias("consecutive_limit_ups"),
        pl.when(is_limit_down.fill_null(False))
          .then((prev_down + 1).cast(pl.UInt32))
          .otherwise(pl.lit(0).cast(pl.UInt32))
          .alias("consecutive_limit_downs"),
    ])

    # 清理
    cleanup = ["_limit_pct", "_is_st", "limit_up", "limit_down"]
    for c in df.columns:
        if c.endswith("_inst"):
            cleanup.append(c)
    for c in ["name", "float_shares"]:
        if c in df.columns:
            cleanup.append(c)
    df = df.drop([c for c in cleanup if c in df.columns])

    return df