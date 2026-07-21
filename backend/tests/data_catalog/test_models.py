from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic import ValidationError

from app.data_catalog.definitions import (
    DATASET_DEFINITIONS,
    get_dataset_definition,
    validate_dataset_definitions,
)
from app.data_catalog.models import (
    DatasetAvailability,
    DatasetState,
    MarketCoverage,
    StorageBreakdown,
    StorageCategory,
)

REQUIRED_DATASET_IDS = {
    "stock_instruments",
    "stock_daily",
    "stock_enriched",
    "stock_minute",
    "stock_adj_factor",
    "etf_instruments",
    "etf_daily",
    "etf_enriched",
    "etf_minute",
    "etf_adj_factor",
    "index_instruments",
    "index_daily",
    "index_enriched",
    "quote_snapshot",
    "sealed_l1",
    "depth5",
    "pools",
    "ext_data",
    "financial_metrics",
    "financial_income",
    "financial_balance_sheet",
    "financial_cash_flow",
    "financial_shares",
}


def test_availability_flags_are_independent() -> None:
    availability = DatasetAvailability(local_materialized=True)

    assert availability.local_materialized is True
    assert availability.provider_supported is False
    assert availability.entitled is False
    assert availability.serving_ready is False


@pytest.mark.parametrize(
    ("factory", "kwargs"),
    [
        (DatasetState, {"dataset_id": "stock_daily", "schema_version": "1", "unit_version": "v1", "updated_at": "2026-07-21", "row_count": -1}),
        (MarketCoverage, {"market": "SH", "ratio": 1.01}),
        (StorageBreakdown, {"managed_data_bytes": 1, "operational_bytes": 1, "total_bytes": 1}),
        (
            StorageBreakdown,
            {
                "total_bytes": 1,
                "categories": [
                    StorageCategory(key="stocks", title="Stocks", kind="managed", bytes=2)
                ],
            },
        ),
    ],
)
def test_models_reject_invalid_counts_ratios_and_storage_totals(factory, kwargs) -> None:
    with pytest.raises(ValidationError):
        factory(**kwargs)


def test_registry_has_exactly_the_required_unique_dataset_ids() -> None:
    ids = [definition.descriptor.dataset_id for definition in DATASET_DEFINITIONS]

    assert set(ids) == REQUIRED_DATASET_IDS
    assert len(ids) == len(set(ids))
    validate_dataset_definitions(DATASET_DEFINITIONS)


def test_registry_has_five_separate_financial_tables_including_shares() -> None:
    financial_ids = {
        definition.descriptor.dataset_id
        for definition in DATASET_DEFINITIONS
        if definition.descriptor.dataset_id.startswith("financial_")
    }

    assert financial_ids == {
        "financial_metrics",
        "financial_income",
        "financial_balance_sheet",
        "financial_cash_flow",
        "financial_shares",
    }
    shares = get_dataset_definition("financial_shares").descriptor
    assert {field.name for field in shares.fields} >= {
        "symbol",
        "period_end",
        "total_shares",
        "float_shares",
    }


def test_limit_prices_are_nullable_cny_prices_without_percentage_scale() -> None:
    instruments = get_dataset_definition("stock_instruments").descriptor
    fields = {field.name: field for field in instruments.fields}

    for name in ("limit_up", "limit_down"):
        assert fields[name].nullable is True
        assert fields[name].unit == "CNY"
        assert "price" in fields[name].semantic.lower()
        assert fields[name].scale is None


def test_enriched_descriptions_identify_the_correct_asset_class() -> None:
    semantics = {
        dataset_id: next(
            field.semantic
            for field in get_dataset_definition(dataset_id).descriptor.fields
            if field.name == "ma5"
        )
        for dataset_id in ("stock_enriched", "etf_enriched", "index_enriched")
    }

    assert "stock" in semantics["stock_enriched"].lower()
    assert "etf" in semantics["etf_enriched"].lower()
    assert "index" in semantics["index_enriched"].lower()
    assert len(set(semantics.values())) == 3


def test_registry_validation_rejects_overlapping_exclusive_roots() -> None:
    stock_daily = get_dataset_definition("stock_daily")
    duplicate_root = replace(stock_daily, descriptor=stock_daily.descriptor.model_copy(update={"dataset_id": "duplicate"}))

    with pytest.raises(ValueError, match="overlap"):
        validate_dataset_definitions((stock_daily, duplicate_root))


def test_depth_root_is_only_allowed_shared_root() -> None:
    sealed_l1 = get_dataset_definition("sealed_l1")
    depth5 = get_dataset_definition("depth5")

    assert sealed_l1.roots == depth5.roots == ("depth5",)
    assert sealed_l1.shared_root_group == depth5.shared_root_group == "depth_semantics"
    assert sealed_l1.semantic_classifier == depth5.semantic_classifier == "depth"


def test_registry_validation_rejects_a_third_depth_root_owner() -> None:
    sealed_l1 = get_dataset_definition("sealed_l1")
    depth5 = get_dataset_definition("depth5")
    third_owner = replace(
        depth5,
        descriptor=depth5.descriptor.model_copy(update={"dataset_id": "other_depth"}),
    )

    with pytest.raises(ValueError, match="overlap"):
        validate_dataset_definitions((sealed_l1, depth5, third_owner))


@pytest.mark.parametrize(
    "root",
    (
        "",
        "/kline_daily",
        ".",
        "./kline_daily",
        "kline_daily/",
        "kline//daily",
        "depth5/.",
        "../kline_daily",
    ),
)
def test_registry_validation_rejects_noncanonical_roots(root: str) -> None:
    stock_daily = get_dataset_definition("stock_daily")
    invalid_root = replace(stock_daily, roots=(root,))

    with pytest.raises(ValueError, match="root"):
        validate_dataset_definitions((invalid_root,))


def test_registry_validation_rejects_ancestor_descendant_root_ownership() -> None:
    stock_daily = get_dataset_definition("stock_daily")
    nested_owner = replace(
        stock_daily,
        descriptor=stock_daily.descriptor.model_copy(update={"dataset_id": "nested_daily"}),
        roots=("kline_daily/partitions",),
    )

    with pytest.raises(ValueError, match="overlap"):
        validate_dataset_definitions((stock_daily, nested_owner))


@pytest.mark.parametrize("reversed_order", (False, True))
def test_depth_dataset_exception_does_not_allow_nested_roots(reversed_order: bool) -> None:
    sealed_l1 = replace(get_dataset_definition("sealed_l1"), roots=("depth5/subdir",))
    depth5 = get_dataset_definition("depth5")
    definitions = (depth5, sealed_l1) if reversed_order else (sealed_l1, depth5)

    with pytest.raises(ValueError, match="overlap"):
        validate_dataset_definitions(definitions)


def test_realtime_datasets_use_utc_timestamp_and_name_shanghai_market_timezone() -> None:
    for dataset_id in ("quote_snapshot", "sealed_l1", "depth5"):
        timestamp = next(
            field
            for field in get_dataset_definition(dataset_id).descriptor.fields
            if field.name == "timestamp"
        )

        assert timestamp.timezone == "UTC"
        assert "asia/shanghai" in timestamp.semantic.lower()
