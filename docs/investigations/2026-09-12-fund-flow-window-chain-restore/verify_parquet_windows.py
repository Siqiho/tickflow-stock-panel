#!/usr/bin/env python3
"""Read-only formal Parquet window verifier.

Independently reads official industry/concept daily Parquet, selects the same
latest eastmoney_fflow_day trading dates, sums each code exactly, and compares
coverage plus every aggregate_board_window (API-service) row/value.

Does not import or call the service function to produce the independent side.
No float tolerance. Exit 1 on any mismatch. Formal data is read-only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import polars as pl

BACKEND = Path("/Users/simon/Trading/one-trading/backend")
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.free_sources.fund_flow import aggregate_board_window  # noqa: E402

DATA_DIR = Path("/Users/simon/Trading/one-trading/data")
WINDOWS = (
    ("industry_5", "board", 5),
    ("industry_63", "board", 63),
    ("industry_126", "board", 126),
    ("concept_5", "concept", 5),
    ("concept_63", "concept", 63),
)
TOP = 8


def _as_iso(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:10] if len(text) >= 10 else None


def _read_snapshot(kind: str) -> list[dict]:
    config_id = "ext_fund_flow_bk" if kind == "board" else "ext_fund_flow_concept"
    path = DATA_DIR / "ext_data" / config_id / "part.parquet"
    if not path.exists():
        return []
    return pl.read_parquet(path).to_dicts()


def _read_daily(kind: str) -> pl.DataFrame:
    config_id = "ext_fund_flow_bk_daily" if kind == "board" else "ext_fund_flow_concept_daily"
    root = DATA_DIR / "ext_data" / config_id / "timeseries"
    if not root.exists():
        return pl.DataFrame()
    frames: list[pl.DataFrame] = []
    for path in sorted(root.rglob("*.parquet")):
        try:
            frames.append(pl.read_parquet(path))
        except Exception:
            continue
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")


def _exact_sum(values: list[float]) -> float:
    total = 0.0
    for value in values:
        total = total + float(value)
    return total


def _rank_items(items: list[dict], top: int) -> list[dict]:
    if not items:
        return []
    n = max(1, int(top))

    def _net(row: dict) -> float:
        value = row.get("main_net")
        return float(value) if isinstance(value, (int, float)) else 0.0

    ranked = [row for row in items if str(row.get("code") or "").strip()]
    high = sorted(ranked, key=_net, reverse=True)[:n]
    high_codes = {str(row.get("code") or "").upper() for row in high}
    low = [
        row
        for row in sorted(ranked, key=_net)
        if str(row.get("code") or "").upper() not in high_codes
    ][:n]
    seen: set[str] = set()
    out: list[dict] = []
    for row in high + low:
        code = str(row.get("code") or "").upper()
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(row)
    return out


def independent_window(kind: str, days: int, top: int = TOP) -> dict:
    snapshot_items = _read_snapshot(kind)
    daily = _read_daily(kind)
    snapshot_codes = [
        str(row.get("code") or "").upper()
        for row in snapshot_items
        if str(row.get("code") or "").strip()
    ]
    if daily.is_empty() or "date" not in daily.columns or "code" not in daily.columns:
        return {
            "kind": kind,
            "requested_days": int(days),
            "window_days": 0,
            "start": None,
            "end": None,
            "snapshot_count": len(snapshot_items),
            "covered_count": 0,
            "full_count": 0,
            "missing_count": len(snapshot_codes),
            "window_complete": False,
            "items": [],
        }
    daily = daily.with_columns(
        pl.col("code").cast(pl.Utf8).str.to_uppercase().alias("code"),
        pl.col("date").cast(pl.Utf8).str.slice(0, 10).alias("date"),
    )
    if "source" in daily.columns:
        daily = daily.filter(pl.col("source") == "eastmoney_fflow_day")
    dates = sorted({str(v) for v in daily["date"].to_list() if v})
    window_dates = dates[-max(1, int(days)) :]
    window = daily.filter(pl.col("date").is_in(window_dates))
    names: dict[str, object] = {}
    if "name" in daily.columns:
        for row in daily.select(["code", "name"]).unique(subset=["code"], keep="last").to_dicts():
            names[str(row.get("code") or "").upper()] = row.get("name")
    for row in snapshot_items:
        code = str(row.get("code") or "").upper()
        if code and code not in names:
            names[code] = row.get("name")

    by_code: dict[str, list[tuple[str, float]]] = {}
    for row in window.to_dicts():
        code = str(row.get("code") or "").upper()
        day = _as_iso(row.get("date"))
        if not code or not day:
            continue
        value = row.get("main_net")
        if not isinstance(value, (int, float)):
            continue
        by_code.setdefault(code, []).append((day, float(value)))

    items: list[dict] = []
    for code, pairs in by_code.items():
        pairs.sort(key=lambda item: item[0])
        unique_days = sorted({day for day, _ in pairs})
        items.append(
            {
                "code": code,
                "name": names.get(code) or code,
                "main_net": _exact_sum([net for _, net in pairs]),
                "days": len(unique_days),
                "window_days": len(window_dates),
            }
        )
    days_by_code = {str(item["code"]): int(item["days"]) for item in items}
    covered_codes = set(days_by_code)
    missing = [code for code in snapshot_codes if code not in covered_codes]
    full_count = sum(1 for code in snapshot_codes if days_by_code.get(code, 0) >= int(days))
    if kind == "concept":
        ranked_source = [item for item in items if int(item["days"]) >= int(days)]
        window_complete = (
            len(window_dates) >= int(days)
            and full_count >= max(20, int(0.9 * len(snapshot_codes)))
            and full_count == len(ranked_source)
        )
    else:
        ranked_source = items
        window_complete = len(window_dates) >= int(days) and full_count == len(snapshot_codes)
    ranked_source.sort(
        key=lambda row: (
            row.get("main_net") is None,
            -(row["main_net"] if isinstance(row.get("main_net"), (int, float)) else 0.0),
        )
    )
    return {
        "kind": kind,
        "requested_days": int(days),
        "window_days": len(window_dates),
        "start": window_dates[0] if window_dates else None,
        "end": window_dates[-1] if window_dates else None,
        "snapshot_count": len(snapshot_items),
        "covered_count": len(covered_codes),
        "full_count": full_count,
        "missing_count": len(missing),
        "window_complete": window_complete,
        "items": _rank_items(ranked_source, top),
        "sums_by_code": {code: days_by_code[code] for code in days_by_code},
        "main_net_by_code": {item["code"]: item["main_net"] for item in items},
    }


def _item_key(row: dict) -> dict:
    return {
        "code": str(row.get("code") or "").upper(),
        "name": row.get("name"),
        "main_net": row.get("main_net"),
        "days": int(row.get("days") or 0),
    }


def compare_window(label: str, kind: str, days: int) -> dict:
    independent = independent_window(kind, days, top=TOP)
    service = aggregate_board_window(DATA_DIR, kind=kind, days=days, top=TOP)
    fields = (
        "kind",
        "requested_days",
        "window_days",
        "start",
        "end",
        "snapshot_count",
        "covered_count",
        "full_count",
        "missing_count",
        "window_complete",
    )
    mismatches: list[str] = []
    for field in fields:
        if independent.get(field) != service.get(field):
            mismatches.append(
                f"{field}: independent={independent.get(field)!r} service={service.get(field)!r}"
            )
    service_items = [_item_key(row) for row in (service.get("items") or [])]
    independent_items = [_item_key(row) for row in (independent.get("items") or [])]
    if service_items != independent_items:
        mismatches.append("items_order_or_values")
    service_by_code = {row["code"]: row for row in service_items}
    for code, row in service_by_code.items():
        independent_net = independent["main_net_by_code"].get(code)
        if independent_net != row["main_net"]:
            mismatches.append(
                f"main_net[{code}]: independent={independent_net!r} service={row['main_net']!r}"
            )
        independent_days = independent["sums_by_code"].get(code)
        if independent_days != row["days"]:
            mismatches.append(
                f"days[{code}]: independent={independent_days!r} service={row['days']!r}"
            )
    return {
        "label": label,
        "kind": kind,
        "days": days,
        "match": not mismatches,
        "mismatches": mismatches,
        "independent": {
            "start": independent["start"],
            "end": independent["end"],
            "window_days": independent["window_days"],
            "snapshot_count": independent["snapshot_count"],
            "covered_count": independent["covered_count"],
            "full_count": independent["full_count"],
            "missing_count": independent["missing_count"],
            "window_complete": independent["window_complete"],
            "items": independent_items,
        },
        "service": {
            "start": service.get("start"),
            "end": service.get("end"),
            "window_days": service.get("window_days"),
            "snapshot_count": service.get("snapshot_count"),
            "covered_count": service.get("covered_count"),
            "full_count": service.get("full_count"),
            "missing_count": service.get("missing_count"),
            "window_complete": service.get("window_complete"),
            "items": service_items,
            "freshness_status": service.get("freshness_status"),
        },
    }


def main() -> int:
    results = [compare_window(label, kind, days) for label, kind, days in WINDOWS]
    payload = {
        "data_dir": str(DATA_DIR),
        "all_match": all(item["match"] for item in results),
        "windows": {item["label"]: item for item in results},
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["all_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
