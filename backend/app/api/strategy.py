"""策略 API 路由 — HTTP 请求 → 调用策略模块 → 返回响应。

只做胶水，不含业务逻辑。
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.services.user_strategies import (
    DeclarativeStrategyGenerator,
    UserStrategyCatalog,
    UserStrategyError,
    UserStrategyWorkspace,
    definition_code,
    normalize_definition,
    resolve_strategy_owner,
)
from app.strategy import config as strategy_config
from app.strategy.ai_generator import AIStrategyGenerator
from app.strategy.engine import StrategyDef, StrategyEngine
from app.strategy.monitor import StrategyMonitorService

router = APIRouter(prefix="/api/strategies", tags=["strategies"])

# ── Helpers ──────────────────────────────────────────────────────────


def _get_engine(request: Request) -> StrategyEngine:
    engine = getattr(request.app.state, "strategy_engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="策略引擎未初始化")
    return engine


def _get_monitor(request: Request) -> StrategyMonitorService:
    mon = getattr(request.app.state, "strategy_monitor", None)
    if not mon:
        raise HTTPException(status_code=503, detail="策略监控未初始化")
    return mon


def _data_dir(request: Request) -> Path:
    return request.app.state.repo.store.data_dir


def _validate_strategy_id(strategy_id: str) -> str:
    sid = (strategy_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", sid):
        raise ValueError("strategy_id 仅允许字母、数字、下划线、短横线")
    return sid


def _target_dir(data_dir: Path, source: str) -> Path:
    if source not in {"ai", "custom", "composite"}:
        raise ValueError("target_source 必须是 ai、custom 或 composite")
    return data_dir / "strategies" / source


def _insert_meta_field(block: str, field: str, value_repr: str) -> str:
    lines = block.splitlines(keepends=True)
    key_indent = None
    for line in lines:
        match = re.match(r"^(\s*)[\"'][^\"']+[\"']\s*:", line)
        if match:
            key_indent = match.group(1)
            break
    if key_indent is None:
        first_indent = re.match(r"^(\s*)", lines[0] if lines else "")
        key_indent = (first_indent.group(1) if first_indent else "") + "    "
    insert_at = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].lstrip().startswith("}"):
            insert_at = i
            break
    for i in range(insert_at - 1, -1, -1):
        if not lines[i].strip():
            continue
        body = lines[i].rstrip("\r\n")
        if body.rstrip() and not body.rstrip().endswith((",", "{")):
            newline = lines[i][len(body):]
            lines[i] = body.rstrip() + "," + newline
        break
    lines.insert(insert_at, f'{key_indent}"{field}": {value_repr},\n')
    return "".join(lines)


def _meta_block_span(code: str) -> tuple[int, int]:
    match = re.search(r"META\s*=\s*\{", code)
    if match is None:
        raise ValueError("找不到 META 字典")
    start = match.start()
    brace_at = code.find("{", match.start())
    depth = 0
    for index in range(brace_at, len(code)):
        char = code[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return start, index + 1
    raise ValueError("找不到 META 字典")


def _set_meta_bool_field(code: str, field: str, value: bool) -> str:
    """Set a META bool without executing code: replace if present, else insert."""
    value_repr = "True" if value else "False"
    start, end = _meta_block_span(code)
    block = code[start:end]
    key_pattern = re.compile(
        rf"(?m)^(\s*[\"']{re.escape(field)}[\"']\s*:\s*)(?:True|False|[\"'][^\"'\n]*[\"'])"
    )
    if key_pattern.search(block):
        next_block = key_pattern.sub(lambda match: f"{match.group(1)}{value_repr}", block, count=1)
    else:
        next_block = _insert_meta_field(block, field, value_repr)
    return code[:start] + next_block + code[end:]


def _set_meta_id(code: str, strategy_id: str) -> str:
    start, end = _meta_block_span(code)
    block = code[start:end]
    next_block = re.sub(
        r'(?m)^(\s*[\"\']id[\"\']\s*:\s*)[\"\'][^\"\']*[\"\']',
        lambda match: f'{match.group(1)}"{strategy_id}"',
        block,
        count=1,
    )
    return code[:start] + next_block + code[end:]


def _restore_strategy_file(path: Path, previous_code: str | None) -> None:
    if previous_code is None:
        path.unlink(missing_ok=True)
    else:
        path.write_text(previous_code, encoding="utf-8")


def _save_strategy_code(req: StrategyCodeSaveRequest, request: Request, *, legacy_ai_path: bool = False) -> dict:
    sid = _validate_strategy_id(req.strategy_id)
    engine = _get_engine(request)
    data_dir = _data_dir(request)
    existing: StrategyDef | None = None
    try:
        existing = engine.get(sid)
    except ValueError:
        existing = None

    if legacy_ai_path:
        out_dir = _target_dir(data_dir, "ai")
        path = out_dir / f"{sid}.py"
        expected_source = "ai"
    elif req.mode == "update":
        if existing is None:
            raise ValueError(f"策略 {sid} 不存在")
        if existing.source == "builtin":
            raise ValueError("内置策略不可覆盖，请另存为自定义策略")
        path = existing.file_path
        expected_source = existing.source
    else:
        if existing is not None:
            raise ValueError(f"策略 {sid} 已存在，请改用修改模式或换一个策略 ID")
        source_dir = req.target_source
        out_dir = _target_dir(data_dir, source_dir)
        path = out_dir / f"{sid}.py"
        expected_source = source_dir

    if path is None:
        raise ValueError("策略源文件路径无效")
    path.parent.mkdir(parents=True, exist_ok=True)
    code = _set_meta_id(req.code, sid)
    if expected_source == "ai" and (legacy_ai_path or req.mode == "create"):
        code = _set_meta_bool_field(code, "research_only", True)
    meta = AIStrategyGenerator._extract_meta(code)
    previous_code = path.read_text(encoding="utf-8") if path.exists() else None
    path.write_text(code, encoding="utf-8")
    try:
        engine.reload()
        loaded = engine.get(sid)
        if loaded.source != expected_source:
            raise ValueError(f"策略来源异常: 期望 {expected_source}, 实际 {loaded.source}")
    except Exception as exc:
        _restore_strategy_file(path, previous_code)
        engine.reload()
        raise ValueError(f"策略保存失败: {exc}") from exc
    _invalidate_strategy_runtime(request)
    return {
        "ok": True,
        "strategy_id": sid,
        "source": expected_source,
        "path": str(path),
        "meta": meta,
        "research_only": meta.get("research_only", False),
    }


def _invalidate_strategy_runtime(request: Request) -> None:
    from app.services import strategy_cache

    strategy_cache.clear_cache(_data_dir(request))
    monitor_engine = getattr(request.app.state, "monitor_engine", None)
    if monitor_engine is not None:
        monitor_engine.invalidate_strategy_state()


def _resolve_owner(request: Request, owner_user_id: str | None = None) -> dict:
    try:
        return resolve_strategy_owner(
            getattr(request.state, "user", None),
            owner_user_id,
        )
    except UserStrategyError as exc:
        raise _translate_user_strategy_error(exc) from exc


def _workspace(request: Request, owner_user_id: str | None = None) -> UserStrategyWorkspace:
    owner = _resolve_owner(request, owner_user_id)
    return UserStrategyWorkspace(_data_dir(request), owner)


def _catalog(request: Request, owner_user_id: str | None = None) -> UserStrategyCatalog:
    actor = getattr(request.state, "user", {})
    owner = _resolve_owner(request, owner_user_id)
    include_global_custom = actor.get("role") == "admin" and owner.get("id") == actor.get("id")
    return UserStrategyCatalog(
        _get_engine(request),
        UserStrategyWorkspace(_data_dir(request), owner),
        include_global_custom=include_global_custom,
    )


def _translate_user_strategy_error(exc: UserStrategyError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _safe(result_dict: dict) -> dict:
    rows = result_dict.get("rows", [])
    for r in rows:
        for k, v in list(r.items()):
            if isinstance(v, float) and not math.isfinite(v):
                r[k] = None
    return result_dict


def _strategy_detail(
    s: StrategyDef,
    overrides: dict | None = None,
    *,
    owner_user_id: str | None = None,
) -> dict:
    """策略详情（含用户覆盖）"""
    bf = {**s.basic_filter}
    scoring = dict(s.meta.get("scoring", {}))
    params_defaults = {p["id"]: p["default"] for p in s.meta.get("params", [])}

    if overrides:
        if overrides.get("basic_filter"):
            bf.update(overrides["basic_filter"])
        if overrides.get("scoring"):
            scoring.update(overrides["scoring"])
        # 用户保存的参数覆盖默认值: 合并进 params_defaults, 前端据此回显
        if overrides.get("params"):
            params_defaults.update(overrides["params"])

    # 名称/描述可被用户覆盖
    name = overrides.get("name", s.meta.get("name", "")) if overrides else s.meta.get("name", "")
    description = overrides.get("description", s.meta.get("description", "")) if overrides else s.meta.get("description", "")

    return {
        "id": s.meta["id"],
        "name": name or s.meta.get("name", ""),
        "description": description or s.meta.get("description", ""),
        "tags": s.meta.get("tags", []),
        "source": s.source,
        "version": s.meta.get("version", "1.0.0"),
        "basic_filter": bf,
        "params": s.meta.get("params", []),
        "params_defaults": params_defaults,
        "scoring": scoring,
        "entry_signals": s.entry_signals,
        "exit_signals": s.exit_signals,
        "stop_loss": overrides.get("stop_loss", s.stop_loss) if overrides else s.stop_loss,
        "take_profit": getattr(s, "take_profit", None),
        "trailing_stop": getattr(s, "trailing_stop", None),
        "trailing_take_profit_activate": getattr(s, "trailing_take_profit_activate", None),
        "trailing_take_profit_drawdown": getattr(s, "trailing_take_profit_drawdown", None),
        "max_hold_days": overrides.get("max_hold_days", s.max_hold_days) if overrides else s.max_hold_days,
        "alerts": s.alerts,
        "order_by": s.meta.get("order_by", "score"),
        "descending": s.meta.get("descending", True),
        "limit": s.meta.get("limit", 30),
        "display_limit": overrides.get("display_limit") if overrides and "display_limit" in overrides else None,
        "rules": s.meta.get("rules", ""),
        "owner_user_id": owner_user_id,
    }


# ── Request Models ───────────────────────────────────────────────────


class RunRequest(BaseModel):
    strategy_id: str
    owner_user_id: str | None = None
    as_of: date | None = None
    pool: list[str] | None = None
    params: dict | None = None


class RunAllRequest(BaseModel):
    as_of: date | None = None


class SaveConfigRequest(BaseModel):
    strategy_id: str
    overrides: dict


class AIGenerateRequest(BaseModel):
    prompt: str


class AISaveRequest(BaseModel):
    code: str
    strategy_id: str


class StrategyCodeSaveRequest(BaseModel):
    code: str
    strategy_id: str
    target_source: Literal["ai", "custom"] = "custom"
    mode: Literal["create", "update"] = "create"
    name: str = ""
    description: str = ""


class MonitorStartRequest(BaseModel):
    strategy_id: str


# ── 列表 / 详情 ─────────────────────────────────────────────────────


@router.get("")
def list_strategies(request: Request, owner_user_id: str | None = None):
    engine = _catalog(request, owner_user_id)
    owner = _resolve_owner(request, owner_user_id)
    actor = getattr(request.state, "user", {})
    data_dir = _data_dir(request)
    all_overrides = (
        strategy_config.list_overrides(data_dir)
        if owner.get("id") == actor.get("id")
        else {}
    )

    result = []
    for meta in engine.list_strategies():
        sid = meta["id"]
        s = engine.get(sid)
        overrides = all_overrides.get(sid)
        result.append(_strategy_detail(s, overrides, owner_user_id=str(owner["id"])))
    return {"strategies": result, "owner_user_id": owner["id"]}


@router.get("/{strategy_id}")
def get_strategy(
    strategy_id: str,
    request: Request,
    owner_user_id: str | None = None,
):
    engine = _catalog(request, owner_user_id)
    owner = _resolve_owner(request, owner_user_id)
    actor = getattr(request.state, "user", {})
    try:
        s = engine.get(strategy_id)
    except (ValueError, UserStrategyError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    overrides = (
        strategy_config.load_override(_data_dir(request), strategy_id)
        if owner.get("id") == actor.get("id")
        else {}
    )
    return _strategy_detail(
        s,
        overrides or None,
        owner_user_id=str(owner["id"]),
    )


# ── 执行选股 ─────────────────────────────────────────────────────────


@router.post("/run")
def run_strategy(req: RunRequest, request: Request):
    engine = _catalog(request, req.owner_user_id)
    owner = _resolve_owner(request, req.owner_user_id)
    actor = getattr(request.state, "user", {})
    data_dir = _data_dir(request)

    # 读取用户覆盖配置
    overrides = (
        strategy_config.load_override(data_dir, req.strategy_id)
        if owner.get("id") == actor.get("id")
        else {}
    )
    params = req.params or {}
    # 合并用户保存的策略参数
    if overrides.get("params"):
        merged = dict(overrides["params"])
        merged.update(params)  # 请求里的优先
        params = merged

    # 确定日期
    as_of = req.as_of
    if not as_of:
        from app.services.screener import ScreenerService
        svc = ScreenerService(request.app.state.repo)
        as_of = svc.latest_date()
    if not as_of:
        raise HTTPException(status_code=400, detail="无可用数据日期")

    try:
        result = engine.run(
            req.strategy_id, as_of,
            pool=req.pool,
            params=params,
            overrides=overrides or None,
        )
    except (ValueError, UserStrategyError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return _safe(asdict(result))


@router.post("/run-all")
def run_all(req: RunAllRequest, request: Request):
    engine = _catalog(request)
    data_dir = _data_dir(request)

    as_of = req.as_of
    if not as_of:
        from app.services.screener import ScreenerService
        svc = ScreenerService(request.app.state.repo)
        as_of = svc.latest_date()
    if not as_of:
        return {"as_of": None, "results": {}}

    all_overrides = strategy_config.list_overrides(data_dir)
    results: dict[str, dict] = {}
    for sid, result in engine.run_all(as_of, overrides_map=all_overrides).items():
        results[sid] = {"total": result.total, "as_of": str(as_of)}

    return {"as_of": str(as_of), "results": results}


# ── 配置持久化 ───────────────────────────────────────────────────────


@router.post("/config")
def save_config(req: SaveConfigRequest, request: Request):
    engine = _catalog(request)
    if not engine.has(req.strategy_id):
        raise HTTPException(status_code=404, detail=f"策略 {req.strategy_id} 不存在")

    # 剥离与策略默认值相同的字段，只保存用户真正修改过的值
    overrides = _strip_defaults(req.strategy_id, req.overrides, engine)

    strategy_config.save_override(_data_dir(request), req.strategy_id, overrides)
    return {"ok": True}


def _strip_defaults(strategy_id: str, overrides: dict, engine) -> dict:
    """剥离与策略默认值相同的字段，避免默认值被固化到 override 中。

    核心问题: 前端把策略的默认 basic_filter 全量发回后端保存，
    导致隐含的默认过滤条件 (如 market_cap_min, amount_min) 被写入 override 文件。
    即使前端 UI 不展示这些字段，它们仍会在策略运行时生效。
    """
    s = engine.get(strategy_id)
    result = dict(overrides)

    # 处理 basic_filter: 只保留与策略默认值不同的键
    bf = result.get("basic_filter")
    if bf and isinstance(bf, dict):
        default_bf = s.basic_filter if s else {}
        stripped_bf = {}
        for k, v in bf.items():
            default_val = default_bf.get(k)
            # 保留与默认值不同的键，以及没有默认值的键
            if k not in default_bf or v != default_val:
                stripped_bf[k] = v
        if stripped_bf:
            result["basic_filter"] = stripped_bf
        else:
            del result["basic_filter"]

    return result


@router.delete("/config/{strategy_id}")
def reset_config(strategy_id: str, request: Request):
    strategy_config.delete_override(_data_dir(request), strategy_id)
    return {"ok": True}


# ── AI 生成 ───────────────────────────────────────────────────────────

class BuildRequest(BaseModel):
    """两步策略构建请求"""
    step: int  # 1 / 2
    # step1 字段
    name: str = ""
    description: str = ""
    direction: str = "long"
    rules: str = ""
    strategy_id: str = ""
    # step2 字段
    current_code: str = ""
    instruction: str = ""


@router.get("/ai/status")
def ai_status(request: Request):
    """Check whether the selected AI provider is configured."""
    from app import secrets_store
    from app.config import settings
    from app.services.ai_provider import (
        ai_access_status,
        ai_configured,
        current_ai_model,
        current_ai_provider,
        is_cloud_subscription_mode,
    )

    has_key = bool(settings.ai_api_key) if is_cloud_subscription_mode() else bool(secrets_store.get_ai_key())
    model = current_ai_model()
    provider = current_ai_provider()
    access = ai_access_status()
    return {
        "configured": ai_configured(provider) and bool(model or provider == "codex_cli"),
        "has_key": has_key,
        "has_model": bool(model),
        "provider": provider,
        "access_state": access["state"],
        "message": access["message"],
    }


@router.get("/{strategy_id}/source")
def get_strategy_source(
    strategy_id: str,
    request: Request,
    owner_user_id: str | None = None,
):
    """Return safe JSON for user strategies or legacy source for the owner."""
    workspace = _workspace(request, owner_user_id)
    if workspace.has(strategy_id):
        definition = workspace.get_definition(strategy_id)
        return {"code": definition_code(definition), "source": definition["source"]}

    engine = _catalog(request, owner_user_id)
    try:
        s = engine.get(strategy_id)
    except (ValueError, UserStrategyError) as exc:
        raise HTTPException(status_code=404, detail=f"策略 {strategy_id} 不存在") from exc

    path = s.file_path
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="策略源文件不存在")

    return {"code": path.read_text(encoding="utf-8"), "source": s.source}


@router.post("/ai/test")
async def ai_test(request: Request):
    """Send a small prompt through the selected AI provider."""
    from app.api.ai_guard import require_ai_http_access
    from app.services.ai_provider import current_ai_model, current_ai_provider, generate_ai_text

    require_ai_http_access()
    try:
        text = await generate_ai_text(
            [{"role": "user", "content": "Reply exactly: OK"}],
            temperature=0,
            max_tokens=8,
            timeout=15,
        )
        return {"ok": True, "model": current_ai_model() or current_ai_provider(), "response": text[:80]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/build")
async def build_strategy(req: BuildRequest, request: Request):
    """Build or modify a strictly declarative, non-executable strategy."""
    from app.api.ai_guard import require_ai_http_access
    require_ai_http_access()
    generator = DeclarativeStrategyGenerator()
    try:
        if req.step == 1:
            instruction = (
                f"创建策略。策略 ID 必须是 {req.strategy_id}；名称：{req.name}；"
                f"描述：{req.description}；方向：{req.direction}；用户规则：{req.rules}。"
            )
            raw = await generator.generate(instruction)
            raw.update(
                {
                    "id": req.strategy_id,
                    "name": req.name,
                    "direction": req.direction,
                    "rules": req.rules,
                    "source": "ai",
                }
            )
            if req.description.strip():
                raw["description"] = req.description
            definition = normalize_definition(raw)
        elif req.step == 2:
            try:
                current_definition = normalize_definition(json.loads(req.current_code))
            except (json.JSONDecodeError, UserStrategyError) as exc:
                raise UserStrategyError("当前策略不是有效的安全 JSON 定义", status_code=422) from exc
            instruction = (
                "修改下面的安全策略 JSON。必须保留原 id，不得输出代码。\n"
                f"当前定义：{definition_code(current_definition)}\n"
                f"修改要求：{req.instruction}"
            )
            raw = await generator.generate(instruction)
            raw["id"] = current_definition["id"]
            raw["source"] = current_definition["source"]
            definition = normalize_definition(raw, previous=current_definition)
        else:
            raise UserStrategyError(f"无效步骤: {req.step}", status_code=400)
    except UserStrategyError as exc:
        raise _translate_user_strategy_error(exc) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "code": definition_code(definition),
        "meta": definition,
        "valid": True,
        "error": None,
    }



@router.post("/ai/generate")
async def ai_generate(req: AIGenerateRequest, request: Request):
    from app.api.ai_guard import require_ai_http_access
    require_ai_http_access()
    try:
        gen = AIStrategyGenerator()
        result = await gen.generate(req.prompt)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI生成失败: {e}") from e
    return result


@router.post("/ai/save")
async def ai_save(req: AISaveRequest, request: Request):
    try:
        definition = _workspace(request).save_code(req.code, expected_id=req.strategy_id)
    except UserStrategyError as exc:
        raise _translate_user_strategy_error(exc) from exc
    return {
        "ok": True,
        "strategy": definition,
        "path": f"user_data/strategies/{definition['id']}.json",
    }


@router.delete("/user/{strategy_id}")
def delete_user_strategy(strategy_id: str, request: Request):
    """Delete only the current account's declarative strategy."""
    try:
        _workspace(request).delete(strategy_id)
    except UserStrategyError as exc:
        raise _translate_user_strategy_error(exc) from exc
    strategy_config.delete_override(_data_dir(request), strategy_id)
    return {"ok": True}


def _publish_path_allowed(path: Path, data_dir: Path, owner: dict) -> bool:
    """Shared engine files or the resolved owner's workspace may be published."""
    from app.services.user_context import user_data_dir_for

    resolved = path.resolve()
    roots = [
        user_data_dir_for(owner, data_dir, create=False).resolve(),
        (data_dir / "strategies").resolve(),
        (data_dir / "user_data" / "strategies").resolve(),
    ]
    for root in roots:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


@router.post("/{strategy_id}/publish")
def publish_ai_strategy(strategy_id: str, request: Request, owner_user_id: str | None = None):
    """把 research_only 的 AI 草稿策略翻转为公开(research_only=False)。

    门 = 人的显式动作: 只有 AI 来源且仍处于草稿态的策略才能被发布。
    发布后即进入公开列表、可 run、可监控。文件写入必须落在当前 owner 工作区
    或共享 strategies 目录, 禁止跨用户改写。
    """
    sid = _validate_strategy_id(strategy_id)
    actor = getattr(getattr(request, "state", None), "user", None)
    if isinstance(actor, dict) and actor.get("id"):
        owner = _resolve_owner(request, owner_user_id)
        workspace = UserStrategyWorkspace(_data_dir(request), owner)
        if workspace.has(sid):
            definition = workspace.get_definition(sid)
            if definition.get("source") != "ai":
                raise HTTPException(status_code=400, detail="仅 AI 策略可经发布端点上线")
            if not definition.get("research_only"):
                raise HTTPException(status_code=400, detail="该策略已是公开状态")
            definition["research_only"] = False
            workspace.save(definition)
            _invalidate_strategy_runtime(request)
            return {"ok": True, "strategy_id": sid}
    else:
        from app.services.user_context import current
        owner = current()

    engine = _get_engine(request)
    try:
        s = engine.get(sid)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=f"策略 {sid} 不存在") from e

    if s.source != "ai":
        raise HTTPException(status_code=400, detail="仅 AI 策略可经发布端点上线")
    if not s.meta.get("research_only"):
        raise HTTPException(status_code=400, detail="该策略已是公开状态")

    path = s.file_path
    if path is None:
        raise HTTPException(status_code=400, detail="策略源文件路径无效, 无法发布")
    if not _publish_path_allowed(path, _data_dir(request), owner):
        raise HTTPException(status_code=403, detail="无权发布其他用户的策略")
    previous_code = path.read_text(encoding="utf-8")
    path.write_text(_set_meta_bool_field(previous_code, "research_only", False), encoding="utf-8")

    try:
        engine.reload()
        loaded = engine.get(sid)
        if loaded.meta.get("research_only"):
            raise ValueError("发布后策略仍为草稿态")
    except Exception as e:
        _restore_strategy_file(path, previous_code)
        engine.reload()
        raise HTTPException(status_code=500, detail=f"策略发布失败: {e}") from e

    _invalidate_strategy_runtime(request)
    return {"ok": True, "strategy_id": sid}


@router.delete("/{strategy_id}")
def delete_strategy(strategy_id: str, request: Request):
    """删除自定义策略 — 清除 .py 文件 + overrides + 热重载。内置策略不可删除。"""

    engine = _get_engine(request)
    try:
        s = engine.get(strategy_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=f"策略 {strategy_id} 不存在") from exc

    if s.source == "builtin":
        raise HTTPException(status_code=403, detail="内置策略不可删除")

    # 删除策略文件
    if s.file_path and s.file_path.exists():
        s.file_path.unlink()

    # 删除 overrides
    data_dir = _data_dir(request)
    from app.services.user_context import user_data_dir
    override_path = user_data_dir(data_dir) / "strategy_overrides" / f"{strategy_id}.json"
    if override_path.exists():
        override_path.unlink()

    # 热重载
    engine.reload()
    return {"ok": True}


# ── 监控 ─────────────────────────────────────────────────────────────
# 注: 策略监控已统一迁移到 MonitorRuleEngine (监控通知页), 旧的 start/stop/status
# 路由已移除。StrategyMonitorService 类保留 (其 _check_signals 被 MonitorRuleEngine 复用)。


# ── 热重载 ───────────────────────────────────────────────────────────


@router.post("/reload")
def reload_strategies(request: Request):
    engine = _get_engine(request)
    engine.reload()
    return {"ok": True, "count": len(engine.list_strategies())}


class CompositeChildIn(BaseModel):
    strategy_id: str
    weight: float = 1.0


class StrategyCompositeSaveRequest(BaseModel):
    strategy_id: str
    name: str = ""
    description: str = ""
    children: list[CompositeChildIn] = []
    merge_mode: str = "union"
    min_confirm: int = 0
    mode: str = "create"


@router.post("/composite/save")
def save_composite_strategy(req: StrategyCompositeSaveRequest, request: Request):
    """Save a declarative composite strategy into the current account workspace."""
    from app.strategy.composite import merge_results  # noqa: F401  — import proves module present
    if not req.children:
        raise HTTPException(400, "叠加策略至少需要一个子策略")
    sid = req.strategy_id.strip() or "composite_strategy"
    if not sid.startswith("composite_"):
        sid = f"composite_{sid}"
    payload = {
        "id": sid,
        "name": req.name or sid,
        "description": req.description,
        "source": "custom",
        "execution_backend": "composite",
        "children": [{"strategy_id": c.strategy_id, "weight": c.weight} for c in req.children],
        "params": {
            "merge_mode": req.merge_mode,
            "min_confirm": req.min_confirm,
        },
    }
    try:
        saved = _workspace(request).save(payload)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "id": saved.get("id", sid), "strategy_id": saved.get("id", sid), "strategy": saved}

