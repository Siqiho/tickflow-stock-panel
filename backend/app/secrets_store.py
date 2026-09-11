"""User-scoped settings plus a separate deployment-owned credential store.

User-managed keys remain under each tenant's ``user_data/secrets.json``.
Hosted Grok OAuth lives at ``DATA_DIR/control/deployment-secrets.json`` so no
product user or Hermes Profile owns the upstream subscription credential.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from contextlib import suppress
from pathlib import Path

logger = logging.getLogger(__name__)
_deployment_lock = threading.Lock()


def _path() -> Path:
    from app.services.user_context import user_path
    p = user_path("secrets.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _deployment_path() -> Path:
    from app.config import settings

    return settings.data_dir / "control" / "deployment-secrets.json"


def _legacy_owner_path() -> Path:
    from app.config import settings

    return settings.data_dir / "user_data" / "secrets.json"


def _load_path(path: Path, *, label: str) -> dict:
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception as exc:
            logger.warning("%s malformed: %s", label, exc)
    return {}


def _atomic_save(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=str(path.parent),
    )
    temp_path = Path(temp_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        os.chmod(path, 0o600)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        with suppress(FileNotFoundError):
            temp_path.unlink()


def load() -> dict:
    return _load_path(_path(), label="secrets.json")


def load_deployment() -> dict:
    """Read server-owned credentials that are never scoped to a product user."""
    return _load_path(_deployment_path(), label="deployment-secrets.json")


def load_legacy_owner() -> dict:
    """Read the pre-multi-user owner store as a non-mutating migration fallback."""
    return _load_path(_legacy_owner_path(), label="legacy owner secrets.json")


def save_deployment(updates: dict) -> dict:
    """Atomically merge deployment credentials under DATA_DIR/control."""
    with _deployment_lock:
        current = load_deployment()
        current.update({key: value for key, value in updates.items() if value is not None})
        _atomic_save(_deployment_path(), current)
        return current


def clear_deployment(*keys: str) -> dict:
    with _deployment_lock:
        path = _deployment_path()
        current = load_deployment()
        if not keys:
            with suppress(FileNotFoundError):
                path.unlink()
            return {}
        for key in keys:
            current.pop(key, None)
        _atomic_save(path, current)
        return current


def save(updates: dict) -> dict:
    """合并写入(不会清掉未提及的字段)。返回新内容。"""
    current = load()
    current.update({k: v for k, v in updates.items() if v is not None})
    p = _path()
    p.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
    with suppress(OSError):
        os.chmod(p, 0o600)
    return current


def clear(*keys: str) -> dict:
    """清掉指定字段(留空清全部)。"""
    p = _path()
    if not p.exists():
        return {}
    if not keys:
        p.unlink()
        return {}
    current = load()
    for k in keys:
        current.pop(k, None)
    p.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
    return current


def get_tickflow_key() -> str:
    """取当前 TickFlow Key:secrets.json 优先,否则 .env。"""
    val = load().get("tickflow_api_key")
    if val:
        return val
    from app.config import settings
    return settings.tickflow_api_key or ""


def get_ai_key() -> str:
    """取当前 AI Key:secrets.json 优先,否则 .env。"""
    val = load().get("ai_api_key")
    if val:
        return val
    from app.config import settings
    return settings.ai_api_key or ""


def get_ai_config(key: str, default: str = "") -> str:
    """取 AI 配置项:secrets.json 优先,否则 config。"""
    val = load().get(key)
    if val:
        return val
    from app.config import settings
    return getattr(settings, key, default) or default


def get_email_smtp_password() -> str:
    """User-scoped SMTP password / authorization code. Empty means unset."""
    return str(load().get("email_smtp_password") or "")


def set_email_smtp_password(password: str) -> str:
    """Persist or clear the user-scoped SMTP password. Never logged."""
    value = str(password or "")
    if value:
        save({"email_smtp_password": value})
    else:
        clear("email_smtp_password")
    return get_email_smtp_password()


def get_custom_webhook_secret() -> str:
    """Optional HMAC secret for the generic third-party JSON webhook."""
    return str(load().get("custom_webhook_secret") or "")


def set_custom_webhook_secret(secret: str) -> str:
    """Persist or clear the generic webhook HMAC secret."""
    value = str(secret or "")
    if value:
        save({"custom_webhook_secret": value})
    else:
        clear("custom_webhook_secret")
    return get_custom_webhook_secret()


def get_env_backed_secret(field: str, env_name: str = "") -> str:
    """secrets.json 优先, 否则读环境变量。"""
    import os

    val = load().get(field)
    if val:
        return str(val)
    if env_name:
        return os.environ.get(env_name, "") or ""
    return ""


def mask(key: str, prefix: int = 4, suffix: int = 4) -> str:
    """脱敏显示。"""
    if not key:
        return ""
    if len(key) <= prefix + suffix:
        return "•" * len(key)
    return f"{key[:prefix]}{'•' * 6}{key[-suffix:]}"
