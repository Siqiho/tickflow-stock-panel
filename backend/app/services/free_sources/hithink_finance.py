"""同花顺官方金融数据服务 (fuyao.aicubes.cn) 的自有 Adapter。

只补当前数据台缺口：官方涨跌停/炸板池、龙虎榜、集合竞价快照、最新估值快照。
不替换 TickFlow 日线，不覆盖本地派生的 valuation_daily / limit_up_events。
Key 只从环境变量或本地 secrets 读取，不得写入仓库、日志或 Prompt。
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import polars as pl

from app.services.atomic_io import atomic_write_parquet, write_lineage_record

logger = logging.getLogger(__name__)

BASE_URL = "https://fuyao.aicubes.cn"
PRODUCER = "hithink_fuyao"
LINEAGE_SOURCE = "hithink_fuyao"
SHANGHAI = ZoneInfo("Asia/Shanghai")
RETRY_CODES = {4001, 5001, 5002, 5003}
MAX_RETRIES = 3
RETRY_BASE_SECONDS = 1.0
DEFAULT_TIMEOUT_SECONDS = 30.0
PAGE_SIZE = 200
MAX_PAGES = 50
VALUATION_BATCH = 100
AUCTION_BATCH = 100

LIMIT_UP_PATH = "/api/a-share/special-data/limit-up-pool"
LIMIT_DOWN_PATH = "/api/a-share/special-data/limit-down-pool"
LIMIT_BREAK_PATH = "/api/a-share/special-data/limit-break-pool"
DRAGON_TIGER_PATH = "/api/a-share/special-data/dragon-tiger-list"
AUCTION_PATH = "/api/a-share/auction/snapshot"
VALUATION_PATH = "/api/a-share/valuations/snapshot"
TICKER_SEARCH_PATH = "/api/meta/tickers/search"

LIMIT_POOL_DATASET = "hithink_limit_pool"
DRAGON_TIGER_DATASET = "hithink_dragon_tiger"
AUCTION_DATASET = "hithink_auction_snapshot"
VALUATION_DATASET = "hithink_valuation_snapshot"

LIMIT_POOL_UNIT = "hithink_limit_pool_v1"
DRAGON_TIGER_UNIT = "hithink_dragon_tiger_v1"
AUCTION_UNIT = "hithink_auction_snapshot_v1"
VALUATION_UNIT = "hithink_valuation_snapshot_v1"

LIMIT_POOL_ROOT = Path("reference") / LIMIT_POOL_DATASET
DRAGON_TIGER_ROOT = Path("reference") / DRAGON_TIGER_DATASET
AUCTION_ROOT = Path("reference") / AUCTION_DATASET
VALUATION_ROOT = Path("reference") / VALUATION_DATASET

LIMIT_POOL_SCHEMA: dict[str, pl.DataType] = {
    "pool_kind": pl.Utf8,
    "symbol": pl.Utf8,
    "ticker": pl.Utf8,
    "name": pl.Utf8,
    "trade_date": pl.Date,
    "is_st": pl.Boolean,
    "is_new": pl.Boolean,
    "last_price": pl.Float64,
    "price_change_ratio_pct": pl.Float64,
    "limit_up_time": pl.Utf8,
    "limit_up_reason": pl.Utf8,
    "continue_day_text": pl.Utf8,
    "continue_day_cnt": pl.Int64,
    "seal_money": pl.Float64,
    "max_seal_money": pl.Float64,
    "first_limit_time": pl.Utf8,
    "last_limit_time": pl.Utf8,
    "turnover_ratio_pct": pl.Float64,
    "open_times": pl.Int64,
    "turnover": pl.Float64,
    "source": pl.Utf8,
    "unit_version": pl.Utf8,
    "upstream_timestamp_ms": pl.Int64,
}
DRAGON_TIGER_SCHEMA: dict[str, pl.DataType] = {
    "symbol": pl.Utf8,
    "ticker": pl.Utf8,
    "name": pl.Utf8,
    "trade_date": pl.Date,
    "board_type": pl.Utf8,
    "concept_list": pl.Utf8,
    "change_pct": pl.Float64,
    "buy_value": pl.Float64,
    "sell_value": pl.Float64,
    "net_value": pl.Float64,
    "net_rate": pl.Float64,
    "org_net_value": pl.Float64,
    "hot_money_net_value": pl.Float64,
    "hot_rank": pl.Int64,
    "range_days": pl.Int64,
    "limit_reason": pl.Utf8,
    "source": pl.Utf8,
    "unit_version": pl.Utf8,
    "upstream_timestamp_ms": pl.Int64,
}
AUCTION_SCHEMA: dict[str, pl.DataType] = {
    "symbol": pl.Utf8,
    "ticker": pl.Utf8,
    "name": pl.Utf8,
    "trade_date": pl.Date,
    "stage": pl.Utf8,
    "auction_phase": pl.Utf8,
    "data_status": pl.Utf8,
    "auction_price": pl.Float64,
    "auction_pct": pl.Float64,
    "auction_volume": pl.Float64,
    "auction_amount": pl.Float64,
    "auction_unmatched": pl.Float64,
    "auction_turnover_pct": pl.Float64,
    "auction_yesterday_ratio_pct": pl.Float64,
    "auction_volume_ratio": pl.Float64,
    "pre_close_price": pl.Float64,
    "open_price": pl.Float64,
    "last_price": pl.Float64,
    "float_market_cap": pl.Float64,
    "source": pl.Utf8,
    "unit_version": pl.Utf8,
    "upstream_timestamp_ms": pl.Int64,
}
VALUATION_SCHEMA: dict[str, pl.DataType] = {
    "symbol": pl.Utf8,
    "ticker": pl.Utf8,
    "name": pl.Utf8,
    "as_of": pl.Date,
    "pe_ttm": pl.Float64,
    "pe_mrq": pl.Float64,
    "pb_mrq": pl.Float64,
    "ps_ttm": pl.Float64,
    "pcf_ttm": pl.Float64,
    "source": pl.Utf8,
    "unit_version": pl.Utf8,
    "upstream_timestamp_ms": pl.Int64,
}

class HiThinkFinanceError(RuntimeError):
    """官方服务调用失败或业务码非 0。"""

    def __init__(self, message: str, *, code: int | None = None, request_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.request_id = request_id


class HiThinkQualityError(ValueError):
    """上游字段不能安全解释为 one-trading canonical 契约。"""


@dataclass(frozen=True)
class DatasetPublishStats:
    dataset_id: str
    rows_published: int
    artifact_path: str
    lineage_path: str
    extra: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["extra"] = dict(self.extra)
        return payload


@dataclass(frozen=True)
class HiThinkSyncResult:
    requested_date: str
    resolved_date: str
    datasets: tuple[DatasetPublishStats, ...]
    rows_published: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "requested_date": self.requested_date,
            "resolved_date": self.resolved_date,
            "rows_published": self.rows_published,
            "datasets": [item.as_dict() for item in self.datasets],
        }


def shanghai_today() -> date:
    return datetime.now(SHANGHAI).date()


def shanghai_date_ms(value: date) -> int:
    return int(datetime(value.year, value.month, value.day, tzinfo=SHANGHAI).timestamp() * 1000)


def canonical_symbol(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text or "." not in text:
        raise HiThinkQualityError(f"invalid thscode: {value!r}")
    code, exchange = text.rsplit(".", 1)
    if not code.isdigit() or len(code) != 6 or exchange not in {"SH", "SZ", "BJ"}:
        raise HiThinkQualityError(f"unsupported A-share thscode: {value!r}")
    return f"{code}.{exchange}"


def resolve_hithink_api_key() -> str:
    for env_name in ("HITHINK_FINANCE_API_KEY", "FUYAO_TOKEN"):
        raw = os.environ.get(env_name, "").strip()
        if raw:
            return raw
    try:
        from app import secrets_store

        stored = str(secrets_store.load().get("hithink_finance_api_key") or "").strip()
        if stored:
            return stored
        stored = str(secrets_store.load_deployment().get("hithink_finance_api_key") or "").strip()
        if stored:
            return stored
    except Exception:
        logger.debug("hithink key secrets lookup failed", exc_info=True)
    try:
        from app.config import settings

        return str(getattr(settings, "hithink_finance_api_key", "") or "").strip()
    except Exception:
        return ""


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    raise HiThinkQualityError(f"invalid boolean: {value!r}")


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise HiThinkQualityError(f"invalid integer: {value!r}") from error


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise HiThinkQualityError(f"invalid number: {value!r}") from error


def _json_list(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    raise HiThinkQualityError("concept_list must be a list or string")


def _empty(schema: dict[str, pl.DataType]) -> pl.DataFrame:
    return pl.DataFrame(schema=schema)


def _artifact(root: Path, partition_name: str, partition_value: date) -> Path:
    return root / f"{partition_name}={partition_value.isoformat()}" / "part.parquet"


def _validate_unique(frame: pl.DataFrame, keys: list[str], label: str) -> None:
    if frame.is_empty():
        return
    if frame.select(pl.struct(keys).is_duplicated().any()).item():
        raise HiThinkQualityError(f"duplicate {label} primary key")

class HiThinkFinanceClient:
    """Minimal official REST client. Retries 4001/5xxx only; never retries 1xxx/2xxx."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        self.api_key = (api_key if api_key is not None else resolve_hithink_api_key()).strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.sleep = sleep
        self._client = httpx.Client(timeout=timeout, transport=transport, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HiThinkFinanceClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def get_data(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.api_key:
            raise HiThinkFinanceError("missing HITHINK_FINANCE_API_KEY")
        url = f"{self.base_url}{path}"
        clean = {key: value for key, value in (params or {}).items() if value is not None}
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self._client.get(
                    url,
                    params=clean,
                    headers={"X-api-key": self.api_key},
                )
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                last_error = error
                if attempt >= MAX_RETRIES - 1:
                    raise HiThinkFinanceError("hithink official API network failure") from error
                self.sleep(RETRY_BASE_SECONDS * (2 ** attempt))
                continue
            if response.status_code in {401, 403}:
                raise HiThinkFinanceError(
                    "hithink official API authentication failed",
                    code=response.status_code,
                )
            if response.status_code >= 500:
                last_error = HiThinkFinanceError(f"hithink official API HTTP {response.status_code}")
                if attempt >= MAX_RETRIES - 1:
                    raise last_error
                self.sleep(RETRY_BASE_SECONDS * (2 ** attempt))
                continue
            if response.status_code >= 400:
                raise HiThinkFinanceError(f"hithink official API HTTP {response.status_code}")
            try:
                payload = response.json()
            except ValueError as error:
                raise HiThinkQualityError("hithink official API returned non-JSON") from error
            if not isinstance(payload, dict):
                raise HiThinkQualityError("hithink official API envelope is not an object")
            code = payload.get("code", -1)
            if code == 0:
                data = payload.get("data")
                if data is None:
                    return {}
                if not isinstance(data, dict):
                    raise HiThinkQualityError("hithink official API data is not an object")
                return data
            if code in RETRY_CODES and attempt < MAX_RETRIES - 1:
                self.sleep(RETRY_BASE_SECONDS * (2 ** attempt))
                continue
            raise HiThinkFinanceError(
                "hithink official API business error",
                code=int(code) if isinstance(code, int) else None,
                request_id=str(payload.get("request_id") or "") or None,
            )
        if last_error:
            raise HiThinkFinanceError("hithink official API network failure") from last_error
        raise HiThinkFinanceError("hithink official API request failed")


def probe_hithink_key(api_key: str, *, client: HiThinkFinanceClient | None = None) -> bool:
    probe = client or HiThinkFinanceClient(api_key=api_key)
    owns = client is None
    try:
        data = probe.get_data(TICKER_SEARCH_PATH, {"q": "600519", "limit": 1})
        items = data.get("item") or data.get("items") or data.get("data") or []
        return isinstance(items, list)
    finally:
        if owns:
            probe.close()


def fetch_paginated_items(
    client: HiThinkFinanceClient,
    path: str,
    *,
    date_ms: int,
    extra: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], int | None]:
    items: list[dict[str, Any]] = []
    timestamp: int | None = None
    for page in range(1, MAX_PAGES + 1):
        payload = client.get_data(
            path,
            {"date_ms": date_ms, "page": page, "size": PAGE_SIZE, **(extra or {})},
        )
        timestamp = _optional_int(payload.get("timestamp"))
        batch = payload.get("item")
        if batch is None:
            batch = []
        if not isinstance(batch, list):
            raise HiThinkQualityError(f"{path} item is not a list")
        typed = [row for row in batch if isinstance(row, dict)]
        if len(typed) != len(batch):
            raise HiThinkQualityError(f"{path} item contains non-object rows")
        items.extend(typed)
        pagination = payload.get("pagination") if isinstance(payload.get("pagination"), dict) else {}
        total = _optional_int(pagination.get("total"))
        pages = _optional_int(pagination.get("pages"))
        if not typed or len(typed) < PAGE_SIZE:
            break
        if pages is not None and page >= pages:
            break
        if total is not None and len(items) >= total:
            break
    else:
        raise HiThinkQualityError(f"{path} pagination exceeded {MAX_PAGES} pages")
    return items, timestamp

def normalize_limit_pool(
    pool_kind: str,
    rows: list[dict[str, Any]],
    trade_date: date,
    *,
    timestamp_ms: int | None,
) -> pl.DataFrame:
    if pool_kind not in {"limit_up", "limit_down", "limit_break"}:
        raise HiThinkQualityError(f"unsupported pool_kind: {pool_kind}")
    records: list[dict[str, Any]] = []
    for row in rows:
        records.append(
            {
                "pool_kind": pool_kind,
                "symbol": canonical_symbol(row.get("thscode") or row.get("symbol")),
                "ticker": _optional_str(row.get("ticker")),
                "name": _optional_str(row.get("name")),
                "trade_date": trade_date,
                "is_st": _optional_bool(row.get("is_st")),
                "is_new": _optional_bool(row.get("is_new")),
                "last_price": _optional_float(row.get("last_price")),
                "price_change_ratio_pct": _optional_float(row.get("price_change_ratio_pct")),
                "limit_up_time": _optional_str(row.get("limit_up_time")),
                "limit_up_reason": _optional_str(row.get("limit_up_reason")),
                "continue_day_text": _optional_str(row.get("continue_day_text")),
                "continue_day_cnt": _optional_int(row.get("continue_day_cnt")),
                "seal_money": _optional_float(row.get("seal_money")),
                "max_seal_money": _optional_float(row.get("max_seal_money")),
                "first_limit_time": _optional_str(row.get("first_limit_time")),
                "last_limit_time": _optional_str(row.get("last_limit_time")),
                "turnover_ratio_pct": _optional_float(row.get("turnover_ratio_pct")),
                "open_times": _optional_int(row.get("open_times")),
                "turnover": _optional_float(row.get("turnover")),
                "source": PRODUCER,
                "unit_version": LIMIT_POOL_UNIT,
                "upstream_timestamp_ms": timestamp_ms,
            }
        )
    frame = pl.DataFrame(records, schema=LIMIT_POOL_SCHEMA) if records else _empty(LIMIT_POOL_SCHEMA)
    _validate_unique(frame, ["trade_date", "pool_kind", "symbol"], "limit pool")
    if frame.filter(pl.col("trade_date") != trade_date).height:
        raise HiThinkQualityError("limit pool mixed trade dates")
    return frame.sort(["pool_kind", "symbol"])


def normalize_dragon_tiger(
    payload: dict[str, Any],
    requested_date: date,
) -> tuple[pl.DataFrame, date]:
    resolved = requested_date
    raw_date = _optional_str(payload.get("trade_date"))
    if raw_date:
        try:
            resolved = date.fromisoformat(raw_date)
        except ValueError as error:
            raise HiThinkQualityError("invalid dragon-tiger trade_date") from error
        if resolved != requested_date:
            raise HiThinkQualityError("dragon-tiger trade_date does not match requested date")
    board_type = _optional_str(payload.get("board_type")) or "all"
    timestamp_ms = _optional_int(payload.get("timestamp"))
    rows = payload.get("stock_items")
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        raise HiThinkQualityError("dragon-tiger stock_items is not a list")
    records: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise HiThinkQualityError("dragon-tiger stock_items contains a non-object")
        records.append(
            {
                "symbol": canonical_symbol(row.get("thscode") or row.get("symbol")),
                "ticker": _optional_str(row.get("ticker")),
                "name": _optional_str(row.get("name")),
                "trade_date": resolved,
                "board_type": board_type,
                "concept_list": _json_list(row.get("concept_list")),
                "change_pct": _optional_float(row.get("change")),
                "buy_value": _optional_float(row.get("buy_value")),
                "sell_value": _optional_float(row.get("sell_value")),
                "net_value": _optional_float(row.get("net_value")),
                "net_rate": _optional_float(row.get("net_rate")),
                "org_net_value": _optional_float(row.get("org_net_value")),
                "hot_money_net_value": _optional_float(row.get("hot_money_net_value")),
                "hot_rank": _optional_int(row.get("hot_rank")),
                "range_days": _optional_int(row.get("range_days")),
                "limit_reason": _optional_str(row.get("limit_reason")),
                "source": PRODUCER,
                "unit_version": DRAGON_TIGER_UNIT,
                "upstream_timestamp_ms": timestamp_ms,
            }
        )
    frame = (
        pl.DataFrame(records, schema=DRAGON_TIGER_SCHEMA)
        if records
        else _empty(DRAGON_TIGER_SCHEMA)
    )
    if not frame.is_empty():
        frame = (
            frame.with_columns(
                pl.col("net_value").fill_null(0).abs().alias("_rank_net"),
                pl.col("buy_value").fill_null(0).abs().alias("_rank_buy"),
                pl.col("org_net_value").is_not_null().cast(pl.Int8).alias("_rank_org"),
            )
            .sort(["_rank_org", "_rank_net", "_rank_buy"], descending=True)
            .unique(subset=["trade_date", "board_type", "symbol"], keep="first")
            .drop(["_rank_net", "_rank_buy", "_rank_org"])
        )
    _validate_unique(frame, ["trade_date", "board_type", "symbol"], "dragon tiger")
    return frame.sort(["symbol"]), resolved

def normalize_auction_snapshot(
    payload: dict[str, Any],
    trade_date: date,
    *,
    stage: str,
) -> pl.DataFrame:
    rows = payload.get("item")
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        raise HiThinkQualityError("auction snapshot item is not a list")
    timestamp_ms = _optional_int(payload.get("timestamp"))
    auction_phase = _optional_str(payload.get("auction_phase"))
    data_status = _optional_str(payload.get("data_status"))
    records: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise HiThinkQualityError("auction snapshot contains a non-object")
        records.append(
            {
                "symbol": canonical_symbol(row.get("thscode") or row.get("symbol")),
                "ticker": _optional_str(row.get("ticker")),
                "name": _optional_str(row.get("name")),
                "trade_date": trade_date,
                "stage": stage,
                "auction_phase": auction_phase,
                "data_status": data_status,
                "auction_price": _optional_float(row.get("auction_price")),
                "auction_pct": _optional_float(row.get("auction_pct")),
                "auction_volume": _optional_float(row.get("auction_volume")),
                "auction_amount": _optional_float(row.get("auction_amount")),
                "auction_unmatched": _optional_float(row.get("auction_unmatched")),
                "auction_turnover_pct": _optional_float(row.get("auction_turnover_pct")),
                "auction_yesterday_ratio_pct": _optional_float(row.get("auction_yesterday_ratio_pct")),
                "auction_volume_ratio": _optional_float(row.get("auction_volume_ratio")),
                "pre_close_price": _optional_float(row.get("pre_close_price")),
                "open_price": _optional_float(row.get("open_price")),
                "last_price": _optional_float(row.get("last_price")),
                "float_market_cap": _optional_float(row.get("float_market_cap")),
                "source": PRODUCER,
                "unit_version": AUCTION_UNIT,
                "upstream_timestamp_ms": timestamp_ms,
            }
        )
    frame = pl.DataFrame(records, schema=AUCTION_SCHEMA) if records else _empty(AUCTION_SCHEMA)
    _validate_unique(frame, ["trade_date", "symbol", "stage"], "auction snapshot")
    return frame.sort(["symbol"])


def normalize_valuation_snapshot(
    payload: dict[str, Any],
    as_of: date,
) -> pl.DataFrame:
    rows = payload.get("item")
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        raise HiThinkQualityError("valuation snapshot item is not a list")
    timestamp_ms = _optional_int(payload.get("timestamp"))
    records: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise HiThinkQualityError("valuation snapshot contains a non-object")
        records.append(
            {
                "symbol": canonical_symbol(row.get("thscode") or row.get("symbol")),
                "ticker": _optional_str(row.get("ticker")),
                "name": _optional_str(row.get("name")),
                "as_of": as_of,
                "pe_ttm": _optional_float(row.get("pe_ttm")),
                "pe_mrq": _optional_float(row.get("pe_mrq")),
                "pb_mrq": _optional_float(row.get("pb_mrq")),
                "ps_ttm": _optional_float(row.get("ps_ttm")),
                "pcf_ttm": _optional_float(row.get("pcf_ttm")),
                "source": PRODUCER,
                "unit_version": VALUATION_UNIT,
                "upstream_timestamp_ms": timestamp_ms,
            }
        )
    frame = pl.DataFrame(records, schema=VALUATION_SCHEMA) if records else _empty(VALUATION_SCHEMA)
    _validate_unique(frame, ["symbol", "as_of"], "valuation snapshot")
    return frame.sort(["symbol"])


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def load_watchlist_symbols(data_dir: Path) -> list[str]:
    path = Path(data_dir) / "user_data" / "watchlist.parquet"
    if not path.exists():
        return []
    frame = pl.read_parquet(path)
    if "symbol" not in frame.columns:
        return []
    symbols: list[str] = []
    seen: set[str] = set()
    for raw in frame.get_column("symbol").to_list():
        try:
            symbol = canonical_symbol(raw)
        except HiThinkQualityError:
            continue
        if symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    return symbols

def _publish(
    data_dir: Path,
    dataset_id: str,
    unit_version: str,
    relative: Path,
    frame: pl.DataFrame,
    trade_date: date,
    extra: dict[str, Any],
) -> DatasetPublishStats:
    data_dir = Path(data_dir)
    artifact = data_dir / relative
    atomic_write_parquet(frame, artifact)
    lineage = write_lineage_record(
        data_dir,
        dataset_id,
        {
            "date": trade_date.isoformat(),
            "source": LINEAGE_SOURCE,
            "producer": PRODUCER,
            "provider": "hithink",
            "operation": f"sync_{dataset_id}",
            "endpoints": extra.get("endpoints", []),
            "unit_version": unit_version,
            "quality_status": "healthy",
            "scope": trade_date.isoformat(),
            "artifact_path": relative.as_posix(),
            "row_count": frame.height,
            **{key: value for key, value in extra.items() if key != "endpoints"},
        },
        run_id=f"hithink-{dataset_id}-{uuid.uuid4().hex}",
    )
    return DatasetPublishStats(
        dataset_id=dataset_id,
        rows_published=frame.height,
        artifact_path=relative.as_posix(),
        lineage_path=lineage.relative_to(data_dir).as_posix(),
        extra={key: value for key, value in extra.items() if key != "endpoints"},
    )


def sync_limit_pool(
    trade_date: date,
    data_dir: Path,
    *,
    client: HiThinkFinanceClient,
) -> DatasetPublishStats:
    date_ms = shanghai_date_ms(trade_date)
    frames: list[pl.DataFrame] = []
    counts: dict[str, int] = {}
    for pool_kind, path, extra in (
        ("limit_up", LIMIT_UP_PATH, {"sort_field": "limit_up_time", "sort_dir": "asc"}),
        ("limit_down", LIMIT_DOWN_PATH, {"sort_field": "last_limit_time", "sort_dir": "desc"}),
        ("limit_break", LIMIT_BREAK_PATH, {"sort_field": "open_times", "sort_dir": "desc"}),
    ):
        rows, timestamp_ms = fetch_paginated_items(client, path, date_ms=date_ms, extra=extra)
        frame = normalize_limit_pool(pool_kind, rows, trade_date, timestamp_ms=timestamp_ms)
        counts[pool_kind] = frame.height
        frames.append(frame)
    published = pl.concat(frames, how="vertical") if frames else _empty(LIMIT_POOL_SCHEMA)
    relative = _artifact(LIMIT_POOL_ROOT, "date", trade_date)
    return _publish(
        data_dir,
        LIMIT_POOL_DATASET,
        LIMIT_POOL_UNIT,
        relative,
        published,
        trade_date,
        {
            "endpoints": [
                f"{BASE_URL}{LIMIT_UP_PATH}",
                f"{BASE_URL}{LIMIT_DOWN_PATH}",
                f"{BASE_URL}{LIMIT_BREAK_PATH}",
            ],
            "limit_up_rows": counts.get("limit_up", 0),
            "limit_down_rows": counts.get("limit_down", 0),
            "limit_break_rows": counts.get("limit_break", 0),
        },
    )


def sync_dragon_tiger(
    trade_date: date,
    data_dir: Path,
    *,
    client: HiThinkFinanceClient,
    board_type: str = "all",
) -> DatasetPublishStats:
    payload = client.get_data(
        DRAGON_TIGER_PATH,
        {"board_type": board_type, "date": trade_date.isoformat()},
    )
    frame, resolved = normalize_dragon_tiger(payload, trade_date)
    relative = _artifact(DRAGON_TIGER_ROOT, "date", resolved)
    return _publish(
        data_dir,
        DRAGON_TIGER_DATASET,
        DRAGON_TIGER_UNIT,
        relative,
        frame,
        resolved,
        {
            "endpoints": [f"{BASE_URL}{DRAGON_TIGER_PATH}"],
            "board_type": board_type,
            "stock_count": int(payload.get("stock_count") or frame.height),
        },
    )


def sync_auction_snapshot(
    trade_date: date,
    data_dir: Path,
    symbols: list[str],
    *,
    client: HiThinkFinanceClient,
    stage: str = "final",
) -> DatasetPublishStats:
    if stage not in {"live", "final"}:
        raise HiThinkQualityError("auction stage must be live or final")
    requested = [canonical_symbol(symbol) for symbol in symbols]
    if not requested:
        raise HiThinkQualityError("auction snapshot requires at least one symbol")
    frames: list[pl.DataFrame] = []
    for batch in _chunks(requested, AUCTION_BATCH):
        payload = client.get_data(
            AUCTION_PATH,
            {"thscodes": ",".join(batch), "stage": stage},
        )
        frames.append(normalize_auction_snapshot(payload, trade_date, stage=stage))
    frame = pl.concat(frames, how="vertical") if frames else _empty(AUCTION_SCHEMA)
    _validate_unique(frame, ["trade_date", "symbol", "stage"], "auction snapshot")
    relative = _artifact(AUCTION_ROOT, "date", trade_date)
    return _publish(
        data_dir,
        AUCTION_DATASET,
        AUCTION_UNIT,
        relative,
        frame,
        trade_date,
        {
            "endpoints": [f"{BASE_URL}{AUCTION_PATH}"],
            "stage": stage,
            "symbols_requested": len(requested),
            "volume_unit": "lot",
            "amount_unit": "CNY",
        },
    )


def sync_valuation_snapshot(
    as_of: date,
    data_dir: Path,
    symbols: list[str],
    *,
    client: HiThinkFinanceClient,
) -> DatasetPublishStats:
    requested = [canonical_symbol(symbol) for symbol in symbols]
    if not requested:
        raise HiThinkQualityError("valuation snapshot requires at least one symbol")
    frames: list[pl.DataFrame] = []
    for batch in _chunks(requested, VALUATION_BATCH):
        payload = client.get_data(VALUATION_PATH, {"thscodes": ",".join(batch)})
        frames.append(normalize_valuation_snapshot(payload, as_of))
    frame = pl.concat(frames, how="vertical") if frames else _empty(VALUATION_SCHEMA)
    _validate_unique(frame, ["symbol", "as_of"], "valuation snapshot")
    relative = _artifact(VALUATION_ROOT, "as_of", as_of)
    return _publish(
        data_dir,
        VALUATION_DATASET,
        VALUATION_UNIT,
        relative,
        frame,
        as_of,
        {
            "endpoints": [f"{BASE_URL}{VALUATION_PATH}"],
            "symbols_requested": len(requested),
            "history_guarantee": "latest_snapshot_only",
        },
    )

DEFAULT_INCLUDE = ("limit_pool", "dragon_tiger", "auction", "valuation")


def sync_hithink_special_data(
    trade_date: date,
    data_dir: Path,
    *,
    include: tuple[str, ...] | list[str] = DEFAULT_INCLUDE,
    symbols: list[str] | None = None,
    client: HiThinkFinanceClient | None = None,
) -> HiThinkSyncResult:
    if trade_date > shanghai_today():
        raise HiThinkQualityError("cannot sync a future Shanghai date")
    selected = tuple(include) or DEFAULT_INCLUDE
    unknown = [item for item in selected if item not in DEFAULT_INCLUDE]
    if unknown:
        raise HiThinkQualityError(f"unsupported hithink sync target: {', '.join(unknown)}")
    owns_client = client is None
    http = client or HiThinkFinanceClient()
    published: list[DatasetPublishStats] = []
    try:
        if "limit_pool" in selected:
            published.append(sync_limit_pool(trade_date, data_dir, client=http))
        if "dragon_tiger" in selected:
            published.append(sync_dragon_tiger(trade_date, data_dir, client=http))
        needs_symbols = [item for item in selected if item in {"auction", "valuation"}]
        resolved_symbols = list(symbols or [])
        if needs_symbols and not resolved_symbols:
            resolved_symbols = load_watchlist_symbols(data_dir)
        if "auction" in selected:
            published.append(
                sync_auction_snapshot(trade_date, data_dir, resolved_symbols, client=http)
            )
        if "valuation" in selected:
            published.append(
                sync_valuation_snapshot(trade_date, data_dir, resolved_symbols, client=http)
            )
    finally:
        if owns_client:
            http.close()
    return HiThinkSyncResult(
        requested_date=trade_date.isoformat(),
        resolved_date=trade_date.isoformat(),
        datasets=tuple(published),
        rows_published=sum(item.rows_published for item in published),
    )


def _read_partition(path: Path, schema: dict[str, pl.DataType]) -> pl.DataFrame:
    if not path.exists():
        return _empty(schema)
    return pl.read_parquet(path).select(tuple(schema))


def query_limit_pool(
    data_dir: Path,
    *,
    trade_date: date | None = None,
    pool_kind: str | None = None,
    symbol: str | None = None,
    limit: int = 500,
) -> tuple[date | None, pl.DataFrame]:
    root = Path(data_dir) / LIMIT_POOL_ROOT
    resolved = trade_date
    if resolved is None:
        dates = sorted(
            date.fromisoformat(path.name.removeprefix("date="))
            for path in root.glob("date=*")
            if (path / "part.parquet").exists()
        )
        resolved = dates[-1] if dates else None
        if resolved is None:
            return None, _empty(LIMIT_POOL_SCHEMA)
    frame = _read_partition(root / f"date={resolved.isoformat()}" / "part.parquet", LIMIT_POOL_SCHEMA)
    if pool_kind:
        frame = frame.filter(pl.col("pool_kind") == pool_kind)
    if symbol:
        frame = frame.filter(pl.col("symbol") == canonical_symbol(symbol))
    return resolved, frame.head(max(1, min(int(limit), 5_000)))


def load_limit_pool_for_date(data_dir: Path | str, trade_date: date) -> pl.DataFrame | None:
    """只读指定交易日官方池。分区不存在或混了别的日期时返回 None，绝不回落到最近一日。"""
    path = Path(data_dir) / LIMIT_POOL_ROOT / f"date={trade_date.isoformat()}" / "part.parquet"
    if not path.is_file():
        return None
    try:
        frame = pl.read_parquet(path)
    except Exception:
        logger.warning("hithink limit pool unreadable: %s", path, exc_info=True)
        return None
    required = {"pool_kind", "symbol", "trade_date"}
    if frame.is_empty():
        return _empty(LIMIT_POOL_SCHEMA)
    if not required.issubset(set(frame.columns)):
        return None
    frame = frame.with_columns(pl.col("trade_date").cast(pl.Date, strict=False))
    if frame.filter(pl.col("trade_date").is_null() | (pl.col("trade_date") != trade_date)).height:
        return None
    keep = [col for col in LIMIT_POOL_SCHEMA if col in frame.columns]
    return frame.select(keep)


def summarize_limit_pool_kpi(frame: pl.DataFrame) -> dict[str, Any]:
    """把同日官方池收成看板 KPI，不写正式日、不回填昨收近似。"""
    kinds = frame.get_column("pool_kind").to_list() if frame.height and "pool_kind" in frame.columns else []
    limit_up = sum(1 for kind in kinds if kind == "limit_up")
    broken = sum(1 for kind in kinds if kind == "limit_break")
    limit_down = sum(1 for kind in kinds if kind == "limit_down")
    board_heights: list[int] = []
    if frame.height and "pool_kind" in frame.columns:
        ups = frame.filter(pl.col("pool_kind") == "limit_up")
        for raw in ups.to_dicts():
            value = raw.get("continue_day_cnt")
            try:
                height = int(value) if value is not None else 1
            except (TypeError, ValueError):
                height = 1
            if height > 0:
                board_heights.append(height)
    tiers_map: dict[int, int] = {}
    for height in board_heights:
        tiers_map[height] = tiers_map.get(height, 0) + 1
    return {
        "limit_up": limit_up,
        "broken": broken,
        "limit_down": limit_down,
        "max_boards": max(board_heights, default=0),
        "tiers": [{"boards": key, "count": value} for key, value in sorted(tiers_map.items(), key=lambda item: -item[0])],
    }


def query_dragon_tiger(
    data_dir: Path,
    *,
    trade_date: date | None = None,
    symbol: str | None = None,
    limit: int = 500,
) -> tuple[date | None, pl.DataFrame]:
    root = Path(data_dir) / DRAGON_TIGER_ROOT
    resolved = trade_date
    if resolved is None:
        dates = sorted(
            date.fromisoformat(path.name.removeprefix("date="))
            for path in root.glob("date=*")
            if (path / "part.parquet").exists()
        )
        resolved = dates[-1] if dates else None
        if resolved is None:
            return None, _empty(DRAGON_TIGER_SCHEMA)
    frame = _read_partition(
        root / f"date={resolved.isoformat()}" / "part.parquet",
        DRAGON_TIGER_SCHEMA,
    )
    if symbol:
        frame = frame.filter(pl.col("symbol") == canonical_symbol(symbol))
    return resolved, frame.head(max(1, min(int(limit), 5_000)))


def query_auction_snapshot(
    data_dir: Path,
    *,
    trade_date: date | None = None,
    symbol: str | None = None,
    limit: int = 500,
) -> tuple[date | None, pl.DataFrame]:
    root = Path(data_dir) / AUCTION_ROOT
    resolved = trade_date
    if resolved is None:
        dates = sorted(
            date.fromisoformat(path.name.removeprefix("date="))
            for path in root.glob("date=*")
            if (path / "part.parquet").exists()
        )
        resolved = dates[-1] if dates else None
        if resolved is None:
            return None, _empty(AUCTION_SCHEMA)
    frame = _read_partition(root / f"date={resolved.isoformat()}" / "part.parquet", AUCTION_SCHEMA)
    if symbol:
        frame = frame.filter(pl.col("symbol") == canonical_symbol(symbol))
    return resolved, frame.head(max(1, min(int(limit), 5_000)))


def query_valuation_snapshot(
    data_dir: Path,
    *,
    as_of: date | None = None,
    symbol: str | None = None,
    limit: int = 500,
) -> tuple[date | None, pl.DataFrame]:
    root = Path(data_dir) / VALUATION_ROOT
    resolved = as_of
    if resolved is None:
        dates = sorted(
            date.fromisoformat(path.name.removeprefix("as_of="))
            for path in root.glob("as_of=*")
            if (path / "part.parquet").exists()
        )
        resolved = dates[-1] if dates else None
        if resolved is None:
            return None, _empty(VALUATION_SCHEMA)
    frame = _read_partition(
        root / f"as_of={resolved.isoformat()}" / "part.parquet",
        VALUATION_SCHEMA,
    )
    if symbol:
        frame = frame.filter(pl.col("symbol") == canonical_symbol(symbol))
    return resolved, frame.head(max(1, min(int(limit), 5_000)))
