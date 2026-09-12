"""Repository 层(§7.4)。

数据分层:
  - DuckDB 视图: 冷查询(统计、元数据、用户自定义SQL)
  - Polars 缓存: 热路径(enriched 最新日 ~5500行 + instruments ~5500行)
  - Polars scan_parquet: 分钟K/历史日K (predicate pushdown)

缓存生命周期:
  - startup 时不加载(数据可能为空)
  - pipeline 完成后调用 refresh_cache()
  - 服务层通过 get_enriched_latest() / get_instruments() 获取缓存
"""
from __future__ import annotations

import glob as globlib
import logging
import re
import sys
import threading
from datetime import date
from pathlib import Path

import duckdb
import polars as pl

from app.config import settings
from app.polars_guard import guarded_collect
from app.services.atomic_io import atomic_write_parquet, optimistic_upsert_parquet, write_lineage_record

logger = logging.getLogger(__name__)


class KlineReadError(RuntimeError):
    """Local parquet exists but cannot be read (corrupt, permission, or parse)."""


def _collect_local_parquet(action, pattern: str, label: str) -> pl.DataFrame:
    """Return empty when no files exist; raise if matching files cannot be read."""
    try:
        matches = globlib.glob(pattern, recursive=True)
    except OSError as exc:
        raise KlineReadError(f"{label}: {exc}") from exc
    if not matches:
        return pl.DataFrame()
    try:
        return action()
    except KlineReadError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise KlineReadError(f"{label}: {exc}") from exc


def enriched_dirname(asset_type: str) -> str:
    """asset_type → enriched parquet 目录名。ETF 走独立目录, 其余(stock)用日K enriched。"""
    return "kline_etf_enriched" if asset_type == "etf" else "kline_daily_enriched"


def _latest_date_partition_glob(root: Path) -> str | None:
    """Latest ``date=*`` parquet glob. Never leftover-unions historical partitions."""
    if not root.is_dir():
        return None
    partitions = sorted(
        child for child in root.iterdir()
        if child.is_dir()
        and child.name.startswith("date=")
        and any(child.glob("*.parquet"))
    )
    if not partitions:
        return None
    return f"{partitions[-1].as_posix()}/*.parquet"


def _route_sql_predicate(route: str, *, leftover_public: bool = False) -> str | None:
    token = (route or "").strip().lower()
    if not token or token == "unresolved" or not re.fullmatch(r"[a-z0-9_.-]+", token):
        return None
    if leftover_public and token == "tickflow":
        return "lower(coalesce(CAST(route AS VARCHAR), 'tickflow')) IN ('tickflow', 'public')"
    if token in {"tickflow", "public"}:
        return f"lower(coalesce(CAST(route AS VARCHAR), '{token}')) = '{token}'"
    return f"lower(CAST(route AS VARCHAR)) = '{token}'"


class DataStore:
    """唯一的存储入口 — 进程启动时创建。"""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = Path(data_dir or settings.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 一次性数据迁移: 旧桌面版把数据放在 exe 同级的兄弟目录 TickFlowStockPanel_Data/,
        # 新版改为 {app}/data/。老用户首次启动时自动把旧数据搬过来, 无感升级。
        self._migrate_legacy_data_dir()

        # 关键子目录(§7.2)
        for sub in (
            "kline_daily",
            "kline_daily_enriched",
            "kline_index_daily",
            "kline_index_enriched",
            "kline_etf_daily",
            "kline_etf_enriched",
            "kline_etf_minute",
            "kline_minute",
            "adj_factor",
            "adj_factor_etf",
            "financials",
            "instruments",
            "instruments_index",
            "instruments_etf",
            "instruments_ext",
            "kline_ext",
            "pools",
            "backtest_results",
            "screener_results",
            "ai_cache",
            "user_data",
            "depth5",
            "sealed_l1",
            "quote_snapshot",
            "lineage",
        ):
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)

        # 财务数据子目录
        for sub in ("metrics", "income", "balance_sheet", "cash_flow"):
            (self.data_dir / "financials" / sub).mkdir(parents=True, exist_ok=True)

        # DuckDB 内存模式 — 不建 .db 文件(§7.1)
        self.db = duckdb.connect(database=":memory:")
        self._register_views()

    def _migrate_legacy_data_dir(self) -> None:
        """把旧桌面版数据目录 (<安装目录>/../TickFlowStockPanel_Data/) 迁移到新位置 (<安装目录>/data/)。

        背景: 旧版 data_dir = exe_dir.parent / "TickFlowStockPanel_Data" (兄弟目录),
        新版改为 exe_dir / "data" (子目录)。老用户首次升级时旧数据在兄弟目录,
        若不迁移会导致历史行情/策略/回测/监控全部"丢失"(实际还在旧位置)。

        策略 (仅打包桌面版触发, 开发/Docker 不受影响):
          1. 旧目录存在且新 data/ 还基本为空 → 整目录搬迁 (shutil.move, 跨盘符安全)。
          2. 新旧目录都已有数据 (用户在两套路径都跑过) → 不自动搬, 仅记日志, 避免覆盖。
          3. 旧目录不存在 → 新装用户, 无需迁移。
        所有异常都吞掉只记警告 —— 数据迁移失败绝不能阻塞应用启动。
        """
        # 仅打包桌面版需要迁移; 开发/Docker 模式 _PROJECT_ROOT/data 本就是唯一路径
        if not getattr(sys, "frozen", False):
            return

        import shutil

        try:
            legacy_dir = self.data_dir.parent / "TickFlowStockPanel_Data"
            if not legacy_dir.exists():
                return  # 新装用户, 无旧数据

            # 新 data/ 目录里已有实质性内容 → 用户已在新路径跑过, 不覆盖
            # (用 .parquet 作为"有真实数据"的判据, 避免空子目录误判)
            has_new_data = any(self.data_dir.rglob("*.parquet")) or any(
                self.data_dir.rglob("*.jsonl")
            )
            if has_new_data:
                logger.info(
                    "legacy data dir %s exists but new %s already has data, skip migration",
                    legacy_dir, self.data_dir,
                )
                return

            logger.info("migrating legacy data %s -> %s", legacy_dir, self.data_dir)
            # 逐项 move 而非整目录 move: data/ 可能已被 __init__ 创建了空子目录,
            # 直接 shutil.move(legacy, data) 会因目标已存在失败。
            for item in legacy_dir.iterdir():
                dest = self.data_dir / item.name
                if dest.exists():
                    # 同名子目录 (如 kline_daily): 合并内容
                    if dest.is_dir():
                        shutil.move(str(item), str(dest / item.name))
                    else:
                        item.unlink()  # 同名文件, 以新路径为准, 删旧
                else:
                    shutil.move(str(item), str(dest))
            # 搬完后清理空的旧目录
            try:
                shutil.rmtree(legacy_dir)
            except OSError:
                logger.warning("legacy dir %s not empty, kept", legacy_dir)
            logger.info("legacy data migration done")
        except Exception as e:  # noqa: BLE001
            logger.warning("legacy data migration failed (startup continues): %s", e)

    def _register_views(self) -> None:
        """Mount parquet as DuckDB views without a leftover-visible raw glob.

        Route-sensitive kline / adj / financial / depth / instrument views
        are gated immediately. Instruments follow the daily route (no
        ``instrument_provider``).
        """
        d = self.data_dir.as_posix()
        statements = []
        kline_ext_glob = _latest_date_partition_glob(self.data_dir / "kline_ext")
        if kline_ext_glob:
            statements.append(
                f"""CREATE OR REPLACE VIEW kline_ext AS
                    SELECT * FROM read_parquet('{kline_ext_glob}', union_by_name=true)"""
            )
        for sql in statements:
            try:
                self.db.execute(sql)
            except duckdb.IOException:
                logger.debug("view registration skipped (no parquet yet): %s", sql[:60])
        self._register_gated_catalog_views()
        self._register_unified_views()

    def _register_gated_catalog_views(self) -> None:
        """Register route-gated kline / adj / financial / depth / instrument views.

        Startup used to ``CREATE VIEW`` from raw ``**/*.parquet`` first and
        only then gate. Concurrent SQL between those statements saw leftover
        TickFlow after a custom switch. Instruments follow the daily route.
        """
        d = self.data_dir.as_posix()
        try:
            from app.services.instrument_sync import instrument_route
        except Exception:  # noqa: BLE001
            instrument_route = None
        if instrument_route is None:
            self._empty_named_views(
                ("instruments", "instruments_index", "instruments_etf", "instruments_ext"),
            )
        else:
            route = instrument_route()
            for name, subdir in (
                ("instruments", "instruments"),
                ("instruments_index", "instruments_index"),
                ("instruments_etf", "instruments_etf"),
                ("instruments_ext", "instruments_ext"),
            ):
                if not self._has_parquet(subdir):
                    continue
                self._register_route_filtered_view(
                    name,
                    f"{d}/{subdir}/**/*.parquet",
                    route,
                )

        try:
            from app.services.financial_sync import FINANCIAL_TABLES, get_financial_df
        except Exception:  # noqa: BLE001
            FINANCIAL_TABLES = ()
            get_financial_df = None
        d = self.data_dir.as_posix()
        for table in FINANCIAL_TABLES:
            path = self.data_dir / "financials" / table / "part.parquet"
            if not path.exists() or get_financial_df is None:
                continue
            name = f"financials_{table}"
            glob = f"{d}/financials/{table}/*.parquet"
            try:
                df = get_financial_df(self.data_dir, table)
                self.db.execute(f"DROP VIEW IF EXISTS {name}")
                self.db.execute(f"DROP TABLE IF EXISTS {name}")
                if df is None or df.is_empty():
                    self.db.execute(
                        f"CREATE OR REPLACE VIEW {name} AS "
                        f"SELECT * FROM read_parquet('{glob}', union_by_name=true) WHERE 1=0"
                    )
                    continue
                tmp = f"_tf_gate_{name}"
                self.db.register(tmp, df.to_arrow())
                self.db.execute(f"CREATE TABLE {name} AS SELECT * FROM {tmp}")
                self.db.unregister(tmp)
            except Exception as exc:  # noqa: BLE001
                logger.debug("gated financial view %s failed, empty: %s", name, exc)
                self._empty_parquet_view(name, glob)

        try:
            from app.services.kline_sync import get_adj_factor_df
        except Exception:  # noqa: BLE001
            get_adj_factor_df = None
        if get_adj_factor_df is not None:
            for asset_type, view_name, subdir in (
                ("stock", "adj_factor", "adj_factor"),
                ("etf", "adj_factor_etf", "adj_factor_etf"),
            ):
                path = self.data_dir / subdir / "all.parquet"
                if not path.exists():
                    continue
                glob = f"{d}/{subdir}/**/*.parquet"
                try:
                    df = get_adj_factor_df(self.data_dir, asset_type=asset_type)
                    self.db.execute(f"DROP VIEW IF EXISTS {view_name}")
                    self.db.execute(f"DROP TABLE IF EXISTS {view_name}")
                    if df is None or df.is_empty():
                        self.db.execute(
                            f"CREATE OR REPLACE VIEW {view_name} AS "
                            f"SELECT * FROM read_parquet('{glob}', union_by_name=true) WHERE 1=0"
                        )
                        continue
                    tmp = f"_tf_gate_{view_name}"
                    self.db.register(tmp, df.to_arrow())
                    self.db.execute(f"CREATE TABLE {view_name} AS SELECT * FROM {tmp}")
                    self.db.unregister(tmp)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("gated adj view %s failed, empty: %s", view_name, exc)
                    self._empty_parquet_view(view_name, glob)

        try:
            from app.services.kline_sync import daily_route, minute_route
        except Exception:  # noqa: BLE001
            daily_route = None
            minute_route = None
        if daily_route is None:
            self._empty_named_views((
                "kline_daily", "kline_enriched",
                "kline_index_daily", "kline_index_enriched",
                "kline_etf_daily", "kline_etf_enriched",
            ))
        if minute_route is None:
            self._empty_named_views(("kline_minute", "kline_etf_minute"))
        if get_financial_df is None:
            self._empty_named_views((
                "financials_metrics", "financials_income",
                "financials_balance_sheet", "financials_cash_flow",
                "financials_shares",
            ))
        if get_adj_factor_df is None:
            self._empty_named_views(("adj_factor", "adj_factor_etf"))
        if daily_route is not None:
            daily_token = daily_route()
            if self._has_parquet("kline_daily"):
                self._register_route_filtered_view(
                    "kline_daily",
                    f"{d}/kline_daily/**/*.parquet",
                    daily_token,
                )
            if self._has_parquet("kline_daily_enriched"):
                self._register_route_filtered_view(
                    "kline_enriched",
                    f"{d}/kline_daily_enriched/**/*.parquet",
                    daily_token,
                )
            if self._has_parquet("kline_index_daily"):
                self._register_route_filtered_view(
                    "kline_index_daily",
                    f"{d}/kline_index_daily/**/*.parquet",
                    daily_token,
                )
            if self._has_parquet("kline_index_enriched"):
                self._register_route_filtered_view(
                    "kline_index_enriched",
                    f"{d}/kline_index_enriched/**/*.parquet",
                    daily_token,
                )
            if self._has_parquet("kline_etf_daily"):
                self._register_route_filtered_view(
                    "kline_etf_daily",
                    f"{d}/kline_etf_daily/**/*.parquet",
                    daily_token,
                )
            if self._has_parquet("kline_etf_enriched"):
                self._register_route_filtered_view(
                    "kline_etf_enriched",
                    f"{d}/kline_etf_enriched/**/*.parquet",
                    daily_token,
                )
        if minute_route is not None:
            if self._has_parquet("kline_minute"):
                self._register_route_filtered_view(
                    "kline_minute",
                    f"{d}/kline_minute/**/*.parquet",
                    minute_route(),
                )
            if self._has_parquet("kline_etf_minute"):
                self._register_route_filtered_view(
                    "kline_etf_minute",
                    f"{d}/kline_etf_minute/**/*.parquet",
                    minute_route(),
                )

        try:
            from app.services.depth_service import depth_route
        except Exception:  # noqa: BLE001
            depth_route = None
        if depth_route is None:
            self._empty_named_views(("depth5",))
        if depth_route is not None:
            depth_globs: list[str] = []
            if self._has_parquet("depth5"):
                depth_globs.append(f"{d}/depth5/**/*.parquet")
            if self._has_parquet("sealed_l1"):
                depth_globs.append(f"{d}/sealed_l1/**/*.parquet")
            if depth_globs:
                self._register_route_filtered_view(
                    "depth5",
                    depth_globs if len(depth_globs) > 1 else depth_globs[0],
                    depth_route(),
                    leftover_public=False,
                )

    def _register_route_filtered_view(
        self,
        name: str,
        glob: str | list[str],
        route: str,
        *,
        leftover_public: bool = False,
    ) -> None:
        """Register a DuckDB view that hides stale other-route parquet.

        Untagged legacy files stay visible only for leftover TickFlow / public.
        ``leftover_public`` is unused by current leftover TickFlow contracts
        (silent sina / public L1 mix is closed).
        """
        if isinstance(glob, list):
            joined = ", ".join(f"'{g}'" for g in glob)
            source = f"read_parquet([{joined}], union_by_name=true)"
            first_glob = glob[0]
        else:
            source = f"read_parquet('{glob}', union_by_name=true)"
            first_glob = glob
        empty_sql = f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM {source} WHERE 1=0"
        pred = _route_sql_predicate(route, leftover_public=leftover_public)
        try:
            self.db.execute(f"DROP VIEW IF EXISTS {name}")
            self.db.execute(f"DROP TABLE IF EXISTS {name}")
        except Exception:  # noqa: BLE001
            pass
        if pred is None:
            try:
                self.db.execute(empty_sql)
            except Exception as exc:  # noqa: BLE001
                logger.debug("empty gated view %s skipped: %s", name, exc)
            return
        try:
            self.db.execute(
                f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM {source} WHERE {pred}"
            )
        except Exception:
            expected = (route or "").strip().lower()
            try:
                if expected in {"tickflow", "public"}:
                    self.db.execute(
                        f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM {source}"
                    )
                else:
                    self.db.execute(empty_sql)
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "gated view %s fallback skipped (%s): %s", name, first_glob, exc,
                )

    def _has_parquet(self, subdir: str) -> bool:
        return any((self.data_dir / subdir).rglob("*.parquet"))

    def _route_sensitive_view_globs(self) -> list[tuple[str, str]]:
        d = self.data_dir.as_posix()
        return [
            ("kline_daily", f"{d}/kline_daily/**/*.parquet"),
            ("kline_enriched", f"{d}/kline_daily_enriched/**/*.parquet"),
            ("kline_index_daily", f"{d}/kline_index_daily/**/*.parquet"),
            ("kline_index_enriched", f"{d}/kline_index_enriched/**/*.parquet"),
            ("kline_etf_daily", f"{d}/kline_etf_daily/**/*.parquet"),
            ("kline_etf_enriched", f"{d}/kline_etf_enriched/**/*.parquet"),
            ("kline_minute", f"{d}/kline_minute/**/*.parquet"),
            ("kline_etf_minute", f"{d}/kline_etf_minute/**/*.parquet"),
            ("adj_factor", f"{d}/adj_factor/**/*.parquet"),
            ("adj_factor_etf", f"{d}/adj_factor_etf/**/*.parquet"),
            ("depth5", f"{d}/depth5/**/*.parquet"),
            ("financials_metrics", f"{d}/financials/metrics/*.parquet"),
            ("financials_income", f"{d}/financials/income/*.parquet"),
            ("financials_balance_sheet", f"{d}/financials/balance_sheet/*.parquet"),
            ("financials_cash_flow", f"{d}/financials/cash_flow/*.parquet"),
            ("financials_shares", f"{d}/financials/shares/*.parquet"),
            ("instruments", f"{d}/instruments/**/*.parquet"),
            ("instruments_index", f"{d}/instruments_index/**/*.parquet"),
            ("instruments_etf", f"{d}/instruments_etf/**/*.parquet"),
            ("instruments_ext", f"{d}/instruments_ext/**/*.parquet"),
        ]

    def _empty_parquet_view(self, name: str, glob: str) -> None:
        """Hide leftover parquet when a route gate cannot be applied."""
        try:
            self.db.execute(f"DROP VIEW IF EXISTS {name}")
            self.db.execute(f"DROP TABLE IF EXISTS {name}")
        except Exception:  # noqa: BLE001
            pass
        try:
            self.db.execute(
                f"CREATE OR REPLACE VIEW {name} AS "
                f"SELECT * FROM read_parquet('{glob}', union_by_name=true) WHERE 1=0"
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("empty view %s skipped: %s", name, exc)

    def _empty_named_views(self, names: tuple[str, ...]) -> None:
        wanted = set(names)
        for name, glob in self._route_sensitive_view_globs():
            if name in wanted:
                self._empty_parquet_view(name, glob)

    def _fail_closed_route_views(self) -> None:
        """Empty route-sensitive DuckDB views so leftover SQL cannot leak."""
        for name, glob in self._route_sensitive_view_globs():
            self._empty_parquet_view(name, glob)

    def re_gate_catalog_views(self) -> None:
        """Re-apply route gates; empty leftover-visible views if gating throws."""
        try:
            self._register_gated_catalog_views()
        except Exception as exc:  # noqa: BLE001
            logger.warning("re-gate catalog views failed, fail-closed: %s", exc)
            self._fail_closed_route_views()

    def refresh_gated_views(self) -> None:
        """Refresh catalog views without an ungated leftover-visible window.

        Callers used to ``CREATE VIEW`` from raw ``**/*.parquet`` and only
        then re-gate. Concurrent SQL between those statements saw leftover
        TickFlow after a custom switch.
        """
        self.re_gate_catalog_views()
        try:
            self._register_unified_views()
        except Exception as exc:  # noqa: BLE001
            logger.debug("unified views after gated refresh failed: %s", exc)

    def _register_unified_views(self) -> None:
        """Register optional all-asset views when their backing parquet exists.

        Physical storage remains split for performance and compatibility. These
        views are convenience read models for new APIs/features.
        """
        daily_parts: list[str] = []
        enriched_parts: list[str] = []
        minute_parts: list[str] = []
        inst_parts: list[str] = []

        if self._has_parquet("kline_daily"):
            daily_parts.append("""
                SELECT symbol, date, open, high, low, close, volume, amount,
                       'stock' AS asset_type, 'tickflow' AS source
                FROM kline_daily
            """)
        if self._has_parquet("kline_index_daily"):
            daily_parts.append("""
                SELECT symbol, date, open, high, low, close, volume, amount,
                       'index' AS asset_type, 'tickflow' AS source
                FROM kline_index_daily
            """)
        if self._has_parquet("kline_etf_daily"):
            daily_parts.append("""
                SELECT symbol, date, open, high, low, close, volume, amount,
                       'etf' AS asset_type, 'tickflow' AS source
                FROM kline_etf_daily
            """)

        if self._has_parquet("kline_daily_enriched"):
            enriched_parts.append("SELECT *, 'stock' AS asset_type, 'tickflow' AS source FROM kline_enriched")
        if self._has_parquet("kline_index_enriched"):
            enriched_parts.append("SELECT *, 'index' AS asset_type, 'tickflow' AS source FROM kline_index_enriched")
        if self._has_parquet("kline_etf_enriched"):
            enriched_parts.append("SELECT *, 'etf' AS asset_type, 'tickflow' AS source FROM kline_etf_enriched")

        if self._has_parquet("kline_minute"):
            minute_parts.append("""
                SELECT symbol, datetime, open, high, low, close, volume, amount,
                       'stock' AS asset_type, 'tickflow' AS source
                FROM kline_minute
            """)
        if self._has_parquet("kline_etf_minute"):
            minute_parts.append("""
                SELECT symbol, datetime, open, high, low, close, volume, amount,
                       'etf' AS asset_type, 'tickflow' AS source
                FROM kline_etf_minute
            """)

        if self._has_parquet("instruments"):
            inst_parts.append("""
                SELECT symbol, name, code, exchange, 'stock' AS asset_type, 'tickflow' AS source
                FROM instruments
            """)
        if self._has_parquet("instruments_index"):
            inst_parts.append("""
                SELECT symbol, name, code, NULL AS exchange, 'index' AS asset_type, 'tickflow' AS source
                FROM instruments_index
                WHERE coalesce(asset_type, 'index') != 'etf'
            """)
        if self._has_parquet("instruments_etf"):
            inst_parts.append("""
                SELECT symbol, name, code, NULL AS exchange, 'etf' AS asset_type, 'tickflow' AS source
                FROM instruments_etf
            """)

        unions = {
            "kline_daily_all": daily_parts,
            "kline_enriched_all": enriched_parts,
            "kline_minute_all": minute_parts,
            "instruments_all": inst_parts,
        }
        for name, parts in unions.items():
            if not parts:
                continue
            try:
                self.db.execute(f"CREATE OR REPLACE VIEW {name} AS " + " UNION ALL BY NAME ".join(parts))
            except Exception as e:  # noqa: BLE001
                logger.debug("unified view %s skipped: %s", name, e)


class KlineRepository:
    """日 K / 分钟 K 的读写入口。"""

    def __init__(self, store: DataStore) -> None:
        self.store = store
        self.db = store.db
        self._lock = threading.Lock()
        # parquet 读-改-写锁; 与 DuckDB _lock 分开, 供分钟落盘与日K upsert 共用
        self._write_lock = threading.Lock()

        # ---- Polars 缓存 ----
        self._enriched_cache: pl.DataFrame | None = None       # 最新一天 (~5500行)
        self._enriched_cache_date: date | None = None
        self._enriched_cache_live: bool = False
        self._etf_enriched_cache_live: bool = False
        self._live_agg_cache: pl.DataFrame | None = None       # 预计算聚合表 (~5500行)
        self._live_agg_cache_date: date | None = None
        self._live_agg_check_date: date | None = None          # 上次跨日校验时的 today (快路径节流)
        self._instruments_cache: pl.DataFrame | None = None
        self._instruments_route: str | None = None
        # 完整 enriched 历史 (含所有指标, 供 filter_history 策略使用)
        self._enriched_history_cache: pl.DataFrame | None = None  # ~100万行
        self._enriched_history_start: date | None = None
        self._index_instruments_cache: pl.DataFrame | None = None
        self._index_instruments_route: str | None = None
        self._etf_enriched_cache: pl.DataFrame | None = None
        self._etf_enriched_cache_date: date | None = None
        self._etf_live_agg_cache: pl.DataFrame | None = None
        self._etf_live_agg_cache_date: date | None = None
        self._etf_instruments_cache: pl.DataFrame | None = None
        self._etf_instruments_route: str | None = None
        self._etf_symbol_set_cache: set[str] | None = None
        self._historical_shares_cache: pl.DataFrame | None = None
        self._historical_shares_mtime_ns: int | None = None
        self._historical_shares_route: str | None = None

        # parquet glob 路径
        self._enriched_glob = str(store.data_dir / "kline_daily_enriched" / "**" / "*.parquet")
        self._index_enriched_glob = str(store.data_dir / "kline_index_enriched" / "**" / "*.parquet")
        self._etf_enriched_glob = str(store.data_dir / "kline_etf_enriched" / "**" / "*.parquet")
        self._minute_glob = str(store.data_dir / "kline_minute" / "**" / "*.parquet")
        self._etf_minute_glob = str(store.data_dir / "kline_etf_minute" / "**" / "*.parquet")
        self._inst_glob = str(store.data_dir / "instruments" / "**" / "*.parquet")
        self._index_inst_glob = str(store.data_dir / "instruments_index" / "**" / "*.parquet")
        self._etf_inst_glob = str(store.data_dir / "instruments_etf" / "**" / "*.parquet")

    def execute_all(self, sql: str, params: list | None = None) -> list[tuple]:
        """线程安全的 SELECT → fetchall。DuckDB 单 connection 非线程安全，所有读路径须走此方法。"""
        with self._lock:
            return self.db.execute(sql, params or []).fetchall()

    def execute_one(self, sql: str, params: list | None = None) -> tuple | None:
        """线程安全的 SELECT → fetchone。"""
        with self._lock:
            return self.db.execute(sql, params or []).fetchone()

    # ================================================================
    # Polars 缓存管理
    # ================================================================

    def refresh_cache(self) -> None:
        """刷新 Polars 缓存。在 pipeline 完成后、服务启动时调用。"""
        self._refresh_instruments()
        self._refresh_index_instruments()
        self._refresh_etf_instruments()
        self._refresh_enriched()

    def clear_cache(self) -> None:
        """清空所有 Polars 内存缓存。

        与 refresh_cache 的区别: refresh_cache 在磁盘无数据时会提前 return,
        导致内存里的旧缓存残留 (clear 数据后看板仍显示旧数据的根因)。
        本方法无条件清空, 供清除数据/重置场景调用。
        """
        self._enriched_cache = None
        self._enriched_cache_date = None
        self._enriched_cache_live = False
        self._enriched_history_cache = None
        self._enriched_history_start = None
        self._live_agg_cache = None
        self._live_agg_cache_date = None
        self._live_agg_check_date = None
        self._instruments_cache = None
        self._instruments_route = None
        self._index_instruments_cache = None
        self._index_instruments_route = None
        self._etf_enriched_cache = None
        self._etf_enriched_cache_date = None
        self._etf_enriched_cache_live = False
        self._etf_live_agg_cache = None
        self._etf_live_agg_cache_date = None
        self._etf_instruments_cache = None
        self._etf_instruments_route = None
        self._etf_symbol_set_cache = None
        self._historical_shares_cache = None
        self._historical_shares_mtime_ns = None
        self._historical_shares_route = None

    def _refresh_enriched(self) -> None:
        """从 parquet 加载 enriched 最新日到内存 + 构建聚合表。

        enriched parquet 仅存 14 列基础数据。启动时读入历史数据并即时计算完整指标，
        将结果缓存在内存中供各服务使用。

        优化: 扩大历史读取范围, 同时缓存完整历史 (含指标), 供 filter_history 策略直接复用。
        """
        try:
            from app.services.kline_sync import filter_daily_cache, scan_usable_daily

            latest = self.latest_enriched_date("stock")
            if not latest:
                # 磁盘已无数据: 必须清空内存缓存, 否则旧数据会残留
                # (清数据后看板仍显示旧数据的根因)
                self.clear_cache()
                return

            # Step 1: 直接读最新日期的分区文件 (仅 14 列)
            enriched_dir = self.store.data_dir / "kline_daily_enriched"
            ds = latest.isoformat() if hasattr(latest, "isoformat") else str(latest)
            target_parquet = enriched_dir / f"date={ds}" / "part.parquet"

            if not target_parquet.exists():
                self.clear_cache()
                return

            df_latest = filter_daily_cache(pl.read_parquet(target_parquet))
            if df_latest.is_empty():
                # Route switch left only leftover TickFlow in the "latest"
                # file: drop pre-switch in-memory enriched instead of serving it.
                self.clear_cache()
                return

            # Step 2: 读近 300 天 14 列数据 → compute → filter(latest) → 缓存
            # 300 日历天 ≈ 210 交易日, 覆盖 filter_history 最大 lookback(90) + warmup(60)
            try:
                from datetime import timedelta
                from app.indicators.pipeline import compute_enriched_history_window
                start_full = latest - timedelta(days=300)
                read_cols = [c for c in ["symbol", "date", "open", "high", "low", "close",
                                         "volume", "amount", "raw_close", "raw_high", "raw_low",
                                         "route"]
                             if c in df_latest.columns]
                lf = scan_usable_daily(
                    self.store.data_dir, table="kline_daily_enriched",
                )
                if lf is None:
                    self.clear_cache()
                    return
                lf = lf.filter(pl.col("date") >= start_full).sort(["symbol", "date"])
                df_hist = filter_daily_cache(lf.select(read_cols).collect())
                if not df_hist.is_empty():
                    instruments = self._instruments_cache if self._instruments_cache is not None else pl.DataFrame()
                    # 分批执行 指标→偏离→信号→涨跌停; 与整帧顺序等价,
                    # 补上已 import 但未调用的 compute_enriched_history_window。
                    df_full = compute_enriched_history_window(
                        df_hist,
                        self.store.data_dir,
                        instruments=instruments,
                        historical_shares=(
                            self.get_historical_shares()
                            if instruments is not None and not instruments.is_empty()
                            else None
                        ),
                    )

                    # JOIN instruments 到完整历史 (filter_history/basic_filter 需要 name/股本等列)
                    if instruments is not None and not instruments.is_empty():
                        inst_cols = [c for c in ["name", "total_shares", "float_shares"]
                                     if c in instruments.columns and c not in df_full.columns]
                        if inst_cols:
                            df_full = df_full.join(
                                instruments.select(["symbol", *inst_cols]).unique(subset=["symbol"]),
                                on="symbol",
                                how="left",
                            )

                    # 缓存完整历史 (含指标+必要基础信息) 供 filter_history/backtest 直接复用
                    self._enriched_history_cache = df_full
                    self._enriched_history_start = df_full["date"].min()
                    logger.info("enriched 历史缓存: %d rows, %s ~ %s",
                                len(df_full), self._enriched_history_start, latest)

                    # 只取最新一天作为 enriched_cache
                    df_today = df_full.filter(pl.col("date") == latest)
                    if not df_today.is_empty():
                        self._enriched_cache = df_today
                        self._enriched_cache_date = latest
                        self._enriched_cache_live = False
                        # 构建盘中递推基准: 若最新分区是今天的实时盘中数据,
                        # 递推状态必须停在上一交易日, 不能把今天作为“昨日”。
                        self._build_live_agg(self._live_agg_baseline_date(latest))
                        logger.info("enriched 缓存已计算: %d 只, 日期 %s (即时计算)", len(df_today), latest)
                        return
            except Exception as e:  # noqa: BLE001
                logger.warning("enriched 即时计算失败, 使用原始 14 列缓存: %s", e)

            # 降级: 直接使用 14 列数据 + 构建 live_agg
            self._enriched_cache = df_latest
            self._enriched_cache_date = latest
            self._enriched_cache_live = False
            self._build_live_agg(self._live_agg_baseline_date(latest))

            logger.info("enriched 缓存已加载: %d 只, 日期 %s", len(df_latest), latest)
        except Exception as e:  # noqa: BLE001
            logger.warning("enriched 缓存刷新失败: %s", e)

    def _build_live_agg(self, latest: date) -> None:
        """从 OHLCV 即时计算递推状态 + 窗口聚合, 构建盘中实时聚合表。

        优化: 优先使用 _enriched_history_cache (启动时已计算), 避免重复 compute_indicators。
        """
        from datetime import timedelta
        from app.indicators.pipeline import _ema_alpha

        start_60d = latest - timedelta(days=90)  # 日历90天 ≈ 60个交易日

        # 优先使用已有的历史缓存 (避免重复 scan_parquet + compute_indicators)
        hist_all = self._usable_history_cache()
        if hist_all is not None and not hist_all.is_empty():
            if "date" in hist_all.columns and hist_all["date"].min() <= start_60d:
                # 从历史缓存中提取所需列 (历史缓存已有指标列)
                base_cols = ["symbol", "date", "open", "high", "low", "close", "volume",
                             "raw_close", "raw_high", "raw_low"]
                needed = [c for c in base_cols if c in hist_all.columns]
                df_hist = hist_all.filter(
                    (pl.col("date") >= start_60d) & (pl.col("date") <= latest)
                ).select(needed).sort(["symbol", "date"])

                # 用历史缓存的指标列提取最新日状态 (无需再次 compute_indicators)
                state_source = hist_all.filter(pl.col("date") == latest)

                state_cols = [
                    "symbol",
                    "ema5", "ema10", "ema20", "ema30", "ema60",
                    "macd_dea",
                    "kdj_k", "kdj_d",
                    "atr_14",
                    "close", "high", "low",
                    "annual_vol_20d",
                ]
                existing_state = [c for c in state_cols if c in state_source.columns]
                agg_a = state_source.select(existing_state)
            else:
                df_hist = pl.DataFrame()
                agg_a = pl.DataFrame()
        else:
            # 降级: 读 parquet + compute_indicators
            df_hist, agg_a = self._build_live_agg_from_parquet(latest, start_60d)

        if df_hist.is_empty():
            self._live_agg_cache = pl.DataFrame()
            self._live_agg_cache_date = None
            return

        if agg_a.is_empty():
            self._live_agg_cache = pl.DataFrame()
            self._live_agg_cache_date = None
            return

        # 单独计算 _ema12 / _ema26 (compute_indicators 内部会 drop 掉)
        df_ema = df_hist.sort(["symbol", "date"]).with_columns([
            pl.col("close").ewm_mean(alpha=_ema_alpha(12), adjust=False).over("symbol").alias("_ema12"),
            pl.col("close").ewm_mean(alpha=_ema_alpha(26), adjust=False).over("symbol").alias("_ema26"),
        ]).filter(pl.col("date") == latest).select("symbol", "_ema12", "_ema26")

        agg_a = agg_a.join(df_ema, on="symbol", how="inner")

        # 单独计算 RSI 状态列 (compute_indicators 内部会 drop 掉)
        df_rsi_base = df_hist.sort(["symbol", "date"]).with_columns(
            pl.col("close").diff().over("symbol").alias("_daily_delta")
        )
        gain = pl.when(pl.col("_daily_delta") > 0).then(pl.col("_daily_delta")).otherwise(0.0)
        loss = pl.when(pl.col("_daily_delta") < 0).then(-pl.col("_daily_delta")).otherwise(0.0)
        rsi_exprs = []
        for n in (6, 14, 24):
            a = 1.0 / n
            rsi_exprs.append(gain.ewm_mean(alpha=a, adjust=False).over("symbol").alias(f"_rsi_avg_gain_{n}"))
            rsi_exprs.append(loss.ewm_mean(alpha=a, adjust=False).over("symbol").alias(f"_rsi_avg_loss_{n}"))
        df_rsi = (
            df_rsi_base
            .with_columns(rsi_exprs)
            .filter(pl.col("date") == latest)
            .select("symbol", *[f"_rsi_avg_gain_{n}" for n in (6, 14, 24)],
                              *[f"_rsi_avg_loss_{n}" for n in (6, 14, 24)])
        )
        agg_a = agg_a.join(df_rsi, on="symbol", how="inner")

        # 前复权因子: adj_factor = close(复权) / raw_close(原始)
        if "raw_close" in df_hist.columns:
            adj_factor_df = (
                df_hist.filter(pl.col("date") == latest)
                .select("symbol", (pl.col("close") / pl.col("raw_close")).alias("_adj_factor"))
            )
            agg_a = agg_a.join(adj_factor_df, on="symbol", how="left")
            if "_adj_factor" in agg_a.columns:
                agg_a = agg_a.with_columns(pl.col("_adj_factor").fill_null(1.0))

        # annual_vol_20d 递推状态: 最近 19 天日收益率的部分和 / 平方和
        df_daily_pct = (
            df_hist.sort(["symbol", "date"])
            .with_columns(
                pl.col("close").pct_change().over("symbol").alias("_daily_pct")
            )
        )
        df_vol = df_daily_pct.group_by("symbol").agg([
            pl.col("_daily_pct").tail(19).sum().alias("_vol_19d_pct_sum"),
            (pl.col("_daily_pct") ** 2).tail(19).sum().alias("_vol_19d_pct_sq_sum"),
        ])
        agg_a = agg_a.join(df_vol, on="symbol", how="left")

        # 昨日连板数: 从当前 route 可用 enriched 取 (用于增量计算同向 +1)
        from app.services.kline_sync import daily_partition_usable, filter_daily_cache

        consec_part = (
            self.store.data_dir / "kline_daily_enriched"
            / f"date={latest.isoformat()}" / "part.parquet"
        )
        if consec_part.exists() and daily_partition_usable(consec_part):
            consec_df = filter_daily_cache(pl.read_parquet(consec_part))
            consec_cols = [
                c for c in ["symbol", "consecutive_limit_ups", "consecutive_limit_downs"]
                if c in consec_df.columns
            ]
            if len(consec_cols) == 3 and not consec_df.is_empty():
                consec = consec_df.select(
                    "symbol",
                    pl.col("consecutive_limit_ups").alias("_prev_consec_up"),
                    pl.col("consecutive_limit_downs").alias("_prev_consec_down"),
                )
                agg_a = agg_a.join(consec, on="symbol", how="left")

        # B类: 按 symbol 分组聚合 — 窗口统计
        agg_b = (
            df_hist.sort(["symbol", "date"])
            .group_by("symbol")
            .agg([
                pl.col("close").tail(4).sum().alias("_ma5_partial_sum"),
                pl.col("close").tail(9).sum().alias("_ma10_partial_sum"),
                pl.col("close").tail(19).sum().alias("_ma20_partial_sum"),
                pl.col("close").tail(29).sum().alias("_ma30_partial_sum"),
                pl.col("close").tail(59).sum().alias("_ma60_partial_sum"),

                pl.col("close").tail(19).sum().alias("_boll_partial_sum"),
                (pl.col("close").tail(19) ** 2).sum().alias("_boll_partial_sq_sum"),

                pl.col("high").tail(59).max().alias("_high_59d"),
                pl.col("low").tail(59).min().alias("_low_59d"),

                pl.col("close").tail(5).first().alias("_close_5d_ago"),
                pl.col("close").tail(10).first().alias("_close_10d_ago"),
                pl.col("close").tail(20).first().alias("_close_20d_ago"),
                pl.col("close").tail(30).first().alias("_close_30d_ago"),
                pl.col("close").tail(60).first().alias("_close_60d_ago"),

                pl.col("volume").tail(4).sum().alias("_vol_ma5_partial_sum"),
                pl.col("volume").tail(9).sum().alias("_vol_ma10_partial_sum"),

                pl.col("low").tail(8).min().alias("_kdj_8d_low"),
                pl.col("high").tail(8).max().alias("_kdj_8d_high"),

                pl.col("close").tail(59).len().alias("_window_len"),
            ])
        )

        self._live_agg_cache = agg_a.join(agg_b, on="symbol", how="inner")
        self._live_agg_cache_date = latest

    def _live_agg_baseline_date(self, latest: date) -> date:
        """盘中递推基准日期。当天实时分区存在时使用上一可用交易日。"""
        if latest != date.today():
            return latest
        # File provenance, not DuckDB: a temporarily ungated view can
        # still expose leftover TickFlow as the previous official day.
        try:
            from app.services.kline_sync import safe_usable_daily_partition_dates

            dates = safe_usable_daily_partition_dates(
                self.store.data_dir, table="kline_daily_enriched",
            )
            prior = [day for day in dates if day < latest]
            if prior:
                return prior[-1]
        except Exception:  # noqa: BLE001
            pass
        return latest

    def _build_live_agg_from_parquet(self, latest: date, start_60d: date) -> tuple[pl.DataFrame, pl.DataFrame]:
        """降级路径: 从 parquet 读取数据并计算指标 (当 _enriched_history_cache 不可用时)。"""
        from app.indicators.pipeline import compute_indicators
        from app.services.kline_sync import filter_daily_cache, scan_usable_daily

        lf = scan_usable_daily(self.store.data_dir, table="kline_daily_enriched")
        if lf is None:
            return pl.DataFrame(), pl.DataFrame()
        lf = (
            lf.filter(pl.col("date") >= start_60d)
            .filter(pl.col("date") <= latest)
            .sort(["symbol", "date"])
        )

        read_cols = [c for c in ["symbol", "date", "open", "high", "low", "close", "volume",
                                 "raw_close", "raw_high", "raw_low", "route"]
                     if c in lf.collect_schema().names()]
        df_hist = filter_daily_cache(
            guarded_collect(lf.select(read_cols), priority="background")
        )

        if df_hist.is_empty():
            return df_hist, pl.DataFrame()

        df_with_indicators = compute_indicators(df_hist)

        state_cols = [
            "symbol",
            "ema5", "ema10", "ema20", "ema30", "ema60",
            "macd_dea",
            "kdj_k", "kdj_d",
            "atr_14",
            "close", "high", "low",
            "annual_vol_20d",
        ]
        existing_state = [c for c in state_cols if c in df_with_indicators.columns]
        agg_a = df_with_indicators.filter(pl.col("date") == latest).select(existing_state)

        return df_hist, agg_a

    def _refresh_etf_enriched(self) -> None:
        """从 ETF enriched parquet 加载最新日到内存缓存。"""
        try:
            from app.services.kline_sync import (
                filter_daily_cache,
                safe_usable_daily_partition_dates,
                scan_usable_daily,
            )

            enriched_dir = self.store.data_dir / "kline_etf_enriched"
            dates = safe_usable_daily_partition_dates(
                self.store.data_dir, table="kline_etf_enriched",
            )
            if not dates:
                self._etf_enriched_cache = None
                self._etf_enriched_cache_date = None
                self._etf_enriched_cache_live = False
                return
            latest = dates[-1]
            target_parquet = enriched_dir / f"date={latest.isoformat()}" / "part.parquet"
            df_latest = filter_daily_cache(pl.read_parquet(target_parquet))
            if df_latest.is_empty():
                self._etf_enriched_cache = None
                self._etf_enriched_cache_date = None
                self._etf_enriched_cache_live = False
                return

            from datetime import timedelta
            from app.indicators.pipeline import compute_indicators, compute_signals
            start_full = latest - timedelta(days=300)
            read_cols = [c for c in ["symbol", "date", "open", "high", "low", "close",
                                     "volume", "amount", "raw_close", "raw_high", "raw_low",
                                     "route"]
                         if c in df_latest.columns]
            lf = scan_usable_daily(self.store.data_dir, table="kline_etf_enriched")
            if lf is None:
                self._etf_enriched_cache = None
                self._etf_enriched_cache_date = None
                self._etf_enriched_cache_live = False
                return
            df_hist = filter_daily_cache(
                guarded_collect(
                    lf.filter(pl.col("date") >= start_full)
                    .select(read_cols)
                    .sort(["symbol", "date"]),
                    priority="background",
                )
            )
            if df_hist.is_empty():
                self._etf_enriched_cache = df_latest.sort(["symbol"])
            else:
                df_full = compute_signals(compute_indicators(df_hist))
                self._etf_enriched_cache = df_full.filter(pl.col("date") == latest).sort(["symbol"])
            self._etf_enriched_cache_date = latest
            self._etf_enriched_cache_live = False
        except Exception as e:  # noqa: BLE001
            logger.debug("ETF enriched 缓存刷新跳过: %s", e)

    def _refresh_instruments(self) -> None:
        """加载当前 daily route 的 instruments。切源后不复用 leftover TickFlow。"""
        try:
            from app.services.instrument_sync import filter_instruments, instrument_route

            route = instrument_route()
            df = guarded_collect(pl.scan_parquet(self._inst_glob), priority="background")
            df = filter_instruments(df, route)
            self._instruments_cache = df if df is not None and not df.is_empty() else pl.DataFrame()
            self._instruments_route = route
            if not self._instruments_cache.is_empty():
                logger.info("instruments 缓存已加载: %d 只", len(self._instruments_cache))
        except Exception as e:  # noqa: BLE001
            logger.warning("instruments 缓存刷新失败: %s", e)
            self._instruments_cache = pl.DataFrame()
            self._instruments_route = "unresolved"

    def _refresh_index_instruments(self) -> None:
        """加载当前 daily route 的指数 instruments。"""
        try:
            from app.services.instrument_sync import filter_instruments, instrument_route

            route = instrument_route()
            df = guarded_collect(pl.scan_parquet(self._index_inst_glob), priority="background")
            df = filter_instruments(df, route)
            self._index_instruments_cache = df if df is not None and not df.is_empty() else pl.DataFrame()
            self._index_instruments_route = route
            if not self._index_instruments_cache.is_empty():
                logger.info("index instruments 缓存已加载: %d 只", len(self._index_instruments_cache))
        except Exception as e:  # noqa: BLE001
            logger.debug("index instruments 缓存刷新跳过: %s", e)
            self._index_instruments_cache = pl.DataFrame()
            self._index_instruments_route = "unresolved"

    def _refresh_etf_instruments(self) -> None:
        """加载 ETF instruments 到内存；兼容旧版 instruments_index 中的 ETF。"""
        parts: list[pl.DataFrame] = []
        try:
            df = guarded_collect(pl.scan_parquet(self._etf_inst_glob), priority="background")
            if not df.is_empty():
                parts.append(df)
        except Exception as e:  # noqa: BLE001
            logger.debug("etf instruments 缓存刷新跳过(new): %s", e)
        try:
            legacy = self.get_index_instruments()
            if not legacy.is_empty() and "asset_type" in legacy.columns:
                legacy = legacy.filter(pl.col("asset_type") == "etf")
                if not legacy.is_empty():
                    parts.append(legacy)
        except Exception as e:  # noqa: BLE001
            logger.debug("etf instruments legacy fallback skipped: %s", e)
        if parts:
            from app.services.instrument_sync import filter_instruments, instrument_route

            route = instrument_route()
            df_all = filter_instruments(
                pl.concat(parts, how="diagonal_relaxed").unique(subset=["symbol"], keep="last").sort("symbol"),
                route,
            )
            self._etf_instruments_cache = df_all
            self._etf_instruments_route = route
            self._etf_symbol_set_cache = None
            if df_all is not None and not df_all.is_empty():
                logger.info("ETF instruments 缓存已加载: %d 只", len(df_all))
        else:
            self._etf_instruments_cache = pl.DataFrame()
            self._etf_instruments_route = None

    def _live_enriched_overlay_allowed(self) -> bool:
        try:
            from app.services.kline_sync import live_enriched_overlay_allowed
            return live_enriched_overlay_allowed()
        except Exception:  # noqa: BLE001
            return False

    def get_enriched_latest(self) -> tuple[pl.DataFrame, date | None]:
        """返回缓存的 enriched 最新日 DataFrame + 日期。如无缓存则懒加载。"""
        if self._enriched_cache_live and not self._live_enriched_overlay_allowed():
            self._enriched_cache = None
            self._enriched_cache_date = None
            self._enriched_cache_live = False
            self._refresh_enriched()
        if self._enriched_cache is None or not self._latest_cache_usable(self._enriched_cache):
            if self._enriched_cache is not None:
                self._enriched_cache = None
                self._enriched_cache_date = None
                self._enriched_cache_live = False
            self._refresh_enriched()
        return self._gate_cached_frame(self._enriched_cache, self._enriched_cache_date)

    def get_enriched_latest_asset(
        self,
        asset_type: str,
        refresh: bool = True,
    ) -> tuple[pl.DataFrame, date | None]:
        """按资产类型返回最新 enriched 缓存。stock 保持旧缓存语义。

        refresh=False: 缓存冷时不触发同步 _refresh_etf_enriched。
        供行情轮询热路径使用, 避免无 ETF 实时数据时白付全量重算。
        """
        if asset_type == "stock":
            return self.get_enriched_latest()
        if asset_type == "etf":
            if self._etf_enriched_cache_live and not self._live_enriched_overlay_allowed():
                self._etf_enriched_cache = None
                self._etf_enriched_cache_date = None
                self._etf_enriched_cache_live = False
                if refresh:
                    self._refresh_etf_enriched()
            if self._etf_enriched_cache is None or not self._latest_cache_usable(
                self._etf_enriched_cache,
            ):
                if self._etf_enriched_cache is not None:
                    self._etf_enriched_cache = None
                    self._etf_enriched_cache_date = None
                    self._etf_enriched_cache_live = False
                if refresh:
                    self._refresh_etf_enriched()
            return self._gate_cached_frame(
                self._etf_enriched_cache, self._etf_enriched_cache_date,
            )
        return pl.DataFrame(), None

    def _latest_cache_usable(self, cached: pl.DataFrame | None) -> bool:
        if cached is None or getattr(cached, "is_empty", lambda: True)():
            return False
        try:
            from app.services.kline_sync import daily_cache_usable, daily_route

            return daily_cache_usable(cached, daily_route())
        except Exception:  # noqa: BLE001
            return False

    def _gate_cached_frame(
        self,
        cached: pl.DataFrame | None,
        cache_date: date | None,
    ) -> tuple[pl.DataFrame, date | None]:
        """Hide leftover TickFlow in-memory latest after a custom switch."""
        if cached is None:
            return pl.DataFrame(), cache_date
        try:
            from app.services.kline_sync import filter_daily_cache

            filtered = filter_daily_cache(cached)
        except Exception:  # noqa: BLE001
            return pl.DataFrame(), None
        if filtered is None or filtered.is_empty():
            return pl.DataFrame(), None
        return filtered, cache_date

    def get_enriched_history(self, target_date: date, lookback_days: int) -> pl.DataFrame | None:
        """返回预计算的 enriched 历史数据 (仅 lookback 范围, 不含 warmup)。

        warmup 部分在 _refresh_enriched 计算指标时已使用, 策略只需要最终的 lookback 窗口。
        返回 ~33万行 (90日历天) 而非 ~107万行, filter_history 策略的 group_by 快 20x+。
        """
        cache = self._enriched_history_cache
        if cache is None or cache.is_empty():
            return None
        if "date" not in cache.columns:
            return None
        cache_max = cache["date"].max()
        cache_min = cache["date"].min()
        from datetime import timedelta
        # 验证缓存覆盖完整范围 (含 warmup)
        warmup_start = target_date - timedelta(days=(lookback_days + 60) * 2)
        if cache_min > warmup_start or cache_max < target_date:
            return None
        # 只返回 lookback 范围 (日历天数 ≈ 2/3 交易日, 足够覆盖)
        lookback_start = target_date - timedelta(days=lookback_days)
        from app.services.kline_sync import filter_daily_cache

        try:
            filtered = filter_daily_cache(
                cache.filter((pl.col("date") >= lookback_start) & (pl.col("date") <= target_date))
            )
        except Exception:  # noqa: BLE001
            return None
        if filtered is None or filtered.is_empty():
            return None
        return filtered

    def get_enriched_range(
        self,
        start: date,
        end: date,
        symbols: list[str] | None = None,
        columns: list[str] | None = None,
    ) -> pl.DataFrame | None:
        """从预计算 enriched 历史缓存返回完整区间；缓存不覆盖时返回 None。"""
        if self._enriched_history_cache is None:
            self._refresh_enriched()
        cache = self._enriched_history_cache
        if cache is None or cache.is_empty() or "date" not in cache.columns:
            return None

        cache_min = cache["date"].min()
        cache_max = cache["date"].max()
        if cache_min > start or cache_max < end:
            return None

        from app.services.kline_sync import filter_daily_cache

        try:
            df = filter_daily_cache(
                cache.filter((pl.col("date") >= start) & (pl.col("date") <= end))
            )
        except Exception:  # noqa: BLE001
            return None
        if df is None or df.is_empty():
            return None
        if symbols is not None:
            df = df.filter(pl.col("symbol").is_in(symbols))
            if df.is_empty():
                return None
        if columns and not df.is_empty():
            existing = [c for c in columns if c in df.columns]
            if "symbol" not in existing and "symbol" in df.columns:
                existing.insert(0, "symbol")
            if "date" not in existing and "date" in df.columns:
                existing.insert(1, "date")
            df = df.select(existing)
        return df.sort(["symbol", "date"])

    def get_live_agg(self) -> pl.DataFrame:
        """返回盘中实时指标预计算聚合表。如无缓存则懒加载。

        live_agg 的核心列 _prev_consec_up/down (昨日连板数) 取自基准日 enriched。
        基准日由 _live_agg_baseline_date 决定: 盘中(today 有实时分区) 取上一交易日,
        非盘中(磁盘最新日 < today) 取该最新日本身。一旦跨日, 期望基准日会前移,
        旧缓存会把连板数整体少算一档, 故这里除首次懒加载外还要校验基准日是否仍
        符合当前预期, 不符则重建 (无需等盘后管道刷缓存)。

        性能: get_live_agg 被每轮实时行情调用 (expert 档 1s 一次)。跨日只在
        date.today() 翻天时发生, 故先用 today 做廉价的 fast-path (μs 级),
        仅当 today 变化时才查磁盘确认 (DuckDB 扫 132 万行约 100ms+) 并按需重建。
        """
        if self._live_agg_cache is not None and not self._live_agg_usable():
            self._live_agg_cache = None
            self._live_agg_cache_date = None
        if self._live_agg_cache is None:
            self._refresh_enriched()
            self._live_agg_check_date = date.today()  # 刚建过, 当天不必再查磁盘
        else:
            today = date.today()
            if self._live_agg_check_date != today:
                # today 翻天了 (次日开盘首次轮询): 校验基准日是否需要前移重建。
                # 同一天内多次调用直接跳过, 避免每轮都扫 parquet。
                self._live_agg_check_date = today
                disk_latest = self.latest_enriched_date("stock")
                if disk_latest is not None:
                    expected = self._live_agg_baseline_date(disk_latest)
                    if self._live_agg_cache_date != expected:
                        logger.info(
                            "live_agg 跨日失效, 重建: 缓存基准=%s, 期望基准=%s",
                            self._live_agg_cache_date, expected,
                        )
                        self._refresh_enriched()
        if self._live_agg_cache is None:
            return pl.DataFrame()
        return self._live_agg_cache

    def get_instruments(self) -> pl.DataFrame:
        """返回当前 daily route 的 instruments。切源后不复用 leftover。"""
        try:
            from app.services.instrument_sync import instrument_route

            route = instrument_route()
        except Exception:  # noqa: BLE001
            route = "unresolved"
        if self._instruments_cache is None or self._instruments_route != route:
            self._refresh_instruments()
        if self._instruments_cache is None:
            return pl.DataFrame()
        return self._instruments_cache

    def get_historical_shares(self) -> pl.DataFrame:
        """读取财务股本历史，并在文件或财务 route 变化后刷新缓存。

        regime_builder / compute_enriched_history_window 的实际依赖;
        无股本文件时返回空表, 不阻塞环境补算。切源后同一 mtime 不能复用 leftover。
        """
        path = self.store.data_dir / "financials" / "shares" / "part.parquet"
        mtime_ns = path.stat().st_mtime_ns if path.exists() else None
        try:
            from app.services.financial_sync import financial_write_route

            route_token = financial_write_route()
        except Exception:  # noqa: BLE001
            route_token = "unresolved"
        if (
            self._historical_shares_cache is None
            or mtime_ns != self._historical_shares_mtime_ns
            or self._historical_shares_route != route_token
        ):
            if route_token == "unresolved":
                self._historical_shares_cache = pl.DataFrame()
            else:
                from app.share_capital import load_share_history

                self._historical_shares_cache = load_share_history(self.store.data_dir)
            self._historical_shares_mtime_ns = mtime_ns
            self._historical_shares_route = route_token
        return self._historical_shares_cache

    def get_index_instruments(self) -> pl.DataFrame:
        """返回当前 daily route 的指数 instruments。"""
        try:
            from app.services.instrument_sync import instrument_route

            route = instrument_route()
        except Exception:  # noqa: BLE001
            route = "unresolved"
        if self._index_instruments_cache is None or self._index_instruments_route != route:
            self._refresh_index_instruments()
        if self._index_instruments_cache is None:
            return pl.DataFrame()
        return self._index_instruments_cache

    def get_etf_instruments(self) -> pl.DataFrame:
        """返回当前 daily route 的 ETF instruments。"""
        try:
            from app.services.instrument_sync import instrument_route

            route = instrument_route()
        except Exception:  # noqa: BLE001
            route = "unresolved"
        if self._etf_instruments_cache is None or self._etf_instruments_route != route:
            self._refresh_etf_instruments()
        if self._etf_instruments_cache is None:
            return pl.DataFrame()
        return self._etf_instruments_cache

    def get_etf_symbol_set(self) -> set[str]:
        """返回已缓存 ETF symbol 集合 (memo, 随 instruments 缓存失效)。"""
        if self._etf_symbol_set_cache is None:
            df = self.get_etf_instruments()
            if df.is_empty() or "symbol" not in df.columns:
                self._etf_symbol_set_cache = set()
            else:
                self._etf_symbol_set_cache = set(df["symbol"].cast(pl.Utf8).to_list())
        return self._etf_symbol_set_cache

    def get_instruments_asset(self, asset_type: str) -> pl.DataFrame:
        """按资产类型返回 instruments；老 stock 路径保持原样。"""
        if asset_type == "stock":
            return self.get_instruments()
        if asset_type == "index":
            df = self.get_index_instruments()
            if not df.is_empty() and "asset_type" in df.columns:
                return df.filter(pl.col("asset_type") != "etf")
            return df
        if asset_type == "etf":
            return self.get_etf_instruments()
        return pl.DataFrame()

    def get_index_symbol_set(self) -> set[str]:
        """返回已缓存指数 symbol 集合。"""
        df = self.get_index_instruments()
        if df.is_empty() or "symbol" not in df.columns:
            return set()
        return set(df["symbol"].cast(pl.Utf8).to_list())

    def enriched_latest_date(self) -> date | None:
        """返回缓存中的 enriched 最新日期。"""
        return self._enriched_cache_date

    # ================================================================
    # 热路径: Polars 查询 (Chart / Screener / Signals / Intraday)
    # ================================================================

    def get_daily(
        self,
        symbol: str,
        start: date,
        end: date,
        columns: list[str] | None = None,
    ) -> pl.DataFrame:
        """单股日K查询 — 从14列parquet读取后即时计算指标。"""
        from datetime import timedelta

        # 快路径: 请求列全是 parquet 存储列 → scan + 列下推, 跳过 warmup 与全套指标。
        # 仍用 enriched_latest 覆盖最新日 (盘中更准)。缺列时回退完整计算路径。
        if columns:
            df = self._scan_daily_symbol(symbol, start, end, columns)
            if not df.is_empty() and all(c in df.columns for c in columns):
                cached, cache_date = self.get_enriched_latest()
                if cached is not None and not cached.is_empty() and cache_date:
                    if start <= cache_date <= end:
                        cached_part = self._filter_cached(cached, symbol, columns)
                        if not cached_part.is_empty():
                            df = df.filter(pl.col("date") != cache_date)
                            common_cols = [c for c in df.columns if c in cached_part.columns]
                            df = pl.concat([df.select(common_cols), cached_part.select(common_cols)])
                return df

        warmup_start = start - timedelta(days=150)

        # 优先复用预计算 enriched 历史缓存 (与回测引擎同源), 覆盖不足时再扫描。
        df = pl.DataFrame()
        hist = self._enriched_history_cache
        if hist is not None and not hist.is_empty() and "date" in hist.columns:
            hist_min = self._enriched_history_start
            hist_max = hist["date"].max()
            if hist_min is not None and hist_min <= start and hist_max >= start:
                from app.services.kline_sync import filter_daily_cache

                try:
                    df = filter_daily_cache(
                        hist.filter(
                            (pl.col("symbol") == symbol)
                            & (pl.col("date") >= start)
                            & (pl.col("date") <= end)
                        )
                    )
                except Exception:  # noqa: BLE001
                    df = pl.DataFrame()
        if df.is_empty():
            df = self._scan_daily_symbol(symbol, warmup_start, end, None)
            if not df.is_empty():
                df = self._compute_enriched_range(df)

        # 尝试用缓存数据覆盖最新日 (盘中更准确)
        cached, cache_date = self.get_enriched_latest()
        if not df.is_empty() and cached is not None and not cached.is_empty() and cache_date:
            if start <= cache_date <= end:
                cached_part = self._filter_cached(cached, symbol, None)
                if not cached_part.is_empty():
                    df = df.filter(pl.col("date") != cache_date)
                    common_cols = [c for c in df.columns if c in cached_part.columns]
                    df = pl.concat([df.select(common_cols), cached_part.select(common_cols)])

        # 裁剪到请求范围
        if not df.is_empty():
            df = df.filter((pl.col("date") >= start) & (pl.col("date") <= end))

        if columns and not df.is_empty():
            existing = [c for c in columns if c in df.columns]
            df = df.select(existing)

        return df

    def get_daily_batch(
        self,
        symbols: list[str],
        start: date,
        end: date,
        columns: list[str] | None = None,
    ) -> pl.DataFrame:
        """批量日K查询。"""
        cached, cache_date = self.get_enriched_latest()
        if cached is not None and not cached.is_empty() and cache_date:
            if start >= cache_date:
                return self._filter_cached_batch(cached, symbols, columns)

        # 回退 scan_parquet
        return self._scan_daily_batch(symbols, start, end, columns)

    def get_index_daily(
        self,
        symbol: str,
        start: date,
        end: date,
        columns: list[str] | None = None,
    ) -> pl.DataFrame:
        """指数日K查询 — 从独立指数 enriched parquet 读取后即时计算通用指标。"""
        from datetime import timedelta

        if columns:
            df = self._scan_index_daily_symbol(symbol, start, end, columns)
            if not df.is_empty() and all(c in df.columns for c in columns):
                return df

        warmup_start = start - timedelta(days=150)
        df = self._scan_index_daily_symbol(symbol, warmup_start, end, None)
        if not df.is_empty():
            df = self._compute_index_enriched_range(df)
            df = df.filter((pl.col("date") >= start) & (pl.col("date") <= end))
        if columns and not df.is_empty():
            existing = [c for c in columns if c in df.columns]
            df = df.select(existing)
        return df

    def get_etf_daily(
        self,
        symbol: str,
        start: date,
        end: date,
        columns: list[str] | None = None,
    ) -> pl.DataFrame:
        """ETF 日K查询 — 优先读独立 ETF enriched，兼容旧版 index enriched 中的 ETF。"""
        from datetime import timedelta

        if columns:
            df = self._scan_etf_daily_symbol(symbol, start, end, columns)
            if not df.is_empty() and all(c in df.columns for c in columns):
                return df

        warmup_start = start - timedelta(days=150)
        df = self._scan_etf_daily_symbol(symbol, warmup_start, end, None)
        if df.is_empty():
            # 旧版 ETF 曾存入 kline_index_enriched；没有独立数据时回退读取。
            df = self._scan_index_daily_symbol(symbol, warmup_start, end, None)
        if not df.is_empty():
            df = self._compute_index_enriched_range(df)
            df = df.filter((pl.col("date") >= start) & (pl.col("date") <= end))
        if columns and not df.is_empty():
            existing = [c for c in columns if c in df.columns]
            df = df.select(existing)
        return df

    def get_daily_asset(
        self,
        asset_type: str,
        symbol: str,
        start: date,
        end: date,
        columns: list[str] | None = None,
    ) -> pl.DataFrame:
        if asset_type == "stock":
            return self.get_daily(symbol, start, end, columns)
        if asset_type == "index":
            return self.get_index_daily(symbol, start, end, columns)
        if asset_type == "etf":
            return self.get_etf_daily(symbol, start, end, columns)
        return pl.DataFrame()

    def _scan_usable_minute(
        self,
        asset_type: str,
        *,
        symbol: str | None = None,
        symbols: list[str] | None = None,
        trade_date: date | None = None,
        start: date | None = None,
        end: date | None = None,
    ):
        """Scan current-route minute partitions only — leftover files must not poison collect."""
        from app.services.kline_sync import scan_usable_minute

        lf = scan_usable_minute(self.store.data_dir, asset_type=asset_type)
        if lf is None:
            return None
        pred = None
        if symbol is not None:
            pred = pl.col("symbol") == symbol
        elif symbols:
            pred = pl.col("symbol").is_in(symbols)
        if trade_date is not None:
            day = pl.col("datetime").dt.date() == trade_date
            pred = day if pred is None else pred & day
        elif start is not None or end is not None:
            day = pl.col("datetime").dt.date()
            rng = True
            if start is not None:
                rng = day >= start
            if end is not None:
                rng = rng & (day <= end)
            pred = rng if pred is None else pred & rng
        if pred is not None:
            lf = lf.filter(pred)
        sort_cols = ["symbol", "datetime"] if symbols or symbol is None else ["datetime"]
        if symbol is not None:
            sort_cols = ["datetime"]
        return lf.sort(sort_cols)

    def get_minute(
        self,
        symbol: str,
        trade_date: date,
        asset_type: str = "stock",
    ) -> pl.DataFrame:
        """分钟K查询 — 只扫当前 minute route 可用分区。"""
        from app.services.kline_sync import usable_minute_partition_paths

        paths = usable_minute_partition_paths(self.store.data_dir, asset_type=asset_type)
        if not paths:
            return pl.DataFrame()
        lf = self._scan_usable_minute(
            asset_type, symbol=symbol, trade_date=trade_date,
        )
        if lf is None:
            return pl.DataFrame()
        df = _collect_local_parquet(
            lambda: lf.collect(),
            str(self.store.data_dir / (
                "kline_etf_minute" if asset_type == "etf" else "kline_minute"
            ) / "**" / "*.parquet"),
            "分钟K读取失败",
        )
        return self._gate_minute_df(df)

    def get_minute_batch(
        self,
        symbols: list[str],
        trade_date: date,
        asset_type: str = "stock",
    ) -> pl.DataFrame:
        """批量分钟K查询 — 只扫当前 minute route 可用分区。"""
        if not symbols:
            return pl.DataFrame()
        lf = self._scan_usable_minute(
            asset_type, symbols=symbols, trade_date=trade_date,
        )
        if lf is None:
            return pl.DataFrame()
        try:
            df = guarded_collect(lf)
        except Exception as e:  # noqa: BLE001
            logger.warning("批量分钟K查询失败: %s", e)
            return pl.DataFrame()
        return self._gate_minute_df(df)

    def get_minute_range(
        self,
        symbols: list[str],
        start: date,
        end: date,
        asset_type: str = "stock",
    ) -> pl.DataFrame:
        """多日分钟K — 只扫当前 minute route 可用分区。"""
        if not symbols:
            return pl.DataFrame()
        lf = self._scan_usable_minute(
            asset_type, symbols=symbols, start=start, end=end,
        )
        if lf is None:
            return pl.DataFrame()
        try:
            df = guarded_collect(lf)
        except Exception as e:  # noqa: BLE001
            logger.warning("分钟K区间查询失败: %s", e)
            return pl.DataFrame()
        return self._gate_minute_df(df)

    def _gate_minute_df(self, df: pl.DataFrame) -> pl.DataFrame:
        """Refuse stale TickFlow/public minute bars after a minute-source switch."""
        try:
            from app.services.kline_sync import filter_minute_cache
            return filter_minute_cache(df)
        except Exception as exc:  # noqa: BLE001
            logger.warning("minute cache gate failed, fail-closed: %s", exc)
            if df is None or getattr(df, "is_empty", lambda: True)():
                return df if df is not None else pl.DataFrame()
            return df.head(0)

    # ================================================================
    # Polars 查询内部方法
    # ================================================================

    def _compute_enriched_range(self, df: pl.DataFrame) -> pl.DataFrame:
        """对14列enriched数据即时计算完整指标+信号。输入应含足够预热行数。"""
        from app.indicators.pipeline import compute_indicators, compute_signals, compute_limit_signals, filter_halt_days
        if df.is_empty() or df.height < 2:
            return df
        # 兜底过滤历史脏数据中的停牌日 (close 可能被填充为前收盘价)
        df = filter_halt_days(df)
        if df.is_empty() or df.height < 2:
            return df
        try:
            df = compute_indicators(df)
            df = compute_signals(df)
            instruments = self.get_instruments()
            df = compute_limit_signals(df, instruments)
        except Exception as e:  # noqa: BLE001
            logger.warning("on-demand compute failed: %s", e)
        return df

    def _compute_index_enriched_range(self, df: pl.DataFrame) -> pl.DataFrame:
        """指数只计算通用技术指标和通用信号，跳过涨跌停/股本/市值逻辑。"""
        from app.indicators.pipeline import compute_indicators, compute_signals
        if df.is_empty() or df.height < 2:
            return df
        try:
            df = compute_indicators(df)
            df = compute_signals(df)
        except Exception as e:  # noqa: BLE001
            logger.warning("index on-demand compute failed: %s", e)
        return df

    def _filter_cached(self, cached: pl.DataFrame, symbol: str, columns: list[str] | None) -> pl.DataFrame:
        from app.services.kline_sync import filter_daily_cache

        try:
            df = filter_daily_cache(cached)
        except Exception:  # noqa: BLE001
            return pl.DataFrame()
        if df is None or df.is_empty() or "symbol" not in df.columns:
            return pl.DataFrame()
        df = df.filter(pl.col("symbol") == symbol)
        if columns and not df.is_empty():
            existing = [c for c in columns if c in df.columns]
            df = df.select(existing)
        return df

    def _filter_cached_batch(self, cached: pl.DataFrame, symbols: list[str], columns: list[str] | None) -> pl.DataFrame:
        from app.services.kline_sync import filter_daily_cache

        try:
            df = filter_daily_cache(cached)
        except Exception:  # noqa: BLE001
            return pl.DataFrame()
        if df is None or df.is_empty() or "symbol" not in df.columns:
            return pl.DataFrame()
        df = df.filter(pl.col("symbol").is_in(symbols))
        if columns and not df.is_empty():
            existing = [c for c in columns if c in df.columns]
            df = df.select(existing)
        return df.sort(["symbol", "date"])

    def _usable_history_cache(self) -> pl.DataFrame | None:
        """In-memory hist only when it matches the current daily route."""
        cache = self._enriched_history_cache
        if cache is None or getattr(cache, "is_empty", lambda: True)():
            return None
        try:
            from app.services.kline_sync import filter_daily_cache

            filtered = filter_daily_cache(cache)
        except Exception:  # noqa: BLE001
            return None
        if filtered is None or filtered.is_empty():
            return None
        return filtered

    def _live_agg_usable(self) -> bool:
        """Refuse leftover TickFlow live-agg after a custom daily switch."""
        if self._live_agg_cache is None or getattr(self._live_agg_cache, "is_empty", lambda: True)():
            return False
        if self._enriched_history_cache is not None:
            return self._latest_cache_usable(self._enriched_history_cache)
        if self._enriched_cache is not None:
            return self._latest_cache_usable(self._enriched_cache)
        return False

    def _collect_gated_daily(self, lf, columns: list[str] | None) -> pl.DataFrame:
        """Collect a daily/enriched scan, hiding leftover other-route rows.

        Read/schema failures raise :class:`KlineReadError` so HTTP can 503
        instead of silent-empty. Route-filter failures stay fail-closed.
        """
        from app.services.kline_sync import filter_daily_cache

        try:
            schema_names = lf.collect_schema().names()
            keep_route = bool(columns) and "route" in columns
            if columns:
                existing = [c for c in columns if c in schema_names]
                if "route" in schema_names and "route" not in existing:
                    existing.append("route")
                if existing:
                    lf = lf.select(existing)
            raw = guarded_collect(lf)
        except Exception as exc:  # noqa: BLE001
            raise KlineReadError(f"日K读取失败: {exc}") from exc
        try:
            df = filter_daily_cache(raw)
        except Exception:  # noqa: BLE001
            return pl.DataFrame()
        if columns and not keep_route and df is not None and not df.is_empty() and "route" in df.columns:
            df = df.drop("route")
        return df

    def _scan_usable_enriched(
        self,
        table: str,
        start: date,
        end: date,
        columns: list[str] | None,
        *,
        symbol: str | None = None,
        symbols: list[str] | None = None,
    ) -> pl.DataFrame:
        """Scan current-route partitions only — leftover files must not poison collect."""
        from app.services.kline_sync import scan_usable_daily

        lf = scan_usable_daily(self.store.data_dir, table=table)
        if lf is None:
            return pl.DataFrame()
        pred = (pl.col("date") >= start) & (pl.col("date") <= end)
        if symbol is not None:
            lf = lf.filter(pred & (pl.col("symbol") == symbol)).sort("date")
        else:
            lf = lf.filter(pred & (pl.col("symbol").is_in(symbols or []))).sort(["symbol", "date"])
        return self._collect_gated_daily(lf, columns)

    def _scan_daily_symbol(self, symbol: str, start: date, end: date, columns: list[str] | None) -> pl.DataFrame:
        return self._scan_usable_enriched(
            "kline_daily_enriched", start, end, columns, symbol=symbol,
        )

    def _scan_daily_batch(self, symbols: list[str], start: date, end: date, columns: list[str] | None) -> pl.DataFrame:
        try:
            return self._scan_usable_enriched(
                "kline_daily_enriched", start, end, columns, symbols=symbols,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("日K批量查询失败: %s", e)
            return pl.DataFrame()

    def _scan_index_daily_symbol(self, symbol: str, start: date, end: date, columns: list[str] | None) -> pl.DataFrame:
        try:
            return self._scan_usable_enriched(
                "kline_index_enriched", start, end, columns, symbol=symbol,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("指数日K查询失败: %s", e)
            return pl.DataFrame()

    def _scan_etf_daily_symbol(self, symbol: str, start: date, end: date, columns: list[str] | None) -> pl.DataFrame:
        try:
            return self._scan_usable_enriched(
                "kline_etf_enriched", start, end, columns, symbol=symbol,
            )
        except Exception as e:  # noqa: BLE001
            logger.debug("ETF 日K查询跳过: %s", e)
            return pl.DataFrame()

    def _merge_cached_and_scan(
        self,
        cached: pl.DataFrame,
        cache_date: date,
        symbol: str,
        start: date,
        end: date,
        columns: list[str] | None,
    ) -> pl.DataFrame:
        """合并缓存部分 + scan 历史部分。

        历史部分用 strict < cache_date, 避免与缓存重复。
        两部分 schema 可能不一致 (增量 vs 全量), concat 前对齐列。
        """
        hist = self._scan_daily_symbol(symbol, start, cache_date, columns)
        cached_part = self._filter_cached(cached, symbol, columns)
        if hist.is_empty():
            return cached_part
        if cached_part.is_empty():
            return hist
        # 去重: 历史部分可能包含 cache_date, 去掉后再合并
        hist = hist.filter(pl.col("date") < cache_date)
        # 对齐列: 取交集, 统一类型
        common_cols = [c for c in hist.columns if c in cached_part.columns]
        hist = hist.select(common_cols)
        cached_part = cached_part.select(common_cols)
        # 统一类型: 历史可能是 Float64, 缓存可能是 Int64, 统一为 cast
        for c in common_cols:
            if hist[c].dtype != cached_part[c].dtype:
                # 统一到更宽的类型
                target = hist[c].dtype if hist.height > cached_part.height else cached_part[c].dtype
                hist = hist.with_columns(pl.col(c).cast(target))
                cached_part = cached_part.with_columns(pl.col(c).cast(target))
        return pl.concat([hist, cached_part])

    # ================================================================
    # DuckDB 查询 (冷路径: 统计/元数据/自定义SQL)
    # ================================================================

    def latest_minute_date(self, symbol: str, asset_type: str = "stock") -> date | None:
        """Newest route-usable minute date that contains ``symbol``.

        DuckDB ``kline_minute`` can be temporarily ungated; file provenance
        is the source of truth so a custom minute route cannot treat leftover
        TickFlow/public parquet as current coverage. ETF symbols read
        ``kline_etf_minute``, not the stock store.
        """
        from app.services.kline_sync import safe_usable_minute_partition_dates

        dates = safe_usable_minute_partition_dates(
            self.store.data_dir, asset_type=asset_type,
        )
        if not dates:
            return None
        wanted = str(symbol or "").strip()
        if not wanted:
            return dates[-1]
        subdir = "kline_etf_minute" if asset_type == "etf" else "kline_minute"
        for day in reversed(dates):
            part = self.store.data_dir / subdir / f"date={day.isoformat()}" / "part.parquet"
            try:
                frame = pl.read_parquet(part, columns=["symbol"])
            except Exception:  # noqa: BLE001
                continue
            if "symbol" not in frame.columns:
                continue
            if frame.filter(pl.col("symbol") == wanted).height:
                return day
        return None

    def earliest_daily_date(self) -> date | None:
        """Earliest route-usable local daily date (pipeline / extend start)."""
        from app.services.kline_sync import safe_usable_daily_partition_dates

        dates = safe_usable_daily_partition_dates(self.store.data_dir)
        return dates[0] if dates else None

    def earliest_minute_date(self) -> date | None:
        """Earliest route-usable local minute date."""
        from app.services.kline_sync import safe_usable_minute_partition_dates

        dates = safe_usable_minute_partition_dates(self.store.data_dir)
        return dates[0] if dates else None

    def latest_minute_date_global(self) -> date | None:
        """Newest route-usable local minute date (any symbol)."""
        from app.services.kline_sync import safe_usable_minute_partition_dates

        dates = safe_usable_minute_partition_dates(self.store.data_dir)
        return dates[-1] if dates else None

    def latest_daily_date(self) -> date | None:
        """Newest route-usable local daily date (pipeline incremental start)."""
        from app.services.kline_sync import safe_usable_daily_partition_dates

        dates = safe_usable_daily_partition_dates(self.store.data_dir)
        return dates[-1] if dates else None

    def _latest_enriched_date_duckdb(self) -> date | None:
        """File provenance only — DuckDB can be temporarily leftover-visible."""
        return self.latest_enriched_date("stock")

    def latest_enriched_date(self, asset_type: str = "stock") -> date | None:
        """Newest route-usable enriched partition date (mining / pipeline)."""
        from app.services.kline_sync import safe_usable_daily_partition_dates

        dates = safe_usable_daily_partition_dates(
            self.store.data_dir, table=enriched_dirname(asset_type),
        )
        return dates[-1] if dates else None

    def get_matrix_data_generation(self, asset_type: str = "stock") -> str:
        """挖掘/回测读到的 enriched 世代。发布中会抛 EnrichedGenerationUnavailableError。"""
        from app.enriched_generation import get_enriched_generation

        return get_enriched_generation(self.store.data_dir, asset_type)

    # ================================================================
    # 写入 (Pipeline / Sync)
    # ================================================================


    def append_daily(self, df: pl.DataFrame) -> None:
        """按日分区写入日K数据 (merge-upsert)。"""
        if df.is_empty():
            return
        self._write_daily_partition(df, "kline_daily")

    def append_enriched(self, df: pl.DataFrame) -> None:
        """按日分区写入 enriched 数据 (merge-upsert)。磁盘仅写入 14 列存储列。"""
        if df.is_empty():
            return
        from app.indicators.pipeline import ENRICHED_STORAGE_COLS
        storage_cols = [c for c in ENRICHED_STORAGE_COLS if c in df.columns]
        df_storage = df.select(storage_cols)
        self._write_daily_partition(df_storage, "kline_daily_enriched")

    def append_index_daily(self, df: pl.DataFrame) -> None:
        """按日分区写入指数日K数据 (merge-upsert)。"""
        if df.is_empty():
            return
        self._write_daily_partition(df, "kline_index_daily")

    def append_index_enriched(self, df: pl.DataFrame) -> None:
        """按日分区写入指数 enriched 数据。磁盘仅写入通用基础行情窄表。"""
        if df.is_empty():
            return
        from app.indicators.pipeline import ENRICHED_STORAGE_COLS
        storage_cols = [c for c in ENRICHED_STORAGE_COLS if c in df.columns]
        df_storage = df.select(storage_cols)
        self._write_daily_partition(df_storage, "kline_index_enriched")

    def append_etf_daily(self, df: pl.DataFrame) -> None:
        """按日分区写入 ETF 日K数据 (merge-upsert)。"""
        if df.is_empty():
            return
        self._write_daily_partition(df, "kline_etf_daily")

    def append_etf_enriched(self, df: pl.DataFrame) -> None:
        """按日分区写入 ETF enriched 数据。磁盘仅写入基础行情窄表。"""
        if df.is_empty():
            return
        from app.indicators.pipeline import ENRICHED_STORAGE_COLS
        storage_cols = [c for c in ENRICHED_STORAGE_COLS if c in df.columns]
        df_storage = df.select(storage_cols)
        self._write_daily_partition(df_storage, "kline_etf_enriched")

    def append_daily_asset(self, asset_type: str, df: pl.DataFrame) -> None:
        """按资产类型写入日K；stock/index 保持旧目录兼容。"""
        if asset_type == "stock":
            self.append_daily(df)
        elif asset_type == "index":
            self.append_index_daily(df)
        elif asset_type == "etf":
            self.append_etf_daily(df)

    def append_enriched_asset(self, asset_type: str, df: pl.DataFrame) -> None:
        """按资产类型写入 enriched；stock/index 保持旧目录兼容。"""
        if asset_type == "stock":
            self.append_enriched(df)
        elif asset_type == "index":
            self.append_index_enriched(df)
        elif asset_type == "etf":
            self.append_etf_enriched(df)

    def write_quote_snapshot_asset(
        self,
        asset_type: str,
        df: pl.DataFrame,
        metadata: dict | None = None,
    ) -> None:
        """Persist the latest intraday quote snapshot outside canonical daily tables."""
        if df.is_empty() or "date" not in df.columns:
            return
        if asset_type not in {"stock", "index", "etf"}:
            raise ValueError(f"unsupported quote snapshot asset type: {asset_type}")

        try:
            from app.services.quote_service import realtime_route, tag_quote_snapshot_route

            route = realtime_route()
        except Exception as exc:  # noqa: BLE001
            logger.warning("skip quote snapshot write: realtime route resolve failed: %s", exc)
            return
        if route == "unresolved":
            logger.warning("skip quote snapshot write for unresolved realtime route")
            return
        snapshot = tag_quote_snapshot_route(df)
        if "route" in snapshot.columns:
            stored = {str(v or "").strip().lower() for v in snapshot["route"].to_list() if v}
            if stored and stored != {route}:
                logger.warning(
                    "skip quote snapshot write: incoming route %s != current %s",
                    stored, route,
                )
                return
        for key, value in (metadata or {}).items():
            if key not in snapshot.columns:
                snapshot = snapshot.with_columns(pl.lit(value).alias(key))

        dt = snapshot["date"][0]
        ds = dt.isoformat() if hasattr(dt, "isoformat") else str(dt)
        out = (
            self.store.data_dir
            / "quote_snapshot"
            / f"asset_type={asset_type}"
            / f"date={ds}"
            / "part.parquet"
        )
        sort_cols = [c for c in ("symbol", "date") if c in snapshot.columns]
        if sort_cols:
            snapshot = snapshot.sort(sort_cols)
        atomic_write_parquet(snapshot, out)
        write_lineage_record(
            self.store.data_dir,
            "quote_snapshot",
            {
                "date": ds,
                "source": "public_quote",
                "unit_version": "cn_quote_v1",
                "row_count": snapshot.height,
                "scope": (metadata or {}).get("scope"),
                "quality": (metadata or {}).get("quality_status", "intraday_partial"),
                "target_artifact": str(out.relative_to(self.store.data_dir)),
                "asset_type": asset_type,
            },
        )

    def publish_live_enriched_asset(
        self,
        asset_type: str,
        df: pl.DataFrame,
        *,
        merge: bool = False,
    ) -> None:
        """Publish intraday enriched data to memory without writing canonical Parquet.

        Leftover TickFlow daily keeps the live overlay. Custom daily and
        unreadable prefs must not mix a different realtime source into
        ``get_enriched_latest`` consumers even when a caller skips the gate.
        """
        if df.is_empty() or "date" not in df.columns:
            return
        if not self._live_enriched_overlay_allowed():
            logger.info("skip live enriched publish: daily route is custom/unresolved")
            return
        dt = df["date"][0]
        live = df
        if asset_type == "stock":
            existing = self._enriched_cache if merge and self._enriched_cache_date == dt else None
            if existing is not None and not existing.is_empty():
                live = pl.concat([existing, df], how="diagonal_relaxed").unique(
                    subset=["symbol", "date"], keep="last"
                )
            self._enriched_cache = live.sort("symbol")
            self._enriched_cache_date = dt
            self._enriched_cache_live = True
        elif asset_type == "etf":
            existing = self._etf_enriched_cache if merge and self._etf_enriched_cache_date == dt else None
            if existing is not None and not existing.is_empty():
                live = pl.concat([existing, df], how="diagonal_relaxed").unique(
                    subset=["symbol", "date"], keep="last"
                )
            self._etf_enriched_cache = live.sort("symbol")
            self._etf_enriched_cache_date = dt
            self._etf_enriched_cache_live = True

    def save_index_instruments(self, df: pl.DataFrame) -> None:
        """保存指数标的维表。Custom / unresolved daily 不落 leftover TickFlow。"""
        from app.services.instrument_sync import instruments_sync_allowed, tag_instruments

        if df.is_empty() or "symbol" not in df.columns or not instruments_sync_allowed():
            return
        out = self.store.data_dir / "instruments_index" / "instruments_index.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_parquet(
            tag_instruments(df.unique(subset=["symbol"], keep="last").sort("symbol")),
            out,
        )
        self._index_instruments_cache = None
        self._index_instruments_route = None
        self._etf_instruments_cache = None
        self._etf_instruments_route = None
        self._etf_symbol_set_cache = None
        self._refresh_index_instruments()

    def save_etf_instruments(self, df: pl.DataFrame) -> None:
        """保存 ETF 标的维表到独立目录。Custom / unresolved daily 不落 leftover TickFlow。"""
        from app.services.instrument_sync import instruments_sync_allowed, tag_instruments

        if df.is_empty() or "symbol" not in df.columns or not instruments_sync_allowed():
            return
        if "asset_type" not in df.columns:
            df = df.with_columns(pl.lit("etf").alias("asset_type"))
        out = self.store.data_dir / "instruments_etf" / "instruments_etf.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_parquet(
            tag_instruments(df.unique(subset=["symbol"], keep="last").sort("symbol")),
            out,
        )
        self._etf_instruments_cache = None
        self._etf_instruments_route = None
        self._etf_symbol_set_cache = None
        self._refresh_etf_instruments()

    def refresh_index_views(self) -> None:
        """刷新指数相关 DuckDB 视图，不经过 leftover-visible 裸 glob。"""
        from app.services.kline_sync import refresh_gated_catalog_views

        refresh_gated_catalog_views(self)

    def refresh_minute_views(self) -> None:
        """Refresh minute and unified DuckDB views after an atomic publish."""
        from app.services.kline_sync import refresh_gated_catalog_views

        try:
            refresh_gated_catalog_views(self)
        except Exception as exc:  # noqa: BLE001
            logger.warning("minute view refresh failed: %s", exc)
            self.store._fail_closed_route_views()

    def _daily_write_context(self, df: pl.DataFrame):
        """Tag daily/enriched writes and refuse unresolved mix.

        Returns ``(frame, incoming_route, usable_fn)`` or ``None`` when the
        current daily route is unresolved (do not write leftover TickFlow).
        Route-resolve throws stay fail-closed so a caller except cannot
        persist leftover TickFlow onto a custom/unreadable daily.
        """
        try:
            from app.services.kline_sync import (
                _incoming_daily_route,
                _tag_daily_route,
                daily_cache_usable,
            )

            tagged = _tag_daily_route(df)
            incoming = _incoming_daily_route(tagged)
        except Exception as exc:  # noqa: BLE001
            logger.warning("skip daily/enriched write: route resolve failed: %s", exc)
            return None
        if incoming == "unresolved":
            logger.warning("skip daily/enriched write for unresolved daily route")
            return None
        return tagged, incoming, daily_cache_usable

    def _write_daily_partition(self, df: pl.DataFrame, table: str) -> None:
        """按 date 分区写入 parquet，每个日期一个文件，支持 merge-upsert。

        Same-date leftover TickFlow/public/custom bars are replaced, not
        concat-mixed. Historical other dates stay until the user re-syncs.
        """
        ctx = self._daily_write_context(df)
        if ctx is None:
            return
        df, incoming_route, usable = ctx
        base = self.store.data_dir / table
        for date_df in df.partition_by("date"):
            dt = date_df["date"][0]
            ds = dt.isoformat() if hasattr(dt, "isoformat") else str(dt)
            out = base / f"date={ds}" / "part.parquet"
            out.parent.mkdir(parents=True, exist_ok=True)
            if out.exists():
                existing = pl.read_parquet(out)
                if not usable(existing, incoming_route):
                    logger.info(
                        "replace stale %s partition %s for route=%s",
                        table, ds, incoming_route,
                    )
                    existing = date_df.head(0)
                date_df = pl.concat([existing, date_df], how="diagonal_relaxed").unique(
                    subset=["symbol", "date"], keep="last"
                )
            date_df = date_df.sort(["symbol", "date"])
            atomic_write_parquet(date_df, out)
            try:
                from app.services import preferences

                source = preferences.get_daily_data_provider()
                scope = preferences.get_pipeline_universe_scope()
            except Exception:  # noqa: BLE001
                source = "unknown"
                scope = None
            write_lineage_record(
                self.store.data_dir,
                table,
                {
                    "date": ds,
                    "source": source,
                    "unit_version": "canonical_daily_v1",
                    "row_count": date_df.height,
                    "scope": scope,
                    "quality": "pending_gate",
                    "target_artifact": str(out.relative_to(self.store.data_dir)),
                },
            )

    def merge_live_daily_asset(self, asset_type: str, df: pl.DataFrame) -> None:
        """按 symbol 合并当天指定资产日K分区。用于少量自选实时，不覆盖全市场。"""
        if df.is_empty() or "date" not in df.columns:
            return
        ctx = self._daily_write_context(df)
        if ctx is None:
            return
        df, incoming_route, usable = ctx
        table = {
            "stock": "kline_daily",
            "index": "kline_index_daily",
            "etf": "kline_etf_daily",
        }.get(asset_type)
        if not table:
            return
        base = self.store.data_dir / table
        dt = df["date"][0]
        ds = dt.isoformat() if hasattr(dt, "isoformat") else str(dt)
        out = base / f"date={ds}" / "part.parquet"
        optimistic_upsert_parquet(
            df.sort(["symbol", "date"]),
            out,
            keys=["symbol", "date"],
            sort_by=["symbol", "date"],
            lock=self._write_lock,
            prepare_existing=lambda existing, route=incoming_route: (
                existing if usable(existing, route) else existing.head(0)
            ),
        )

    def merge_live_enriched_asset(self, asset_type: str, df: pl.DataFrame) -> None:
        """按 symbol 合并当天 enriched 分区和内存缓存。用于少量自选实时。"""
        if df.is_empty() or "date" not in df.columns:
            return
        ctx = self._daily_write_context(df)
        if ctx is None:
            return
        df, incoming_route, usable = ctx
        dt = df["date"][0]
        if asset_type == "stock":
            table = "kline_daily_enriched"
            existing_cache = self._enriched_cache if self._enriched_cache_date == dt else pl.DataFrame()
        elif asset_type == "etf":
            table = "kline_etf_enriched"
            existing_cache = self._etf_enriched_cache if self._etf_enriched_cache_date == dt else pl.DataFrame()
        elif asset_type == "index":
            table = "kline_index_enriched"
            existing_cache = pl.DataFrame()
        else:
            return

        merged_cache = df
        if existing_cache is not None and not existing_cache.is_empty() and usable(existing_cache, incoming_route):
            merged_cache = pl.concat([existing_cache, df], how="diagonal_relaxed").unique(
                subset=["symbol", "date"], keep="last"
            )
        merged_cache = merged_cache.sort(["symbol"])
        if asset_type == "stock":
            self._enriched_cache = merged_cache
            self._enriched_cache_date = dt
            self._enriched_cache_live = False
        elif asset_type == "etf":
            self._etf_enriched_cache = merged_cache
            self._etf_enriched_cache_date = dt
            self._etf_enriched_cache_live = False

        from app.indicators.pipeline import ENRICHED_STORAGE_COLS
        storage_cols = [c for c in ENRICHED_STORAGE_COLS if c in df.columns]
        if "route" in df.columns and "route" not in storage_cols:
            storage_cols.append("route")
        df_storage = df.select(storage_cols).sort(["symbol"])
        base = self.store.data_dir / table
        ds = dt.isoformat() if hasattr(dt, "isoformat") else str(dt)
        out = base / f"date={ds}" / "part.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            existing = pl.read_parquet(out)
            if not usable(existing, incoming_route):
                existing = df_storage.head(0)
            df_storage = pl.concat([existing, df_storage], how="diagonal_relaxed").unique(
                subset=["symbol", "date"], keep="last"
            )
        atomic_write_parquet(df_storage.sort(["symbol"]), out)

    def flush_live_daily(self, df: pl.DataFrame) -> None:
        """覆写当天 kline_daily 分区 (实时行情落盘, 非merge)。"""
        if df.is_empty() or "date" not in df.columns:
            return
        self.flush_live_daily_asset("stock", df)

    def flush_live_daily_asset(self, asset_type: str, df: pl.DataFrame) -> None:
        """覆写当天指定资产日K分区 (实时行情落盘, 非merge)。"""
        if df.is_empty() or "date" not in df.columns:
            return
        ctx = self._daily_write_context(df)
        if ctx is None:
            return
        df, _incoming_route, _usable = ctx
        table = {
            "stock": "kline_daily",
            "index": "kline_index_daily",
            "etf": "kline_etf_daily",
        }.get(asset_type)
        if not table:
            return
        base = self.store.data_dir / table
        dt = df["date"][0]
        ds = dt.isoformat() if hasattr(dt, "isoformat") else str(dt)
        out = base / f"date={ds}" / "part.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_parquet(df.sort(["symbol", "date"]), out)

    def flush_live_enriched(self, df: pl.DataFrame) -> None:
        """覆写当天 kline_daily_enriched 分区 (实时 enriched 落盘, 非merge)。

        内存缓存保留完整指标列供各服务使用，磁盘仅写入 14 列存储列。
        """
        self.flush_live_enriched_asset("stock", df)

    def flush_live_enriched_asset(self, asset_type: str, df: pl.DataFrame) -> None:
        """覆写当天指定资产 enriched 分区 (实时 enriched 落盘, 非merge)。"""
        if df.is_empty() or "date" not in df.columns:
            return
        ctx = self._daily_write_context(df)
        if ctx is None:
            return
        df, _incoming_route, _usable = ctx
        dt = df["date"][0]
        if asset_type == "stock":
            self._enriched_cache = df.sort(["symbol"])
            self._enriched_cache_date = dt
            self._enriched_cache_live = False
            table = "kline_daily_enriched"
        elif asset_type == "etf":
            self._etf_enriched_cache = df.sort(["symbol"])
            self._etf_enriched_cache_date = dt
            self._etf_enriched_cache_live = False
            table = "kline_etf_enriched"
        elif asset_type == "index":
            table = "kline_index_enriched"
        else:
            return

        from app.indicators.pipeline import ENRICHED_STORAGE_COLS
        storage_cols = [c for c in ENRICHED_STORAGE_COLS if c in df.columns]
        if "route" in df.columns and "route" not in storage_cols:
            storage_cols.append("route")
        df_storage = df.select(storage_cols).sort(["symbol"])
        base = self.store.data_dir / table
        ds = dt.isoformat() if hasattr(dt, "isoformat") else str(dt)
        out = base / f"date={ds}" / "part.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_parquet(df_storage, out)
