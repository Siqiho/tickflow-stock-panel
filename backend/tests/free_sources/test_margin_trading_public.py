from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from app.services.free_sources.http_resilience import FetchResult, ResilientHttpClient
from app.services.free_sources.margin_trading_public import (
    MarginTradingQualityError,
    MarginTradingQueryError,
    fetch_margin_trading,
    map_offline_quantdb_margin_frame,
    query_margin_trading,
    query_margin_trading_result,
    sync_margin_trading,
)


def _upstream_row(
    symbol: str = "600519.SH",
    trade_date: str = "2026-08-04 00:00:00",
) -> dict:
    return {
        "MARKET_NAME": "沪市" if symbol.endswith(".SH") else "深市",
        "MARKET_CODE": "001" if symbol.endswith(".SH") else "002",
        "TRADE_DATE": trade_date,
        "SECURITY_CODE": symbol[:6],
        "SECUCODE": symbol,
        "SECURITY_NAME_ABBR": "贵州茅台" if symbol == "600519.SH" else "平安银行",
        "FIN_BALANCE": 17_419_738_098,
        "FIN_BUY_AMT": 458_522_930,
        "FIN_REPAY_AMT": 361_238_245,
        "FIN_NETBUY_AMT": 97_284_685,
        "LOAN_BALANCE": 138_508_097.2,
        "LOAN_SELL_VOL": 2_100,
        "LOAN_REPAY_VOL": 4_100,
        "LOAN_BALANCE_VOL": 104_270,
        "MARGIN_BALANCE": 17_558_246_195.2,
    }


def _payload(rows: list[dict]) -> dict:
    return {
        "success": True,
        "code": 0,
        "message": "ok",
        "result": {"pages": 1, "count": len(rows), "data": rows},
    }


def test_fetch_margin_trading_normalizes_units_and_primary_key(monkeypatch) -> None:
    client = ResilientHttpClient()

    def fake_get_json(url, **kwargs):
        assert kwargs["params"]["reportName"] == "RPT_RZRQ_STOCKS_DETAIL"
        assert kwargs["params"]["filter"] == '(SECUCODE="600519.SH")'
        return FetchResult(ok=True, status_code=200, data=_payload([_upstream_row()]))

    monkeypatch.setattr(client, "get_json", fake_get_json)

    frame = fetch_margin_trading("600519.SH", client=client, max_rows=50)

    assert frame.height == 1
    row = frame.row(0, named=True)
    assert row["symbol"] == "600519.SH"
    assert row["trade_date"] == date(2026, 8, 4)
    assert row["financing_balance"] == 17_419_738_098.0
    assert row["securities_lending_balance_volume"] == 104_270
    assert row["margin_balance"] == pytest.approx(
        row["financing_balance"] + row["securities_lending_balance"]
    )
    assert row["source"] == "eastmoney_rzrq"
    assert row["unit_version"] == "stock_margin_trading_v1"


def test_fetch_margin_trading_rejects_inconsistent_amount_semantics(monkeypatch) -> None:
    client = ResilientHttpClient()
    broken = _upstream_row()
    broken["MARGIN_BALANCE"] = 1.0
    monkeypatch.setattr(
        client,
        "get_json",
        lambda *args, **kwargs: FetchResult(ok=True, data=_payload([broken])),
    )

    with pytest.raises(MarginTradingQualityError, match="margin balance mismatch"):
        fetch_margin_trading("600519.SH", client=client)


def test_fetch_margin_trading_preserves_signed_lending_repayment_adjustment(monkeypatch) -> None:
    client = ResilientHttpClient()
    adjustment = _upstream_row("300502.SZ", "2026-06-11 00:00:00")
    adjustment.update(
        {
            "LOAN_SELL_VOL": 13_000,
            "LOAN_REPAY_VOL": -74_524,
            "LOAN_BALANCE_VOL": 300_284,
        }
    )
    monkeypatch.setattr(
        client,
        "get_json",
        lambda *args, **kwargs: FetchResult(ok=True, data=_payload([adjustment])),
    )

    frame = fetch_margin_trading("300502.SZ", client=client)

    assert frame.row(0, named=True)["securities_lending_repayment_volume"] == -74_524


def test_sync_margin_trading_is_idempotent_and_writes_lineage(tmp_path: Path, monkeypatch) -> None:
    from app.services.free_sources import margin_trading_public as module

    frame = module.normalize_margin_trading_rows([_upstream_row()])
    monkeypatch.setattr(module, "fetch_margin_trading", lambda *args, **kwargs: frame)

    first = sync_margin_trading(["600519.SH"], tmp_path, max_rows=50)
    second = sync_margin_trading(["600519.SH"], tmp_path, max_rows=50)

    assert first.rows_fetched == 1
    assert first.rows_published == 1
    assert second.rows_published == 1
    artifact = tmp_path / "f10" / "stock_margin_trading" / "part.parquet"
    stored = pl.read_parquet(artifact)
    assert stored.height == 1
    assert stored.select(pl.struct(["symbol", "trade_date"]).n_unique()).item() == 1
    lineage = list((tmp_path / "lineage" / "stock_margin_trading").glob("date=*/*.json"))
    assert len(lineage) == 2

    queried = query_margin_trading(tmp_path, symbol="600519.SH", limit=20)
    assert queried.height == 1
    assert queried["trade_date"].to_list() == [date(2026, 8, 4)]


def test_sync_failure_preserves_existing_artifact(tmp_path: Path, monkeypatch) -> None:
    from app.services.free_sources import margin_trading_public as module

    frame = module.normalize_margin_trading_rows([_upstream_row()])
    monkeypatch.setattr(module, "fetch_margin_trading", lambda *args, **kwargs: frame)
    sync_margin_trading(["600519.SH"], tmp_path)
    artifact = tmp_path / "f10" / "stock_margin_trading" / "part.parquet"
    before = hashlib.sha256(artifact.read_bytes()).hexdigest()

    def fail(*args, **kwargs):
        raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(module, "fetch_margin_trading", fail)
    with pytest.raises(RuntimeError, match="upstream unavailable"):
        sync_margin_trading(["000001.SZ"], tmp_path)

    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == before
    assert pl.read_parquet(artifact).height == 1


def _offline_row(
    symbol: str = "000001.SZ",
    trade_date: str = "2026-08-04",
    **overrides: object,
) -> dict:
    row = {
        "time": date.fromisoformat(trade_date),
        "Symbol": symbol,
        "finance_balance": 100.0,
        "slo_volume": 12.0,
        "finance_buy": 3.0,
        "slo_sell_amount": 2.5,
        "finance_repay": 7.0,
        "slo_repay": 4.0,
        "finance_net": 0.5,
        "slo_net": 1.0,
    }
    row.update(overrides)
    return row


def _write_offline(tmp_path: Path, symbol: str, rows: list[dict]) -> Path:
    dest = tmp_path / "2_base_sector" / "margin_trading" / f"{symbol}.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(dest)
    return dest


def test_query_margin_trading_local_default_ignores_offline_root(tmp_path: Path) -> None:
    from app.services.free_sources import margin_trading_public as module

    frame = module.normalize_margin_trading_rows([_upstream_row()])
    module.merge_margin_trading(tmp_path, frame)
    offline = _write_offline(tmp_path / "qd", "600519.SH", [_offline_row("600519.SH")])

    queried = query_margin_trading(
        tmp_path,
        symbol="600519.SH",
        limit=20,
        offline_root=tmp_path / "qd",
    )
    assert queried.height == 1
    assert queried["source"].to_list() == ["eastmoney_rzrq"]
    assert queried["margin_balance"].to_list() == [pytest.approx(17_558_246_195.2)]
    assert offline.is_file()


def test_map_offline_quantdb_keeps_nulls_and_does_not_use_write_validator(monkeypatch) -> None:
    from app.services.free_sources import margin_trading_public as module

    def boom(frame):
        raise AssertionError("_validate_frame must not run on offline rows")

    monkeypatch.setattr(module, "_validate_frame", boom)
    mapped = map_offline_quantdb_margin_frame(pl.DataFrame([_offline_row()]))
    row = mapped.row(0, named=True)
    assert row["financing_balance"] == 1_000_000.0
    assert row["financing_buy_amount"] == 30_000.0
    assert row["financing_net_buy_amount"] == 5_000.0
    assert row["financing_repayment_amount"] == 25_000.0
    assert row["securities_lending_sell_volume"] == 7
    assert row["securities_lending_balance_volume"] == 12
    assert row["securities_lending_repayment_volume"] == 4
    assert row["securities_lending_balance"] is None
    assert row["margin_balance"] is None
    assert row["source"] == "offline_quantdb"


def test_query_offline_quantdb_filters_dates_and_reports_file_as_of(tmp_path: Path) -> None:
    _write_offline(
        tmp_path,
        "000001.SZ",
        [
            _offline_row(trade_date="2026-08-03"),
            _offline_row(trade_date="2026-08-04"),
            _offline_row(trade_date="2026-08-05"),
        ],
    )
    result = query_margin_trading_result(
        tmp_path,
        symbol="000001.SZ",
        start_date=date(2026, 8, 4),
        end_date=date(2026, 8, 4),
        source="offline_quantdb",
        offline_root=tmp_path,
    )
    assert result.source == "offline_quantdb"
    assert result.status == "ok"
    assert result.as_of == "2026-08-05"
    assert result.frame.height == 1
    assert result.frame["trade_date"].to_list() == [date(2026, 8, 4)]
    assert result.missing_fields == ("securities_lending_balance", "margin_balance")


def test_query_offline_empty_window_is_not_missing_file(tmp_path: Path) -> None:
    _write_offline(tmp_path, "000001.SZ", [_offline_row(trade_date="2026-08-04")])
    result = query_margin_trading_result(
        tmp_path,
        symbol="000001.SZ",
        start_date=date(2010, 1, 1),
        end_date=date(2010, 1, 2),
        source="offline_quantdb",
        offline_root=tmp_path,
    )
    assert result.status == "empty"
    assert result.frame.height == 0
    assert result.as_of == "2026-08-04"


def test_query_offline_missing_file_and_columns_are_distinct(tmp_path: Path) -> None:
    with pytest.raises(MarginTradingQueryError, match="not found") as missing:
        query_margin_trading_result(
            tmp_path,
            symbol="000001.SZ",
            source="offline_quantdb",
            offline_root=tmp_path,
        )
    assert missing.value.code == "margin_trading_offline_not_found"

    dest = _write_offline(tmp_path, "000001.SZ", [_offline_row()])
    thin = pl.read_parquet(dest).drop("finance_balance")
    thin.write_parquet(dest)
    with pytest.raises(MarginTradingQueryError, match="missing columns") as schema:
        query_margin_trading_result(
            tmp_path,
            symbol="000001.SZ",
            source="offline_quantdb",
            offline_root=tmp_path,
        )
    assert schema.value.code == "margin_trading_offline_invalid_schema"


def test_query_offline_rejects_invalid_symbol_and_unconfigured() -> None:
    with pytest.raises(ValueError, match="invalid A-share symbol"):
        query_margin_trading_result(
            Path("/tmp"),
            symbol="../secret",
            source="offline_quantdb",
            offline_root=Path("/tmp"),
        )
    with pytest.raises(MarginTradingQueryError) as unconfigured:
        query_margin_trading_result(
            Path("/tmp"),
            symbol="000001.SZ",
            source="offline_quantdb",
            offline_root=None,
        )
    assert unconfigured.value.code == "margin_trading_offline_unconfigured"
