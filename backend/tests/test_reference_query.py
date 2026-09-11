from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import reference_data
from app.services.reference_query import query_reference_dataset
from app.services.user_console_data import USER_CONSOLE_DATA_VIEWS


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    app.include_router(reference_data.router)
    return TestClient(app)


def _write_partitioned(tmp_path: Path, dataset: str, rows: list[dict], day: str) -> None:
    target = tmp_path / "reference" / dataset / f"date={day}" / "part.parquet"
    target.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(target)


def test_valuation_query_requires_symbol_or_date_window(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="symbol 或日期窗口"):
        query_reference_dataset(tmp_path, "valuation_daily")


def test_valuation_and_limit_queries_read_local_partitions(tmp_path: Path) -> None:
    _write_partitioned(
        tmp_path,
        "valuation_daily",
        [
            {
                "symbol": "600756.SH",
                "trade_date": date(2026, 8, 12),
                "close": 16.37,
                "total_mv": 5723.0,
                "shares_pit_safe": True,
                "unit_version": "valuation_daily_v2",
            }
        ],
        "2026-08-12",
    )
    _write_partitioned(
        tmp_path,
        "limit_up_events",
        [
            {
                "symbol": "600105.SH",
                "trade_date": date(2026, 8, 12),
                "state": "limit_up_final",
                "board": "SH_MAIN",
                "limit_pct": 0.1,
                "unit_version": "limit_up_events_v2",
            }
        ],
        "2026-08-12",
    )

    valuation = query_reference_dataset(tmp_path, "valuation_daily", symbol="600756.SH")
    assert valuation["count"] == 1
    assert valuation["data"][0]["total_mv"] == 5723.0
    assert valuation["data"][0]["trade_date"] == "2026-08-12"

    events = query_reference_dataset(tmp_path, "limit_up_events", start_date="2026-08-12")
    assert events["count"] == 1
    assert events["data"][0]["state"] == "limit_up_final"


def test_membership_and_corporate_actions_filter_local_files(tmp_path: Path) -> None:
    members = tmp_path / "reference" / "index_membership_history" / "members.parquet"
    members.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "index_code": "000300",
                "effective_from": date(2026, 7, 17),
                "pool_id": "CSI300",
                "membership_basis": "snapshot_seed",
                "unit_version": "index_membership_history_v2",
                "as_of": date(2026, 7, 17),
            },
            {
                "symbol": "600519.SH",
                "index_code": "000905",
                "effective_from": date(2026, 7, 17),
                "pool_id": "CSI500",
                "membership_basis": "snapshot_seed",
                "unit_version": "index_membership_history_v2",
                "as_of": date(2026, 7, 17),
            },
        ]
    ).write_parquet(members)

    actions = tmp_path / "reference" / "corporate_actions" / "actions.parquet"
    actions.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        [
            {
                "symbol": "600519.SH",
                "action_id": "cash-1",
                "action_type": "dividend_cash",
                "ex_date": date(2026, 6, 20),
                "announce_date": date(2026, 4, 1),
                "cash_per_share": 2.5,
                "source": "eastmoney_sharebonus_det",
                "as_of": date(2026, 8, 13),
                "is_verification_signal": False,
                "unit_version": "corporate_actions_v2",
            }
        ]
    ).write_parquet(actions)

    membership = query_reference_dataset(tmp_path, "index_membership_history", pool_id="CSI300")
    assert membership["count"] == 1
    assert membership["data"][0]["symbol"] == "000001.SZ"

    corp = query_reference_dataset(tmp_path, "corporate_actions", symbol="600519.SH")
    assert corp["count"] == 1
    assert corp["data"][0]["cash_per_share"] == 2.5


def test_reference_api_is_local_only_and_rejects_unbounded_valuation(tmp_path: Path) -> None:
    client = _client(tmp_path)
    missing = client.get("/api/reference/valuation-daily")
    assert missing.status_code == 400

    _write_partitioned(
        tmp_path,
        "valuation_daily",
        [
            {
                "symbol": "600756.SH",
                "trade_date": date(2026, 8, 12),
                "close": 16.37,
                "shares_pit_safe": True,
                "unit_version": "valuation_daily_v2",
            }
        ],
        "2026-08-12",
    )
    response = client.get("/api/reference/valuation-daily?symbol=600756.SH&limit=10")
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "local"
    assert body["dataset_id"] == "valuation_daily"
    assert body["count"] == 1


def test_hermes_catalog_includes_new_reference_views() -> None:
    view_ids = {view.id for view in USER_CONSOLE_DATA_VIEWS}
    assert {
        "valuation_daily",
        "limit_up_events",
        "index_membership_history",
        "corporate_actions",
    }.issubset(view_ids)
    by_id = {view.id: view for view in USER_CONSOLE_DATA_VIEWS}
    assert by_id["valuation_daily"].path == "/api/reference/valuation-daily"
    assert by_id["limit_up_events"].path == "/api/reference/limit-up-events"
    assert by_id["index_membership_history"].path == "/api/reference/index-membership"
    assert by_id["corporate_actions"].path == "/api/reference/corporate-actions"
