"""东方财富个股融资融券日数据的自有采集、规范化与本地落库。"""

from __future__ import annotations

import math
import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl

from app.services.atomic_io import atomic_write_parquet, write_lineage_record
from app.services.free_sources.http_resilience import ResilientHttpClient, get_shared_client

ENDPOINT = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
REPORT_NAME = "RPT_RZRQ_STOCKS_DETAIL"
SOURCE = "eastmoney_rzrq"
LINEAGE_SOURCE = "eastmoney"
UNIT_VERSION = "stock_margin_trading_v1"
DATASET_ID = "stock_margin_trading"
ARTIFACT_RELATIVE = Path("f10") / DATASET_ID / "part.parquet"

_HEADERS = {
    "Referer": "https://emweb.securities.eastmoney.com/",
    "Origin": "https://emweb.securities.eastmoney.com",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}
_UPSTREAM_COLUMNS = (
    "MARKET_NAME,MARKET_CODE,TRADE_DATE,SECURITY_CODE,SECUCODE,SECURITY_NAME_ABBR,"
    "FIN_BALANCE,FIN_BUY_AMT,FIN_REPAY_AMT,LOAN_BALANCE,LOAN_SELL_VOL,"
    "LOAN_REPAY_VOL,MARGIN_BALANCE,LOAN_BALANCE_VOL,FIN_NETBUY_AMT"
)

SCHEMA: dict[str, pl.DataType] = {
    "symbol": pl.Utf8,
    "name": pl.Utf8,
    "market": pl.Utf8,
    "trade_date": pl.Date,
    "financing_balance": pl.Float64,
    "financing_buy_amount": pl.Float64,
    "financing_repayment_amount": pl.Float64,
    "financing_net_buy_amount": pl.Float64,
    "securities_lending_balance": pl.Float64,
    "securities_lending_sell_volume": pl.Int64,
    "securities_lending_repayment_volume": pl.Int64,
    "securities_lending_balance_volume": pl.Int64,
    "margin_balance": pl.Float64,
    "source": pl.Utf8,
    "unit_version": pl.Utf8,
}
CANONICAL_COLUMNS = tuple(SCHEMA)
LOCAL_SOURCE = "local"
OFFLINE_SOURCE = "offline_quantdb"
OFFLINE_MARGIN_RELATIVE = Path("2_base_sector") / "margin_trading"
OFFLINE_MISSING_FIELDS = ("securities_lending_balance", "margin_balance")
OFFLINE_REQUIRED_COLUMNS = (
    "Symbol",
    "time",
    "finance_balance",
    "finance_buy",
    "finance_net",
    "slo_sell_amount",
    "finance_repay",
    "slo_volume",
    "slo_repay",
)
OFFLINE_AMOUNT_SCALE = 10_000.0
OFFLINE_NOTE = (
    "QuantDB by_symbol field-name mapping; not official Eastmoney identity. "
    "securities_lending_balance and margin_balance are absent in this file."
)


class MarginTradingQualityError(ValueError):
    """Upstream rows cannot be safely interpreted under the canonical contract."""


class MarginTradingQueryError(Exception):
    """Offline or local query cannot return a trustworthy result."""

    def __init__(self, code: str, message: str, *, http_status: int) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status


@dataclass(frozen=True)
class MarginTradingQueryResult:
    frame: pl.DataFrame
    source: str
    as_of: str | None
    status: str
    missing_fields: tuple[str, ...] = ()
    unit_version: str = UNIT_VERSION
    note: str | None = None


@dataclass(frozen=True)
class MarginTradingSyncResult:
    symbols_requested: int
    symbols_with_data: int
    empty_symbols: tuple[str, ...]
    rows_fetched: int
    rows_published: int
    latest_trade_date: str | None
    artifact_path: str | None
    lineage_path: str | None

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["empty_symbols"] = list(self.empty_symbols)
        return payload


def _empty_frame() -> pl.DataFrame:
    return pl.DataFrame(schema=SCHEMA)


def normalize_symbol(value: str) -> str:
    raw = str(value or "").strip().upper()
    if raw.startswith(("SH", "SZ", "BJ")) and len(raw) == 8:
        raw = f"{raw[2:]}.{raw[:2]}"
    if "." in raw:
        code, exchange = raw.split(".", 1)
        if len(code) == 6 and code.isdigit() and exchange in {"SH", "SZ", "BJ"}:
            return f"{code}.{exchange}"
        raise ValueError(f"invalid A-share symbol: {value}")
    if len(raw) != 6 or not raw.isdigit():
        raise ValueError(f"invalid A-share symbol: {value}")
    if raw.startswith("6") or (raw.startswith("9") and not raw.startswith("92")):
        exchange = "SH"
    elif raw.startswith(("0", "3")):
        exchange = "SZ"
    elif raw.startswith(("4", "8", "92")):
        exchange = "BJ"
    else:
        raise ValueError(f"cannot infer exchange for symbol: {value}")
    return f"{raw}.{exchange}"


def _float_value(row: dict[str, Any], key: str) -> float:
    value = row.get(key)
    if value in (None, "", "-"):
        return 0.0
    number = float(value)
    if not math.isfinite(number):
        raise MarginTradingQualityError(f"non-finite {key}")
    return number


def _int_value(row: dict[str, Any], key: str) -> int:
    return round(_float_value(row, key))


def _market_name(symbol: str, upstream: Any) -> str:
    if upstream:
        return str(upstream)
    return {"SH": "沪市", "SZ": "深市", "BJ": "北交所"}.get(symbol[-2:], symbol[-2:])


def _within_tolerance(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=1e-9, abs_tol=0.01)


def _validate_frame(frame: pl.DataFrame) -> None:
    missing = [column for column in CANONICAL_COLUMNS if column not in frame.columns]
    if missing:
        raise MarginTradingQualityError(f"missing canonical columns: {', '.join(missing)}")
    if frame.is_empty():
        return
    if frame.select(pl.struct(["symbol", "trade_date"]).is_duplicated().any()).item():
        raise MarginTradingQualityError("duplicate symbol + trade_date")
    nonnegative = (
        "financing_balance",
        "financing_buy_amount",
        "financing_repayment_amount",
        "securities_lending_balance",
        "securities_lending_sell_volume",
        "securities_lending_balance_volume",
        "margin_balance",
    )
    for column in nonnegative:
        if frame.select((pl.col(column) < 0).any()).item():
            raise MarginTradingQualityError(f"negative value in {column}")
    for row in frame.iter_rows(named=True):
        if not _within_tolerance(
            float(row["margin_balance"]),
            float(row["financing_balance"]) + float(row["securities_lending_balance"]),
        ):
            raise MarginTradingQualityError("margin balance mismatch")
        if not _within_tolerance(
            float(row["financing_net_buy_amount"]),
            float(row["financing_buy_amount"])
            - float(row["financing_repayment_amount"]),
        ):
            raise MarginTradingQualityError("financing net-buy mismatch")


def normalize_margin_trading_rows(rows: Iterable[dict[str, Any]]) -> pl.DataFrame:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        symbol = normalize_symbol(str(row.get("SECUCODE") or row.get("SECURITY_CODE") or ""))
        trade_date = date.fromisoformat(str(row.get("TRADE_DATE") or "")[:10])
        normalized.append(
            {
                "symbol": symbol,
                "name": str(row.get("SECURITY_NAME_ABBR") or "").strip(),
                "market": _market_name(symbol, row.get("MARKET_NAME")),
                "trade_date": trade_date,
                "financing_balance": _float_value(row, "FIN_BALANCE"),
                "financing_buy_amount": _float_value(row, "FIN_BUY_AMT"),
                "financing_repayment_amount": _float_value(row, "FIN_REPAY_AMT"),
                "financing_net_buy_amount": _float_value(row, "FIN_NETBUY_AMT"),
                "securities_lending_balance": _float_value(row, "LOAN_BALANCE"),
                "securities_lending_sell_volume": _int_value(row, "LOAN_SELL_VOL"),
                "securities_lending_repayment_volume": _int_value(row, "LOAN_REPAY_VOL"),
                "securities_lending_balance_volume": _int_value(row, "LOAN_BALANCE_VOL"),
                "margin_balance": _float_value(row, "MARGIN_BALANCE"),
                "source": SOURCE,
                "unit_version": UNIT_VERSION,
            }
        )
    if not normalized:
        return _empty_frame()
    frame = (
        pl.DataFrame(normalized, schema=SCHEMA)
        .unique(subset=["symbol", "trade_date"], keep="last")
        .sort(["symbol", "trade_date"])
    )
    _validate_frame(frame)
    return frame


def fetch_margin_trading(
    symbol: str,
    *,
    client: ResilientHttpClient | None = None,
    max_rows: int = 250,
    page_size: int = 100,
) -> pl.DataFrame:
    canonical_symbol = normalize_symbol(symbol)
    max_rows = max(1, min(int(max_rows), 1_000))
    page_size = max(1, min(int(page_size), 500, max_rows))
    http = client or get_shared_client()
    collected: list[dict[str, Any]] = []
    page = 1

    while len(collected) < max_rows:
        result = http.get_json(
            ENDPOINT,
            source_key=f"eastmoney-margin-trading:{canonical_symbol}",
            headers=_HEADERS,
            timeout=20.0,
            params={
                "reportName": REPORT_NAME,
                "columns": _UPSTREAM_COLUMNS,
                "quoteColumns": "",
                "filter": f'(SECUCODE="{canonical_symbol}")',
                "pageNumber": str(page),
                "pageSize": str(page_size),
                "sortTypes": "-1",
                "sortColumns": "TRADE_DATE",
                "source": "Datacenter",
                "client": "PC",
            },
            cooldown_on_error=15.0,
        )
        if not result.ok:
            raise RuntimeError(f"东方财富融资融券暂时不可用: {result.error or 'unknown error'}")
        payload = result.data if isinstance(result.data, dict) else {}
        if payload.get("success") is not True:
            message = str(payload.get("message") or "upstream rejected request")
            raise RuntimeError(f"东方财富融资融券返回失败: {message}")
        upstream_result = payload.get("result") or {}
        rows = upstream_result.get("data") or []
        if not isinstance(rows, list):
            raise MarginTradingQualityError("upstream data is not a list")
        collected.extend(item for item in rows if isinstance(item, dict))
        if len(rows) < page_size or len(collected) >= max_rows:
            break
        page += 1

    frame = normalize_margin_trading_rows(collected)
    if frame.height > max_rows:
        frame = frame.sort("trade_date", descending=True).head(max_rows).sort(
            ["symbol", "trade_date"]
        )
    return frame


def merge_margin_trading(data_dir: Path, incoming: pl.DataFrame) -> tuple[Path | None, int]:
    data_dir = Path(data_dir)
    artifact = data_dir / ARTIFACT_RELATIVE
    if incoming.is_empty():
        return (artifact if artifact.exists() else None, pl.read_parquet(artifact).height if artifact.exists() else 0)
    _validate_frame(incoming)
    if artifact.exists():
        existing = pl.read_parquet(artifact)
        _validate_frame(existing)
        merged = pl.concat([existing, incoming], how="vertical_relaxed")
    else:
        merged = incoming
    merged = merged.unique(subset=["symbol", "trade_date"], keep="last").sort(
        ["symbol", "trade_date"]
    )
    _validate_frame(merged)
    atomic_write_parquet(merged.select(CANONICAL_COLUMNS), artifact)
    return artifact, int(merged.height)


def sync_margin_trading(
    symbols: Iterable[str],
    data_dir: Path,
    *,
    client: ResilientHttpClient | None = None,
    max_rows: int = 250,
) -> MarginTradingSyncResult:
    requested = tuple(dict.fromkeys(normalize_symbol(symbol) for symbol in symbols))
    if not requested:
        raise ValueError("at least one symbol is required")
    frames: list[pl.DataFrame] = []
    empty_symbols: list[str] = []
    for symbol in requested:
        frame = fetch_margin_trading(symbol, client=client, max_rows=max_rows)
        if frame.is_empty():
            empty_symbols.append(symbol)
        else:
            frames.append(frame)

    incoming = pl.concat(frames, how="vertical_relaxed") if frames else _empty_frame()
    artifact, rows_published = merge_margin_trading(Path(data_dir), incoming)
    latest = incoming["trade_date"].max() if not incoming.is_empty() else None
    lineage_path: Path | None = None
    if artifact is not None and not incoming.is_empty():
        lineage_path = write_lineage_record(
            Path(data_dir),
            DATASET_ID,
            {
                "date": latest,
                "source": LINEAGE_SOURCE,
                "provider": "public",
                "operation": "sync_margin_trading",
                "endpoint": ENDPOINT,
                "report_name": REPORT_NAME,
                "unit_version": UNIT_VERSION,
                "quality_status": "healthy",
                "scope": ",".join(requested),
                "artifact_path": ARTIFACT_RELATIVE.as_posix(),
                "row_count": rows_published,
                "rows_fetched": int(incoming.height),
            },
            run_id=f"margin-{uuid.uuid4().hex}",
        )
    return MarginTradingSyncResult(
        symbols_requested=len(requested),
        symbols_with_data=len(frames),
        empty_symbols=tuple(empty_symbols),
        rows_fetched=int(incoming.height),
        rows_published=rows_published,
        latest_trade_date=latest.isoformat() if isinstance(latest, date) else None,
        artifact_path=(ARTIFACT_RELATIVE.as_posix() if artifact is not None else None),
        lineage_path=(lineage_path.relative_to(data_dir).as_posix() if lineage_path else None),
    )


def query_margin_trading(
    data_dir: Path,
    *,
    symbol: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 250,
    source: str = LOCAL_SOURCE,
    offline_root: Path | None = None,
) -> pl.DataFrame:
    return query_margin_trading_result(
        data_dir,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        source=source,
        offline_root=offline_root,
    ).frame


def query_margin_trading_result(
    data_dir: Path,
    *,
    symbol: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 250,
    source: str = LOCAL_SOURCE,
    offline_root: Path | None = None,
) -> MarginTradingQueryResult:
    selected = str(source or LOCAL_SOURCE).strip()
    if selected == LOCAL_SOURCE:
        return _query_local_margin_trading(
            data_dir,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
    if selected == OFFLINE_SOURCE:
        return _query_offline_quantdb_margin_trading(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offline_root=offline_root,
        )
    raise ValueError(f"unsupported margin trading source: {source}")


def _query_local_margin_trading(
    data_dir: Path,
    *,
    symbol: str | None,
    start_date: date | None,
    end_date: date | None,
    limit: int,
) -> MarginTradingQueryResult:
    artifact = Path(data_dir) / ARTIFACT_RELATIVE
    if not artifact.exists():
        return MarginTradingQueryResult(
            frame=_empty_frame(),
            source=LOCAL_SOURCE,
            as_of=None,
            status="empty",
        )
    frame = pl.read_parquet(artifact)
    _validate_frame(frame)
    as_of = _frame_as_of(frame)
    if symbol:
        frame = frame.filter(pl.col("symbol") == normalize_symbol(symbol))
    if start_date:
        frame = frame.filter(pl.col("trade_date") >= start_date)
    if end_date:
        frame = frame.filter(pl.col("trade_date") <= end_date)
    frame = frame.sort(["trade_date", "symbol"], descending=[True, False]).head(
        max(1, min(int(limit), 5_000))
    )
    return MarginTradingQueryResult(
        frame=frame,
        source=LOCAL_SOURCE,
        as_of=as_of,
        status="ok" if frame.height else "empty",
    )


def _offline_margin_path(root: Path, symbol: str) -> Path:
    canonical = normalize_symbol(symbol)
    base = (Path(root).resolve() / OFFLINE_MARGIN_RELATIVE).resolve()
    candidate = (base / f"{canonical}.parquet").resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"invalid A-share symbol: {symbol}") from exc
    if candidate.name != f"{canonical}.parquet":
        raise ValueError(f"invalid A-share symbol: {symbol}")
    return candidate


def _optional_scaled_float(value: Any, field: str) -> float | None:
    if value is None or value == "":
        return None
    number = float(value)
    if not math.isfinite(number):
        raise MarginTradingQueryError(
            "margin_trading_offline_invalid_value",
            f"non-finite {field}",
            http_status=422,
        )
    return number * OFFLINE_AMOUNT_SCALE


def _optional_int(value: Any, field: str) -> int | None:
    if value is None or value == "":
        return None
    number = float(value)
    if not math.isfinite(number):
        raise MarginTradingQueryError(
            "margin_trading_offline_invalid_value",
            f"non-finite {field}",
            http_status=422,
        )
    return round(number)


def _as_trade_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        raise MarginTradingQueryError(
            "margin_trading_offline_invalid_schema",
            "offline margin file missing trade date",
            http_status=422,
        )
    return date.fromisoformat(text[:10])


def _frame_as_of(frame: pl.DataFrame) -> str | None:
    if frame.is_empty() or "trade_date" not in frame.columns:
        return None
    latest = frame["trade_date"].max()
    if isinstance(latest, datetime):
        return latest.date().isoformat()
    if isinstance(latest, date):
        return latest.isoformat()
    return str(latest)[:10] if latest is not None else None


def map_offline_quantdb_margin_frame(frame: pl.DataFrame) -> pl.DataFrame:
    missing = [column for column in OFFLINE_REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise MarginTradingQueryError(
            "margin_trading_offline_invalid_schema",
            f"offline margin file missing columns: {', '.join(missing)}",
            http_status=422,
        )
    mapped: list[dict[str, Any]] = []
    seen: set[tuple[str, date]] = set()
    for row in frame.iter_rows(named=True):
        symbol = normalize_symbol(str(row.get("Symbol") or ""))
        trade_date = _as_trade_date(row.get("time"))
        key = (symbol, trade_date)
        if key in seen:
            raise MarginTradingQueryError(
                "margin_trading_offline_invalid_value",
                "duplicate symbol + trade_date",
                http_status=422,
            )
        seen.add(key)
        mapped.append(
            {
                "symbol": symbol,
                "name": "",
                "market": _market_name(symbol, None),
                "trade_date": trade_date,
                "financing_balance": _optional_scaled_float(
                    row.get("finance_balance"), "finance_balance"
                ),
                "financing_buy_amount": _optional_scaled_float(
                    row.get("finance_buy"), "finance_buy"
                ),
                "financing_repayment_amount": _optional_scaled_float(
                    row.get("slo_sell_amount"), "slo_sell_amount"
                ),
                "financing_net_buy_amount": _optional_scaled_float(
                    row.get("finance_net"), "finance_net"
                ),
                "securities_lending_balance": None,
                "securities_lending_sell_volume": _optional_int(
                    row.get("finance_repay"), "finance_repay"
                ),
                "securities_lending_repayment_volume": _optional_int(
                    row.get("slo_repay"), "slo_repay"
                ),
                "securities_lending_balance_volume": _optional_int(
                    row.get("slo_volume"), "slo_volume"
                ),
                "margin_balance": None,
                "source": OFFLINE_SOURCE,
                "unit_version": UNIT_VERSION,
            }
        )
    if not mapped:
        return _empty_frame()
    return pl.DataFrame(mapped, schema=SCHEMA).sort(["symbol", "trade_date"])


def _query_offline_quantdb_margin_trading(
    *,
    symbol: str | None,
    start_date: date | None,
    end_date: date | None,
    limit: int,
    offline_root: Path | None,
) -> MarginTradingQueryResult:
    if offline_root is None or not str(offline_root).strip():
        raise MarginTradingQueryError(
            "margin_trading_offline_unconfigured",
            "offline_quantdb root is not configured",
            http_status=503,
        )
    if not symbol:
        raise ValueError("symbol is required for offline_quantdb")
    path = _offline_margin_path(Path(offline_root), symbol)
    if not path.is_file():
        raise MarginTradingQueryError(
            "margin_trading_offline_not_found",
            f"offline margin file not found for {normalize_symbol(symbol)}",
            http_status=404,
        )
    try:
        raw = pl.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        raise MarginTradingQueryError(
            "margin_trading_offline_unreadable",
            f"offline margin file unreadable for {normalize_symbol(symbol)}",
            http_status=422,
        ) from exc
    mapped = map_offline_quantdb_margin_frame(raw)
    as_of = _frame_as_of(mapped)
    if start_date:
        mapped = mapped.filter(pl.col("trade_date") >= start_date)
    if end_date:
        mapped = mapped.filter(pl.col("trade_date") <= end_date)
    mapped = mapped.sort(["trade_date", "symbol"], descending=[True, False]).head(
        max(1, min(int(limit), 5_000))
    )
    return MarginTradingQueryResult(
        frame=mapped,
        source=OFFLINE_SOURCE,
        as_of=as_of,
        status="ok" if mapped.height else "empty",
        missing_fields=OFFLINE_MISSING_FIELDS,
        note=OFFLINE_NOTE,
    )
