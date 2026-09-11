"""Regression tests for the watchlist/enriched public contract."""

from __future__ import annotations

from types import SimpleNamespace

import polars as pl
import pytest

from app.api import watchlist as watchlist_api
from app.services.ext_data import ExtConfig, ExtConfigStore, ExtField


class _FakeRepo:
    def __init__(
        self,
        enriched: pl.DataFrame,
        as_of: str | None,
        names: dict[str, str],
        data_dir=None,
    ):
        self._enriched = enriched
        self._as_of = as_of
        self._names = names
        if data_dir is not None:
            self.store = SimpleNamespace(data_dir=data_dir, db=SimpleNamespace())

    def get_enriched_latest(self):
        return self._enriched, self._as_of

    def get_instruments(self):
        return pl.DataFrame(
            [{"symbol": symbol, "name": name} for symbol, name in self._names.items()]
        )


def _request(repo: _FakeRepo):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(repo=repo)))


def _enriched(rows: list[tuple[str, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {"symbol": symbol, "name": "缓存名称", "close": close, "change_pct": 0.0}
            for symbol, close in rows
        ],
        schema_overrides={"close": pl.Float64, "change_pct": pl.Float64},
    )


def _write_ext_config(
    data_dir,
    config_id: str,
    mode: str,
    fields: list[tuple[str, str]],
) -> None:
    ExtConfigStore(data_dir).upsert(
        ExtConfig(
            id=config_id,
            label=config_id,
            mode=mode,
            fields=[ExtField(name, dtype) for name, dtype in fields],
        )
    )


def _write_snapshot(data_dir, config_id: str, rows: list[dict]) -> None:
    path = data_dir / "ext_data" / config_id / "part.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(path)


def test_partial_latest_partition_keeps_every_watchlist_symbol(monkeypatch):
    symbols = ["300502.SZ", "301526.SZ", "300204.SZ"]
    monkeypatch.setattr(
        watchlist_api.watchlist,
        "list_symbols",
        lambda: [{"symbol": symbol} for symbol in symbols],
    )
    repo = _FakeRepo(
        enriched=_enriched([("301526.SZ", 28.88)]),
        as_of="2026-08-03",
        names={
            "300502.SZ": "新易盛",
            "301526.SZ": "国际复材",
            "300204.SZ": "舒泰神",
        },
    )

    result = watchlist_api.watchlist_enriched(_request(repo), ext_columns=None)

    assert [row["symbol"] for row in result["rows"]] == symbols
    assert next(row for row in result["rows"] if row["symbol"] == "301526.SZ")["close"] == 28.88
    assert next(row for row in result["rows"] if row["symbol"] == "300502.SZ")["close"] is None
    assert next(row for row in result["rows"] if row["symbol"] == "300502.SZ")["name"] == "新易盛"


def test_empty_latest_partition_returns_pending_watchlist_rows(monkeypatch):
    symbols = ["300502.SZ", "300204.SZ"]
    monkeypatch.setattr(
        watchlist_api.watchlist,
        "list_symbols",
        lambda: [{"symbol": symbol} for symbol in symbols],
    )
    repo = _FakeRepo(
        enriched=pl.DataFrame(schema={"symbol": pl.Utf8}),
        as_of=None,
        names={"300502.SZ": "新易盛", "300204.SZ": "舒泰神"},
    )

    result = watchlist_api.watchlist_enriched(_request(repo), ext_columns=None)

    assert [row["symbol"] for row in result["rows"]] == symbols
    assert all(row.get("close") is None for row in result["rows"])
    assert result["as_of"] is None


def test_latest_quote_snapshot_overlays_realtime_watchlist_fields(monkeypatch, tmp_path):
    symbols = ["300502.SZ", "301526.SZ"]
    monkeypatch.setattr(
        watchlist_api.watchlist,
        "list_symbols",
        lambda: [{"symbol": symbol} for symbol in symbols],
    )
    repo = _FakeRepo(
        enriched=_enriched([("301526.SZ", 29.73)]),
        as_of="2026-08-03",
        names={"300502.SZ": "新易盛", "301526.SZ": "国际复材"},
        data_dir=tmp_path,
    )
    snapshot = tmp_path / "quote_snapshot" / "asset_type=stock" / "date=2026-08-04" / "part.parquet"
    snapshot.parent.mkdir(parents=True)
    pl.DataFrame(
        [
            {
                "symbol": "300502.SZ",
                "date": "2026-08-04",
                "close": 440.88,
                "change_pct": 11.875761,
                "amount": 20_331_840_000.0,
                "name": "新易盛",
                "source": "tencent",
                "fetched_at": "2026-08-04T11:39:42+08:00",
            },
        ]
    ).write_parquet(snapshot)

    result = watchlist_api.watchlist_enriched(_request(repo), ext_columns=None)

    row = next(item for item in result["rows"] if item["symbol"] == "300502.SZ")
    assert row["close"] is None
    assert row["rt_price"] == 440.88
    assert row["rt_pct"] == pytest.approx(0.11875761)
    assert row["rt_amount"] == 20_331_840_000.0
    assert row["rt_source"] == "tencent"
    assert row["rt_fetched_at"] == "2026-08-04T11:39:42+08:00"
    assert result["realtime_count"] == 1
    assert result["realtime_as_of"] == "2026-08-04T11:39:42+08:00"


def test_quote_snapshot_older_than_enriched_is_not_used_as_realtime(monkeypatch, tmp_path):
    monkeypatch.setattr(
        watchlist_api.watchlist,
        "list_symbols",
        lambda: [{"symbol": "300502.SZ"}],
    )
    repo = _FakeRepo(
        enriched=_enriched([("300502.SZ", 450.0)]),
        as_of="2026-08-04",
        names={"300502.SZ": "新易盛"},
        data_dir=tmp_path,
    )
    snapshot = tmp_path / "quote_snapshot" / "asset_type=stock" / "date=2026-08-03" / "part.parquet"
    snapshot.parent.mkdir(parents=True)
    pl.DataFrame(
        [
            {
                "symbol": "300502.SZ",
                "date": "2026-08-03",
                "close": 394.08,
                "change_pct": -1.0,
                "fetched_at": "2026-08-03T15:00:00+08:00",
            },
        ]
    ).write_parquet(snapshot)

    result = watchlist_api.watchlist_enriched(_request(repo), ext_columns=None)

    assert result["rows"][0]["close"] == 450.0
    assert result["rows"][0].get("rt_price") is None
    assert result["realtime_count"] == 0
    assert result["realtime_as_of"] is None


def test_industry_fund_flow_columns_resolve_through_stock_membership(monkeypatch, tmp_path):
    symbols = ["300502.SZ", "600756.SH"]
    monkeypatch.setattr(
        watchlist_api.watchlist,
        "list_symbols",
        lambda: [{"symbol": symbol} for symbol in symbols],
    )
    repo = _FakeRepo(
        enriched=_enriched([(symbol, 10.0) for symbol in symbols]),
        as_of="2026-08-05",
        names={"300502.SZ": "新易盛", "600756.SH": "浪潮软件"},
        data_dir=tmp_path,
    )
    _write_ext_config(
        tmp_path, "ext_hy_ths", "snapshot", [("symbol", "string"), ("所属同花顺行业", "string")]
    )
    _write_ext_config(
        tmp_path,
        "ext_fund_flow_bk",
        "snapshot",
        [("name", "string"), ("main_net", "float"), ("rank", "int")],
    )
    _write_snapshot(
        tmp_path,
        "ext_hy_ths",
        [
            {"symbol": "300502.SZ", "所属同花顺行业": "通信-通信设备-通信网络设备及器件"},
            {"symbol": "600756.SH", "所属同花顺行业": "计算机-IT服务-IT服务Ⅲ"},
        ],
    )
    _write_snapshot(
        tmp_path,
        "ext_fund_flow_bk",
        [
            {"name": "通信设备", "main_net": 8_000_000.0, "rank": 3},
            {"name": "IT服务Ⅱ", "main_net": -2_000_000.0, "rank": 9},
        ],
    )

    result = watchlist_api.watchlist_enriched(
        _request(repo),
        ext_columns="ext_fund_flow_bk.name,ext_fund_flow_bk.main_net",
    )

    by_symbol = {row["symbol"]: row for row in result["rows"]}
    assert by_symbol["300502.SZ"]["ext_fund_flow_bk__name"] == "通信设备"
    assert by_symbol["300502.SZ"]["ext_fund_flow_bk__main_net"] == 8_000_000.0
    assert by_symbol["600756.SH"]["ext_fund_flow_bk__name"] == "IT服务Ⅱ"
    assert by_symbol["600756.SH"]["ext_fund_flow_bk__main_net"] == -2_000_000.0


def test_concept_fund_flow_uses_highest_ranked_membership(monkeypatch, tmp_path):
    monkeypatch.setattr(
        watchlist_api.watchlist,
        "list_symbols",
        lambda: [{"symbol": "300866.SZ"}],
    )
    repo = _FakeRepo(
        enriched=_enriched([("300866.SZ", 100.0)]),
        as_of="2026-08-05",
        names={"300866.SZ": "安克创新"},
        data_dir=tmp_path,
    )
    _write_ext_config(
        tmp_path, "ext_gn_ths", "snapshot", [("symbol", "string"), ("所属概念", "string")]
    )
    _write_ext_config(
        tmp_path,
        "ext_fund_flow_concept",
        "snapshot",
        [("name", "string"), ("main_net", "float"), ("rank", "int")],
    )
    _write_snapshot(
        tmp_path,
        "ext_gn_ths",
        [
            {"symbol": "300866.SZ", "所属概念": "机器人概念;人工智能;消费电子概念"},
        ],
    )
    _write_snapshot(
        tmp_path,
        "ext_fund_flow_concept",
        [
            {"name": "机器人概念", "main_net": 2_000_000.0, "rank": 30},
            {"name": "人工智能", "main_net": 9_000_000.0, "rank": 12},
            {"name": "消费电子概念", "main_net": 5_000_000.0, "rank": 89},
        ],
    )

    result = watchlist_api.watchlist_enriched(
        _request(repo),
        ext_columns="ext_fund_flow_concept.name,ext_fund_flow_concept.main_net",
    )

    row = result["rows"][0]
    assert row["ext_fund_flow_concept__name"] == "人工智能"
    assert row["ext_fund_flow_concept__main_net"] == 9_000_000.0


def test_sparse_stock_timeseries_uses_latest_row_per_symbol(monkeypatch, tmp_path):
    symbols = ["300502.SZ", "301526.SZ"]
    monkeypatch.setattr(
        watchlist_api.watchlist,
        "list_symbols",
        lambda: [{"symbol": symbol} for symbol in symbols],
    )
    repo = _FakeRepo(
        enriched=_enriched([(symbol, 10.0) for symbol in symbols]),
        as_of="2026-08-05",
        names={"300502.SZ": "新易盛", "301526.SZ": "国际复材"},
        data_dir=tmp_path,
    )
    _write_ext_config(
        tmp_path,
        "ext_fund_flow_stock",
        "timeseries",
        [("symbol", "string"), ("date", "string"), ("main_net", "float")],
    )
    for snapshot_date, rows in {
        "2026-08-04": [
            {"symbol": "300502.SZ", "date": "2026-08-04", "main_net": 1_000_000.0},
            {"symbol": "301526.SZ", "date": "2026-08-04", "main_net": 2_000_000.0},
        ],
        "2026-08-05": [
            {"symbol": "300502.SZ", "date": "2026-08-05", "main_net": 3_000_000.0},
        ],
    }.items():
        path = (
            tmp_path
            / "ext_data"
            / "ext_fund_flow_stock"
            / "timeseries"
            / f"date={snapshot_date}"
            / "part.parquet"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        pl.DataFrame(rows).write_parquet(path)

    result = watchlist_api.watchlist_enriched(
        _request(repo),
        ext_columns="ext_fund_flow_stock.main_net",
    )

    by_symbol = {row["symbol"]: row for row in result["rows"]}
    assert by_symbol["300502.SZ"]["ext_fund_flow_stock__main_net"] == 3_000_000.0
    assert by_symbol["301526.SZ"]["ext_fund_flow_stock__main_net"] == 2_000_000.0


def test_local_financial_metrics_are_joined_with_watchlist_units(monkeypatch, tmp_path):
    monkeypatch.setattr(
        watchlist_api.watchlist,
        "list_symbols",
        lambda: [{"symbol": "300502.SZ"}],
    )
    repo = _FakeRepo(
        enriched=_enriched([("300502.SZ", 400.0)]),
        as_of="2026-08-05",
        names={"300502.SZ": "新易盛"},
        data_dir=tmp_path,
    )
    metrics_path = tmp_path / "financials" / "metrics" / "part.parquet"
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        [
            {
                "symbol": "300502.SZ",
                "period_end": "2025-12-31",
                "basic_eps": 1.5,
                "bps": 10.0,
                "roe": 20.0,
                "gross_margin": 30.0,
                "net_margin": 15.0,
                "total_revenue_yoy": 25.0,
                "parent_net_profit_yoy": 40.0,
                "asset_liab_ratio": 35.0,
            },
            {
                "symbol": "300502.SZ",
                "period_end": "2026-03-31",
                "basic_eps": 2.8,
                "bps": 20.5,
                "roe": 31.2,
                "gross_margin": 47.0,
                "net_margin": 33.3,
                "total_revenue_yoy": 105.8,
                "parent_net_profit_yoy": 76.8,
                "asset_liab_ratio": 31.0,
            },
        ]
    ).write_parquet(metrics_path)

    result = watchlist_api.watchlist_enriched(_request(repo), ext_columns=None)

    row = result["rows"][0]
    assert row["eps"] == 2.8
    assert row["bps"] == 20.5
    assert row["roe"] == pytest.approx(0.312)
    assert row["gross_margin"] == pytest.approx(0.47)
    assert row["net_margin"] == pytest.approx(0.333)
    assert row["revenue_yoy"] == pytest.approx(1.058)
    assert row["net_income_yoy"] == pytest.approx(0.768)
    assert row["debt_ratio"] == pytest.approx(0.31)
