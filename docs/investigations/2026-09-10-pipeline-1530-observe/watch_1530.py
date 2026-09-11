#!/usr/bin/env python3
"""Watch the official 15:30 daily_pipeline fire. Do not trigger it."""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl

SH = ZoneInfo("Asia/Shanghai")
ROOT = Path("/Users/simon/Trading/one-trading")
JOB_DIR = ROOT / "data" / "job_store"
EVID = Path(__file__).resolve().parent / "evidence"
DATA_DIR = ROOT / "data"
TARGET = datetime(2026, 9, 10, 15, 30, 0, tzinfo=SH)
ONTIME_END = datetime(2026, 9, 10, 15, 30, 30, tzinfo=SH)
GIVE_UP_START = datetime(2026, 9, 10, 15, 35, 0, tzinfo=SH)
GIVE_UP_FINISH = datetime(2026, 9, 10, 16, 15, 0, tzinfo=SH)
KNOWN = {"f0125e68cf"}


def now() -> datetime:
    return datetime.now(SH)


def load_jobs() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in JOB_DIR.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if payload.get("_work_key") != "owner|daily_pipeline|daily_pipeline":
            continue
        out[path.stem] = payload
    return out


def h5_max(kind_daily: str) -> dict:
    root = DATA_DIR / "ext_data" / kind_daily / "timeseries"
    frames = [pl.read_parquet(p) for p in sorted(root.rglob("*.parquet"))]
    df = pl.concat(frames, how="diagonal_relaxed")
    h = df.filter(pl.col("source") == "eastmoney_fflow_day")
    mx = h.select(pl.col("date").cast(pl.Utf8).max()).item()
    latest = h.filter(pl.col("date").cast(pl.Utf8) == mx)
    return {
        "h5_max_date": mx,
        "latest_rows": latest.height,
        "latest_codes": latest.select(pl.col("code")).n_unique(),
    }


def classify_start(started_at: str | None) -> str:
    if not started_at:
        return "missing_started_at"
    ts = datetime.fromisoformat(started_at.replace("Z", "+00:00")).astimezone(SH)
    if TARGET <= ts <= ONTIME_END:
        return "on_time"
    if datetime(2026, 9, 10, 15, 30, 31, tzinfo=SH) <= ts <= datetime(2026, 9, 10, 16, 30, 0, tzinfo=SH):
        return "misfire"
    return "other"


def wait_until(dt: datetime) -> None:
    while now() < dt:
        remaining = (dt - now()).total_seconds()
        time.sleep(min(15.0, max(0.5, remaining)))


def main() -> None:
    EVID.mkdir(parents=True, exist_ok=True)
    print(f"watch start {now().isoformat()} next_target={TARGET.isoformat()}", flush=True)
    wait_until(datetime(2026, 9, 10, 15, 29, 0, tzinfo=SH))
    before = load_jobs()
    known = set(before) | KNOWN
    (EVID / "watch-start.json").write_text(
        json.dumps(
            {
                "captured_at": now().isoformat(),
                "known_jobs": sorted(known),
                "known_count": len(known),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    found_id = None
    found = None
    while now() < GIVE_UP_START:
        jobs = load_jobs()
        new_ids = [jid for jid in jobs if jid not in known]
        if new_ids:
            new_ids.sort(key=lambda jid: jobs[jid].get("started_at") or "")
            found_id = new_ids[-1]
            found = jobs[found_id]
            break
        time.sleep(3)
    if found is None:
        result = {
            "observed": False,
            "reason": "no_new_daily_pipeline_job_by_15:35",
            "captured_at": now().isoformat(),
        }
        (EVID / "today-observe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return
    while found.get("finished_at") is None and now() < GIVE_UP_FINISH:
        time.sleep(5)
        jobs = load_jobs()
        found = jobs.get(found_id) or found
    industry = (found.get("result") or {}).get("industry_fund_flow_daily")
    concept = (found.get("result") or {}).get("concept_fund_flow_daily")
    start_class = classify_start(found.get("started_at"))
    result = {
        "observed": bool(
            start_class == "on_time"
            and found.get("finished_at")
            and industry is not None
            and concept is not None
        ),
        "start_class": start_class,
        "job_id": found_id,
        "work_key": found.get("_work_key"),
        "started_at": found.get("started_at"),
        "finished_at": found.get("finished_at"),
        "status": found.get("status"),
        "duration_s": found.get("duration_s"),
        "industry_fund_flow_daily": {
            "ok": None if industry is None else industry.get("ok"),
            "status": None if industry is None else industry.get("status"),
            "latest_data_date": None if industry is None else industry.get("latest_data_date"),
            "latest_day_covered": None if industry is None else industry.get("latest_day_covered"),
            "latest_day_complete": None if industry is None else industry.get("latest_day_complete"),
        },
        "concept_fund_flow_daily": None
        if concept is None
        else {
            "ok": concept.get("ok"),
            "status": concept.get("status"),
            "latest_data_date": concept.get("latest_data_date"),
            "latest_day_covered": concept.get("latest_day_covered"),
            "latest_day_complete": concept.get("latest_day_complete"),
        },
        "parquet_after": {
            "industry": h5_max("ext_fund_flow_bk_daily"),
            "concept": h5_max("ext_fund_flow_concept_daily"),
        },
        "captured_at": now().isoformat(),
    }
    (EVID / "today-observe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
