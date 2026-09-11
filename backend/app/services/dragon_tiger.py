"""龙虎榜数据服务 — 复盘页卡片 + AI 复盘上下文。

优先走 fuyao 三榜 (all/org/hot_money); 未配置或拉取失败时回退本地
HiThink 官方分区 `reference/hithink_dragon_tiger` (只读 parquet, 不现场拉取)。
两边都没有时才是 source_unavailable, 文案指向数据页同步, 而不是「必须 fuyao」。

数据契约 (实测 2026-08, 文档的 limit_reason/amount 实际不返回):
- 三榜一次取齐: all/org 为股票表 (org 额外带机构 4 字段), hot_money 为席位表
- 历史榜单不可变 → 按日落 JSON 缓存 (data/dragon_tiger/date=YYYY-MM-DD.json)
- 当日榜单盘中未发布 → 自动回退上一交易日并标记 state=fallback_prev
- 本地 HiThink 默认只有 board_type=all, 无席位表; 不写入 fuyao JSON 缓存

日期解析: 接口对显式非交易日报 code=1002, 本层用本地 kline_daily 分区日期
把目标日回退到「≤目标日的最近交易日」, 规避报错。
"""

from __future__ import annotations

import contextlib
import json
import logging
from datetime import date as date_cls
from pathlib import Path
from typing import Any

from app.market_time import cn_today

logger = logging.getLogger(__name__)

_BOARDS = ("all", "org", "hot_money")


def _local_trading_days(data_dir: Path) -> list[date_cls]:
    """本地日K分区日期 = 当前 route 可用交易日集合 (升序)。扫描失败返回空。"""
    from app.services.kline_sync import safe_usable_daily_partition_dates

    return safe_usable_daily_partition_dates(data_dir, table="kline_daily")


def resolve_trade_date(data_dir: Path, target: date_cls | None) -> date_cls | None:
    """目标日 → ≤目标日的最近本地交易日。None 或本地无更早分区 → None (由 fuyao 默认)。

    目标日早于全部本地分区 (极老的历史复盘) → 原样返回, 由调用方试显式日期,
    失败如实报 no_data, 不静默给错日期的数据。
    """
    if target is None:
        return None
    days = _local_trading_days(data_dir)
    if not days:
        return target
    candidates = [d for d in days if d <= target]
    return max(candidates) if candidates else target


def _prev_trading_day(data_dir: Path, d: date_cls) -> date_cls | None:
    days = _local_trading_days(data_dir)
    earlier = [x for x in days if x < d]
    return max(earlier) if earlier else None


def _provider():
    from app.data_providers import custom as custom_sources

    if not custom_sources.is_custom_provider("fuyao"):
        return None
    return custom_sources.get_provider("fuyao")


def _fetch_boards(provider, d: date_cls) -> dict:
    """三榜取齐。任一榜失败抛 FuyaoError (整日失败, 不留半套缓存)。"""
    return {
        bt: _boards_of(provider, bt, d.isoformat()) for bt in _BOARDS
    }


def _boards_of(provider, board_type: str, iso: str | None) -> dict:
    data = provider.dragon_tiger(board_type, iso)
    return {
        "trade_date": data.get("trade_date"),
        "stock_count": data.get("stock_count"),
        "count": data.get("count"),
        "stock_items": data.get("stock_items") or [],
        "hot_money_items": data.get("hot_money_items") or [],
    }


def _cache_path(data_dir: Path, d: date_cls) -> Path:
    return data_dir / "dragon_tiger" / f"date={d.isoformat()}.json"


def _load_cache(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _store_cache(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _as_decimal_ratio(value: Any) -> float | None:
    if value is None:
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x / 100.0 if abs(x) > 1.0 else x


def _parse_concept_list(raw: Any) -> list[dict] | None:
    if raw is None:
        return None
    data = raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            data = json.loads(text)
        except ValueError:
            return [{"name": text}]
    if isinstance(data, list):
        out: list[dict] = []
        for item in data:
            if isinstance(item, str):
                out.append({"name": item})
            elif isinstance(item, dict):
                name = item.get("name") or item.get("concept")
                out.append({"name": str(name) if name is not None else None})
            else:
                out.append({"name": str(item)})
        return out or None
    return [{"name": str(data)}]


def _hithink_stock_item(row: dict) -> dict:
    return {
        "thscode": row.get("symbol"),
        "ticker": row.get("ticker"),
        "name": row.get("name"),
        "change": _as_decimal_ratio(row.get("change_pct")),
        "net_value": row.get("net_value"),
        "net_rate": _as_decimal_ratio(row.get("net_rate")),
        "buy_value": row.get("buy_value"),
        "sell_value": row.get("sell_value"),
        "hot_rank": row.get("hot_rank"),
        "range_days": row.get("range_days"),
        "hot_money_net_value": row.get("hot_money_net_value"),
        "org_net_value": row.get("org_net_value"),
        "concept_list": _parse_concept_list(row.get("concept_list")),
        "limit_reason": row.get("limit_reason"),
    }


def _from_hithink_local(data_dir: Path, requested: date_cls | None) -> dict | None:
    """只读本地 HiThink 龙虎榜分区; 无分区返回 None。不写 fuyao JSON 缓存。"""
    from app.services.free_sources.hithink_finance import query_dragon_tiger

    resolved, frame = query_dragon_tiger(data_dir, trade_date=requested, limit=5_000)
    if frame is None or frame.is_empty():
        resolved, frame = query_dragon_tiger(data_dir, trade_date=None, limit=5_000)
    if frame is None or frame.is_empty() or resolved is None:
        return None

    today = cn_today()
    state = "ok"
    if requested is not None and resolved < requested:
        state = "fallback_prev"
    elif requested is None and resolved < today:
        state = "fallback_prev"

    rows = frame.to_dicts()
    all_rows = [row for row in rows if (row.get("board_type") or "all") == "all"] or rows
    org_rows = [row for row in rows if row.get("board_type") == "org"]
    if not org_rows:
        org_rows = [row for row in all_rows if row.get("org_net_value") is not None]
    items = [_hithink_stock_item(row) for row in all_rows]
    org_items = [_hithink_stock_item(row) for row in org_rows]
    iso = resolved.isoformat()
    return {
        "state": state,
        "source": "hithink_official",
        "requested_date": requested.isoformat() if requested else None,
        "trade_date": iso,
        "all": {
            "trade_date": iso,
            "stock_count": len(items),
            "count": len(items),
            "stock_items": items,
        },
        "org": {
            "trade_date": iso,
            "stock_count": len(org_items),
            "count": len(org_items),
            "stock_items": org_items,
        },
        "hot_money": {
            "trade_date": iso,
            "count": 0,
            "hot_money_items": [],
        },
    }


def get_dragon_tiger(data_dir: Path, target: date_cls | None = None) -> dict:
    """取龙虎榜 (三榜)。返回给前端的统一容器。

    state: ok (正常) | fallback_prev (当日未发布, 已回退上一期并带上一期数据)
          | source_unavailable (fuyao 与本地 HiThink 都没有) | no_data (拉取失败)
    """
    # 无目标日 → 最近本地交易日 (走缓存判定; 本地无任何分区才让 fuyao 自取默认)
    if target is None:
        days = _local_trading_days(data_dir)
        target = max(days) if days else None
    trade_date = resolve_trade_date(data_dir, target)
    today = cn_today()

    # 历史日缓存优先 (纯本地, 不触发插件注册表加载)
    if trade_date is not None and trade_date < today:
        cached = _load_cache(_cache_path(data_dir, trade_date))
        if cached is not None:
            return cached

    provider = _provider()
    if provider is None:
        local = _from_hithink_local(data_dir, trade_date)
        return local if local is not None else {"state": "source_unavailable"}

    from app.plugins.fuyao.client import FuyaoError

    # 日期未知 (target=None / 本地无分区) → 省略 date 让 fuyao 取最近已发布交易日
    explicit = trade_date.isoformat() if trade_date is not None else None
    try:
        raw = {bt: _boards_of(provider, bt, explicit) for bt in _BOARDS}
        try:
            actual = date_cls.fromisoformat(str(raw["all"].get("trade_date")))
        except ValueError:
            actual = None
        payload = {
            "state": "ok",
            "source": "fuyao",
            "requested_date": explicit,
            "trade_date": raw["all"].get("trade_date"),
            **raw,
        }
        # 历史日不可变 → 落缓存; 当日不缓存 (盘中 fallback / 盘后补充都以现拉为准)
        if actual is not None and actual < today:
            with contextlib.suppress(OSError):
                _store_cache(_cache_path(data_dir, actual), payload)
        return payload
    except FuyaoError as e:
        # 显式日期失败 (当日未发布 / 边界日) → 回退上一交易日一次
        if trade_date is not None:
            prev = _prev_trading_day(data_dir, trade_date)
            if prev is not None:
                try:
                    cached_prev = _load_cache(_cache_path(data_dir, prev))
                    if cached_prev is not None:
                        base = dict(cached_prev)
                        base.pop("state", None)
                        return {**base, "state": "fallback_prev",
                                "requested_date": explicit}
                    raw_prev = _fetch_boards(provider, prev)
                    base = {
                        "source": "fuyao",
                        "requested_date": prev.isoformat(),
                        "trade_date": prev.isoformat(),
                        **raw_prev,
                    }
                    with contextlib.suppress(OSError):
                        _store_cache(_cache_path(data_dir, prev), {**base, "state": "ok"})
                    return {**base, "state": "fallback_prev",
                            "requested_date": explicit}
                except FuyaoError:
                    pass
        local = _from_hithink_local(data_dir, trade_date)
        if local is not None:
            return local
        logger.warning("龙虎榜拉取失败: %s", e)
        return {"state": "no_data", "message": str(e)}


def build_recap_context(data_dir: Path) -> str:
    """AI 复盘的龙虎榜摘要段 (纯文本, 失败返回空串不影响复盘)。"""
    try:
        payload = get_dragon_tiger(data_dir, None)
        if payload.get("state") not in ("ok", "fallback_prev"):
            return ""
        items = payload.get("all", {}).get("stock_items") or []
        org_items = payload.get("org", {}).get("stock_items") or []
        hm_items = payload.get("hot_money", {}).get("hot_money_items") or []
        trade_date = payload.get("trade_date") or ""
        lines = [f"(数据日期: {trade_date})"]

        top_buy = sorted(
            [i for i in items if (i.get("net_value") or 0) > 0],
            key=lambda x: x.get("net_value") or 0, reverse=True,
        )[:5]
        if top_buy:
            lines.append("净买入居前: " + "; ".join(
                f"{i.get('name')}({i.get('thscode')}) 净买{float(i.get('net_value') or 0)/1e8:.2f}亿"
                f" 涨跌{(i.get('change') or 0)*100:.1f}%"
                + (" [3日榜]" if i.get("range_days") == 3 else "")
                for i in top_buy))
        top_sell = sorted(
            [i for i in items if (i.get("net_value") or 0) < 0],
            key=lambda x: x.get("net_value") or 0,
        )[:5]
        if top_sell:
            lines.append("净卖出居前: " + "; ".join(
                f"{i.get('name')} 净卖{abs(float(i.get('net_value') or 0))/1e8:.2f}亿"
                for i in top_sell))
        if org_items:
            lines.append("机构净买居前: " + "; ".join(
                f"{i.get('name')} 机构净买{float(i.get('org_net_value') or 0)/1e8:.2f}亿"
                for i in sorted(org_items, key=lambda x: x.get("org_net_value") or 0, reverse=True)[:5]))
        if hm_items:
            lines.append("活跃游资: " + "; ".join(
                f"{h.get('name')} 净买{float(h.get('buying') or 0)/1e8:.2f}亿"
                for h in sorted(hm_items, key=lambda x: x.get('buying') or 0, reverse=True)[:5]))
        return "\n".join(lines)
    except Exception as e:  # noqa: BLE001 — 摘要失败不影响复盘主流程
        logger.debug("龙虎榜复盘摘要构建失败: %s", e)
        return ""
