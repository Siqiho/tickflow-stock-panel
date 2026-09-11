"""用户偏好设置持久化。

存储位置: data/user_data/preferences.json
沿用 secrets_store 的 merge-write 模式,但不做 chmod 0600 (非敏感数据)。
"""
from __future__ import annotations

import copy
import json
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# 进程内缓存: 行情轮询会连续读 getter。
# 签名必须绑定解析后的文件路径（含租户目录与 DATA_DIR），不能只比 (mtime_ns, size)。
# load_server() 不加这套缓存，避免把用户 sidebar 别名成服务器 pipeline 配置。
_cache: dict | None = None
_cache_sig: tuple[str, int, int] | None = None
_CACHE_LOCK = threading.Lock()


def _path() -> Path:
    from app.services.user_context import user_path
    p = user_path("preferences.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _server_path() -> Path:
    """Return the owner-managed preferences file for shared market services."""
    from app.config import settings

    p = settings.data_dir / "user_data" / "preferences.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _file_sig(path: Path) -> tuple[str, int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (str(path.resolve()), st.st_mtime_ns, st.st_size)


def _invalidate_cache() -> None:
    global _cache, _cache_sig
    with _CACHE_LOCK:
        _cache = None
        _cache_sig = None


def _read(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("preferences.json malformed: %s", e)
    return {}


def _write(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8",
    )


def load() -> dict:
    """Load the current account's UI preferences (path+mtime+size cache)."""
    global _cache, _cache_sig
    p = _path()
    sig = _file_sig(p)
    if sig is None:
        return {}
    with _CACHE_LOCK:
        if _cache is not None and sig == _cache_sig:
            return copy.deepcopy(_cache)
        data = _read(p)
        _cache = data
        _cache_sig = sig
        return copy.deepcopy(_cache)


def load_server() -> dict:
    """Load the one deployment-wide market-data/runtime preference set."""
    return _read(_server_path())


_SAVE_LOCK = threading.Lock()


def save(updates: dict) -> dict:
    """Merge into the current account's personal preference file.

    锁内 read-modify-write, 避免并行 PUT 互相覆盖。
    """
    with _SAVE_LOCK:
        current = load()
        current.update(updates)
        _write(_path(), current)
        _invalidate_cache()
        return current


def save_server(updates: dict) -> dict:
    """Merge deployment-wide market settings; only the owner may mutate them."""
    from app.services import user_context

    if not user_context.is_admin():
        raise PermissionError("shared market settings are administrator-owned")
    current = load_server()
    current.update(updates)
    _write(_server_path(), current)
    return current


def get_realtime_quotes_enabled() -> bool:
    return load_server().get("realtime_quotes_enabled", False)


def get_indices_nav_pinned() -> bool:
    """侧栏指数报价卡片是否固定显示。默认 True（常驻）。
    关闭后，卡片跟随实时行情开关（仅实时开时显示）。"""
    return load().get("indices_nav_pinned", True)


BOARD_QUOTE_INTERVAL_S = 15.0


def get_realtime_quote_interval() -> float:
    """看板整页快照默认 15 秒一轮。已保存的自定义间隔照旧。"""
    stored = load_server().get("realtime_quote_interval", BOARD_QUOTE_INTERVAL_S)
    try:
        return float(stored)
    except (TypeError, ValueError):
        return BOARD_QUOTE_INTERVAL_S


def get_realtime_watchlist_symbols() -> list[str]:
    """Free 档自选实时监控标的:直接取自选页前 5 个。"""
    try:
        from app.services import watchlist
        rows = watchlist.list_symbols()
    except Exception as e:
        logger.warning("load watchlist for realtime failed: %s", e)
        return []
    out: list[str] = []
    for row in rows:
        symbol = str((row or {}).get("symbol") or "").strip().upper()
        if symbol and symbol not in out:
            out.append(symbol)
        if len(out) >= 5:
            break
    return out


def set_realtime_watchlist_symbols(symbols: list[str]) -> list[str]:
    """兼容旧接口: Free 实时标的现在由自选页前 5 个决定。"""
    return get_realtime_watchlist_symbols()


def set_realtime_quote_interval(interval: float) -> float:
    """保存行情轮询间隔（不在此做 min/max 校验，由调用方按档位限制）。"""
    save_server({"realtime_quote_interval": interval})
    return interval


def get_minute_sync_enabled() -> bool:
    return load_server().get("minute_sync_enabled", False)


def get_minute_sync_days() -> int:
    return max(1, min(30, load_server().get("minute_sync_days", 5)))


def get_minute_sync_segment_days() -> int:
    """分钟 K 拉取的单段大小(交易日)。默认 20, 范围 [5, 30]。"""
    raw = load_server().get("minute_sync_segment_days", 20)
    try:
        return max(5, min(30, int(raw)))
    except (TypeError, ValueError):
        return 20


# ===== 数据源选择 (默认 TickFlow；第一阶段仅日K切换入口) =====

_ALLOWED_DATA_PROVIDERS = {"tickflow"}
_ALLOWED_ADJ_FACTOR_PROVIDERS = {"tickflow", "public", "sina", "sina_qfq", "free"}


def get_minute_batch_compress() -> bool:
    """分时详情与批量响应是否启用 gzip 传输压缩。默认开启 (公网部署传输是大头);
    本机/内网可关闭省服务端 CPU。每次请求即时读取, 开关保存后立即生效。
    """
    raw = load().get("minute_batch_compress", True)
    return bool(raw)


def get_daily_batch_compress() -> bool:
    """日K详情与批量响应是否启用 gzip 传输压缩 (与分时各自独立配置)。默认开启。"""
    raw = load().get("daily_batch_compress", True)
    return bool(raw)


def _allowed_data_providers() -> set[str]:
    try:
        from app.data_providers import custom as custom_sources
        return _ALLOWED_DATA_PROVIDERS | custom_sources.names()
    except Exception:  # noqa: BLE001
        return set(_ALLOWED_DATA_PROVIDERS)


def get_daily_data_provider() -> str:
    provider = str(load_server().get("daily_data_provider", "tickflow") or "tickflow").lower()
    return provider if provider in _allowed_data_providers() else "tickflow"


def get_adj_factor_provider() -> str:
    """Adj factor source: tickflow | public/sina/sina_qfq/free | same_as_daily.

    public/sina* bypass TickFlow Cap.ADJ_FACTOR and use free_sources.adj_factor_public.
    Legacy same_as_daily heals to the current daily provider so callers receive a
    real source name (capability-matrix status mapping still accepts the token).
    """
    provider = str(load_server().get("adj_factor_provider", "same_as_daily") or "same_as_daily").lower()
    if provider == "same_as_daily":
        return get_daily_data_provider()
    if provider in _ALLOWED_ADJ_FACTOR_PROVIDERS or provider in _allowed_data_providers():
        return provider
    return get_daily_data_provider()


def is_public_adj_factor_provider(name: str | None = None) -> bool:
    p = (name or get_adj_factor_provider()).lower()
    if p == "same_as_daily":
        return False
    return p in {"public", "sina", "sina_qfq", "free"}


_ALLOWED_FINANCIAL_PROVIDERS = {"tickflow", "public", "eastmoney", "em", "free"}


def get_full_minute_data_provider() -> str:
    provider = str(load().get("full_minute_data_provider", "tickflow") or "tickflow").lower()
    return provider if provider in _allowed_data_providers() else "tickflow"


def get_depth5_data_provider() -> str:
    provider = str(load_server().get("depth5_data_provider") or "tickflow").strip().lower()
    return provider if provider in _allowed_data_providers() else "tickflow"


def set_depth5_data_provider(name: str) -> str:
    save_server({"depth5_data_provider": str(name or "tickflow").strip() or "tickflow"})
    return get_depth5_data_provider()


def get_financial_provider() -> str:
    """Financial statements source: tickflow | public/eastmoney/em/free | plugin.

    public* uses free_sources.financials_public (East Money HSF10) and bypasses Cap.FINANCIAL.
    Frontend v0.2 writes financial_data_provider; the local key is financial_provider.
    Prefer the local key so a leftover v0.2 TickFlow value cannot hide an explicit public setting.
    """
    data = load_server()
    provider = str(
        data.get("financial_provider")
        or data.get("financial_data_provider")
        or "tickflow"
    ).lower()
    if provider in _ALLOWED_FINANCIAL_PROVIDERS or provider in _allowed_data_providers():
        return provider
    return "tickflow"


def is_public_financial_provider(name: str | None = None) -> bool:
    p = (name or get_financial_provider()).lower()
    return p in {"public", "eastmoney", "em", "free"}


_ALLOWED_POOL_PROVIDERS = {"tickflow", "public", "csindex", "sina", "free"}


def get_pool_provider() -> str:
    """Index constituent pool source: tickflow | public/csindex/sina/free.

    public* uses free_sources.pools_public (CSI XLS + Sina fallback).
    """
    provider = str(load_server().get("pool_provider", "public") or "public").lower()
    if provider in _ALLOWED_POOL_PROVIDERS:
        return provider
    return "public"


def is_public_pool_provider(name: str | None = None) -> bool:
    p = (name or get_pool_provider()).lower()
    return p in {"public", "csindex", "sina", "free"}




def get_minute_data_provider() -> str:
    provider = str(load_server().get("minute_data_provider", "tickflow") or "tickflow").lower()
    return provider if provider in _allowed_data_providers() else "tickflow"


def get_realtime_data_provider() -> str:
    """Realtime source: tickflow | public (Tencent/Sina) | plugin.

    Default is public when unset so None/Free tiers can drive full-market live
    without a paid TickFlow key. Explicit "tickflow" keeps the paid path.
    """
    raw = str(load_server().get("realtime_data_provider", "public") or "public").strip().lower()
    if raw in {"public", "tencent", "sina", "free", "local_public"}:
        return "public"
    if raw in _allowed_data_providers():
        return raw
    return "public"


# ===== 盘后管道拉取内容开关 (A股 / ETF / 指数 独立控制) =====

def get_pipeline_pull_a_share() -> bool:
    """Whether the after-hours pipeline pulls A-share daily bars.

    Default True. Must read the saved preference — a hardcoded True made the
    Data page checkbox a no-op (#216).
    """
    return bool(load_server().get("pipeline_pull_a_share", True))


def get_pipeline_pull_etf() -> bool:
    """是否拉取 ETF 日K。默认 False(标的多,首次较慢)。"""
    return load_server().get("pipeline_pull_etf", False)


def get_pipeline_pull_index() -> bool:
    """是否拉取指数日K。默认 True。"""
    return load_server().get("pipeline_pull_index", True)


_PIPELINE_PULL_KEYS = ("pipeline_pull_a_share", "pipeline_pull_etf", "pipeline_pull_index")


def get_pipeline_pull_types() -> dict:
    """返回三个拉取开关的当前值。"""
    return {
        "pipeline_pull_a_share": get_pipeline_pull_a_share(),
        "pipeline_pull_etf": get_pipeline_pull_etf(),
        "pipeline_pull_index": get_pipeline_pull_index(),
    }


def set_pipeline_pull_types(cfg: dict) -> dict:
    """批量保存拉取开关。只接受白名单内的布尔字段。"""
    updates = {
        k: bool(v) for k, v in cfg.items()
        if k in _PIPELINE_PULL_KEYS and v is not None
    }
    save_server(updates)
    return get_pipeline_pull_types()



_VALID_UNIVERSE_SCOPES = ("ALL", "CSI300", "CSI500", "CSI800", "CSI1000", "CSI1800", "SSE50", "WATCHLIST")


def _norm_universe_scope(value: str | None, default: str) -> str:
    from app.services.universe_scope import normalize_scope
    return normalize_scope(value, default=default)


def get_pipeline_universe_scope() -> str:
    """盘后日K/管道主标的范围。默认 ALL（全A），保持历史日K覆盖。"""
    return _norm_universe_scope(load_server().get("pipeline_universe_scope"), "ALL")


def set_pipeline_universe_scope(scope: str) -> str:
    val = _norm_universe_scope(scope, "ALL")
    save_server({"pipeline_universe_scope": val})
    return val


def get_public_data_scope() -> str:
    """public 复权/财务默认同范围。默认 CSI300；可升 CSI800(300∪500)。"""
    return _norm_universe_scope(load_server().get("public_data_scope"), "CSI300")


def set_public_data_scope(scope: str) -> str:
    val = _norm_universe_scope(scope, "CSI300")
    save_server({"public_data_scope": val})
    return val



def get_financial_max_periods() -> int:
    """How many report periods to keep/pull for public financials (default 12)."""
    try:
        n = int(load_server().get("financial_max_periods", 12) or 12)
    except (TypeError, ValueError):
        n = 12
    return max(4, min(40, n))


def set_financial_max_periods(n: int) -> int:
    val = max(4, min(40, int(n)))
    save_server({"financial_max_periods": val})
    return val


def get_pipeline_index_symbols() -> str:
    """指数自定义拉取代码(逗号/换行/空格分隔)。空串表示全量。"""
    return str(load_server().get("pipeline_index_symbols", "") or "").strip()


def set_pipeline_index_symbols(symbols: str) -> str:
    """保存指数自定义代码,返回规范化后的字符串。"""
    save_server({"pipeline_index_symbols": symbols})
    return get_pipeline_index_symbols()


def get_pipeline_schedule() -> dict:
    """返回盘后管道调度时间 {"hour": 15, "minute": 30}。"""
    d = load_server().get("pipeline_schedule", {"hour": 15, "minute": 30})
    return {"hour": d.get("hour", 15), "minute": d.get("minute", 30)}


def set_pipeline_schedule(hour: int, minute: int) -> dict:
    h = max(0, min(23, hour))
    m = max(0, min(59, minute))
    # 盘后不早于 15:00
    if h * 60 + m < 15 * 60:
        h, m = 15, 0
    save_server({"pipeline_schedule": {"hour": h, "minute": m}})
    return {"hour": h, "minute": m}


def get_instruments_schedule() -> dict:
    """返回盘前标的维表调度时间 {"hour": 9, "minute": 10}。"""
    d = load_server().get("instruments_schedule", {"hour": 9, "minute": 10})
    return {"hour": d.get("hour", 9), "minute": d.get("minute", 10)}


def set_instruments_schedule(hour: int, minute: int) -> dict:
    h = max(0, min(23, hour))
    m = max(0, min(59, minute))
    # 盘前不晚于 09:15
    if h * 60 + m > 9 * 60 + 15:
        h, m = 9, 15
    save_server({"instruments_schedule": {"hour": h, "minute": m}})
    return {"hour": h, "minute": m}


def get_enriched_batch_size() -> int:
    """返回 enriched 全量计算每批 symbol 数量。"""
    return max(1, min(10000, load_server().get("enriched_batch_size", 1000)))


def set_enriched_batch_size(size: int) -> int:
    """保存 enriched 全量计算批次大小。"""
    size = max(10, min(6000, size))
    save_server({"enriched_batch_size": size})
    return size


def get_index_daily_batch_size() -> int:
    """返回指数日 K 同步每批 symbol 数量。"""
    return max(1, min(10000, load_server().get("index_daily_batch_size", 100)))


def set_index_daily_batch_size(size: int) -> int:
    """保存指数日 K 同步批次大小。"""
    size = max(1, min(10000, size))
    save_server({"index_daily_batch_size": size})
    return size


# ── 五档盘口 sealed(真假涨停) 配置 ──────────────────────

def get_limit_ladder_monitor_enabled() -> bool:
    """连板梯队 5 档监控开关。关闭时 depth 不轮询(连板梯队降级显示)。"""
    return load_server().get("limit_ladder_monitor_enabled", False)


def get_depth_polling_interval() -> float:
    """depth 盘中轮询间隔(秒)。默认 20(Pro/Expert 都适用)。"""
    return float(load_server().get("depth_polling_interval", 20.0))


def set_depth_polling_interval(interval: float) -> float:
    """保存 depth 轮询间隔。套餐范围 clamp 由 depth_service 按档位做。"""
    interval = max(1.0, min(600.0, float(interval)))
    save_server({"depth_polling_interval": interval})
    return interval


def get_depth_finalize_time() -> dict:
    """盘后 sealed 定版时间 {"hour": 15, "minute": 2}。范围 15:01~18:00。"""
    d = load_server().get("depth_finalize_time", {"hour": 15, "minute": 2})
    return {"hour": d.get("hour", 15), "minute": d.get("minute", 2)}


def set_depth_finalize_time(hour: int, minute: int) -> dict:
    """保存盘后 sealed 定版时间,强制范围 15:01~18:00。"""
    h = max(0, min(23, hour))
    m = max(0, min(59, minute))
    # 下限 15:01, 上限 18:00
    if h * 60 + m < 15 * 60 + 1:
        h, m = 15, 1
    if h * 60 + m > 18 * 60:
        h, m = 18, 0
    save_server({"depth_finalize_time": {"hour": h, "minute": m}})
    return {"hour": h, "minute": m}


# 复盘推送可选渠道白名单 (微信等暂未实现, 不在白名单内, 前端仅作占位)
# 多选: 不推送 = 空数组, 而非 'none'
REVIEW_PUSH_CHANNELS = {"feishu"}
# custom/email 进入白名单后仍默认关闭: 空数组 = 不推送, 不自动勾选新渠道。
PUSH_CHANNELS = {"feishu", "wecom", "custom", "email"}


def get_review_schedule() -> dict:
    """定时复盘调度 {"enabled": False, "hour": 15, "minute": 40}。默认关闭。

    默认 15:40: 盘后管道默认 15:35 启动, 留 5 分钟缓冲, 复盘使用管道
    产出的最终口径数据 (含盘后量校正的日K/enriched)。强制下限 15:00 —
    偏好收盘后即时复盘 (走实时快照缓存, 不等管道) 的用户可自行调早。
    """
    d = load().get("review_schedule", {"enabled": False, "hour": 15, "minute": 40})
    return {
        "enabled": bool(d.get("enabled", False)),
        "hour": d.get("hour", 15),
        "minute": d.get("minute", 40),
    }


def set_review_schedule(enabled: bool, hour: int, minute: int) -> dict:
    """保存定时复盘调度。强制时间下限 15:00(A股收盘)。

    enabled=False 时时间仍保存(下次开启可沿用), 但调度器不会注册 job。
    """
    h = max(0, min(23, hour))
    m = max(0, min(59, minute))
    # 下限 15:00: A股 15:00 收盘, 收盘后才有当日完整数据复盘
    if h * 60 + m < 15 * 60:
        h, m = 15, 0
    save({"review_schedule": {"enabled": bool(enabled), "hour": h, "minute": m}})
    return {"enabled": bool(enabled), "hour": h, "minute": m}


def get_review_push_channels() -> list[str]:
    """复盘推送渠道(多选) — 选定的外部工具列表, 复盘归档后逐个推送。

    与 review_schedule / 实时行情完全独立, 常驻可单独设置。
    空列表 = 不推送; ['feishu'] = 推送到飞书(复用监控中心全局 feishu_webhook_url/secret)。

    向后兼容:
      - 老多版本单选 review_push_channel=='feishu' → ['feishu']
      - 更老布尔 review_push_enabled==True → ['feishu']
    """
    d = load()
    raw = d.get("review_push_channels")
    if isinstance(raw, list):
        return [c for c in raw if c in PUSH_CHANNELS]
    # 兼容老单选字符串
    if d.get("review_push_channel") == "feishu":
        return ["feishu"]
    # 兼容更老布尔开关
    if d.get("review_push_enabled") is True:
        return ["feishu"]
    return []


def set_review_push_channels(channels: list[str]) -> list[str]:
    """保存复盘推送渠道(多选)。过滤白名单外的值、去重、保序。空列表 = 不推送。"""
    seen: set[str] = set()
    cleaned: list[str] = []
    for c in channels or []:
        if c in PUSH_CHANNELS and c not in seen:
            seen.add(c)
            cleaned.append(c)
    save({"review_push_channels": cleaned})
    return cleaned


REVIEW_PUSH_MODES = frozenset({"auto", "manual"})


def get_review_push_mode() -> str:
    """复盘推送触发方式: auto=归档后自动推; manual=仅显式 push。默认 manual。

    定时复盘与手动保存复盘共用此开关。manual 时定时路径只归档不推送,
    手动路径需 save_report 显式传 push=True 才推。
    """
    mode = load().get("review_push_mode", "manual")
    return mode if mode in REVIEW_PUSH_MODES else "manual"


def set_review_push_mode(mode: str) -> str:
    """保存复盘推送触发方式, 白名单外的值回退 manual。"""
    mode = mode if mode in REVIEW_PUSH_MODES else "manual"
    save({"review_push_mode": mode})
    return mode



# ===== 实时监控 =====

# 页面 SSE 刷新配置: { "watchlist": true, "monitor": true, ... }
# 可刷新的页面列表及其默认值
SSE_REFRESH_PAGES_DEFAULT = {
    "overview-market": True,
    "watchlist": True,
    "limit-ladder": False,
}

# 侧栏指数是用户界面偏好, 存在当前账户 preferences.json。
# 与 pipeline_index_symbols / realtime_index_symbols (server) 分轨, 不得互相别名。
SIDEBAR_INDEX_SYMBOLS_DEFAULT = ["000001.SH", "399001.SZ", "399006.SZ", "000680.SH"]


# ===== 盘中实时行情范围 (独立于盘后管道范围) =====
# 指数不在其中: 展示层固定核心四只 (app.services.index_const), 不开放配置。


def get_realtime_pull_stock() -> bool:
    return load_server().get("realtime_pull_stock", True)


def get_realtime_pull_etf() -> bool:
    # 老用户兼容: ETF 实时默认关闭，避免升级后请求量/写盘量突然增加。
    return load_server().get("realtime_pull_etf", False)


def get_realtime_pull_index() -> bool:
    return load_server().get("realtime_pull_index", True)


def get_realtime_index_mode() -> str:
    mode = str(load_server().get("realtime_index_mode", "core") or "core").lower()
    return mode if mode in {"core", "all"} else "core"


def get_realtime_index_symbols() -> list[str]:
    stored = load_server().get("realtime_index_symbols", SIDEBAR_INDEX_SYMBOLS_DEFAULT)
    if isinstance(stored, str):
        import re
        stored = [s.strip() for s in re.split(r"[,\s]+", stored) if s.strip()]
    return [str(s) for s in stored if str(s).strip()]


def set_realtime_quote_scope(cfg: dict) -> dict:
    updates = {}
    for key in ("realtime_pull_stock", "realtime_pull_etf"):
        if key in cfg and cfg[key] is not None:
            updates[key] = bool(cfg[key])
    if updates:
        save_server(updates)
    return get_realtime_quote_scope()


def get_realtime_quote_scope() -> dict:
    return {
        "realtime_pull_stock": get_realtime_pull_stock(),
        "realtime_pull_etf": get_realtime_pull_etf(),
    }


def get_sse_refresh_pages() -> dict[str, bool]:
    """返回每个页面的 SSE 刷新开关。"""
    stored = load().get("sse_refresh_pages", {})
    # 合并默认值 (新增页面自动出现)
    result = dict(SSE_REFRESH_PAGES_DEFAULT)
    result.update(stored)
    return result


def set_sse_refresh_pages(pages: dict[str, bool]) -> dict[str, bool]:
    """保存页面 SSE 刷新配置。"""
    save({"sse_refresh_pages": pages})
    return get_sse_refresh_pages()


def get_sidebar_index_symbols() -> list[str]:
    """返回当前账户侧栏显示的指数代码 (用户 UI 偏好, 不是管道全局指数)。"""
    stored = load().get("sidebar_index_symbols", SIDEBAR_INDEX_SYMBOLS_DEFAULT)
    if isinstance(stored, str):
        import re
        stored = [s.strip() for s in re.split(r"[,\s]+", stored) if s.strip()]
    if not isinstance(stored, list):
        stored = list(SIDEBAR_INDEX_SYMBOLS_DEFAULT)
    allowed = set(SIDEBAR_INDEX_SYMBOLS_DEFAULT)
    return [str(s).strip().upper() for s in stored if str(s).strip().upper() in allowed]


def set_sidebar_index_symbols(symbols: list[str] | None) -> list[str]:
    """保存当前账户侧栏指数。只接受默认四只核心指数, 保序去重。"""
    allowed = set(SIDEBAR_INDEX_SYMBOLS_DEFAULT)
    seen: set[str] = set()
    cleaned: list[str] = []
    for raw in symbols or []:
        symbol = str(raw or "").strip().upper()
        if symbol in allowed and symbol not in seen:
            seen.add(symbol)
            cleaned.append(symbol)
    save({"sidebar_index_symbols": cleaned})
    return get_sidebar_index_symbols()


def get_strategy_monitor_enabled() -> bool:
    """策略告警评估总开关。"""
    return load().get("strategy_monitor_enabled", False)


def get_system_notify_enabled() -> bool:
    """系统通知开关 — 开启后监控告警同时推送到操作系统通知中心。"""
    return load().get("system_notify_enabled", False)


def set_system_notify_enabled(enabled: bool) -> bool:
    """保存系统通知开关。"""
    save({"system_notify_enabled": bool(enabled)})
    return bool(enabled)


def get_feishu_webhook_url() -> str:
    """飞书自定义机器人 Webhook 地址 — 全局共用一处, 所有启用推送的规则都推到这一个群。"""
    return load().get("feishu_webhook_url", "")


def get_feishu_webhook_secret() -> str:
    """飞书自定义机器人签名密钥 — 机器人启用「签名校验」时必填, 留空表示不验签。"""
    return load().get("feishu_webhook_secret", "")


def set_feishu_webhook_url(url: str) -> str:
    """保存飞书 Webhook 地址。传入空串表示清空配置。"""
    save({"feishu_webhook_url": str(url or "").strip()})
    return get_feishu_webhook_url()


def set_feishu_webhook_secret(secret: str) -> str:
    """保存飞书签名密钥。传入空串表示不验签。"""
    save({"feishu_webhook_secret": str(secret or "").strip()})
    return get_feishu_webhook_secret()


def get_webhook_enabled_default() -> bool:
    """新建监控规则时是否默认勾选「飞书推送」。

    数据模型当前只有一个 webhook_enabled 布尔 (即飞书), QMT/ptrade 待定。
    此默认值供规则编辑器新建规则时预填, 单条规则仍可独立修改。
    """
    return load().get("webhook_enabled_default", False)


def set_webhook_enabled_default(enabled: bool) -> bool:
    """保存飞书推送默认勾选态。"""
    save({"webhook_enabled_default": bool(enabled)})
    return get_webhook_enabled_default()


def get_webhook_default_channels() -> list[str]:
    """新建监控规则时默认勾选的推送渠道。空列表 = 默认不推送。"""
    data = load()
    raw = data.get("webhook_default_channels")
    if isinstance(raw, list):
        return [channel for channel in raw if channel in PUSH_CHANNELS]
    # 本地冲突保留: 老布尔只映射飞书, 不因白名单扩大而默认打开 wecom/custom/email。
    if data.get("webhook_enabled_default") is True:
        return ["feishu"]
    return []


def set_webhook_default_channels(channels: list[str]) -> list[str]:
    """保存新建规则默认推送渠道。过滤白名单、去重、保序。空列表 = 不推送。"""
    seen: set[str] = set()
    cleaned: list[str] = []
    for channel in channels or []:
        if channel in PUSH_CHANNELS and channel not in seen:
            seen.add(channel)
            cleaned.append(channel)
    save({"webhook_default_channels": cleaned})
    return cleaned


def get_custom_webhook_url() -> str:
    """Generic third-party JSON Webhook URL shared by enabled rules and reviews."""
    return str(load().get("custom_webhook_url") or "")


def set_custom_webhook_url(url: str) -> str:
    """Persist or clear the generic third-party JSON Webhook URL. Does not enable push."""
    value = str(url or "").strip()
    save({"custom_webhook_url": value})
    return value


_EMAIL_SMTP_DEFAULTS = {
    "host": "",
    "port": 465,
    "security": "ssl",
    "username": "",
    "from_address": "",
    "to_addresses": [],
}


def get_email_smtp_config() -> dict:
    """读取当前账户的非密钥 SMTP 配置; 畸形字段回退默认值, 不读 server prefs。"""
    raw = load().get("email_smtp_config")
    if not isinstance(raw, dict):
        raw = {}
    security = raw.get("security", _EMAIL_SMTP_DEFAULTS["security"])
    if security not in {"ssl", "starttls", "none"}:
        security = _EMAIL_SMTP_DEFAULTS["security"]
    try:
        port = int(raw.get("port", _EMAIL_SMTP_DEFAULTS["port"]))
    except (TypeError, ValueError):
        port = _EMAIL_SMTP_DEFAULTS["port"]
    if not 1 <= port <= 65535:
        port = _EMAIL_SMTP_DEFAULTS["port"]
    recipients = raw.get("to_addresses")
    if not isinstance(recipients, list):
        recipients = []
    return {
        "host": str(raw.get("host") or "").strip(),
        "port": port,
        "security": security,
        "username": str(raw.get("username") or "").strip(),
        "from_address": str(raw.get("from_address") or "").strip(),
        "to_addresses": [str(item).strip() for item in recipients if str(item).strip()],
    }


def set_email_smtp_config(config: dict) -> dict:
    """原子写入当前账户的非密钥 SMTP 配置组; 不改 server prefs, 不自动启用推送。"""
    normalized = {
        "host": str(config.get("host") or "").strip(),
        "port": int(config.get("port", 465)),
        "security": str(config.get("security") or "ssl"),
        "username": str(config.get("username") or "").strip(),
        "from_address": str(config.get("from_address") or "").strip(),
        "to_addresses": [
            str(item).strip() for item in config.get("to_addresses", []) if str(item).strip()
        ],
    }
    save({"email_smtp_config": normalized})
    return get_email_smtp_config()


def get_screener_auto_run() -> bool:
    """选股页进入时是否自动运行所有策略 (获取命中数)。默认开。"""
    return load().get("screener_auto_run", True)


def get_strategy_monitor_ids() -> list[str]:
    """返回监控池中的策略 ID。"""
    return load().get("strategy_monitor_ids", [])


def set_realtime_monitor_config(cfg: dict) -> dict:
    """批量更新实时监控配置。"""
    updates = {}
    if "sse_refresh_pages" in cfg:
        updates["sse_refresh_pages"] = cfg["sse_refresh_pages"]
    if "strategy_monitor_enabled" in cfg:
        updates["strategy_monitor_enabled"] = cfg["strategy_monitor_enabled"]
    if "strategy_monitor_ids" in cfg:
        updates["strategy_monitor_ids"] = cfg["strategy_monitor_ids"]
    if "screener_auto_run" in cfg:
        updates["screener_auto_run"] = bool(cfg["screener_auto_run"])
    if "sidebar_index_symbols" in cfg:
        allowed = set(SIDEBAR_INDEX_SYMBOLS_DEFAULT)
        seen: set[str] = set()
        cleaned: list[str] = []
        for raw in cfg["sidebar_index_symbols"] or []:
            symbol = str(raw or "").strip().upper()
            if symbol in allowed and symbol not in seen:
                seen.add(symbol)
                cleaned.append(symbol)
        updates["sidebar_index_symbols"] = cleaned
    if updates:
        save(updates)
    return get_realtime_monitor_config()


def get_realtime_monitor_config() -> dict:
    """返回完整的实时监控配置。"""
    return {
        "sse_refresh_pages": get_sse_refresh_pages(),
        "strategy_monitor_enabled": get_strategy_monitor_enabled(),
        "strategy_monitor_ids": get_strategy_monitor_ids(),
        "sidebar_index_symbols": get_sidebar_index_symbols(),
        "screener_auto_run": get_screener_auto_run(),
    }


def get_nav_order() -> list[str]:
    """返回左侧菜单的自定义排序（内置页面 path + 扩展分析菜单 id）。"""
    return load().get("nav_order", [])


def set_nav_order(order: list[str]) -> list[str]:
    """保存左侧菜单排序。"""
    save({"nav_order": order})
    return get_nav_order()


def get_nav_hidden() -> list[str]:
    """返回左侧菜单中隐藏的项 id 列表。"""
    return load().get("nav_hidden", [])


def set_nav_hidden(hidden: list[str]) -> list[str]:
    """保存左侧菜单隐藏项。"""
    save({"nav_hidden": hidden})
    return get_nav_hidden()


def get_watchlist_columns() -> list[dict] | None:
    """返回自选列表列配置。"""
    return load().get("watchlist_columns")


def set_watchlist_columns(columns: list[dict]) -> list[dict]:
    """保存自选列表列配置。"""
    save({"watchlist_columns": columns})
    return columns


def get_screener_result_columns() -> list[dict] | None:
    """返回策略结果列表列配置。"""
    return load().get("screener_result_columns")


def set_screener_result_columns(columns: list[dict]) -> list[dict]:
    """保存策略结果列表列配置。"""
    save({"screener_result_columns": columns})
    return columns


# ===== 首次使用引导 =====

def get_onboarding_completed() -> bool:
    """是否已完成首次使用向导。默认 False（新用户）。"""
    return bool(load().get("onboarding_completed", False))


def set_onboarding_completed(done: bool = True) -> bool:
    """标记首次使用向导完成状态。"""
    save({"onboarding_completed": bool(done)})
    return bool(done)


# ===== 财务数据同步时间(持久化,重启不丢失) =====
# 结构: { "metrics": "2026-06-25T10:00:00+08:00", "income": ..., ... }

def get_financial_sync_times() -> dict[str, str]:
    """返回各财务表的最后同步时间(ISO 字符串)。未同步过的表不在返回值中。"""
    return load_server().get("financial_sync_times", {}) or {}


def set_financial_sync_time(table: str, iso_ts: str) -> None:
    """更新单张财务表的最后同步时间(合并写入,不清除其他表)。"""
    times = get_financial_sync_times()
    times[table] = iso_ts
    save_server({"financial_sync_times": times})


def get_sentiment_exclude_st() -> bool:
    """市场环境/主线统计是否剔除风险警示股。默认 True。"""
    return bool(load().get("sentiment_exclude_st", True))


def set_sentiment_exclude_st(v: bool) -> bool:
    save({"sentiment_exclude_st": bool(v)})
    return get_sentiment_exclude_st()


def get_pipeline_regime_enabled() -> bool:
    """盘后管道是否自动计算市场环境(regime)。默认 False。"""
    return load_server().get("pipeline_regime_enabled", False)


_REGIME_BATCH_DAYS_MIN = 25
_REGIME_BATCH_DAYS_MAX = 500
_REGIME_WARMUP_DAYS_MIN = 35
_REGIME_WARMUP_DAYS_MAX = 90


def get_regime_batch_days() -> int:
    v = load_server().get("regime_batch_days", 60)
    try:
        return max(_REGIME_BATCH_DAYS_MIN, min(_REGIME_BATCH_DAYS_MAX, int(v)))
    except (TypeError, ValueError):
        return 60


def get_regime_warmup_days() -> int:
    v = load_server().get("regime_warmup_days", 40)
    try:
        return max(_REGIME_WARMUP_DAYS_MIN, min(_REGIME_WARMUP_DAYS_MAX, int(v)))
    except (TypeError, ValueError):
        return 40


def set_pipeline_regime_enabled(enabled: bool) -> bool:
    save_server({"pipeline_regime_enabled": bool(enabled)})
    return get_pipeline_regime_enabled()


def set_regime_batch_params(batch_days: int | None = None, warmup_days: int | None = None) -> dict:
    payload = {}
    if batch_days is not None:
        payload["regime_batch_days"] = max(_REGIME_BATCH_DAYS_MIN, min(_REGIME_BATCH_DAYS_MAX, int(batch_days)))
    if warmup_days is not None:
        payload["regime_warmup_days"] = max(_REGIME_WARMUP_DAYS_MIN, min(_REGIME_WARMUP_DAYS_MAX, int(warmup_days)))
    if payload:
        save_server(payload)
    return {
        "regime_batch_days": get_regime_batch_days(),
        "regime_warmup_days": get_regime_warmup_days(),
    }


def get_wecom_webhook_url() -> str:
    """企业微信群推送 Webhook。默认空 = 已实现但关闭, 不是未实现。"""
    return load().get("wecom_webhook_url", "")


def set_wecom_webhook_url(url: str) -> str:
    from app.services.webhook_adapter import normalize_wecom_url
    save({"wecom_webhook_url": normalize_wecom_url(url)})
    return get_wecom_webhook_url()


def get_wecom_bot_id() -> str:
    return load_server().get("wecom_bot_id", "")


def set_wecom_bot_id(bot_id: str) -> str:
    save_server({"wecom_bot_id": (bot_id or "").strip()})
    return get_wecom_bot_id()


def get_wecom_bot_secret() -> str:
    return load_server().get("wecom_bot_secret", "")


def set_wecom_bot_secret(secret: str) -> str:
    save_server({"wecom_bot_secret": (secret or "").strip()})
    return get_wecom_bot_secret()


def get_wecom_bot_enabled() -> bool:
    return load_server().get("wecom_bot_enabled", False)


def set_wecom_bot_enabled(enabled: bool) -> bool:
    save_server({"wecom_bot_enabled": bool(enabled)})
    return get_wecom_bot_enabled()


def get_watchlist_groups_in_nav() -> bool:
    return bool(load().get("watchlist_groups_in_nav", False))


def set_watchlist_groups_in_nav(enabled: bool) -> bool:
    save({"watchlist_groups_in_nav": bool(enabled)})
    return get_watchlist_groups_in_nav()


_MINUTE_REFRESH_INTERVAL_MIN = 3
_MINUTE_REFRESH_INTERVAL_MAX = 120


def get_minute_refresh_enabled() -> bool:
    return bool(load_server().get("minute_refresh_enabled", False))


def get_minute_refresh_interval() -> int:
    return max(
        _MINUTE_REFRESH_INTERVAL_MIN,
        min(_MINUTE_REFRESH_INTERVAL_MAX, int(load_server().get("minute_refresh_interval", 6))),
    )


def set_minute_refresh(enabled: bool | None = None, interval: int | None = None) -> dict:
    payload: dict = {}
    if enabled is not None:
        payload["minute_refresh_enabled"] = bool(enabled)
    if interval is not None:
        payload["minute_refresh_interval"] = max(
            _MINUTE_REFRESH_INTERVAL_MIN,
            min(_MINUTE_REFRESH_INTERVAL_MAX, int(interval)),
        )
    if payload:
        save_server(payload)
    return {
        "minute_refresh_enabled": get_minute_refresh_enabled(),
        "minute_refresh_interval": get_minute_refresh_interval(),
    }


DATA_SOURCE_JOB_TIMEOUT_MIN_S = 60


def get_data_source_job_timeout_s() -> int:
    raw = load_server().get("data_source_job_timeout_s", 300)
    try:
        timeout_s = int(raw)
    except (TypeError, ValueError):
        timeout_s = 300
    return max(DATA_SOURCE_JOB_TIMEOUT_MIN_S, timeout_s)


def get_data_source_long_job_timeout_s() -> int:
    raw = load_server().get("data_source_long_job_timeout_s", 1800)
    try:
        timeout_s = int(raw)
    except (TypeError, ValueError):
        timeout_s = 1800
    return max(DATA_SOURCE_JOB_TIMEOUT_MIN_S, timeout_s)


def set_data_source_job_timeouts(job_timeout_s: int | None = None, long_job_timeout_s: int | None = None) -> dict:
    payload: dict = {}
    if job_timeout_s is not None:
        payload["data_source_job_timeout_s"] = max(DATA_SOURCE_JOB_TIMEOUT_MIN_S, int(job_timeout_s))
    if long_job_timeout_s is not None:
        payload["data_source_long_job_timeout_s"] = max(DATA_SOURCE_JOB_TIMEOUT_MIN_S, int(long_job_timeout_s))
    if payload:
        save_server(payload)
    return {
        "data_source_job_timeout_s": get_data_source_job_timeout_s(),
        "data_source_long_job_timeout_s": get_data_source_long_job_timeout_s(),
    }


MINING_BUDGET_PROFILES = frozenset({"balanced", "strict"})


def get_mining_schedule() -> dict:
    data = load_server()
    weekday = data.get("mining_schedule_weekday", 4)
    if isinstance(weekday, bool) or not isinstance(weekday, int) or not 0 <= weekday <= 4:
        weekday = 4
    profile = data.get("mining_budget_profile", "balanced")
    if not isinstance(profile, str) or profile not in MINING_BUDGET_PROFILES:
        profile = "balanced"
    enabled = data.get("mining_schedule_enabled", False)
    if not isinstance(enabled, bool):
        enabled = False
    return {
        "mining_schedule_enabled": enabled,
        "mining_schedule_weekday": weekday,
        "mining_budget_profile": profile,
    }


def set_mining_schedule(enabled: bool, weekday: int, profile: str) -> dict:
    if isinstance(weekday, bool) or not isinstance(weekday, int) or not 0 <= weekday <= 4:
        raise ValueError("mining schedule weekday must be between 0 and 4")
    if profile not in MINING_BUDGET_PROFILES:
        raise ValueError("mining budget profile must be balanced or strict")
    result = {
        "mining_schedule_enabled": bool(enabled),
        "mining_schedule_weekday": weekday,
        "mining_budget_profile": profile,
    }
    save_server(result)
    return result

