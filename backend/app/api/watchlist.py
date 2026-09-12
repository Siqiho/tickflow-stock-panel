"""自选股 API。"""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from typing import Callable

import polars as pl
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel

from app.services import watchlist
from app.services.watchlist_csv import import_watchlist_codes, import_watchlist_csv

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class AddRequest(BaseModel):
    symbol: str
    note: str = ""
    group_id: str | None = None


class BatchAddRequest(BaseModel):
    symbols: list[str]
    note: str = ""
    group_id: str | None = None
    group_ids: list[str] | None = None


class GroupNameRequest(BaseModel):
    name: str
    color: str | None = None


class GroupReorderRequest(BaseModel):
    ordered_ids: list[str]


class GroupAssignRequest(BaseModel):
    group_id: str | None = None


class ImportCodesRequest(BaseModel):
    text: str


_MAX_IMPORT_CSV_BYTES = 5 * 1024 * 1024
_IMPORT_CSV_TYPES = {
    "text/csv",
    "text/plain",
    "application/csv",
}
_UPLOAD_CHUNK_BYTES = 1024 * 1024


async def _read_upload_capped(file: UploadFile, max_bytes: int, too_large: str) -> bytes:
    """分块读取上传。越过上限立即 400，避免先整文件进内存。"""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(400, too_large)
        chunks.append(chunk)
    return b"".join(chunks)


def _run_candidate_import(parse: Callable[[], dict], empty_msg: str) -> dict:
    """解析候选：ValueError→400、空候选→400、剥离 raw_text。不写入自选。"""
    try:
        result = parse()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result["candidates"]:
        raise HTTPException(status_code=400, detail=empty_msg)
    result.pop("raw_text", None)
    return result


def _require_watchlist_capacity(symbols: list[str]) -> None:
    from app.config import settings
    from app.services import user_context

    if user_context.is_admin():
        return
    existing = {str(row.get("symbol") or "").upper() for row in watchlist.list_symbols()}
    additions = {str(symbol or "").strip().upper() for symbol in symbols} - existing
    limit = max(0, int(settings.user_watchlist_limit))
    if len(existing) + len(additions) > limit:
        raise HTTPException(
            status_code=429,
            detail={"code": "watchlist_quota_exhausted", "message": f"自选股最多 {limit} 只"},
        )


def _with_names(rows: list[dict], request: Request) -> list[dict]:
    if not rows:
        return rows
    try:
        df_i = request.app.state.repo.get_instruments()
        if df_i.is_empty() or "symbol" not in df_i.columns or "name" not in df_i.columns:
            return rows
        name_by_symbol = dict(df_i.select(["symbol", "name"]).iter_rows())
        return [{**row, "name": name_by_symbol.get(row.get("symbol"))} for row in rows]
    except Exception as e:  # noqa: BLE001
        logger.debug("attach watchlist names failed: %s", e)
        return rows


@router.get("")
def list_all(request: Request):
    return {"symbols": _with_names(watchlist.list_symbols(), request)}


@router.post("")
def add_one(req: AddRequest, request: Request):
    _require_watchlist_capacity([req.symbol])
    rows = watchlist.add(req.symbol, req.note, req.group_id)
    return {"symbols": _with_names(rows, request)}


@router.post("/batch")
def add_batch(req: BatchAddRequest, request: Request):
    _require_watchlist_capacity(req.symbols)
    rows, added = watchlist.add_batch(req.symbols, req.note, req.group_id)
    return {"symbols": _with_names(rows, request), "added": added}


@router.get("/groups")
def list_groups():
    return {"groups": watchlist.list_groups()}


@router.post("/groups")
def create_group(req: GroupNameRequest):
    try:
        groups, group = watchlist.create_group(req.name, req.color)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"groups": groups, "group": group}


@router.put("/groups/reorder")
def reorder_groups(req: GroupReorderRequest):
    try:
        groups = watchlist.reorder_groups(req.ordered_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"groups": groups}


@router.put("/groups/{group_id}")
def rename_group(group_id: str, req: GroupNameRequest):
    try:
        groups = watchlist.rename_group(group_id, req.name, req.color)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"分组不存在: {group_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"groups": groups}


@router.delete("/groups/{group_id}")
def delete_group(group_id: str, request: Request):
    try:
        groups, rows = watchlist.delete_group(group_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"分组不存在: {group_id}") from exc
    return {"groups": groups, "symbols": _with_names(rows, request)}


@router.post("/groups/{group_id}/clear")
def clear_group(group_id: str, request: Request):
    rows = watchlist.clear_group(group_id)
    return {"symbols": _with_names(rows, request)}


@router.post("/import-csv")
async def import_from_csv(request: Request, file: UploadFile = File(...)):
    """CSV/TXT → 候选列表。只解析、不去重写入；确认导入仍走 /batch。"""
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    filename = (file.filename or "").lower()
    ok_type = content_type in _IMPORT_CSV_TYPES
    ok_ext = filename.endswith((".csv", ".txt"))
    if not ok_type and not ok_ext:
        raise HTTPException(status_code=400, detail="仅支持 CSV / TXT 文件")

    data = await _read_upload_capped(file, _MAX_IMPORT_CSV_BYTES, "文件过大（上限 5MB）")
    if not data:
        raise HTTPException(status_code=400, detail="空文件")

    data_dir = request.app.state.repo.store.data_dir
    return _run_candidate_import(
        lambda: import_watchlist_csv(
            data,
            data_dir,
            existing_symbols={r["symbol"] for r in watchlist.list_symbols()},
        ),
        "文件中未识别到股票代码或名称",
    )


@router.post("/import-codes")
def import_from_codes(req: ImportCodesRequest, request: Request):
    """粘贴证券代码 → 候选列表。去重保序，不写入自选。"""
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="请输入要导入的股票代码")

    existing = {r["symbol"] for r in watchlist.list_symbols()}
    data_dir = request.app.state.repo.store.data_dir
    return _run_candidate_import(
        lambda: import_watchlist_codes(text, data_dir, existing_symbols=existing),
        "未识别到股票代码",
    )


@router.put("/{symbol}/group")
def assign_group(symbol: str, req: GroupAssignRequest, request: Request):
    try:
        rows = watchlist.set_group(symbol, req.group_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"symbols": _with_names(rows, request)}


@router.post("/groups/{group_id}/members/{symbol}")
def add_member(group_id: str, symbol: str, request: Request):
    try:
        rows = watchlist.add_to_group(symbol, group_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"symbols": _with_names(rows, request)}


@router.delete("/groups/{group_id}/members/{symbol}")
def remove_member(group_id: str, symbol: str, request: Request):
    try:
        rows = watchlist.remove_from_group(symbol, group_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"symbols": _with_names(rows, request)}


@router.post("/{symbol}/top")
def move_one_to_top(symbol: str, request: Request):
    rows = watchlist.move_to_top(symbol)
    return {"symbols": _with_names(rows, request)}


@router.delete("/{symbol}")
def remove_one(symbol: str, request: Request):
    rows = watchlist.remove(symbol)
    return {"symbols": _with_names(rows, request)}


@router.delete("")
def clear_all():
    """清空自选列表。"""
    count = watchlist.clear()
    return {"removed": count}


# 自选页需要的列
_WATCHLIST_COLS = [
    "symbol",
    "close",
    "change_pct",
    "change_amount",
    "amount",
    "turnover_rate",
    "amplitude",
    "annual_vol_20d",
    "vol_ratio_5d",
    "ma5",
    "ma10",
    "ma20",
    "ma60",
    "vol_ma5",
    "vol_ma10",
    "high_60d",
    "low_60d",
    "rsi_6",
    "rsi_14",
    "rsi_24",
    "macd_dif",
    "macd_dea",
    "macd_hist",
    "kdj_k",
    "kdj_d",
    "kdj_j",
    "boll_upper",
    "boll_lower",
    "atr_14",
    "momentum_5d",
    "momentum_10d",
    "momentum_20d",
    "momentum_30d",
    "momentum_60d",
    "consecutive_limit_ups",
    "consecutive_limit_downs",
    "signal_limit_up",
    "signal_limit_down",
    "signal_volume_surge",
    "signal_ma_golden_5_20",
    "signal_macd_golden",
    "signal_n_day_high",
    "signal_boll_breakout_upper",
    "signal_ma20_breakout",
    "signal_ma_dead_5_20",
    "signal_macd_dead",
    "signal_n_day_low",
    "signal_boll_breakdown_lower",
    "signal_ma20_breakdown",
    "eps",
    "bps",
    "roe",
    "pe_ttm",
    "pb",
    "gross_margin",
    "net_margin",
    "revenue_yoy",
    "net_income_yoy",
    "debt_ratio",
]


_FINANCIAL_METRIC_FIELDS = {
    "basic_eps": ("eps", False),
    "bps": ("bps", False),
    "roe": ("roe", True),
    "gross_margin": ("gross_margin", True),
    "net_margin": ("net_margin", True),
    "total_revenue_yoy": ("revenue_yoy", True),
    "parent_net_profit_yoy": ("net_income_yoy", True),
    "asset_liab_ratio": ("debt_ratio", True),
}

_INDUSTRY_FUND_FLOW_CONFIGS = {"ext_fund_flow_bk", "ext_fund_flow_bk_daily"}
_CONCEPT_FUND_FLOW_CONFIGS = {"ext_fund_flow_concept", "ext_fund_flow_concept_daily"}
_INDUSTRY_SUFFIX_RE = re.compile(r"[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+$")


def _latest_realtime_snapshot(
    repo, symbols: list[str], cache_date
) -> tuple[pl.DataFrame, str | None]:
    """读取最新股票行情快照并转换为自选页 rt_* 覆盖列。"""
    data_dir = getattr(getattr(repo, "store", None), "data_dir", None)
    if data_dir is None:
        return pl.DataFrame(), None
    base = data_dir / "quote_snapshot" / "asset_type=stock"
    parts = sorted(base.glob("date=*/part.parquet"), key=lambda path: path.parent.name)
    if not parts:
        return pl.DataFrame(), None
    try:
        from app.services.quote_service import quote_snapshot_partition_usable

        usable = [path for path in reversed(parts) if quote_snapshot_partition_usable(path)]
        if not usable:
            return pl.DataFrame(), None
        snapshot = pl.read_parquet(usable[0])
    except Exception as exc:
        logger.debug("read watchlist realtime snapshot failed: %s", exc)
        return pl.DataFrame(), None
    if snapshot.is_empty() or "symbol" not in snapshot.columns:
        return pl.DataFrame(), None

    snapshot_date = None
    if "date" in snapshot.columns:
        snapshot_date = snapshot.select(pl.col("date").max()).item()
        if cache_date is not None and str(snapshot_date) < str(cache_date):
            return pl.DataFrame(), None

    snapshot = snapshot.filter(pl.col("symbol").is_in(symbols))
    if snapshot.is_empty() or "close" not in snapshot.columns:
        return pl.DataFrame(), None

    columns = [pl.col("symbol"), pl.col("close").alias("rt_price")]
    if "change_pct" in snapshot.columns:
        # quote_snapshot 使用百分点, Watchlist fmtPct 使用小数比例。
        columns.append((pl.col("change_pct") / 100.0).alias("rt_pct"))
    if "change_amount" in snapshot.columns:
        columns.append(pl.col("change_amount").alias("rt_change_amount"))
    if "amount" in snapshot.columns:
        columns.append(pl.col("amount").alias("rt_amount"))
    if "name" in snapshot.columns:
        columns.append(pl.col("name").alias("rt_name"))
    if "source" in snapshot.columns:
        columns.append(pl.col("source").alias("rt_source"))
    if "date" in snapshot.columns:
        columns.append(pl.col("date").cast(pl.Utf8).alias("rt_date"))
    if "fetched_at" in snapshot.columns:
        columns.append(pl.col("fetched_at").alias("rt_fetched_at"))

    realtime = snapshot.select(columns).unique(subset=["symbol"], keep="last")
    realtime_as_of = None
    if "rt_fetched_at" in realtime.columns:
        values = realtime["rt_fetched_at"].drop_nulls()
        if len(values) > 0:
            realtime_as_of = str(values[0])
    if realtime_as_of is None and snapshot_date is not None:
        realtime_as_of = str(snapshot_date)
    return realtime, realtime_as_of


def _join_local_financial_metrics(df: pl.DataFrame, repo, symbols: list[str]) -> pl.DataFrame:
    """用本地公开财务指标补齐自选股财务列, 不覆盖已有 provider 值。"""
    data_dir = getattr(getattr(repo, "store", None), "data_dir", None)
    if data_dir is None:
        return df
    try:
        from app.services.financial_sync import get_financial_df
        metrics = get_financial_df(data_dir, "metrics")
    except Exception as exc:
        logger.debug("read watchlist financial metrics failed: %s", exc)
        return df
    if metrics.is_empty() or "symbol" not in metrics.columns:
        return df

    available = [source for source in _FINANCIAL_METRIC_FIELDS if source in metrics.columns]
    if not available:
        return df
    metrics = metrics.filter(pl.col("symbol").is_in(symbols))
    if metrics.is_empty():
        return df

    sort_columns = [
        column
        for column in ("symbol", "period_end", "update_date", "fetched_at", "restatement_id")
        if column in metrics.columns
    ]
    if sort_columns:
        metrics = metrics.sort(sort_columns)
    metrics = metrics.unique(subset=["symbol"], keep="last")

    expressions = [pl.col("symbol")]
    joined_columns: list[str] = []
    for source in available:
        target, percent_points = _FINANCIAL_METRIC_FIELDS[source]
        joined = f"_financial_{target}"
        value = pl.col(source).cast(pl.Float64, strict=False)
        if percent_points:
            value = value / 100.0
        expressions.append(value.alias(joined))
        joined_columns.append(target)
    metrics = metrics.select(expressions)
    df = df.join(metrics, on="symbol", how="left")

    for target in joined_columns:
        joined = f"_financial_{target}"
        if target in df.columns:
            df = df.with_columns(pl.coalesce([pl.col(target), pl.col(joined)]).alias(target)).drop(
                joined
            )
        else:
            df = df.rename({joined: target})
    return df


def _read_ext_for_watchlist(config, data_dir, symbols: list[str]) -> pl.DataFrame:
    """读取扩展表; 稀疏个股时序按每只股票各自的最新记录收口。"""
    from app.api.ext_data import _read_ext_dataframe

    field_names = {field.name for field in config.fields}
    if config.mode != "timeseries" or "symbol" not in field_names:
        ext_df, _ = _read_ext_dataframe(config, data_dir)
        return ext_df

    base = data_dir / "ext_data" / config.id / "timeseries"
    parts = sorted(base.glob("date=*/part.parquet")) if base.exists() else []
    if not parts:
        return pl.DataFrame()
    try:
        ext_df = pl.read_parquet(parts)
    except Exception as exc:
        logger.debug("read watchlist ext history failed for %s: %s", config.id, exc)
        return pl.DataFrame()
    if ext_df.is_empty() or "symbol" not in ext_df.columns:
        return ext_df
    ext_df = ext_df.filter(pl.col("symbol").is_in(symbols))
    sort_columns = [
        column for column in ("symbol", "date", "as_of", "snap_time") if column in ext_df.columns
    ]
    if sort_columns:
        ext_df = ext_df.sort(sort_columns)
    return ext_df.unique(subset=["symbol"], keep="last")


def _normalize_industry_name(value: object) -> str:
    text = re.sub(r"\s+", "", str(value or "").strip())
    return _INDUSTRY_SUFFIX_RE.sub("", text)


def _membership_rows(config_id: str, data_dir) -> pl.DataFrame:
    from app.api.ext_data import _read_ext_dataframe
    from app.services.ext_data import ExtConfigStore

    membership_id = "ext_hy_ths" if config_id in _INDUSTRY_FUND_FLOW_CONFIGS else "ext_gn_ths"
    membership = ExtConfigStore(data_dir).get(membership_id)
    if membership is None:
        return pl.DataFrame()
    membership_df, _ = _read_ext_dataframe(membership, data_dir)
    return membership_df


def _resolve_fund_flow_membership(
    config_id: str,
    ext_df: pl.DataFrame,
    data_dir,
    symbols: list[str],
    fields: list[str],
) -> pl.DataFrame:
    """把板块粒度资金流投影到股票; 不对重叠概念做虚假加总。"""
    if ext_df.is_empty() or "name" not in ext_df.columns:
        return pl.DataFrame()
    membership_df = _membership_rows(config_id, data_dir)
    membership_field = "所属同花顺行业" if config_id in _INDUSTRY_FUND_FLOW_CONFIGS else "所属概念"
    if (
        membership_df.is_empty()
        or "symbol" not in membership_df.columns
        or membership_field not in membership_df.columns
    ):
        return pl.DataFrame()

    membership_by_symbol = {
        row["symbol"]: row[membership_field]
        for row in membership_df.filter(pl.col("symbol").is_in(symbols))
        .select(["symbol", membership_field])
        .unique(subset=["symbol"], keep="last")
        .to_dicts()
    }
    fund_rows = ext_df.to_dicts()

    if config_id in _INDUSTRY_FUND_FLOW_CONFIGS:
        by_name: dict[str, dict] = {}
        for row in fund_rows:
            normalized = _normalize_industry_name(row.get("name"))
            if normalized:
                by_name[normalized] = row

        def choose(value: object) -> dict | None:
            components = [part for part in str(value or "").split("-") if part]
            for component in reversed(components):
                matched = by_name.get(_normalize_industry_name(component))
                if matched is not None:
                    return matched
            return None
    else:
        by_name = {str(row.get("name") or "").strip(): row for row in fund_rows if row.get("name")}

        def choose(value: object) -> dict | None:
            candidates = [
                by_name[name]
                for name in (part.strip() for part in str(value or "").split(";"))
                if name in by_name
            ]
            if not candidates:
                return None
            if any(row.get("rank") is not None for row in candidates):
                return min(
                    candidates,
                    key=lambda row: (
                        row.get("rank") if row.get("rank") is not None else float("inf")
                    ),
                )
            if any(row.get("main_net") is not None for row in candidates):
                return max(candidates, key=lambda row: abs(float(row.get("main_net") or 0.0)))
            return sorted(candidates, key=lambda row: str(row.get("name") or ""))[0]

    rows = []
    for symbol in symbols:
        selected = choose(membership_by_symbol.get(symbol))
        row = {"symbol": symbol}
        for field in fields:
            row[f"{config_id}__{field}"] = selected.get(field) if selected is not None else None
        rows.append(row)
    return pl.DataFrame(rows)


def _direct_ext_join(
    config_id: str,
    ext_df: pl.DataFrame,
    fields: list[str],
) -> pl.DataFrame:
    if ext_df.is_empty() or "symbol" not in ext_df.columns:
        return pl.DataFrame()
    available = [field for field in fields if field in ext_df.columns]
    if not available:
        return pl.DataFrame()
    rename = {field: f"{config_id}__{field}" for field in available}
    return (
        ext_df.select(["symbol", *available]).unique(subset=["symbol"], keep="last").rename(rename)
    )


@router.get("/enriched")
def watchlist_enriched(
    request: Request,
    ext_columns: str | None = Query(None, description="逗号分隔的 ext 列: config_id.field_name"),
):
    """自选股 enriched 数据 — 直接从 enriched 最新日读取, 无即时计算。

    ext_columns 参数示例: "industry_rating.score,fund_flow.net_inflow"
    会动态 LEFT JOIN 对应的 ext_{config_id} DuckDB view。
    """
    t0 = time.perf_counter()

    repo = request.app.state.repo
    symbols = [r["symbol"] for r in watchlist.list_symbols()]
    if not symbols:
        return {"rows": [], "as_of": None, "elapsed_ms": 0}

    df_e, cache_date = repo.get_enriched_latest()
    # 自选列表是页面主表；最新 enriched 分区只是可缺失的增强数据。
    # 以 enriched 为主表做 filter 会把不在当日同步范围内的自选股整行丢失。
    watchlist_df = pl.DataFrame({"symbol": symbols})
    df = watchlist_df if df_e.is_empty() else watchlist_df.join(df_e, on="symbol", how="left")

    # JOIN instruments 取 name + float_shares
    df_i = repo.get_instruments()
    if not df_i.is_empty() and "name" in df_i.columns:
        inst_cols = [c for c in ["symbol", "name", "float_shares"] if c in df_i.columns]
        df = df.join(df_i.select(inst_cols), on="symbol", how="left", suffix="_instrument")
        for column in ("name", "float_shares"):
            instrument_column = f"{column}_instrument"
            if instrument_column not in df.columns:
                continue
            if column in df.columns:
                df = df.with_columns(
                    pl.coalesce([pl.col(instrument_column), pl.col(column)]).alias(column)
                ).drop(instrument_column)
            else:
                df = df.rename({instrument_column: column})

    # 选择内置需要的列
    keep = [c for c in _WATCHLIST_COLS + ["name", "float_shares"] if c in df.columns]
    df = df.select(keep)

    # 免费公开财务表以百分点存储; 转换为前端统一的小数比例并作为已有 provider 的兜底。
    df = _join_local_financial_metrics(df, repo, symbols)

    # 实时快照只覆盖页面 rt_* 字段; 正式 close/指标仍保持盘后数据语义。
    realtime_df, realtime_as_of = _latest_realtime_snapshot(repo, symbols, cache_date)
    if not realtime_df.is_empty():
        df = df.join(realtime_df, on="symbol", how="left")

    # 动态 JOIN 扩展数据表
    ext_specs = _parse_ext_columns(ext_columns) if ext_columns else []
    if ext_specs:
        data_dir = repo.store.data_dir
        from app.services.ext_data import ExtConfigStore

        ext_store = ExtConfigStore(data_dir)
        configs = {c.id: c for c in ext_store.load_all()}

        specs_by_config: dict[str, list[str]] = defaultdict(list)
        for config_id, field_name in ext_specs:
            if field_name not in specs_by_config[config_id]:
                specs_by_config[config_id].append(field_name)

        for config_id, field_names in specs_by_config.items():
            try:
                cfg = configs.get(config_id)
                if cfg is not None:
                    ext_df = _read_ext_for_watchlist(cfg, data_dir, symbols)
                    if config_id in _INDUSTRY_FUND_FLOW_CONFIGS | _CONCEPT_FUND_FLOW_CONFIGS:
                        join_df = _resolve_fund_flow_membership(
                            config_id,
                            ext_df,
                            data_dir,
                            symbols,
                            field_names,
                        )
                    else:
                        join_df = _direct_ext_join(config_id, ext_df, field_names)
                else:
                    # Missing ext config: do not leftover-union DuckDB ext_* views.
                    continue
                if not join_df.is_empty():
                    df = df.join(join_df, on="symbol", how="left")
            except Exception as exc:
                logger.debug("ext join failed for %s.%s: %s", config_id, field_names, exc)

    # sanitize NaN / Inf
    float_cols = [c for c in df.columns if df[c].dtype.is_float()]
    if float_cols:
        df = df.with_columns(
            [
                pl.when(pl.col(c).is_nan() | pl.col(c).is_infinite())
                .then(None)
                .otherwise(pl.col(c))
                .alias(c)
                for c in float_cols
            ]
        )

    # 按自选添加顺序（新加的在前）重排行
    order_map = {s: i for i, s in enumerate(symbols)}
    df = df.with_columns(
        pl.col("symbol")
        .map_elements(lambda s: order_map.get(s, len(symbols)), return_dtype=pl.Int32)
        .alias("_sort_order")
    )
    df = df.sort("_sort_order").drop("_sort_order")

    rows = df.to_dicts()
    elapsed = (time.perf_counter() - t0) * 1000
    realtime_count = sum(row.get("rt_price") is not None for row in rows)
    return {
        "rows": rows,
        "as_of": str(cache_date) if cache_date else None,
        "realtime_as_of": realtime_as_of,
        "realtime_count": realtime_count,
        "elapsed_ms": elapsed,
    }


def _parse_ext_columns(ext_columns: str) -> list[tuple[str, str]]:
    """解析 'config_id1.field1,config_id2.field2' 为 [(config_id, field_name), ...]"""
    result = []
    for part in ext_columns.split(","):
        part = part.strip()
        if "." not in part:
            continue
        config_id, field_name = part.split(".", 1)
        config_id = config_id.strip()
        field_name = field_name.strip()
        if config_id and field_name:
            result.append((config_id, field_name))
    return result


@router.get("/ocr-status")
def ocr_status():
    try:
        from app.services.watchlist_ocr.provider import get_ocr_provider
        provider = get_ocr_provider()
        return {"provider": getattr(provider, "name", "unknown"), "available": True}
    except Exception:
        return {"provider": "none", "available": False}


@router.post("/import-image")
async def import_image(request: Request):
    from fastapi import HTTPException, UploadFile
    form = await request.form()
    upload = form.get("file")
    if upload is None:
        raise HTTPException(400, "缺少图片文件")
    try:
        from app.services.watchlist_ocr import import_watchlist_image
        data = await upload.read()
        return import_watchlist_image(data, filename=getattr(upload, "filename", "upload.png"), repo=request.app.state.repo)
    except ImportError as exc:
        raise HTTPException(503, "OCR 识别未安装或不可用") from exc

