"""Cross-check trading calendars across producers (Lab only)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl

from app.data_lab.publish_protocol import PublishRequest, publish_dataset
from app.data_lab.sources.calendar_probe import (
    CalendarProbeError,
    build_trading_calendar_from_szse,
    fetch_szse_calendar_range,
    month_range,
)
from app.data_lab.sources.tencent_calendar_probe import (
    fetch_tencent_open_days,
    tencent_probe_meta,
)
from app.services.atomic_io import atomic_write_json


@dataclass(frozen=True)
class CalendarCrosscheckConfig:
    lab_dir: Path
    start: date
    end: date
    as_of: date | None = None
    szse_timeout: float = 10.0
    tencent_timeout: float = 10.0
    tencent_code_sh: str = "sh000001"
    tencent_code_sz: str = "sz399001"
    retries: int = 2
    # Optional cached SZSE frame (e.g. prior isolated lab parquet) if live SZSE is down.
    szse_cache_parquet: Path | None = None
    fetch_live_szse: bool = True
    fetch_tencent: bool = True


def _empty_report_base(cfg: CalendarCrosscheckConfig) -> dict[str, Any]:
    return {
        "kind": "trading_calendar_second_source_crosscheck",
        "started_at": datetime.now().astimezone().isoformat(),
        "window": [cfg.start.isoformat(), cfg.end.isoformat()],
        "lab_dir": str(cfg.lab_dir),
        "sources": {},
        "comparisons": {},
        "network": {},
        "admission": {},
        "ok": False,
    }


def _open_days_from_calendar(frame: pl.DataFrame, exchange: str = "SH") -> set[date]:
    if frame.is_empty():
        return set()
    sub = frame.filter((pl.col("exchange") == exchange) & pl.col("is_open"))
    return set(sub.get_column("trade_date").to_list())


def _compare_open_sets(
    left_name: str,
    left: set[date],
    right_name: str,
    right: set[date],
    *,
    span: tuple[date, date] | None = None,
) -> dict[str, Any]:
    if span is not None:
        lo, hi = span
        left = {d for d in left if lo <= d <= hi}
        right = {d for d in right if lo <= d <= hi}
    only_left = sorted(left - right)
    only_right = sorted(right - left)
    both = sorted(left & right)
    return {
        "left": left_name,
        "right": right_name,
        "span": [span[0].isoformat(), span[1].isoformat()] if span else None,
        "left_count": len(left),
        "right_count": len(right),
        "intersection": len(both),
        "only_left_count": len(only_left),
        "only_right_count": len(only_right),
        "only_left": [d.isoformat() for d in only_left[:30]],
        "only_right": [d.isoformat() for d in only_right[:30]],
        "equal": only_left == [] and only_right == [] and len(left) > 0 and len(right) > 0,
    }


def _load_szse_cache(path: Path, start: date, end: date) -> pl.DataFrame:
    df = pl.read_parquet(path)
    need = {"exchange", "trade_date", "is_open"}
    if not need.issubset(df.columns):
        raise ValueError(f"cache missing columns: {sorted(need - set(df.columns))}")
    out = df.filter((pl.col("trade_date") >= start) & (pl.col("trade_date") <= end))
    return out


def _fetch_szse_with_retries(
    start: date,
    end: date,
    *,
    timeout: float,
    retries: int,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    last_err: str | None = None
    for attempt in range(max(1, retries + 1)):
        try:
            raw = fetch_szse_calendar_range(start, end, timeout=timeout)
            frame = build_trading_calendar_from_szse(raw, as_of=end)
            meta = {
                "producer": "szse_month_list",
                "mode": "live",
                "attempt": attempt,
                "months": month_range(start, end),
                "raw_days": len({r["trade_date"] for r in raw}),
                "open_days": len({r["trade_date"] for r in raw if str(r.get("is_open_flag")) == "1"}),
            }
            return frame, meta
        except Exception as exc:  # network variability
            last_err = str(exc)
    raise CalendarProbeError(last_err or "SZSE fetch failed")


def run_calendar_second_source_crosscheck(cfg: CalendarCrosscheckConfig) -> dict[str, Any]:
    """Run SZSE (live or cache) vs Tencent SH/SZ open-day cross-check in lab_dir."""
    lab_dir = Path(cfg.lab_dir)
    lab_dir.mkdir(parents=True, exist_ok=True)
    marker = lab_dir / "LAB_ISOLATION.md"
    if (
        any(lab_dir.iterdir())
        and not marker.exists()
        and not (lab_dir / "lab_reports").exists()
        and not (lab_dir / "reference").exists()
    ):
        raise RuntimeError(f"refusing non-lab non-empty directory: {lab_dir}")
    if not marker.exists():
        marker.write_text(
            "# Isolated calendar second-source Lab\n\nNot production data/.\n",
            encoding="utf-8",
        )

    as_of = cfg.as_of or date.today()
    report = _empty_report_base(cfg)
    report["as_of"] = as_of.isoformat()

    szse_frame: pl.DataFrame | None = None
    # 1) SZSE live
    if cfg.fetch_live_szse:
        try:
            szse_frame, meta = _fetch_szse_with_retries(
                cfg.start, cfg.end, timeout=cfg.szse_timeout, retries=cfg.retries
            )
            report["sources"]["szse"] = meta
            report["network"]["szse_live"] = "ok"
        except Exception as exc:
            report["network"]["szse_live"] = f"error: {exc}"
            report["sources"]["szse_live_error"] = str(exc)

    # 2) SZSE cache fallback
    if szse_frame is None and cfg.szse_cache_parquet is not None:
        try:
            szse_frame = _load_szse_cache(Path(cfg.szse_cache_parquet), cfg.start, cfg.end)
            report["sources"]["szse"] = {
                "producer": "szse_month_list",
                "mode": "cache_parquet",
                "path": str(cfg.szse_cache_parquet),
                "rows": szse_frame.height,
            }
            report["network"]["szse_cache"] = "ok"
        except Exception as exc:
            report["network"]["szse_cache"] = f"error: {exc}"
            report["sources"]["szse_cache_error"] = str(exc)

    if szse_frame is not None and szse_frame.height:
        # publish into this lab_dir for lineage/artifacts
        src_name = str(report.get("sources", {}).get("szse", {}).get("producer", "szse_month_list"))
        pub = publish_dataset(
            PublishRequest(
                dataset_id="trading_calendar",
                data_dir=lab_dir,
                frame=szse_frame,
                source=src_name,
                run_id=f"xcheck-szse-{as_of.isoformat()}",
                as_of=as_of,
                cleanup_staging_on_success=False,
            )
        )
        report["sources"]["szse_publish"] = pub.as_dict()
        # if cache lacks full schema fields, rebuild via open days only is not done here

    # 3) Tencent SH/SZ
    tx_sh: set[date] = set()
    tx_sz: set[date] = set()
    if cfg.fetch_tencent:
        try:
            days = fetch_tencent_open_days(
                code=cfg.tencent_code_sh,
                start=cfg.start,
                end=cfg.end,
                timeout=cfg.tencent_timeout,
                retries=cfg.retries,
            )
            tx_sh = set(days)
            report["sources"]["tencent_sh"] = tencent_probe_meta(
                code=cfg.tencent_code_sh, start=cfg.start, end=cfg.end, open_days=days
            )
            report["network"]["tencent_sh"] = "ok"
        except Exception as exc:
            report["network"]["tencent_sh"] = f"error: {exc}"
            report["sources"]["tencent_sh_error"] = str(exc)
        try:
            days = fetch_tencent_open_days(
                code=cfg.tencent_code_sz,
                start=cfg.start,
                end=cfg.end,
                timeout=cfg.tencent_timeout,
                retries=cfg.retries,
            )
            tx_sz = set(days)
            report["sources"]["tencent_sz"] = tencent_probe_meta(
                code=cfg.tencent_code_sz, start=cfg.start, end=cfg.end, open_days=days
            )
            report["network"]["tencent_sz"] = "ok"
        except Exception as exc:
            report["network"]["tencent_sz"] = f"error: {exc}"
            report["sources"]["tencent_sz_error"] = str(exc)

    # 4) Comparisons
    if tx_sh and tx_sz:
        report["comparisons"]["tencent_sh_vs_tencent_sz"] = _compare_open_sets(
            "tencent_sh", tx_sh, "tencent_sz", tx_sz, span=(cfg.start, cfg.end)
        )
    if szse_frame is not None and szse_frame.height and tx_sh:
        szse_open = _open_days_from_calendar(szse_frame, "SH")
        # intersect with available span of both
        if szse_open and tx_sh:
            lo = max(min(szse_open), min(tx_sh), cfg.start)
            hi = min(max(szse_open), max(tx_sh), cfg.end)
            report["comparisons"]["szse_sh_vs_tencent_sh"] = _compare_open_sets(
                "szse_sh_open", szse_open, "tencent_sh", tx_sh, span=(lo, hi)
            )
        # weekend open sanity on szse
        if "trade_date" in szse_frame.columns:
            weekend_open = szse_frame.filter(
                pl.col("is_open") & (pl.col("trade_date").dt.weekday() >= 6)
            )
            report["comparisons"]["szse_weekend_open_rows"] = weekend_open.height

    # 5) Official SSE API status (explicit absence)
    report["sources"]["sse_official_api"] = {
        "status": "unavailable_in_this_environment",
        "attempts": [
            "https://query.sse.com.cn/commonSoaQuery.do?sqlId=COMMON_SSE_ZQPZ_GLRLB",
            "https://www.sse.com.cn/services/tradingservice/calendar/",
        ],
        "note": (
            "No stable official SSE machine-readable calendar endpoint succeeded "
            "in Lab probes (404 / SOA null / SSL failures). Secondary check uses "
            "Tencent SH composite open days as a proxy, clearly labeled."
        ),
    }

    # 6) Admission judgment for trading_calendar only
    cmp_main = report["comparisons"].get("szse_sh_vs_tencent_sh") or {}
    tx_equal = (report["comparisons"].get("tencent_sh_vs_tencent_sz") or {}).get("equal")
    equal = bool(cmp_main.get("equal"))
    has_szse = szse_frame is not None and szse_frame.height > 0
    has_tx = bool(tx_sh)

    if has_szse and has_tx and equal and tx_equal is not False:
        status = "LAB_PASS_CANDIDATE_SECOND_SOURCE_OK"
        discuss_publish = "DISCUSS_ONLY"
        reason = (
            "SZSE calendar open days match Tencent SH open-day series on the compared span; "
            "Tencent SH/SZ series also match. Official SSE API still unavailable; "
            "production publish remains gated on rights + operator approval."
        )
        report["ok"] = True
    elif has_tx and not has_szse:
        status = "LAB_PARTIAL_TENCENT_ONLY"
        discuss_publish = "NO"
        reason = (
            "Tencent secondary series reachable, but SZSE primary live/cache unavailable "
            "for this run; cannot complete dual-source admission."
        )
        report["ok"] = False
    elif has_szse and not has_tx:
        status = "LAB_PARTIAL_SZSE_ONLY"
        discuss_publish = "NO"
        reason = "SZSE available but Tencent secondary failed; second-source gate not met."
        report["ok"] = False
    elif has_szse and has_tx and not equal:
        status = "LAB_FAIL_MISMATCH"
        discuss_publish = "NO"
        reason = "SZSE vs Tencent open-day mismatch on compared span."
        report["ok"] = False
    else:
        status = "LAB_FAIL_NO_SOURCE"
        discuss_publish = "NO"
        reason = "Neither SZSE nor Tencent produced usable open-day sets."
        report["ok"] = False

    report["admission"]["trading_calendar"] = {
        "status": status,
        "discuss_standalone_production_publish": discuss_publish,
        "reason": reason,
        "blockers_for_production": [
            "exchange_data_redistribution_rights_not_formally_signed_off",
            "official_sse_machine_readable_calendar_still_missing",
            "bj_special_session_identity_not_independently_proven",
            "operator_explicit_approval_required_before_writing_production_data",
            *(
                []
                if report["sources"].get("szse", {}).get("mode") != "cache_parquet"
                else ["this_run_used_szse_cache_because_live_endpoint_failed"]
            ),
        ],
    }
    report["production_publish"] = {
        "status": "NO_GO",
        "dataset": "trading_calendar",
        "may_discuss_standalone_publish": discuss_publish == "DISCUSS_ONLY",
        "reason": (
            "Even with second-source agreement, formal production write is blocked until "
            "rights sign-off and explicit user approval. Listing/status datasets remain out of scope."
        ),
    }
    report["finished_at"] = datetime.now().astimezone().isoformat()

    out = lab_dir / "lab_reports" / "calendar_second_source_crosscheck.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(report, out, indent=2)
    report["report_path"] = str(out)
    return report
