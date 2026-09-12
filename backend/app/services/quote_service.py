"""全局实时行情服务。

集中管理全市场行情拉取 + enriched 缓存，供盘中选股、自选股等所有模块复用。

架构:
  - 后台线程轮询 TickFlow get_by_universes(["CN_Equity_A", "CN_ETF"]) + 核心指数按码拉取
    (自定义源走 provider.get_realtime() + 可选 get_realtime_indices() 指数补充)
  - 拉取行情 → 写 kline_daily (不复权) + 增量计算 enriched → 写盘 + 更新缓存
  - _enriched_cache 是唯一的盘中数据源 (OHLCV + 全套技术指标)
  - _live_agg_cache 是递推状态 (只加载一次, 盘中不变)

数据流 (每轮 ~15s):
  1. API 拉取 → raw_records (临时变量)
  2. raw_records → 写 kline_daily (不复权原始价格)
  3. raw_records → 更新 _enriched_cache 的 OHLCV
  4. 增量计算 enriched 指标 (~50ms)
  5. 写 kline_daily_enriched + 替换 _enriched_cache
  6. 通知 SSE

生命周期:
  - 服务启动时读取 preferences，若 enabled 则自动启动线程
  - 运行中可通过 API 切换开关
  - 关闭时停止线程
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from datetime import date, datetime, time as dt_time

import polars as pl

from app.market_time import cn_now
from app.services.index_const import CORE_INDEX_SYMBOLS as AUTHORITY_CORE_INDEX_SYMBOLS
from app.strategy.monitor import format_alert_quote

logger = logging.getLogger(__name__)


def realtime_route() -> str:
    """Effective realtime write/read route: public | tickflow | <custom name> | unresolved.

    Explicit leftover TickFlow / public stay those tokens. Unreadable prefs
    and empty names are unresolved — never treat leftover TickFlow snapshots
    as the current live surface after a switch.
    """
    try:
        from app.services import preferences as _prefs

        return (_prefs.get_realtime_data_provider() or "").strip().lower() or "unresolved"
    except Exception:  # noqa: BLE001
        return "unresolved"


def quote_snapshot_cache_usable(df: pl.DataFrame | None, route: str) -> bool:
    """Whether on-disk quote snapshots may be served for the current realtime route.

    Custom / unresolved never reuse leftover TickFlow or public files.
    Tagged files must match. Untagged legacy files stay valid for leftover
    TickFlow / public only.
    """
    if df is None or getattr(df, "is_empty", lambda: True)():
        return False
    expected = (route or "").strip().lower()
    if not expected or expected == "unresolved":
        return False
    if "route" not in df.columns:
        return expected in {"tickflow", "public"}
    stored = [str(v or "").strip().lower() for v in df["route"].to_list()]
    nonempty = [s for s in stored if s]
    if not nonempty:
        return expected in {"tickflow", "public"}
    if any(s != expected for s in nonempty):
        return False
    if len(nonempty) != len(stored):
        return expected in {"tickflow", "public"}
    return True


def usable_quote_snapshot_files(part_dir, route: str | None = None):
    """Current-route quote_snapshot extras in one date directory."""
    from pathlib import Path

    root = Path(part_dir)
    if not root.is_dir():
        return []
    try:
        expected = route if route is not None else realtime_route()
    except Exception:  # noqa: BLE001
        return []
    if not expected or str(expected).strip().lower() == "unresolved":
        return []
    files = [path for path in sorted(root.glob("*.parquet")) if path.is_file()]
    from app.services.kline_sync import prefer_tagged_route_files

    preferred = prefer_tagged_route_files(files, expected)
    usable = []
    for path in preferred:
        try:
            if quote_snapshot_partition_usable(path, expected):
                usable.append(path)
        except Exception:  # noqa: BLE001
            continue
    return usable


def quote_snapshot_partition_usable(path, route: str | None = None) -> bool:
    """Whether one quote_snapshot partition matches the current realtime route."""
    from pathlib import Path

    expected = (route if route is not None else realtime_route()).strip().lower()
    part = Path(path)
    if not part.is_file():
        return False
    try:
        names = pl.read_parquet_schema(part).names()
        if "route" not in names:
            return expected in {"tickflow", "public"}
        df = pl.read_parquet(part, columns=["route"])
    except Exception as exc:  # noqa: BLE001
        logger.debug("quote snapshot probe failed %s: %s", part, exc)
        # Corrupt leftovers used to mint a TickFlow / public calendar entry.
        return False
    return quote_snapshot_cache_usable(df, expected)


def tag_quote_snapshot_route(df: pl.DataFrame) -> pl.DataFrame:
    route = realtime_route()
    if df is None or getattr(df, "is_empty", lambda: True)():
        return df
    if not route or route == "unresolved" or "route" in df.columns:
        return df
    return df.with_columns(pl.lit(route).alias("route"))


SOURCE_LABELS = {
    "strategy": "策略", "signal": "信号", "price": "价格",
    "market": "异动", "ladder": "连板梯队", "sector": "板块",
    "volume_delta": "放量", "abnormal": "异动", "date": "日期提醒",
}

# Webhook 投递专用线程池 —— 与行情轮询线程隔离。
# send_* 内置重试, 若在 _poll_loop 上同步投递会拖垮实时行情+告警。
_WEBHOOK_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="feishu-webhook")


def _submit_webhook(fn, *args):
    """提交到线程池时复制当前 ContextVar, 避免把别人的通知配置发到错误用户。"""
    ctx = copy_context()

    def wrapped(*inner_args):
        return ctx.run(fn, *inner_args)

    wrapped.__name__ = getattr(fn, "__name__", "webhook")
    wrapped.__qualname__ = getattr(fn, "__qualname__", wrapped.__name__)
    return _WEBHOOK_EXECUTOR.submit(wrapped, *args)


def _body_with_quote(body: str, ev: dict) -> str:
    """推送正文尾部补上触发时的现价/涨跌幅 (日期提醒无行情, 自然为空)。"""
    quote_tail = format_alert_quote(ev.get("price"), ev.get("change_pct"))
    if not quote_tail or body.endswith(quote_tail):
        return body
    return f"{body} · {quote_tail}"


def _persist_last_fetch(fetched_at: float) -> None:
    """Hook for tests / optional last-fetch persistence. Default is a no-op."""
    return


class QuoteService:
    """全局实时行情服务 — 单例。"""

    CORE_INDEX_SYMBOLS = AUTHORITY_CORE_INDEX_SYMBOLS

    # 档位 → 最小轮询间隔 (秒)
    TIER_MIN_INTERVAL = {
        "expert": 1.0,
        "pro": 2.0,
        "starter": 3.0,
        "free": 6.0,
        "none": 8.0,  # public watchlist fallback
    }
    DEFAULT_INTERVAL = 15.0
    MAX_INTERVAL = 60.0

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._enabled = False      # 全局开关 (持久化到 preferences)
        self._interval = self.DEFAULT_INTERVAL
        self._thread: threading.Thread | None = None
        self._repo = None          # 延迟注入, 避免循环导入
        self._update_event = threading.Event()  # SSE 通知: 行情更新后 set
        self._alert_event = threading.Event()   # SSE 通知: 有告警时 set
        self._depth_update_event = threading.Event()  # SSE 通知: depth 五档修正后 set (刷新连板梯队)
        self._pending_alerts: list[dict] = []    # 待推送的告警
        self._max_pending_alerts: int = 1000     # 背压上限: 超出丢弃最旧
        # 复盘进度 SSE 通道: 定时复盘流式生成时, 把 meta/delta/done 事件推给开着页面的前端
        self._review_event = threading.Event()        # SSE 通知: 有复盘进度事件时 set
        self._pending_review: list[str] = []          # 待推送的复盘事件(JSON 字符串)
        self._max_pending_review: int = 200           # 背压上限: 超出丢弃最旧
        self._strategy_monitor = None            # 延迟注入
        self._app_state = None                   # 延迟注入 (FastAPI app.state)
        self._last_final_confirmed: bool | None = None

        # 拉取元信息 (给 SSE / status 用)
        self._fetch_time: float = 0.0       # perf_counter (用于计算 quote_age_ms)
        self._fetch_ms: float = 0.0         # 拉取耗时 (毫秒)
        self._fetched_at: float = 0.0       # 拉取完成的 Unix 时间戳 (毫秒)
        self._symbol_count: int = 0
        self._index_symbol_count: int = 0
        self._etf_symbol_count: int = 0
        self._index_quotes_cache: pl.DataFrame | None = None
        self._index_quotes_cache_token: str | None = None
        self._abnormal_last_eval: float = 0.0

    # ================================================================
    # 生命周期
    # ================================================================

    def _sync_interval_from_prefs(self) -> float:
        """把内存间隔对齐到偏好文件，避免进程残留 8 秒而磁盘已是 15 秒。"""
        from app.services import preferences
        clamped = self._clamp_interval(preferences.get_realtime_quote_interval())
        if clamped != self._interval:
            logger.info("轮询间隔已从偏好同步为 %.1fs (原 %.1fs)", clamped, self._interval)
            self._interval = clamped
        return self._interval

    def start(self, interval: float = 0.0) -> None:
        """启动后台行情轮询线程。"""
        if self._running:
            return
        if interval <= 0:
            from app.services import preferences
            interval = preferences.get_realtime_quote_interval()
        self._interval = self._clamp_interval(interval)
        self._running = True
        self._enabled = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        self._save_enabled(True)
        logger.info("行情服务已启动, 轮询间隔 %.1fs", self._interval)

    def stop(self, *, persist: bool = True) -> None:
        """停止后台行情轮询线程; 运行时退出不应改写用户偏好。"""
        self._running = False
        self._enabled = False
        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None
        if persist:
            self._save_enabled(False)
        logger.info("行情服务已停止")

    def enable(self) -> bool:
        """开启自动行情 (不立即启动线程，等下一个交易时段)。

        leftover TickFlow none/free 仍是 mode=none（不静默改走公开源）; starter+ 或公开/自定义源开启全市场实时。返回值表示是否真正开启。
        """
        if not self.is_realtime_allowed():
            logger.warning("实时行情开启被拒:当前模式不允许实时行情")
            return False
        self._enabled = True
        self._save_enabled(True)
        self._sync_interval_from_prefs()
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._poll_loop, daemon=True)
            self._thread.start()
        logger.info("行情服务已启用, 轮询间隔 %.1fs", self._interval)
        return True

    def disable(self) -> None:
        """关闭自动行情。"""
        self.stop()
        logger.info("行情服务已关闭")

    def boot_check(self) -> None:
        """启动时检查 preferences，若 enabled 则自动启动。

        若 preferences 标记 enabled 且当前模式允许，则自动启动。
        """
        from app.services import preferences
        if not self.is_realtime_allowed():
            if preferences.get_realtime_quotes_enabled():
                self._save_enabled(False)
            logger.info("实时行情未启动:当前模式不允许实时行情")
            return
        if preferences.get_realtime_quotes_enabled():
            self.start()

    def set_repo(self, repo) -> None:
        """注入 KlineRepository, 用于实时落盘。"""
        self._repo = repo

    def set_app_state(self, app_state) -> None:
        """注入 FastAPI app.state, 用于获取 strategy_monitor 等单例。"""
        self._app_state = app_state

    def set_interval(self, interval: float) -> float:
        """运行时更新轮询间隔（立即生效）。"""
        clamped = self._clamp_interval(interval)
        self._interval = clamped
        from app.services import preferences
        preferences.set_realtime_quote_interval(clamped)
        logger.info("轮询间隔已更新为 %.1fs", clamped)
        return clamped

    def get_min_interval(self) -> float:
        """返回当前档位允许的最小间隔。"""
        return self._tier_min_interval()

    def wait_for_update(self, timeout: float = 30.0) -> bool:
        """阻塞等待下一次行情更新 (供 SSE 线程使用)。"""
        self._update_event.clear()
        return self._update_event.wait(timeout=timeout)

    def wait_for_alert(self, timeout: float = 30.0) -> bool:
        """阻塞等待告警 (供 SSE 线程使用)。"""
        self._alert_event.clear()
        return self._alert_event.wait(timeout=timeout)

    def notify_depth_updated(self) -> None:
        """五档盘口修正完成后调用: 通知 SSE 推送 depth_updated, 触发连板梯队刷新。

        与行情/告警通道独立 — 只刷新连板梯队, 不连带刷新 watchlist 等。
        """
        self._depth_update_event.set()

    def wait_for_depth_update(self, timeout: float = 30.0) -> bool:
        """阻塞等待 depth 修正 (供 SSE 线程使用)。"""
        self._depth_update_event.clear()
        return self._depth_update_event.wait(timeout=timeout)

    def pop_alerts(self) -> list[dict]:
        """取走所有待推送的告警 (线程安全)。"""
        with self._lock:
            alerts = self._pending_alerts
            self._pending_alerts = []
            return alerts

    # ================================================================
    # 复盘进度 SSE 通道 — 定时复盘流式生成时, 把事件实时推给前端
    # ================================================================
    def push_review_event(self, event_json: str) -> None:
        """追加一条复盘进度事件(JSON 字符串), 并唤醒 SSE generator。

        事件格式与 recap_market_stream 的产出一致(meta/delta/error/done),
        前端 reviewStore 直接消费。背压: 超过上限丢弃最旧(复盘流几百条 delta, 200 够用)。
        """
        with self._lock:
            self._pending_review.append(event_json)
            if len(self._pending_review) > self._max_pending_review:
                overflow = len(self._pending_review) - self._max_pending_review
                self._pending_review = self._pending_review[overflow:]
            self._review_event.set()

    def wait_for_review(self, timeout: float = 30.0) -> bool:
        """阻塞等待复盘进度事件 (供 SSE 线程使用)。"""
        self._review_event.clear()
        return self._review_event.wait(timeout=timeout)

    def pop_review_events(self) -> list[str]:
        """取走所有待推送的复盘事件 (线程安全)。"""
        with self._lock:
            events = self._pending_review
            self._pending_review = []
            return events

    # ================================================================
    # 档位感知间隔限制
    # ================================================================

    @staticmethod
    def _current_tier() -> str:
        """获取当前档位名（小写）。"""
        from app.tickflow.policy import tier_label
        return tier_label().split()[0].split("+")[0].strip().lower()

    @classmethod
    def realtime_mode(cls) -> str:
        """当前实时行情模式: none / watchlist / full_market。

        - realtime_data_provider=public: 全市场公开源快照（本地标的池分批）
        - 自定义/插件实时源: 全市场（不跟 TickFlow 档位）
        - TickFlow starter+: 全市场付费 universes
        - TickFlow none/free: 无实时。不降级为自选、也不静默改走公开源。
        """
        try:
            from app.services import preferences as _prefs
            provider = _prefs.get_realtime_data_provider()
        except Exception:
            # Prefer fail-closed none over a silent public mix when prefs are unreadable.
            return "none"
        if provider == "public":
            return "full_market"
        if provider != "tickflow":
            return "full_market"
        try:
            from app.services.kline_sync import leftover_tickflow_follow_daily

            if not leftover_tickflow_follow_daily():
                return "none"
        except Exception:
            return "none"
        tier = cls._current_tier()
        if tier in ("none", "free"):
            return "none"
        return "full_market"

    @classmethod
    def is_realtime_allowed(cls) -> bool:
        """当前档位是否允许使用实时行情。"""
        return cls.realtime_mode() != "none"

    @classmethod
    def _tier_min_interval(cls) -> float:
        tier = cls._current_tier()
        return cls.TIER_MIN_INTERVAL.get(tier, cls.DEFAULT_INTERVAL)

    def _clamp_interval(self, interval: float) -> float:
        return max(self._tier_min_interval(), min(self.MAX_INTERVAL, interval))

    # ================================================================
    # 行情数据访问
    # ================================================================

    def get_enriched_today(self) -> tuple[pl.DataFrame, date | None]:
        """返回今天 enriched 数据 + 日期 (线程安全)。

        所有页面统一通过此方法获取实时行情 + 技术指标。
        """
        if not self._repo:
            return pl.DataFrame(), None
        return self._repo.get_enriched_latest()

    def get_quotes_compat(self) -> pl.DataFrame:
        """兼容接口: 返回行情 DataFrame (用于盘中选股等需要 last_price/prev_close 的场景)。

        从 _enriched_cache 取 today 的数据, 只选行情基础列, 补上 last_price 别名。
        不返回指标列, 避免 JOIN live_agg 时列名冲突。
        """
        df, _ = self.get_enriched_today()
        if df.is_empty():
            return df

        # 只取盘中选股需要的行情基础列
        keep = [c for c in [
            "symbol", "close", "open", "high", "low", "volume", "amount",
            "prev_close", "change_pct", "change_amount", "amplitude", "turnover_rate",
        ] if c in df.columns]
        df = df.select(keep)

        # enriched 的 close 等价于 last_price
        if "close" in df.columns and "last_price" not in df.columns:
            df = df.with_columns(pl.col("close").alias("last_price"))
        return df

    @staticmethod
    def _realtime_cache_token() -> str:
        """Current realtime provider token. Unreadable prefs stay unresolved."""
        return realtime_route()

    def get_index_quotes(self, symbols: list[str] | None = None) -> pl.DataFrame:
        """返回实时指数行情缓存。不会触发 TickFlow 请求。

        Cache is keyed by the current realtime provider so leftover TickFlow
        quotes cannot serve after a custom / public switch.
        """
        token = self._realtime_cache_token()
        with self._lock:
            if self._index_quotes_cache_token != token:
                return pl.DataFrame()
            df = self._index_quotes_cache.clone() if self._index_quotes_cache is not None else pl.DataFrame()
        if df.is_empty():
            return df
        if symbols:
            return df.filter(pl.col("symbol").is_in(symbols))
        return df

    def status(self) -> dict:
        """返回共享行情服务状态,不读取请求用户的个人自选。"""
        age = (time.perf_counter() - self._fetch_time) * 1000 if self._fetch_time else -1
        mode = self.realtime_mode()
        return {
            "enabled": self._enabled,
            "running": self._running,
            "mode": mode,
            "realtime_allowed": mode != "none",
            # QuoteService 是服务器级单例。这里必须报告该单例实际缓存的
            # 标的数量,不能在请求上下文中读取某个用户的私有自选列表。
            "watchlist_symbol_count": self._symbol_count if mode == "watchlist" else 0,
            "interval_s": self._sync_interval_from_prefs(),
            "symbol_count": self._symbol_count,
            "index_symbol_count": self._index_symbol_count,
            "etf_symbol_count": self._etf_symbol_count,
            "quote_age_ms": round(age, 0) if age >= 0 else None,
            "is_trading_hours": self._is_trading_hours(),
            "last_fetch_ms": round(self._fetched_at, 0) if self._fetched_at else None,
        }

    def refresh(self) -> dict:
        """手动触发一次行情拉取。"""
        self._fetch_quotes()
        return self.status()

    # ================================================================
    # 后台轮询
    # ================================================================

    def _poll_loop(self) -> None:
        while self._running and self._enabled:
            try:
                if self.realtime_mode() == "none":
                    logger.debug("实时行情未开启, 跳过轮询")
                elif self._is_trading_hours():
                    self._fetch_quotes()
                else:
                    # Off-hours: keep core index snapshots fresh for Indices/overview,
                    # but skip expensive full-market stock batches.
                    from app.services import preferences
                    if (
                        preferences.get_realtime_data_provider() == "public"
                        and preferences.get_realtime_pull_index()
                    ):
                        core = set(preferences.get_realtime_index_symbols() or self.CORE_INDEX_SYMBOLS)
                        self._bootstrap_core_index_quotes(core)
                    else:
                        logger.debug("非交易时段, 跳过行情轮询")
            except Exception as e:  # noqa: BLE001
                logger.warning("行情轮询异常: %s", e)

            waited = 0.0
            # Off-hours poll less aggressively. Re-read prefs so leftover memory (8s)
            # cannot outlive the board clock written in preferences (15s).
            self._sync_interval_from_prefs()
            interval = self._interval if self._is_trading_hours() else max(self._interval, 60.0)
            while self._running and self._enabled and waited < interval:
                time.sleep(0.5)
                waited += 0.5

    def _fetch_quotes(self) -> None:
        """按当前档位拉取行情。mode=none 不拉、不改走其他源。"""
        mode = self.realtime_mode()
        if mode == "none":
            return
        if mode == "watchlist":
            self._fetch_watchlist_quotes()
            return
        self._fetch_full_market_quotes()

    def _bootstrap_core_index_quotes(self, core_index_symbols: set[str]) -> list[dict]:
        """Fetch core indices first and publish cache immediately.

        Full-market public batches can take 1-2+ minutes; the Indices page should
        not wait on stock universe completion for 上证/深证/创业/科创.
        """
        if not core_index_symbols:
            return []
        try:
            rows = self._fetch_public_quote_rows(
                sorted(core_index_symbols), batch_size=20, pause_s=0.0
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("core index bootstrap failed: %s", e)
            return []
        records: list[dict] = []
        for r in rows or []:
            records.append(
                {
                    "symbol": r.get("symbol"),
                    "name": r.get("name"),
                    "last_price": r.get("last"),
                    "prev_close": r.get("prev_close"),
                    "open": r.get("open"),
                    "high": r.get("high"),
                    "low": r.get("low"),
                    "volume": r.get("volume"),
                    "amount": r.get("amount"),
                    "change_pct": r.get("change_pct"),
                    "change_amount": r.get("change_amount"),
                    "source": r.get("source") or "public",
                    "source_volume_unit": r.get("source_volume_unit"),
                    "source_amount_unit": r.get("source_amount_unit"),
                    "unit_version": r.get("unit_version"),
                }
            )
        if not records:
            return []
        df = self._build_index_quotes(records)
        with self._lock:
            self._index_quotes_cache = df
            self._index_quotes_cache_token = self._realtime_cache_token()
            self._index_symbol_count = int(df.height) if df is not None else 0
            # mark freshness so /status and SSE consumers see a live pulse
            self._fetch_time = time.perf_counter()
            self._fetched_at = time.time() * 1000
        try:
            if self._repo and not df.is_empty():
                snapshot = self._build_quote_snapshot(records)
                if not snapshot.is_empty():
                    self._repo.write_quote_snapshot_asset(
                        "index",
                        snapshot,
                        metadata=self._snapshot_metadata("core_indices"),
                    )
        except Exception as e:  # noqa: BLE001
            logger.warning("core index quote snapshot write failed: %s", e)
        logger.info("core index bootstrap: %d 只", len(records))
        self._update_event.set()
        return records

    def _fetch_full_market_quotes(self) -> None:
        """拉取全市场行情 → 写 daily + 计算 enriched + 更新缓存。

        Source selection:
          - preferences.realtime_data_provider=public → 腾讯/新浪分批快照
          - 自定义/插件实时源 → provider.get_realtime() (+ 可选指数补充)
          - TickFlow paid universes (Starter+)
        Custom / TickFlow are fail-closed: no silent public mix.
        """
        from app.services import preferences

        t0 = time.perf_counter()
        now_ts = time.perf_counter()
        try:
            provider = preferences.get_realtime_data_provider()
        except Exception as e:  # noqa: BLE001
            logger.warning("realtime prefs unreadable, fail-closed (no TickFlow/public mix): %s", e)
            return

        try:
            all_index_symbols = set(self._repo.get_index_symbol_set()) if self._repo else set()
            core_index_symbols = set(self.CORE_INDEX_SYMBOLS)
            all_index_symbols.update(core_index_symbols)
            if provider == "public" and preferences.get_realtime_pull_index() and core_index_symbols:
                self._bootstrap_core_index_quotes(core_index_symbols)
            all_etf_symbols = set()
            if self._repo:
                etf_inst = self._repo.get_etf_instruments()
                if not etf_inst.is_empty() and "symbol" in etf_inst.columns:
                    all_etf_symbols = set(etf_inst["symbol"].cast(pl.Utf8).to_list())

            if provider == "public":
                records = self._fetch_public_full_market_records(
                    all_index_symbols=all_index_symbols,
                    core_index_symbols=core_index_symbols,
                    all_etf_symbols=all_etf_symbols,
                )
                replace_index_cache = bool(records)
            elif provider != "tickflow":
                records, replace_index_cache = self._fetch_custom_full_market_records()
            else:
                records = self._fetch_tickflow_full_market_records(
                    all_index_symbols=all_index_symbols,
                    core_index_symbols=core_index_symbols,
                    all_etf_symbols=all_etf_symbols,
                )
                replace_index_cache = bool(records)
        except Exception as e:  # noqa: BLE001
            logger.warning("行情拉取失败: %s", e)
            return

        if not records:
            logger.warning("行情数据为空")
            return

        if provider == "public" and preferences.get_realtime_pull_index() and core_index_symbols:
            have = {
                str(r.get("symbol") or "").upper()
                for r in records
                if isinstance(r, dict) and r.get("symbol") in all_index_symbols
            }
            missing = [s for s in sorted(core_index_symbols) if s not in have]
            if missing:
                try:
                    extra = self._fetch_public_quote_rows(missing, batch_size=20, pause_s=0.0)
                    for r in extra or []:
                        records.append(
                            {
                                "symbol": r.get("symbol"),
                                "name": r.get("name"),
                                "last_price": r.get("last"),
                                "prev_close": r.get("prev_close"),
                                "open": r.get("open"),
                                "high": r.get("high"),
                                "low": r.get("low"),
                                "volume": r.get("volume"),
                                "amount": r.get("amount"),
                                "change_pct": r.get("change_pct"),
                                "change_amount": r.get("change_amount"),
                                "source": r.get("source") or "public",
                                "source_volume_unit": r.get("source_volume_unit"),
                                "source_amount_unit": r.get("source_amount_unit"),
                                "unit_version": r.get("unit_version"),
                            }
                        )
                except Exception as e:  # noqa: BLE001
                    logger.warning("core index top-up failed: %s", e)

        self._process_full_market_records(
            records,
            t0=t0,
            now_ts=now_ts,
            replace_index_cache=replace_index_cache,
        )


    def _fetch_custom_full_market_records(self) -> tuple[list[dict], bool]:
        """Custom/plugin realtime: get_realtime + optional get_realtime_indices.

        Returns (records, replace_index_cache). None / exception on the optional
        index hook keeps the previous index cache (fail-soft, no TickFlow mix).
        """
        from app.services import preferences
        from app.indicators.pipeline import BENCHMARK_INDEX_SYMBOLS

        provider_name = preferences.get_realtime_data_provider()
        from app.data_providers import custom as custom_sources

        if not custom_sources.provider_has_dataset(provider_name, "realtime"):
            logger.warning("realtime provider %s 未声明 realtime, fail-closed", provider_name)
            return [], False
        provider = custom_sources.get_provider(provider_name)
        fetch = getattr(provider, "get_realtime", None)
        if not callable(fetch):
            logger.warning("realtime provider %s 未实现 get_realtime, fail-closed", provider_name)
            return [], False
        records = list(fetch() or [])
        replace_index_cache = True
        index_fn = getattr(provider, "get_realtime_indices", None)
        if callable(index_fn):
            wanted = sorted(
                set(self.CORE_INDEX_SYMBOLS)
                | set(BENCHMARK_INDEX_SYMBOLS)
                | self._collect_monitor_index_symbols()
            )
            try:
                extra = index_fn(wanted)
                if extra is None:
                    replace_index_cache = False
                else:
                    records.extend(list(extra))
            except Exception as e:  # noqa: BLE001
                logger.warning("custom realtime indices failed (%s): %s", provider_name, e)
                replace_index_cache = False
        return records, replace_index_cache

    def _process_full_market_records(
        self,
        records: list[dict],
        *,
        t0: float,
        now_ts: float,
        replace_index_cache: bool = True,
        final_boundary_ms: int | None = None,
    ) -> None:
        """Classify / cache / persist a full-market quote payload."""
        all_index_symbols = set(self._repo.get_index_symbol_set()) if self._repo else set()
        all_index_symbols.update(self.CORE_INDEX_SYMBOLS)
        all_etf_symbols: set[str] = set()
        if self._repo:
            etf_inst = self._repo.get_etf_instruments()
            if not etf_inst.is_empty() and "symbol" in etf_inst.columns:
                all_etf_symbols = set(etf_inst["symbol"].cast(pl.Utf8).to_list())

        index_records = [r for r in records if r.get("symbol") in all_index_symbols]
        etf_records = [r for r in records if r.get("symbol") in all_etf_symbols]
        stock_records = [
            r for r in records
            if r.get("symbol") not in all_index_symbols and r.get("symbol") not in all_etf_symbols
        ]

        persist = True
        if final_boundary_ms is None:
            self._last_final_confirmed = None
        else:
            timestamps = [
                r.get("timestamp")
                for r in records
                if isinstance(r, dict) and r.get("timestamp") not in (None, 0)
            ]
            if not timestamps:
                persist = False
                self._last_final_confirmed = False
            else:
                try:
                    max_ts = max(int(ts) for ts in timestamps)
                except (TypeError, ValueError):
                    persist = False
                    self._last_final_confirmed = False
                else:
                    persist = max_ts >= final_boundary_ms
                    self._last_final_confirmed = persist

        fetch_ms = (time.perf_counter() - t0) * 1000
        fetched_at = time.time() * 1000

        with self._lock:
            self._fetch_time = now_ts
            self._fetch_ms = fetch_ms
            self._fetched_at = fetched_at
            self._symbol_count = len(stock_records)
            self._etf_symbol_count = len(etf_records)
            if replace_index_cache:
                self._index_quotes_cache = (
                    self._build_index_quotes(index_records) if index_records else pl.DataFrame()
                )
                self._index_quotes_cache_token = self._realtime_cache_token()
                self._index_symbol_count = len(index_records)
            else:
                self._index_symbol_count = (
                    0 if self._index_quotes_cache is None or self._index_quotes_cache.is_empty()
                    else int(self._index_quotes_cache.height)
                )

        logger.info(
            "行情刷新: %d 只股票, %d 只ETF, %d 只指数, 耗时 %.0fms",
            len(stock_records), len(etf_records), len(index_records), fetch_ms,
        )
        _persist_last_fetch(fetched_at)
        self._update_volume_delta(records, fetched_at)

        is_public_snapshot = self._records_are_public(records)
        from app.services import kline_sync
        allow_canonical = (not is_public_snapshot) and kline_sync.live_daily_persist_allowed()
        daily_df = self._build_daily(stock_records)
        etf_daily_df = self._build_daily(etf_records)
        index_daily_df = self._build_daily(index_records)
        quote_extra = self._build_quote_extra(stock_records)
        etf_quote_extra = self._build_quote_extra(etf_records)

        if persist:
            if not daily_df.is_empty() and self._repo:
                try:
                    if not allow_canonical:
                        self._repo.write_quote_snapshot_asset(
                            "stock",
                            self._build_quote_snapshot(stock_records),
                            metadata=self._snapshot_metadata("full_market"),
                        )
                    else:
                        self._repo.flush_live_daily(daily_df)
                except Exception as e:  # noqa: BLE001
                    logger.warning("股票行情持久化失败: %s", e)

            if not etf_daily_df.is_empty() and self._repo:
                try:
                    if not allow_canonical:
                        self._repo.write_quote_snapshot_asset(
                            "etf",
                            self._build_quote_snapshot(etf_records),
                            metadata=self._snapshot_metadata("full_market"),
                        )
                    else:
                        self._repo.flush_live_daily_asset("etf", etf_daily_df)
                except Exception as e:  # noqa: BLE001
                    logger.warning("ETF 行情持久化失败: %s", e)

            if not index_daily_df.is_empty() and self._repo:
                try:
                    if not allow_canonical:
                        self._repo.write_quote_snapshot_asset(
                            "index",
                            self._build_quote_snapshot(index_records),
                            metadata=self._snapshot_metadata("full_market"),
                        )
                    else:
                        self._repo.flush_live_daily_asset("index", index_daily_df)
                except Exception as e:  # noqa: BLE001
                    logger.warning("指数行情持久化失败: %s", e)

            if not daily_df.is_empty() and self._repo:
                self._flush_live_enriched(
                    daily_df,
                    quote_extra,
                    asset_type="stock",
                    persist=allow_canonical,
                )
            if not etf_daily_df.is_empty() and self._repo:
                self._flush_live_enriched(
                    etf_daily_df,
                    etf_quote_extra,
                    asset_type="etf",
                    persist=allow_canonical,
                )
            if not index_daily_df.is_empty() and self._repo and allow_canonical:
                index_quote_extra = self._build_quote_extra(index_records)
                self._flush_live_enriched(index_daily_df, index_quote_extra, asset_type="index")

        self._broadcast_quote_updated()
        if persist:
            self._evaluate_monitors(daily_df, quote_extra)

    def _broadcast_quote_updated(self) -> None:
        self._update_event.set()

    def _update_volume_delta(self, records: list[dict], fetched_at: float) -> None:
        return

    @classmethod
    def _final_boundary_ms(cls, kind: str) -> int | None:
        if kind == "close_final":
            boundary = dt_time(15, 0)
        elif kind == "morning_final":
            boundary = dt_time(11, 30)
        else:
            return None
        from app.market_time import CN_TZ, cn_today
        return int(datetime.combine(cn_today(), boundary, tzinfo=CN_TZ).timestamp() * 1000)

    @classmethod
    def _past_final_deadline(cls, kind: str) -> bool:
        now = cn_now()
        if kind == "close_final":
            return now.time() >= dt_time(15, 30)
        if kind == "morning_final":
            return now.time() >= dt_time(12, 10)
        return False

    def _fetch_tickflow_full_market_records(
        self,
        *,
        all_index_symbols: set,
        core_index_symbols: set,
        all_etf_symbols: set,
    ) -> list[dict]:
        from app.services import preferences
        from app.services.kline_sync import leftover_tickflow_follow_daily
        from app.tickflow.client import get_paid_realtime_client

        if not leftover_tickflow_follow_daily():
            logger.info(
                "TickFlow full-market skipped: leftover TickFlow after custom/unresolved daily"
            )
            return []

        tf = get_paid_realtime_client()
        if tf is None:
            logger.warning("TickFlow 全市场实时不可用(无付费 Key)，fail-closed")
            return []

        universes: list[str] = []
        if preferences.get_realtime_pull_stock():
            universes.append("CN_Equity_A")
        if preferences.get_realtime_pull_etf() and all_etf_symbols:
            universes.append("CN_ETF")
        if preferences.get_realtime_pull_index() and preferences.get_realtime_index_mode() == "all":
            universes.append("CN_Index")

        resp = []
        if universes:
            resp.extend(tf.quotes.get_by_universes(universes=universes) or [])
        if preferences.get_realtime_pull_index() and preferences.get_realtime_index_mode() == "core":
            resp.extend(tf.quotes.get(symbols=sorted(core_index_symbols)) or [])
        return self._normalize_quote_records(resp)

    def _fetch_public_full_market_records(
        self,
        *,
        all_index_symbols: set,
        core_index_symbols: set,
        all_etf_symbols: set,
    ) -> list[dict]:
        """Public full-market snapshot from local universe + Tencent/Sina batches."""
        from app.services import preferences
        from app.services.universe_scope import resolve_symbols

        symbols: list[str] = []
        # Indices first so a slow/partial full-market cycle still prices the board.
        if preferences.get_realtime_pull_index():
            if preferences.get_realtime_index_mode() == "all" and all_index_symbols:
                symbols.extend(sorted(all_index_symbols))
            else:
                symbols.extend(sorted(core_index_symbols))
        if preferences.get_realtime_pull_stock():
            stock_syms: list[str] = []
            try:
                stock_syms = resolve_symbols(
                    "ALL",
                    data_dir=self._repo.store.data_dir if self._repo else None,
                    default="ALL",
                    include_watchlist=True,
                    refresh_pools_if_missing=False,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("resolve ALL symbols failed: %s", e)
                stock_syms = []
            if not stock_syms:
                try:
                    scope = preferences.get_public_data_scope()
                    stock_syms = resolve_symbols(
                        scope,
                        data_dir=self._repo.store.data_dir if self._repo else None,
                        default=scope,
                        include_watchlist=True,
                        refresh_pools_if_missing=True,
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning("resolve public scope symbols failed: %s", e)
                    stock_syms = []
            # Must extend — never replace; indices were prepended above.
            if stock_syms:
                symbols.extend(stock_syms)

        if preferences.get_realtime_pull_etf() and all_etf_symbols:
            symbols.extend(sorted(all_etf_symbols))

        seen: set[str] = set()
        ordered: list[str] = []
        for s in symbols:
            su = str(s).strip().upper()
            if su and su not in seen:
                seen.add(su)
                ordered.append(su)

        if not ordered:
            logger.warning("公开源全市场: 本地标的池为空")
            return []

        rows = self._fetch_public_quote_rows(ordered, batch_size=80, pause_s=0.05)
        logger.info("公开源全市场行情: 请求 %d 只, 返回 %d 只", len(ordered), len(rows))
        fake_resp = []
        for r in rows:
            fake_resp.append(
                {
                    "symbol": r.get("symbol"),
                    "name": r.get("name"),
                    "last_price": r.get("last"),
                    "prev_close": r.get("prev_close"),
                    "open": r.get("open"),
                    "high": r.get("high"),
                    "low": r.get("low"),
                    "volume": r.get("volume"),
                    "amount": r.get("amount"),
                    "ext": {
                        "change_pct": r.get("change_pct"),
                        "name": r.get("name"),
                    },
                    "source": r.get("source") or "public",
                    "source_volume_unit": r.get("source_volume_unit"),
                    "source_amount_unit": r.get("source_amount_unit"),
                    "unit_version": r.get("unit_version"),
                }
            )
        return self._normalize_quote_records(fake_resp)

    @staticmethod
    def _normalize_quote_records(resp: list) -> list[dict]:
        records = []
        for q in resp or []:
            if not isinstance(q, dict):
                continue
            ext = q.get("ext") or {}
            last_price = q.get("last_price")
            prev_close = q.get("prev_close")
            change_amount = ext.get("change_amount")
            change_pct = ext.get("change_pct")
            if change_amount is None and last_price is not None and prev_close is not None:
                try:
                    change_amount = float(last_price) - float(prev_close)
                except (TypeError, ValueError):
                    change_amount = None
            if change_pct is None and change_amount is not None and prev_close not in (None, 0):
                try:
                    change_pct = float(change_amount) / float(prev_close) * 100
                except (TypeError, ValueError):
                    change_pct = None
            sym = q.get("symbol")
            if not sym:
                continue
            records.append({
                "symbol": sym,
                "name": q.get("name") or ext.get("name"),
                "last_price": last_price,
                "prev_close": prev_close,
                "open": q.get("open"),
                "high": q.get("high"),
                "low": q.get("low"),
                "volume": q.get("volume"),
                "amount": q.get("amount"),
                "change_pct": change_pct,
                "change_amount": change_amount,
                "amplitude": ext.get("amplitude"),
                "turnover_rate": ext.get("turnover_rate"),
                "timestamp": q.get("timestamp"),
                "session": q.get("session"),
                "source": q.get("source"),
                "source_volume_unit": q.get("source_volume_unit"),
                "source_amount_unit": q.get("source_amount_unit"),
                "unit_version": q.get("unit_version"),
            })
        return records

    def _fetch_watchlist_quotes(self) -> None:
        """Watchlist realtime: TickFlow paid/free key when available, else public fallback."""
        from app.services import preferences
        from app.tickflow.client import get_paid_realtime_client

        symbols = preferences.get_realtime_watchlist_symbols()
        if not symbols:
            logger.info("自选实时未配置标的, 跳过行情拉取")
            return

        t0 = time.perf_counter()
        now_ts = time.perf_counter()
        resp: list = []

        try:
            realtime_provider = preferences.get_realtime_data_provider()
        except Exception as e:  # noqa: BLE001
            logger.warning("watchlist quotes skipped: realtime prefs unreadable: %s", e)
            return
        if realtime_provider not in {"public", "tickflow"}:
            logger.warning(
                "watchlist quotes skipped: custom realtime=%s is fail-closed on this path",
                realtime_provider,
            )
            return
        if realtime_provider == "tickflow":
            from app.services.kline_sync import leftover_tickflow_follow_daily

            if not leftover_tickflow_follow_daily():
                logger.info(
                    "watchlist quotes skipped: leftover TickFlow after custom/unresolved daily"
                )
                return

        tf = get_paid_realtime_client() if realtime_provider == "tickflow" else None
        if tf is not None:
            try:
                resp = tf.quotes.get(symbols=symbols) or []
            except Exception as e:  # noqa: BLE001
                logger.warning("TickFlow watchlist quotes failed: %s", e)
                resp = []

        if not resp:
            if realtime_provider != "public":
                logger.warning(
                    "watchlist quotes empty, not falling back to public (realtime=%s)",
                    realtime_provider,
                )
                return
            try:
                free_rows = self._fetch_public_quote_rows(list(symbols), batch_size=80, pause_s=0.0)
            except Exception as e:  # noqa: BLE001
                logger.warning("free quote fallback failed: %s", e)
                free_rows = []
            resp = []
            for r in free_rows:
                resp.append(
                    {
                        "symbol": r.get("symbol"),
                        "name": r.get("name"),
                        "last_price": r.get("last"),
                        "prev_close": r.get("prev_close"),
                        "open": r.get("open"),
                        "high": r.get("high"),
                        "low": r.get("low"),
                        "volume": r.get("volume"),
                        "amount": r.get("amount"),
                        "ext": {
                            "change_pct": r.get("change_pct"),
                            "name": r.get("name"),
                        },
                        "source": r.get("source"),
                        "source_volume_unit": r.get("source_volume_unit"),
                        "source_amount_unit": r.get("source_amount_unit"),
                        "unit_version": r.get("unit_version"),
                    }
                )
            if resp:
                logger.info("watchlist quotes via free fallback: %d", len(resp))

        if not resp:
            logger.warning("自选实时行情数据为空")
            return

        records = self._normalize_quote_records(resp)

        fetch_ms = (time.perf_counter() - t0) * 1000
        fetched_at = time.time() * 1000
        with self._lock:
            self._fetch_time = now_ts
            self._fetch_ms = fetch_ms
            self._fetched_at = fetched_at
            self._symbol_count = len(records)
            self._index_symbol_count = 0
            self._etf_symbol_count = 0
            self._index_quotes_cache = None
            self._index_quotes_cache_token = None

        logger.info("自选实时刷新: %d 只股票, 耗时 %.0fms", len(records), fetch_ms)

        daily_df = self._build_daily(records)
        quote_extra = self._build_quote_extra(records)
        if not daily_df.is_empty() and self._repo:
            is_public_snapshot = self._records_are_public(records)
            from app.services import kline_sync
            allow_canonical = (
                (not is_public_snapshot) and kline_sync.live_daily_persist_allowed()
            )
            try:
                if not allow_canonical:
                    self._repo.write_quote_snapshot_asset(
                        "stock",
                        self._build_quote_snapshot(records),
                        metadata=self._snapshot_metadata("watchlist"),
                    )
                else:
                    self._repo.merge_live_daily_asset("stock", daily_df)
            except Exception as e:  # noqa: BLE001
                logger.warning("自选实时行情持久化失败: %s", e)
            self._flush_live_enriched(
                daily_df,
                quote_extra,
                asset_type="stock",
                merge=True,
                persist=allow_canonical,
            )

        self._update_event.set()
        self._evaluate_monitors(daily_df, quote_extra)

    # ================================================================
    # 工具
    # ================================================================

    def _collect_monitor_index_symbols(self) -> set[str]:
        """启用中的指数监控规则标的 (asset_type=index & scope=symbols)。"""
        engine = getattr(self._app_state, "monitor_engine", None) if self._app_state else None
        if not engine:
            return set()
        out: set[str] = set()
        for _r in list(engine.rules.values()):
            if _r.get("enabled", True) and _r.get("asset_type") == "index" and _r.get("scope") == "symbols":
                out.update(s for s in _r.get("symbols", []) if s)
        return out

    @staticmethod
    def _build_daily(records: list[dict]) -> pl.DataFrame:
        """将 API records 转为日K格式 DataFrame (只有 OHLCV, 写 kline_daily 用)。"""
        if not records:
            return pl.DataFrame()
        df = pl.DataFrame(records)
        cols_map = {
            "symbol": "symbol",
            "last_price": "close",
            "open": "open",
            "high": "high",
            "low": "low",
            "volume": "volume",
            "amount": "amount",
        }
        select_exprs = []
        for src, dst in cols_map.items():
            if src in df.columns:
                select_exprs.append(pl.col(src).alias(dst))
        if not select_exprs:
            return pl.DataFrame()
        if "timestamp" in df.columns:
            select_exprs.append(
                pl.col("timestamp").cast(pl.Int64, strict=False).alias("quote_ts")
            )
        elif "quote_ts" in df.columns:
            select_exprs.append(
                pl.col("quote_ts").cast(pl.Int64, strict=False).alias("quote_ts")
            )
        from app.market_time import CN_TZ, cn_today

        result = df.select(select_exprs).with_columns(
            pl.lit(cn_today()).cast(pl.Date).alias("date"),
        )
        # 停牌股回归: 实时源对停牌标的返回停牌前最后一份快照 — OHLCV 全为旧日
        # 真实值, 仅 timestamp 停在旧日。这类记录不属于当日, 不过滤会把旧日 K 线
        # 原样复制成当日假蜡烛 (如 301266.SZ 2026-09-04)。按 quote_ts 的北京
        # 日期归属过滤; 时间戳缺失/为空的源无法判断, 维持原行为保留。
        if "quote_ts" in result.columns:
            day_start_ms = int(
                datetime.combine(cn_today(), dt_time(0, 0), tzinfo=CN_TZ).timestamp() * 1000
            )
            result = result.filter(
                pl.col("quote_ts").is_null()
                | pl.col("quote_ts").is_between(day_start_ms, day_start_ms + 86_400_000, closed="left")
            )
        # 停牌/尚无集合竞价的记录 open/high 均为 0。必须在下方用 close 填充前
        # 过滤, 否则零成交行会被伪装成有效日K, 并在 batch 同步后作为实时残留
        # 反复触发历史完整性修复。
        from app.indicators.pipeline import filter_halt_days
        result = filter_halt_days(result)
        # 修复: API 在非交易时段可能返回 open/high/low=0 或 null,
        # 导致蜡烛从 0 开始。用 close 填充这些异常值。
        for col in ("open", "high", "low"):
            if col in result.columns:
                result = result.with_columns(
                    pl.when((pl.col(col) == 0) | pl.col(col).is_null())
                    .then(pl.col("close"))
                    .otherwise(pl.col(col))
                    .alias(col)
                )
        return result

    @staticmethod
    def _fetch_public_quote_rows(
        symbols: list[str],
        *,
        batch_size: int,
        pause_s: float,
    ) -> list[dict]:
        from app.data_providers.registry import get_provider

        provider = get_provider("public")
        frame = provider.get_quote_snapshot(symbols, batch_size=batch_size, pause_s=pause_s)
        return frame.to_dicts() if frame is not None and not frame.is_empty() else []

    @classmethod
    def _build_quote_snapshot(cls, records: list[dict]) -> pl.DataFrame:
        """Build a lineage-rich intraday snapshot using canonical quote units."""
        daily = cls._build_daily(records)
        if daily.is_empty():
            return daily
        raw = pl.DataFrame(records)
        metadata_cols = [
            c
            for c in (
                "symbol",
                "name",
                "prev_close",
                "change_pct",
                "change_amount",
                "source",
                "source_volume_unit",
                "source_amount_unit",
                "unit_version",
                "timestamp",
                "session",
            )
            if c in raw.columns
        ]
        if "symbol" not in metadata_cols:
            return daily
        metadata = raw.select(metadata_cols).unique(subset=["symbol"], keep="last")
        return daily.join(metadata, on="symbol", how="left")

    @staticmethod
    def _snapshot_metadata(scope: str) -> dict:
        return {
            "fetched_at": datetime.now().astimezone().isoformat(),
            "scope": scope,
            "quality_status": "intraday_partial",
        }

    @staticmethod
    def _records_are_public(records: list[dict]) -> bool:
        sources = {
            str(r.get("source") or "").strip().lower()
            for r in records
            if isinstance(r, dict)
        }
        return bool(sources) and sources.issubset({"public", "tencent", "sina"})

    @staticmethod
    def _build_quote_extra(records: list[dict]) -> pl.DataFrame:
        """构建 API 直接提供的补充字段 (不写 daily, 只传给 enriched 计算)。

        包含: prev_close, change_pct, change_amount, amplitude, turnover_rate。
        """
        if not records:
            return pl.DataFrame()
        df = pl.DataFrame(records)
        keep = [c for c in [
            "symbol", "prev_close", "change_pct", "change_amount",
            "amplitude", "turnover_rate",
        ] if c in df.columns]
        if not keep or "symbol" not in keep:
            return pl.DataFrame()
        return df.select(keep)

    @staticmethod
    def _as_percent_change(v: float | None, *, last: float | None = None, prev: float | None = None) -> float | None:
        """Normalize change ratio/percent to percentage points.

        Public Tencent/Sina path already emits percent (e.g. 1.17 / -0.48).
        TickFlow path historically emitted fractions (0.0117). Always prefer
        recomputing from last/prev when both are present so unit cannot drift.
        """
        if last is not None and prev not in (None, 0):
            try:
                return (float(last) - float(prev)) / float(prev) * 100.0
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        if v is None:
            return None
        try:
            x = float(v)
        except (TypeError, ValueError):
            return None
        # Heuristic only when prices missing: |x|<=1 is almost always a fraction
        # for single-day index moves; |x|>1 is already percentage points.
        if abs(x) <= 1.0:
            return x * 100.0
        return x

    @staticmethod
    def _build_index_quotes(records: list[dict]) -> pl.DataFrame:
        """构建指数实时行情缓存，不落股票 parquet。

        Output change_pct/amplitude are percentage points (1.17 = +1.17%),
        matching _fallback_index_quotes_from_daily and Indices page fmtPct.
        """
        if not records:
            return pl.DataFrame()
        rows: list[dict] = []
        for r in records:
            if not isinstance(r, dict) or not r.get("symbol"):
                continue
            last = r.get("last_price")
            prev = r.get("prev_close")
            try:
                last_f = float(last) if last is not None else None
            except (TypeError, ValueError):
                last_f = None
            try:
                prev_f = float(prev) if prev is not None else None
            except (TypeError, ValueError):
                prev_f = None
            change_amount = r.get("change_amount")
            if change_amount is None and last_f is not None and prev_f is not None:
                change_amount = last_f - prev_f
            change_pct = QuoteService._as_percent_change(
                r.get("change_pct"), last=last_f, prev=prev_f
            )
            amp = r.get("amplitude")
            if amp is not None and last_f is not None and prev_f not in (None, 0):
                # amplitude: prefer (high-low)/prev if OHLC present
                try:
                    hi = float(r["high"]) if r.get("high") is not None else None
                    lo = float(r["low"]) if r.get("low") is not None else None
                    if hi is not None and lo is not None and prev_f:
                        amp = (hi - lo) / prev_f * 100.0
                    else:
                        amp = QuoteService._as_percent_change(amp)
                except (TypeError, ValueError, ZeroDivisionError):
                    amp = QuoteService._as_percent_change(amp)
            elif amp is not None:
                amp = QuoteService._as_percent_change(amp)
            rows.append({
                "symbol": r.get("symbol"),
                "name": r.get("name"),
                "last_price": last_f,
                "prev_close": prev_f,
                "open": r.get("open"),
                "high": r.get("high"),
                "low": r.get("low"),
                "volume": r.get("volume"),
                "amount": r.get("amount"),
                "change_pct": change_pct,
                "change_amount": change_amount,
                "amplitude": amp,
                "timestamp": r.get("timestamp"),
                "session": r.get("session"),
                "close": last_f,
            })
        if not rows:
            return pl.DataFrame()
        return pl.DataFrame(rows)

    @staticmethod
    def _is_trading_hours() -> bool:
        now = datetime.now()
        t = now.time()
        morning = dt_time(9, 15) <= t <= dt_time(11, 35)
        afternoon = dt_time(12, 55) <= t <= dt_time(15, 5)
        return now.weekday() < 5 and (morning or afternoon)

    @staticmethod
    def _is_continuous_trading() -> bool:
        """A股连续竞价(北京时间): 9:30-11:30 / 13:00-15:00。与 depth sealed 窗口对齐。

        行情轮询仍走本地 _is_trading_hours 宽窗口, 不把 Catalog/HiThink 拉数改成只在连续竞价。
        """
        now = cn_now()
        t = now.time()
        morning = dt_time(9, 30) <= t <= dt_time(11, 30)
        afternoon = dt_time(13, 0) <= t <= dt_time(15, 0)
        return now.weekday() < 5 and (morning or afternoon)

    @staticmethod
    def _save_enabled(enabled: bool) -> None:
        from app.services import preferences
        preferences.save_server({"realtime_quotes_enabled": enabled})

    # ================================================================
    # 策略监控
    # ================================================================

    def _inject_intraday_signals(self, enriched: pl.DataFrame, engine, asset_type: str = "stock"):
        """Inject monitor-only intraday signals from local minute partitions or API.

        Stock + healthy full-minute service reads local partitions. ETF and
        unhealthy stock fall back to ``fetch_intraday_monitor_batch`` (routed).
        """
        if enriched is None or getattr(enriched, "is_empty", lambda: True)():
            return enriched
        symbols = set()
        getter = getattr(engine, "intraday_signal_symbols", None)
        if callable(getter):
            try:
                symbols = set(getter(asset_type) or [])
            except Exception as e:  # noqa: BLE001
                logger.debug("intraday_signal_symbols failed: %s", e)
        if not symbols:
            return enriched

        evaluator = getattr(self, "_intraday_signal_evaluator", None)
        if evaluator is None:
            from app.strategy.intraday_signals import IntradaySignalEvaluator
            evaluator = IntradaySignalEvaluator()
            self._intraday_signal_evaluator = evaluator

        minute_df = pl.DataFrame()
        minute_svc = getattr(self._app_state, "minute_refresh", None) if self._app_state else None
        healthy = bool(
            minute_svc is not None
            and callable(getattr(minute_svc, "is_healthy", None))
            and minute_svc.is_healthy()
        )
        if asset_type == "stock" and healthy and self._repo is not None:
            from app.market_time import cn_today
            from app.services import kline_sync
            local_get = getattr(self._repo, "get_minute_batch", None)
            if callable(local_get):
                try:
                    minute_df = local_get(list(symbols), cn_today())
                    if not kline_sync.minute_cache_usable(
                        minute_df, kline_sync.full_minute_route(),
                    ):
                        minute_df = pl.DataFrame()
                except Exception as e:  # noqa: BLE001
                    logger.debug("local minute batch for intraday signals failed: %s", e)
                    minute_df = pl.DataFrame()

        if minute_df is None or getattr(minute_df, "is_empty", lambda: True)():
            from app.services import kline_sync
            if not kline_sync.full_minute_may_use_minute_fallback():
                minute_df = pl.DataFrame()
            else:
                capset = getattr(self._app_state, "capabilities", None) if self._app_state else None
                try:
                    minute_df = kline_sync.fetch_intraday_monitor_batch(sorted(symbols), capset)
                except Exception as e:  # noqa: BLE001
                    logger.warning("intraday monitor batch failed: %s", e)
                    minute_df = pl.DataFrame()

        prev_close: dict[str, float] = {}
        if "prev_close" in enriched.columns:
            for row in enriched.select(["symbol", "prev_close"]).iter_rows(named=True):
                try:
                    prev_close[str(row["symbol"])] = float(row["prev_close"])
                except (TypeError, ValueError):
                    continue
        elif "close" in enriched.columns:
            for row in enriched.select(["symbol", "close"]).iter_rows(named=True):
                try:
                    prev_close[str(row["symbol"])] = float(row["close"])
                except (TypeError, ValueError):
                    continue

        from app.market_time import cn_now
        try:
            signals = evaluator.evaluate(
                minute_df,
                symbols=symbols,
                prev_close=prev_close,
                asset_type=asset_type,
                now=cn_now(),
            )
        except TypeError:
            signals = evaluator.evaluate(minute_df)
        inject = getattr(evaluator, "inject", None)
        if callable(inject):
            return inject(enriched, signals or [])
        return enriched

    def _evaluate_monitors(self, daily_df: pl.DataFrame, quote_extra: pl.DataFrame | None) -> None:
        """行情更新后评估统一监控规则引擎,并刷新策略结果缓存。"""
        try:
            # 获取 enriched 数据 (刚算好的)
            enriched_today, enriched_date = self.get_enriched_today()
            if enriched_today.is_empty():
                return

            all_alerts: list[dict] = []
            rule_events: list[dict] = []
            engine = None

            # 通用监控规则评估 (统一引擎: signal/price/market/strategy)
            if self._app_state:
                engine = getattr(self._app_state, "monitor_engine", None)
                if engine and engine.rule_count > 0:
                    # 预构建 symbol → name 映射 (enriched 已 drop name 列, 引擎触发时回填用)
                    try:
                        inst_df = self._app_state.repo.get_instruments()
                        if not inst_df.is_empty() and "symbol" in inst_df.columns and "name" in inst_df.columns:
                            engine.set_name_map({
                                row["symbol"]: row["name"]
                                for row in inst_df.select(["symbol", "name"]).iter_rows(named=True)
                                if row.get("name")
                            })
                    except Exception as e:  # noqa: BLE001
                        logger.debug("name_map 构建失败 (不影响监控): %s", e)
                    enriched_today = self._inject_intraday_signals(
                        enriched_today, engine, asset_type="stock",
                    )
                    rule_events = engine.evaluate(enriched_today, asset_type="stock")
                    if engine.has_rule_type("abnormal") and self._repo is not None:
                        now_ts = time.time()
                        if now_ts - self._abnormal_last_eval >= 30.0:
                            self._abnormal_last_eval = now_ts
                            try:
                                from app.services import abnormal_moves
                                overview = abnormal_moves.build_overview(
                                    self._repo, self,
                                    min_closeness=engine.min_abnormal_closeness(),
                                    limit=1000,
                                )
                                rule_events += engine.evaluate_abnormal(overview.get("rows") or [])
                            except Exception as exc:  # noqa: BLE001
                                logger.warning("异动监控规则评估失败 (不影响其他告警): %s", exc)
                    if (
                        hasattr(engine, "has_asset_rules")
                        and engine.has_asset_rules("etf")
                        and self._repo is not None
                    ):
                        try:
                            etf_enriched, _ = self._repo.get_enriched_latest_asset(
                                "etf",
                                refresh=False,
                            )
                            if not etf_enriched.is_empty():
                                etf_enriched = self._inject_intraday_signals(
                                    etf_enriched, engine, asset_type="etf",
                                )
                                rule_events = [
                                    *rule_events,
                                    *engine.evaluate(
                                        etf_enriched,
                                        asset_type="etf",
                                        reset_strategy_results=False,
                                    ),
                                ]
                        except Exception as e:  # noqa: BLE001
                            logger.warning("ETF 监控评估失败 (不影响股票告警): %s", e)
                    if rule_events:
                        # 落盘到 alerts.jsonl
                        try:
                            from app.services import alert_store
                            alert_store.append_many(
                                self._app_state.repo.store.data_dir, rule_events,
                            )
                        except Exception as e:  # noqa: BLE001
                            logger.warning("告警落盘失败: %s", e)
                        # 转为 SSE 推送格式 (兼容旧 alert schema)
                        for ev in rule_events:
                            all_alerts.append({
                                "source": ev["source"],
                                "type": ev["type"],
                                "rule_id": ev.get("rule_id"),
                                "strategy_id": ev.get("rule_id") if ev["source"] == "strategy" else None,
                                "symbol": ev["symbol"],
                                "name": ev["name"],
                                "message": ev["message"],
                                "price": ev["price"],
                                "change_pct": ev["change_pct"],
                                "signals": ev["signals"],
                                "severity": ev.get("severity", "info"),
                                "conditions": ev.get("conditions") or [],
                                "logic": ev.get("logic") or "and",
                            })

            # 策略页实时回显: 不写文件 (实时行情每轮更新 enriched, 写文件会被 read_cache
            # 的 mtime 校验判过期, 反复读不到)。监控引擎本轮已算出的结果存在内存
            # (latest_strategy_results), 由 /api/screener/cached 端点直接叠加读取。

            # 推入待推送队列 + 通知 SSE (含背压保护)
            if all_alerts:
                with self._lock:
                    self._pending_alerts.extend(all_alerts)
                    # 背压: 超出上限丢弃最旧
                    if len(self._pending_alerts) > self._max_pending_alerts:
                        overflow = len(self._pending_alerts) - self._max_pending_alerts
                        self._pending_alerts = self._pending_alerts[overflow:]
                self._alert_event.set()
                logger.info("监控评估完成: %d 条通知", len(all_alerts))

                # 系统通知 (可选通道, 由 preferences 开关控制)。
                # cooldown 去重已在 MonitorRuleEngine 做过, 这里只负责转发。
                self._maybe_send_system_notifications(all_alerts)

            # Webhook 推送 (飞书等外部 IM, 由规则 webhook_enabled 开关控制)。
            # 紧随系统通知, 同样静默降级不阻断主流程。
            if rule_events:
                self._maybe_send_webhook(rule_events, engine)

        except Exception as e:  # noqa: BLE001
            logger.warning("监控评估失败: %s", e)

    def _maybe_send_webhook(self, rule_events: list[dict], engine) -> None:
        """把告警通过 Webhook 推送到外部 IM (由规则 webhook_channels 指定渠道)。

        - 飞书 / 企业微信 / 第三方 Webhook / 邮件均按规则独立选择
        - webhook_enabled=False 显式关闭时不推; 缺省时以 webhook_channels 为准
        - 空渠道 + 未显式启用 = 不外发 (新通知默认关闭)
        - 提交到独立线程池, 不阻塞行情轮询; 失败不阻断主流程
        - 去重: 复用 MonitorRuleEngine 的 cooldown, 此处不重复去重
        """
        try:
            from app import secrets_store
            from app.services import email_adapter, preferences, webhook_adapter

            feishu_url = preferences.get_feishu_webhook_url()
            feishu_secret = preferences.get_feishu_webhook_secret()
            wecom_url = preferences.get_wecom_webhook_url()
            custom_url = preferences.get_custom_webhook_url()
            custom_secret = secrets_store.get_custom_webhook_secret()
            email_config = preferences.get_email_smtp_config()
            email_password = secrets_store.get_email_smtp_password()
            default_channels = preferences.get_webhook_default_channels()
            if not any((feishu_url, wecom_url, custom_url, email_adapter.is_configured(email_config))):
                return

            enqueued = 0
            for ev in rule_events:
                if engine is not None and hasattr(engine, "get_rule"):
                    rule = engine.get_rule(ev.get("rule_id"), ev.get("owner_user_id"))
                else:
                    rules = engine.rules if engine is not None else {}
                    rule = rules.get(ev.get("rule_id")) if isinstance(rules, dict) else None
                if not rule:
                    continue
                if rule.get("webhook_enabled") is False:
                    continue
                channels = rule.get("webhook_channels") or (
                    default_channels if rule.get("webhook_enabled") else None
                )
                if not channels:
                    continue
                source = ev.get("source", "")
                source_label = SOURCE_LABELS.get(source, source or "通知")
                symbol = ev.get("symbol") or ""
                name = ev.get("name") or ""
                message = ev.get("message") or ""
                title = source_label
                body = f"{symbol} {name} {message}".strip() if symbol else (message or name)
                body = _body_with_quote(body, ev)
                if feishu_url and "feishu" in channels:
                    _submit_webhook(webhook_adapter.send_feishu, feishu_url, title, body, feishu_secret)
                    enqueued += 1
                if wecom_url and "wecom" in channels:
                    _submit_webhook(webhook_adapter.send_wecom, wecom_url, title, body)
                    enqueued += 1
                if custom_url and "custom" in channels:
                    _submit_webhook(
                        webhook_adapter.send_custom,
                        custom_url,
                        title,
                        body,
                        "monitor_alert",
                        ev,
                        custom_secret,
                    )
                    enqueued += 1
                if email_adapter.is_configured(email_config) and "email" in channels:
                    _submit_webhook(
                        email_adapter.send_email,
                        email_config,
                        email_password,
                        title,
                        body,
                    )
                    enqueued += 1
            if enqueued:
                logger.info("Webhook 已提交 %d 条 (异步投递, 按渠道独立投递, 失败记 WARNING)", enqueued)
        except Exception as e:  # noqa: BLE001
            logger.warning("Webhook 提交异常 (不影响告警主流程): %s", e)

    def _maybe_send_system_notifications(self, all_alerts: list[dict]) -> None:
        """把告警转发到操作系统通知中心 (由 preferences 开关控制)。

        - 开关关闭: 直接返回
        - 开关开启: 逐条发系统通知; 失败静默, 不阻断主流程
        - 去重: 复用 MonitorRuleEngine 的 cooldown, 此处不重复去重
        - 批量策略事件 (symbol="") 聚合为一条通知, 避免刷屏
        """
        try:
            from app.services import preferences
            from app.services import notify_adapter

            if not preferences.get_system_notify_enabled():
                return

            for ev in all_alerts:
                # 通知标题: 用 source 分类 (策略/信号/价格/异动)
                source = ev.get("source", "")
                source_label = {
                    "strategy": "策略", "signal": "信号",
                    "price": "价格", "market": "异动",
                }.get(source, source or "通知")

                name = ev.get("name") or ""
                symbol = ev.get("symbol") or ""
                message = ev.get("message") or ""

                # 正文: 优先用现成 message, 拼上 symbol/name 让用户一眼定位
                if symbol:
                    body = f"{symbol} {name} {message}".strip()
                else:
                    body = message or name
                # 补上触发时的现价/涨跌幅 (日期提醒无行情, 自然为空)
                body = _body_with_quote(body, ev)

                title = f"TickFlow · {source_label}"
                notify_adapter.notify(title, body)
        except Exception as e:  # noqa: BLE001
            logger.debug("系统通知发送异常 (不影响告警主流程): %s", e)

    @staticmethod
    def _get_strategy_monitor():
        """获取 StrategyMonitorService — 不再使用, 改用 _app_state 注入。"""
        return None

    # ================================================================
    # enriched 增量计算
    # ================================================================

    def _flush_live_enriched(
        self,
        daily_df: pl.DataFrame,
        quote_extra: pl.DataFrame | None = None,
        asset_type: str = "stock",
        merge: bool = False,
        persist: bool = True,
    ) -> None:
        """增量计算今天的 enriched: 用昨天的递推状态 + 今天 OHLCV → 只算今天 5500 行。

        quote_extra: API 直接提供的补充字段 (prev_close, change_pct 等),
                     不写 daily, 直接传给 compute_enriched_today 避免重复计算。
        """
        try:
            if not persist:
                from app.services.kline_sync import live_enriched_overlay_allowed
                if not live_enriched_overlay_allowed():
                    logger.info(
                        "skip live enriched publish: daily route is custom/unresolved"
                    )
                    return

            today = date.today()
            t0 = time.perf_counter()

            # ---- 尝试增量路径 ----
            live_agg = self._repo.get_live_agg() if asset_type == "stock" else pl.DataFrame()
            prev_enriched, prev_date = (
                self._repo.get_enriched_latest()
                if asset_type == "stock"
                else self._repo.get_enriched_latest_asset(asset_type)
            )

            use_incremental = (
                asset_type == "stock"
                and not live_agg.is_empty()
                and not prev_enriched.is_empty()
                and prev_date is not None
            )

            if use_incremental:
                from app.indicators.pipeline import compute_enriched_today
                instruments = self._repo.get_instruments()
                # 将 API 直接提供的补充字段 JOIN 到 daily_df
                today_ohlcv = daily_df
                if quote_extra is not None and not quote_extra.is_empty():
                    today_ohlcv = daily_df.join(quote_extra, on="symbol", how="left")
                enriched_today = compute_enriched_today(
                    live_agg=live_agg,
                    prev_enriched=prev_enriched,
                    today_ohlcv=today_ohlcv,
                    instruments=instruments,
                )
                if enriched_today.is_empty():
                    logger.warning("增量计算结果为空, 回退到全量计算")
                    use_incremental = False

            # ---- 全量回退路径 ----
            if not use_incremental:
                from datetime import timedelta
                from app.indicators.pipeline import compute_enriched

                logger.info("enriched 全量计算 (live_agg=%s, 上次日期=%s)",
                            "ok" if not live_agg.is_empty() else "空", prev_date)

                cutoff = today - timedelta(days=90)
                table = "kline_etf_daily" if asset_type == "etf" else "kline_daily"
                ohlcv_cols = ["symbol", "date", "open", "high", "low", "close", "volume", "amount"]
                from app.polars_guard import guarded_collect
                from app.services.kline_sync import filter_daily_cache, scan_usable_daily
                lf = scan_usable_daily(self._repo.store.data_dir, table=table)
                if lf is None:
                    return
                hist_df = filter_daily_cache(
                    guarded_collect(
                        lf.filter(pl.col("date") >= cutoff).sort(["symbol", "date"]),
                        priority="background",
                    )
                )
                if hist_df is None or hist_df.is_empty():
                    return

                hist_cols = [c for c in ohlcv_cols if c in hist_df.columns]
                hist_df = hist_df.select(hist_cols).filter(pl.col("date") != today)
                daily_ohlcv = daily_df.select([c for c in ohlcv_cols if c in daily_df.columns])
                full_df = pl.concat([hist_df, daily_ohlcv], how="diagonal_relaxed")
                full_df = full_df.sort(["symbol", "date"])

                from app.services.kline_sync import get_adj_factor_df
                factors = get_adj_factor_df(
                    self._repo.store.data_dir,
                    asset_type="etf" if asset_type == "etf" else "stock",
                )
                instruments = self._repo.get_instruments() if asset_type == "stock" else None

                enriched_full = compute_enriched(full_df, factors=factors, instruments=instruments)
                enriched_today = enriched_full.filter(pl.col("date") == today)

            if enriched_today.is_empty():
                return

            # 异动偏离列: 盘中路径不经过 _refresh_enriched 冷刷新,
            # 需在此附着 (基准 = 历史帧 + 指数实时外推), 否则盘中异动列表为空
            if asset_type == "stock":
                from app.indicators.pipeline import attach_deviation_columns_today
                try:
                    index_quotes = self.get_index_quotes()
                except Exception:
                    index_quotes = None
                enriched_today = attach_deviation_columns_today(
                    enriched_today, self._repo.store.data_dir, index_quotes
                )

            # Public intraday snapshots are published to the live cache only.
            if not persist:
                self._repo.publish_live_enriched_asset(asset_type, enriched_today, merge=merge)
            elif merge:
                self._repo.merge_live_enriched_asset(asset_type, enriched_today)
            else:
                self._repo.flush_live_enriched_asset(asset_type, enriched_today)

            elapsed = time.perf_counter() - t0
            mode_label = "增量" if use_incremental else "全量"
            logger.info("enriched %s: %d 只, %s, 耗时 %.0fms",
                        mode_label, len(enriched_today), today, elapsed * 1000)
        except Exception as e:  # noqa: BLE001
            logger.warning("enriched 计算失败: %s", e)
