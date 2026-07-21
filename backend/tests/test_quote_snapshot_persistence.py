from __future__ import annotations

from datetime import date

import polars as pl

from app.services.quote_service import QuoteService
from app.tickflow.repository import DataStore, KlineRepository


def _quote_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "symbol": ["000001.SZ"],
            "date": [date(2026, 7, 20)],
            "open": [9.5],
            "high": [10.2],
            "low": [9.4],
            "close": [10.0],
            "volume": [1_256_397.0],
            "amount": [1_372_730_000.0],
            "source": ["tencent"],
            "source_volume_unit": ["lot"],
            "source_amount_unit": ["ten_thousand_cny"],
            "unit_version": ["cn_quote_v1"],
        }
    )


def test_quote_snapshot_is_atomic_and_does_not_create_daily_partition(tmp_path):
    repo = KlineRepository(DataStore(tmp_path))

    repo.write_quote_snapshot_asset(
        "stock",
        _quote_frame(),
        metadata={"fetched_at": "2026-07-20T14:30:00+08:00", "scope": "full_market"},
    )

    target = tmp_path / "quote_snapshot" / "asset_type=stock" / "date=2026-07-20" / "part.parquet"
    assert target.exists()
    saved = pl.read_parquet(target)
    assert saved["amount"].item() == 1_372_730_000
    assert saved["fetched_at"].item() == "2026-07-20T14:30:00+08:00"
    assert not list((tmp_path / "kline_daily").rglob("*.parquet"))
    assert not list(tmp_path.rglob("*.tmp-*"))
    lineage = list((tmp_path / "lineage" / "quote_snapshot" / "date=2026-07-20").glob("*.json"))
    assert len(lineage) == 1


def test_public_full_market_refresh_never_calls_canonical_daily_writers(tmp_path, monkeypatch):
    repo = KlineRepository(DataStore(tmp_path))
    service = QuoteService()
    service.set_repo(repo)
    records = [
        {
            "symbol": "000001.SZ",
            "name": "测试",
            "last_price": 10.0,
            "prev_close": 9.0,
            "open": 9.5,
            "high": 10.2,
            "low": 9.4,
            "volume": 1_256_397.0,
            "amount": 1_372_730_000.0,
            "change_pct": 11.11,
            "source": "tencent",
            "source_volume_unit": "lot",
            "source_amount_unit": "ten_thousand_cny",
            "unit_version": "cn_quote_v1",
        }
    ]

    monkeypatch.setattr("app.services.preferences.get_realtime_data_provider", lambda: "public")
    monkeypatch.setattr("app.services.preferences.get_realtime_pull_index", lambda: False)
    monkeypatch.setattr("app.services.preferences.get_realtime_pull_etf", lambda: False)
    monkeypatch.setattr("app.services.preferences.get_realtime_pull_stock", lambda: True)
    monkeypatch.setattr(repo, "get_index_symbol_set", lambda: set())
    monkeypatch.setattr(repo, "get_etf_instruments", lambda: pl.DataFrame())
    monkeypatch.setattr(service, "_fetch_public_full_market_records", lambda **kwargs: records)
    monkeypatch.setattr(service, "_evaluate_monitors", lambda *args, **kwargs: None)

    enriched_calls: list[dict] = []
    monkeypatch.setattr(
        service,
        "_flush_live_enriched",
        lambda *args, **kwargs: enriched_calls.append(kwargs),
    )
    monkeypatch.setattr(
        repo,
        "flush_live_daily",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("canonical stock writer called")),
    )
    monkeypatch.setattr(
        repo,
        "flush_live_daily_asset",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("canonical asset writer called")),
    )

    service._fetch_full_market_quotes()

    snapshots = list((tmp_path / "quote_snapshot").rglob("*.parquet"))
    assert len(snapshots) == 1
    assert not list((tmp_path / "kline_daily").rglob("*.parquet"))
    assert enriched_calls == [{"asset_type": "stock", "persist": False}]


def test_publish_live_enriched_updates_cache_without_writing_enriched_partition(tmp_path):
    repo = KlineRepository(DataStore(tmp_path))
    live = _quote_frame()

    repo.publish_live_enriched_asset("stock", live)

    cached, cached_date = repo.get_enriched_latest()
    assert cached_date == date(2026, 7, 20)
    assert cached["symbol"].to_list() == ["000001.SZ"]
    assert not list((tmp_path / "kline_daily_enriched").rglob("*.parquet"))
