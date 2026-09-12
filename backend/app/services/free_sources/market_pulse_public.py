"""财联社市场脉搏的自有采集、规范化与本地落库。"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import polars as pl

from app.services.atomic_io import atomic_write_parquet, write_lineage_record
from app.services.free_sources.http_resilience import ResilientHttpClient, get_shared_client

logger = logging.getLogger(__name__)

DATASET_ID = "market_pulse"
SOURCE = "cls_market_pulse"
LINEAGE_SOURCE = "cls"
UNIT_VERSION = "market_pulse_v1"
BENCHMARK_SYMBOL = "000001.SH"
BENCHMARK_NAME = "上证指数"
TLINE_ENDPOINT = "https://x-quote.cls.cn/quote/index/tline"
ANCHOR_ENDPOINT = "https://www.cls.cn/v3/transaction/anchor"
ARTIFACT_ROOT = Path("market") / "pulse"
SHANGHAI = ZoneInfo("Asia/Shanghai")

_HEADERS = {
    "Referer": "https://www.cls.cn/finance",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}
_BASE_PARAMS = {"app": "CailianpressWeb", "os": "web", "sv": "8.7.9"}

SCHEMA: dict[str, pl.DataType] = {
    "record_type": pl.Utf8,
    "event_id": pl.Utf8,
    "trade_date": pl.Date,
    "event_time": pl.Datetime("us"),
    "minute": pl.Int64,
    "benchmark_symbol": pl.Utf8,
    "benchmark_name": pl.Utf8,
    "last_price": pl.Float64,
    "change_ratio": pl.Float64,
    "preclose": pl.Float64,
    "open": pl.Float64,
    "volume": pl.Int64,
    "amount": pl.Float64,
    "sector_code": pl.Utf8,
    "sector_name": pl.Utf8,
    "direction": pl.Utf8,
    "article_id": pl.Int64,
    "source": pl.Utf8,
    "unit_version": pl.Utf8,
}
CANONICAL_COLUMNS = tuple(SCHEMA)


class MarketPulseQualityError(ValueError):
    """上游数据不能安全解释为 market_pulse_v1。"""


@dataclass(frozen=True)
class MarketPulseSyncResult:
    requested_date: str
    resolved_date: str
    minute_rows: int
    event_rows: int
    rows_published: int
    artifact_path: str
    lineage_path: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _empty_frame() -> pl.DataFrame:
    return pl.DataFrame(schema=SCHEMA)


def _artifact_relative(trade_date: date) -> Path:
    return ARTIFACT_ROOT / f"date={trade_date.isoformat()}" / "part.parquet"


def _readable_partition_files(part: Path) -> list[Path]:
    """Readable extras in one date directory. Leftover part must not hide extras."""
    from app.services.kline_sync import _parquet_probe_readable

    if not Path(part).is_dir():
        return []
    return [
        path for path in sorted(part.glob("*.parquet"))
        if path.is_file() and _parquet_probe_readable(path)
    ]


def _read_partition_dir(part: Path) -> pl.DataFrame:
    files = _readable_partition_files(part)
    if not files:
        return _empty_frame()
    frames: list[pl.DataFrame] = []
    for path in files:
        try:
            frames.append(pl.read_parquet(path).select(CANONICAL_COLUMNS))
        except Exception:
            continue
    if not frames:
        return _empty_frame()
    return frames[0] if len(frames) == 1 else pl.concat(frames, how="diagonal_relaxed")


def _minute_datetime(trade_date: date, minute: int) -> datetime:
    hour, minute_value = divmod(int(minute), 100)
    return datetime(
        trade_date.year,
        trade_date.month,
        trade_date.day,
        hour,
        minute_value,
    )


def _parse_anchor_time(value: Any) -> datetime:
    try:
        return datetime.fromisoformat(str(value or "").strip())
    except ValueError as error:
        raise MarketPulseQualityError("invalid sector event time") from error


def normalize_market_pulse(
    tline_rows: list[dict[str, Any]],
    anchor_rows: list[dict[str, Any]],
    requested_date: date,
) -> pl.DataFrame:
    records: list[dict[str, Any]] = []
    for row in tline_rows:
        upstream_date = str(row.get("date") or "")
        if upstream_date != requested_date.strftime("%Y%m%d"):
            raise MarketPulseQualityError("index minute date does not match requested date")
        minute = int(row.get("minute") or 0)
        event_time = _minute_datetime(requested_date, minute)
        records.append(
            {
                "record_type": "minute",
                "event_id": f"minute:{minute:04d}",
                "trade_date": requested_date,
                "event_time": event_time,
                "minute": minute,
                "benchmark_symbol": BENCHMARK_SYMBOL,
                "benchmark_name": BENCHMARK_NAME,
                "last_price": float(row.get("last_px") or 0),
                "change_ratio": float(row.get("change") or 0),
                "preclose": float(row.get("preclose_px") or 0),
                "open": float(row.get("open_px") or 0),
                "volume": int(row.get("business_amount") or 0),
                "amount": float(row.get("business_balance") or 0),
                "sector_code": None,
                "sector_name": None,
                "direction": None,
                "article_id": None,
                "source": SOURCE,
                "unit_version": UNIT_VERSION,
            }
        )

    for row in anchor_rows:
        event_time = _parse_anchor_time(row.get("c_time"))
        if event_time.date() != requested_date:
            raise MarketPulseQualityError("sector event date does not match requested date")
        direction = str(row.get("float") or "").strip().lower()
        sector_code = str(row.get("symbol_code") or "").strip()
        sector_name = str(row.get("symbol_name") or "").strip()
        article_id = int(row.get("article_id") or 0)
        records.append(
            {
                "record_type": "sector_event",
                "event_id": (
                    f"event:{article_id}:{sector_code}:"
                    f"{event_time.strftime('%H%M%S')}"
                ),
                "trade_date": requested_date,
                "event_time": event_time,
                "minute": event_time.hour * 100 + event_time.minute,
                "benchmark_symbol": BENCHMARK_SYMBOL,
                "benchmark_name": BENCHMARK_NAME,
                "last_price": None,
                "change_ratio": None,
                "preclose": None,
                "open": None,
                "volume": None,
                "amount": None,
                "sector_code": sector_code,
                "sector_name": sector_name,
                "direction": direction,
                "article_id": article_id,
                "source": SOURCE,
                "unit_version": UNIT_VERSION,
            }
        )

    frame = pl.DataFrame(records, schema=SCHEMA) if records else _empty_frame()
    return frame.sort(["event_time", "record_type", "event_id"])


def validate_market_pulse(frame: pl.DataFrame, requested_date: date) -> None:
    missing = [column for column in CANONICAL_COLUMNS if column not in frame.columns]
    if missing:
        raise MarketPulseQualityError(f"missing canonical columns: {', '.join(missing)}")
    if frame.is_empty():
        raise MarketPulseQualityError("market pulse payload is empty")
    if frame.select(pl.struct(["trade_date", "record_type", "event_id"]).is_duplicated().any()).item():
        raise MarketPulseQualityError("duplicate market pulse primary key")
    if frame.filter(pl.col("trade_date") != requested_date).height:
        raise MarketPulseQualityError("mixed trade dates in market pulse payload")

    minute_rows = frame.filter(pl.col("record_type") == "minute")
    if minute_rows.is_empty():
        raise MarketPulseQualityError("index minute payload is empty")
    if minute_rows.select(pl.col("minute").is_duplicated().any()).item():
        raise MarketPulseQualityError("duplicate index minute")
    if minute_rows.filter(
        (pl.col("last_price") <= 0)
        | (pl.col("preclose") <= 0)
        | (pl.col("volume") < 0)
        | (pl.col("amount") < 0)
    ).height:
        raise MarketPulseQualityError("invalid index minute price or amount")
    valid_session = (
        ((pl.col("minute") >= 930) & (pl.col("minute") <= 1130))
        | ((pl.col("minute") >= 1300) & (pl.col("minute") <= 1500))
    )
    if minute_rows.filter(~valid_session).height:
        raise MarketPulseQualityError("index minute outside A-share session")
    today = datetime.now(SHANGHAI).date()
    if requested_date < today and not 216 <= minute_rows.height <= 242:
        raise MarketPulseQualityError(
            f"historical index minute row count out of range: {minute_rows.height}"
        )
    if minute_rows.height > 242:
        raise MarketPulseQualityError("index minute row count exceeds one trading day")

    event_rows = frame.filter(pl.col("record_type") == "sector_event")
    if not event_rows.is_empty() and event_rows.filter(
        pl.col("direction").is_null()
        | ~pl.col("direction").is_in(["up", "down"])
        | pl.col("sector_code").is_null()
        | (pl.col("sector_code").str.len_chars() == 0)
        | pl.col("sector_name").is_null()
        | (pl.col("sector_name").str.len_chars() == 0)
    ).height:
        raise MarketPulseQualityError("invalid sector event fields")


def fetch_market_pulse(
    requested_date: date,
    *,
    client: ResilientHttpClient | None = None,
) -> pl.DataFrame:
    http = client or get_shared_client()
    tline = http.get_json(
        TLINE_ENDPOINT,
        source_key="cls-market-pulse-tline",
        headers=_HEADERS,
        params={**_BASE_PARAMS, "date": requested_date.strftime("%Y%m%d")},
        cooldown_on_error=15.0,
    )
    if not tline.ok:
        raise RuntimeError(f"CLS index tline unavailable: {tline.error or 'unknown error'}")
    tline_payload = tline.data if isinstance(tline.data, dict) else {}
    if tline_payload.get("code") != 200 or not isinstance(tline_payload.get("data"), list):
        raise MarketPulseQualityError("CLS index tline response is incomplete")

    anchors = http.get_json(
        ANCHOR_ENDPOINT,
        source_key="cls-market-pulse-anchors",
        headers=_HEADERS,
        params={**_BASE_PARAMS, "cdate": requested_date.isoformat()},
        cooldown_on_error=15.0,
    )
    if not anchors.ok:
        raise RuntimeError(f"CLS sector anchors unavailable: {anchors.error or 'unknown error'}")
    anchor_payload = anchors.data if isinstance(anchors.data, dict) else {}
    if anchor_payload.get("errno") != 0 or not isinstance(anchor_payload.get("data"), list):
        raise MarketPulseQualityError("CLS sector anchors response is incomplete")

    frame = normalize_market_pulse(
        [row for row in tline_payload["data"] if isinstance(row, dict)],
        [row for row in anchor_payload["data"] if isinstance(row, dict)],
        requested_date,
    )
    validate_market_pulse(frame, requested_date)
    return frame


def publish_market_pulse(
    data_dir: Path,
    requested_date: date,
    frame: pl.DataFrame,
) -> tuple[Path, Path]:
    validate_market_pulse(frame, requested_date)
    data_dir = Path(data_dir)
    relative = _artifact_relative(requested_date)
    artifact = data_dir / relative
    atomic_write_parquet(frame.select(CANONICAL_COLUMNS), artifact)
    minute_rows = frame.filter(pl.col("record_type") == "minute").height
    event_rows = frame.filter(pl.col("record_type") == "sector_event").height
    lineage = write_lineage_record(
        data_dir,
        DATASET_ID,
        {
            "date": requested_date.isoformat(),
            "source": LINEAGE_SOURCE,
            "producer": "cls",
            "provider": "public",
            "operation": "sync_market_pulse",
            "endpoints": [TLINE_ENDPOINT, ANCHOR_ENDPOINT],
            "benchmark_symbol": BENCHMARK_SYMBOL,
            "unit_version": UNIT_VERSION,
            "quality_status": "healthy",
            "scope": requested_date.isoformat(),
            "artifact_path": relative.as_posix(),
            "row_count": frame.height,
            "minute_rows": minute_rows,
            "event_rows": event_rows,
        },
        run_id=f"market-pulse-{uuid.uuid4().hex}",
    )
    return artifact, lineage


def sync_market_pulse(
    requested_date: date,
    data_dir: Path,
    *,
    client: ResilientHttpClient | None = None,
) -> MarketPulseSyncResult:
    frame = fetch_market_pulse(requested_date, client=client)
    artifact, lineage = publish_market_pulse(Path(data_dir), requested_date, frame)
    return MarketPulseSyncResult(
        requested_date=requested_date.isoformat(),
        resolved_date=requested_date.isoformat(),
        minute_rows=frame.filter(pl.col("record_type") == "minute").height,
        event_rows=frame.filter(pl.col("record_type") == "sector_event").height,
        rows_published=frame.height,
        artifact_path=artifact.relative_to(data_dir).as_posix(),
        lineage_path=lineage.relative_to(data_dir).as_posix(),
    )


def _available_dates(data_dir: Path) -> list[date]:
    root = Path(data_dir) / ARTIFACT_ROOT
    dates: list[date] = []
    if not root.exists():
        return dates
    for partition in root.glob("date=*"):
        extras = [path for path in partition.glob("*.parquet") if path.is_file()]
        if not extras:
            continue
        try:
            dates.append(date.fromisoformat(partition.name.removeprefix("date=")))
        except ValueError:
            continue
    return sorted(set(dates))


def query_market_pulse(
    data_dir: Path,
    requested_date: date | None = None,
) -> tuple[date | None, pl.DataFrame, datetime | None, list[date]]:
    """读取本地市场脉搏。

    显式指定日期时严格校验, 未通过即抛 MarketPulseQualityError。
    自动解析(未指定日期)时, 跳过未通过校验的分区(典型场景: 盘中同步留下的
    当日部分数据, 次日按历史标准失效), 回退到最近一个有效分区, 并把被跳过的
    日期一并返回供调用方披露; 不静默丢弃该事实。
    """
    data_dir = Path(data_dir)
    if requested_date is not None:
        part = data_dir / ARTIFACT_ROOT / f"date={requested_date.isoformat()}"
        files = _readable_partition_files(part)
        if not files:
            return requested_date, _empty_frame(), None, []
        frame = _read_partition_dir(part)
        validate_market_pulse(frame, requested_date)
        updated_at = datetime.fromtimestamp(max(path.stat().st_mtime for path in files), tz=SHANGHAI)
        return requested_date, frame, updated_at, []

    skipped: list[date] = []
    for candidate in reversed(_available_dates(data_dir)):
        part = data_dir / ARTIFACT_ROOT / f"date={candidate.isoformat()}"
        files = _readable_partition_files(part)
        if not files:
            continue
        frame = _read_partition_dir(part)
        try:
            validate_market_pulse(frame, candidate)
        except MarketPulseQualityError as exc:
            logger.warning(
                "skip invalid local market pulse partition date=%s: %s", candidate, exc
            )
            skipped.append(candidate)
            continue
        updated_at = datetime.fromtimestamp(max(path.stat().st_mtime for path in files), tz=SHANGHAI)
        return candidate, frame, updated_at, skipped
    return None, _empty_frame(), None, skipped
