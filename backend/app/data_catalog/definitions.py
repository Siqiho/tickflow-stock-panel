"""Static dataset descriptors and their private local-storage ownership."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from .models import DatasetAvailability, DatasetDescriptor, FieldContract


@dataclass(frozen=True)
class DatasetDefinition:
    descriptor: DatasetDescriptor
    roots: tuple[str, ...]
    provider: str | None
    operation: str | None
    storage_category: str
    symbol_column: str | None = "symbol"
    time_column: str | None = None
    partition_key: str | None = None
    lineage_ids: tuple[str, ...] = ()
    semantic_classifier: Literal["default", "depth"] = "default"
    shared_root_group: str | None = None
    required_columns: tuple[str, ...] = ()
    required_column_sets: tuple[tuple[str, ...], ...] = ()
    schema_policy: Literal["strict", "opaque_dynamic"] = "strict"
    unit_policy: Literal["lineage", "reference"] = "lineage"
    ignored_parquet_names: tuple[str, ...] = ()


def _field(
    name: str,
    dtype: str,
    semantic: str,
    *,
    unit: str | None = None,
    scale: str | None = None,
    currency: str | None = None,
    timezone: str | None = None,
    nullable: bool = False,
) -> FieldContract:
    return FieldContract(
        name=name,
        dtype=dtype,
        semantic=semantic,
        unit=unit,
        scale=scale,
        currency=currency,
        timezone=timezone,
        nullable=nullable,
    )


def _descriptor(
    dataset_id: str,
    title: str,
    asset_types: list[str],
    grain: str,
    primary_key: list[str],
    fields: list[FieldContract],
    *,
    partition_keys: list[str] | None = None,
    point_in_time: bool = True,
    adjustment: str | None = None,
    unit_version: str = "cn_market_v1",
) -> DatasetDescriptor:
    return DatasetDescriptor(
        dataset_id=dataset_id,
        title=title,
        asset_types=asset_types,
        grain=grain,
        primary_key=primary_key,
        partition_keys=partition_keys or [],
        schema_version="1",
        unit_version=unit_version,
        point_in_time=point_in_time,
        adjustment=adjustment,
        availability=DatasetAvailability(),
        fields=fields,
    )


def _instrument_fields(asset_name: str) -> list[FieldContract]:
    return [
        _field("symbol", "string", f"Canonical {asset_name} identifier"),
        _field("name", "string", f"Display name of the {asset_name}"),
        _field("code", "string", f"Exchange-local code for the {asset_name}"),
        _field("asset_type", "string", f"Asset classification for the {asset_name}"),
    ]


def _stock_instrument_fields() -> list[FieldContract]:
    return [
        _field("symbol", "string", "Canonical stock identifier"),
        _field("name", "string", "Display name of the stock", nullable=True),
        _field("code", "string", "Exchange-local stock code", nullable=True),
        _field("exchange", "string", "Stock listing exchange", nullable=True),
        _field("region", "string", "Stock listing region", nullable=True),
        _field("type", "string", "Provider instrument type", nullable=True),
        _field("listing_date", "date", "Stock listing date", nullable=True),
        _field("total_shares", "float64", "Total shares outstanding", unit="share", nullable=True),
        _field(
            "float_shares", "float64", "Tradable shares outstanding", unit="share", nullable=True
        ),
        _field(
            "tick_size", "float64", "Minimum price tick", unit="CNY", currency="CNY", nullable=True
        ),
        _field(
            "limit_up",
            "float64",
            "Upper daily price limit for the stock",
            unit="CNY",
            currency="CNY",
            nullable=True,
        ),
        _field(
            "limit_down",
            "float64",
            "Lower daily price limit for the stock",
            unit="CNY",
            currency="CNY",
            nullable=True,
        ),
        _field(
            "as_of",
            "date",
            "Reference snapshot date in the Asia/Shanghai market calendar",
            timezone="Asia/Shanghai",
        ),
    ]


def _bar_fields(
    asset_name: str,
    time_name: str,
    *,
    time_semantic: str | None = None,
    time_timezone: str | None = None,
) -> list[FieldContract]:
    return [
        _field("symbol", "string", f"Canonical {asset_name} identifier"),
        _field(
            time_name,
            "date" if time_name == "date" else "datetime",
            time_semantic or f"{asset_name.title()} bar time",
            timezone=time_timezone,
        ),
        _field(
            "open", "float64", f"Opening price of the {asset_name} bar", unit="CNY", currency="CNY"
        ),
        _field(
            "high", "float64", f"Highest price of the {asset_name} bar", unit="CNY", currency="CNY"
        ),
        _field(
            "low", "float64", f"Lowest price of the {asset_name} bar", unit="CNY", currency="CNY"
        ),
        _field(
            "close", "float64", f"Closing price of the {asset_name} bar", unit="CNY", currency="CNY"
        ),
        _field("volume", "float64", f"Trading volume of the {asset_name} bar", unit="lot"),
        _field(
            "amount",
            "float64",
            f"Trading amount of the {asset_name} bar",
            unit="CNY",
            currency="CNY",
        ),
    ]


def _enriched_fields(asset_name: str) -> list[FieldContract]:
    return [
        *_bar_fields(asset_name, "date"),
        _field(
            "raw_close",
            "float64",
            f"Unadjusted closing price for the {asset_name}",
            unit="CNY",
            currency="CNY",
        ),
        _field(
            "raw_high",
            "float64",
            f"Unadjusted high price for the {asset_name}",
            unit="CNY",
            currency="CNY",
        ),
        _field(
            "raw_low",
            "float64",
            f"Unadjusted low price for the {asset_name}",
            unit="CNY",
            currency="CNY",
        ),
        *(
            [
                _field(
                    "turnover_rate",
                    "float64",
                    "Stored turnover rate for the stock",
                    unit="percentage_point",
                    nullable=True,
                ),
                _field(
                    "consecutive_limit_ups",
                    "int64",
                    "Stored consecutive upper-limit count for the stock",
                    nullable=True,
                ),
                _field(
                    "consecutive_limit_downs",
                    "int64",
                    "Stored consecutive lower-limit count for the stock",
                    nullable=True,
                ),
            ]
            if asset_name.lower() == "stock"
            else []
        ),
    ]


def _adjustment_fields(asset_name: str) -> list[FieldContract]:
    return [
        _field("symbol", "string", f"Canonical {asset_name} identifier"),
        _field("trade_date", "date", f"Trading date for the {asset_name} adjustment factor"),
        _field("ex_factor", "float64", f"Price adjustment factor for the {asset_name}"),
    ]


def _financial_fields(table: str) -> list[FieldContract]:
    identifiers = [
        _field("symbol", "string", "Canonical stock identifier"),
        _field("period_end", "date", "Financial reporting period end"),
        _field(
            "announce_date" if table == "shares" else "notice_date",
            "date",
            "Public announcement date",
            nullable=True,
        ),
    ]
    representative = {
        "metrics": [
            _field("roe", "float64", "Return on equity", unit="percentage_point", nullable=True)
        ],
        "income": [
            _field(
                "total_revenue",
                "float64",
                "Total operating revenue",
                unit="CNY",
                currency="CNY",
                nullable=True,
            )
        ],
        "balance_sheet": [
            _field(
                "total_assets", "float64", "Total assets", unit="CNY", currency="CNY", nullable=True
            )
        ],
        "cash_flow": [
            _field(
                "netcash_operate",
                "float64",
                "Net operating cash flow",
                unit="CNY",
                currency="CNY",
                nullable=True,
            )
        ],
        "shares": [
            _field(
                "total_shares", "float64", "Total shares outstanding", unit="share", nullable=True
            ),
            _field(
                "float_shares",
                "float64",
                "Tradable shares outstanding",
                unit="share",
                nullable=True,
            ),
        ],
    }
    return identifiers + representative[table]


DATASET_DEFINITIONS: tuple[DatasetDefinition, ...] = (
    DatasetDefinition(
        _descriptor(
            "stock_instruments",
            "Stocks",
            ["stock"],
            "one row per stock snapshot",
            ["symbol", "as_of"],
            _stock_instrument_fields(),
            unit_version="stock_instruments_v1",
        ),
        ("instruments",),
        None,
        None,
        "stocks",
        time_column="as_of",
        required_columns=(
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
        ),
        unit_policy="reference",
    ),
    DatasetDefinition(
        _descriptor(
            "stock_daily",
            "Stock daily bars",
            ["stock"],
            "one row per stock and trading day",
            ["symbol", "date"],
            _bar_fields("stock", "date"),
            partition_keys=["date"],
            unit_version="canonical_daily_v1",
        ),
        ("kline_daily",),
        None,
        None,
        "stocks",
        time_column="date",
        partition_key="date",
        required_columns=("symbol", "date", "open", "high", "low", "close", "volume", "amount"),
    ),
    DatasetDefinition(
        _descriptor(
            "stock_enriched",
            "Enriched stock daily bars",
            ["stock"],
            "one persisted narrow row per stock and trading day",
            ["symbol", "date"],
            _enriched_fields("stock"),
            partition_keys=["date"],
            unit_version="canonical_daily_v1",
        ),
        ("kline_daily_enriched",),
        None,
        None,
        "stocks",
        time_column="date",
        partition_key="date",
        required_columns=(
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
        ),
    ),
    DatasetDefinition(
        _descriptor(
            "stock_minute",
            "Stock minute bars",
            ["stock"],
            "one row per stock and minute",
            ["symbol", "datetime"],
            _bar_fields("stock", "datetime"),
            partition_keys=["date"],
            unit_version="canonical_minute_v1",
        ),
        ("kline_minute",),
        None,
        None,
        "stocks",
        time_column="datetime",
        partition_key="date",
        required_columns=("symbol", "datetime", "open", "high", "low", "close", "volume", "amount"),
    ),
    DatasetDefinition(
        _descriptor(
            "stock_adj_factor",
            "Stock adjustment factors",
            ["stock"],
            "one row per stock and trading day",
            ["symbol", "trade_date"],
            _adjustment_fields("stock"),
            partition_keys=["trade_date"],
            unit_version="canonical_adj_factor_v1",
        ),
        ("adj_factor",),
        None,
        None,
        "stocks",
        time_column="trade_date",
        partition_key="trade_date",
        required_columns=("symbol", "trade_date", "ex_factor"),
        ignored_parquet_names=("coverage.parquet",),
    ),
    DatasetDefinition(
        _descriptor(
            "etf_instruments",
            "ETFs",
            ["etf"],
            "one row per ETF",
            ["symbol"],
            _instrument_fields("ETF"),
            unit_version="etf_instruments_v1",
        ),
        ("instruments_etf",),
        None,
        None,
        "etfs",
        required_columns=("symbol", "name", "code", "asset_type"),
        unit_policy="reference",
    ),
    DatasetDefinition(
        _descriptor(
            "etf_daily",
            "ETF daily bars",
            ["etf"],
            "one row per ETF and trading day",
            ["symbol", "date"],
            _bar_fields("ETF", "date"),
            partition_keys=["date"],
            unit_version="canonical_daily_v1",
        ),
        ("kline_etf_daily",),
        None,
        None,
        "etfs",
        time_column="date",
        partition_key="date",
        required_columns=("symbol", "date", "open", "high", "low", "close", "volume", "amount"),
    ),
    DatasetDefinition(
        _descriptor(
            "etf_enriched",
            "Enriched ETF daily bars",
            ["etf"],
            "one persisted narrow row per ETF and trading day",
            ["symbol", "date"],
            _enriched_fields("ETF"),
            partition_keys=["date"],
            unit_version="canonical_daily_v1",
        ),
        ("kline_etf_enriched",),
        None,
        None,
        "etfs",
        time_column="date",
        partition_key="date",
        required_columns=(
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
        ),
    ),
    DatasetDefinition(
        _descriptor(
            "etf_minute",
            "ETF minute bars",
            ["etf"],
            "one row per ETF and minute",
            ["symbol", "datetime"],
            _bar_fields("ETF", "datetime"),
            partition_keys=["date"],
            unit_version="canonical_minute_v1",
        ),
        ("kline_etf_minute",),
        None,
        None,
        "etfs",
        time_column="datetime",
        partition_key="date",
        required_columns=("symbol", "datetime", "open", "high", "low", "close", "volume", "amount"),
    ),
    DatasetDefinition(
        _descriptor(
            "etf_adj_factor",
            "ETF adjustment factors",
            ["etf"],
            "one row per ETF and trading day",
            ["symbol", "trade_date"],
            _adjustment_fields("ETF"),
            partition_keys=["trade_date"],
            unit_version="canonical_adj_factor_v1",
        ),
        ("adj_factor_etf",),
        None,
        None,
        "etfs",
        time_column="trade_date",
        partition_key="trade_date",
        required_columns=("symbol", "trade_date", "ex_factor"),
    ),
    DatasetDefinition(
        _descriptor(
            "index_instruments",
            "Indices",
            ["index"],
            "one row per index",
            ["symbol"],
            _instrument_fields("index"),
            unit_version="index_instruments_v1",
        ),
        ("instruments_index",),
        None,
        None,
        "indices",
        required_columns=("symbol", "name", "code", "asset_type"),
        unit_policy="reference",
    ),
    DatasetDefinition(
        _descriptor(
            "index_daily",
            "Index daily bars",
            ["index"],
            "one row per index and trading day",
            ["symbol", "date"],
            _bar_fields("index", "date"),
            partition_keys=["date"],
            unit_version="canonical_daily_v1",
        ),
        ("kline_index_daily",),
        None,
        None,
        "indices",
        time_column="date",
        partition_key="date",
        required_columns=("symbol", "date", "open", "high", "low", "close", "volume", "amount"),
    ),
    DatasetDefinition(
        _descriptor(
            "index_enriched",
            "Enriched index daily bars",
            ["index"],
            "one persisted narrow row per index and trading day",
            ["symbol", "date"],
            _enriched_fields("index"),
            partition_keys=["date"],
            unit_version="canonical_daily_v1",
        ),
        ("kline_index_enriched",),
        None,
        None,
        "indices",
        time_column="date",
        partition_key="date",
        required_columns=(
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
        ),
    ),
    DatasetDefinition(
        _descriptor(
            "quote_snapshot",
            "Quote snapshots",
            ["stock", "etf", "index"],
            "one row per symbol and market-date snapshot",
            ["symbol", "date"],
            [
                *_bar_fields("quote snapshot", "date"),
                _field("source", "string", "Quote source"),
                _field("unit_version", "string", "Row unit contract"),
                _field(
                    "fetched_at",
                    "datetime",
                    "UTC fetch time; market timezone Asia/Shanghai",
                    timezone="UTC",
                    nullable=True,
                ),
            ],
            unit_version="cn_quote_v1",
        ),
        ("quote_snapshot",),
        None,
        None,
        "quote_snapshot",
        time_column="date",
        required_columns=(
            "symbol",
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "source",
            "unit_version",
        ),
    ),
    DatasetDefinition(
        _descriptor(
            "sealed_l1",
            "Sealed L1 quotes",
            ["stock"],
            "one sealed-limit summary per symbol and fetch time",
            ["symbol", "fetched_at"],
            [
                _field("symbol", "string", "Canonical stock identifier"),
                _field("sealed_up", "bool", "Whether the upper limit is sealed", nullable=True),
                _field("sealed_down", "bool", "Whether the lower limit is sealed", nullable=True),
                _field(
                    "ask1_vol",
                    "int64",
                    "Best ask volume used for sealed-limit judgment",
                    unit="unknown",
                    nullable=True,
                ),
                _field(
                    "bid1_vol",
                    "int64",
                    "Best bid volume used for sealed-limit judgment",
                    unit="unknown",
                    nullable=True,
                ),
                _field("status", "string", "Limit direction status"),
                _field(
                    "fetched_at",
                    "float64",
                    "UTC epoch seconds fetched time; market timezone Asia/Shanghai",
                    unit="s",
                    timezone="UTC",
                ),
            ],
            unit_version="sealed_l1_v1",
        ),
        ("sealed_l1", "depth5"),
        None,
        None,
        "sealed_l1",
        time_column="fetched_at",
        semantic_classifier="depth",
        shared_root_group="depth_semantics",
        required_columns=(
            "symbol",
            "sealed_up",
            "sealed_down",
            "ask1_vol",
            "bid1_vol",
            "status",
            "fetched_at",
        ),
    ),
    DatasetDefinition(
        _descriptor(
            "depth5",
            "Five-level order book",
            ["stock"],
            "one true five-level order book per symbol and quote time",
            ["symbol", "timestamp"],
            [
                _field("symbol", "string", "Canonical stock identifier"),
                _field(
                    "timestamp",
                    "datetime",
                    "UTC quote timestamp; market timezone Asia/Shanghai",
                    timezone="UTC",
                ),
                _field(
                    "bid_prices",
                    "list<float64>",
                    "Five bid prices",
                    unit="CNY",
                    currency="CNY",
                    nullable=True,
                ),
                _field(
                    "ask_prices",
                    "list<float64>",
                    "Five ask prices",
                    unit="CNY",
                    currency="CNY",
                    nullable=True,
                ),
                _field(
                    "bid_price_1",
                    "float64",
                    "Level-one bid price",
                    unit="CNY",
                    currency="CNY",
                    nullable=True,
                ),
                _field(
                    "bid_price_5",
                    "float64",
                    "Level-five bid price",
                    unit="CNY",
                    currency="CNY",
                    nullable=True,
                ),
                _field(
                    "ask_price_1",
                    "float64",
                    "Level-one ask price",
                    unit="CNY",
                    currency="CNY",
                    nullable=True,
                ),
                _field(
                    "ask_price_5",
                    "float64",
                    "Level-five ask price",
                    unit="CNY",
                    currency="CNY",
                    nullable=True,
                ),
                _field(
                    "bid_volume_5",
                    "float64",
                    "Level-five bid volume",
                    unit="unknown",
                    nullable=True,
                ),
                _field(
                    "ask_volume_5",
                    "float64",
                    "Level-five ask volume",
                    unit="unknown",
                    nullable=True,
                ),
            ],
            unit_version="depth5_v1",
        ),
        ("depth5",),
        None,
        None,
        "depth5",
        time_column="timestamp",
        semantic_classifier="depth",
        shared_root_group="depth_semantics",
        required_column_sets=(
            ("symbol", "timestamp", "bid_prices", "ask_prices"),
            ("symbol", "timestamp", "bid_price_1", "bid_price_5", "ask_price_1", "ask_price_5"),
        ),
    ),
    DatasetDefinition(
        _descriptor(
            "pools",
            "Stock pools",
            ["stock"],
            "one row per pool constituent snapshot",
            ["pool_id", "symbol", "as_of"],
            [
                _field("pool_id", "string", "Stock pool identifier"),
                _field("symbol", "string", "Canonical stock identifier"),
                _field("as_of", "date", "Pool membership snapshot date"),
            ],
            unit_version="pool_reference_v1",
        ),
        ("pools",),
        None,
        None,
        "pools",
        time_column="as_of",
        required_columns=("pool_id", "symbol", "as_of"),
        unit_policy="reference",
    ),
    DatasetDefinition(
        _descriptor(
            "ext_data",
            "External data",
            ["reference"],
            "provider-defined dynamic external rows",
            ["dynamic"],
            [_field("dynamic", "opaque", "Provider-defined dynamic schema", nullable=True)],
            unit_version="ext_data_dynamic_v1",
        ),
        ("ext_data",),
        None,
        None,
        "ext_data",
        symbol_column=None,
        schema_policy="opaque_dynamic",
        unit_policy="reference",
    ),
    DatasetDefinition(
        _descriptor(
            "financial_metrics",
            "Financial metrics",
            ["stock"],
            "one row per stock and reporting period",
            ["symbol", "period_end"],
            _financial_fields("metrics"),
            partition_keys=["period_end"],
            unit_version="financial_cn_v1",
        ),
        ("financials/metrics",),
        None,
        None,
        "financials",
        time_column="period_end",
        partition_key="period_end",
        required_columns=("symbol", "period_end"),
    ),
    DatasetDefinition(
        _descriptor(
            "financial_income",
            "Income statements",
            ["stock"],
            "one row per stock and reporting period",
            ["symbol", "period_end"],
            _financial_fields("income"),
            partition_keys=["period_end"],
            unit_version="financial_cn_v1",
        ),
        ("financials/income",),
        None,
        None,
        "financials",
        time_column="period_end",
        partition_key="period_end",
        required_columns=("symbol", "period_end"),
    ),
    DatasetDefinition(
        _descriptor(
            "financial_balance_sheet",
            "Balance sheets",
            ["stock"],
            "one row per stock and reporting period",
            ["symbol", "period_end"],
            _financial_fields("balance_sheet"),
            partition_keys=["period_end"],
            unit_version="financial_cn_v1",
        ),
        ("financials/balance_sheet",),
        None,
        None,
        "financials",
        time_column="period_end",
        partition_key="period_end",
        required_columns=("symbol", "period_end"),
    ),
    DatasetDefinition(
        _descriptor(
            "financial_cash_flow",
            "Cash-flow statements",
            ["stock"],
            "one row per stock and reporting period",
            ["symbol", "period_end"],
            _financial_fields("cash_flow"),
            partition_keys=["period_end"],
            unit_version="financial_cn_v1",
        ),
        ("financials/cash_flow",),
        None,
        None,
        "financials",
        time_column="period_end",
        partition_key="period_end",
        required_columns=("symbol", "period_end"),
    ),
    DatasetDefinition(
        _descriptor(
            "financial_shares",
            "Shares outstanding",
            ["stock"],
            "one row per stock and reporting period",
            ["symbol", "period_end"],
            _financial_fields("shares"),
            partition_keys=["period_end"],
            unit_version="financial_cn_v1",
        ),
        ("financials/shares",),
        None,
        None,
        "financials",
        time_column="period_end",
        partition_key="period_end",
        required_columns=("symbol", "period_end"),
    ),
)


def _is_canonical_relative_posix_root(root: str) -> bool:
    if not root or root.startswith("/") or root.endswith("/") or "\\" in root or "//" in root:
        return False
    return all(part not in {"", ".", ".."} for part in root.split("/"))


def _roots_overlap(left: str, right: str) -> bool:
    left_parts = PurePosixPath(left).parts
    right_parts = PurePosixPath(right).parts
    shortest = min(len(left_parts), len(right_parts))
    return left_parts[:shortest] == right_parts[:shortest]


def _allows_depth5_share(
    candidate_root: str,
    existing_root: str,
    left: DatasetDefinition,
    right: DatasetDefinition,
) -> bool:
    return (
        candidate_root == existing_root == "depth5"
        and left.shared_root_group == right.shared_root_group == "depth_semantics"
        and left.semantic_classifier == right.semantic_classifier == "depth"
        and {left.descriptor.dataset_id, right.descriptor.dataset_id} == {"sealed_l1", "depth5"}
    )


def validate_dataset_definitions(definitions: tuple[DatasetDefinition, ...]) -> None:
    seen_ids: set[str] = set()
    roots: dict[str, DatasetDefinition] = {}
    for definition in definitions:
        descriptor = definition.descriptor
        if not descriptor.dataset_id or descriptor.dataset_id in seen_ids:
            raise ValueError("dataset IDs must be non-empty and unique")
        seen_ids.add(descriptor.dataset_id)
        if not all(
            (
                descriptor.title,
                descriptor.asset_types,
                descriptor.grain,
                descriptor.schema_version,
                descriptor.unit_version,
                descriptor.primary_key,
                descriptor.fields,
            )
        ):
            raise ValueError(f"dataset {descriptor.dataset_id} has incomplete descriptor metadata")
        field_names = [field.name for field in descriptor.fields]
        if len(field_names) != len(set(field_names)):
            raise ValueError(f"dataset {descriptor.dataset_id} has duplicate field names")
        if not definition.roots:
            raise ValueError(f"dataset {descriptor.dataset_id} has no roots")
        if definition.required_columns and definition.required_column_sets:
            raise ValueError(
                f"dataset {descriptor.dataset_id} cannot use both required column forms"
            )
        descriptor_fields = set(field_names)
        required_sets = (
            definition.required_column_sets
            if definition.required_column_sets
            else (definition.required_columns,)
        )
        if definition.schema_policy == "strict" and any(
            not set(required) <= descriptor_fields for required in required_sets
        ):
            raise ValueError(
                f"dataset {descriptor.dataset_id} required columns must be descriptor fields"
            )
        for root in definition.roots:
            if not _is_canonical_relative_posix_root(root):
                raise ValueError(f"dataset {descriptor.dataset_id} has invalid root {root!r}")
            for existing_root, existing in roots.items():
                if _roots_overlap(root, existing_root) and not _allows_depth5_share(
                    root, existing_root, definition, existing
                ):
                    raise ValueError(f"root overlap is not allowed: {root}")
            roots[root] = definition


def get_dataset_definition(dataset_id: str) -> DatasetDefinition:
    for definition in DATASET_DEFINITIONS:
        if definition.descriptor.dataset_id == dataset_id:
            return definition
    raise KeyError(f"unknown dataset_id: {dataset_id}")


validate_dataset_definitions(DATASET_DEFINITIONS)
