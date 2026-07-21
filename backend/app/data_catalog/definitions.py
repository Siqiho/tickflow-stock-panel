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
        _field("exchange", "string", f"Listing exchange for the {asset_name}"),
        _field("asset_type", "string", f"Asset classification for the {asset_name}"),
        _field("list_date", "date", f"Listing date of the {asset_name}", nullable=True),
        _field("status", "string", f"Listing status of the {asset_name}", nullable=True),
    ]


def _stock_instrument_fields() -> list[FieldContract]:
    return [
        *_instrument_fields("stock"),
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
        _field("open", "float64", f"Opening price of the {asset_name} bar", unit="CNY", currency="CNY"),
        _field("high", "float64", f"Highest price of the {asset_name} bar", unit="CNY", currency="CNY"),
        _field("low", "float64", f"Lowest price of the {asset_name} bar", unit="CNY", currency="CNY"),
        _field("close", "float64", f"Closing price of the {asset_name} bar", unit="CNY", currency="CNY"),
        _field("volume", "float64", f"Trading volume of the {asset_name} bar", unit="lot"),
        _field("amount", "float64", f"Trading amount of the {asset_name} bar", unit="CNY", currency="CNY"),
        _field("change_pct", "float64", f"Price change of the {asset_name} bar", unit="percentage_point"),
    ]


def _enriched_fields(asset_name: str) -> list[FieldContract]:
    return [
        *_bar_fields(asset_name, "date"),
        _field("ma5", "float64", f"Five-day moving average for the {asset_name}", unit="CNY", currency="CNY", nullable=True),
        _field("rsi14", "float64", f"Fourteen-day RSI for the {asset_name}", nullable=True),
        _field("signal_limit_up", "bool", f"Whether the {asset_name} closed at its upper daily price limit", nullable=True),
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
        _field("announcement_date", "date", "Public announcement date", nullable=True),
    ]
    representative = {
        "metrics": [_field("roe", "float64", "Return on equity", unit="percentage_point", nullable=True)],
        "income": [_field("revenue", "float64", "Operating revenue", unit="CNY", currency="CNY", nullable=True)],
        "balance_sheet": [_field("total_assets", "float64", "Total assets", unit="CNY", currency="CNY", nullable=True)],
        "cash_flow": [_field("net_operating_cash_flow", "float64", "Net operating cash flow", unit="CNY", currency="CNY", nullable=True)],
        "shares": [
            _field("total_shares", "float64", "Total shares outstanding", unit="share", nullable=True),
            _field("float_shares", "float64", "Tradable shares outstanding", unit="share", nullable=True),
        ],
    }
    return identifiers + representative[table]


DATASET_DEFINITIONS: tuple[DatasetDefinition, ...] = (
    DatasetDefinition(_descriptor("stock_instruments", "Stocks", ["stock"], "one row per stock", ["symbol"], _stock_instrument_fields()), ("instruments",), None, None, "stocks"),
    DatasetDefinition(_descriptor("stock_daily", "Stock daily bars", ["stock"], "one row per stock and trading day", ["symbol", "date"], _bar_fields("stock", "date"), partition_keys=["date"]), ("kline_daily",), None, None, "stocks", time_column="date", partition_key="date"),
    DatasetDefinition(_descriptor("stock_enriched", "Enriched stock daily bars", ["stock"], "one row per stock and trading day", ["symbol", "date"], _enriched_fields("stock"), partition_keys=["date"]), ("kline_daily_enriched",), None, None, "stocks", time_column="date", partition_key="date"),
    DatasetDefinition(_descriptor("stock_minute", "Stock minute bars", ["stock"], "one row per stock and minute", ["symbol", "datetime"], _bar_fields("stock", "datetime"), partition_keys=["date"]), ("kline_minute",), None, None, "stocks", time_column="datetime", partition_key="date"),
    DatasetDefinition(_descriptor("stock_adj_factor", "Stock adjustment factors", ["stock"], "one row per stock and trading day", ["symbol", "trade_date"], _adjustment_fields("stock"), partition_keys=["trade_date"]), ("adj_factor",), None, None, "stocks", time_column="trade_date", partition_key="trade_date"),
    DatasetDefinition(_descriptor("etf_instruments", "ETFs", ["etf"], "one row per ETF", ["symbol"], _instrument_fields("ETF")), ("instruments_etf",), None, None, "etfs"),
    DatasetDefinition(_descriptor("etf_daily", "ETF daily bars", ["etf"], "one row per ETF and trading day", ["symbol", "date"], _bar_fields("ETF", "date"), partition_keys=["date"]), ("kline_etf_daily",), None, None, "etfs", time_column="date", partition_key="date"),
    DatasetDefinition(_descriptor("etf_enriched", "Enriched ETF daily bars", ["etf"], "one row per ETF and trading day", ["symbol", "date"], _enriched_fields("ETF"), partition_keys=["date"]), ("kline_etf_enriched",), None, None, "etfs", time_column="date", partition_key="date"),
    DatasetDefinition(_descriptor("etf_minute", "ETF minute bars", ["etf"], "one row per ETF and minute", ["symbol", "datetime"], _bar_fields("ETF", "datetime"), partition_keys=["date"]), ("kline_etf_minute",), None, None, "etfs", time_column="datetime", partition_key="date"),
    DatasetDefinition(_descriptor("etf_adj_factor", "ETF adjustment factors", ["etf"], "one row per ETF and trading day", ["symbol", "trade_date"], _adjustment_fields("ETF"), partition_keys=["trade_date"]), ("adj_factor_etf",), None, None, "etfs", time_column="trade_date", partition_key="trade_date"),
    DatasetDefinition(_descriptor("index_instruments", "Indices", ["index"], "one row per index", ["symbol"], _instrument_fields("index")), ("instruments_index",), None, None, "indices"),
    DatasetDefinition(_descriptor("index_daily", "Index daily bars", ["index"], "one row per index and trading day", ["symbol", "date"], _bar_fields("index", "date"), partition_keys=["date"]), ("kline_index_daily",), None, None, "indices", time_column="date", partition_key="date"),
    DatasetDefinition(_descriptor("index_enriched", "Enriched index daily bars", ["index"], "one row per index and trading day", ["symbol", "date"], _enriched_fields("index"), partition_keys=["date"]), ("kline_index_enriched",), None, None, "indices", time_column="date", partition_key="date"),
    DatasetDefinition(_descriptor("quote_snapshot", "Quote snapshots", ["stock", "etf", "index"], "one row per symbol and snapshot", ["symbol", "timestamp"], _bar_fields("quote snapshot", "timestamp", time_semantic="UTC quote snapshot timestamp; market timezone Asia/Shanghai", time_timezone="UTC"), unit_version="cn_market_v1"), ("quote_snapshot",), None, None, "quote_snapshot", time_column="timestamp"),
    DatasetDefinition(_descriptor("sealed_l1", "Sealed L1 quotes", ["stock"], "one row per symbol and quote time", ["symbol", "timestamp"], [_field("symbol", "string", "Canonical stock identifier"), _field("timestamp", "datetime", "UTC quote timestamp; market timezone Asia/Shanghai", timezone="UTC"), _field("bid_price_1", "float64", "Best bid price", unit="CNY", currency="CNY"), _field("bid_volume_1", "float64", "Best bid volume", unit="lot"), _field("ask_price_1", "float64", "Best ask price", unit="CNY", currency="CNY"), _field("ask_volume_1", "float64", "Best ask volume", unit="lot")]), ("depth5",), None, None, "sealed_l1", time_column="timestamp", semantic_classifier="depth", shared_root_group="depth_semantics"),
    DatasetDefinition(_descriptor("depth5", "Five-level order book", ["stock"], "one row per symbol and quote time", ["symbol", "timestamp"], [_field("symbol", "string", "Canonical stock identifier"), _field("timestamp", "datetime", "UTC quote timestamp; market timezone Asia/Shanghai", timezone="UTC"), _field("bid_price_1", "float64", "Level-one bid price", unit="CNY", currency="CNY"), _field("bid_price_5", "float64", "Level-five bid price", unit="CNY", currency="CNY"), _field("ask_price_1", "float64", "Level-one ask price", unit="CNY", currency="CNY"), _field("ask_price_5", "float64", "Level-five ask price", unit="CNY", currency="CNY"), _field("bid_volume_5", "float64", "Level-five bid volume", unit="lot"), _field("ask_volume_5", "float64", "Level-five ask volume", unit="lot")]), ("depth5",), None, None, "depth5", time_column="timestamp", semantic_classifier="depth", shared_root_group="depth_semantics"),
    DatasetDefinition(_descriptor("pools", "Stock pools", ["stock"], "one row per pool constituent", ["pool_id", "symbol"], [_field("pool_id", "string", "Stock pool identifier"), _field("symbol", "string", "Canonical stock identifier"), _field("as_of_date", "date", "Pool membership date")]), ("pools",), None, None, "pools", time_column="as_of_date"),
    DatasetDefinition(_descriptor("ext_data", "External data", ["reference"], "one row per external record", ["source", "record_id"], [_field("source", "string", "External data source"), _field("record_id", "string", "External source record identifier"), _field("published_at", "datetime", "External record publication time", nullable=True)], unit_version="ext_data_v1"), ("ext_data",), None, None, "ext_data", symbol_column=None, time_column="published_at"),
    DatasetDefinition(_descriptor("financial_metrics", "Financial metrics", ["stock"], "one row per stock and reporting period", ["symbol", "period_end"], _financial_fields("metrics"), partition_keys=["period_end"]), ("financials/metrics",), None, None, "financials", time_column="period_end", partition_key="period_end"),
    DatasetDefinition(_descriptor("financial_income", "Income statements", ["stock"], "one row per stock and reporting period", ["symbol", "period_end"], _financial_fields("income"), partition_keys=["period_end"]), ("financials/income",), None, None, "financials", time_column="period_end", partition_key="period_end"),
    DatasetDefinition(_descriptor("financial_balance_sheet", "Balance sheets", ["stock"], "one row per stock and reporting period", ["symbol", "period_end"], _financial_fields("balance_sheet"), partition_keys=["period_end"]), ("financials/balance_sheet",), None, None, "financials", time_column="period_end", partition_key="period_end"),
    DatasetDefinition(_descriptor("financial_cash_flow", "Cash-flow statements", ["stock"], "one row per stock and reporting period", ["symbol", "period_end"], _financial_fields("cash_flow"), partition_keys=["period_end"]), ("financials/cash_flow",), None, None, "financials", time_column="period_end", partition_key="period_end"),
    DatasetDefinition(_descriptor("financial_shares", "Shares outstanding", ["stock"], "one row per stock and reporting period", ["symbol", "period_end"], _financial_fields("shares"), partition_keys=["period_end"]), ("financials/shares",), None, None, "financials", time_column="period_end", partition_key="period_end"),
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
        if not all((descriptor.title, descriptor.asset_types, descriptor.grain, descriptor.schema_version, descriptor.unit_version, descriptor.primary_key, descriptor.fields)):
            raise ValueError(f"dataset {descriptor.dataset_id} has incomplete descriptor metadata")
        field_names = [field.name for field in descriptor.fields]
        if len(field_names) != len(set(field_names)):
            raise ValueError(f"dataset {descriptor.dataset_id} has duplicate field names")
        if not definition.roots:
            raise ValueError(f"dataset {descriptor.dataset_id} has no roots")
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
