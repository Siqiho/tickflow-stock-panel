from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import polars as pl
import pytest

from app.services.free_sources.hithink_finance import (
    AUCTION_PATH,
    DRAGON_TIGER_PATH,
    LIMIT_BREAK_PATH,
    LIMIT_DOWN_PATH,
    LIMIT_UP_PATH,
    VALUATION_PATH,
    HiThinkFinanceClient,
    HiThinkQualityError,
    canonical_symbol,
    normalize_auction_snapshot,
    normalize_dragon_tiger,
    normalize_limit_pool,
    normalize_valuation_snapshot,
    query_auction_snapshot,
    query_dragon_tiger,
    query_limit_pool,
    query_valuation_snapshot,
    load_limit_pool_for_date,
    summarize_limit_pool_kpi,
    sync_hithink_special_data,
)


def _envelope(data: dict) -> dict:
    return {"code": 0, "message": "ok", "request_id": "req-1", "data": data}


def _limit_up_row(symbol: str = "600519.SH") -> dict:
    return {
        "thscode": symbol,
        "ticker": symbol.split(".")[0],
        "name": "贵州茅台",
        "is_st": False,
        "is_new": False,
        "last_price": 1800.5,
        "price_change_ratio_pct": 10.0,
        "limit_up_time": "09:30:01",
        "limit_up_reason": "业绩预增",
        "continue_day_text": "首板",
        "continue_day_cnt": 1,
        "seal_money": 1_200_000.0,
        "max_seal_money": 2_000_000.0,
    }


def _limit_down_row(symbol: str = "000001.SZ") -> dict:
    return {
        "thscode": symbol,
        "ticker": symbol.split(".")[0],
        "name": "平安银行",
        "last_price": 10.0,
        "first_limit_time": "10:01:00",
        "last_limit_time": "14:50:00",
        "turnover_ratio_pct": 3.2,
    }


def _limit_break_row(symbol: str = "300502.SZ") -> dict:
    return {
        "thscode": symbol,
        "ticker": symbol.split(".")[0],
        "name": "新易盛",
        "open_times": 2,
        "turnover": 8_800_000.0,
    }


def _dragon_payload(trade_date: date) -> dict:
    return {
        "trade_date": trade_date.isoformat(),
        "board_type": "all",
        "timestamp": 1_777_000_000_000,
        "stock_count": 1,
        "stock_items": [
            {
                "thscode": "600519.SH",
                "ticker": "600519",
                "name": "贵州茅台",
                "concept_list": ["白酒"],
                "change": 3.2,
                "buy_value": 100.0,
                "sell_value": 40.0,
                "net_value": 60.0,
                "net_rate": 0.12,
                "org_net_value": 20.0,
                "hot_money_net_value": 40.0,
                "hot_rank": 1,
                "range_days": 1,
                "limit_reason": "机构买入",
            }
        ],
    }


def _auction_payload() -> dict:
    return {
        "timestamp": 1_777_000_000_100,
        "auction_phase": "final",
        "data_status": "ok",
        "item": [
            {
                "thscode": "600519.SH",
                "ticker": "600519",
                "name": "贵州茅台",
                "auction_price": 1810.0,
                "auction_pct": 1.2,
                "auction_volume": 1234.0,
                "auction_amount": 2_233_540.0,
                "auction_unmatched": 10.0,
                "auction_turnover_pct": 0.01,
                "auction_yesterday_ratio_pct": 80.0,
                "auction_volume_ratio": 1.1,
                "pre_close_price": 1800.0,
                "open_price": 1810.0,
                "last_price": 1810.0,
                "float_market_cap": 2.2e12,
            }
        ],
    }


def _valuation_payload() -> dict:
    return {
        "timestamp": 1_777_000_000_200,
        "item": [
            {
                "thscode": "600519.SH",
                "ticker": "600519",
                "name": "贵州茅台",
                "pe_ttm": 28.5,
                "pe_mrq": -3.1,
                "pb_mrq": 8.2,
                "ps_ttm": None,
                "pcf_ttm": 21.0,
            }
        ],
    }


def _mock_client(trade_date: date) -> HiThinkFinanceClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-api-key") == "test-key"
        path = request.url.path
        if path == LIMIT_UP_PATH:
            return httpx.Response(
                200,
                json=_envelope(
                    {
                        "timestamp": 1,
                        "item": [_limit_up_row()],
                        "pagination": {"page": 1, "size": 200, "total": 1, "pages": 1},
                    }
                ),
            )
        if path == LIMIT_DOWN_PATH:
            return httpx.Response(
                200,
                json=_envelope(
                    {
                        "timestamp": 1,
                        "item": [_limit_down_row()],
                        "pagination": {"page": 1, "size": 200, "total": 1, "pages": 1},
                    }
                ),
            )
        if path == LIMIT_BREAK_PATH:
            return httpx.Response(
                200,
                json=_envelope(
                    {
                        "timestamp": 1,
                        "item": [_limit_break_row()],
                        "pagination": {"page": 1, "size": 200, "total": 1, "pages": 1},
                    }
                ),
            )
        if path == DRAGON_TIGER_PATH:
            return httpx.Response(200, json=_envelope(_dragon_payload(trade_date)))
        if path == AUCTION_PATH:
            return httpx.Response(200, json=_envelope(_auction_payload()))
        if path == VALUATION_PATH:
            return httpx.Response(200, json=_envelope(_valuation_payload()))
        return httpx.Response(404, json={"code": 4040, "message": "missing"})

    return HiThinkFinanceClient(api_key="test-key", transport=httpx.MockTransport(handler), sleep=lambda _s: None)


def test_canonical_symbol_requires_exchange_suffix() -> None:
    assert canonical_symbol("600519.SH") == "600519.SH"
    with pytest.raises(HiThinkQualityError, match="invalid thscode"):
        canonical_symbol("600519")


def test_normalize_limit_pool_keeps_official_reason_and_unique_key() -> None:
    trade_date = date(2026, 8, 25)
    frame = normalize_limit_pool("limit_up", [_limit_up_row()], trade_date, timestamp_ms=9)
    row = frame.row(0, named=True)
    assert row["symbol"] == "600519.SH"
    assert row["limit_up_reason"] == "业绩预增"
    assert row["source"] == "hithink_fuyao"
    assert row["unit_version"] == "hithink_limit_pool_v1"


def test_normalize_auction_volume_stays_in_lots() -> None:
    trade_date = date(2026, 8, 25)
    frame = normalize_auction_snapshot(_auction_payload(), trade_date, stage="final")
    assert frame.row(0, named=True)["auction_volume"] == 1234.0
    assert frame.row(0, named=True)["stage"] == "final"


def test_normalize_valuation_preserves_nulls_and_negatives() -> None:
    frame = normalize_valuation_snapshot(_valuation_payload(), date(2026, 8, 25))
    row = frame.row(0, named=True)
    assert row["pe_mrq"] == -3.1
    assert row["ps_ttm"] is None


def test_normalize_dragon_tiger_keeps_richer_duplicate_symbol() -> None:
    payload = _dragon_payload(date(2026, 8, 25))
    payload["stock_items"].append(
        {
            "thscode": "600519.SH",
            "ticker": "600519",
            "name": "贵州茅台",
            "change": 3.2,
            "buy_value": 1.0,
            "sell_value": 1.0,
            "net_value": 0.0,
            "net_rate": 0.0,
            "org_net_value": None,
            "hot_money_net_value": None,
            "hot_rank": 9,
            "range_days": 10,
            "limit_reason": "重复行",
        }
    )
    frame, resolved = normalize_dragon_tiger(payload, date(2026, 8, 25))
    assert resolved == date(2026, 8, 25)
    assert frame.height == 1
    row = frame.row(0, named=True)
    assert row["symbol"] == "600519.SH"
    assert row["net_value"] == 60.0
    assert row["org_net_value"] == 20.0
    assert row["limit_reason"] == "机构买入"


def test_normalize_dragon_tiger_rejects_wrong_date() -> None:
    payload = _dragon_payload(date(2026, 8, 25))
    payload["trade_date"] = "2026-08-24"
    with pytest.raises(HiThinkQualityError, match="does not match"):
        normalize_dragon_tiger(payload, date(2026, 8, 25))


def test_sync_hithink_special_data_writes_independent_roots_and_lineage(tmp_path: Path) -> None:
    trade_date = date(2026, 8, 25)
    watchlist = tmp_path / "user_data" / "watchlist.parquet"
    watchlist.parent.mkdir(parents=True)
    pl.DataFrame({"symbol": ["600519.SH"], "added_at": ["2026-08-25"], "note": [None]}).write_parquet(watchlist)

    result = sync_hithink_special_data(trade_date, tmp_path, client=_mock_client(trade_date))

    assert result.rows_published == 6
    by_id = {item.dataset_id: item for item in result.datasets}
    assert by_id["hithink_limit_pool"].rows_published == 3
    assert by_id["hithink_dragon_tiger"].rows_published == 1
    assert by_id["hithink_auction_snapshot"].rows_published == 1
    assert by_id["hithink_valuation_snapshot"].rows_published == 1
    assert by_id["hithink_auction_snapshot"].extra["volume_unit"] == "lot"

    limit_path = tmp_path / "reference" / "hithink_limit_pool" / f"date={trade_date.isoformat()}" / "part.parquet"
    auction_path = tmp_path / "reference" / "hithink_auction_snapshot" / f"date={trade_date.isoformat()}" / "part.parquet"
    valuation_path = tmp_path / "reference" / "hithink_valuation_snapshot" / f"as_of={trade_date.isoformat()}" / "part.parquet"
    assert pl.read_parquet(limit_path).select(pl.struct(["trade_date", "pool_kind", "symbol"]).n_unique()).item() == 3
    assert pl.read_parquet(auction_path)["auction_volume"].to_list() == [1234.0]
    assert pl.read_parquet(valuation_path)["pe_mrq"].to_list() == [-3.1]

    lineage_root = tmp_path / "lineage"
    assert list((lineage_root / "hithink_limit_pool").glob("date=*/*.json"))
    assert list((lineage_root / "hithink_dragon_tiger").glob("date=*/*.json"))
    assert list((lineage_root / "hithink_auction_snapshot").glob("date=*/*.json"))
    assert list((lineage_root / "hithink_valuation_snapshot").glob("date=*/*.json"))
    auction_lineage = next((lineage_root / "hithink_auction_snapshot").glob("date=*/*.json"))
    extra = auction_lineage.read_text()
    assert '"volume_unit": "lot"' in extra

    resolved, queried = query_limit_pool(tmp_path, trade_date=trade_date)
    assert resolved == trade_date
    assert queried.height == 3
    _, auction = query_auction_snapshot(tmp_path, trade_date=trade_date)
    assert auction.height == 1
    _, dragon = query_dragon_tiger(tmp_path, trade_date=trade_date)
    assert dragon.height == 1
    _, valuation = query_valuation_snapshot(tmp_path, as_of=trade_date)
    assert valuation.height == 1


def test_sync_hithink_special_data_is_idempotent(tmp_path: Path) -> None:
    trade_date = date(2026, 8, 25)
    watchlist = tmp_path / "user_data" / "watchlist.parquet"
    watchlist.parent.mkdir(parents=True)
    pl.DataFrame({"symbol": ["600519.SH"]}).write_parquet(watchlist)
    first = sync_hithink_special_data(trade_date, tmp_path, client=_mock_client(trade_date))
    second = sync_hithink_special_data(trade_date, tmp_path, client=_mock_client(trade_date))
    assert first.rows_published == second.rows_published == 6
    stored = pl.read_parquet(
        tmp_path / "reference" / "hithink_limit_pool" / f"date={trade_date.isoformat()}" / "part.parquet"
    )
    assert stored.height == 3


def test_load_limit_pool_for_date_does_not_fall_back_to_latest(tmp_path: Path) -> None:
    yesterday = date(2026, 8, 25)
    today = date(2026, 8, 26)
    frame = normalize_limit_pool(
        "limit_up",
        [_limit_up_row(), _limit_up_row("000002.SZ")],
        yesterday,
        timestamp_ms=1,
    )
    path = tmp_path / "reference" / "hithink_limit_pool" / f"date={yesterday.isoformat()}" / "part.parquet"
    path.parent.mkdir(parents=True)
    frame.write_parquet(path)

    assert load_limit_pool_for_date(tmp_path, today) is None
    loaded = load_limit_pool_for_date(tmp_path, yesterday)
    assert loaded is not None
    assert loaded.height == 2
    kpi = summarize_limit_pool_kpi(loaded)
    assert kpi["limit_up"] == 2
    assert kpi["max_boards"] == 1
