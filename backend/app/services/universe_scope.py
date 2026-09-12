"""Universe scope helpers for pipeline and public data sync.

Scopes:
  ALL     — full A-share list (instruments / CN_Equity_A)
  CSI300  — 沪深300 constituents (data/pools/CSI300.parquet)
  CSI500  — 中证500（与 CSI300 官方成分互不重叠）
  CSI800  — 中证800 官方成分（000906；不再只用 300∪500 近似）
  CSI1000 — 中证1000 官方成分（000852）
  CSI1800 — 中证800 ∪ 中证1000（约 1800）
  SSE50   — 上证50
  WATCHLIST — user watchlist only

Defaults (by design):
  pipeline_universe_scope = ALL   (daily kline keeps broad coverage)
  public_data_scope       = CSI300 (adj/financials public default fill; can raise to CSI800)
"""
from __future__ import annotations

import logging
from pathlib import Path

import polars as pl

from app.config import settings

logger = logging.getLogger(__name__)

SCOPE_ALL = "ALL"
SCOPE_CSI300 = "CSI300"
SCOPE_CSI500 = "CSI500"
SCOPE_CSI800 = "CSI800"
SCOPE_CSI1000 = "CSI1000"
SCOPE_CSI1800 = "CSI1800"
SCOPE_SSE50 = "SSE50"
SCOPE_WATCHLIST = "WATCHLIST"

VALID_SCOPES = (
    SCOPE_ALL,
    SCOPE_CSI300,
    SCOPE_CSI500,
    SCOPE_CSI800,
    SCOPE_CSI1000,
    SCOPE_CSI1800,
    SCOPE_SSE50,
    SCOPE_WATCHLIST,
)
CSI_POOL_SCOPES = (SCOPE_CSI300, SCOPE_CSI500, SCOPE_CSI800, SCOPE_CSI1000, SCOPE_SSE50)
UNION_SCOPES = (SCOPE_CSI1800,)

SCOPE_LABELS = {
    SCOPE_ALL: "全A",
    SCOPE_CSI300: "沪深300",
    SCOPE_CSI500: "中证500",
    SCOPE_CSI800: "中证800",
    SCOPE_CSI1000: "中证1000",
    SCOPE_CSI1800: "中证1800(800∪1000)",
    SCOPE_SSE50: "上证50",
    SCOPE_WATCHLIST: "自选",
}


def normalize_scope(scope: str | None, *, default: str = SCOPE_ALL) -> str:
    s = (scope or default).strip().upper()
    aliases = {
        "FULL": SCOPE_ALL,
        "CN_EQUITY_A": SCOPE_ALL,
        "A": SCOPE_ALL,
        "HS300": SCOPE_CSI300,
        "000300": SCOPE_CSI300,
        "ZZ500": SCOPE_CSI500,
        "000905": SCOPE_CSI500,
        "ZZ800": SCOPE_CSI800,
        "000906": SCOPE_CSI800,
        "ZZ1000": SCOPE_CSI1000,
        "000852": SCOPE_CSI1000,
        "ZZ1800": SCOPE_CSI1800,
        "CSI800_CSI1000": SCOPE_CSI1800,
        "SH50": SCOPE_SSE50,
        "000016": SCOPE_SSE50,
        "WL": SCOPE_WATCHLIST,
    }
    s = aliases.get(s, s)
    return s if s in VALID_SCOPES else default


def _load_instruments(data_dir: Path) -> list[str]:
    path = data_dir / "instruments" / "instruments.parquet"
    if not path.exists():
        return []
    try:
        from app.services.instrument_sync import filter_instruments, instrument_route

        df = filter_instruments(pl.read_parquet(path), instrument_route())
        if df.is_empty() or "symbol" not in df.columns:
            return []
        return [str(s).strip().upper() for s in df["symbol"].to_list() if s]
    except Exception as e:
        logger.warning("read instruments failed: %s", e)
        return []


def tickflow_all_a_expansion_allowed(capset, *, scope: str | None = None) -> bool:
    """True only for leftover TickFlow ALL expansion.

    Public / custom pool, custom daily, or unreadable prefs must not expand
    via TickFlow ``CN_Equity_A``.
    """
    from app.tickflow.capabilities import Cap
    from app.tickflow.pools import pool_route

    if scope is None:
        from app.services import preferences as _prefs
        scope = normalize_scope(_prefs.get_pipeline_universe_scope(), default=SCOPE_ALL)
    else:
        scope = normalize_scope(scope, default=SCOPE_ALL)
    if scope != SCOPE_ALL:
        return False
    if capset is None or not capset.has(Cap.KLINE_DAILY_BATCH):
        return False
    if pool_route() != "tickflow":
        return False
    try:
        from app.services import kline_sync
        if kline_sync.daily_provider_is_custom():
            return False
    except Exception:
        return False
    return True


def _ensure_csi_pool(pool_id: str, data_dir: Path, *, refresh_if_missing: bool = True) -> list[str]:
    from app.data_providers.registry import get_provider
    from app.services.free_sources.pools_public import load_pool_symbols
    from app.tickflow.pools import get_pool, pool_cache_usable, pool_route

    route = pool_route()
    if route in {"custom", "unresolved"}:
        logger.warning(
            "pool_provider route=%s cannot use cached CSI pool %s",
            route, pool_id,
        )
        return []
    if route == "tickflow":
        try:
            from app.services.kline_sync import leftover_tickflow_follow_daily

            if not leftover_tickflow_follow_daily():
                logger.info("skip leftover TickFlow CSI pool %s after custom/unresolved daily", pool_id)
                return []
        except Exception:  # noqa: BLE001
            return []

    # Prefer on-disk cache only when provenance matches the current route.
    path = data_dir / "pools" / f"{pool_id}.parquet"
    if path.exists():
        try:
            df = pl.read_parquet(path)
            if pool_cache_usable(df, route):
                return [str(s).strip().upper() for s in df["symbol"].to_list() if s]
            logger.info("skip stale CSI cache %s for route=%s", pool_id, route)
        except Exception as e:
            logger.warning("read CSI pool %s failed: %s", pool_id, e)
    if not refresh_if_missing:
        return []
    if route == "public":
        try:
            get_provider("public").sync_pools(data_dir, pool_ids=[pool_id])
            syms = load_pool_symbols(data_dir, pool_id)
            if syms:
                return [str(s).strip().upper() for s in syms if s]
        except Exception as e:
            logger.warning("sync pool %s failed: %s", pool_id, e)
        return []
    if route == "tickflow":
        try:
            return [str(s).strip().upper() for s in (get_pool(pool_id, refresh=True) or []) if s]
        except Exception as e:
            logger.warning("get_pool %s failed: %s", pool_id, e)
            return []
    logger.warning("pool_provider route=%s cannot refresh CSI pool %s", route, pool_id)
    return []


def resolve_symbols(
    scope: str | None,
    *,
    data_dir: Path | None = None,
    default: str = SCOPE_ALL,
    include_watchlist: bool = False,
    refresh_pools_if_missing: bool = True,
) -> list[str]:
    """Resolve symbol list for a scope. Always returns sorted unique list."""
    from app.tickflow.pools import DEMO_SYMBOLS, get_pool

    data_dir = Path(data_dir or settings.data_dir)
    sc = normalize_scope(scope, default=default)
    out: list[str] = []

    if sc == SCOPE_ALL:
        # Prefer instruments parquet (works offline / free)
        out = _load_instruments(data_dir)
        if not out:
            from app.tickflow.pools import pool_route
            from app.services.kline_sync import daily_provider_is_custom, daily_route

            try:
                daily = daily_route()
                daily_custom = daily_provider_is_custom() or daily == "unresolved"
            except Exception:
                daily_custom = True
            if not daily_custom:
                route = pool_route()
                if route == "tickflow":
                    try:
                        out = [
                            str(s).strip().upper()
                            for s in (get_pool("CN_Equity_A", refresh=False) or [])
                            if s
                        ]
                    except Exception:
                        out = []
                # Public leftover may use the offline demo set. Custom / unreadable
                # daily must not expand via TickFlow cache or DEMO mix.
                if not out and route not in {"custom", "unresolved"}:
                    out = list(DEMO_SYMBOLS)
    elif sc == SCOPE_CSI1800:
        a = _ensure_csi_pool(SCOPE_CSI800, data_dir, refresh_if_missing=refresh_pools_if_missing)
        b = _ensure_csi_pool(SCOPE_CSI1000, data_dir, refresh_if_missing=refresh_pools_if_missing)
        out = list(a) + list(b)
        if not out:
            logger.warning("scope CSI1800 empty after pool fetch")
    elif sc in CSI_POOL_SCOPES:
        out = _ensure_csi_pool(sc, data_dir, refresh_if_missing=refresh_pools_if_missing)
        if not out:
            # degrade rather than empty: instruments head is wrong; keep demo+watchlist later
            logger.warning("scope %s empty after pool fetch", sc)
    elif sc == SCOPE_WATCHLIST:
        try:
            out = [str(s).strip().upper() for s in (get_pool("watchlist") or []) if s]
        except Exception:
            out = []
    else:
        out = _load_instruments(data_dir)

    if include_watchlist and sc != SCOPE_WATCHLIST:
        try:
            wl = [str(s).strip().upper() for s in (get_pool("watchlist") or []) if s]
            out = list(out) + wl
        except Exception:
            pass

    # unique preserve sort
    seen: set[str] = set()
    ordered: list[str] = []
    for s in out:
        u = s.strip().upper()
        if not u or u in seen:
            continue
        seen.add(u)
        ordered.append(u)
    ordered.sort()
    return ordered


def scope_info(scope: str | None, *, default: str = SCOPE_ALL) -> dict:
    sc = normalize_scope(scope, default=default)
    return {
        "scope": sc,
        "label": SCOPE_LABELS.get(sc, sc),
        "is_csi": sc in CSI_POOL_SCOPES or sc in UNION_SCOPES,
        "is_union": sc in UNION_SCOPES,
        "is_all": sc == SCOPE_ALL,
    }
