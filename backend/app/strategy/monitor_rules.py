"""监控规则 — 统一的 MonitorRule 模型,覆盖策略/个股信号/个股价格/市场异动四类。

职责:
  - 从 data/user_data/monitor_rules/*.json 加载规则定义
  - 校验规则字段合法性
  - 提供 CRUD (load_all / save_one / delete_one)

不知道: 行情评估引擎、API、告警落盘。纯函数 + 文件存储。

设计 (镜像 custom_signals.py 的写法):
  - 一对象一文件 + glob 全扫 + 全量重写
  - 字段白名单复用 custom_signals.ALLOWED_FIELDS (阈值条件) + 信号列清单 (布尔条件)
  - id 正则与 custom_signals 一致,保证可纳入同一索引体系
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.services.fs_utils import atomic_write_text
from app.strategy.custom_signals import ALLOWED_FIELDS

logger = logging.getLogger(__name__)

# ── 常量 ────────────────────────────────────────────────
ID_RE = re.compile(r"^[a-z0-9_]{1,40}$")
RULE_TYPES = {"strategy", "signal", "price", "market", "date", "abnormal"}
SCOPES = {"symbols", "all", "sector"}
LOGICS = {"and", "or"}
DIRECTIONS = {"entry", "exit", "both"}
ABNORMAL_DIRECTIONS = {"up", "down", "both"}
ABNORMAL_WINDOWS = {"any", "3d", "10d", "30d"}
SEVERITIES = {"info", "warn", "critical"}
OPS = {">", ">=", "<", "<=", "==", "!="}

# 布尔信号列前缀 (op=truth 时 field 取这些)
_SIGNAL_PREFIXES = ("signal_", "csg_")


# ── 持久化 (镜像 custom_signals.py) ─────────────────────
def _dir(data_dir: Path) -> Path:
    from app.services.user_context import user_data_dir
    d = user_data_dir(data_dir) / "monitor_rules"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(data_dir: Path, rule_id: str) -> Path:
    return _dir(data_dir) / f"{rule_id}.json"


def load_all(data_dir: Path) -> list[dict]:
    """读取全部监控规则。损坏的文件被跳过。"""
    d = _dir(data_dir)
    out: list[dict] = []
    for f in sorted(d.glob("*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception as e:
            logger.warning("monitor rule load failed %s: %s", f.name, e)
    return out


def _load_from_directory(directory: Path) -> list[dict]:
    if not directory.is_dir():
        return []
    out: list[dict] = []
    for file in sorted(directory.glob("*.json")):
        try:
            out.append(json.loads(file.read_text(encoding="utf-8")))
        except Exception as exc:
            logger.warning("monitor rule load failed %s: %s", file.name, exc)
    return out


def iter_user_principals(data_dir: Path) -> list[dict]:
    """Enumerate tenant principals that already have a user_data directory."""
    principals = [{
        "id": "owner",
        "username": "admin",
        "role": "admin",
        "legacy_home": True,
    }]
    tenants = Path(data_dir) / "tenants"
    if tenants.is_dir():
        for child in sorted(tenants.iterdir()):
            if child.is_dir() and (child / "user_data").is_dir() and child.name != "owner":
                principals.append({
                    "id": child.name,
                    "username": child.name,
                    "role": "user",
                    "legacy_home": False,
                })
    return principals


def load_all_users(data_dir: Path) -> list[tuple[str, list[dict]]]:
    """Load every tenant's monitor rules without binding request context."""
    from app.services.user_context import user_data_dir_for

    loaded: list[tuple[str, list[dict]]] = []
    for principal in iter_user_principals(data_dir):
        root = user_data_dir_for(principal, data_dir, create=False)
        rules = _load_from_directory(root / "monitor_rules")
        loaded.append((str(principal["id"]), rules))
    return loaded


def load_one(data_dir: Path, rule_id: str) -> dict | None:
    p = _path(data_dir, rule_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("monitor rule load failed %s: %s", rule_id, e)
        return None


def save_one(data_dir: Path, rule: dict) -> None:
    p = _path(data_dir, rule["id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(p, json.dumps(rule, ensure_ascii=False, indent=2))


def delete_one(data_dir: Path, rule_id: str) -> bool:
    p = _path(data_dir, rule_id)
    if p.exists():
        p.unlink()
        return True
    return False


# ── 校验 ────────────────────────────────────────────────
def _is_signal_field(field: str) -> bool:
    """判断 field 是否为布尔信号列 (signal_ / csg_ 前缀)。"""
    return any(field.startswith(p) for p in _SIGNAL_PREFIXES)


def date_rule_in_window(remind_date: str, lead_days: int, today: str) -> bool:
    """提醒窗口 [remind_date - lead_days, remind_date] 是否包含 today (均 YYYY-MM-DD)。

    只判自然日历窗口; 是否在交易时段由调用方决定。到期落在休市/节假日不会顺延,
    需 lead_days 覆盖 (交易日历口径待 issue 定夺)。非法输入一律返回 False (fail-safe)。
    """
    try:
        remind = date.fromisoformat(remind_date)
        today_d = date.fromisoformat(today)
        lead = max(0, int(lead_days or 0))
    except (ValueError, TypeError):
        return False
    start = remind - timedelta(days=lead)
    return start <= today_d <= remind


def validate(rule: dict) -> None:
    """校验一条监控规则,非法则抛 ValueError (含中文信息)。"""
    rid = rule.get("id", "")
    if not isinstance(rid, str) or not ID_RE.match(rid):
        raise ValueError(f"规则 id 非法 (仅小写字母数字下划线, 1-40字符): {rid!r}")
    if not isinstance(rule.get("name"), str) or not rule["name"].strip():
        raise ValueError("规则 name 不能为空")
    if rule.get("type") not in RULE_TYPES:
        raise ValueError(f"type 必须是 {RULE_TYPES} 之一")

    # 策略类型: 需要 strategy_id + direction,conditions 可空
    if rule.get("type") == "strategy":
        if not rule.get("strategy_id"):
            raise ValueError("策略类型规则必须指定 strategy_id")
        if rule.get("direction", "entry") not in DIRECTIONS:
            raise ValueError(f"direction 必须是 {DIRECTIONS} 之一")
    elif rule.get("type") == "date":
        remind = rule.get("remind_date")
        if not remind:
            raise ValueError("日期提醒规则必须指定 remind_date")
        try:
            date.fromisoformat(str(remind).strip())
        except ValueError as exc:
            raise ValueError(f"remind_date 必须是 YYYY-MM-DD 日期: {remind!r}") from exc
    elif rule.get("type") == "abnormal":
        if rule.get("direction", "both") not in ABNORMAL_DIRECTIONS:
            raise ValueError(f"异动监控 direction 必须是 {ABNORMAL_DIRECTIONS} 之一")
        if rule.get("abnormal_window", "any") not in ABNORMAL_WINDOWS:
            raise ValueError(f"abnormal_window 必须是 {ABNORMAL_WINDOWS} 之一")
        threshold_pct = rule.get("threshold_pct")
        if not isinstance(threshold_pct, (int, float)) or not 1 <= threshold_pct <= 150:
            raise ValueError("异动监控 threshold_pct 必须是 1-150 的接近度百分比")
        if rule.get("asset_type") == "etf":
            raise ValueError("异动监控不支持 asset_type=etf")
    else:
        # 信号/价格/市场类型: 需要 conditions
        conds = rule.get("conditions")
        if not isinstance(conds, list) or len(conds) == 0:
            raise ValueError("conditions 不能为空")
        if len(conds) > 8:
            raise ValueError("conditions 最多 8 条")
        if rule.get("logic", "and") not in LOGICS:
            raise ValueError(f"logic 必须是 {LOGICS} 之一")
        for i, c in enumerate(conds):
            if not isinstance(c, dict):
                raise ValueError(f"第 {i+1} 个条件格式错误")
            field = c.get("field", "")
            op = c.get("op", "")
            if op == "truth":
                # 布尔信号: field 必须是 signal_/csg_ 前缀
                if not _is_signal_field(field):
                    raise ValueError(f"第 {i+1} 个条件: op=truth 时 field 必须是信号列 (signal_/csg_ 前缀): {field!r}")
            elif op in OPS:
                # 阈值比较: field 必须在白名单, 需要 value
                if field not in ALLOWED_FIELDS:
                    raise ValueError(f"第 {i+1} 个条件: 阈值字段 {field!r} 不在白名单")
                if not isinstance(c.get("value"), (int, float)):
                    raise ValueError(f"第 {i+1} 个条件: value 必须是数字")
            else:
                raise ValueError(f"第 {i+1} 个条件: op {op!r} 非法 (应为 truth 或 {OPS})")

    # scope 校验
    if rule.get("scope", "symbols") not in SCOPES:
        raise ValueError(f"scope 必须是 {SCOPES} 之一")
    if rule.get("scope") == "symbols":
        syms = rule.get("symbols")
        if not isinstance(syms, list) or len(syms) == 0:
            raise ValueError("scope=symbols 时 symbols 不能为空")
    if rule.get("scope") == "sector":
        sector = str(rule.get("sector") or rule.get("sector_name") or "").strip()
        targets = rule.get("sector_targets")
        has_targets = isinstance(targets, list) and len(targets) > 0
        if not sector and not has_targets:
            raise ValueError("scope=sector 时必须提供 sector 或 sector_targets, 不能按全市场执行")

    # 其余枚举
    if rule.get("severity", "info") not in SEVERITIES:
        raise ValueError(f"severity 必须是 {SEVERITIES} 之一")
    cd = rule.get("cooldown_seconds", 3600)
    if not isinstance(cd, int) or cd < 0:
        raise ValueError("cooldown_seconds 必须是非负整数")


def normalize(rule: dict) -> dict:
    """补全默认字段,返回规范化后的规则 (不校验)。"""
    r = dict(rule)
    r.setdefault("enabled", True)
    if r.get("type") == "abnormal":
        r.setdefault("scope", "all")
        r.setdefault("direction", "both")
        r.setdefault("threshold_pct", 70.0)
        r.setdefault("abnormal_window", "any")
    else:
        r.setdefault("scope", "symbols")
        r.setdefault("direction", "entry")
    r.setdefault("symbols", [])
    r.setdefault("sector", None)
    r.setdefault("strategy_id", None)
    r.setdefault("conditions", [])
    r.setdefault("logic", "and")
    r.setdefault("cooldown_seconds", 3600)
    r.setdefault("severity", "info")
    r.setdefault("message", "")
    r.setdefault("webhook_url", "")
    r.setdefault("webhook_enabled", False)
    r.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    return r


# 策略监控自动迁移的规则 id 前缀 (固定, 保证幂等)
STRATEGY_RULE_PREFIX = "mr_strategy_"


def strategy_rule_id(strategy_id: str) -> str:
    """策略监控规则 id = mr_strategy_{strategy_id}。"""
    return f"{STRATEGY_RULE_PREFIX}{strategy_id}"


def migrate_strategy_monitors(data_dir: Path, strategy_ids: list[str], strategy_names: dict[str, str]) -> list[dict]:
    """把 preferences.strategy_monitor_ids 里的策略,同步生成/更新 type=strategy 规则。

    幂等: 已存在的策略规则会被更新 (方向/名称),不会重复创建。
    已从 strategy_ids 移除的策略, 其规则会被停用 (enabled=False) 而非删除 (保留历史触发记录的关联)。

    Args:
        data_dir: 数据目录
        strategy_ids: 当前监控池中的策略 id 列表
        strategy_names: {strategy_id: 策略名} 用于规则显示名
    Returns:
        本次生成/更新的规则列表
    """
    desired = set(strategy_ids)
    existing = load_all(data_dir)
    # 已存在的策略规则 {strategy_id: rule}
    existing_strategy_rules: dict[str, dict] = {}
    for r in existing:
        rid = r.get("id", "")
        if rid.startswith(STRATEGY_RULE_PREFIX):
            sid = rid[len(STRATEGY_RULE_PREFIX):]
            if sid:
                existing_strategy_rules[sid] = r

    touched: list[dict] = []
    # 1. 为当前监控池的策略 upsert 规则
    for sid in desired:
        rule_id = strategy_rule_id(sid)
        name = strategy_names.get(sid, sid)
        rule = existing_strategy_rules.get(sid)
        if rule is None:
            rule = normalize({
                "id": rule_id,
                "name": f"策略监控 · {name}",
                "type": "strategy",
                "scope": "all",
                "strategy_id": sid,
                "direction": "entry",
                "conditions": [],
                "cooldown_seconds": 3600,
                "enabled": True,
            })
        else:
            rule = dict(rule)
            rule["enabled"] = True
            rule["strategy_id"] = sid
            rule["name"] = f"策略监控 · {name}"
            rule.setdefault("scope", "all")
            rule.setdefault("direction", "entry")
        save_one(data_dir, rule)
        touched.append(rule)

    # 2. 不在监控池的策略 → 停用其规则 (不删除)
    for sid, rule in existing_strategy_rules.items():
        if sid not in desired and rule.get("enabled") is not False:
            rule = dict(rule)
            rule["enabled"] = False
            save_one(data_dir, rule)

    return touched
