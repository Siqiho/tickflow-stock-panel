"""Per-account portfolio ledger enriched from the shared market data plane.

This Module records holdings only.  It has no broker credentials, order API or
external side effects; prices and names are projected from the common market
repository at read time.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.atomic_io import atomic_write_json
from app.services.user_context import current, user_data_dir_for

_SYMBOL_RE = re.compile(r"^\d{6}\.(?:SH|SZ|BJ)$")


class PortfolioError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class PortfolioWorkspace:
    """Own the durable holdings ledger for one authenticated account."""

    def __init__(self, data_dir: Path, principal: dict[str, Any] | None = None) -> None:
        self.principal = dict(principal or current())
        self.path = (
            user_data_dir_for(self.principal, data_dir, create=False)
            / "portfolio"
            / "holdings.json"
        )

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": 1, "updated_at": None, "holdings": []}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PortfolioError("持仓账本损坏或不可读取", status_code=500) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("holdings"), list):
            raise PortfolioError("持仓账本格式无效", status_code=500)
        return payload

    @staticmethod
    def _normalize(raw: dict[str, Any], *, previous: dict[str, Any] | None = None) -> dict[str, Any]:
        symbol = str(raw.get("symbol") or "").strip().upper()
        if not _SYMBOL_RE.fullmatch(symbol):
            raise PortfolioError("股票代码格式应为 600000.SH / 000001.SZ / 430001.BJ", status_code=422)
        try:
            quantity = int(raw.get("quantity"))
        except (TypeError, ValueError) as exc:
            raise PortfolioError("持仓数量必须是正整数", status_code=422) from exc
        if quantity <= 0 or quantity > 10_000_000_000:
            raise PortfolioError("持仓数量必须在 1 到 100 亿股之间", status_code=422)
        try:
            avg_cost = float(raw.get("avg_cost"))
        except (TypeError, ValueError) as exc:
            raise PortfolioError("平均成本必须是正数", status_code=422) from exc
        if not 0 < avg_cost <= 10_000_000:
            raise PortfolioError("平均成本超出允许范围", status_code=422)
        note = " ".join(str(raw.get("note") or "").split())
        if len(note) > 240:
            raise PortfolioError("持仓备注不能超过 240 个字符", status_code=422)
        return {
            "symbol": symbol,
            "quantity": quantity,
            "avg_cost": round(avg_cost, 6),
            "note": note,
            "created_at": (previous or {}).get("created_at") or _now(),
            "updated_at": _now(),
        }

    def list(self) -> list[dict[str, Any]]:
        return sorted(self._load()["holdings"], key=lambda item: str(item.get("symbol") or ""))

    def upsert(self, raw: dict[str, Any]) -> dict[str, Any]:
        payload = self._load()
        previous = next(
            (item for item in payload["holdings"] if item.get("symbol") == str(raw.get("symbol") or "").upper()),
            None,
        )
        holding = self._normalize(raw, previous=previous)
        remaining = [item for item in payload["holdings"] if item.get("symbol") != holding["symbol"]]
        remaining.append(holding)
        next_payload = {
            "schema_version": 1,
            "updated_at": _now(),
            "holdings": sorted(remaining, key=lambda item: item["symbol"]),
        }
        atomic_write_json(next_payload, self.path, indent=2)
        return holding

    def delete(self, symbol: str) -> bool:
        safe_symbol = str(symbol or "").strip().upper()
        if not _SYMBOL_RE.fullmatch(safe_symbol):
            raise PortfolioError("持仓不存在", status_code=404)
        payload = self._load()
        remaining = [item for item in payload["holdings"] if item.get("symbol") != safe_symbol]
        if len(remaining) == len(payload["holdings"]):
            raise PortfolioError("持仓不存在", status_code=404)
        atomic_write_json(
            {"schema_version": 1, "updated_at": _now(), "holdings": remaining},
            self.path,
            indent=2,
        )
        return True

    def snapshot(self, repo: Any) -> dict[str, Any]:
        from app.services.screener import ScreenerService

        holdings = self.list()
        service = ScreenerService(repo)
        as_of = service.latest_date()
        quotes: dict[str, dict[str, Any]] = {}
        if as_of and holdings:
            frame = service._load_enriched_for_date(as_of)
            if not frame.is_empty() and "symbol" in frame.columns:
                wanted = [holding["symbol"] for holding in holdings]
                columns = [
                    column
                    for column in ("symbol", "name", "close", "change_pct")
                    if column in frame.columns
                ]
                quotes = {
                    str(row["symbol"]): row
                    for row in frame.filter(frame["symbol"].is_in(wanted)).select(columns).to_dicts()
                }

        rows: list[dict[str, Any]] = []
        total_cost = 0.0
        total_market_value = 0.0
        priced_count = 0
        for holding in holdings:
            quote = quotes.get(holding["symbol"], {})
            close_raw = quote.get("close")
            close = float(close_raw) if isinstance(close_raw, (int, float)) else None
            cost_value = float(holding["quantity"]) * float(holding["avg_cost"])
            market_value = float(holding["quantity"]) * close if close is not None else None
            pnl_amount = market_value - cost_value if market_value is not None else None
            pnl_pct = pnl_amount / cost_value if pnl_amount is not None and cost_value > 0 else None
            total_cost += cost_value
            if market_value is not None:
                total_market_value += market_value
                priced_count += 1
            rows.append(
                {
                    **holding,
                    "name": quote.get("name"),
                    "close": close,
                    "change_pct": quote.get("change_pct"),
                    "cost_value": round(cost_value, 2),
                    "market_value": round(market_value, 2) if market_value is not None else None,
                    "pnl_amount": round(pnl_amount, 2) if pnl_amount is not None else None,
                    "pnl_pct": round(pnl_pct, 8) if pnl_pct is not None else None,
                }
            )
        total_pnl = total_market_value - total_cost if priced_count == len(rows) else None
        return {
            "as_of": str(as_of) if as_of else None,
            "holdings": rows,
            "summary": {
                "holding_count": len(rows),
                "priced_count": priced_count,
                "total_cost": round(total_cost, 2),
                "total_market_value": round(total_market_value, 2) if priced_count else None,
                "total_pnl": round(total_pnl, 2) if total_pnl is not None else None,
                "total_pnl_pct": (
                    round(total_pnl / total_cost, 8)
                    if total_pnl is not None and total_cost > 0
                    else None
                ),
            },
        }

