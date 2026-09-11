"""Public A-share adjustment factors (Sina qfq.js) → event-level ex_factor.

Sina returns a *cumulative* forward factor series C(d) on corporate-action dates:
  - newest event C ≈ 1.0
  - older events C > 1
  - raw OHLC 前复权 = raw / C  (akshare stock_zh_a_sina)

one-trading pipeline stores *per-event* ratios:
  adj_factor: symbol, trade_date, ex_factor
  adjusted = raw / product(ex_factor of events strictly after bar date)
             == raw * cum_at_D / total_cum
             == raw / C_effective

Conversion (events sorted ascending by date, drop 1900-01-01 sentinel):
  for i in 1..n-1:
      ex_factor(d_i) = C(d_{i-1}) / C(d_i)

Then product(all ex) == C(oldest) and pipeline qfq matches Sina.
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterable, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl

from app.services.free_sources.http_resilience import ResilientHttpClient, get_shared_client
from app.services.atomic_io import atomic_write_parquet

logger = logging.getLogger(__name__)

SINA_QFQ_URL = "https://finance.sina.com.cn/realstock/company/{code}/qfq.js"
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.sina.com.cn/",
}

ADJ_COLS = ["symbol", "trade_date", "ex_factor"]
COVERAGE_COLS = ["symbol", "status", "source", "events_n", "checked_at", "note"]

# status:
#   events      — has real corporate-action ex_factor rows
#   no_event    — verified no dividend/split (adj identity / raw prices OK)
#   fetch_failed — public sources unavailable
_NO_EVENT_STATUS = "no_event"
_EVENTS_STATUS = "events"
_FAIL_STATUS = "fetch_failed"
_QUARANTINE_STATUS = "quarantined"


def _coverage_path(data_dir: Path, *, asset_type: str = "stock") -> Path:
    factor_dir = "adj_factor_etf" if asset_type == "etf" else "adj_factor"
    return Path(data_dir) / factor_dir / "coverage.parquet"


def read_adj_coverage(data_dir: Path, *, asset_type: str = "stock") -> pl.DataFrame:
    path = _coverage_path(data_dir, asset_type=asset_type)
    if not path.exists():
        return pl.DataFrame(
            schema={
                "symbol": pl.Utf8,
                "status": pl.Utf8,
                "source": pl.Utf8,
                "events_n": pl.Int64,
                "checked_at": pl.Utf8,
                "note": pl.Utf8,
            }
        )
    try:
        df = pl.read_parquet(path)
    except Exception as e:
        logger.warning("read adj coverage failed: %s", e)
        return pl.DataFrame(
            schema={
                "symbol": pl.Utf8,
                "status": pl.Utf8,
                "source": pl.Utf8,
                "events_n": pl.Int64,
                "checked_at": pl.Utf8,
                "note": pl.Utf8,
            }
        )
    for c, dt in (
        ("symbol", pl.Utf8),
        ("status", pl.Utf8),
        ("source", pl.Utf8),
        ("events_n", pl.Int64),
        ("checked_at", pl.Utf8),
        ("note", pl.Utf8),
    ):
        if c not in df.columns:
            df = df.with_columns(pl.lit(None).cast(dt).alias(c))
    return df.select(COVERAGE_COLS)


def merge_write_adj_coverage(
    rows: list[dict[str, Any]] | pl.DataFrame,
    data_dir: Path,
    *,
    asset_type: str = "stock",
) -> int:
    """Upsert coverage rows by symbol. Returns total coverage row count."""
    if isinstance(rows, pl.DataFrame):
        new_df = rows
    else:
        if not rows:
            return read_adj_coverage(data_dir, asset_type=asset_type).height
        new_df = pl.DataFrame(rows)
    if new_df.is_empty() or "symbol" not in new_df.columns:
        return read_adj_coverage(data_dir, asset_type=asset_type).height
    new_df = new_df.with_columns(pl.col("symbol").cast(pl.Utf8).str.to_uppercase())
    for c in COVERAGE_COLS:
        if c not in new_df.columns:
            if c == "events_n":
                new_df = new_df.with_columns(pl.lit(0).cast(pl.Int64).alias(c))
            else:
                new_df = new_df.with_columns(pl.lit(None).cast(pl.Utf8).alias(c))
    new_df = new_df.select(COVERAGE_COLS)
    existing = read_adj_coverage(data_dir, asset_type=asset_type)
    merged = (
        pl.concat([existing, new_df], how="diagonal_relaxed")
        .unique(subset=["symbol"], keep="last")
        .sort("symbol")
    )
    out = _coverage_path(data_dir, asset_type=asset_type)
    out.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_parquet(merged, out)
    return int(merged.height)


def is_sina_unit_only_cumulative(cumulative: Sequence[tuple[date, float]]) -> bool:
    """True when Sina qfq has no real scale change (only ~1.0 points / IPO placeholder)."""
    if not cumulative:
        return False
    vals = [c for _d, c in cumulative if c is not None]
    if not vals:
        return False
    return all(abs(float(c) - 1.0) < 1e-9 for c in vals)


def verify_no_corp_action_em(symbol: str, *, client: ResilientHttpClient | None = None) -> tuple[bool, str]:
    """Cross-check East Money F10 bonus page: all plans are 不分配不转增 / no ex-date.

    Returns (verified_no_event, note).
    """
    sym = (symbol or "").strip().upper()
    if "." not in sym:
        return False, "bad_symbol"
    code, mkt = sym.split(".", 1)
    client = client or get_shared_client()
    headers = {
        "User-Agent": _DEFAULT_HEADERS["User-Agent"],
        "Referer": "https://emweb.securities.eastmoney.com/",
    }
    url = (
        "https://emweb.securities.eastmoney.com/PC_HSF10/BonusFinancing/PageAjax"
        f"?code={mkt.lower()}{code}"
    )
    try:
        res = client.get_json(url, source_key="em_bonus_f10", headers=headers, timeout=15.0)
    except Exception as e:
        return False, f"em_bonus_err:{e}"
    if not res.ok or not isinstance(res.data, dict):
        return False, f"em_bonus_http:{res.error or 'no_data'}"
    rows = res.data.get("fhyx")
    if not isinstance(rows, list) or not rows:
        # empty history can still mean no actions after listing
        return True, "em_bonus_empty_history"
    actionable = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        profile = str(row.get("IMPL_PLAN_PROFILE") or row.get("IMPL_PLAN_NEWPROFILE") or "")
        ex_d = row.get("EX_DIVIDEND_DATE")
        # real cash/stock dividends or transfers usually have ex-date and non-empty plan
        if ex_d:
            actionable += 1
            continue
        if profile and ("不分配" not in profile and "不转增" not in profile):
            # e.g. 10派 / 转增 / 送
            if any(k in profile for k in ("派", "转", "送", "股", "元")):
                actionable += 1
    if actionable == 0:
        return True, "em_bonus_all_no_distribution"
    return False, f"em_bonus_actionable={actionable}"


def identity_adj_marker_row(symbol: str, as_of: date | None = None) -> dict[str, Any]:
    """One identity event so the symbol is present in adj_factor parquet.

    ex_factor=1.0 is a no-op in _apply_adj_factor (ratio stays 1).
    """
    d = as_of or date.today()
    return {"symbol": symbol.upper(), "trade_date": d, "ex_factor": 1.0}



def to_sina_code(symbol: str) -> str | None:
    """Map 000001.SZ / SH600000 / 600000 → sz000001 / sh600000."""
    s = (symbol or "").strip().upper()
    if not s:
        return None
    if s.startswith(("SH", "SZ", "BJ")) and len(s) >= 8 and s[2:].isdigit():
        return f"{s[:2].lower()}{s[2:8]}"
    if "." in s:
        code, ex = s.split(".", 1)
    else:
        code, ex = s, ""
    code = code.zfill(6) if code.isdigit() else code
    if not code.isdigit() or len(code) != 6:
        return None
    if ex == "SH" or code.startswith(("5", "6", "9")):
        return f"sh{code}"
    if ex == "BJ" or code.startswith(("4", "8")):
        return f"bj{code}"
    return f"sz{code}"


def from_sina_code(code: str) -> str:
    c = (code or "").strip().lower()
    if c.startswith("sh") and len(c) >= 8:
        return f"{c[2:8]}.SH"
    if c.startswith("sz") and len(c) >= 8:
        return f"{c[2:8]}.SZ"
    if c.startswith("bj") and len(c) >= 8:
        return f"{c[2:8]}.BJ"
    return code.upper()


def parse_sina_qfq_text(text: str) -> list[tuple[date, float]]:
    """Parse qfq.js body → sorted ascending (trade_date, cumulative_factor)."""
    if not text or "=" not in text:
        return []
    payload = text.split("=", 1)[1].split("\n", 1)[0].rstrip().rstrip(";")
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        # rare: single-quoted legacy
        try:
            obj = json.loads(payload.replace("'", '"'))
        except json.JSONDecodeError:
            return []
    rows = obj.get("data") if isinstance(obj, dict) else None
    if not isinstance(rows, list):
        return []

    out: list[tuple[date, float]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        d_raw = item.get("d") or item.get("date")
        # Stock path uses "f"; some fund payloads put scale in "s" with f==1 — skip fund-style
        # when only s/u present and f is trivially 1 with no real series (handled below).
        f_raw = item.get("f")
        if f_raw is None:
            f_raw = item.get("qfq_factor")
        if d_raw is None or f_raw is None:
            continue
        d_str = str(d_raw)[:10]
        if d_str.startswith("1900"):
            continue
        try:
            d = date.fromisoformat(d_str)
            c = float(f_raw)
        except (TypeError, ValueError):
            continue
        if c <= 0:
            continue
        out.append((d, c))

    if not out:
        return []

    # Fund/ETF payloads often keep f==1 on every row (split in other fields) — not usable as stock qfq.
    uniq_c = {round(c, 10) for _, c in out}
    if len(out) >= 2 and uniq_c == {1.0}:
        return []

    out.sort(key=lambda x: x[0])
    # de-dupe same date keep last
    dedup: dict[date, float] = {}
    for d, c in out:
        dedup[d] = c
    return sorted(dedup.items(), key=lambda x: x[0])


def cumulative_to_event_ex_factors(
    cumulative: Sequence[tuple[date, float]],
) -> list[tuple[date, float]]:
    """C ascending → event ex_factor on each date except the first.

    ex(d_i) = C(d_{i-1}) / C(d_i)
    """
    if len(cumulative) < 2:
        return []
    events: list[tuple[date, float]] = []
    for i in range(1, len(cumulative)):
        _d_prev, c_prev = cumulative[i - 1]
        d, c = cumulative[i]
        if c <= 0:
            continue
        ex = c_prev / c
        if ex <= 0:
            continue
        # skip pure noise / identical factors
        if abs(ex - 1.0) < 1e-12:
            # still keep 1.0 events? pipeline no-ops them; drop to reduce clutter
            continue
        events.append((d, float(ex)))
    return events


def is_suspicious_adj_events(events: Sequence[tuple[date, float]]) -> tuple[bool, str]:
    """Reject dense near-1 pseudo-events such as the known 689009 feed anomaly."""
    if len(events) < 120:
        return False, ""
    ordered = sorted(events, key=lambda item: item[0])
    span_days = max(1, (ordered[-1][0] - ordered[0][0]).days + 1)
    density = len(ordered) / span_days
    micro_share = sum(abs(float(factor) - 1.0) < 0.02 for _d, factor in ordered) / len(ordered)
    if density >= 0.10 and micro_share >= 0.90:
        return True, (
            f"dense_micro_events:n={len(ordered)},span_days={span_days},"
            f"density={density:.3f},micro_share={micro_share:.3f}"
        )
    return False, ""


def fetch_sina_qfq_cumulative(
    symbol: str,
    *,
    client: ResilientHttpClient | None = None,
) -> list[tuple[date, float]]:
    code = to_sina_code(symbol)
    if not code:
        return []
    client = client or get_shared_client()
    url = SINA_QFQ_URL.format(code=code)
    res = client.get_text(url, source_key="sina_qfq", headers=_DEFAULT_HEADERS, timeout=12.0)
    if not res.ok or not res.text:
        raise RuntimeError(res.error or f"sina qfq failed for {symbol}")
    return parse_sina_qfq_text(res.text)


def fetch_adj_factors_symbol(
    symbol: str,
    *,
    client: ResilientHttpClient | None = None,
    start: date | None = None,
    end: date | None = None,
    allow_identity_marker: bool = False,
) -> pl.DataFrame:
    """Return event-level factors for one symbol (may be empty).

    When allow_identity_marker=True and sources verify no corporate actions,
    returns a single ex_factor=1.0 marker row so coverage can include the symbol.
    """
    meta = fetch_adj_factors_symbol_meta(
        symbol, client=client, start=start, end=end, allow_identity_marker=allow_identity_marker
    )
    return meta["frame"]


def fetch_adj_factors_symbol_meta(
    symbol: str,
    *,
    client: ResilientHttpClient | None = None,
    start: date | None = None,
    end: date | None = None,
    allow_identity_marker: bool = True,
) -> dict[str, Any]:
    """Fetch factors + coverage metadata for one symbol."""
    empty = pl.DataFrame(schema={"symbol": pl.Utf8, "trade_date": pl.Date, "ex_factor": pl.Float64})
    sym = (symbol or "").strip().upper()
    if "." not in sym:
        code = to_sina_code(sym)
        sym = from_sina_code(code) if code else sym
    client = client or get_shared_client()
    checked = datetime.now().isoformat(timespec="seconds")

    try:
        cumulative = fetch_sina_qfq_cumulative(sym, client=client)
    except Exception as e:
        logger.warning("sina qfq %s failed: %s", sym, e)
        # try EM verification alone
        ok_em, note_em = verify_no_corp_action_em(sym, client=client)
        if ok_em and allow_identity_marker:
            row = identity_adj_marker_row(sym)
            df = pl.DataFrame([row]).with_columns(
                pl.col("trade_date").cast(pl.Date), pl.col("ex_factor").cast(pl.Float64)
            )
            return {
                "frame": df.select(ADJ_COLS),
                "coverage": {
                    "symbol": sym,
                    "status": _NO_EVENT_STATUS,
                    "source": "em_bonus+identity",
                    "events_n": 0,
                    "checked_at": checked,
                    "note": f"sina_fail;{note_em}",
                },
            }
        return {
            "frame": empty,
            "coverage": {
                "symbol": sym,
                "status": _FAIL_STATUS,
                "source": "sina_qfq",
                "events_n": 0,
                "checked_at": checked,
                "note": str(e),
            },
        }

    events = cumulative_to_event_ex_factors(cumulative)
    if events:
        suspicious, quarantine_reason = is_suspicious_adj_events(events)
        if suspicious:
            return {
                "frame": empty,
                "coverage": {
                    "symbol": sym,
                    "status": _QUARANTINE_STATUS,
                    "source": "sina_qfq",
                    "events_n": len(events),
                    "checked_at": checked,
                    "note": quarantine_reason,
                },
            }
        rows = [{"symbol": sym, "trade_date": d, "ex_factor": ex} for d, ex in events]
        df = pl.DataFrame(rows).with_columns(
            pl.col("trade_date").cast(pl.Date),
            pl.col("ex_factor").cast(pl.Float64),
        )
        if start is not None:
            df = df.filter(pl.col("trade_date") >= start)
        if end is not None:
            df = df.filter(pl.col("trade_date") <= end)
        if df.is_empty():
            # all events filtered by date window — still has history events
            return {
                "frame": empty,
                "coverage": {
                    "symbol": sym,
                    "status": _EVENTS_STATUS,
                    "source": "sina_qfq",
                    "events_n": len(events),
                    "checked_at": checked,
                    "note": "events_outside_window",
                },
            }
        return {
            "frame": df.select(ADJ_COLS),
            "coverage": {
                "symbol": sym,
                "status": _EVENTS_STATUS,
                "source": "sina_qfq",
                "events_n": int(df.height),
                "checked_at": checked,
                "note": "",
            },
        }

    # No event ratios from Sina — either never distributed, or sina incomplete.
    unit_only = is_sina_unit_only_cumulative(cumulative)
    ok_em, note_em = verify_no_corp_action_em(sym, client=client)
    if (unit_only or ok_em) and allow_identity_marker:
        # use latest cumulative date as marker when present
        as_of = cumulative[-1][0] if cumulative else date.today()
        row = identity_adj_marker_row(sym, as_of=as_of)
        df = pl.DataFrame([row]).with_columns(
            pl.col("trade_date").cast(pl.Date), pl.col("ex_factor").cast(pl.Float64)
        )
        src = "sina_unit+em_bonus" if (unit_only and ok_em) else ("sina_unit" if unit_only else "em_bonus")
        return {
            "frame": df.select(ADJ_COLS),
            "coverage": {
                "symbol": sym,
                "status": _NO_EVENT_STATUS,
                "source": src,
                "events_n": 0,
                "checked_at": checked,
                "note": note_em,
            },
        }

    return {
        "frame": empty,
        "coverage": {
            "symbol": sym,
            "status": _FAIL_STATUS if not cumulative else _NO_EVENT_STATUS,
            "source": "sina_qfq",
            "events_n": 0,
            "checked_at": checked,
            "note": f"no_events;unit_only={unit_only};{note_em}",
        },
    }


def _normalize_adj_symbols(symbols: Iterable[str]) -> list[str]:
    syms = [s.strip().upper() for s in symbols if s and str(s).strip()]
    normed: list[str] = []
    for s in syms:
        if "." in s:
            normed.append(s)
        else:
            code = to_sina_code(s)
            normed.append(from_sina_code(code) if code else s)
    seen: set[str] = set()
    ordered: list[str] = []
    for s in normed:
        if s not in seen:
            seen.add(s)
            ordered.append(s)
    return ordered


def _parse_checked_at(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo is None else raw.replace(tzinfo=None)
    try:
        s = str(raw).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo is None else dt.replace(tzinfo=None)
    except Exception:
        return None


def _recently_checked_symbols(
    data_dir: Path,
    symbols: Sequence[str],
    *,
    asset_type: str = "stock",
    within_hours: float | None,
) -> set[str]:
    """Symbols whose coverage was checked within ``within_hours`` (local clock)."""
    if within_hours is None or within_hours <= 0:
        return set()
    cov = read_adj_coverage(data_dir, asset_type=asset_type)
    if cov.is_empty() or "symbol" not in cov.columns or "checked_at" not in cov.columns:
        return set()
    want = set(symbols)
    now = datetime.now()
    out: set[str] = set()
    for row in cov.select(["symbol", "checked_at"]).to_dicts():
        sym = str(row.get("symbol") or "").upper()
        if sym not in want:
            continue
        checked = _parse_checked_at(row.get("checked_at"))
        if checked is None:
            continue
        age_h = (now - checked).total_seconds() / 3600.0
        if age_h <= float(within_hours):
            out.add(sym)
    return out


def fetch_adj_factors_batch(
    symbols: Iterable[str],
    *,
    client: ResilientHttpClient | None = None,
    start: date | None = None,
    end: date | None = None,
    pause_s: float = 0.05,
    on_progress: Callable[[int, int, str], None] | None = None,
    allow_identity_marker: bool = True,
    return_coverage: bool = False,
    workers: int = 1,
) -> pl.DataFrame | tuple[pl.DataFrame, list[dict[str, Any]]]:
    """Fetch and concat event factors for many symbols.

    ``workers>1`` enables limited concurrency (each task uses its own HTTP client).
    """
    ordered = _normalize_adj_symbols(symbols)
    frames: list[pl.DataFrame] = []
    coverage_rows: list[dict[str, Any]] = []
    total = len(ordered)
    empty_schema = {"symbol": pl.Utf8, "trade_date": pl.Date, "ex_factor": pl.Float64}
    workers_n = max(1, int(workers or 1))

    def _consume(meta: dict[str, Any]) -> None:
        df = meta.get("frame")
        if df is not None and not df.is_empty():
            frames.append(df)
        if meta.get("coverage"):
            coverage_rows.append(meta["coverage"])

    if workers_n == 1:
        client = client or get_shared_client()
        for i, sym in enumerate(ordered, 1):
            meta = fetch_adj_factors_symbol_meta(
                sym,
                client=client,
                start=start,
                end=end,
                allow_identity_marker=allow_identity_marker,
            )
            _consume(meta)
            if on_progress:
                on_progress(i, total, sym)
            if pause_s > 0 and i < total:
                time.sleep(pause_s)
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _one(sym: str) -> tuple[str, dict[str, Any]]:
            c = ResilientHttpClient(default_timeout=12.0, max_workers=2)
            meta = fetch_adj_factors_symbol_meta(
                sym,
                client=c,
                start=start,
                end=end,
                allow_identity_marker=allow_identity_marker,
            )
            return sym, meta

        done = 0
        with ThreadPoolExecutor(max_workers=workers_n, thread_name_prefix="adj-pub") as ex:
            futs = [ex.submit(_one, sym) for sym in ordered]
            for fut in as_completed(futs):
                sym, meta = fut.result()
                _consume(meta)
                done += 1
                if on_progress:
                    on_progress(done, total, sym)
                if pause_s > 0 and done < total:
                    time.sleep(pause_s)

    if not frames:
        out = pl.DataFrame(schema=empty_schema)
    else:
        out = pl.concat(frames, how="vertical_relaxed").select(ADJ_COLS)
    if return_coverage:
        return out, coverage_rows
    return out


def _select_adj_cols(df: pl.DataFrame) -> pl.DataFrame:
    cols = [c for c in ADJ_COLS if c in df.columns]
    if len(cols) < 3:
        return pl.DataFrame(schema={"symbol": pl.Utf8, "trade_date": pl.Date, "ex_factor": pl.Float64})
    if "route" in df.columns:
        cols = [*cols, "route"]
    return df.select(cols)


def merge_write_adj_factor(
    new_data: pl.DataFrame,
    data_dir: Path,
    *,
    asset_type: str = "stock",
) -> tuple[int, list[str]]:
    """Merge into data/adj_factor[/etf]/all.parquet. Returns (delta_rows_est, affected_symbols)."""
    if new_data is None or new_data.is_empty():
        return 0, []
    need = {"symbol", "trade_date", "ex_factor"}
    if not need.issubset(set(new_data.columns)):
        raise ValueError(f"adj factor frame missing columns: {need - set(new_data.columns)}")

    df = (
        new_data.select(ADJ_COLS)
        .with_columns(
            pl.col("symbol").cast(pl.Utf8),
            pl.col("trade_date").cast(pl.Date, strict=False),
            pl.col("ex_factor").cast(pl.Float64, strict=False),
        )
        .drop_nulls()
    )
    if df.is_empty():
        return 0, []

    try:
        from app.services.kline_sync import adj_cache_usable, adj_route, _tag_adj_route
        df = _tag_adj_route(df)
        route = adj_route()
    except Exception:  # noqa: BLE001
        adj_cache_usable = None
        route = ""

    affected = df["symbol"].unique().to_list()
    factor_dir = "adj_factor_etf" if asset_type == "etf" else "adj_factor"
    out = Path(data_dir) / factor_dir / "all.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)

    if out.exists():
        existing = _select_adj_cols(pl.read_parquet(out))
        if adj_cache_usable is not None and not adj_cache_usable(existing, route):
            existing = df.head(0)
        before = existing.height
        merged = (
            pl.concat([existing, df], how="diagonal_relaxed")
            .unique(subset=["symbol", "trade_date"], keep="last")
            .sort(["symbol", "trade_date"])
        )
        atomic_write_parquet(merged, out)
        added = merged.height - before
        logger.info(
            "public adj_factor merged: %d total (delta %d), %d symbols touched -> %s",
            merged.height,
            added,
            len(affected),
            out,
        )
        return added, affected

    atomic_write_parquet(df.sort(["symbol", "trade_date"]), out)
    logger.info("public adj_factor wrote: %d rows (%d symbols) -> %s", df.height, len(affected), out)
    return df.height, affected


def sync_adj_factor_public(
    symbols: Sequence[str],
    data_dir: Path,
    *,
    asset_type: str = "stock",
    start: date | datetime | None = None,
    end: date | datetime | None = None,
    pause_s: float = 0.0,
    on_progress: Callable[[int, int, str], None] | None = None,
    client: ResilientHttpClient | None = None,
    workers: int = 4,
    flush_every: int = 25,
    skip_checked_within_hours: float | None = 18.0,
) -> dict[str, Any]:
    """Pull public factors and merge-write. Always available (no TickFlow Cap).

    - skip symbols checked recently (coverage.checked_at) so daily re-runs are fast
    - limited concurrency via ``workers``
    - checkpoint merge every ``flush_every`` symbols (interrupt-safe)
    """
    def _as_date(v: date | datetime | None) -> date | None:
        if v is None:
            return None
        if isinstance(v, datetime):
            return v.date()
        return v

    start_d = _as_date(start)
    end_d = _as_date(end)
    ordered = _normalize_adj_symbols(symbols)
    workers_n = max(1, int(workers or 1))
    flush_n = max(1, int(flush_every or 1))
    t0 = time.perf_counter()

    skipped = sorted(_recently_checked_symbols(
        data_dir,
        ordered,
        asset_type=asset_type,
        within_hours=skip_checked_within_hours,
    ))
    skip_set = set(skipped)
    todo = [s for s in ordered if s not in skip_set]
    if skipped:
        logger.info(
            "public adj resume skip=%d todo=%d within_hours=%s",
            len(skipped), len(todo), skip_checked_within_hours,
        )

    pending_frames: list[pl.DataFrame] = []
    pending_coverage: list[dict[str, Any]] = []
    total_written = 0
    affected_all: list[str] = []
    done = len(skipped)
    total = len(ordered)
    pending_n = 0

    if on_progress and skipped:
        on_progress(done, total, f"skip {len(skipped)}")

    def _flush() -> None:
        nonlocal pending_n, total_written
        if pending_frames:
            df_part = pl.concat(pending_frames, how="vertical_relaxed").select(ADJ_COLS)
            written, affected = merge_write_adj_factor(df_part, data_dir, asset_type=asset_type)
            total_written += int(written)
            affected_all.extend(affected)
            pending_frames.clear()
        if pending_coverage:
            merge_write_adj_coverage(pending_coverage, data_dir, asset_type=asset_type)
            pending_coverage.clear()
        pending_n = 0

    def _consume(meta: dict[str, Any]) -> None:
        nonlocal pending_n
        df = meta.get("frame")
        if df is not None and not df.is_empty():
            pending_frames.append(df)
        if meta.get("coverage"):
            pending_coverage.append(meta["coverage"])
        pending_n += 1
        if pending_n >= flush_n:
            _flush()

    if todo and workers_n == 1:
        client = client or get_shared_client()
        for sym in todo:
            meta = fetch_adj_factors_symbol_meta(
                sym,
                client=client,
                start=start_d,
                end=end_d,
                allow_identity_marker=True,
            )
            _consume(meta)
            done += 1
            if on_progress:
                on_progress(done, total, sym)
            if pause_s > 0 and done < total:
                time.sleep(pause_s)
    elif todo:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _one(sym: str) -> tuple[str, dict[str, Any]]:
            c = ResilientHttpClient(default_timeout=12.0, max_workers=2)
            meta = fetch_adj_factors_symbol_meta(
                sym,
                client=c,
                start=start_d,
                end=end_d,
                allow_identity_marker=True,
            )
            return sym, meta

        with ThreadPoolExecutor(max_workers=workers_n, thread_name_prefix="adj-pub") as ex:
            futs = [ex.submit(_one, sym) for sym in todo]
            for fut in as_completed(futs):
                sym, meta = fut.result()
                _consume(meta)
                done += 1
                if on_progress:
                    on_progress(done, total, sym)
                if pause_s > 0 and done < total:
                    time.sleep(pause_s)

    _flush()

    cov_df = read_adj_coverage(data_dir, asset_type=asset_type)
    status_counts: dict[str, int] = {}
    if not cov_df.is_empty() and "status" in cov_df.columns:
        for row in cov_df.group_by("status").len().to_dicts():
            status_counts[str(row["status"])] = int(row["len"])
    no_event_syms = []
    if not cov_df.is_empty():
        no_event_syms = (
            cov_df.filter(pl.col("status") == _NO_EVENT_STATUS)["symbol"].to_list()
        )
    # unique affected preserve order
    aff_seen: set[str] = set()
    affected_unique: list[str] = []
    for s in affected_all:
        if s not in aff_seen:
            aff_seen.add(s)
            affected_unique.append(s)

    return {
        "ok": True,
        "source": "sina_qfq+em_bonus_fallback",
        "asset_type": asset_type,
        "requested": len(ordered),
        "symbols_skipped": skipped,
        "symbols_skipped_n": len(skipped),
        "symbols_todo_n": len(todo),
        "rows_fetched": total_written,  # approximate delta rows from merges
        "rows_delta": int(total_written),
        "symbols_affected": affected_unique,
        "symbols_affected_n": len(affected_unique),
        "coverage_rows": int(cov_df.height) if cov_df is not None else 0,
        "coverage_status_counts": status_counts,
        "no_event_symbols_n": len(no_event_syms),
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "workers": workers_n,
        "flush_every": flush_n,
        "skip_checked_within_hours": skip_checked_within_hours,
        "path": str(Path(data_dir) / ("adj_factor_etf" if asset_type == "etf" else "adj_factor") / "all.parquet"),
        "coverage_path": str(_coverage_path(data_dir, asset_type=asset_type)),
    }
