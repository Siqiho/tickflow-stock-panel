"""统一运行日志 — 数据台后端 + 用户台前端事件。

落盘目录: ``{data_dir}/logs/``
  - app.log        后端模块日志 (INFO+)
  - error.log      错误日志 (ERROR+)
  - access.log     HTTP 访问
  - ui.log         前端上报事件
  - runtime.jsonl  结构化统一事件流 (供 UI 查询)

同时在内存保留环形缓冲, 便于设置页快速拉取最近运行轨迹。
"""
from __future__ import annotations

import contextlib
import json
import logging
import sys
import threading
import uuid
from collections import deque
from collections.abc import Iterable
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

# ── 常量 ──────────────────────────────────────────────
_MAX_BUFFER = 3000
_MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB
_BACKUP_COUNT = 5
_SKIP_ACCESS_PREFIXES = (
    "/api/runtime-logs",
    "/health",
    "/api/health",
    "/openapi.json",
    "/docs",
    "/redoc",
    "/assets/",
)
# 高频轮询 GET: 默认不写 access 日志, 避免淹没真正操作轨迹
_SKIP_ACCESS_GET_EXACT = {
    "/api/intraday/status",
    "/api/pipeline/jobs",
    "/api/data/status",
    "/api/financials/status",
    "/api/alerts",
    "/api/auth/status",
    "/api/backtest/status",
    "/api/strategies/ai/status",
}
_SKIP_ACCESS_GET_PREFIXES = (
    "/api/pipeline/jobs/",
)
_SENSITIVE_KEYS = {
    "password",
    "old_password",
    "new_password",
    "api_key",
    "ai_api_key",
    "token",
    "authorization",
    "cookie",
    "secret",
    "feishu_webhook_secret",
}

_lock = threading.RLock()
_buffer: deque[dict[str, Any]] = deque(maxlen=_MAX_BUFFER)
_configured = False
_log_dir: Path | None = None
_process_id = uuid.uuid4().hex[:8]
_jsonl_path: Path | None = None
_ui_logger = logging.getLogger("one_trading.ui")
_access_logger = logging.getLogger("one_trading.access")
_runtime_logger = logging.getLogger("one_trading.runtime")
# 专用 logger 不向 root 传播, 避免 BufferHandler 递归
_ui_logger.propagate = False
_access_logger.propagate = False
_runtime_logger.propagate = False


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def log_dir() -> Path | None:
    return _log_dir


def process_id() -> str:
    return _process_id


def is_configured() -> bool:
    return _configured


def setup_runtime_logging(level: str = "INFO", data_dir: Path | None = None) -> Path:
    """初始化控制台 + 滚动文件日志。幂等。"""
    global _configured, _log_dir, _jsonl_path

    with _lock:
        if data_dir is None:
            from app.config import settings

            data_dir = settings.data_dir

        target = Path(data_dir) / "logs"
        target.mkdir(parents=True, exist_ok=True)

        if _configured and _log_dir == target:
            return target

        # 若目录变更(测试场景), 清掉旧 handler 再配
        root = logging.getLogger()
        for h in list(root.handlers):
            root.removeHandler(h)
            with contextlib.suppress(Exception):
                h.close()

        numeric = getattr(logging, str(level).upper(), logging.INFO)
        root.setLevel(numeric)

        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

        console = logging.StreamHandler(sys.stderr)
        console.setLevel(numeric)
        console.setFormatter(fmt)
        root.addHandler(console)

        app_handler = RotatingFileHandler(
            target / "app.log",
            maxBytes=_MAX_FILE_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        app_handler.setLevel(numeric)
        app_handler.setFormatter(fmt)
        root.addHandler(app_handler)

        err_handler = RotatingFileHandler(
            target / "error.log",
            maxBytes=_MAX_FILE_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        err_handler.setLevel(logging.ERROR)
        err_handler.setFormatter(fmt)
        root.addHandler(err_handler)

        access_handler = RotatingFileHandler(
            target / "access.log",
            maxBytes=_MAX_FILE_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        access_handler.setLevel(logging.INFO)
        access_handler.setFormatter(fmt)
        _access_logger.handlers.clear()
        _access_logger.setLevel(logging.INFO)
        _access_logger.propagate = False
        _access_logger.addHandler(access_handler)
        # 也写一份到 app.log
        _access_logger.addHandler(app_handler)

        ui_handler = RotatingFileHandler(
            target / "ui.log",
            maxBytes=_MAX_FILE_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        ui_handler.setLevel(logging.INFO)
        ui_handler.setFormatter(fmt)
        _ui_logger.handlers.clear()
        _ui_logger.setLevel(logging.INFO)
        _ui_logger.propagate = False
        _ui_logger.addHandler(ui_handler)
        _ui_logger.addHandler(app_handler)

        _runtime_logger.handlers.clear()
        _runtime_logger.setLevel(logging.INFO)
        _runtime_logger.propagate = False
        _runtime_logger.addHandler(app_handler)
        _runtime_logger.addHandler(err_handler)

        # 把标准 logging 记录镜像进结构化缓冲
        root.addHandler(_BufferHandler())

        _log_dir = target
        _jsonl_path = target / "runtime.jsonl"
        _configured = True

        emit_event(
            source="backend",
            level="INFO",
            category="lifecycle",
            message="runtime logging ready",
            detail={
                "log_dir": str(target),
                "level": str(level).upper(),
                "process_id": _process_id,
            },
        )
        return target


class _BufferHandler(logging.Handler):
    """把常规 logging 记录同步进环形缓冲 / jsonl。"""

    _guard = threading.local()

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(self._guard, "active", False):
            return
        # 避免把 access/ui 专用 logger 再写一遍(它们已显式 emit_event)
        if record.name in {"one_trading.access", "one_trading.ui", "one_trading.runtime"}:
            return
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        self._guard.active = True
        try:
            source = "backend"
            category = "system"
            name = record.name or ""
            if name.startswith("uvicorn") or name.startswith("fastapi"):
                category = "server"
            elif ".api." in name or name.endswith(".api"):
                category = "api"
            elif "data_providers" in name or "tickflow" in name or "pipeline" in name:
                category = "data"
            elif "strategy" in name or "monitor" in name or "screener" in name:
                category = "strategy"
            elif "ai_" in name or name.endswith("ai_provider"):
                category = "ai"

            emit_event(
                source=source,
                level=record.levelname,
                category=category,
                message=msg,
                logger_name=name,
                detail={
                    "pathname": getattr(record, "pathname", None),
                    "lineno": getattr(record, "lineno", None),
                },
                mirror_std_log=False,
            )
        finally:
            self._guard.active = False



def _sanitize(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return "…"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            key = str(k)
            if key.lower() in _SENSITIVE_KEYS or any(s in key.lower() for s in ("password", "secret", "token", "api_key")):
                out[key] = "***"
            else:
                out[key] = _sanitize(v, depth=depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        if len(value) > 20:
            return [_sanitize(v, depth=depth + 1) for v in value[:20]] + [f"…(+{len(value) - 20})"]
        return [_sanitize(v, depth=depth + 1) for v in value]
    if isinstance(value, str) and len(value) > 500:
        return value[:500] + "…"
    return value


def emit_event(
    *,
    source: str,
    level: str,
    category: str,
    message: str,
    detail: dict[str, Any] | None = None,
    logger_name: str | None = None,
    session_id: str | None = None,
    path: str | None = None,
    method: str | None = None,
    status: int | None = None,
    duration_ms: float | None = None,
    change: dict[str, Any] | None = None,
    ts: str | None = None,
    mirror_std_log: bool = True,
) -> dict[str, Any]:
    """写入一条结构化运行事件。"""
    event = {
        "id": uuid.uuid4().hex[:12],
        "ts": ts or _utc_now_iso(),
        "source": source,
        "level": (level or "INFO").upper(),
        "category": category or "general",
        "message": str(message)[:2000],
        "process_id": _process_id,
    }
    if logger_name:
        event["logger"] = logger_name
    if session_id:
        event["session_id"] = session_id
    if path is not None:
        event["path"] = path
    if method is not None:
        event["method"] = method
    if status is not None:
        event["status"] = status
    if duration_ms is not None:
        event["duration_ms"] = round(float(duration_ms), 2)
    if detail:
        event["detail"] = _sanitize(detail)
    if change:
        event["change"] = _sanitize(change)

    with _lock:
        _buffer.appendleft(event)
        if _jsonl_path is not None:
            try:
                with _jsonl_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
            except Exception:
                pass

        if mirror_std_log:
            line = _format_line(event)
            lvl = event["level"]
            if source == "ui":
                _log_to(_ui_logger, lvl, line)
            elif category == "access" or source == "access":
                _log_to(_access_logger, lvl, line)
            else:
                _log_to(_runtime_logger, lvl, line)

    return event


def _log_to(logger: logging.Logger, level: str, line: str) -> None:
    level_no = getattr(logging, level, logging.INFO)
    logger.log(level_no if isinstance(level_no, int) else logging.INFO, line)


def _format_line(event: dict[str, Any]) -> str:
    parts = [
        f"[{event.get('source', '-')}/{event.get('category', '-')}]",
        event.get("message", ""),
    ]
    if event.get("method") or event.get("path"):
        parts.append(f"{event.get('method', '')} {event.get('path', '')}".strip())
    if event.get("status") is not None:
        parts.append(f"status={event['status']}")
    if event.get("duration_ms") is not None:
        parts.append(f"{event['duration_ms']}ms")
    if event.get("change"):
        parts.append(f"change={json.dumps(event['change'], ensure_ascii=False, default=str)}")
    if event.get("detail"):
        # 细节过长时截断
        detail_s = json.dumps(event["detail"], ensure_ascii=False, default=str)
        if len(detail_s) > 400:
            detail_s = detail_s[:400] + "…"
        parts.append(f"detail={detail_s}")
    return " ".join(str(p) for p in parts if p)


def should_skip_access(path: str, method: str | None = None) -> bool:
    p = path or ""
    if any(p == pref or p.startswith(pref) for pref in _SKIP_ACCESS_PREFIXES):
        return True
    m = (method or "GET").upper()
    if m == "GET":
        if p in _SKIP_ACCESS_GET_EXACT:
            return True
        if any(p.startswith(pref) for pref in _SKIP_ACCESS_GET_PREFIXES):
            return True
    return False


def log_access(
    *,
    method: str,
    path: str,
    status: int,
    duration_ms: float,
    client: str | None = None,
    query: str | None = None,
) -> None:
    if should_skip_access(path, method):
        return
    level = "INFO"
    if status >= 500:
        level = "ERROR"
    elif status >= 400:
        level = "WARNING"
    msg = f"HTTP {method} {path} -> {status} ({duration_ms:.1f}ms)"
    emit_event(
        source="access",
        level=level,
        category="access",
        message=msg,
        method=method,
        path=path,
        status=status,
        duration_ms=duration_ms,
        detail={"client": client, "query": query or None},
    )


def ingest_client_events(events: Iterable[dict[str, Any]], *, default_session: str | None = None) -> int:
    """接收前端批量事件。"""
    count = 0
    for raw in events:
        if not isinstance(raw, dict):
            continue
        message = str(raw.get("message") or raw.get("msg") or "").strip()
        if not message:
            continue
        emit_event(
            source="ui",
            level=str(raw.get("level") or "INFO"),
            category=str(raw.get("category") or "ui"),
            message=message,
            session_id=str(raw.get("session_id") or default_session or "") or None,
            path=raw.get("path"),
            method=raw.get("method"),
            status=raw.get("status") if isinstance(raw.get("status"), int) else None,
            duration_ms=raw.get("duration_ms"),
            detail=raw.get("detail") if isinstance(raw.get("detail"), dict) else None,
            change=raw.get("change") if isinstance(raw.get("change"), dict) else None,
            ts=str(raw["ts"]) if raw.get("ts") else None,
        )
        count += 1
    return count


def query_events(
    *,
    source: str | None = None,
    level: str | None = None,
    category: str | None = None,
    q: str | None = None,
    limit: int = 200,
    after_id: str | None = None,
) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 200), 1000))
    level_u = level.upper() if level else None
    source_l = source.lower() if source else None
    category_l = category.lower() if category else None
    q_l = q.lower() if q else None

    with _lock:
        items = list(_buffer)

    # after_id: 返回比该 id 更新的事件 (缓冲是新->旧)
    if after_id:
        trimmed: list[dict[str, Any]] = []
        for ev in items:
            if ev.get("id") == after_id:
                break
            trimmed.append(ev)
        items = trimmed

    out: list[dict[str, Any]] = []
    for ev in items:
        src = str(ev.get("source", "")).lower()
        if source_l and src != source_l and not (
            source_l == "backend" and src in {"backend", "access"}
        ):
            # access 也可归到 backend 过滤器
            continue
        # 返回该级别及以上
        if level_u and _level_rank(ev.get("level")) < _level_rank(level_u):
            continue
        if category_l and str(ev.get("category", "")).lower() != category_l:
            continue
        if q_l:
            blob = json.dumps(ev, ensure_ascii=False, default=str).lower()
            if q_l not in blob:
                continue
        out.append(ev)
        if len(out) >= limit:
            break
    return out


def _level_rank(level: str | None) -> int:
    order = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "WARN": 30, "ERROR": 40, "CRITICAL": 50}
    return order.get((level or "INFO").upper(), 20)


def get_status() -> dict[str, Any]:
    files: dict[str, Any] = {}
    if _log_dir and _log_dir.exists():
        for name in ("app.log", "error.log", "access.log", "ui.log", "runtime.jsonl"):
            p = _log_dir / name
            if p.exists():
                st = p.stat()
                files[name] = {
                    "path": str(p),
                    "size_bytes": st.st_size,
                    "mtime": datetime.fromtimestamp(st.st_mtime, tz=UTC)
                    .isoformat(timespec="seconds")
                    .replace("+00:00", "Z"),
                }
            else:
                files[name] = None
    with _lock:
        buf_len = len(_buffer)
        latest_ts = _buffer[0]["ts"] if _buffer else None
    return {
        "configured": _configured,
        "process_id": _process_id,
        "log_dir": str(_log_dir) if _log_dir else None,
        "buffer_size": buf_len,
        "buffer_capacity": _MAX_BUFFER,
        "latest_ts": latest_ts,
        "files": files,
        "uptime_s": None,
    }


def clear_logs(*, keep_files: bool = False) -> dict[str, Any]:
    """清空内存缓冲; 可选截断日志文件。"""
    removed_files: list[str] = []
    with _lock:
        _buffer.clear()
        if not keep_files and _log_dir is not None:
            for name in ("app.log", "error.log", "access.log", "ui.log", "runtime.jsonl"):
                p = _log_dir / name
                if p.exists():
                    try:
                        p.write_text("", encoding="utf-8")
                        removed_files.append(name)
                    except Exception:
                        pass
    emit_event(
        source="backend",
        level="INFO",
        category="lifecycle",
        message="runtime logs cleared",
        detail={"truncated_files": removed_files},
    )
    return {"ok": True, "truncated_files": removed_files}


def reset_for_tests() -> None:
    """测试辅助: 重置全局状态。"""
    global _configured, _log_dir, _jsonl_path, _process_id
    with _lock:
        _buffer.clear()
        root = logging.getLogger()
        for h in list(root.handlers):
            root.removeHandler(h)
            with contextlib.suppress(Exception):
                h.close()
        for lg in (_ui_logger, _access_logger, _runtime_logger):
            for h in list(lg.handlers):
                lg.removeHandler(h)
                with contextlib.suppress(Exception):
                    h.close()
        _configured = False
        _log_dir = None
        _jsonl_path = None
        _process_id = uuid.uuid4().hex[:8]
