"""Page-embedded Hermes analysis reports.

Independent from stock/financial/review reports. Stores the visible conversation
plus page snapshot metadata so charts and text can be reopened later.

Storage: data/user_data/ai_page_reports.json
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_REPORTS = 50


def _path() -> Path:
    from app.services.user_context import user_path
    p = user_path("ai_page_reports.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def list_reports() -> list[dict]:
    p = _path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return sorted(data, key=lambda r: r.get("created_at", ""), reverse=True)
    except Exception as e:  # noqa: BLE001
        logger.warning("ai_page_reports.json malformed: %s", e)
    return []


def get_report(report_id: str) -> dict | None:
    wanted = str(report_id or "").strip()
    if not wanted:
        return None
    for item in list_reports():
        if str(item.get("id") or "") == wanted:
            return item
    return None


def _save_all(reports: list[dict]) -> None:
    reports.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    if len(reports) > MAX_REPORTS:
        reports = reports[:MAX_REPORTS]
    _path().write_text(
        json.dumps(reports, indent=2, ensure_ascii=False), encoding="utf-8",
    )


def save_report(report: dict) -> dict:
    reports = list_reports()
    if not report.get("id"):
        route = str(report.get("route") or "page").replace("/", "_").strip("_") or "page"
        report["id"] = f"par_{int(time.time() * 1000)}_{route}"
    if not report.get("created_at"):
        report["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    reports.append(report)
    _save_all(reports)
    logger.info("Page AI report saved: %s (%s), total %d", report.get("title"), report.get("id"), len(reports))
    return report


def delete_report(report_id: str) -> bool:
    reports = list_reports()
    kept = [item for item in reports if str(item.get("id") or "") != report_id]
    if len(kept) == len(reports):
        return False
    _save_all(kept)
    return True
