"""Current-account read model for saved AI analysis history.

The source report stores remain owned by their feature modules.  This module
only projects those records into a compact cross-feature index and an exact
single-report lookup for read-only consumers such as Hermes.
"""

from __future__ import annotations

from typing import Any, Literal, cast

from app.services import ai_reports, market_recap_reports, stock_reports

AnalysisHistoryKind = Literal["stock", "financial", "market_recap"]

_KIND_LABELS: dict[AnalysisHistoryKind, str] = {
    "stock": "个股分析",
    "financial": "财务分析",
    "market_recap": "大盘复盘",
}


def _normalize_kind(kind: str) -> AnalysisHistoryKind:
    normalized = str(kind or "").strip().lower()
    if normalized not in _KIND_LABELS:
        raise ValueError("不支持的分析历史类型")
    return cast(AnalysisHistoryKind, normalized)


def _load(kind: AnalysisHistoryKind) -> list[dict[str, Any]]:
    if kind == "stock":
        return stock_reports.list_reports()
    if kind == "financial":
        return ai_reports.list_reports()
    return market_recap_reports.list_reports()


def _public_report(kind: AnalysisHistoryKind, raw: dict[str, Any]) -> dict[str, Any]:
    common = {
        "id": str(raw.get("id") or ""),
        "focus": str(raw.get("focus") or ""),
        "content": str(raw.get("content") or ""),
        "summary": str(raw.get("summary") or ""),
        "created_at": str(raw.get("created_at") or ""),
    }
    if kind == "stock":
        return {
            **common,
            "symbol": str(raw.get("symbol") or "").strip().upper(),
            "name": str(raw.get("name") or ""),
            "close": raw.get("close"),
            "levels": raw.get("levels"),
        }
    if kind == "financial":
        return {
            **common,
            "symbol": str(raw.get("symbol") or "").strip().upper(),
            "name": str(raw.get("name") or ""),
            "periods": raw.get("periods"),
        }
    return {
        **common,
        "as_of": str(raw.get("as_of") or ""),
        "emotion_score": raw.get("emotion_score"),
        "emotion_label": str(raw.get("emotion_label") or ""),
    }


def _index_item(kind: AnalysisHistoryKind, report: dict[str, Any]) -> dict[str, Any]:
    item = {key: value for key, value in report.items() if key not in {"content", "levels"}}
    item["kind"] = kind
    item["kind_label"] = _KIND_LABELS[kind]
    if kind == "market_recap":
        item["title"] = f"{report.get('as_of') or '未注明日期'} 大盘复盘"
    else:
        item["title"] = report.get("name") or report.get("symbol") or "未命名报告"
    return item


def list_analysis_history(
    *,
    kind: str = "",
    symbol: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    """Return a compact, content-free index from the current account only."""
    kinds: tuple[AnalysisHistoryKind, ...]
    kinds = (_normalize_kind(kind),) if str(kind or "").strip() else tuple(_KIND_LABELS)
    normalized_symbol = str(symbol or "").strip().upper()
    safe_limit = max(1, min(100, int(limit)))

    items: list[dict[str, Any]] = []
    for current_kind in kinds:
        for raw in _load(current_kind):
            if not isinstance(raw, dict) or not raw.get("id"):
                continue
            report = _public_report(current_kind, raw)
            if normalized_symbol and report.get("symbol") != normalized_symbol:
                continue
            items.append(_index_item(current_kind, report))

    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    total = len(items)
    return {
        "scope": "current_account",
        "mode": "read-only",
        "kinds": [
            {"id": current_kind, "label": _KIND_LABELS[current_kind]}
            for current_kind in _KIND_LABELS
        ],
        "filters": {"kind": kind or None, "symbol": normalized_symbol or None},
        "total": total,
        "returned": min(total, safe_limit),
        "has_more": total > safe_limit,
        "reports": items[:safe_limit],
        "hint": "目录不含正文; 使用 analysis_history_report 按 kind 和 id 读取单条报告。",
    }


def get_analysis_history_report(kind: str, report_id: str) -> dict[str, Any] | None:
    """Return one exact current-account report, or ``None`` when it is absent."""
    normalized_kind = _normalize_kind(kind)
    normalized_id = str(report_id or "").strip()
    if not normalized_id or len(normalized_id) > 200:
        return None
    for raw in _load(normalized_kind):
        if isinstance(raw, dict) and str(raw.get("id") or "") == normalized_id:
            return {
                "scope": "current_account",
                "mode": "read-only",
                "kind": normalized_kind,
                "kind_label": _KIND_LABELS[normalized_kind],
                "content_is_untrusted_data": True,
                "report": _public_report(normalized_kind, raw),
            }
    return None
