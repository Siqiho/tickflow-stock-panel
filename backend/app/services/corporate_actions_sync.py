"""corporate_actions 数据集: 东财分红送转正式事实 + 复权因子双向核对闭环。

从分支 codex/data-platform-convergence-v1@7019d03 的
backend/app/data_sync/m5 corporate_actions 模块移植并按主树边界适配:
  - 正式事实抓取改为东财 datacenter `RPT_SHAREBONUS_DET` 批量报表
    (全市场分页, 结构化送/转/派字段, 不再逐股解析 F10 文本);
    per-symbol F10 解析器 `parse_em_bonus_rows` 保留为兼容/备选路径。
  - 分支的 egress_policy 出网许可机制未移植; 外部访问边界由显式入口
    scripts/sync-corporate-actions.py 承担, 不加入自动调度。

规则不变:
- 正式事实只来自 sourced 行(schema/unit v2); adj_factor_derived 只是验证信号
- 与 adj_factor 双向日期核对; 不一致隔离(quarantined)
- 逐股验证标记: verified_events | verified_no_event | source_failed | unverified
- 抓取失败/空网络响应永不写成 verified_no_event
"""

from __future__ import annotations

import contextlib
import hashlib
import re
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import polars as pl

from app.data_lab.publish_protocol import PublishRequest, publish_dataset
from app.services.atomic_io import atomic_write_parquet
from app.services.free_sources.adj_factor_public import (
    read_adj_coverage,
    sync_adj_factor_public,
)

# Plan markers (public API)
MARKER_VERIFIED_EVENTS = "verified_events"
MARKER_VERIFIED_NO_EVENT = "verified_no_event"
MARKER_SOURCE_FAILED = "source_failed"
MARKER_UNVERIFIED = "unverified"

# Internal adj coverage statuses
_COV_EVENTS = "events"
_COV_NO_EVENT = "no_event"
_COV_FAIL = "fetch_failed"
_COV_QUARANTINE = "quarantined"


def _utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _action_id(symbol: str, ex_date: date, action_type: str, source: str) -> str:
    raw = f"{symbol}|{ex_date.isoformat()}|{action_type}|{source}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


CORPORATE_ACTIONS_UNIT_VERSION = "corporate_actions_v2"
CORPORATE_ACTIONS_SCHEMA_VERSION = "2"
FORMAL_EVENT_SOURCES = frozenset(
    {
        "eastmoney_bonus_f10",
        "eastmoney_sharebonus_det",
        "cninfo_crosscheck",
        "exchange_notice",
    }
)
VERIFICATION_SIGNAL_SOURCES = frozenset({"adj_factor_derived"})

_SHAREBONUS_ENDPOINT = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_SHAREBONUS_HEADERS = {
    "Referer": "https://data.eastmoney.com/",
    "User-Agent": "Mozilla/5.0",
}


def empty_corporate_actions() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "symbol": pl.Utf8,
            "action_id": pl.Utf8,
            "action_type": pl.Utf8,
            "announce_date": pl.Date,
            "record_date": pl.Date,
            "ex_date": pl.Date,
            "pay_date": pl.Date,
            "cash_per_share": pl.Float64,
            "stock_ratio": pl.Float64,
            "rights_ratio": pl.Float64,
            "currency": pl.Utf8,
            "source_published_at": pl.Datetime(time_unit="us"),
            "first_seen_at": pl.Datetime(time_unit="us"),
            "source": pl.Utf8,
            "as_of": pl.Date,
            # M5.3 v2 fields
            "source_record_id": pl.Utf8,
            "source_url": pl.Utf8,
            "plan_status": pl.Utf8,
            "raw_plan_text": pl.Utf8,
            "raw_unit": pl.Utf8,
            "history_guarantee": pl.Utf8,
            "verification_status": pl.Utf8,
            "is_verification_signal": pl.Boolean,
            "schema_version": pl.Utf8,
            "unit_version": pl.Utf8,
        }
    )


def ensure_corporate_actions_v2(df: pl.DataFrame) -> pl.DataFrame:
    """Ensure v2 columns exist; adj_factor_derived marked verification_signal only."""
    if df is None:
        return empty_corporate_actions()
    if df.is_empty() and not df.columns:
        return empty_corporate_actions()
    out = df
    defaults: dict[str, object] = {
        "source_record_id": None,
        "source_url": None,
        "plan_status": "unknown",
        "raw_plan_text": None,
        "raw_unit": None,
        "history_guarantee": "as_collected",
        "verification_status": MARKER_UNVERIFIED,
        "is_verification_signal": False,
        "schema_version": CORPORATE_ACTIONS_SCHEMA_VERSION,
        "unit_version": CORPORATE_ACTIONS_UNIT_VERSION,
    }
    for col, default in defaults.items():
        if col not in out.columns:
            if default is None:
                if col in {"is_verification_signal"}:
                    out = out.with_columns(pl.lit(False).alias(col))
                else:
                    out = out.with_columns(pl.lit(None).cast(pl.Utf8).alias(col))
            elif isinstance(default, bool):
                out = out.with_columns(pl.lit(default).alias(col))
            else:
                out = out.with_columns(pl.lit(str(default)).alias(col))
    # Mark verification signals
    if "source" in out.columns:
        out = out.with_columns(
            (
                pl.col("source").is_in(list(VERIFICATION_SIGNAL_SOURCES))
                | (pl.col("action_type") == "identity_marker")
            ).alias("is_verification_signal")
        )
        # adj-derived unknown events are verification signals, not formal facts
        out = out.with_columns(
            pl.when(pl.col("source").is_in(list(VERIFICATION_SIGNAL_SOURCES)))
            .then(pl.lit("verification_signal"))
            .otherwise(pl.col("plan_status").fill_null("unknown"))
            .alias("plan_status")
        )
    out = out.with_columns(
        [
            pl.lit(CORPORATE_ACTIONS_SCHEMA_VERSION).alias("schema_version"),
            pl.lit(CORPORATE_ACTIONS_UNIT_VERSION).alias("unit_version"),
        ]
    )
    return out


def formal_event_facts(df: pl.DataFrame) -> pl.DataFrame:
    """Return only non-signal corporate action facts for production-facing consumers."""
    out = ensure_corporate_actions_v2(df)
    if out.is_empty():
        return out
    return out.filter(~pl.col("is_verification_signal").fill_null(False))


def load_adj_factor_frame(data_dir: Path, *, asset_type: str = "stock") -> pl.DataFrame:
    from app.services.kline_sync import get_adj_factor_df

    return get_adj_factor_df(data_dir, asset_type=asset_type)


def map_coverage_status_to_marker(status: str | None, *, crosscheck_ok: bool | None = None) -> str:
    """Map internal coverage status → plan verification marker.

    Important: fetch_failed never becomes verified_no_event.
    """
    s = (status or "").strip().lower()
    if s == _COV_FAIL:
        return MARKER_SOURCE_FAILED
    if s == _COV_QUARANTINE:
        return MARKER_UNVERIFIED
    if s == _COV_NO_EVENT:
        # only verified when source explicitly confirmed no event
        return MARKER_VERIFIED_NO_EVENT
    if s == _COV_EVENTS:
        if crosscheck_ok is False:
            return MARKER_UNVERIFIED
        return MARKER_VERIFIED_EVENTS
    return MARKER_UNVERIFIED


def corporate_actions_from_adj_events(
    adj: pl.DataFrame,
    *,
    as_of: date | None = None,
    source: str = "adj_factor_derived",
) -> pl.DataFrame:
    """Derive corporate_actions skeleton from event-level ex_factor rows.

    Factor feeds usually lack cash/stock split detail — action_type=unknown unless
    ex_factor==1.0 identity marker.
    """
    as_of = as_of or date.today()
    if adj is None or adj.is_empty():
        return empty_corporate_actions()
    df = adj
    if "trade_date" not in df.columns or "symbol" not in df.columns:
        return empty_corporate_actions()
    seen = _utc_naive()
    rows: list[dict[str, Any]] = []
    for item in df.select(
        [c for c in ("symbol", "trade_date", "ex_factor") if c in df.columns]
    ).to_dicts():
        sym = str(item.get("symbol") or "").upper()
        ex_d = item.get("trade_date")
        if not sym or ex_d is None:
            continue
        if isinstance(ex_d, datetime):
            ex_d = ex_d.date()
        elif not isinstance(ex_d, date):
            try:
                ex_d = date.fromisoformat(str(ex_d)[:10])
            except ValueError:
                continue
        ex_f = item.get("ex_factor")
        try:
            ex_f_f = float(ex_f) if ex_f is not None else None
        except (TypeError, ValueError):
            ex_f_f = None
        if ex_f_f is not None and abs(ex_f_f - 1.0) < 1e-12:
            action_type = "identity_marker"
        else:
            action_type = "unknown"
        aid = _action_id(sym, ex_d, action_type, source)
        rows.append(
            {
                "symbol": sym,
                "action_id": aid,
                "action_type": action_type,
                "announce_date": None,
                "record_date": None,
                "ex_date": ex_d,
                "pay_date": None,
                "cash_per_share": None,
                "stock_ratio": None,
                "rights_ratio": None,
                "currency": "CNY" if action_type != "identity_marker" else "unknown",
                "source_published_at": seen,
                "first_seen_at": seen,
                "source": source,
                "as_of": as_of,
                "source_record_id": f"adj:{sym}:{ex_d.isoformat()}:{ex_f_f}",
                "source_url": None,
                "plan_status": "verification_signal",
                "raw_plan_text": None,
                "raw_unit": "ex_factor",
                "history_guarantee": "as_collected",
                "verification_status": MARKER_UNVERIFIED,
                "is_verification_signal": True,
                "schema_version": CORPORATE_ACTIONS_SCHEMA_VERSION,
                "unit_version": CORPORATE_ACTIONS_UNIT_VERSION,
            }
        )
    if not rows:
        return empty_corporate_actions()
    return ensure_corporate_actions_v2(
        pl.DataFrame(rows)
        .unique(subset=["symbol", "action_id"], keep="last")
        .sort(["symbol", "ex_date"])
    )


def parse_em_bonus_rows(
    rows: list[dict[str, Any]],
    *,
    symbol: str,
    as_of: date | None = None,
    source: str = "eastmoney_bonus_f10",
) -> pl.DataFrame:
    """Normalize East Money F10 bonus rows into corporate_actions (optional enricher)."""
    as_of = as_of or date.today()
    seen = _utc_naive()
    out: list[dict[str, Any]] = []
    sym = symbol.upper()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        profile = str(row.get("IMPL_PLAN_PROFILE") or row.get("IMPL_PLAN_NEWPROFILE") or "")
        ex_raw = row.get("EX_DIVIDEND_DATE") or row.get("EX_DATE")
        if not ex_raw:
            continue
        try:
            ex_d = date.fromisoformat(str(ex_raw)[:10])
        except ValueError:
            continue
        announce_raw = row.get("NOTICE_DATE") or row.get("ASSIGN_RECORD_DATE")
        announce_d = None
        if announce_raw:
            try:
                announce_d = date.fromisoformat(str(announce_raw)[:10])
            except ValueError:
                announce_d = None
        cash = None
        stock_ratio = None
        # crude parse: 10派X元 / 10转Y / 10送Z
        m_cash = re.search(r"派\s*([0-9]+(?:\.[0-9]+)?)\s*元", profile)
        if m_cash:
            try:
                cash = float(m_cash.group(1)) / 10.0
            except ValueError:
                cash = None
        m_zhuan = re.search(r"转\s*([0-9]+(?:\.[0-9]+)?)", profile)
        m_song = re.search(r"送\s*([0-9]+(?:\.[0-9]+)?)", profile)
        ratios = []
        for m in (m_zhuan, m_song):
            if m:
                with contextlib.suppress(ValueError):
                    ratios.append(float(m.group(1)) / 10.0)
        if ratios:
            stock_ratio = sum(ratios)
        if cash is not None and stock_ratio is not None:
            action_type = "mixed"
        elif cash is not None:
            action_type = "dividend_cash"
        elif stock_ratio is not None:
            action_type = "bonus"
        else:
            action_type = "unknown"
        code, _, mkt = sym.partition(".")
        source_url = (
            "https://emweb.securities.eastmoney.com/PC_HSF10/BonusFinancing/Index"
            f"?type=web&code={mkt.lower()}{code}"
        )
        source_record_id = str(
            row.get("SECUCODE")
            or row.get("SECURITY_CODE")
            or row.get("NOTICE_DATE")
            or f"{sym}:{ex_d.isoformat()}:{profile}"
        )
        # plan implementation status if present
        plan_status = str(row.get("ASSIGN_PROGRESS") or row.get("IMPL_PROGRESS") or "announced").strip() or "announced"
        aid = _action_id(sym, ex_d, action_type, source + ":" + source_record_id)
        out.append(
            {
                "symbol": sym,
                "action_id": aid,
                "action_type": action_type,
                "announce_date": announce_d,
                "record_date": None,
                "ex_date": ex_d,
                "pay_date": None,
                "cash_per_share": cash,
                "stock_ratio": stock_ratio,
                "rights_ratio": None,
                "currency": "CNY",
                "source_published_at": seen,
                "first_seen_at": seen,
                "source": source,
                "as_of": as_of,
                "source_record_id": source_record_id,
                "source_url": source_url,
                "plan_status": plan_status,
                "raw_plan_text": profile or None,
                "raw_unit": "per_10_shares_plan_text",
                "history_guarantee": "as_collected",
                "verification_status": MARKER_UNVERIFIED,
                "is_verification_signal": False,
                "schema_version": CORPORATE_ACTIONS_SCHEMA_VERSION,
                "unit_version": CORPORATE_ACTIONS_UNIT_VERSION,
            }
        )
    if not out:
        return empty_corporate_actions()
    return ensure_corporate_actions_v2(pl.DataFrame(out, schema=empty_corporate_actions().schema))


def merge_corporate_actions(*frames: pl.DataFrame) -> pl.DataFrame:
    parts = [ensure_corporate_actions_v2(f) for f in frames if f is not None and not f.is_empty()]
    if not parts:
        return empty_corporate_actions()
    return ensure_corporate_actions_v2(
        pl.concat(parts, how="diagonal_relaxed")
        .unique(subset=["symbol", "action_id"], keep="last")
        .sort(["symbol", "ex_date", "action_type"])
    )


def crosscheck_actions_vs_adj(
    actions: pl.DataFrame,
    adj: pl.DataFrame,
    *,
    date_tol_days: int = 0,
) -> dict[str, Any]:
    """Bidirectional date-level cross-check per symbol.

    Returns summary + per-symbol agreement flags.
    identity_marker actions are ignored on the action side for event matching.
    """
    act = actions
    if act is None or act.is_empty():
        act_events = empty_corporate_actions()
    else:
        act_events = act.filter(~pl.col("action_type").is_in(["identity_marker"]))

    adj_f = adj if adj is not None else pl.DataFrame()
    if not adj_f.is_empty() and "ex_factor" in adj_f.columns:
        # ignore pure identity markers in adj for event matching
        adj_events = adj_f.filter(
            pl.col("ex_factor").is_not_null() & ((pl.col("ex_factor") - 1.0).abs() > 1e-12)
        )
    else:
        adj_events = adj_f

    symbols = set()
    if not act_events.is_empty():
        symbols |= set(act_events.get_column("symbol").to_list())
    if not adj_events.is_empty() and "symbol" in adj_events.columns:
        symbols |= set(adj_events.get_column("symbol").to_list())

    per_symbol: list[dict[str, Any]] = []
    matched_total = 0
    only_actions = 0
    only_adj = 0
    for sym in sorted(symbols):
        a_dates: set[date] = set()
        f_dates: set[date] = set()
        if not act_events.is_empty():
            for d in act_events.filter(pl.col("symbol") == sym).get_column("ex_date").to_list():
                if d is None:
                    continue
                if isinstance(d, datetime):
                    d = d.date()
                elif not isinstance(d, date):
                    try:
                        d = date.fromisoformat(str(d)[:10])
                    except ValueError:
                        continue
                a_dates.add(d)
        if not adj_events.is_empty():
            for d in adj_events.filter(pl.col("symbol") == sym).get_column("trade_date").to_list():
                if d is None:
                    continue
                if isinstance(d, datetime):
                    d = d.date()
                elif not isinstance(d, date):
                    try:
                        d = date.fromisoformat(str(d)[:10])
                    except ValueError:
                        continue
                f_dates.add(d)
        if date_tol_days <= 0:
            inter = a_dates & f_dates
            only_a = a_dates - f_dates
            only_f = f_dates - a_dates
        else:
            inter = set()
            only_a = set(a_dates)
            only_f = set(f_dates)
            for ad in list(only_a):
                for fd in list(only_f):
                    if abs((ad - fd).days) <= date_tol_days:
                        inter.add(ad)
                        only_a.discard(ad)
                        only_f.discard(fd)
                        break
        matched_total += len(inter)
        only_actions += len(only_a)
        only_adj += len(only_f)
        ok = len(only_a) == 0 and len(only_f) == 0
        # both empty → no events agreed
        if not a_dates and not f_dates:
            ok = True
        per_symbol.append(
            {
                "symbol": sym,
                "action_ex_dates": len(a_dates),
                "adj_ex_dates": len(f_dates),
                "matched": len(inter),
                "only_actions": len(only_a),
                "only_adj": len(only_f),
                "crosscheck_ok": ok,
            }
        )

    return {
        "symbols": len(per_symbol),
        "matched_dates": matched_total,
        "only_actions_dates": only_actions,
        "only_adj_dates": only_adj,
        "agreement_ratio": (
            sum(1 for r in per_symbol if r["crosscheck_ok"]) / len(per_symbol)
            if per_symbol
            else 1.0
        ),
        "per_symbol": per_symbol,
    }


def build_verification_table(
    *,
    coverage: pl.DataFrame,
    crosscheck: dict[str, Any],
    universe: Iterable[str] | None = None,
) -> pl.DataFrame:
    """Per-symbol verification markers for E5.

    Markers:
      verified_events / verified_no_event / source_failed / unverified
    """
    cc_map = {
        r["symbol"]: bool(r.get("crosscheck_ok"))
        for r in (crosscheck.get("per_symbol") or [])
        if r.get("symbol")
    }
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    if coverage is not None and not coverage.is_empty():
        for item in coverage.to_dicts():
            sym = str(item.get("symbol") or "").upper()
            if not sym:
                continue
            seen.add(sym)
            status = item.get("status")
            marker = map_coverage_status_to_marker(
                status, crosscheck_ok=cc_map.get(sym)
            )
            rows.append(
                {
                    "symbol": sym,
                    "verification": marker,
                    "coverage_status": status,
                    "source": item.get("source"),
                    "events_n": item.get("events_n"),
                    "crosscheck_ok": cc_map.get(sym),
                    "note": item.get("note"),
                    "checked_at": item.get("checked_at"),
                }
            )
    if universe is not None:
        for s in universe:
            sym = str(s).upper().strip()
            if not sym or sym in seen:
                continue
            # not fetched yet — unverified, NOT verified_no_event
            rows.append(
                {
                    "symbol": sym,
                    "verification": MARKER_UNVERIFIED,
                    "coverage_status": None,
                    "source": None,
                    "events_n": None,
                    "crosscheck_ok": None,
                    "note": "not_fetched",
                    "checked_at": None,
                }
            )
    if not rows:
        return pl.DataFrame(
            schema={
                "symbol": pl.Utf8,
                "verification": pl.Utf8,
                "coverage_status": pl.Utf8,
                "source": pl.Utf8,
                "events_n": pl.Int64,
                "crosscheck_ok": pl.Boolean,
                "note": pl.Utf8,
                "checked_at": pl.Utf8,
            }
        )
    return pl.DataFrame(rows).sort("symbol")


def write_verification_table(df: pl.DataFrame, data_dir: Path, *, asset_type: str = "stock") -> Path:
    factor_dir = "adj_factor_etf" if asset_type == "etf" else "adj_factor"
    path = Path(data_dir) / factor_dir / "verification.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_parquet(df, path)
    return path




def apply_crosscheck_to_actions(
    actions: pl.DataFrame,
    crosscheck: dict[str, Any],
) -> pl.DataFrame:
    """Stamp verification_status; quarantine unexplained action/adj mismatches."""
    out = ensure_corporate_actions_v2(actions)
    if out.is_empty():
        return out
    bad = {
        r["symbol"]
        for r in (crosscheck.get("per_symbol") or [])
        if r.get("symbol") and r.get("crosscheck_ok") is False
    }
    good = {
        r["symbol"]
        for r in (crosscheck.get("per_symbol") or [])
        if r.get("symbol") and r.get("crosscheck_ok") is True
    }
    status_expr = (
        pl.when(pl.col("symbol").is_in(sorted(bad)))
        .then(pl.lit("quarantined"))
        .when(pl.col("is_verification_signal").fill_null(False))
        .then(pl.lit(MARKER_UNVERIFIED))
        .when(pl.col("symbol").is_in(sorted(good)) & ~pl.col("is_verification_signal").fill_null(False))
        .then(pl.lit(MARKER_VERIFIED_EVENTS))
        .otherwise(pl.col("verification_status").fill_null(MARKER_UNVERIFIED))
        .alias("verification_status")
    )
    out = out.with_columns(status_expr)
    # plan_status quarantine for mismatched formal facts
    out = out.with_columns(
        pl.when(pl.col("verification_status") == "quarantined")
        .then(pl.lit("quarantined"))
        .otherwise(pl.col("plan_status"))
        .alias("plan_status")
    )
    return out


def _row_date(row: dict[str, Any], key: str) -> date | None:
    raw = row.get(key)
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def _row_float(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_sharebonus_report_rows(
    rows: list[dict[str, Any]],
    *,
    as_of: date | None = None,
    source: str = "eastmoney_sharebonus_det",
) -> pl.DataFrame:
    """东财 RPT_SHAREBONUS_DET 批量行 -> corporate_actions v2 正式事实。

    结构化字段: BONUS_RATIO=每10股送股, IT_RATIO=每10股转增,
    PRETAX_BONUS_RMB=每10股税前派息(元), EQUITY_RECORD_DATE=股权登记日,
    EX_DIVIDEND_DATE=除权除息日, PLAN_NOTICE_DATE=预案公告日。
    无除权除息日的预案行跳过(尚未形成可核对事件)。
    """
    as_of = as_of or date.today()
    seen = _utc_naive()
    out: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        sym = str(row.get("SECUCODE") or "").upper()
        if "." not in sym:
            continue
        ex_raw = row.get("EX_DIVIDEND_DATE")
        if not ex_raw:
            continue
        try:
            ex_d = date.fromisoformat(str(ex_raw)[:10])
        except ValueError:
            continue

        announce_d = _row_date(row, "PLAN_NOTICE_DATE") or _row_date(row, "NOTICE_DATE")
        cash10 = _row_float(row, "PRETAX_BONUS_RMB")
        cash = cash10 / 10.0 if cash10 is not None else None
        total10 = _row_float(row, "BONUS_IT_RATIO")
        if total10 is None:
            bonus10 = _row_float(row, "BONUS_RATIO")
            it10 = _row_float(row, "IT_RATIO")
            if bonus10 is not None or it10 is not None:
                total10 = (bonus10 or 0.0) + (it10 or 0.0)
        stock_ratio = total10 / 10.0 if total10 is not None else None
        if stock_ratio == 0.0:
            stock_ratio = None
        if cash is not None and stock_ratio is not None:
            action_type = "mixed"
        elif cash is not None:
            action_type = "dividend_cash"
        elif stock_ratio is not None:
            action_type = "bonus"
        else:
            action_type = "unknown"
        source_record_id = (
            f"{sym}:{ex_d.isoformat()}:{str(row.get('NOTICE_DATE') or '')[:10]}"
        )
        plan_status = str(row.get("ASSIGN_PROGRESS") or "announced").strip() or "announced"
        aid = _action_id(sym, ex_d, action_type, source + ":" + source_record_id)
        out.append(
            {
                "symbol": sym,
                "action_id": aid,
                "action_type": action_type,
                "announce_date": announce_d,
                "record_date": _row_date(row, "EQUITY_RECORD_DATE"),
                "ex_date": ex_d,
                "pay_date": None,
                "cash_per_share": cash,
                "stock_ratio": stock_ratio,
                "rights_ratio": None,
                "currency": "CNY",
                "source_published_at": seen,
                "first_seen_at": seen,
                "source": source,
                "as_of": as_of,
                "source_record_id": source_record_id,
                "source_url": "https://data.eastmoney.com/yjfp/",
                "plan_status": plan_status,
                "raw_plan_text": str(row.get("IMPL_PLAN_PROFILE") or "") or None,
                "raw_unit": "per_10_shares_report_fields",
                "history_guarantee": "as_collected",
                "verification_status": MARKER_UNVERIFIED,
                "is_verification_signal": False,
                "schema_version": CORPORATE_ACTIONS_SCHEMA_VERSION,
                "unit_version": CORPORATE_ACTIONS_UNIT_VERSION,
            }
        )
    if not out:
        return empty_corporate_actions()
    frame = pl.DataFrame(out, schema=empty_corporate_actions().schema)
    return ensure_corporate_actions_v2(frame.unique(subset=["symbol", "action_id"], keep="last"))


def fetch_sharebonus_events(
    *,
    client: Any | None = None,
    as_of: date | None = None,
    page_size: int = 500,
    max_pages: int | None = None,
    sleep_s: float = 0.2,
    on_progress: Any | None = None,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """全市场分页拉取东财分红送转明细并解析为正式事实。

    分页失败立即停止并如实报告; 已取页不作为完整历史结论。
    """
    import time as _time

    from app.services.free_sources.http_resilience import get_shared_client

    client = client or get_shared_client()
    as_of = as_of or date.today()
    stats: dict[str, Any] = {"pages_fetched": 0, "rows_raw": 0, "ok": True}
    frames: list[pl.DataFrame] = []
    page = 1
    total_pages: int | None = None
    while True:
        url = (
            f"{_SHAREBONUS_ENDPOINT}?reportName=RPT_SHAREBONUS_DET&columns=ALL"
            f"&pageSize={page_size}&pageNumber={page}"
            "&sortColumns=EX_DIVIDEND_DATE&sortTypes=-1"
        )
        res = client.get_json(
            url,
            source_key="eastmoney_sharebonus_det",
            headers=_SHAREBONUS_HEADERS,
            timeout=20.0,
        )
        if not res.ok:
            stats["ok"] = False
            stats["error"] = res.error or f"page {page} failed"
            stats["failed_page"] = page
            break
        payload = res.data if isinstance(res.data, dict) else {}
        result = payload.get("result") or {}
        rows = result.get("data") or []
        if total_pages is None:
            total_pages = int(result.get("pages") or 1)
            stats["report_pages"] = total_pages
            stats["report_count"] = int(result.get("count") or 0)
        if not isinstance(rows, list) or not rows:
            break
        stats["pages_fetched"] += 1
        stats["rows_raw"] += len(rows)
        frame = parse_sharebonus_report_rows(rows, as_of=as_of)
        if not frame.is_empty():
            frames.append(frame)
        if on_progress:
            on_progress(page, total_pages)
        if page >= total_pages or (max_pages is not None and page >= max_pages):
            break
        page += 1
        if sleep_s > 0:
            _time.sleep(sleep_s)
    if not frames:
        return empty_corporate_actions(), stats
    return merge_corporate_actions(*frames), stats

def run_corporate_actions_loop(
    data_dir: Path,
    *,
    asset_type: str = "stock",
    symbols: list[str] | None = None,
    as_of: date | None = None,
    fetch_missing_adj: bool = False,
    fetch_sharebonus: bool = False,
    sharebonus_max_pages: int | None = None,
    publish_actions: bool = True,
    lab_dir: Path | None = None,
    formal_facts_only: bool = False,
) -> dict[str, Any]:
    """Build actions from adj, cross-check, write verification markers.

    If fetch_missing_adj and symbols provided, optionally extends public adj coverage first.
    """
    data_dir = Path(data_dir)
    as_of = as_of or date.today()
    report: dict[str, Any] = {
        "as_of": as_of.isoformat(),
        "asset_type": asset_type,
        "fetch_missing_adj": fetch_missing_adj,
    }

    if fetch_missing_adj and symbols:
        try:
            sync_res = sync_adj_factor_public(
                symbols,
                data_dir,
                asset_type=asset_type,
            )
            report["adj_sync"] = {
                "ok": True,
                "result_keys": list(sync_res.keys()) if isinstance(sync_res, dict) else type(sync_res).__name__,
                "summary": {
                    k: sync_res.get(k)
                    for k in (
                        "symbols_total",
                        "symbols_done",
                        "symbols_failed",
                        "rows_written",
                        "path",
                    )
                    if isinstance(sync_res, dict) and k in sync_res
                },
            }
        except Exception as exc:
            report["adj_sync"] = {"ok": False, "error": str(exc)}

    adj = load_adj_factor_frame(data_dir, asset_type=asset_type)
    coverage = read_adj_coverage(data_dir, asset_type=asset_type)
    derived = corporate_actions_from_adj_events(adj, as_of=as_of)
    report["adj_rows"] = int(adj.height)
    report["adj_symbols"] = int(adj.get_column("symbol").n_unique()) if not adj.is_empty() else 0
    report["derived_signal_rows"] = int(derived.height)

    sourced = empty_corporate_actions()
    if fetch_sharebonus:
        sourced, sb_stats = fetch_sharebonus_events(
            as_of=as_of,
            max_pages=sharebonus_max_pages,
        )
        report["sharebonus"] = sb_stats
        report["sourced_event_rows"] = int(sourced.height)
        if symbols:
            wanted = {str(s).upper() for s in symbols}
            sourced = sourced.filter(pl.col("symbol").is_in(sorted(wanted)))
            report["sourced_event_rows_in_scope"] = int(sourced.height)
    # Formal publish frame: sourced events + optional derived signals (tagged)
    candidate = merge_corporate_actions(sourced, derived)

    # publish corporate_actions into lab_dir or data_dir/reference
    publish_root = Path(lab_dir) if lab_dir is not None else data_dir
    prior_actions_path = publish_root / "reference" / "corporate_actions" / "actions.parquet"
    prior_actions = (
        pl.read_parquet(prior_actions_path) if prior_actions_path.exists() else empty_corporate_actions()
    )
    # Corporate actions are append-only facts. Prior rows keep their exact
    # first-published payload (including verification stamps); only NEW rows get
    # stamped by this run's cross-check. Current per-symbol verification lives in
    # adj_factor/verification.parquet, so frozen prior stamps stay honest without
    # tripping the overlap-conflict admission gate.
    actions = merge_corporate_actions(candidate, prior_actions)
    # Expand universe for verification markers when not provided.
    universe = symbols
    if universe is None:
        if asset_type == "stock":
            inst = data_dir / "instruments"
            files = list(inst.rglob("*.parquet")) if inst.exists() else []
            if files:
                idf = pl.concat([pl.read_parquet(f) for f in files], how="diagonal_relaxed")
                if "symbol" in idf.columns:
                    universe = [str(s) for s in idf.get_column("symbol").unique().to_list()]
        elif asset_type == "etf":
            inst = data_dir / "instruments_etf"
            files = list(inst.rglob("*.parquet")) if inst.exists() else []
            if files:
                idf = pl.concat([pl.read_parquet(f) for f in files], how="diagonal_relaxed")
                if "symbol" in idf.columns:
                    universe = [str(s) for s in idf.get_column("symbol").unique().to_list()]

    # Cross-check uses all actions (including verification signals and prior rows).
    # Formal publish may drop signals when formal_facts_only=True.
    report["action_rows_precheck"] = int(actions.height)
    cross = crosscheck_actions_vs_adj(actions, adj)
    report["crosscheck"] = {
        k: cross.get(k)
        for k in ("symbols", "matched_dates", "only_actions_dates", "only_adj_dates", "agreement_ratio")
    }
    report["crosscheck_sample"] = (cross.get("per_symbol") or [])[:20]
    stamped_new = apply_crosscheck_to_actions(candidate, cross)
    # prior 在后, 共享 action_id 时保留 prior 原行(append-only)
    actions = merge_corporate_actions(stamped_new, prior_actions)
    if formal_facts_only:
        actions = formal_event_facts(actions)
        report["formal_fact_rows"] = int(actions.height)
    report["action_rows"] = int(actions.height)

    verification = build_verification_table(
        coverage=coverage,
        crosscheck=cross,
        universe=universe,
    )
    ver_path = write_verification_table(verification, data_dir, asset_type=asset_type)
    report["verification_path"] = str(ver_path)
    if not verification.is_empty():
        report["verification_counts"] = {
            str(k): int(v)
            for k, v in verification.group_by("verification").len().iter_rows()
        }
    else:
        report["verification_counts"] = {}

    if publish_actions and not actions.is_empty():
        if lab_dir is not None:
            lab_dir = Path(lab_dir)
            lab_dir.mkdir(parents=True, exist_ok=True)
            (lab_dir / "LAB_ISOLATION.md").write_text(
                "# Corporate actions lab sink\n", encoding="utf-8"
            )
            pub = publish_dataset(
                PublishRequest(
                    dataset_id="corporate_actions",
                    data_dir=lab_dir,
                    frame=actions,
                    source="corporate_actions_v2",
                    run_id=f"corp-act-{as_of.isoformat()}",
                    as_of=as_of,
                    cleanup_staging_on_success=False,
                )
            )
            report["publish"] = pub.as_dict()
        else:
            pub = publish_dataset(
                PublishRequest(
                    dataset_id="corporate_actions",
                    data_dir=data_dir,
                    frame=actions,
                    source="corporate_actions_v2",
                    run_id=f"corp-act-{as_of.isoformat()}",
                    as_of=as_of,
                    cleanup_staging_on_success=True,
                )
            )
            report["publish"] = pub.as_dict()
    else:
        report["publish"] = {"ok": True, "skipped": True, "row_count": int(actions.height)}

    report["unit_version"] = CORPORATE_ACTIONS_UNIT_VERSION
    report["schema_version"] = CORPORATE_ACTIONS_SCHEMA_VERSION
    report["rules"] = {
        "never_treat_fetch_failed_as_no_event": True,
        "never_treat_empty_network_as_no_event": True,
        "adj_factor_derived_is_verification_signal": True,
        "markers": [
            MARKER_VERIFIED_EVENTS,
            MARKER_VERIFIED_NO_EVENT,
            MARKER_SOURCE_FAILED,
            MARKER_UNVERIFIED,
        ],
    }
    return report
