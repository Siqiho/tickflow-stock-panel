"""Isolated M5 reference Source Lab runner.

Always writes under an explicit lab_dir. Never defaults to production data/.
When source_data_dir is provided it is read-only for instruments/kline shadows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl

from app.data_lab.fixtures import make_trading_calendar_frame
from app.data_lab.publish_protocol import PublishRequest, publish_dataset
from app.data_lab.sources.calendar_probe import (
    build_trading_calendar_from_szse,
    calendar_probe_meta,
    fetch_szse_calendar_range,
    month_range,
)
from app.data_lab.sources.shadow_coverage import (
    build_listing_events_from_instruments,
    build_status_history_shadow,
    compare_calendar_to_kline_partitions,
    summarize_listing_coverage,
    summarize_status_shadow,
)
from app.services.atomic_io import atomic_write_json


@dataclass(frozen=True)
class LabRunConfig:
    lab_dir: Path
    source_data_dir: Path | None = None
    calendar_start: date = date(2026, 6, 1)
    calendar_end: date = date(2026, 7, 21)
    as_of: date | None = None
    fetch_public_calendar: bool = True
    status_sample_days: int = 8
    status_max_symbols: int | None = 500
    http_timeout: float = 10.0


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(payload, path, indent=2)


def run_reference_source_lab(config: LabRunConfig) -> dict[str, Any]:
    lab_dir = Path(config.lab_dir)
    if lab_dir.exists():
        # refuse to reuse non-empty non-lab marker blindly
        marker = lab_dir / "LAB_ISOLATION.md"
        if any(lab_dir.iterdir()) and not marker.exists():
            raise RuntimeError(
                f"refusing to use non-empty non-lab directory as lab_dir: {lab_dir}"
            )
    lab_dir.mkdir(parents=True, exist_ok=True)
    marker = lab_dir / "LAB_ISOLATION.md"
    marker.write_text(
        "# Isolated M5 Source Lab\n\n"
        "Not production data/.\n\n"
        f"- created_at: {datetime.now().astimezone().isoformat()}\n"
        f"- source_data_dir_readonly: {config.source_data_dir}\n",
        encoding="utf-8",
    )
    (lab_dir / "README.md").write_text(
        "# M5 Reference Source Lab (isolated)\n\n"
        "This directory is an isolated DATA_DIR for Lab only.\n"
        "Do not point production services here without explicit approval.\n",
        encoding="utf-8",
    )

    as_of = config.as_of or date.today()
    report: dict[str, Any] = {
        "ok": True,
        "as_of": as_of.isoformat(),
        "lab_dir": str(lab_dir),
        "source_data_dir": str(config.source_data_dir) if config.source_data_dir else None,
        "started_at": datetime.now().astimezone().isoformat(),
        "datasets": {},
        "admission": {},
    }

    # ---- trading_calendar ----
    cal_section: dict[str, Any] = {"producer_attempted": config.fetch_public_calendar}
    try:
        if config.fetch_public_calendar:
            raw = fetch_szse_calendar_range(
                config.calendar_start,
                config.calendar_end,
                timeout=config.http_timeout,
            )
            months = month_range(config.calendar_start, config.calendar_end)
            open_days = len({r["trade_date"] for r in raw if str(r.get("is_open_flag")) == "1"})
            cal_meta = calendar_probe_meta(
                months=months,
                row_count=len({r["trade_date"] for r in raw}),
                open_days=open_days,
            )
            frame = build_trading_calendar_from_szse(raw, as_of=as_of)
            cal_section["meta"] = cal_meta
            cal_section["source"] = "szse_month_list"
        else:
            frame = make_trading_calendar_frame(
                start=config.calendar_start,
                days=(config.calendar_end - config.calendar_start).days + 1,
                as_of=as_of,
            )
            cal_section["source"] = "lab_fixture"
            cal_section["meta"] = {"producer": "lab_fixture"}

        # optional raw archive inside lab only
        raw_path = lab_dir / "lab_raw" / "trading_calendar" / "normalized_preview.parquet"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        frame.write_parquet(raw_path)

        pub = publish_dataset(
            PublishRequest(
                dataset_id="trading_calendar",
                data_dir=lab_dir,
                frame=frame,
                source=str(cal_section.get("source") or "unknown"),
                run_id=f"lab-cal-{as_of.isoformat()}",
                as_of=as_of,
                cleanup_staging_on_success=False,
            )
        )
        cal_section["publish"] = pub.as_dict()

        # shadow compare vs local kline partitions if available
        if config.source_data_dir is not None:
            kline_root = Path(config.source_data_dir) / "kline_daily"
            cal_section["kline_shadow"] = compare_calendar_to_kline_partitions(
                frame, kline_root, exchange="SH"
            )
            # fixture-style weekend sanity: no open on pure weekends from SZSE should hold
            weekend_open = frame.filter(
                pl.col("is_open") & (pl.col("trade_date").dt.weekday() >= 6)
            )
            # polars weekday: Monday=1 ... Sunday=7
            cal_section["weekend_open_rows"] = weekend_open.height

            # compare fixture month against public for structural equality on is_open if both
            fixture = make_trading_calendar_frame(
                start=config.calendar_start,
                days=min(14, (config.calendar_end - config.calendar_start).days + 1),
                as_of=as_of,
                exchanges=("SH",),
            )
            pub_slice = frame.filter(
                (pl.col("exchange") == "SH")
                & (pl.col("trade_date") >= fixture.get_column("trade_date").min())
                & (pl.col("trade_date") <= fixture.get_column("trade_date").max())
            ).select(["trade_date", "is_open"]).sort("trade_date")
            fix_slice = fixture.select(["trade_date", "is_open"]).sort("trade_date")
            joined = pub_slice.join(fix_slice, on="trade_date", how="inner", suffix="_fix")
            disagree = joined.filter(pl.col("is_open") != pl.col("is_open_fix")) if joined.height else joined
            cal_section["fixture_vs_public"] = {
                "overlap_days": joined.height,
                "is_open_disagreements": disagree.height if joined.height else 0,
                "disagreement_dates": [
                    str(x) for x in (
                        disagree.get_column("trade_date").to_list() if disagree.height else []
                    )[:20]
                ],
                "note": (
                    "lab_fixture uses weekend-only closes; public includes holidays — "
                    "disagreements on weekday holidays are expected and good"
                ),
            }
        report["datasets"]["trading_calendar"] = cal_section
        report["admission"]["trading_calendar"] = {
            "status": "LAB_PASS_CANDIDATE" if pub.ok else "LAB_FAIL",
            "reason": (
                "public SZSE month list normalized and published into isolated lab_dir"
                if pub.ok and cal_section.get("source") == "szse_month_list"
                else pub.error or "fixture_only"
            ),
            "blockers_for_production": [
                "confirm exchange ToS / redistribution rights",
                "verify SH/BJ identity vs SZSE calendar on special sessions",
                "extend history depth beyond current lab window",
                "optional second-source cross-check (SSE official) still missing",
            ],
        }
        if not pub.ok:
            report["ok"] = False
    except Exception as exc:
        report["ok"] = False
        report["datasets"]["trading_calendar"] = {
            **cal_section,
            "error": str(exc),
        }
        report["admission"]["trading_calendar"] = {
            "status": "LAB_FAIL",
            "reason": str(exc),
        }

    # ---- listing_delisting_events shadow ----
    list_section: dict[str, Any] = {"mode": "shadow_from_instruments"}
    try:
        if config.source_data_dir is None:
            raise RuntimeError("source_data_dir required for listing shadow")
        inst_path = Path(config.source_data_dir) / "instruments" / "instruments.parquet"
        if not inst_path.exists():
            raise FileNotFoundError(f"missing instruments snapshot: {inst_path}")
        events = build_listing_events_from_instruments(inst_path, as_of=as_of)
        summary = summarize_listing_coverage(inst_path, events)
        list_section["coverage"] = summary
        pub = publish_dataset(
            PublishRequest(
                dataset_id="listing_delisting_events",
                data_dir=lab_dir,
                frame=events,
                source="local_instruments_snapshot_shadow",
                run_id=f"lab-list-{as_of.isoformat()}",
                as_of=as_of,
                cleanup_staging_on_success=False,
            )
        )
        list_section["publish"] = pub.as_dict()
        report["datasets"]["listing_delisting_events"] = list_section
        report["admission"]["listing_delisting_events"] = {
            "status": "LAB_SHADOW_ONLY",
            "reason": "seeded from current instruments snapshot; no delist history",
            "blockers_for_production": summary.get("gaps", []),
        }
        if not pub.ok:
            report["ok"] = False
    except Exception as exc:
        report["ok"] = False
        list_section["error"] = str(exc)
        report["datasets"]["listing_delisting_events"] = list_section
        report["admission"]["listing_delisting_events"] = {
            "status": "LAB_FAIL",
            "reason": str(exc),
        }

    # ---- instrument_status_history shadow ----
    status_section: dict[str, Any] = {"mode": "shadow_from_kline_halt_heuristic"}
    try:
        if config.source_data_dir is None:
            raise RuntimeError("source_data_dir required for status shadow")
        kline_root = Path(config.source_data_dir) / "kline_daily"
        inst_path = Path(config.source_data_dir) / "instruments" / "instruments.parquet"
        status = build_status_history_shadow(
            kline_root,
            sample_days=config.status_sample_days,
            as_of=as_of,
            max_symbols=config.status_max_symbols,
            instruments_path=inst_path if inst_path.exists() else None,
        )
        status_section["coverage"] = summarize_status_shadow(
            status, sample_days=config.status_sample_days, kline_root=kline_root
        )
        if status.height == 0:
            # still record empty refusal via publish protocol
            pub = publish_dataset(
                PublishRequest(
                    dataset_id="instrument_status_history",
                    data_dir=lab_dir,
                    frame=status,
                    source="local_kline_halt_heuristic_shadow",
                    run_id=f"lab-status-{as_of.isoformat()}",
                    as_of=as_of,
                    cleanup_staging_on_success=False,
                )
            )
            status_section["publish"] = pub.as_dict()
            report["admission"]["instrument_status_history"] = {
                "status": "LAB_SHADOW_EMPTY",
                "reason": "no halt-heuristic rows in sampled partitions",
                "blockers_for_production": status_section["coverage"].get("gaps", []),
            }
        else:
            pub = publish_dataset(
                PublishRequest(
                    dataset_id="instrument_status_history",
                    data_dir=lab_dir,
                    frame=status,
                    source="local_kline_halt_heuristic_shadow",
                    run_id=f"lab-status-{as_of.isoformat()}",
                    as_of=as_of,
                    cleanup_staging_on_success=False,
                )
            )
            status_section["publish"] = pub.as_dict()
            report["admission"]["instrument_status_history"] = {
                "status": "LAB_SHADOW_ONLY",
                "reason": "bar heuristic intervals only; not an exchange status feed",
                "blockers_for_production": status_section["coverage"].get("gaps", []),
            }
            if not pub.ok:
                report["ok"] = False
        report["datasets"]["instrument_status_history"] = status_section
    except Exception as exc:
        report["ok"] = False
        status_section["error"] = str(exc)
        report["datasets"]["instrument_status_history"] = status_section
        report["admission"]["instrument_status_history"] = {
            "status": "LAB_FAIL",
            "reason": str(exc),
        }

    report["finished_at"] = datetime.now().astimezone().isoformat()
    # overall production admission remains no-go
    report["production_publish"] = {
        "status": "NO_GO",
        "reason": (
            "Only trading_calendar has a public producer candidate; "
            "listing/status remain shadow-only; rights and second-source checks open"
        ),
    }
    out_path = lab_dir / "lab_reports" / "reference_source_lab_report.json"
    _write_json(out_path, report)
    report["report_path"] = str(out_path)
    return report
