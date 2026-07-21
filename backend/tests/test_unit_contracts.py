from __future__ import annotations

import polars as pl
import pytest
from pydantic import ValidationError

from app.data_providers.base import ProviderDatasetManifest
from app.data_providers.normalizer import normalize_daily
from app.data_providers.registry import get_provider_manifests, list_provider_manifests
from app.data_providers.tickflow_provider import TickFlowProvider
from app.data_providers.unit_contracts import (
    UnitContractError,
    canonicalize_amount,
    canonicalize_ratio,
    canonicalize_volume,
    ensure_publishable_units,
)


def _daily_manifest(**overrides) -> ProviderDatasetManifest:
    data = {
        "provider": "fixture",
        "dataset_id": "stock_daily",
        "asset_types": ("stock",),
        "operations": ("daily",),
        "source_units": {
            "volume": "share",
            "amount": "TEN_THOUSAND_CNY",
            "ratio": "fraction",
        },
        "canonical_units": {
            "volume": "lot",
            "amount": "CNY",
            "ratio": "percentage_point",
        },
    }
    data.update(overrides)
    return ProviderDatasetManifest(**data)


def test_canonicalizers_convert_cn_volume_amount_and_fraction_ratio():
    assert canonicalize_volume(250.0, "share", market="CN") == 2.5
    assert canonicalize_volume(None, "share", market="CN") is None
    assert canonicalize_amount(2.5, "TEN_THOUSAND_CNY", market="CN") == 25_000.0
    assert canonicalize_ratio(0.01, "fraction", target_scale="percentage_point") == 1.0


def test_publishable_units_fail_closed_for_unknown_required_unit():
    manifest = _daily_manifest(source_units={"volume": "unknown", "amount": "unknown"})

    with pytest.raises(UnitContractError, match="volume"):
        ensure_publishable_units(manifest, required_fields={"volume", "amount"}, market="CN")


def test_publishable_units_reject_cn_canonical_contract_for_non_cn_market():
    with pytest.raises(UnitContractError, match="non-CN"):
        ensure_publishable_units(
            _daily_manifest(), required_fields={"volume", "amount"}, market="US"
        )


def test_manifest_validates_required_values_unique_operations_and_string_unit_maps():
    with pytest.raises(ValidationError, match="provider"):
        ProviderDatasetManifest(
            provider="",
            dataset_id="stock_daily",
            asset_types=("stock",),
            operations=("daily",),
        )
    with pytest.raises(ValidationError, match="unique"):
        ProviderDatasetManifest(
            provider="fixture",
            dataset_id="stock_daily",
            asset_types=("stock",),
            operations=("daily", "daily"),
        )
    with pytest.raises(ValidationError, match="source_units"):
        ProviderDatasetManifest(
            provider="fixture",
            dataset_id="stock_daily",
            asset_types=("stock",),
            operations=("daily",),
            source_units={"volume": 100},
        )


def test_normalize_daily_converts_declared_units_only_for_publication():
    data = pl.DataFrame(
        {
            "symbol": ["000001.SZ"],
            "date": ["2026-07-21"],
            "open": [10.0],
            "high": [11.0],
            "low": [9.0],
            "close": [10.5],
            "volume": [250.0],
            "amount": [2.5],
            "change_pct": [0.01],
            "turnover_rate": [0.02],
        }
    )

    staged = normalize_daily(data, source="fixture")
    published = normalize_daily(
        data, source="fixture", manifest=_daily_manifest(), for_publication=True
    )

    assert staged["volume"].item() == 250.0
    assert staged["amount"].item() == 2.5
    assert published["volume"].item() == 2.5
    assert published["amount"].item() == 25_000.0
    assert published["change_pct"].item() == 1.0
    assert published["turnover_rate"].item() == 2.0


def test_tickflow_daily_rejects_unknown_manifest_units_before_provider_client(monkeypatch):
    def no_client():
        raise AssertionError("provider client must not be reached")

    monkeypatch.setattr("app.data_providers.tickflow_provider.get_client", no_client)

    with pytest.raises(UnitContractError, match="unknown"):
        TickFlowProvider().get_daily(["000001.SZ"], None, None, "stock")


def test_builtin_manifests_are_local_ordered_and_cover_required_datasets(monkeypatch):
    def no_custom_load():
        raise AssertionError("manifest lookup must not load custom YAML")

    monkeypatch.setattr("app.data_providers.custom.load_all", no_custom_load)
    manifests = list_provider_manifests()

    assert [(m.provider, m.dataset_id, m.operations) for m in manifests] == sorted(
        (m.provider, m.dataset_id, m.operations) for m in manifests
    )
    assert get_provider_manifests("missing-custom") == []

    public = get_provider_manifests("public")
    tickflow = get_provider_manifests("tickflow")
    public_ids = {manifest.dataset_id for manifest in public}
    tickflow_ids = {manifest.dataset_id for manifest in tickflow}
    financial_ids = {
        "financial_metrics",
        "financial_income",
        "financial_balance_sheet",
        "financial_cash_flow",
        "financial_shares",
    }
    assert {
        "quote_snapshot",
        "sealed_l1",
        "stock_adj_factor",
        "pools",
        *financial_ids,
    } <= public_ids
    assert "depth5" not in public_ids
    assert {
        "stock_instruments",
        "etf_instruments",
        "index_instruments",
        "stock_daily",
        "etf_daily",
        "index_daily",
        "stock_minute",
        "stock_adj_factor",
        "quote_snapshot",
        "depth5",
        *financial_ids,
    } <= tickflow_ids


def test_book_and_financial_manifests_keep_independent_truthful_metadata():
    manifests = list_provider_manifests()
    by_key = {(m.provider, m.dataset_id): m for m in manifests}
    sealed = by_key[("public", "sealed_l1")]
    depth = by_key[("tickflow", "depth5")]

    assert sealed.source_units["book_volume"] == "unknown"
    assert depth.source_units["book_volume"] == "unknown"
    assert sealed is not depth
    tickflow_daily = by_key[("tickflow", "stock_daily")]
    assert tickflow_daily.source_units["ratio"] == "fraction"
    assert tickflow_daily.canonical_units["ratio"] == "percentage_point"
    assert tickflow_daily.verified_at is None
    for provider in ("public", "tickflow"):
        for dataset_id in (
            "financial_metrics",
            "financial_income",
            "financial_balance_sheet",
            "financial_cash_flow",
            "financial_shares",
        ):
            manifest = by_key[(provider, dataset_id)]
            assert {"monetary_currency", "monetary_scale"} <= manifest.source_units.keys()
            assert {"monetary_currency", "monetary_scale"} <= manifest.canonical_units.keys()
