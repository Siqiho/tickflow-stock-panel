"""Account-owned durable history for strategy backtest results."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.atomic_io import atomic_write_json
from app.services.user_context import current, user_data_dir_for

_RUN_ID_RE = re.compile(r"^[a-f0-9]{10}$")
_MAX_HISTORY = 100


class BacktestHistoryError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class BacktestHistoryStore:
    """Persist and query one actor's strategy backtest history."""

    def __init__(self, data_dir: Path, principal: dict[str, Any] | None = None) -> None:
        self.principal = dict(principal or current())
        self.root = (
            user_data_dir_for(self.principal, data_dir, create=False)
            / "backtests"
            / "strategy"
        )

    def save(
        self,
        result: dict[str, Any],
        *,
        strategy_owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        run_id = str(result.get("run_id") or "")
        if not _RUN_ID_RE.fullmatch(run_id):
            raise BacktestHistoryError("回测结果缺少有效 run_id", status_code=422)
        payload = dict(result)
        payload["saved_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        payload["actor_user_id"] = str(self.principal.get("id") or "")
        payload["strategy_owner_user_id"] = str(
            strategy_owner_user_id or self.principal.get("id") or ""
        )
        self.root.mkdir(parents=True, exist_ok=True)
        atomic_write_json(payload, self.root / f"{run_id}.json", indent=2)
        self._prune()
        return payload

    def list(self, *, limit: int = 30) -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        rows: list[dict[str, Any]] = []
        paths = sorted(
            self.root.glob("*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in paths[: max(1, min(_MAX_HISTORY, int(limit)))]:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            strategy_info = payload.get("strategy_info") or {}
            config = payload.get("config") or {}
            stats = payload.get("stats") or {}
            rows.append(
                {
                    "run_id": payload.get("run_id"),
                    "saved_at": payload.get("saved_at"),
                    "strategy_id": strategy_info.get("id") or config.get("strategy_id"),
                    "strategy_name": strategy_info.get("name") or config.get("strategy_id"),
                    "strategy_source": strategy_info.get("source"),
                    "strategy_owner_user_id": payload.get("strategy_owner_user_id"),
                    "start": config.get("start"),
                    "end": config.get("end"),
                    "total_return": stats.get("total_return"),
                    "trade_count": stats.get("total_trades", len(payload.get("trades") or [])),
                    "error": payload.get("error"),
                }
            )
        return rows

    def get(self, run_id: str) -> dict[str, Any]:
        safe_id = str(run_id or "").strip().lower()
        if not _RUN_ID_RE.fullmatch(safe_id):
            raise BacktestHistoryError("回测记录不存在", status_code=404)
        path = self.root / f"{safe_id}.json"
        if not path.exists():
            raise BacktestHistoryError("回测记录不存在", status_code=404)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BacktestHistoryError("回测记录损坏或不可读取", status_code=500) from exc
        if payload.get("actor_user_id") != self.principal.get("id"):
            raise BacktestHistoryError("无权访问其他用户的回测记录", status_code=403)
        return payload

    def delete(self, run_id: str) -> bool:
        self.get(run_id)
        (self.root / f"{run_id}.json").unlink()
        return True

    def _prune(self) -> None:
        paths = sorted(
            self.root.glob("*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in paths[_MAX_HISTORY:]:
            path.unlink(missing_ok=True)

