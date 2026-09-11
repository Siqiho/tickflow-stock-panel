"""Safe, account-owned strategy definitions over the shared market dataset.

The Module owns the complete user-strategy lifecycle: validation, atomic JSON
storage, compilation to a ``StrategyDef`` and a read/run catalog that can be
handed to the existing screener and backtest engines.  User input never becomes
Python source and is never imported or evaluated.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from app.indicators.pipeline import ENRICHED_COLUMNS
from app.services.atomic_io import atomic_write_json
from app.services.user_context import current, user_data_dir_for
from app.strategy.custom_signals import ALLOWED_FIELDS, OPS, _parse_right
from app.strategy.engine import DEFAULT_BASIC_FILTER, StrategyDef, StrategyEngine

_ID_RE = re.compile(r"^(?:ai|custom)_[a-z0-9_]{1,32}$")
_SIGNAL_RE = re.compile(r"^signal_[a-z0-9_]{1,56}$")
_SAFE_SIGNALS = frozenset(
    field for field in ENRICHED_COLUMNS if field.startswith("signal_")
)
_SAFE_BOARDS = frozenset({"沪主板", "深主板", "创业板", "科创板", "北交所"})
_NUMERIC_FILTERS = frozenset(
    {
        "price_min",
        "price_max",
        "market_cap_min",
        "market_cap_max",
        "float_cap_min",
        "float_cap_max",
        "amount_min",
        "amount_max",
        "turnover_min",
        "turnover_max",
    }
)
_BOOL_FILTERS = frozenset({"enabled", "exclude_st"})
_MAX_DEFINITIONS = 100


class UserStrategyError(RuntimeError):
    """Stable validation/storage failure at the user strategy seam."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def resolve_strategy_owner(
    actor: dict[str, Any] | None,
    owner_user_id: str | None = None,
) -> dict[str, Any]:
    """Authorize and resolve the owner whose strategy workspace is requested."""
    if not isinstance(actor, dict) or not actor.get("id"):
        raise UserStrategyError("策略操作缺少用户身份", status_code=401)
    target_id = str(owner_user_id or actor["id"]).strip()
    if target_id == actor["id"]:
        return actor
    if actor.get("role") != "admin":
        raise UserStrategyError("无权访问其他用户的策略", status_code=403)
    from app.services import auth

    target = auth.user_by_id(target_id)
    if target is None or target.get("role") != "user":
        raise UserStrategyError("目标普通用户不存在或已停用", status_code=404)
    return target


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _text(value: Any, *, field: str, maximum: int, required: bool = False) -> str:
    normalized = " ".join(str(value or "").split())
    if required and not normalized:
        raise UserStrategyError(f"{field} 不能为空", status_code=422)
    if len(normalized) > maximum:
        raise UserStrategyError(f"{field} 不能超过 {maximum} 个字符", status_code=422)
    return normalized


def _number(
    value: Any,
    *,
    field: str,
    minimum: float,
    maximum: float,
    allow_none: bool = True,
) -> float | None:
    if value is None or value == "":
        if allow_none:
            return None
        raise UserStrategyError(f"{field} 不能为空", status_code=422)
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise UserStrategyError(f"{field} 必须是数字", status_code=422) from exc
    if not minimum <= parsed <= maximum:
        raise UserStrategyError(
            f"{field} 必须在 {minimum:g} 到 {maximum:g} 之间",
            status_code=422,
        )
    return parsed


def _normalize_conditions(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise UserStrategyError("conditions 至少需要一条安全条件", status_code=422)
    if len(value) > 12:
        raise UserStrategyError("conditions 最多 12 条", status_code=422)
    conditions: list[dict[str, Any]] = []
    for index, raw in enumerate(value, start=1):
        if not isinstance(raw, dict):
            raise UserStrategyError(f"第 {index} 条条件格式错误", status_code=422)
        left = str(raw.get("left") or "")
        op = str(raw.get("op") or "")
        right = raw.get("right")
        if left not in ALLOWED_FIELDS:
            raise UserStrategyError(f"第 {index} 条条件字段不受支持: {left}", status_code=422)
        if op not in OPS:
            raise UserStrategyError(f"第 {index} 条条件运算符不受支持: {op}", status_code=422)
        try:
            kind, parsed = _parse_right(right)
        except ValueError as exc:
            raise UserStrategyError(str(exc), status_code=422) from exc
        safe_right: str | float = f"field:{parsed}" if kind == "field" else float(parsed)
        conditions.append({"left": left, "op": op, "right": safe_right})
    return conditions


def _normalize_signals(value: Any, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 8:
        raise UserStrategyError(f"{field} 必须是最多 8 项的列表", status_code=422)
    result: list[str] = []
    for raw in value:
        signal = str(raw or "").strip()
        if not _SIGNAL_RE.fullmatch(signal) or signal not in _SAFE_SIGNALS:
            raise UserStrategyError(f"{field} 包含不受支持的信号: {signal}", status_code=422)
        if signal not in result:
            result.append(signal)
    return result


def _normalize_basic_filter(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    unknown = set(raw) - _NUMERIC_FILTERS - _BOOL_FILTERS - {"exclude_new_days", "boards"}
    if unknown:
        raise UserStrategyError(
            f"basic_filter 包含不受支持的字段: {', '.join(sorted(unknown))}",
            status_code=422,
        )
    result = dict(DEFAULT_BASIC_FILTER)
    for key in _NUMERIC_FILTERS:
        if key in raw:
            result[key] = _number(
                raw[key],
                field=f"basic_filter.{key}",
                minimum=0,
                maximum=1e15,
            )
    for key in _BOOL_FILTERS:
        if key in raw:
            if not isinstance(raw[key], bool):
                raise UserStrategyError(f"basic_filter.{key} 必须是布尔值", status_code=422)
            result[key] = raw[key]
    if "exclude_new_days" in raw:
        days = _number(
            raw["exclude_new_days"],
            field="basic_filter.exclude_new_days",
            minimum=0,
            maximum=3650,
            allow_none=False,
        )
        result["exclude_new_days"] = int(days or 0)
    if "boards" in raw:
        boards = raw["boards"]
        if not isinstance(boards, list) or any(board not in _SAFE_BOARDS for board in boards):
            raise UserStrategyError("basic_filter.boards 包含不受支持的板块", status_code=422)
        result["boards"] = list(dict.fromkeys(boards))
    return result


def _normalize_scoring(value: Any) -> dict[str, float]:
    raw = value if isinstance(value, dict) else {}
    if len(raw) > 8:
        raise UserStrategyError("scoring 最多支持 8 个字段", status_code=422)
    scoring: dict[str, float] = {}
    for field, weight in raw.items():
        if field not in ALLOWED_FIELDS:
            raise UserStrategyError(f"scoring 字段不受支持: {field}", status_code=422)
        parsed = _number(
            weight,
            field=f"scoring.{field}",
            minimum=0,
            maximum=100,
            allow_none=False,
        )
        if parsed and parsed > 0:
            scoring[field] = parsed
    if not scoring:
        scoring = {"change_pct": 1.0}
    total = sum(scoring.values())
    return {key: round(weight / total, 6) for key, weight in scoring.items()}


def normalize_definition(raw: dict[str, Any], *, previous: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the canonical declarative strategy or raise a safe 422 error."""
    if not isinstance(raw, dict):
        raise UserStrategyError("策略定义必须是 JSON 对象", status_code=422)
    strategy_id = str(raw.get("id") or "").strip().lower()
    if not _ID_RE.fullmatch(strategy_id):
        raise UserStrategyError(
            "策略 ID 必须以 ai_ 或 custom_ 开头，并只含小写字母、数字、下划线",
            status_code=422,
        )
    name = _text(raw.get("name"), field="策略名称", maximum=80, required=True)
    description = _text(raw.get("description"), field="策略描述", maximum=500)
    rules = _text(raw.get("rules"), field="策略规则", maximum=4000, required=True)
    direction = str(raw.get("direction") or "long")
    if direction not in {"long", "short", "monitor"}:
        raise UserStrategyError("direction 必须是 long / short / monitor", status_code=422)
    logic = str(raw.get("logic") or "all")
    if logic not in {"all", "any"}:
        raise UserStrategyError("logic 必须是 all 或 any", status_code=422)
    tags_raw = raw.get("tags") if isinstance(raw.get("tags"), list) else []
    tags = []
    for tag in tags_raw[:5]:
        safe = _text(tag, field="标签", maximum=20)
        if safe and safe not in tags:
            tags.append(safe)
    source = str(raw.get("source") or (previous or {}).get("source") or "ai")
    if source not in {"ai", "custom"}:
        source = "ai"
    order_by = str(raw.get("order_by") or "score")
    if order_by != "score" and order_by not in ALLOWED_FIELDS:
        raise UserStrategyError(f"order_by 字段不受支持: {order_by}", status_code=422)
    limit_number = _number(
        raw.get("limit", 100),
        field="limit",
        minimum=1,
        maximum=500,
        allow_none=False,
    )
    max_hold_raw = _number(
        raw.get("max_hold_days", 20),
        field="max_hold_days",
        minimum=1,
        maximum=3650,
    )
    created_at = str((previous or {}).get("created_at") or raw.get("created_at") or _now())
    return {
        "schema_version": 1,
        "id": strategy_id,
        "name": name,
        "description": description,
        "tags": tags or ["用户策略"],
        "source": source,
        "direction": direction,
        "rules": rules,
        "logic": logic,
        "conditions": _normalize_conditions(raw.get("conditions")),
        "basic_filter": _normalize_basic_filter(raw.get("basic_filter")),
        "scoring": _normalize_scoring(raw.get("scoring")),
        "entry_signals": _normalize_signals(raw.get("entry_signals"), field="entry_signals"),
        "exit_signals": _normalize_signals(raw.get("exit_signals"), field="exit_signals"),
        "stop_loss": _number(raw.get("stop_loss", -0.05), field="stop_loss", minimum=-1, maximum=0),
        "take_profit": _number(raw.get("take_profit"), field="take_profit", minimum=0, maximum=10),
        "trailing_stop": _number(raw.get("trailing_stop"), field="trailing_stop", minimum=0, maximum=1),
        "trailing_take_profit_activate": _number(
            raw.get("trailing_take_profit_activate"),
            field="trailing_take_profit_activate",
            minimum=0,
            maximum=10,
        ),
        "trailing_take_profit_drawdown": _number(
            raw.get("trailing_take_profit_drawdown"),
            field="trailing_take_profit_drawdown",
            minimum=0,
            maximum=1,
        ),
        "max_hold_days": int(max_hold_raw) if max_hold_raw is not None else None,
        "order_by": order_by,
        "descending": bool(raw.get("descending", True)),
        "limit": int(limit_number or 100),
        "created_at": created_at,
        "updated_at": _now(),
    }


def _condition_expr(condition: dict[str, Any]) -> pl.Expr:
    left = pl.col(condition["left"])
    kind, value = _parse_right(condition["right"])
    right: pl.Expr | float = pl.col(str(value)) if kind == "field" else float(value)
    op = condition["op"]
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == "==":
        return left == right
    return left != right


def compile_definition(definition: dict[str, Any], *, file_path: Path | None = None) -> StrategyDef:
    conditions = [dict(condition) for condition in definition["conditions"]]
    logic = definition["logic"]

    def filter_fn(df: pl.DataFrame, _params: dict) -> pl.Expr:
        required: set[str] = set()
        for condition in conditions:
            required.add(condition["left"])
            right = condition["right"]
            if isinstance(right, str) and right.startswith("field:"):
                required.add(right[6:])
        if not required.issubset(set(df.columns)):
            return pl.lit(False)
        parts = [_condition_expr(condition).fill_null(False) for condition in conditions]
        return pl.all_horizontal(parts) if logic == "all" else pl.any_horizontal(parts)

    strategy = StrategyDef(
        meta={
            "id": definition["id"],
            "name": definition["name"],
            "description": definition["description"],
            "tags": definition["tags"],
            "version": "1.0.0",
            "params": [],
            "scoring": definition["scoring"],
            "order_by": definition["order_by"],
            "descending": definition["descending"],
            "limit": definition["limit"],
            "rules": definition["rules"],
            "schema_version": definition["schema_version"],
        },
        basic_filter=definition["basic_filter"],
        entry_signals=definition["entry_signals"],
        exit_signals=definition["exit_signals"],
        stop_loss=definition["stop_loss"],
        trailing_stop=definition["trailing_stop"],
        trailing_take_profit_activate=definition["trailing_take_profit_activate"],
        trailing_take_profit_drawdown=definition["trailing_take_profit_drawdown"],
        max_hold_days=definition["max_hold_days"],
        alerts=[],
        filter_fn=filter_fn,
        filter_history_fn=None,
        lookback_days=1,
        source=definition["source"],
        file_path=file_path,
    )
    strategy.take_profit = definition["take_profit"]  # type: ignore[attr-defined]
    return strategy


class UserStrategyWorkspace:
    """Persistent strategy workspace owned by exactly one product account."""

    def __init__(
        self,
        data_dir: Path,
        principal: dict[str, Any] | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.principal = dict(principal or current())
        self.root = user_data_dir_for(self.principal, self.data_dir, create=False) / "strategies"

    def list(self) -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        definitions: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                normalized = normalize_definition(raw, previous=raw)
                normalized["created_at"] = raw.get("created_at") or normalized["created_at"]
                normalized["updated_at"] = raw.get("updated_at") or normalized["updated_at"]
                definitions.append(normalized)
            except (OSError, json.JSONDecodeError, UserStrategyError):
                continue
        definitions.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return definitions

    def summaries(self) -> list[dict[str, Any]]:
        return [
            {
                "id": item["id"],
                "name": item["name"],
                "description": item["description"],
                "source": item["source"],
                "rules": item["rules"],
                "updated_at": item["updated_at"],
            }
            for item in self.list()
        ]

    def get_definition(self, strategy_id: str) -> dict[str, Any]:
        safe_id = str(strategy_id or "").strip().lower()
        if not _ID_RE.fullmatch(safe_id):
            raise UserStrategyError("用户策略不存在", status_code=404)
        path = self.root / f"{safe_id}.json"
        if not path.exists():
            raise UserStrategyError("用户策略不存在", status_code=404)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            normalized = normalize_definition(raw, previous=raw)
            normalized["created_at"] = raw.get("created_at") or normalized["created_at"]
            normalized["updated_at"] = raw.get("updated_at") or normalized["updated_at"]
            return normalized
        except (OSError, json.JSONDecodeError, UserStrategyError) as exc:
            raise UserStrategyError("用户策略文件损坏或不可读取", status_code=500) from exc

    def get(self, strategy_id: str) -> StrategyDef:
        definition = self.get_definition(strategy_id)
        return compile_definition(definition, file_path=self.root / f"{definition['id']}.json")

    def has(self, strategy_id: str) -> bool:
        try:
            self.get_definition(strategy_id)
            return True
        except UserStrategyError:
            return False

    def save(self, raw: dict[str, Any]) -> dict[str, Any]:
        existing = None
        strategy_id = str(raw.get("id") or "").strip().lower()
        if strategy_id and self.has(strategy_id):
            existing = self.get_definition(strategy_id)
        elif len(self.list()) >= _MAX_DEFINITIONS:
            raise UserStrategyError(f"每个用户最多保存 {_MAX_DEFINITIONS} 个策略", status_code=409)
        definition = normalize_definition(raw, previous=existing)
        self.root.mkdir(parents=True, exist_ok=True)
        atomic_write_json(definition, self.root / f"{definition['id']}.json", indent=2)
        return definition

    def save_code(self, code: str, *, expected_id: str | None = None) -> dict[str, Any]:
        try:
            raw = json.loads(str(code or ""))
        except json.JSONDecodeError as exc:
            raise UserStrategyError("用户策略只接受安全 JSON 定义，不接受可执行 Python", status_code=422) from exc
        if not isinstance(raw, dict):
            raise UserStrategyError("策略定义必须是 JSON 对象", status_code=422)
        if expected_id and str(raw.get("id") or "") != expected_id:
            raise UserStrategyError("策略 ID 与保存目标不一致", status_code=422)
        return self.save(raw)

    def delete(self, strategy_id: str) -> bool:
        definition = self.get_definition(strategy_id)
        path = self.root / f"{definition['id']}.json"
        path.unlink()
        return True


class UserStrategyCatalog(StrategyEngine):
    """Read/run Adapter combining shared built-ins with one user's workspace."""

    def __init__(
        self,
        shared_engine: StrategyEngine,
        workspace: UserStrategyWorkspace,
        *,
        include_global_custom: bool = False,
    ) -> None:
        self._shared_engine = shared_engine
        self._workspace = workspace
        self._include_global_custom = include_global_custom
        self._loader = shared_engine._loader
        self._history_loader = shared_engine._history_loader
        self._strategy_dirs = []
        self._strategies = {}

    def _shared_visible(self, strategy: StrategyDef) -> bool:
        return strategy.source == "builtin" or self._include_global_custom

    def get(self, strategy_id: str) -> StrategyDef:
        if self._workspace.has(strategy_id):
            return self._workspace.get(strategy_id)
        strategy = self._shared_engine.get(strategy_id)
        if not self._shared_visible(strategy):
            raise ValueError(f"unknown strategy: {strategy_id}")
        return strategy

    def has(self, strategy_id: str) -> bool:
        try:
            self.get(strategy_id)
            return True
        except (ValueError, UserStrategyError):
            return False

    def list_strategies(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for meta in self._shared_engine.list_strategies():
            strategy = self._shared_engine.get(meta["id"])
            if self._shared_visible(strategy):
                result.append(meta)
                seen.add(str(meta["id"]))
        for definition in self._workspace.list():
            if definition["id"] not in seen:
                result.append(
                    {
                        "id": definition["id"],
                        "name": definition["name"],
                        "description": definition["description"],
                        "tags": definition["tags"],
                        "source": definition["source"],
                    }
                )
        return result

    def reload(self) -> None:
        if self._include_global_custom:
            self._shared_engine.reload()

    def run_all(
        self,
        as_of,
        params_map: dict | None = None,
        overrides_map: dict | None = None,
    ) -> dict:
        params_map = params_map or {}
        overrides_map = overrides_map or {}
        results = {}
        for meta in self.list_strategies():
            strategy_id = str(meta["id"])
            try:
                results[strategy_id] = self.run(
                    strategy_id,
                    as_of,
                    params=params_map.get(strategy_id),
                    overrides=overrides_map.get(strategy_id),
                )
            except (ValueError, UserStrategyError):
                continue
        return results


def definition_code(definition: dict[str, Any]) -> str:
    return json.dumps(definition, ensure_ascii=False, indent=2)


class DeclarativeStrategyGenerator:
    """LLM Adapter that can only return data accepted by this Module."""

    @staticmethod
    def _system_prompt() -> str:
        fields = ", ".join(sorted(ALLOWED_FIELDS))
        signals = ", ".join(sorted(_SAFE_SIGNALS))
        return f"""你是 A 股量化策略设计助手。只返回一个 JSON 对象，不要 Markdown，不要代码。
该 JSON 会经过严格白名单校验，任何 Python、SQL、函数、表达式字符串都会被拒绝。

固定结构：
{{
  "id": "ai_xxx",
  "name": "名称",
  "description": "说明",
  "tags": ["标签"],
  "source": "ai",
  "direction": "long",
  "rules": "用户可读规则",
  "logic": "all",
  "conditions": [{{"left": "close", "op": ">", "right": "field:ma20"}}],
  "basic_filter": {{"price_min": 3, "price_max": 300, "amount_min": 20000000, "exclude_st": true, "exclude_new_days": 30, "boards": ["沪主板", "深主板", "创业板", "科创板", "北交所"]}},
  "scoring": {{"change_pct": 0.5, "vol_ratio_5d": 0.5}},
  "entry_signals": [],
  "exit_signals": ["signal_ma20_breakdown"],
  "stop_loss": -0.05,
  "take_profit": null,
  "trailing_stop": null,
  "trailing_take_profit_activate": null,
  "trailing_take_profit_drawdown": null,
  "max_hold_days": 20,
  "order_by": "score",
  "descending": true,
  "limit": 100
}}

conditions.left、field:右值、scoring 和非 score 的 order_by 只能使用：{fields}
op 只能使用：{", ".join(sorted(OPS))}
entry_signals / exit_signals 只能使用：{signals}
logic 只能是 all 或 any。条件必须能由当前字段直接表达；不要虚构字段。
"""

    async def generate(self, instruction: str) -> dict[str, Any]:
        from app.services.ai_provider import generate_ai_text

        content = await generate_ai_text(
            [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": instruction},
            ],
            temperature=0.2,
            max_tokens=1800,
        )
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1]).strip() if len(lines) >= 3 else text
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise UserStrategyError("AI 未返回有效的安全策略 JSON，请重试", status_code=400) from exc
        if not isinstance(raw, dict):
            raise UserStrategyError("AI 返回的策略不是 JSON 对象，请重试", status_code=400)
        return raw
