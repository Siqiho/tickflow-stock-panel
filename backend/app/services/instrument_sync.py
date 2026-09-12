"""标的维表同步服务。

盘前 9:10 调用 tf.exchanges.get_instruments("SH"/"SZ"/"BJ", type="stock")
获取全量标的元数据，flatten ext 字段，写入 instruments.parquet。

Starter+ 盘后可用 quotes.get(universes) 顺便补充 name。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import polars as pl

from app.services.atomic_io import atomic_write_parquet, write_lineage_record
from app.tickflow.client import get_client

logger = logging.getLogger(__name__)


def instrument_route() -> str:
    """Instruments follow the daily route. There is no instrument_provider."""
    try:
        from app.services.kline_sync import daily_route

        return daily_route()
    except Exception:  # noqa: BLE001
        return "unresolved"


def instruments_sync_allowed() -> bool:
    """TickFlow instrument fetch/write only for leftover TickFlow daily."""
    return instrument_route() == "tickflow"


def instrument_cache_usable(df: pl.DataFrame | None, route: str | None = None) -> bool:
    """Whether on-disk instruments may be served for the current daily route.

    Leftover TickFlow still sees untagged files. Custom / unresolved never
    reuse leftover TickFlow universe as if it belonged to the current daily.
    """
    if df is None or getattr(df, "is_empty", lambda: True)():
        return False
    expected = (route if route is not None else instrument_route()).strip().lower()
    if not expected or expected == "unresolved":
        return False
    if "route" not in df.columns:
        return expected == "tickflow"
    stored = [str(v or "").strip().lower() for v in df["route"].to_list()]
    nonempty = [s for s in stored if s]
    if not nonempty:
        return expected == "tickflow"
    if any(s != expected for s in nonempty):
        return False
    if len(nonempty) != len(stored):
        return expected == "tickflow"
    return True


def filter_instruments(df: pl.DataFrame | None, route: str | None = None) -> pl.DataFrame:
    """Keep current-route instrument rows. Empty on leftover-only / unresolved."""
    if df is None or getattr(df, "is_empty", lambda: True)():
        return df if df is not None else pl.DataFrame()
    expected = route if route is not None else instrument_route()
    if not instrument_cache_usable(df, expected):
        return df.head(0)
    return df


def tag_instruments(df: pl.DataFrame, route: str | None = None) -> pl.DataFrame:
    token = (route if route is not None else instrument_route()).strip().lower()
    if df is None or getattr(df, "is_empty", lambda: True)() or not token or token == "unresolved":
        return df
    if "route" not in df.columns:
        return df.with_columns(pl.lit(token).alias("route"))
    tokens = pl.col("route").cast(pl.Utf8).fill_null("").str.strip_chars()
    return df.with_columns(
        pl.when(tokens == "").then(pl.lit(token)).otherwise(pl.col("route")).alias("route")
    )


def read_usable_instruments(
    data_dir,
    route: str | None = None,
    *,
    kind: str = "instruments",
) -> pl.DataFrame:
    """Current-route instrument rows. Empty on leftover-only / unresolved.

    Named ``instruments.parquet`` plus same-directory extras. Leftover TickFlow
    still sees untagged files. Same-day untagged extras beside tagged leftover
    must not concat-mix. Custom / unresolved never reuse leftover TickFlow
    universe as if it belonged to the current daily.
    """
    from app.services.kline_sync import preferred_readable_route_files

    root = Path(data_dir) / kind
    named = root / f"{kind}.parquet"
    paths: list[Path] = []
    if named.exists():
        paths.append(named)
    if root.is_dir():
        paths.extend(path for path in sorted(root.glob("*.parquet")) if path not in paths)
    expected = route if route is not None else instrument_route()
    paths = preferred_readable_route_files(paths, expected)
    frames: list[pl.DataFrame] = []
    for path in paths:
        try:
            frames.append(filter_instruments(pl.read_parquet(path), route))
        except Exception as exc:  # noqa: BLE001
            logger.debug("read usable instruments failed %s: %s", path, exc)
    if not frames:
        return pl.DataFrame()
    out = pl.concat(frames, how="diagonal_relaxed") if len(frames) > 1 else frames[0]
    if out.is_empty() or "symbol" not in out.columns or len(frames) == 1:
        return out
    return out.unique(subset=["symbol"], keep="last", maintain_order=True)

_EXCHANGES = ("SH", "SZ", "BJ")
_CHINA = ZoneInfo("Asia/Shanghai")

FIRST_SNAPSHOT_MIN_ROWS = 5_000
MIN_TOTAL_COVERAGE_RATIO = 0.95
MIN_MARKET_COVERAGE_RATIO = 0.90


@dataclass(frozen=True)
class InstrumentSyncOutcome:
    outcome: Literal["published", "kept_prior", "failed_before_publish"]
    rows_fetched: int
    rows_published: int
    market_counts: dict[str, int]
    prior_rows: int
    prior_market_counts: dict[str, int]
    failed_exchanges: tuple[str, ...] = ()
    error_code: str | None = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.outcome == "published"

    @property
    def kept_prior(self) -> bool:
        return self.outcome == "kept_prior"

    def as_dict(self) -> dict:
        return asdict(self)


def _flatten_instruments(items: list[dict]) -> list[dict]:
    """把 SDK 返回的 Instrument 列表 flatten 成扁平行。"""
    rows = []
    for item in items:
        row = {
            "symbol": item.get("symbol"),
            "name": item.get("name"),
            "code": item.get("code"),
            "exchange": item.get("exchange"),
            "region": item.get("region"),
            "type": item.get("type"),
        }
        ext = item.get("ext") or {}
        row["listing_date"] = ext.get("listing_date")
        row["total_shares"] = ext.get("total_shares")
        row["float_shares"] = ext.get("float_shares")
        row["tick_size"] = ext.get("tick_size")
        row["limit_up"] = ext.get("limit_up")
        row["limit_down"] = ext.get("limit_down")
        rows.append(row)
    return rows


def _market_counts(df: pl.DataFrame | None) -> dict[str, int]:
    if df is None or df.is_empty() or "exchange" not in df.columns:
        return {exchange: 0 for exchange in _EXCHANGES}
    return {exchange: df.filter(pl.col("exchange") == exchange).height for exchange in _EXCHANGES}


def _read_prior(path: Path) -> pl.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pl.read_parquet(path)
    except Exception as exc:
        logger.warning("read prior instruments failed: %s", exc)
        return None


def _candidate_frame(rows: list[dict]) -> tuple[pl.DataFrame | None, str | None]:
    normalized: list[dict] = []
    seen: set[str] = set()
    for raw in rows:
        row = dict(raw)
        symbol = str(row.get("symbol") or "").strip().upper()
        exchange = str(row.get("exchange") or "").strip().upper()
        code = str(row.get("code") or "").strip()
        if not symbol or "." not in symbol:
            return None, "instrument symbol is missing or malformed"
        symbol_code, suffix = symbol.rsplit(".", 1)
        if exchange not in _EXCHANGES or suffix != exchange:
            return None, f"instrument exchange mismatch: {symbol}/{exchange}"
        if code != symbol_code or len(code) != 6 or not code.isdigit():
            return None, f"instrument code mismatch: {symbol}/{code}"
        if symbol in seen:
            return None, f"duplicate instrument symbol: {symbol}"
        seen.add(symbol)
        row.update(symbol=symbol, exchange=exchange, code=code)
        normalized.append(row)
    if not normalized:
        return None, "instrument candidate is empty"
    return (
        pl.DataFrame(normalized)
        .with_columns(pl.lit(datetime.now(_CHINA).date()).alias("as_of"))
        .sort("symbol"),
        None,
    )


def _prior_is_valid(prior: pl.DataFrame | None, counts: dict[str, int]) -> bool:
    return bool(
        prior is not None
        and prior.height >= FIRST_SNAPSHOT_MIN_ROWS
        and all(counts[exchange] > 0 for exchange in _EXCHANGES)
        and "symbol" in prior.columns
        and prior.get_column("symbol").n_unique() == prior.height
    )


def _rejected(
    *,
    prior: pl.DataFrame | None,
    candidate: pl.DataFrame | None,
    prior_counts: dict[str, int],
    failed_exchanges: tuple[str, ...] = (),
    error_code: str,
    error_message: str,
) -> InstrumentSyncOutcome:
    candidate_counts = _market_counts(candidate)
    outcome = "kept_prior" if prior is not None else "failed_before_publish"
    logger.warning(
        "instruments %s: code=%s candidate_rows=%d markets=%s prior_rows=%d prior_markets=%s detail=%s",
        outcome,
        error_code,
        candidate.height if candidate is not None else 0,
        candidate_counts,
        prior.height if prior is not None else 0,
        prior_counts,
        error_message,
    )
    return InstrumentSyncOutcome(
        outcome=outcome,
        rows_fetched=candidate.height if candidate is not None else 0,
        rows_published=0,
        market_counts=candidate_counts,
        prior_rows=prior.height if prior is not None else 0,
        prior_market_counts=prior_counts,
        failed_exchanges=failed_exchanges,
        error_code=error_code,
        error_message=error_message,
    )


def sync_instruments_result(data_dir: Path) -> InstrumentSyncOutcome:
    """全量同步标的维表:候选不完整时保留整个旧快照。"""
    data_dir = Path(data_dir)
    out = data_dir / "instruments" / "instruments.parquet"
    prior = _read_prior(out)
    prior_counts = _market_counts(prior)
    if not instruments_sync_allowed():
        return _rejected(
            prior=prior,
            candidate=None,
            prior_counts=prior_counts,
            failed_exchanges=_EXCHANGES,
            error_code="instrument_route_refused",
            error_message="TickFlow instruments skipped after custom/unresolved daily",
        )

    try:
        tf = get_client()
    except Exception as exc:
        return _rejected(
            prior=prior,
            candidate=None,
            prior_counts=prior_counts,
            failed_exchanges=_EXCHANGES,
            error_code="instrument_client_unavailable",
            error_message=f"{type(exc).__name__}: {exc}",
        )
    all_rows: list[dict] = []
    failures: dict[str, str] = {}
    for exchange in _EXCHANGES:
        try:
            items = tf.exchanges.get_instruments(exchange, instrument_type="stock")
        except Exception as exc:
            failures[exchange] = f"{type(exc).__name__}: {exc}"
            logger.warning("get_instruments(%s) failed: %s", exchange, exc)
            continue
        if not items:
            failures[exchange] = "empty result"
            logger.warning("get_instruments(%s) returned no stocks", exchange)
            continue
        flattened = _flatten_instruments(items)
        for row in flattened:
            row["exchange"] = row.get("exchange") or exchange
        all_rows.extend(flattened)
        logger.info("instruments %s: %d stocks", exchange, len(flattened))

    candidate, validation_error = _candidate_frame(all_rows)
    if failures:
        failed = tuple(exchange for exchange in _EXCHANGES if exchange in failures)
        return _rejected(
            prior=prior,
            candidate=candidate,
            prior_counts=prior_counts,
            failed_exchanges=failed,
            error_code="required_exchange_incomplete",
            error_message="; ".join(f"{exchange}: {failures[exchange]}" for exchange in failed),
        )
    if validation_error is not None or candidate is None:
        return _rejected(
            prior=prior,
            candidate=candidate,
            prior_counts=prior_counts,
            error_code="instrument_candidate_invalid",
            error_message=validation_error or "instrument candidate is invalid",
        )

    counts = _market_counts(candidate)
    missing = tuple(exchange for exchange in _EXCHANGES if counts[exchange] == 0)
    if missing:
        return _rejected(
            prior=prior,
            candidate=candidate,
            prior_counts=prior_counts,
            failed_exchanges=missing,
            error_code="required_exchange_incomplete",
            error_message=f"candidate has no rows for: {', '.join(missing)}",
        )

    if _prior_is_valid(prior, prior_counts):
        assert prior is not None
        total_ratio = candidate.height / prior.height
        market_ratios = {
            exchange: counts[exchange] / prior_counts[exchange] for exchange in _EXCHANGES
        }
        if total_ratio < MIN_TOTAL_COVERAGE_RATIO or any(
            ratio < MIN_MARKET_COVERAGE_RATIO for ratio in market_ratios.values()
        ):
            return _rejected(
                prior=prior,
                candidate=candidate,
                prior_counts=prior_counts,
                error_code="coverage_below_prior",
                error_message=(
                    f"total_ratio={total_ratio:.4f}; market_ratios={market_ratios}; "
                    f"required_total={MIN_TOTAL_COVERAGE_RATIO:.2f}; "
                    f"required_market={MIN_MARKET_COVERAGE_RATIO:.2f}"
                ),
            )
    elif candidate.height < FIRST_SNAPSHOT_MIN_ROWS:
        return _rejected(
            prior=prior,
            candidate=candidate,
            prior_counts=prior_counts,
            error_code="first_snapshot_incomplete",
            error_message=(
                f"recovery/first snapshot requires at least {FIRST_SNAPSHOT_MIN_ROWS} rows "
                "with SH/SZ/BJ coverage"
            ),
        )

    atomic_write_parquet(tag_instruments(candidate), out)
    run_id = f"instruments-{uuid.uuid4().hex}"
    try:
        write_lineage_record(
            data_dir,
            "stock_instruments",
            {
                "date": datetime.now(_CHINA).date().isoformat(),
                "run_id": run_id,
                "source": "tickflow",
                "unit_version": "stock_instruments_v1",
                "quality_status": "healthy",
                "target_artifact": "instruments/instruments.parquet",
                "row_count": candidate.height,
                "market_counts": counts,
                "prior_row_count": prior.height if prior is not None else 0,
                "prior_market_counts": prior_counts,
            },
            run_id=run_id,
        )
    except Exception as exc:
        # The canonical Parquet publish is already complete and atomic. Keep the
        # serving result truthful even if the auxiliary audit sidecar cannot be written.
        logger.warning("instruments lineage write failed: %s", exc)
    logger.info("instruments published: %d rows markets=%s → %s", candidate.height, counts, out)
    return InstrumentSyncOutcome(
        outcome="published",
        rows_fetched=candidate.height,
        rows_published=candidate.height,
        market_counts=counts,
        prior_rows=prior.height if prior is not None else 0,
        prior_market_counts=prior_counts,
    )


def sync_instruments(data_dir: Path) -> int:
    """兼容旧调用:仅在完整候选正式发布时返回写入行数。

    返回写入的行数。
    """
    return sync_instruments_result(data_dir).rows_published


def enrich_names_from_quotes(
    data_dir: Path,
    quotes_data: list[dict],
) -> int:
    """从 quotes 响应中提取 name，更新 instruments 维表（兜底补充）。

    盘后 quotes.get(universes) 返回的数据中包含 ext.name，
    用来补充 instruments 中可能缺失的 name。
    """
    if not quotes_data or not instruments_sync_allowed():
        return 0

    # 构建 symbol → name 映射
    name_map: dict[str, str] = {}
    for q in quotes_data:
        symbol = q.get("symbol", "")
        ext = q.get("ext") or {}
        name = ext.get("name") or q.get("name", "")
        if symbol and name:
            name_map[symbol] = name

    if not name_map:
        return 0

    inst_path = data_dir / "instruments" / "instruments.parquet"
    if not inst_path.exists():
        return 0

    df = pl.read_parquet(inst_path)

    # 只更新空 name 的行
    updates = pl.DataFrame(
        {
            "symbol": list(name_map.keys()),
            "_new_name": list(name_map.values()),
        }
    )
    df = df.join(updates, on="symbol", how="left")
    df = df.with_columns(
        pl.when(pl.col("name").is_null() | (pl.col("name") == ""))
        .then(pl.col("_new_name"))
        .otherwise(pl.col("name"))
        .alias("name"),
    ).drop("_new_name")

    atomic_write_parquet(df, inst_path)
    logger.info("instruments name enriched from quotes: %d names", len(name_map))
    return len(name_map)
