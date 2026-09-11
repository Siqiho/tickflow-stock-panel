from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic import ValidationError

from app.data_catalog.definitions import (
    DATASET_DEFINITIONS,
    FIXED_EXT_DATA_DIRECTORY_IDS,
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
    "trading_calendar",
    "ext_data",
    "ext_fund_flow_bk",
    "ext_fund_flow_bk_daily",
    "ext_fund_flow_concept",
    "ext_fund_flow_concept_daily",
    "ext_fund_flow_stock",
    "ext_gn_ths",
    "ext_hy_ths",
    "financial_metrics",
    "financial_income",
    "financial_balance_sheet",
    "financial_cash_flow",
    "financial_shares",
    "stock_margin_trading",
    "market_pulse",
    "valuation_daily",
    "limit_up_events",
    "index_membership_history",
    "corporate_actions",
    "hithink_limit_pool",
    "hithink_dragon_tiger",
    "hithink_auction_snapshot",
    "hithink_valuation_snapshot",
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
        (
            DatasetState,
            {
                "dataset_id": "stock_daily",
                "schema_version": "1",
                "unit_version": "v1",
                "updated_at": "2026-07-21",
                "row_count": -1,
            },
        ),
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
    assert shares.unit_version == "financial_cn_v2"
    assert {field.name for field in shares.fields} >= {
        "symbol",
        "period_end",
        "total_shares",
        "float_shares",
    }


def test_market_pulse_has_owned_partition_and_unit_contract() -> None:
    definition = get_dataset_definition("market_pulse")

    assert definition.roots == ("market/pulse",)
    assert definition.partition_key == "trade_date"
    assert definition.coverage_policy == "on_demand"
    assert definition.descriptor.primary_key == ["trade_date", "record_type", "event_id"]
    assert definition.descriptor.unit_version == "market_pulse_v1"



def test_hithink_official_special_data_uses_independent_reference_roots() -> None:
    expected = {
        "hithink_limit_pool": (
            "reference/hithink_limit_pool",
            "trade_date",
            ["trade_date", "pool_kind", "symbol"],
            "hithink_limit_pool_v1",
        ),
        "hithink_dragon_tiger": (
            "reference/hithink_dragon_tiger",
            "trade_date",
            ["trade_date", "board_type", "symbol"],
            "hithink_dragon_tiger_v1",
        ),
        "hithink_auction_snapshot": (
            "reference/hithink_auction_snapshot",
            "trade_date",
            ["trade_date", "symbol", "stage"],
            "hithink_auction_snapshot_v1",
        ),
        "hithink_valuation_snapshot": (
            "reference/hithink_valuation_snapshot",
            "as_of",
            ["symbol", "as_of"],
            "hithink_valuation_snapshot_v1",
        ),
    }
    for dataset_id, (root, partition_key, primary_key, unit_version) in expected.items():
        definition = get_dataset_definition(dataset_id)
        assert definition.roots == (root,)
        assert definition.storage_category == "reference"
        assert definition.provider == "hithink"
        assert definition.unit_policy == "reference"
        assert definition.coverage_policy == "on_demand"
        assert definition.partition_key == partition_key
        assert definition.descriptor.primary_key == primary_key
        assert definition.descriptor.unit_version == unit_version
        assert definition.descriptor.point_in_time is False

    auction = get_dataset_definition("hithink_auction_snapshot")
    volume = next(field for field in auction.descriptor.fields if field.name == "auction_volume")
    assert volume.unit == "lot"


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
            if field.name == "raw_close"
        )
        for dataset_id in ("stock_enriched", "etf_enriched", "index_enriched")
    }

    assert "stock" in semantics["stock_enriched"].lower()
    assert "etf" in semantics["etf_enriched"].lower()
    assert "index" in semantics["index_enriched"].lower()
    assert len(set(semantics.values())) == 3


def test_enriched_descriptors_expose_only_columns_persisted_by_each_writer() -> None:
    fields = {
        dataset_id: {field.name for field in get_dataset_definition(dataset_id).descriptor.fields}
        for dataset_id in ("stock_enriched", "etf_enriched", "index_enriched")
    }
    common = {
        "symbol",
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "raw_close",
        "raw_high",
        "raw_low",
    }

    assert fields["etf_enriched"] == common
    assert fields["index_enriched"] == common
    assert fields["stock_enriched"] == common | {
        "turnover_rate",
        "consecutive_limit_ups",
        "consecutive_limit_downs",
    }


def test_registry_validation_rejects_overlapping_exclusive_roots() -> None:
    stock_daily = get_dataset_definition("stock_daily")
    duplicate_root = replace(
        stock_daily,
        descriptor=stock_daily.descriptor.model_copy(update={"dataset_id": "duplicate"}),
    )

    with pytest.raises(ValueError, match="overlap"):
        validate_dataset_definitions((stock_daily, duplicate_root))


def test_depth_root_is_only_allowed_shared_root() -> None:
    sealed_l1 = get_dataset_definition("sealed_l1")
    depth5 = get_dataset_definition("depth5")

    assert sealed_l1.roots == ("sealed_l1", "depth5")
    assert depth5.roots == ("depth5",)
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


def test_registry_allows_ext_data_remainder_and_fixed_child_roots() -> None:
    remainder = get_dataset_definition("ext_data")
    child = get_dataset_definition("ext_fund_flow_bk")

    assert remainder.roots == ("ext_data",)
    assert remainder.schema_policy == "opaque_dynamic"
    assert child.roots == ("ext_data/ext_fund_flow_bk",)
    assert set(FIXED_EXT_DATA_DIRECTORY_IDS) <= {
        definition.descriptor.dataset_id for definition in DATASET_DEFINITIONS
    }
    validate_dataset_definitions((remainder, child))


def test_registry_rejects_duplicate_ext_data_child_roots() -> None:
    remainder = get_dataset_definition("ext_data")
    child = get_dataset_definition("ext_fund_flow_bk")
    duplicate = replace(
        child,
        descriptor=child.descriptor.model_copy(update={"dataset_id": "ext_fund_flow_bk_dup"}),
    )

    with pytest.raises(ValueError, match="overlap"):
        validate_dataset_definitions((remainder, child, duplicate))


def test_registry_rejects_nested_ext_data_root_beyond_one_level() -> None:
    remainder = get_dataset_definition("ext_data")
    nested = replace(
        get_dataset_definition("ext_fund_flow_bk"),
        descriptor=get_dataset_definition("ext_fund_flow_bk").descriptor.model_copy(
            update={"dataset_id": "ext_fund_flow_bk_nested"}
        ),
        roots=("ext_data/ext_fund_flow_bk/extra",),
    )

    with pytest.raises(ValueError, match="overlap"):
        validate_dataset_definitions((remainder, nested))


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
    for dataset_id, time_field in (
        ("quote_snapshot", "fetched_at"),
        ("sealed_l1", "fetched_at"),
        ("depth5", "timestamp"),
    ):
        timestamp = next(
            field
            for field in get_dataset_definition(dataset_id).descriptor.fields
            if field.name == time_field
        )

        assert timestamp.timezone == "UTC"
        assert "asia/shanghai" in timestamp.semantic.lower()


def test_writer_contracts_are_explicit_and_match_current_materialized_columns() -> None:
    instruments = get_dataset_definition("stock_instruments")
    pools = get_dataset_definition("pools")
    sealed = get_dataset_definition("sealed_l1")
    ext_data = get_dataset_definition("ext_data")

    assert instruments.required_columns == (
        "symbol",
        "name",
        "code",
        "exchange",
        "region",
        "type",
        "listing_date",
        "total_shares",
        "float_shares",
        "tick_size",
        "limit_up",
        "limit_down",
        "as_of",
    )
    assert instruments.time_column == "as_of"
    assert pools.required_columns == ("pool_id", "symbol", "as_of")
    assert pools.time_column == "as_of"
    assert sealed.required_columns == (
        "symbol",
        "sealed_up",
        "sealed_down",
        "ask1_vol",
        "bid1_vol",
        "status",
        "fetched_at",
    )
    assert sealed.descriptor.unit_version == "sealed_l1_v1"
    assert ext_data.schema_policy == "opaque_dynamic"
    assert ext_data.required_columns == ()
    assert ext_data.descriptor.title == "扩展数据余项"
    daily = get_dataset_definition("ext_fund_flow_bk_daily")
    assert daily.roots == ("ext_data/ext_fund_flow_bk_daily",)
    assert daily.unit_policy == "reference"
    assert daily.coverage_policy == "on_demand"
    assert daily.required_columns == ("code", "name", "date", "main_net", "source")


def test_enriched_and_financial_descriptors_describe_persisted_narrow_tables() -> None:
    stock_enriched = get_dataset_definition("stock_enriched")
    fields = {field.name for field in stock_enriched.descriptor.fields}
    assert {"raw_close", "raw_high", "raw_low", "turnover_rate"} <= fields
    assert "rsi14" not in fields

    financial_fields = {
        dataset_id: {field.name for field in get_dataset_definition(dataset_id).descriptor.fields}
        for dataset_id in (
            "financial_metrics",
            "financial_income",
            "financial_balance_sheet",
            "financial_cash_flow",
            "financial_shares",
        )
    }
    assert "notice_date" in financial_fields["financial_metrics"]
    assert "total_revenue" in financial_fields["financial_income"]
    assert "netcash_operate" in financial_fields["financial_cash_flow"]
    assert "announce_date" in financial_fields["financial_shares"]


def test_trading_calendar_definition_is_reference_owned() -> None:
    definition = get_dataset_definition("trading_calendar")
    assert definition.roots == ("reference/trading_calendar",)
    assert definition.storage_category == "reference"
    assert definition.symbol_column is None
    assert definition.time_column == "trade_date"
    assert definition.unit_policy == "reference"
    assert definition.lineage_ids == ("trading_calendar",)
    assert definition.descriptor.unit_version == "trading_calendar_v1"
    assert definition.descriptor.primary_key == ["exchange", "trade_date"]
    field_names = {field.name for field in definition.descriptor.fields}
    assert {
        "exchange",
        "trade_date",
        "is_open",
        "session_type",
        "open_time",
        "close_time",
        "source",
        "as_of",
    } <= field_names


def test_margin_trading_definition_is_first_class_f10_data() -> None:
    definition = get_dataset_definition("stock_margin_trading")
    assert definition.roots == ("f10/stock_margin_trading",)
    assert definition.storage_category == "f10"
    assert definition.time_column == "trade_date"
    assert definition.descriptor.primary_key == ["symbol", "trade_date"]
    assert definition.descriptor.unit_version == "stock_margin_trading_v1"
    assert definition.descriptor.point_in_time is False
    fields = {field.name: field for field in definition.descriptor.fields}
    for name in (
        "financing_balance",
        "financing_buy_amount",
        "financing_repayment_amount",
        "financing_net_buy_amount",
        "securities_lending_balance",
        "margin_balance",
    ):
        assert fields[name].unit == "CNY"
    for name in (
        "securities_lending_sell_volume",
        "securities_lending_repayment_volume",
        "securities_lending_balance_volume",
    ):
        assert fields[name].unit == "share"
