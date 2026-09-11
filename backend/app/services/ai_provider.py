"""AI provider adapter for OpenAI-compatible APIs and local Codex CLI."""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import sys
import tempfile
import tomllib
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from app import secrets_store
from app.config import settings

OPENAI_COMPAT_PROVIDER = "openai_compat"
CODEX_CLI_PROVIDER = "codex_cli"
XAI_PROVIDER = "xai"
XAI_API_BASE = "https://api.x.ai/v1"
XAI_DEFAULT_MODEL = "grok-4.5"
GAMESTORE_PROVIDER = "86gamestore"
GAMESTORE_API_BASE = "https://api.86gamestore.com/v1"
GAMESTORE_DEFAULT_MODEL = "gpt-5.6-sol"
GAMESTORE_MODELS = (
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6",
    "gpt-5.5",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.3-codex-spark",
    "codex-auto-review",
)
SUBROUTER_PROVIDER = "subrouter"
SUBROUTER_API_BASE = "https://subrouter.ai/v1"
SUBROUTER_DEFAULT_MODEL = "gpt-5.6-sol"
SUBROUTER_MODELS = ("gpt-5.6-sol",)
CLOUD_SUBSCRIPTION_MODE = "cloud_subscription"
CODEX_DEFAULT_COMMAND = "codex"
CODEX_SERVICE_TIER_FALLBACK = "fast"
CODEX_SUPPORTED_SERVICE_TIERS = {"fast", "flex"}
_ACTIVE_PROVIDER_KEY = "ai_active_provider"
_ACTIVE_MODEL_KEY = "ai_active_model"


def _source_api_key_secret(provider: str) -> str:
    return f"ai_source_{provider}_api_key"


def _source_base_url_secret(provider: str) -> str:
    return f"ai_source_{provider}_base_url"

Message = dict[str, str]

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


@dataclass(frozen=True)
class ServerSubscriptionSpec:
    """One deployment-owned upstream that hosted AI / Hermes may use."""

    provider: str
    label: str
    website: str
    website_label: str
    base_url: str
    default_model: str
    models: tuple[str, ...]
    description: str


@dataclass(frozen=True)
class ServerGrokSubscriptionRuntime:
    """One deployment-owned model runtime shared by every product account."""

    provider: str
    model: str
    bearer_token: str
    base_url: str
    plan: str
    credential_source: str


CLOUD_SUBSCRIPTION_SPECS: tuple[ServerSubscriptionSpec, ...] = (
    ServerSubscriptionSpec(
        provider=XAI_PROVIDER,
        label="Grok",
        website="https://accounts.x.ai/",
        website_label="accounts.x.ai",
        base_url=XAI_API_BASE,
        default_model=XAI_DEFAULT_MODEL,
        models=("grok-4.5", "grok-4.5-latest", "grok-4.20", "grok-code-fast"),
        description="现有 SuperGrok / xAI 订阅。可用 OAuth 或服务器 API Key。",
    ),
    ServerSubscriptionSpec(
        provider=GAMESTORE_PROVIDER,
        label="86game",
        website="https://api.86gamestore.com/",
        website_label="api.86gamestore.com",
        base_url=GAMESTORE_API_BASE,
        default_model=GAMESTORE_DEFAULT_MODEL,
        models=GAMESTORE_MODELS,
        description="本机已有的 86gamestore OpenAI 兼容订阅。默认 gpt-5.6-sol。",
    ),
    ServerSubscriptionSpec(
        provider=SUBROUTER_PROVIDER,
        label="Subrouter",
        website="https://subrouter.ai/",
        website_label="subrouter.ai",
        base_url=SUBROUTER_API_BASE,
        default_model=SUBROUTER_DEFAULT_MODEL,
        models=SUBROUTER_MODELS,
        description="本机已有的 SubRouter 订阅。当前账户可见模型以 gpt-5.6-sol 为主。",
    ),
)
CLOUD_PROVIDER_IDS = {spec.provider for spec in CLOUD_SUBSCRIPTION_SPECS}


def _cloud_spec(provider: str | None) -> ServerSubscriptionSpec | None:
    value = (provider or "").strip()
    for spec in CLOUD_SUBSCRIPTION_SPECS:
        if spec.provider == value:
            return spec
    return None


def _cloud_env_key(provider: str) -> str:
    if provider == GAMESTORE_PROVIDER:
        return (settings.ai_86gamestore_api_key or "").strip()
    if provider == SUBROUTER_PROVIDER:
        return (settings.ai_subrouter_api_key or "").strip()
    return (settings.ai_api_key or "").strip()


def _cloud_key(provider: str) -> str:
    """Prefer admin-saved deployment key, then env/.env bootstrap key."""
    stored = str(
        secrets_store.load_deployment().get(_source_api_key_secret(provider)) or ""
    ).strip()
    if stored:
        return stored
    return _cloud_env_key(provider)


def _cloud_base_url(provider: str) -> str:
    spec = _cloud_spec(provider)
    default = spec.base_url if spec else ""
    stored = str(
        secrets_store.load_deployment().get(_source_base_url_secret(provider)) or ""
    ).strip()
    if stored:
        return normalize_openai_base_url(stored)
    return default


def _cloud_selection() -> dict[str, str]:
    stored = secrets_store.load_deployment()
    return {
        "provider": str(stored.get(_ACTIVE_PROVIDER_KEY) or "").strip(),
        "model": str(stored.get(_ACTIVE_MODEL_KEY) or "").strip(),
    }


def default_model_for_provider(provider: str | None) -> str:
    spec = _cloud_spec(provider)
    if spec:
        return spec.default_model
    return ""


def current_ai_provider() -> str:
    if is_cloud_subscription_mode():
        selected = _cloud_selection()["provider"]
        if selected in CLOUD_PROVIDER_IDS:
            return selected
        configured = (settings.ai_provider or "").strip()
        if configured in CLOUD_PROVIDER_IDS:
            return configured
        return XAI_PROVIDER
    return secrets_store.get_ai_config("ai_provider", settings.ai_provider) or OPENAI_COMPAT_PROVIDER


def current_ai_model() -> str:
    provider = current_ai_provider()
    if is_cloud_subscription_mode():
        selected_model = _cloud_selection()["model"]
        if selected_model:
            return selected_model
        model = (settings.ai_model or "").strip()
        return model or default_model_for_provider(provider)
    if provider == CODEX_CLI_PROVIDER:
        return normalize_codex_model(str(secrets_store.load().get("ai_model") or ""))
    model = secrets_store.get_ai_config("ai_model", settings.ai_model)
    if provider == XAI_PROVIDER and not (model or "").strip():
        return XAI_DEFAULT_MODEL
    return model


def current_codex_command() -> str:
    if is_cloud_subscription_mode():
        return CODEX_DEFAULT_COMMAND
    return normalize_codex_command(
        secrets_store.get_ai_config("ai_codex_command", settings.ai_codex_command),
        strict=False,
    )


def is_codex_cli_provider(provider: str | None = None) -> bool:
    return (provider or current_ai_provider()) == CODEX_CLI_PROVIDER


def is_xai_provider(provider: str | None = None) -> bool:
    return (provider or current_ai_provider()) == XAI_PROVIDER


def is_cloud_subscription_mode() -> bool:
    return (settings.ai_access_mode or "").strip().lower() == CLOUD_SUBSCRIPTION_MODE


def _cloud_provider_state(provider: str) -> dict[str, object]:
    spec = _cloud_spec(provider)
    model = current_ai_model() if provider == current_ai_provider() else (spec.default_model if spec else "")
    if spec is None:
        return {
            "ready": False,
            "credential_source": None,
            "message": "云端 AI 订阅当前不支持该供应商",
        }
    if provider == XAI_PROVIDER:
        from app.services import xai_oauth

        has_oauth = xai_oauth.has_oauth()
        has_api_key = bool(_cloud_key(provider))
        ready = bool((has_oauth or has_api_key) and model)
        if has_oauth:
            source = "server_oauth"
        elif has_api_key:
            source = "api_key"
        else:
            source = None
        return {
            "ready": ready,
            "credential_source": source,
            "message": "云端 Grok 已连接" if ready else "云端 Grok 服务尚未完成配置",
        }

    has_api_key = bool(_cloud_key(provider))
    ready = bool(has_api_key and (model or spec.default_model))
    return {
        "ready": ready,
        "credential_source": "api_key" if has_api_key else None,
        "message": (
            f"云端 {spec.label} 已连接" if ready else f"云端 {spec.label} 尚未配置服务器 Key"
        ),
    }


def list_server_subscriptions(*, include_secrets: bool = False) -> list[dict[str, object]]:
    """Catalog of hosted subscription sources. Keys stay masked or omitted."""
    active = current_ai_provider() if is_cloud_subscription_mode() else ""
    active_model = current_ai_model() if is_cloud_subscription_mode() else ""
    rows: list[dict[str, object]] = []
    for spec in CLOUD_SUBSCRIPTION_SPECS:
        state = _cloud_provider_state(spec.provider)
        key = _cloud_key(spec.provider)
        base_url = _cloud_base_url(spec.provider)
        row: dict[str, object] = {
            "provider": spec.provider,
            "label": spec.label,
            "website": spec.website,
            "website_label": spec.website_label,
            "description": spec.description,
            "base_url": base_url,
            "default_base_url": spec.base_url,
            "default_model": spec.default_model,
            "models": list(spec.models),
            "ready": bool(state["ready"]),
            "active": spec.provider == active,
            "model": active_model if spec.provider == active else spec.default_model,
            "credential_source": state["credential_source"],
            "message": state["message"],
            "has_api_key": bool(key),
        }
        if include_secrets:
            row["api_key_masked"] = secrets_store.mask(key) if key else ""
        rows.append(row)
    return rows


def select_server_subscription(provider: str, model: str = "") -> dict[str, object]:
    """Switch the deployment-owned hosted subscription. Keys stay server-owned."""
    if not is_cloud_subscription_mode():
        raise RuntimeError("当前不是云端订阅模式")
    spec = _cloud_spec(provider)
    if spec is None:
        raise ValueError("不支持的云端订阅源")
    chosen_model = (model or "").strip() or spec.default_model
    if spec.provider == XAI_PROVIDER:
        from app.services import xai_oauth

        if not (xai_oauth.has_oauth() or _cloud_key(spec.provider)):
            raise RuntimeError("云端 Grok 服务尚未完成配置")
    elif not _cloud_key(spec.provider):
        raise RuntimeError(f"云端 {spec.label} 尚未配置服务器 Key")
    base_url = _cloud_base_url(spec.provider)
    secrets_store.save_deployment({
        _ACTIVE_PROVIDER_KEY: spec.provider,
        _ACTIVE_MODEL_KEY: chosen_model,
    })
    settings.ai_provider = spec.provider
    settings.ai_model = chosen_model
    settings.ai_base_url = base_url
    return ai_access_status()


def save_server_subscription_source(
    provider: str,
    *,
    base_url: str = "",
    api_key: str | None = None,
    clear_api_key: bool = False,
) -> dict[str, object]:
    """Persist admin-managed URL/key for one hosted source. Never returns raw keys."""
    if not is_cloud_subscription_mode():
        raise RuntimeError("当前不是云端订阅模式")
    spec = _cloud_spec(provider)
    if spec is None:
        raise ValueError("不支持的云端订阅源")
    updates: dict[str, str] = {}
    url = (base_url or "").strip()
    if url:
        updates[_source_base_url_secret(spec.provider)] = normalize_openai_base_url(url)
    if clear_api_key:
        secrets_store.clear_deployment(_source_api_key_secret(spec.provider))
    elif api_key is not None:
        key = api_key.strip()
        if key:
            updates[_source_api_key_secret(spec.provider)] = key
    if updates:
        secrets_store.save_deployment(updates)
    if current_ai_provider() == spec.provider:
        settings.ai_base_url = _cloud_base_url(spec.provider)
    return {
        "ok": True,
        "provider": spec.provider,
        "base_url": _cloud_base_url(spec.provider),
        "has_api_key": bool(_cloud_key(spec.provider)),
        "api_key_masked": secrets_store.mask(_cloud_key(spec.provider)),
        "ai_subscriptions": list_server_subscriptions(include_secrets=True),
        "ai_access": ai_access_status(),
    }


def _resolve_cloud_provider_credentials(
    provider: str,
    *,
    api_key: str = "",
    base_url: str = "",
) -> tuple[str, str, ServerSubscriptionSpec]:
    """Return bearer token and base URL for one hosted source without switching it."""
    if not is_cloud_subscription_mode():
        raise RuntimeError("当前不是云端订阅模式")
    spec = _cloud_spec(provider)
    if spec is None:
        raise ValueError("不支持的云端订阅源")
    resolved_base = normalize_openai_base_url(base_url) if base_url.strip() else _cloud_base_url(provider)
    override_key = api_key.strip()
    if override_key:
        return override_key, resolved_base, spec
    if provider == XAI_PROVIDER:
        from app.services import xai_oauth

        if xai_oauth.has_oauth() and not override_key:
            token = xai_oauth.get_valid_access_token()
            if token:
                return token, resolved_base, spec
        key = _cloud_key(provider)
        if not key:
            raise RuntimeError("云端 Grok 尚未登录。请先在服务器网页完成授权或填写 API Key")
        return key, resolved_base, spec
    key = _cloud_key(provider)
    if not key:
        raise RuntimeError(f"云端 {spec.label} 尚未配置服务器 Key")
    return key, resolved_base, spec


async def probe_server_subscription(
    provider: str,
    model: str = "",
    *,
    api_key: str = "",
    base_url: str = "",
) -> dict[str, object]:
    """Probe one hosted source+model without changing the active selection."""
    resolved_key, resolved_base, spec = _resolve_cloud_provider_credentials(
        provider,
        api_key=api_key,
        base_url=base_url,
    )
    chosen_model = (model or "").strip() or spec.default_model
    client = _openai_client(resolved_key, 15.0, base_url=resolved_base)
    try:
        resp = await client.chat.completions.create(
            model=chosen_model,
            messages=[{"role": "user", "content": "Reply exactly: OK"}],
            temperature=0,
            max_tokens=8,
        )
    except Exception as exc:
        return {
            "ok": False,
            "provider": spec.provider,
            "label": spec.label,
            "model": chosen_model,
            "base_url": resolved_base,
            "error": str(exc)[:240],
        }
    text = ""
    if resp.choices:
        text = (resp.choices[0].message.content or "").strip()
    return {
        "ok": True,
        "provider": spec.provider,
        "label": spec.label,
        "model": chosen_model,
        "base_url": resolved_base,
        "response": text[:80],
    }


def ai_access_status() -> dict[str, object]:
    """Return the server-side AI entitlement and provider readiness contract.

    In cloud subscription mode the deployment itself is the entitlement
    boundary. One server-owned credential is shared by all authorized
    product accounts; clients and Hermes Profiles can consume it through
    server APIs but cannot read, replace, or select that credential.
    """
    provider = current_ai_provider()
    model = current_ai_model()

    if is_cloud_subscription_mode():
        spec = _cloud_spec(provider)
        entitled = bool(settings.ai_subscription_enabled)
        state = _cloud_provider_state(provider)
        provider_supported = spec is not None
        provider_ready = bool(state["ready"])
        allowed = entitled and provider_ready
        if not entitled:
            status_state = "subscription_required"
            message = "AI 订阅尚未开通"
        elif not provider_supported:
            status_state = "service_unavailable"
            message = "云端 AI 订阅当前不支持该供应商"
        elif not provider_ready:
            status_state = "service_unavailable"
            message = str(state["message"])
        else:
            status_state = "active"
            message = str(state["message"])
        plan = settings.ai_subscription_plan or "AI"
        if spec and spec.provider != XAI_PROVIDER:
            plan = spec.label
        return {
            "mode": CLOUD_SUBSCRIPTION_MODE,
            "state": status_state,
            "allowed": allowed,
            "entitled": entitled,
            "configured": provider_ready,
            "provider": provider,
            "model": model,
            "plan": plan,
            "message": message,
            "credential_source": state["credential_source"],
        }

    configured = _self_hosted_ai_configured(provider)
    return {
        "mode": "self_hosted",
        "state": "active" if configured else "not_configured",
        "allowed": configured,
        "entitled": True,
        "configured": configured,
        "provider": provider,
        "model": model,
        "plan": None,
        "message": "AI 已连接" if configured else "AI 未配置",
        "credential_source": None,
    }


def resolve_server_grok_subscription() -> ServerGrokSubscriptionRuntime:
    """Resolve the hosted upstream model runtime allowed for Hermes Profiles."""
    status = ai_access_status()
    if status.get("mode") != CLOUD_SUBSCRIPTION_MODE:
        raise RuntimeError("Hermes Agent 只允许使用服务器统一 Grok 订阅")
    provider = str(status.get("provider") or "")
    spec = _cloud_spec(provider)
    if spec is None:
        raise RuntimeError("服务器统一 AI 订阅当前不支持该供应商")
    if not status.get("allowed"):
        raise RuntimeError(str(status.get("message") or "服务器统一 AI 订阅当前不可用"))

    bearer_token, base_url = _resolve_openai_credentials()
    return ServerGrokSubscriptionRuntime(
        provider=spec.provider,
        model=str(status.get("model") or spec.default_model),
        bearer_token=bearer_token,
        base_url=base_url,
        plan=str(status.get("plan") or spec.label),
        credential_source=str(status.get("credential_source") or "server_managed"),
    )


def require_ai_access() -> None:
    status = ai_access_status()
    if status["allowed"]:
        return
    raise RuntimeError(str(status["message"]))


def normalize_codex_model(model: str) -> str:
    value = model.strip()
    aliases = {
        "gpt5": "gpt-5",
        "gpt5.5": "gpt-5.5",
    }
    return aliases.get(value.lower(), value)


def normalize_codex_command(command: str | None, *, strict: bool = True) -> str:
    value = (command or "").strip()
    if not value or value.lower() == CODEX_DEFAULT_COMMAND:
        return CODEX_DEFAULT_COMMAND
    if strict:
        raise ValueError("Codex CLI 仅支持使用默认 codex 命令自动解析, 不支持自定义可执行路径")
    return CODEX_DEFAULT_COMMAND


def normalize_openai_base_url(url: str) -> str:
    """Return the OpenAI-compatible base URL expected by the OpenAI SDK."""
    base = (url or "").strip().rstrip("/")
    if base.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")].rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return base


def codex_cli_available() -> bool:
    try:
        _codex_base_command()
        return True
    except RuntimeError:
        return False


def ai_configured(provider: str | None = None) -> bool:
    provider = provider or current_ai_provider()
    if is_cloud_subscription_mode():
        return bool(ai_access_status()["allowed"])
    return _self_hosted_ai_configured(provider)


def _self_hosted_ai_configured(provider: str) -> bool:
    if is_codex_cli_provider(provider):
        return codex_cli_available()
    if is_xai_provider(provider):
        from app.services import xai_oauth
        # SuperGrok OAuth 或粘贴的 xAI API Key 均可
        if xai_oauth.has_oauth():
            return True
        return bool(secrets_store.get_ai_key())
    return bool(secrets_store.get_ai_key())


async def generate_ai_text(
    messages: Sequence[Message],
    *,
    temperature: float = 0.3,
    max_tokens: int = 3000,
    timeout: float = 180.0,
) -> str:
    """Return a complete AI response from the currently configured provider."""
    require_ai_access()
    if is_codex_cli_provider():
        return await _run_codex_cli(messages, max_tokens=max_tokens, timeout=max(timeout, 600.0))
    return await _run_openai_once(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )


async def stream_ai_text(
    messages: Sequence[Message],
    *,
    temperature: float = 0.5,
    max_tokens: int = 4000,
    timeout: float = 180.0,
    prefer_final_answer: bool = False,
) -> AsyncIterator[str]:
    """Yield text deltas from the configured provider.

    Codex CLI only exposes the final assistant message for this use case, so it
    yields one complete chunk after the command exits.
    """
    require_ai_access()
    if is_codex_cli_provider():
        yield await _run_codex_cli(messages, max_tokens=max_tokens, timeout=max(timeout, 600.0))
        return

    async for chunk in _stream_openai(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        prefer_final_answer=prefer_final_answer,
    ):
        yield chunk


async def _run_openai_once(
    messages: Sequence[Message],
    *,
    temperature: float,
    max_tokens: int,
    timeout: float,
) -> str:
    api_key, base_url = _resolve_openai_credentials()
    client = _openai_client(api_key, timeout, base_url=base_url)
    resp = await client.chat.completions.create(
        model=current_ai_model(),
        messages=list(messages),
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if not resp.choices:
        return ""
    return (resp.choices[0].message.content or "").strip()


async def _stream_openai(
    messages: Sequence[Message],
    *,
    temperature: float,
    max_tokens: int,
    timeout: float,
    prefer_final_answer: bool,
) -> AsyncIterator[str]:
    api_key, base_url = _resolve_openai_credentials()
    client = _openai_client(api_key, timeout, base_url=base_url)
    stream = await client.chat.completions.create(
        model=current_ai_model(),
        messages=list(messages),
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield delta.content


def _resolve_openai_credentials() -> tuple[str, str]:
    """Return (api_key, base_url) for the active HTTP AI provider."""
    if is_cloud_subscription_mode():
        provider = current_ai_provider()
        spec = _cloud_spec(provider)
        if spec is None:
            raise RuntimeError("云端 AI 订阅当前不支持该供应商")
        base_url = _cloud_base_url(provider)
        if provider == XAI_PROVIDER:
            from app.services import xai_oauth

            if xai_oauth.has_oauth():
                token = xai_oauth.get_valid_access_token()
                if token:
                    return token, base_url
            key = _cloud_key(provider)
            if not key:
                raise RuntimeError("云端 Grok 尚未登录。请先在服务器网页完成授权")
            return key, base_url
        key = _cloud_key(provider)
        if not key:
            raise RuntimeError(f"云端 {spec.label} 尚未配置服务器 Key")
        return key, base_url

    if is_xai_provider():
        from app.services import xai_oauth
        token = xai_oauth.get_valid_access_token()
        if token:
            return token, XAI_API_BASE
        key = secrets_store.get_ai_key()
        if key:
            base = secrets_store.get_ai_config("ai_base_url", XAI_API_BASE) or XAI_API_BASE
            return key, base
        raise RuntimeError("xAI / Grok 未登录。请在设置页使用 SuperGrok 登录或粘贴 xAI API Key。")

    key = secrets_store.get_ai_key()
    if not key:
        raise RuntimeError("AI API Key 未配置, 请在设置页配置")
    base = secrets_store.get_ai_config("ai_base_url", settings.ai_base_url)
    return key, base


def _openai_client(api_key: str, timeout: float, *, base_url: str | None = None):
    from openai import AsyncOpenAI

    user_agent = secrets_store.get_ai_config("ai_user_agent", "") or settings.ai_user_agent
    return AsyncOpenAI(
        api_key=api_key,
        base_url=normalize_openai_base_url(base_url or secrets_store.get_ai_config("ai_base_url", settings.ai_base_url)),
        timeout=timeout,
        max_retries=2,
        default_headers={"User-Agent": user_agent},
    )


async def _run_codex_cli(
    messages: Sequence[Message],
    *,
    max_tokens: int,
    timeout: float,
) -> str:
    prompt = _codex_prompt(messages, max_tokens=max_tokens)
    with tempfile.TemporaryDirectory(prefix="tickflow-codex-run-") as run_dir:
        run_path = Path(run_dir)
        codex_home_path = run_path / "codex-home"
        workspace_path = run_path / "workspace"
        codex_home_path.mkdir()
        workspace_path.mkdir()
        output_path = codex_home_path / "last-message.txt"
        _prepare_codex_home(codex_home_path)

        args = [
            *_codex_base_command(),
            "exec",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--color",
            "never",
            "--output-last-message",
            str(output_path),
        ]
        model = current_ai_model().strip()
        if model:
            args.extend(["--model", model])
        args.extend(["--cd", str(workspace_path), "-"])

        env = os.environ.copy()
        env.setdefault("NO_COLOR", "1")
        env["CODEX_HOME"] = str(codex_home_path)

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(prompt.encode("utf-8")),
                timeout=timeout,
            )
        except TimeoutError as exc:
            proc.kill()
            await proc.wait()
            raise RuntimeError("Codex CLI 调用超时, 请稍后重试或检查本机 Codex 登录状态") from exc

        out = _clean_process_text(stdout)
        err = _clean_process_text(stderr)
        final_message = _read_output_file(output_path)
        if proc.returncode != 0:
            detail = err or out or f"exit code {proc.returncode}"
            raise RuntimeError(f"Codex CLI 调用失败: {detail[-1200:]}")
        result = final_message or out
        if not result:
            raise RuntimeError("Codex CLI 未返回内容")
        return result


def _codex_prompt(messages: Sequence[Message], *, max_tokens: int) -> str:
    parts = [
        "You are one-trading's local AI provider.",
        "This is a text-generation task. The working directory is intentionally empty.",
        "Use only the user-provided prompt content below; do not inspect or modify local files.",
        "Return only the final requested content; do not include execution logs.",
    ]
    if max_tokens > 0:
        parts.append(f"Keep the final answer within about {max_tokens} output tokens.")
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        parts.append(f"\n<{role}>\n{content}\n</{role}>")
    return "\n".join(parts)


def _codex_base_command() -> list[str]:
    command = current_codex_command()
    resolved = _resolve_command(command)
    if not resolved:
        raise RuntimeError(f"未找到 Codex CLI 命令: {command}")

    if sys.platform == "win32" and resolved.lower().endswith(".ps1"):
        return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", resolved]
    return [resolved]


def _resolve_command(command: str) -> str | None:
    if command.lower() != CODEX_DEFAULT_COMMAND:
        return None

    if sys.platform == "win32":
        desktop_codex = _resolve_windows_desktop_codex()
        if desktop_codex:
            return desktop_codex

    resolved = shutil.which(command)
    if sys.platform == "win32" and resolved:
        resolved_path = Path(resolved)
        if not resolved_path.suffix:
            cmd_path = resolved_path.with_suffix(".cmd")
            if cmd_path.exists():
                return str(cmd_path)
    if not resolved and sys.platform == "win32" and not command.lower().endswith(".cmd"):
        resolved = shutil.which(f"{command}.cmd")
    if not resolved and sys.platform == "win32":
        resolved = _resolve_windows_codex_command(command)
    return resolved


def _resolve_windows_codex_command(command: str) -> str | None:
    """Find npm-installed Codex when the backend process has a minimal PATH."""
    raw = Path(command)
    if raw.parent != Path("."):
        return None

    names = [command]
    if not raw.suffix:
        names = [f"{command}.cmd", f"{command}.exe", f"{command}.bat", f"{command}.ps1", command]

    dirs: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        dirs.append(Path(appdata) / "npm")
    dirs.append(Path.home() / "AppData" / "Roaming" / "npm")

    for env_name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        value = os.environ.get(env_name)
        if value:
            dirs.append(Path(value) / "nodejs")

    for directory in dirs:
        for name in names:
            candidate = directory / name
            if candidate.exists():
                return str(candidate)
    return None


def _resolve_windows_desktop_codex() -> str | None:
    """Prefer the Codex Desktop bundled CLI over an older npm shim."""
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        return None

    root = Path(local_appdata) / "OpenAI" / "Codex" / "bin"
    if not root.exists():
        return None

    candidates = list(root.glob("*/codex.exe"))
    direct = root / "codex.exe"
    if direct.exists():
        candidates.append(direct)
    if not candidates:
        return None

    newest = max(candidates, key=lambda p: p.stat().st_mtime)
    return str(newest)


def _prepare_codex_home(target: Path) -> None:
    """Create an isolated CODEX_HOME that reuses auth but not fragile config."""
    source = _codex_home()
    auth_file = source / "auth.json"
    if auth_file.exists():
        shutil.copy2(auth_file, target / "auth.json")
    _write_compatible_codex_config(target / "config.toml")


def _codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def _write_compatible_codex_config(path: Path) -> None:
    config = _read_codex_config()
    lines: list[str] = []

    tier = str(config.get("service_tier") or "").strip()
    if tier not in CODEX_SUPPORTED_SERVICE_TIERS:
        tier = CODEX_SERVICE_TIER_FALLBACK
    lines.append(_toml_string("service_tier", tier))
    lines.append(_toml_string("approval_policy", "never"))
    lines.append(_toml_string("sandbox_mode", "read-only"))

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_codex_config() -> dict:
    path = _codex_home() / "config.toml"
    if not path.exists():
        return {}
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError:
        return _read_codex_config_lenient(path)
    except OSError:
        return {}


def _read_codex_config_lenient(path: Path) -> dict:
    config: dict[str, str] = {}
    pattern = re.compile(r'^\s*([A-Za-z0-9_-]+)\s*=\s*"([^"]*)"\s*$')
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = pattern.match(line)
            if match:
                config[match.group(1)] = match.group(2)
    except OSError:
        pass
    return config


def _toml_string(key: str, value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'{key} = "{escaped}"'


def _clean_process_text(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace")
    return _ANSI_RE.sub("", text).strip()


def _read_output_file(path: Path) -> str:
    if path.exists():
        return _ANSI_RE.sub("", path.read_text(encoding="utf-8", errors="replace")).strip()
    return ""
