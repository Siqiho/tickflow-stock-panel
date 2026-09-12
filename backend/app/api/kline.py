"""K 线 / 同步 API。"""
from __future__ import annotations

import gzip
import json
import logging
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.indicators.pipeline import compute_enriched
from app.market_time import cn_now, cn_today, in_continuous_session
from app.services import kline_sync
from app.tickflow.capabilities import Cap, CapabilitySet
from app.tickflow.repository import KlineReadError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/kline", tags=["kline"])


def _minute_rows_without_route(df) -> list[dict]:
    if df is None or getattr(df, "is_empty", lambda: True)():
        return []
    if "route" in df.columns:
        df = df.drop("route")
    return df.to_dicts()


def _dicts_without_route(rows: list[dict]) -> list[dict]:
    return [{k: v for k, v in row.items() if k != "route"} for row in rows]


def _accepts_gzip(accept_encoding: str | None) -> bool:
    """RFC 9110 Accept-Encoding: gzip;q=0 表示明确拒绝, 不得压缩。"""
    if not accept_encoding:
        return False
    for part in accept_encoding.split(","):
        item = part.strip()
        if not item:
            continue
        name, _, rest = item.partition(";")
        if name.strip().lower() != "gzip":
            continue
        q = 1.0
        for param in rest.split(";"):
            param = param.strip()
            if param.lower().startswith("q="):
                try:
                    q = float(param[2:].strip())
                except ValueError:
                    q = 0.0
        return q > 0
    return False


def _http_capset(request: Request) -> CapabilitySet:
    """HTTP 入口缺 capabilities 时 fail-closed, 不把 None 当成“无门控”。

    库函数 fetch_minute_single(..., capset=None) 仍表示旧直接调用、允许 TickFlow。
    """
    capset = getattr(getattr(request, "app", None), "state", None)
    capset = getattr(capset, "capabilities", None) if capset is not None else None
    if capset is None:
        return CapabilitySet()
    return capset


def _minute_allowed(capset) -> bool:
    """是否有分钟K权限 (TickFlow 批量 或 已解析成功的 custom minute 源)。resolver 异常 fail-closed。"""
    return kline_sync.minute_sync_allowed(capset)


def _gzip_payload(request: Request, payload: dict, *, pref_key: str) -> dict | Response:
    """大 JSON 响应的传输压缩: 偏好开启 + 客户端接受 gzip + 响应超阈值才压。

    分时/日K各自使用独立偏好键 (沿用已有 *_batch_compress 存储键保证兼容)。
    """
    from app.services import preferences as _prefs
    _getters = {
        "minute_batch_compress": _prefs.get_minute_batch_compress,
        "daily_batch_compress": _prefs.get_daily_batch_compress,
    }
    getter = _getters.get(pref_key)
    compress_on = False
    if getter is not None:
        try:
            compress_on = bool(getter())
        except Exception:  # 偏好读取异常按不压缩返回原样
            compress_on = False
    headers = getattr(request, "headers", None) or {}
    if compress_on and _accepts_gzip(headers.get("accept-encoding")):
        raw = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), allow_nan=True,
            default=lambda o: o.isoformat() if hasattr(o, "isoformat") else str(o),
        ).encode()
        if len(raw) > 1024:
            return Response(
                content=gzip.compress(raw, 6),
                media_type="application/json",
                headers={"Content-Encoding": "gzip", "Vary": "Accept-Encoding"},
            )
    return payload


@router.get("/instruments/search")
def search_instruments(
    request: Request,
    q: str = Query("", min_length=0, max_length=50, description="搜索关键词"),
    limit: int = Query(20, ge=1, le=50),
):
    """模糊搜索标的 (代码 / 名称)。从内存 instruments 缓存中查。"""
    repo = request.app.state.repo
    df = repo.get_instruments()
    if df.is_empty() or not q.strip():
        return {"results": []}

    keyword = q.strip().upper()
    import polars as pl

    # code/symbol 前缀优先，再 name 包含匹配
    prefix_mask = (
        pl.col("code").str.starts_with(keyword)
        | pl.col("symbol").str.to_uppercase().str.starts_with(keyword)
    )
    contains_mask = (
        pl.col("code").str.contains(keyword, literal=True)
        | pl.col("symbol").str.to_uppercase().str.contains(keyword, literal=True)
        | pl.col("name").str.contains(keyword, literal=True)
    )

    # 前缀匹配优先，剩余名额用包含匹配补充
    prefix_hits = df.filter(prefix_mask).head(limit)
    if prefix_hits.height >= limit:
        matched = prefix_hits
    else:
        remaining = limit - prefix_hits.height
        # 排除已匹配的 symbol
        prefix_symbols = set(prefix_hits["symbol"].to_list()) if not prefix_hits.is_empty() else set()
        contain_hits = df.filter(contains_mask & ~pl.col("symbol").is_in(prefix_symbols)).head(remaining)
        matched = pl.concat([prefix_hits, contain_hits]) if not prefix_hits.is_empty() else contain_hits
    rows = matched.select(["symbol", "name", "code"]).to_dicts()
    return {"results": rows}


@router.post("/instruments/names")
def instruments_names(request: Request, symbols: list[str]):
    """批量查股票名称。传入 symbol 列表, 返回 {symbol: name}。"""
    if not symbols:
        return {"names": {}}
    repo = request.app.state.repo
    df = repo.get_instruments()
    if df.is_empty():
        return {"names": {}}
    import polars as pl
    matched = df.filter(pl.col("symbol").is_in(symbols)).select(["symbol", "name"])
    names = {row["symbol"]: row["name"] for row in matched.iter_rows(named=True)}
    return {"names": names}


def _usable_instrument_row(row) -> bool:
    """Accept real SQL rows only. MagicMock / leftover objects are not names."""
    return isinstance(row, (tuple, list)) and len(row) >= 1


def _get_stock_info(repo, symbol: str) -> dict:
    """从 instruments 视图查标的名称 + 股本。"""
    try:
        row = repo.execute_one(
            "SELECT name, total_shares, float_shares FROM instruments WHERE symbol = ? LIMIT 1",
            [symbol],
        )
    except Exception:  # noqa: BLE001
        row = None
    if _usable_instrument_row(row):
        return {
            "name": row[0],
            "total_shares": row[1],
            "float_shares": row[2],
        }
    try:
        import polars as pl
        df = repo.get_instruments()
        if df is None or df.is_empty() or "symbol" not in df.columns:
            return {}
        required = ("name", "total_shares", "float_shares")
        if any(col not in df.columns for col in required):
            # Incomplete instrument row is the same as the SQL-error contract:
            # do not advertise None shares as usable capital.
            return {}
        hit = df.filter(pl.col("symbol") == symbol).head(1)
        if hit.is_empty():
            return {}
        rec = hit.to_dicts()[0]
        return {
            "name": rec.get("name"),
            "total_shares": rec.get("total_shares"),
            "float_shares": rec.get("float_shares"),
        }
    except Exception:  # noqa: BLE001
        return {}


@router.get("/daily")
def get_daily(
    request: Request,
    symbol: str = Query(..., description="标的代码,如 000001.SZ"),
    days: int = Query(120, ge=10, le=2000),
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD, 优先于 days"),
    end_date: Optional[str] = Query(None, description="截止日期 YYYY-MM-DD, 默认今天"),
    ext_columns: Optional[str] = Query(None, description="逗号分隔的 ext 列: config_id.field_name"),
):
    """读取本地 enriched 表中某只股票的日 K。

    - 正式日线之后若有本地行情快照, 只在响应中补齐后续交易日蜡烛
    - 若 QuoteService 有当日实时行情, 追加/覆盖今日实时蜡烛
    - Free 用户: 若 enriched 表里没有该股票, 实时拉取 + 本地算 enriched 返回
    - ext_columns: 可选，动态 LEFT JOIN 扩展数据表，结果平铺到 stock_info.ext 下
      (key 为 "{config_id}__{field_name}")，供日K信息条等场景展示自定义字段
    """
    import polars as pl

    repo = request.app.state.repo
    end = date.fromisoformat(end_date) if end_date else date.today()
    if start_date:
        start = date.fromisoformat(start_date)
    else:
        start = end - timedelta(days=days)

    stock_info = _get_stock_info(repo, symbol)
    stock_name = stock_info.get("name")

    # 从 enriched 表读取 (已含前复权 OHLCV + 技术指标 + 信号)
    try:
        if hasattr(repo, "get_daily"):
            df = repo.get_daily(symbol, start, end)
        elif hasattr(repo, "get_daily_asset"):
            df = repo.get_daily_asset("stock", symbol, start, end)
        else:
            import polars as pl
            df = pl.DataFrame()
    except KlineReadError as e:
        raise HTTPException(
            status_code=503,
            detail={"code": "kline_daily_read_failed", "message": str(e)},
        ) from e

    if df.is_empty():
        try:
            capset = _http_capset(request)
            raw = kline_sync.fetch_routed_daily(
                [symbol],
                start_time=datetime.combine(start, datetime.min.time()),
                end_time=datetime.combine(end, datetime.max.time().replace(microsecond=0)),
                asset_type="stock",
                capset=capset,
                count=days + 30,
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"daily fetch failed: {e}") from e
        if raw.is_empty():
            return _gzip_payload(
                request,
                {"symbol": symbol, "name": stock_name, "stock_info": stock_info, "rows": []},
                pref_key="daily_batch_compress",
            )
        # 拉除权因子做前复权: 公开/已声明自定义源不看 TickFlow cap;
        # leftover TickFlow 有 cap 走 TickFlow, 无 cap 不再静默公开新浪 qfq。
        factors = pl.DataFrame()
        capset = getattr(request.app.state, "capabilities", None)
        try:
            if kline_sync.adj_live_fetch_allowed(capset):
                factors = kline_sync.fetch_adj_factor_single(symbol, capset=capset)
        except Exception as e:  # noqa: BLE001
            logger.debug("单股除权因子拉取失败 %s: %s", symbol, e)
        enriched = compute_enriched(raw, factors=factors)
        rows = enriched.tail(days).to_dicts()
        rows, quote_overlay = _overlay_persisted_quote_candles(repo, symbol, rows, start, end)
        # 即使 live 模式也尝试追加实时蜡烛
        rows = _maybe_inject_live_candle(request, symbol, rows)
        resp = {
            "symbol": symbol,
            "name": stock_name,
            "stock_info": stock_info,
            "rows": rows,
            "source": "live",
            "quote_overlay": quote_overlay,
        }
        return _gzip_payload(
            request,
            _attach_ext(resp, repo, symbol, ext_columns),
            pref_key="daily_batch_compress",
        )

    rows = df.to_dicts()

    # quote_snapshot 是独立的盘中/收盘快照资产:这里只做只读响应覆盖,
    # 绝不回写 canonical kline_daily,避免把未封账行情混入正式历史日线。
    rows, quote_overlay = _overlay_persisted_quote_candles(repo, symbol, rows, start, end)

    # 追加/覆盖今日实时蜡烛
    rows = _maybe_inject_live_candle(request, symbol, rows)

    resp = {
        "symbol": symbol,
        "name": stock_name,
        "stock_info": stock_info,
        "rows": rows,
        "source": "enriched",
        "quote_overlay": quote_overlay,
    }
    return _gzip_payload(
        request,
        _attach_ext(resp, repo, symbol, ext_columns),
        pref_key="daily_batch_compress",
    )


def _row_date(value) -> date | None:
    if isinstance(value, date):
        return value
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _positive_or_close(value, close: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return close
    return number if math.isfinite(number) and number > 0 else close


def _quote_overlay_allowed() -> bool:
    """Overlay snapshots onto leftover TickFlow / public daily only.

    Custom / unresolved daily must not mix leftover TickFlow or public
    snapshots onto HTTP daily. Default leftover TickFlow daily + public
    realtime still overlays (isolated live asset). Snapshot *files* stay
    realtime-route gated.
    """
    try:
        daily = kline_sync.daily_route()
    except Exception:  # noqa: BLE001
        return False
    return daily in {"tickflow", "public"}


def _finite_or_none(value, *, divisor: float = 1.0) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number / divisor if math.isfinite(number) else None


def _overlay_persisted_quote_candles(
    repo,
    symbol: str,
    rows: list[dict],
    start: date,
    end: date,
) -> tuple[list[dict], dict]:
    """把正式日线之后的本地 quote_snapshot 作为只读蜡烛补进响应。

    快照和 canonical 日线保持物理隔离;同一天已有正式日线时,正式日线优先。
    quote_snapshot.change_pct 使用百分点,Kline API 则统一返回小数比例。
    """
    overlay_meta = {
        "applied": False,
        "row_count": 0,
        "latest_date": None,
        "latest_source": None,
        "latest_fetched_at": None,
    }
    if not _quote_overlay_allowed():
        return rows, overlay_meta
    data_dir = getattr(getattr(repo, "store", None), "data_dir", None)
    if data_dir is None:
        return rows, overlay_meta

    existing_dates = [parsed for row in rows if (parsed := _row_date(row.get("date")))]
    latest_canonical = max(existing_dates) if existing_dates else start - timedelta(days=1)
    base = data_dir / "quote_snapshot" / "asset_type=stock"
    parts = []
    try:
        from app.services.quote_service import usable_quote_snapshot_files
    except Exception:
        return rows, overlay_meta
    for child in base.glob("date=*"):
        partition_date = _row_date(child.name.removeprefix("date="))
        if not (partition_date and latest_canonical < partition_date <= end and partition_date >= start):
            continue
        for path in usable_quote_snapshot_files(child):
            parts.append((partition_date, path))
    if not parts:
        return rows, overlay_meta

    import polars as pl

    overlay_rows: list[dict] = []
    for partition_date, path in sorted(parts, key=lambda item: item[0]):
        try:
            snapshot = pl.read_parquet(path)
            if snapshot.is_empty() or "symbol" not in snapshot.columns or "close" not in snapshot.columns:
                continue
            matched = snapshot.filter(pl.col("symbol") == symbol)
            if matched.is_empty():
                continue
            quote = matched.to_dicts()[-1]
            quote_date = _row_date(quote.get("date")) or partition_date
            if not (latest_canonical < quote_date <= end and quote_date >= start):
                continue
            close = float(quote.get("close"))
            if not math.isfinite(close) or close <= 0:
                continue
        except Exception as exc:
            logger.debug("read Kline quote overlay failed %s: %s", path, exc)
            continue

        change_pct = quote.get("change_pct")
        overlay_row = {
            "symbol": symbol,
            "date": str(quote_date),
            "open": _positive_or_close(quote.get("open"), close),
            "high": _positive_or_close(quote.get("high"), close),
            "low": _positive_or_close(quote.get("low"), close),
            "close": close,
            "volume": _finite_or_none(quote.get("volume")),
            "amount": _finite_or_none(quote.get("amount")),
            "prev_close": _finite_or_none(quote.get("prev_close")),
            "change_amount": _finite_or_none(quote.get("change_amount")),
            "change_pct": _finite_or_none(change_pct, divisor=100.0),
            "is_quote_snapshot": True,
            "quote_source": quote.get("source"),
            "quote_fetched_at": quote.get("fetched_at"),
            "quote_quality_status": quote.get("quality_status"),
        }
        overlay_rows.append(overlay_row)

    if not overlay_rows:
        return rows, overlay_meta

    combined = [*rows, *overlay_rows]
    combined.sort(key=lambda row: str(row.get("date") or ""))
    latest = overlay_rows[-1]
    overlay_meta.update(
        {
            "applied": True,
            "row_count": len(overlay_rows),
            "latest_date": latest["date"],
            "latest_source": latest.get("quote_source"),
            "latest_fetched_at": latest.get("quote_fetched_at"),
        }
    )
    return combined, overlay_meta


def _attach_ext(resp: dict, repo, symbol: str, ext_columns: Optional[str]) -> dict:
    """按 ext_columns 规格为单只股票 LEFT JOIN 扩展数据，平铺到 stock_info['ext']。

    key 形如 "{config_id}__{field_name}"，与自选列表 enriched 接口保持一致。
    JOIN 逻辑参考 watchlist.watchlist_enriched；任何 ext 表/字段缺失都静默跳过。
    """
    if not ext_columns or not ext_columns.strip():
        return resp

    specs: list[tuple[str, str]] = []
    for part in ext_columns.split(","):
        part = part.strip()
        if "." not in part:
            continue
        config_id, field_name = part.split(".", 1)
        config_id, field_name = config_id.strip(), field_name.strip()
        if config_id and field_name:
            specs.append((config_id, field_name))
    if not specs:
        return resp

    import polars as pl
    data_dir = repo.store.data_dir
    try:
        from app.services.ext_data import ExtConfigStore
        from app.api.ext_data import _read_ext_dataframe
        ext_store = ExtConfigStore(data_dir)
        configs = {c.id: c for c in ext_store.load_all()}
    except Exception:  # noqa: BLE001
        configs = {}

    ext_values: dict = {}
    for config_id, field_name in specs:
        ext_col_name = f"{config_id}__{field_name}"
        value = None
        try:
            cfg = configs.get(config_id)
            if not cfg:
                # Missing ext config: do not leftover-union DuckDB ext_* views.
                ext_df = pl.DataFrame()
            else:
                ext_df, _ = _read_ext_dataframe(cfg, data_dir)
            if not ext_df.is_empty() and "symbol" in ext_df.columns and field_name in ext_df.columns:
                # 时序表取最新分区，避免一个 symbol 多行
                row = (
                    ext_df
                    .select(["symbol", field_name])
                    .unique(subset=["symbol"], keep="last")
                    .filter(pl.col("symbol") == symbol)
                )
                if not row.is_empty():
                    value = row[field_name][0]
        except Exception as e:  # noqa: BLE001
            logger.debug("kline ext join failed for %s.%s: %s", config_id, field_name, e)
        ext_values[ext_col_name] = value

    stock_info = dict(resp.get("stock_info") or {})
    stock_info["ext"] = ext_values
    resp["stock_info"] = stock_info
    return resp


def _latest_live_candle(
    request: Request,
    symbol: str,
    asset_type: str = "stock",
    *,
    refresh_asset: bool = True,
) -> dict | None:
    """从内存缓存读取单只标的的当日实时 enriched 行。"""
    try:
        from app.services.kline_sync import live_enriched_overlay_allowed
        if not live_enriched_overlay_allowed():
            return None
    except Exception:  # noqa: BLE001
        return None
    if asset_type == "etf":
        df_today, enriched_date = request.app.state.repo.get_enriched_latest_asset("etf")
        if df_today.is_empty():
            return None
        if not enriched_date or enriched_date != date.today():
            return None
        import polars as pl
        try:
            q = df_today.filter(pl.col("symbol") == symbol).to_dicts()
            if not q:
                return None
            q = q[0]
        except Exception:
            return None
        close_price = q.get("close")
        if not close_price or close_price <= 0:
            return None
        raw_open = q.get("open")
        raw_high = q.get("high")
        raw_low = q.get("low")
        live_row = {
            "date": str(enriched_date),
            "symbol": symbol,
            "open": raw_open if raw_open and raw_open > 0 else close_price,
            "high": raw_high if raw_high and raw_high > 0 else close_price,
            "low": raw_low if raw_low and raw_low > 0 else close_price,
            "close": close_price,
            "volume": q.get("volume"),
            "amount": q.get("amount"),
            "change_pct": q.get("change_pct"),
            "is_live": True,
        }
        for key in ("ma5", "ma10", "ma20", "ma30", "ma60",
                    "macd_dif", "macd_dea", "macd_hist",
                    "kdj_k", "kdj_d", "kdj_j",
                    "boll_upper", "boll_lower",
                    "rsi_6", "rsi_14", "rsi_24",
                    "atr_14", "vol_ratio_5d"):
            if key in q and q[key] is not None:
                live_row[key] = q[key]
        return live_row

    # stock path keeps the local QuoteService reader.
    qs = getattr(request.app.state, "quote_service", None)
    if not qs:
        return None

    df_today, enriched_date = qs.get_enriched_today()
    if df_today.is_empty():
        return None

    # 非交易日(周末/假日)缓存日期 != 今天, 跳过注入避免产生重复蜡烛
    if not enriched_date or enriched_date != date.today():
        return None

    # 查找该 symbol 的实时 enriched 行
    import polars as pl
    try:
        q = df_today.filter(pl.col("symbol") == symbol).to_dicts()
        if not q:
            return None
        q = q[0]
    except Exception:
        return None

    close_price = q.get("close")
    if not close_price or close_price <= 0:
        return None

    # 沿用完整日K接口原有的实时行投影, 避免增量接口形成第二套字段契约。
    # API 在非交易时段可能返回 open/high/low=0, 用 close 填充避免异常蜡烛。
    raw_open = q.get("open")
    raw_high = q.get("high")
    raw_low = q.get("low")
    live_row = {
        "date": str(enriched_date),
        "symbol": symbol,
        "open": raw_open if raw_open and raw_open > 0 else close_price,
        "high": raw_high if raw_high and raw_high > 0 else close_price,
        "low": raw_low if raw_low and raw_low > 0 else close_price,
        "close": close_price,
        "volume": q.get("volume"),
        "amount": q.get("amount"),
        "change_pct": q.get("change_pct"),
        "is_live": True,
    }
    for key in ("ma5", "ma10", "ma20", "ma30", "ma60",
                "macd_dif", "macd_dea", "macd_hist",
                "kdj_k", "kdj_d", "kdj_j",
                "boll_upper", "boll_lower",
                "rsi_6", "rsi_14", "rsi_24",
                "atr_14", "vol_ratio_5d"):
        if key in q and q[key] is not None:
            live_row[key] = q[key]
    return live_row


def _maybe_inject_live_candle(request: Request, symbol: str, rows: list[dict], asset_type: str = "stock") -> list[dict]:
    """如果有当日实时 enriched 数据, 用实时数据生成今日蜡烛并追加/覆盖。"""
    live_row = _latest_live_candle(request, symbol, asset_type)
    if live_row is None:
        return rows

    # 如果已有今天的 enriched 行, 覆盖; 否则追加
    found = False
    for r in rows:
        if str(r.get("date")) == live_row["date"]:
            r.update(live_row)
            found = True
            break

    if not found:
        rows.append(live_row)

    return rows


@router.get("/daily/latest")
def get_daily_latest(
    request: Request,
    symbol: str = Query(..., description="标的代码,如 000001.SZ"),
):
    """返回内存中的当日单行 K 线, 供详情页实时增量更新。"""
    repo = request.app.state.repo
    asset_type = repo.resolve_asset_type(symbol)
    row = _latest_live_candle(request, symbol, asset_type, refresh_asset=False)
    return {
        "symbol": symbol,
        "row": row,
        "source": "live" if row is not None else "none",
    }


class DailyBatchRequest:
    """批量日K请求。"""
    symbols: list[str]
    days: int = 12


@router.post("/daily-batch")
def get_daily_batch(request: Request, body: dict):
    """批量获取多只股票最近 N 天日K (OHLCV)。

    用于自选列表迷你蜡烛图等场景，只返回基础列，不返回全部 enriched 指标。
    """
    symbols = body.get("symbols", [])
    days = body.get("days", 12)
    if not symbols:
        return _gzip_payload(request, {"data": {}}, pref_key="daily_batch_compress")
    days = max(5, min(60, days))

    repo = request.app.state.repo
    import polars as pl
    from datetime import date, timedelta

    end = date.today()
    start = end - timedelta(days=days * 2)  # 多取一些确保交易日够

    cols = ["symbol", "date", "open", "high", "low", "close", "volume"]
    df = repo.get_daily_batch(symbols, start, end, columns=cols)

    if df.is_empty():
        return _gzip_payload(request, {"data": {}}, pref_key="daily_batch_compress")

    # 按 symbol 分组, 每只取最近 N 条
    result: dict[str, list[dict]] = {}
    for sym in symbols:
        sub = df.filter(pl.col("symbol") == sym).sort("date").tail(days)
        if not sub.is_empty():
            result[sym] = sub.to_dicts()

    return _gzip_payload(request, {"data": result}, pref_key="daily_batch_compress")


def _coerce_session_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _minute_range_prev_closes(repo, symbol: str, trade_dates: list, asset_type: str = "stock") -> dict:
    """Previous official daily close per session from the current daily route.

    HTTP used to leave prev_close null and let leftover DuckDB daily fill
    names elsewhere. Gated get_daily_asset keeps leftover TickFlow out after
    a custom switch. ETF sessions read ETF daily, not the stock store.
    Untagged leftover TickFlow daily still serves.
    """
    days = [_coerce_session_date(d) for d in trade_dates]
    days = [d for d in days if d is not None]
    getter = getattr(repo, "get_daily_asset", None)
    if not callable(getter) or not days:
        return {}
    start = days[0] - timedelta(days=20)
    end = days[-1]
    table = "etf" if asset_type == "etf" else "stock"
    try:
        daily = getter(table, symbol, start, end)
    except TypeError:
        try:
            daily = getter(symbol, start, end)
        except Exception:  # noqa: BLE001
            return {}
    except Exception:  # noqa: BLE001
        return {}
    if daily is None or not hasattr(daily, "is_empty") or daily.is_empty():
        return {}
    try:
        daily = kline_sync.filter_daily_cache(daily)
    except Exception:  # noqa: BLE001
        return {}
    if daily.is_empty() or "date" not in daily.columns or "close" not in daily.columns:
        return {}
    close_by_date: dict[date, float] = {}
    for rec in daily.select(["date", "close"]).to_dicts():
        day = _coerce_session_date(rec.get("date"))
        if day is None:
            continue
        close_by_date[day] = rec.get("close")
    ordered = sorted(close_by_date)
    out: dict = {}
    for raw, day in zip(trade_dates, days):
        prior = [d for d in ordered if d < day]
        out[raw] = close_by_date[prior[-1]] if prior else None
        out[day] = out[raw]
    return out


@router.get("/minute-range")
def get_minute_range(
    request: Request,
    symbol: str = Query(..., description="标的代码"),
    days: int = Query(10, ge=1, le=20, description="最近交易日数量"),
):
    """读取单只标的最近 N 个已落库交易日的分钟 K。"""
    import polars as pl

    repo = request.app.state.repo
    resolver = getattr(repo, "resolve_asset_type", None)
    asset_type = resolver(symbol) if callable(resolver) else "stock"
    stock_info = _get_stock_info(repo, symbol)
    base_response = {
        "symbol": symbol,
        "name": stock_info.get("name"),
        "asset_type": asset_type,
        "requested_days": days,
    }
    if asset_type == "index":
        return _gzip_payload(
            request,
            {**base_response, "sessions": [], "source": "none"},
            pref_key="minute_batch_compress",
        )
    end = cn_today()
    start = end - timedelta(days=days * 3 + 20)
    minute = pl.DataFrame()
    getter = getattr(repo, "get_minute_range", None)
    if callable(getter):
        try:
            candidate = getter([symbol], start, end, asset_type=asset_type)
        except TypeError:
            try:
                candidate = getter([symbol], start, end)
            except Exception as exc:  # noqa: BLE001
                logger.warning("minute-range getter failed: %s", exc)
                candidate = None
        except Exception as exc:  # noqa: BLE001
            logger.warning("minute-range getter failed: %s", exc)
            candidate = None
        if isinstance(candidate, pl.DataFrame):
            try:
                minute = kline_sync.filter_minute_cache(candidate)
            except Exception as exc:  # noqa: BLE001
                logger.warning("minute-range getter leftover filter failed: %s", exc)
                minute = pl.DataFrame()
    if minute is None or minute.is_empty():
        data_dir = getattr(getattr(repo, "store", None), "data_dir", None)
        if not isinstance(data_dir, (str, Path)):
            return _gzip_payload(
                request,
                {**base_response, "sessions": [], "source": "none"},
                pref_key="minute_batch_compress",
            )
        try:
            lf = kline_sync.scan_usable_minute(data_dir, asset_type=asset_type)
            if lf is None:
                minute = pl.DataFrame()
            else:
                minute = kline_sync.filter_minute_cache(
                    lf.filter(
                        (pl.col("symbol") == symbol)
                        & (pl.col("datetime").dt.date() >= start)
                        & (pl.col("datetime").dt.date() <= end)
                    ).collect()
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("minute-range scan failed: %s", exc)
            if minute is None or minute.is_empty():
                return _gzip_payload(
                    request,
                    {**base_response, "sessions": [], "source": "none"},
                    pref_key="minute_batch_compress",
                )
    if minute.is_empty() or "datetime" not in minute.columns:
        return _gzip_payload(
            request,
            {**base_response, "sessions": [], "source": "none"},
            pref_key="minute_batch_compress",
        )

    minute = minute.with_columns(pl.col("datetime").dt.date().alias("_trade_date"))
    trade_dates = sorted(minute["_trade_date"].unique().to_list())[-days:]
    prev_closes = _minute_range_prev_closes(repo, symbol, trade_dates, asset_type=asset_type)
    row_columns = [
        column
        for column in ("datetime", "open", "high", "low", "close", "volume", "amount")
        if column in minute.columns
    ]
    sessions = []
    for trade_date in trade_dates:
        rows = (
            minute.filter(pl.col("_trade_date") == trade_date)
            .sort("datetime")
            .select(row_columns)
            .to_dicts()
        )
        if rows:
            sessions.append({
                "date": trade_date.isoformat(),
                "prev_close": prev_closes.get(trade_date),
                "rows": rows,
            })
    return _gzip_payload(
        request,
        {
            **base_response,
            "sessions": sessions,
            "source": "local" if sessions else "none",
        },
        pref_key="minute_batch_compress",
    )


@router.post("/minute-batch")
def get_minute_batch(request: Request, body: dict):
    """批量分钟K: 本地优先, 缺口按 stock/ETF 补拉并原子落盘。

    HTTP 缺 capset 时 fail-closed, 只读本地、不走 TickFlow。
    自定义分钟源或 TickFlow 批量权限存在时才补拉。
    """
    import polars as pl

    symbols: list[str] = body.get("symbols") or []
    trade_date_str: str | None = body.get("date")
    since_str = body.get("since")
    since_dt: datetime | None = None
    if since_str:
        try:
            since_dt = datetime.fromisoformat(str(since_str))
            if since_dt.tzinfo is not None:
                since_dt = since_dt.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
        except ValueError:
            since_dt = None
    prefer_local = bool(body.get("prefer_local", False))
    if not symbols:
        return _gzip_payload(request, {"data": {}}, pref_key="minute_batch_compress")

    repo = request.app.state.repo
    capset = _http_capset(request)
    can_pull = _minute_allowed(capset)
    trade_date = date.fromisoformat(trade_date_str) if trade_date_str else cn_today()

    etf_getter = getattr(repo, "get_etf_symbol_set", None)
    etf_set = etf_getter() if callable(etf_getter) else set()
    stock_syms = [s for s in symbols if s not in etf_set]
    etf_syms = [s for s in symbols if s in etf_set]

    def _local_batch(syms: list[str], asset: str) -> pl.DataFrame:
        if not syms:
            return pl.DataFrame()
        getter = getattr(repo, "get_minute_batch", None)
        if callable(getter):
            try:
                return getter(syms, trade_date, asset_type=asset)
            except TypeError:
                return getter(syms, trade_date)
        frames = []
        for symbol in syms:
            one = repo.get_minute(symbol, trade_date)
            if one is not None and not one.is_empty():
                if "symbol" not in one.columns:
                    one = one.with_columns(pl.lit(symbol).alias("symbol"))
                frames.append(one)
        return pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()

    df_local = _local_batch(stock_syms, "stock")
    if etf_syms:
        df_etf = _local_batch(etf_syms, "etf")
        if df_local.is_empty():
            df_local = df_etf
        elif not df_etf.is_empty():
            df_local = pl.concat([df_local, df_etf], how="diagonal_relaxed")

    now = cn_now()
    h, m = now.hour, now.minute
    if trade_date != cn_today():
        expected = 240
    elif h < 9 or (h == 9 and m < 30):
        expected = 0
    elif h < 12 or (h == 12 and m == 0):
        expected = (h - 9) * 60 + m - 30
    elif h < 13:
        expected = 120
    elif h < 15:
        expected = 120 + (h - 13) * 60 + m
    else:
        expected = 240

    _LUNCH_GAP_MIN = 91

    def _has_holes(sub: pl.DataFrame) -> bool:
        gaps = sub["datetime"].diff().dt.total_minutes().drop_nulls()
        return gaps.filter((gaps != 1) & (gaps != _LUNCH_GAP_MIN)).len() > 0

    result: dict[str, list[dict]] = {}
    full_pull: list[str] = []
    stale_last: dict[str, datetime] = {}
    local_parts: dict[str, pl.DataFrame] = {}
    minute_route = kline_sync.minute_route()
    if not df_local.is_empty() and "symbol" in df_local.columns:
        for part in df_local.partition_by("symbol", maintain_order=True):
            part = part.sort("datetime")
            if kline_sync.minute_cache_usable(part, minute_route):
                local_parts[part["symbol"][0]] = part
    fresh_floor = max(0, expected - 2)
    for sym in symbols:
        sub = local_parts.get(sym, pl.DataFrame())
        if expected == 0 or sub.height >= fresh_floor:
            if not sub.is_empty():
                result[sym] = _minute_rows_without_route(sub)
            continue
        if sub.is_empty() or _has_holes(sub):
            full_pull.append(sym)
        else:
            stale_last[sym] = sub["datetime"][-1]

    if not can_pull:
        for sym in symbols:
            if sym not in result:
                sub = local_parts.get(sym)
                if sub is not None and not sub.is_empty():
                    result[sym] = _minute_rows_without_route(sub)
        full_pull = []
        stale_last = {}

    full_minute_healthy = False
    if prefer_local:
        svc = getattr(request.app.state, "minute_refresh", None)
        full_minute_healthy = bool(svc is not None and svc.is_healthy())
    if full_minute_healthy:
        for sym in [*full_pull, *stale_last]:
            if sym not in etf_set:
                sub = local_parts.get(sym)
                if sub is not None and not sub.is_empty():
                    result[sym] = _minute_rows_without_route(sub)
        full_pull = [s for s in full_pull if s in etf_set]
        stale_last = {s: t for s, t in stale_last.items() if s in etf_set}

    day_start = datetime(trade_date.year, trade_date.month, trade_date.day, 9, 25, 0)
    session_end = datetime(trade_date.year, trade_date.month, trade_date.day, 15, 5, 0)
    lim = capset.limits(Cap.KLINE_MINUTE_BATCH) if can_pull else None
    store = getattr(repo, "store", None)
    data_dir = getattr(store, "data_dir", None) if store is not None else None
    minute_dirs = {
        "stock": data_dir / "kline_minute" if isinstance(data_dir, Path) else None,
        "etf": data_dir / "kline_etf_minute" if isinstance(data_dir, Path) else None,
    }
    live_map: dict[str, pl.DataFrame] = {}

    def _pull(asset: str, sym_list: list[str], start: datetime) -> None:
        if not can_pull or not sym_list:
            return
        df_live = kline_sync.sync_minute_batch(
            sym_list,
            start_time=start,
            end_time=session_end,
            batch_size=lim.batch if lim else None,
            rpm=lim.rpm if lim else None,
            asset_type=asset,
            capset=capset,
        )
        if df_live.is_empty():
            return
        try:
            minute_dir = minute_dirs[asset]
            write_lock = getattr(repo, "_write_lock", None)
            if isinstance(minute_dir, Path) and write_lock is not None:
                with write_lock:
                    kline_sync._write_minute_partition(
                        kline_sync._with_minute_route(df_live, kline_sync.minute_route()),
                        minute_dir,
                    )
        except Exception as e:  # noqa: BLE001
            logger.warning("minute-batch 补拉落盘失败 (降级为仅返回): %s", e)
        for part in df_live.partition_by("symbol", maintain_order=True):
            live_map[part["symbol"][0]] = part.sort("datetime")

    _pull("stock", [s for s in full_pull if s not in etf_set], day_start)
    _pull("etf", [s for s in full_pull if s in etf_set], day_start)
    if stale_last:
        inc_start = min(stale_last.values())
        if inc_start < session_end:
            _pull("stock", [s for s in stale_last if s not in etf_set], inc_start)
            _pull("etf", [s for s in stale_last if s in etf_set], inc_start)

    for sym, sub in local_parts.items():
        live = live_map.get(sym)
        if live is not None:
            merged = (
                pl.concat([sub, live])
                .unique(subset=["symbol", "datetime"], keep="last")
                .sort("datetime")
            )
            result[sym] = _minute_rows_without_route(merged)
    for sym, live in live_map.items():
        if sym not in result:
            result[sym] = _minute_rows_without_route(live)

    if since_dt is not None:
        result = {
            sym: [r for r in rows if r["datetime"] >= since_dt]
            for sym, rows in result.items()
        }
        result = {sym: rows for sym, rows in result.items() if rows}

    return _gzip_payload(
        request,
        {
            "data": result,
            "full_minute_local": full_minute_healthy,
            "incremental": since_dt is not None,
        },
        pref_key="minute_batch_compress",
    )


def _fetch_minute_live(symbol: str, trade_date: date, capset) -> object:
    return kline_sync.fetch_minute_single(symbol, trade_date, capset=capset)


@router.get("/minute")
def get_minute(
    request: Request,
    symbol: str = Query(..., description="标的代码"),
    trade_date: date | None = Query(None, alias="date", description="交易日期, 默认最新"),
    live: bool = Query(False, description="当日盘中跳过本地优先, 直接实时拉取(个股详情分时轮询用)"),
):
    """读取某只股票某天的分钟 K 线。

    - 本地有完整数据(240条) → 直接返回
    - 自选股历史日无数据 → 按需读取精确日期，日线对账后写入本地
    - 非自选股或当日数据 → 保持即时读取，不扩大全市场分钟数据
    - live=true 且当日连续竞价时段 → 跳过本地优先直接实时拉取
    - 自定义源失败时, 仅具备 TickFlow 单股分钟能力才回退 TickFlow
    """
    repo = request.app.state.repo
    capset = _http_capset(request)
    resolver = getattr(repo, "resolve_asset_type", None)
    asset_type = resolver(symbol) if callable(resolver) else "stock"
    stock_info = _get_stock_info(repo, symbol)
    stock_name = stock_info.get("name")

    def _minute_payload(rows, source: str, extra: dict | None = None):
        body = {
            "symbol": symbol, "name": stock_name, "stock_info": stock_info,
            "date": str(trade_date), "rows": _dicts_without_route(rows or []),
            "source": source,
        }
        if extra:
            body.update(extra)
        return _gzip_payload(request, body, pref_key="minute_batch_compress")

    if asset_type == "index":
        if trade_date is None:
            trade_date = cn_today()
        return _minute_payload([], "none")

    if trade_date is None:
        today = cn_today()
        need_fallback = today.weekday() >= 5
        if need_fallback:
            recent = None
            getter = getattr(repo, "latest_minute_date", None)
            if callable(getter):
                try:
                    recent = getter(symbol, asset_type=asset_type)
                except TypeError:
                    recent = getter(symbol)
            trade_date = recent if recent is not None else today
        else:
            trade_date = today

    today = cn_today()
    if live and trade_date == today and in_continuous_session():
        live_df = kline_sync.filter_minute_trade_date(
            _fetch_minute_live(symbol, trade_date, capset),
            trade_date,
        )
        if not live_df.is_empty():
            return _minute_payload(live_df.to_dicts(), "live")

    try:
        try:
            stored_minute = repo.get_minute(symbol, trade_date, asset_type=asset_type)
        except TypeError:
            stored_minute = repo.get_minute(symbol, trade_date)
        df = kline_sync.filter_minute_trade_date(stored_minute, trade_date)
    except KlineReadError as e:
        raise HTTPException(
            status_code=503,
            detail={"code": "kline_minute_read_failed", "message": str(e)},
        ) from e
    import polars as pl
    if not kline_sync.minute_cache_usable(df, kline_sync.minute_route()):
        df = pl.DataFrame()

    # 完整交易日应有 240 条分钟K；如果是今天(盘中)，期望条数按已交易分钟估算
    expected = 240
    if trade_date == today:
        now = cn_now()
        h, m = now.hour, now.minute
        if h < 9 or (h == 9 and m < 30):
            expected = 0  # 还没开盘
        elif h < 12 or (h == 12 and m == 0):
            expected = (h - 9) * 60 + m - 30  # 9:30 起
        elif h < 13:
            expected = 120  # 午休
        elif h < 15:
            expected = 120 + (h - 13) * 60 + m
        else:
            expected = 240

    is_complete = not df.is_empty() and len(df) >= expected * 0.9  # 允许 10% 容差

    if is_complete:
        return _minute_payload(df.to_dicts(), "local")

    # 自选股历史日按需读取并保存；不做全市场分钟数据扩展。
    from app.services import watchlist

    data_dir = getattr(getattr(repo, "store", None), "data_dir", None)
    is_watchlist = bool(data_dir) and watchlist.contains(symbol, data_dir=data_dir)
    if trade_date < today and is_watchlist:
        daily_getter = getattr(repo, "get_daily_asset", None)
        if callable(daily_getter):
            daily_df = daily_getter(asset_type, symbol, trade_date, trade_date)
        else:
            daily_df = repo.get_daily(symbol, trade_date, trade_date)

        def _accept_candidate(provider: str, lineage_source: str, candidate):
            result = kline_sync.persist_historical_minute(
                candidate,
                repo,
                symbol,
                trade_date,
                daily_df,
                source=lineage_source,
                adapter=provider,
            )
            try:
                from app.api.data import invalidate_storage_cache

                invalidate_storage_cache()
                catalog = getattr(request.app.state, "catalog_service", None)
                if catalog is not None:
                    catalog.refresh_after_mutation("stock_minute")
            except Exception as exc:  # noqa: BLE001
                logger.warning("stock_minute catalog refresh failed: %s", exc)
            try:
                stored_after = repo.get_minute(symbol, trade_date, asset_type=asset_type)
            except TypeError:
                stored_after = repo.get_minute(symbol, trade_date)
            stored = kline_sync.filter_minute_trade_date(
                stored_after,
                trade_date,
            )
            return _minute_payload(
                stored.to_dicts(),
                "local",
                {"provider": provider, "persisted": True, "quality": result},
            )

        # Leftover TickFlow may still use TDX then public/TickFlow (old contract).
        # Declared custom minute / prefs-unreadable / resolve failure must not.
        may_use_tdx = False
        try:
            may_use_tdx = kline_sync.minute_may_use_leftover_public()
        except Exception:  # noqa: BLE001
            may_use_tdx = False
        if may_use_tdx:
            try:
                from app.services.free_sources.tdx_history_minute import fetch_history_minute

                return _accept_candidate(
                    "easy_tdx_1.20.6",
                    "tdx_public",
                    fetch_history_minute(symbol, trade_date),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "TDX historical minute failed or rejected for %s %s: %s",
                    symbol,
                    trade_date,
                    exc,
                )

        # TDX 不可用或未允许时保留已有 TickFlow/公开源作为受同一质量门约束的兜底。
        try:
            return _accept_candidate(
                "runtime_minute_fallback",
                "runtime_minute_fallback",
                _fetch_minute_live(symbol, trade_date, capset),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "historical minute fallback rejected for %s %s: %s",
                symbol,
                trade_date,
                exc,
            )
        return _minute_payload([], "none")

    # 非自选股或今天：沿用即时读取，不写入历史缓存。
    live_df = kline_sync.filter_minute_trade_date(
        _fetch_minute_live(symbol, trade_date, capset),
        trade_date,
    )
    return _minute_payload(
        live_df.to_dicts(),
        "live" if not live_df.is_empty() else "none",
    )


@router.post("/sync_minute_single")
async def sync_minute_single(request: Request, body: dict):
    """手动拉取单只股票的分钟K并落库。指数代码显式 400, 避免污染 kline_minute。"""
    import asyncio

    from app.services.preferences import get_minute_sync_days

    symbol = str(body.get("symbol") or "").strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol 不能为空")

    repo = request.app.state.repo
    capset = _http_capset(request)
    resolver = getattr(repo, "resolve_asset_type", None)
    asset_type = resolver(symbol) if callable(resolver) else "stock"
    if asset_type == "index":
        raise HTTPException(
            status_code=400,
            detail="指数分钟K不支持落库同步 (指数分钟数据走 /api/index/minute 实时读取)",
        )
    if not _minute_allowed(capset):
        raise HTTPException(status_code=403, detail="需要 Pro+ 权限")

    requested_days = body.get("days")
    if requested_days is None:
        days = get_minute_sync_days()
    else:
        if isinstance(requested_days, bool) or not isinstance(requested_days, int):
            raise HTTPException(status_code=400, detail="days 必须是整数")
        if requested_days < 1 or requested_days > 30:
            raise HTTPException(status_code=400, detail="days 必须在 1 到 30 之间")
        days = requested_days

    loop = asyncio.get_event_loop()
    written = await loop.run_in_executor(
        None,
        lambda: kline_sync.sync_and_persist_minute(
            [symbol], repo, capset, days=days, force_full_days=True,
        ),
    )
    try:
        from app.jobs.daily_pipeline import _refresh_single_view

        _refresh_single_view(repo, "kline_minute")
    except Exception as exc:  # noqa: BLE001
        logger.debug("minute view refresh after single sync failed: %s", exc)
    return {"status": "ok", "symbol": symbol, "rows": written}


@router.post("/sync")
def sync_symbol(
    request: Request,
    symbol: str = Query(...),
    days: int = Query(250, ge=10, le=2000),
):
    """手动触发单股同步(Free 用户在 K 线页用)。"""
    repo = request.app.state.repo
    capset = _http_capset(request)
    n = kline_sync.sync_and_persist_daily_batch([symbol], repo, capset, count=days)
    return {"symbol": symbol, "rows_written": n}


@router.post("/sync_batch")
def sync_batch(
    request: Request,
    symbols: list[str],
    days: int = Query(250, ge=10, le=2000),
):
    repo = request.app.state.repo
    capset = _http_capset(request)
    n = kline_sync.sync_and_persist_daily_batch(symbols, repo, capset, count=days)
    return {"symbols": symbols, "rows_written": n}


@router.post("/refresh_views")
def refresh_views(request: Request):
    """刷新所有 DuckDB 视图(解决视图状态不一致问题)。"""
    from app.jobs.daily_pipeline import _refresh_views
    repo = request.app.state.repo
    _refresh_views(repo)
    return {"status": "ok"}


@router.post("/sync_minute")
async def sync_minute(request: Request):
    """手动触发分钟 K 同步(全市场)。返回 pipeline job_id 可轮询进度。"""
    import asyncio

    from app.services.pipeline_jobs import is_cancelled, job_store, release_run_slot, try_acquire_run_slot
    from app.api.data import invalidate_storage_cache
    from app.services.preferences import get_minute_sync_days
    repo = request.app.state.repo
    capset = _http_capset(request)

    if not _minute_allowed(capset):
        raise HTTPException(status_code=403, detail="需要分钟批量能力或已配置的自定义分钟源")

    created = job_store.create(work_key="kline.sync_minute", long_running=True)
    job_id = str(created)
    if not created.is_new:
        return {"status": "reused", "job_id": job_id}

    async def task() -> None:
        if is_cancelled(job_id):
            return
        if not try_acquire_run_slot(job_id):
            job_store.fail(job_id, "已有数据任务在运行(或上一次任务卡死未结束),请稍后再试")
            return
        try:
            job_store.start(job_id)
            loop = asyncio.get_event_loop()

            def progress(stage: str, pct: int, msg: str) -> None:
                job_store.progress(job_id, stage, pct, msg)

            try:
                progress("sync_minute", 5, "解析标的池…")
                universe = _resolve_minute_universe(capset, repo)
                progress("sync_minute", 10, f"标的池 {len(universe)} 只")

                days = get_minute_sync_days()

                def _run():
                    return kline_sync.sync_and_persist_minute(universe, repo, capset, days=days)

                written = await loop.run_in_executor(_long_task_executor, _run)

                from app.jobs.daily_pipeline import _refresh_single_view
                _refresh_single_view(repo, "kline_minute")

                progress("done", 100, f"分钟 K 同步完成,{written} 行")
                job_store.succeed(job_id, {"minute_rows": written, "universe_size": len(universe)})
                invalidate_storage_cache()
            except Exception as e:  # noqa: BLE001
                job_store.fail(job_id, str(e))
                invalidate_storage_cache()
        finally:
            release_run_slot(job_id)

    asyncio.create_task(task())
    return {"status": "started", "job_id": job_id}


@router.post("/extend_history")
async def extend_history(request: Request):
    """向前扩展历史日K数据 — 独立于盘后管道。

    body: { "value": int, "unit": "day"|"month"|"year" }
    返回 job_id,可轮询 /api/pipeline/jobs 查看进度。
    """
    import asyncio
    import traceback as _tb
    try:
        body = await request.json()
        value = body.get("value")
        unit = body.get("unit", "month")
        if not value or value <= 0:
            raise HTTPException(status_code=400, detail="value 必须为正整数")
        if unit not in ("day", "month", "year"):
            raise HTTPException(status_code=400, detail="unit 只支持 day/month/year")

        repo = request.app.state.repo
        capset = _http_capset(request)

        from app.tickflow.capabilities import Cap
        if not capset.has(Cap.KLINE_DAILY_BATCH) and not kline_sync.daily_provider_is_custom():
            raise HTTPException(status_code=403, detail="需要 Pro+ 权限 (batch K-line)")

        from app.services.extend_history import run_extend_history
        from app.services.pipeline_jobs import is_cancelled, job_store, release_run_slot, try_acquire_run_slot
        from app.api.data import invalidate_storage_cache

        created = job_store.create(work_key=f"kline.extend_history|{unit}|{value}")
        job_id = str(created)
        if not created.is_new:
            return {"status": "reused", "job_id": job_id}

        async def task() -> None:
            if is_cancelled(job_id):
                return
            if not try_acquire_run_slot(job_id):
                job_store.fail(job_id, "已有数据任务在运行(或上一次任务卡死未结束),请稍后再试")
                return
            try:
                job_store.start(job_id)
                loop = asyncio.get_event_loop()

                def progress(stage: str, pct: int, msg: str,
                             stage_pct: int | None = None, skip_log: bool = False) -> None:
                    job_store.progress(job_id, stage, pct, msg,
                                       stage_pct=stage_pct, skip_log=skip_log)

                try:
                    result = await loop.run_in_executor(
                        _long_task_executor,
                        lambda: run_extend_history(repo, capset, value, unit, on_progress=progress),
                    )
                    if "error" in result:
                        job_store.fail(job_id, result["error"])
                    else:
                        job_store.succeed(job_id, result)
                    invalidate_storage_cache()
                except Exception as e:
                    logger.exception("extend_history failed: job_id=%s", job_id)
                    job_store.fail(job_id, str(e))
                    invalidate_storage_cache()
            finally:
                release_run_slot(job_id)

        asyncio.create_task(task())
        return {"status": "started", "job_id": job_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("extend_history error: %s\n%s", e, _tb.format_exc())
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/rebuild_enriched")
async def rebuild_enriched(request: Request):
    """全量重算 enriched 表 — 不获取任何数据,仅基于已有 kline_daily + adj_factor 重算复权+指标。

    返回 job_id,可轮询 /api/pipeline/jobs 查看进度。
    """
    import asyncio
    try:
        repo = request.app.state.repo

        from app.services.pipeline_jobs import is_cancelled, job_store, release_run_slot, try_acquire_run_slot
        from app.api.data import invalidate_storage_cache

        created = job_store.create(work_key="kline.rebuild_enriched")
        job_id = str(created)
        if not created.is_new:
            return {"status": "reused", "job_id": job_id}

        async def task() -> None:
            if is_cancelled(job_id):
                return
            if not try_acquire_run_slot(job_id):
                job_store.fail(job_id, "已有数据任务在运行(或上一次任务卡死未结束),请稍后再试")
                return
            try:
                job_store.start(job_id)
                loop = asyncio.get_event_loop()

                def progress(stage: str, pct: int, msg: str,
                             stage_pct: int | None = None, skip_log: bool = False) -> None:
                    job_store.progress(job_id, stage, pct, msg,
                                       stage_pct=stage_pct, skip_log=skip_log)

                try:
                    progress("rebuild_enriched", 10, "全量计算 enriched…")
                    from app.indicators.pipeline import run_pipeline

                    def _batch_progress(cur: int, tot: int) -> None:
                        pct = 10 + int(85 * cur / tot)
                        progress("rebuild_enriched", pct,
                                 f"计算指标 批次 {cur}/{tot}",
                                 stage_pct=int(100 * cur / tot), skip_log=True)

                    written = await loop.run_in_executor(
                        _long_task_executor,
                        lambda: run_pipeline(on_batch_done=_batch_progress),
                    )

                    from app.jobs.daily_pipeline import _refresh_single_view
                    from app.services.kline_sync import safe_usable_daily_partition_dates

                    enriched_days = len(safe_usable_daily_partition_dates(
                        repo.store.data_dir, table="kline_daily_enriched",
                    ))
                    _refresh_single_view(repo, "kline_enriched")

                    progress("refresh_cache", 98, "刷新内存缓存…")
                    await loop.run_in_executor(_long_task_executor, repo.refresh_cache)
                    progress("rebuild_enriched", 100, f"完成,覆盖 {enriched_days} 天")
                    job_store.succeed(job_id, {
                        "enriched_days": enriched_days,
                        "enriched_rows": written,
                    })
                    invalidate_storage_cache()
                except Exception as e:
                    logger.exception("rebuild_enriched failed: job_id=%s", job_id)
                    job_store.fail(job_id, str(e))
                    invalidate_storage_cache()
            finally:
                release_run_slot(job_id)

        asyncio.create_task(task())
        return {"status": "started", "job_id": job_id}
    except Exception as e:
        import traceback as _tb
        logger.error("rebuild_enriched error: %s\n%s", e, _tb.format_exc())
        raise HTTPException(status_code=500, detail=str(e)) from e


# 长时间任务专用线程池（隔离于 FastAPI 默认线程池，防止阻塞请求处理）
import concurrent.futures as _cf
_long_task_executor = _cf.ThreadPoolExecutor(max_workers=2, thread_name_prefix="long-task")


@router.post("/extend_minute_history")
async def extend_minute_history(request: Request):
    """向前扩展分钟K历史数据 — 仅拉数据,不做任何后续处理。

    body: { "value": int, "unit": "day"|"month" }
    - day 单位:1~15 天(所有有分钟K权限的套餐可用)
    - month 单位:1~6 月(每月按 30 天计,即最多 180 天)—— 仅 Expert+ 可用
    返回 job_id,可轮询 /api/pipeline/jobs 查看进度。
    """
    import asyncio
    import traceback as _tb
    try:
        body = await request.json()
        value = body.get("value")
        unit = body.get("unit", "day")
        if not value or value <= 0:
            raise HTTPException(status_code=400, detail="value 必须为正整数")
        if unit not in ("day", "month"):
            raise HTTPException(status_code=400, detail="unit 只支持 day/month")

        repo = request.app.state.repo
        capset = _http_capset(request)

        from app.tickflow.capabilities import Cap
        if not _minute_allowed(capset):
            raise HTTPException(status_code=403, detail="需要分钟批量能力或已配置的自定义分钟源")

        # month 单位(按月扩展更长的分钟K历史)仅 Expert+ 开放;Pro 仅可用 day
        if unit == "month":
            from app.tickflow.policy import tier_label
            base_tier = tier_label().split()[0].split("+")[0].strip().lower()
            if base_tier != "expert":
                raise HTTPException(
                    status_code=403,
                    detail="按月扩展分钟K历史需要 Expert 及以上套餐",
                )

        # 计算天数上限:day 最多 15 天;month 最多 6 月(180 天)
        from datetime import timedelta
        if unit == "month":
            total_days = min(value * 30, 180)
        else:
            total_days = min(value, 15)

        if total_days <= 0:
            raise HTTPException(status_code=400, detail="扩展范围无效")

        from app.services.pipeline_jobs import is_cancelled, job_store, release_run_slot, try_acquire_run_slot
        from app.api.data import invalidate_storage_cache

        created = job_store.create(
            work_key=f"kline.extend_minute_history|{unit}|{total_days}",
            long_running=True,
        )
        job_id = str(created)
        if not created.is_new:
            return {"status": "reused", "job_id": job_id}

        async def task() -> None:
            if is_cancelled(job_id):
                return
            if not try_acquire_run_slot(job_id):
                job_store.fail(job_id, "已有数据任务在运行(或上一次任务卡死未结束),请稍后再试")
                return
            try:
                job_store.start(job_id)
                loop = asyncio.get_event_loop()

                def progress(stage: str, pct: int, msg: str,
                             stage_pct: int | None = None, skip_log: bool = False) -> None:
                    job_store.progress(job_id, stage, pct, msg,
                                       stage_pct=stage_pct, skip_log=skip_log)

                # 获取当前最早日期 — 只认当前 minute route 的分区,
                # 自定义分钟不得把 leftover TickFlow 最早日当成已覆盖。
                usable_dates = kline_sync.safe_usable_minute_partition_dates(repo.store.data_dir)
                earliest = usable_dates[0] if usable_dates else None
                if not earliest:
                    # 本地无当前源分钟K → 以今天为基准往前获取
                    from datetime import date as _date
                    latest = _date.today()
                else:
                    latest = earliest

                new_start = latest - timedelta(days=total_days)
                if new_start >= latest:
                    job_store.fail(job_id, "扩展范围无效")
                    invalidate_storage_cache()
                    return

                start_str = new_start.strftime("%Y-%m-%d")
                end_str = latest.strftime("%Y-%m-%d")

                progress("extend_minute", 5, "解析标的池…")
                universe = _resolve_minute_universe(capset, repo)
                progress("extend_minute", 8, f"标的池: {len(universe)} 只")

                from app.tickflow.capabilities import Cap

                lim = capset.limits(Cap.KLINE_MINUTE_BATCH)
                batch_size = lim.batch if lim and lim.batch else 100
                rpm = lim.rpm if lim else 30

                def _run():
                    """全部在 executor 线程里完成,避免阻塞事件循环。"""
                    from datetime import datetime as _dt

                    def _chunk(cur: int, tot: int) -> None:
                        progress("extend_minute", 8 + int(85 * cur / tot),
                                 f"分钟K 批次 {cur}/{tot}", stage_pct=int(100 * cur / tot), skip_log=True)

                    df = kline_sync.sync_minute_batch(
                        universe,
                        start_time=_dt.combine(new_start, _dt.min.time()),
                        end_time=_dt.combine(latest, _dt.min.time()),
                        batch_size=batch_size, rpm=rpm,
                        on_chunk_done=_chunk,
                        capset=capset,
                    )

                    written = kline_sync.persist_routed_minute_bars(df, repo)
                    day_count = 0
                    if written and df is not None and not df.is_empty() and "datetime" in df.columns:
                        day_count = int(df["datetime"].dt.date().n_unique())
                    return written, day_count

                progress("extend_minute", 10, f"获取分钟K [{start_str} ~ {end_str}]…")
                written, day_count = await loop.run_in_executor(_long_task_executor, _run)

                progress("extend_minute", 95, f"分钟K 完成,{day_count} 天")
                job_store.succeed(job_id, {
                    "minute_days": day_count,
                    "universe_size": len(universe),
                    "earliest_before": (earliest or latest).isoformat(),
                    "earliest_after": new_start.isoformat(),
                })
                invalidate_storage_cache()
            except Exception as e:
                logger.exception("extend_minute_history failed: job_id=%s", job_id)
                job_store.fail(job_id, str(e))
                invalidate_storage_cache()
            finally:
                release_run_slot(job_id)

        asyncio.create_task(task())
        return {"status": "started", "job_id": job_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("extend_minute_history error: %s\n%s", e, _tb.format_exc())
        raise HTTPException(status_code=500, detail=str(e)) from e


def _resolve_minute_universe(capset, repo) -> list[str]:
    """分钟K标的池解析。与盘后管道同一标的池，尊重 pool_provider。"""
    if not _minute_allowed(capset):
        return []
    try:
        from app.jobs.daily_pipeline import resolve_universe
        return resolve_universe(capset)
    except Exception:
        return []
