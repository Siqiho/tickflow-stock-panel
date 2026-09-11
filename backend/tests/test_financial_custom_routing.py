"""Custom financial_provider must not silently call TickFlow."""
from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl

from app.services import financial_sync
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet


class _FinProvider:
    def __init__(self):
        self.calls: list[tuple] = []

    def get_financials(self, table, symbols, latest_only=True):
        self.calls.append((table, list(symbols), latest_only))
        return pl.DataFrame({
            "symbol": symbols[:1] or ["000001.SZ"],
            "end_date": ["2026-03-31"],
            "revenue": [1.0],
        })


def _route_financial(monkeypatch, provider, name: str = "fuyao", declared: bool = True):
    monkeypatch.setattr(financial_sync, "_use_public_financials", lambda: False)
    from app.services import preferences
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: name)
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda n=None: False)
    from app.data_providers import custom
    monkeypatch.setattr(
        custom,
        "provider_has_dataset",
        lambda n, dataset: n == name and declared and dataset == "financial",
    )
    monkeypatch.setattr(custom, "get_provider", lambda n: provider)


def test_custom_financial_sync_writes_provider_rows(monkeypatch, tmp_path):
    provider = _FinProvider()
    _route_financial(monkeypatch, provider)
    tf = MagicMock()
    monkeypatch.setattr("app.tickflow.client.get_client", lambda: tf)

    rows = financial_sync._sync_table(
        "income",
        ["000001.SZ"],
        tmp_path,
        CapabilitySet({Cap.FINANCIAL: CapabilityLimits()}),
        latest_only=True,
    )
    assert rows == 1
    assert provider.calls == [("income", ["000001.SZ"], True)]
    tf.financials.income.assert_not_called()
    stored = pl.read_parquet(tmp_path / "financials" / "income" / "part.parquet")
    assert stored["symbol"].to_list() == ["000001.SZ"]


def test_custom_financial_without_dataset_does_not_use_tickflow(monkeypatch, tmp_path):
    provider = _FinProvider()
    _route_financial(monkeypatch, provider, declared=False)
    tf = MagicMock()
    monkeypatch.setattr("app.tickflow.client.get_client", lambda: tf)

    rows = financial_sync._sync_table(
        "income",
        ["000001.SZ"],
        tmp_path,
        CapabilitySet({Cap.FINANCIAL: CapabilityLimits()}),
        latest_only=True,
    )
    assert rows == 0
    assert provider.calls == []
    tf.financials.income.assert_not_called()
    assert not (tmp_path / "financials" / "income" / "part.parquet").exists()


def test_tickflow_financial_still_uses_client_when_selected(monkeypatch, tmp_path):
    monkeypatch.setattr(financial_sync, "_use_public_financials", lambda: False)
    from app.services import preferences
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda n=None: False)

    tf = MagicMock()
    tf.financials.income.return_value = {
        "000001.SZ": [{"revenue": 2.0}],
    }
    monkeypatch.setattr("app.tickflow.client.get_client", lambda: tf)

    rows = financial_sync._sync_table(
        "income",
        ["000001.SZ"],
        tmp_path,
        CapabilitySet({Cap.FINANCIAL: CapabilityLimits()}),
        latest_only=True,
    )
    assert rows == 1
    tf.financials.income.assert_called_once()
