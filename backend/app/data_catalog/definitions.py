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
    coverage_policy: Literal["full_universe", "on_demand"] = "full_universe"


FIXED_EXT_DATA_DIRECTORY_IDS: tuple[str, ...] = (
    "ext_fund_flow_bk",
    "ext_fund_flow_bk_daily",
    "ext_fund_flow_concept",
    "ext_fund_flow_concept_daily",
    "ext_fund_flow_stock",
    "ext_gn_ths",
    "ext_hy_ths",
)


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


def _margin_trading_fields() -> list[FieldContract]:
    money_fields = [
        _field(name, "float64", semantic, unit="CNY", currency="CNY")
        for name, semantic in (
            ("financing_balance", "Outstanding financing balance"),
            ("financing_buy_amount", "Daily financing purchase amount"),
            ("financing_repayment_amount", "Daily financing repayment amount"),
            ("financing_net_buy_amount", "Daily net financing purchase amount"),
            ("securities_lending_balance", "Outstanding securities-lending balance"),
            ("margin_balance", "Combined financing and securities-lending balance"),
        )
    ]
    volume_fields = [
        _field(name, "int64", semantic, unit="share")
        for name, semantic in (
            ("securities_lending_sell_volume", "Daily securities-lending sell volume"),
            (
                "securities_lending_repayment_volume",
                "Signed daily securities-lending repayment volume; negative values are source adjustments",
            ),
            ("securities_lending_balance_volume", "Outstanding securities-lending volume"),
        )
    ]
    return [
        _field("symbol", "string", "Canonical stock identifier"),
        _field("name", "string", "Stock display name", nullable=True),
        _field("market", "string", "EastMoney market display label"),
        _field(
            "trade_date",
            "date",
            "A-share trading date in the Asia/Shanghai market calendar",
            timezone="Asia/Shanghai",
        ),
        *money_fields,
        *volume_fields,
        _field("source", "string", "Observed producer endpoint identifier"),
        _field("unit_version", "string", "Canonical amount and volume unit contract"),
    ]


def _hithink_common_identity() -> list[FieldContract]:
    return [
        _field("symbol", "string", "Canonical A-share identifier mapped from official thscode"),
        _field("ticker", "string", "Exchange-local 6-digit code", nullable=True),
        _field("name", "string", "Official display name", nullable=True),
    ]


def _hithink_limit_pool_fields() -> list[FieldContract]:
    return [
        _field("pool_kind", "string", "Official pool kind: limit_up, limit_down, or limit_break"),
        *_hithink_common_identity(),
        _field(
            "trade_date",
            "date",
            "A-share trading date in the Asia/Shanghai market calendar",
            timezone="Asia/Shanghai",
        ),
        _field("is_st", "bool", "Official ST marker from the limit-up pool", nullable=True),
        _field("is_new", "bool", "Official new-listing marker from the limit-up pool", nullable=True),
        _field("last_price", "float64", "Official last price", unit="CNY", currency="CNY", nullable=True),
        _field("price_change_ratio_pct", "float64", "Official change ratio as a percent value", nullable=True),
        _field("limit_up_time", "string", "Official limit-up time text", nullable=True),
        _field("limit_up_reason", "string", "Official limit-up reason text", nullable=True),
        _field("continue_day_text", "string", "Official consecutive-board text", nullable=True),
        _field("continue_day_cnt", "int64", "Official consecutive-board count", nullable=True),
        _field("seal_money", "float64", "Official seal amount", unit="CNY", currency="CNY", nullable=True),
        _field("max_seal_money", "float64", "Official maximum seal amount", unit="CNY", currency="CNY", nullable=True),
        _field("first_limit_time", "string", "Official first limit-down time text", nullable=True),
        _field("last_limit_time", "string", "Official last limit-down time text", nullable=True),
        _field("turnover_ratio_pct", "float64", "Official turnover ratio as a percent value", nullable=True),
        _field("open_times", "int64", "Official limit-break open count", nullable=True),
        _field("turnover", "float64", "Official turnover amount", unit="CNY", currency="CNY", nullable=True),
        _field("source", "string", "Observed producer endpoint identifier"),
        _field("unit_version", "string", "Canonical official limit-pool unit contract"),
        _field("upstream_timestamp_ms", "int64", "Official payload timestamp in milliseconds", nullable=True),
    ]


def _hithink_dragon_tiger_fields() -> list[FieldContract]:
    return [
        *_hithink_common_identity(),
        _field(
            "trade_date",
            "date",
            "A-share trading date in the Asia/Shanghai market calendar",
            timezone="Asia/Shanghai",
        ),
        _field("board_type", "string", "Official board type: all, org, or hot_money"),
        _field("concept_list", "string", "Official concept list serialized as JSON", nullable=True),
        _field("change_pct", "float64", "Official change ratio as a percent value", nullable=True),
        _field("buy_value", "float64", "Official buy amount", unit="CNY", currency="CNY", nullable=True),
        _field("sell_value", "float64", "Official sell amount", unit="CNY", currency="CNY", nullable=True),
        _field("net_value", "float64", "Official net amount", unit="CNY", currency="CNY", nullable=True),
        _field("net_rate", "float64", "Official net amount ratio", nullable=True),
        _field("org_net_value", "float64", "Official institution net amount", unit="CNY", currency="CNY", nullable=True),
        _field("hot_money_net_value", "float64", "Official hot-money net amount", unit="CNY", currency="CNY", nullable=True),
        _field("hot_rank", "int64", "Official heat rank", nullable=True),
        _field("range_days", "int64", "Official consecutive listing days", nullable=True),
        _field("limit_reason", "string", "Official limit reason text", nullable=True),
        _field("source", "string", "Observed producer endpoint identifier"),
        _field("unit_version", "string", "Canonical official dragon-tiger unit contract"),
        _field("upstream_timestamp_ms", "int64", "Official payload timestamp in milliseconds", nullable=True),
    ]


def _hithink_auction_fields() -> list[FieldContract]:
    return [
        *_hithink_common_identity(),
        _field(
            "trade_date",
            "date",
            "A-share trading date in the Asia/Shanghai market calendar",
            timezone="Asia/Shanghai",
        ),
        _field("stage", "string", "Requested auction stage: live or final"),
        _field("auction_phase", "string", "Official auction phase", nullable=True),
        _field("data_status", "string", "Official data status", nullable=True),
        _field("auction_price", "float64", "Official auction price", unit="CNY", currency="CNY", nullable=True),
        _field("auction_pct", "float64", "Official auction change as a percent value", nullable=True),
        _field("auction_volume", "float64", "Official auction volume in lots", unit="lot", nullable=True),
        _field("auction_amount", "float64", "Official auction amount", unit="CNY", currency="CNY", nullable=True),
        _field("auction_unmatched", "float64", "Official unmatched auction volume", nullable=True),
        _field("auction_turnover_pct", "float64", "Official auction turnover as a percent value", nullable=True),
        _field("auction_yesterday_ratio_pct", "float64", "Official volume versus yesterday as a percent value", nullable=True),
        _field("auction_volume_ratio", "float64", "Official auction volume ratio", nullable=True),
        _field("pre_close_price", "float64", "Official previous close", unit="CNY", currency="CNY", nullable=True),
        _field("open_price", "float64", "Official open price", unit="CNY", currency="CNY", nullable=True),
        _field("last_price", "float64", "Official last price", unit="CNY", currency="CNY", nullable=True),
        _field("float_market_cap", "float64", "Official float market cap", unit="CNY", currency="CNY", nullable=True),
        _field("source", "string", "Observed producer endpoint identifier"),
        _field("unit_version", "string", "Canonical official auction snapshot unit contract"),
        _field("upstream_timestamp_ms", "int64", "Official payload timestamp in milliseconds", nullable=True),
    ]


def _hithink_valuation_fields() -> list[FieldContract]:
    return [
        *_hithink_common_identity(),
        _field(
            "as_of",
            "date",
            "Shanghai calendar date of the latest official valuation snapshot",
            timezone="Asia/Shanghai",
        ),
        _field("pe_ttm", "float64", "Official PE TTM; nulls and negatives are preserved", nullable=True),
        _field("pe_mrq", "float64", "Official PE MRQ; nulls and negatives are preserved", nullable=True),
        _field("pb_mrq", "float64", "Official PB MRQ; nulls and negatives are preserved", nullable=True),
        _field("ps_ttm", "float64", "Official PS TTM; nulls and negatives are preserved", nullable=True),
        _field("pcf_ttm", "float64", "Official PCF TTM; nulls and negatives are preserved", nullable=True),
        _field("source", "string", "Observed producer endpoint identifier"),
        _field("unit_version", "string", "Canonical official valuation snapshot unit contract"),
        _field("upstream_timestamp_ms", "int64", "Official payload timestamp in milliseconds", nullable=True),
    ]


def _market_pulse_fields() -> list[FieldContract]:
    return [
        _field("record_type", "string", "Record kind: index minute or sector event"),
        _field("event_id", "string", "Stable identifier within the trading date"),
        _field(
            "trade_date",
            "date",
            "A-share trading date in the Asia/Shanghai market calendar",
            timezone="Asia/Shanghai",
        ),
        _field(
            "event_time",
            "datetime",
            "Minute or sector-event wall-clock time",
            timezone="Asia/Shanghai",
        ),
        _field("minute", "int64", "HHMM wall-clock minute in Asia/Shanghai"),
        _field("benchmark_symbol", "string", "Canonical benchmark index identifier"),
        _field("benchmark_name", "string", "Benchmark index display name"),
        _field("last_price", "float64", "Benchmark index level", unit="point", nullable=True),
        _field("change_ratio", "float64", "Benchmark change ratio", unit="ratio", nullable=True),
        _field("preclose", "float64", "Previous benchmark close", unit="point", nullable=True),
        _field("open", "float64", "Benchmark open level", unit="point", nullable=True),
        _field("volume", "int64", "Upstream minute trading volume", unit="share", nullable=True),
        _field(
            "amount",
            "float64",
            "Upstream minute trading amount",
            unit="CNY",
            currency="CNY",
            nullable=True,
        ),
        _field("sector_code", "string", "CLS sector identifier", nullable=True),
        _field("sector_name", "string", "CLS sector display name", nullable=True),
        _field("direction", "string", "Sector event direction: up or down", nullable=True),
        _field("article_id", "int64", "CLS source event identifier", nullable=True),
        _field("source", "string", "Observed producer endpoint identifier"),
        _field("unit_version", "string", "Canonical market-pulse unit contract"),
    ]


def _fund_flow_snapshot_fields() -> list[FieldContract]:
    return [
        _field("code", "string", "Board or concept code"),
        _field("name", "string", "Board or concept name"),
        _field(
            "main_net",
            "float64",
            "Main-force net inflow",
            unit="CNY",
            currency="CNY",
            nullable=True,
        ),
        _field("change_pct", "float64", "Change percent", nullable=True),
        _field("main_net_pct", "float64", "Main-force net inflow share", nullable=True),
        _field(
            "price",
            "float64",
            "Latest price",
            unit="CNY",
            currency="CNY",
            nullable=True,
        ),
        _field("leader_name", "string", "Leading stock name", nullable=True),
        _field("leader_code", "string", "Leading stock code", nullable=True),
        _field("rank", "int64", "Rank", nullable=True),
        _field("as_of", "string", "Snapshot time"),
        _field("kind", "string", "Board or concept kind", nullable=True),
        _field("source", "string", "Observed producer identifier"),
        _field("unit_amount", "string", "Amount unit", nullable=True),
    ]


def _fund_flow_daily_fields(*, stock: bool = False) -> list[FieldContract]:
    identity = (
        [
            _field("symbol", "string", "Canonical stock identifier"),
            _field("date", "string", "Trading date"),
        ]
        if stock
        else [
            _field("code", "string", "Board or concept code"),
            _field("name", "string", "Board or concept name", nullable=True),
            _field("date", "string", "Trading date"),
        ]
    )
    return [
        *identity,
        _field(
            "main_net",
            "float64",
            "Main-force net inflow",
            unit="CNY",
            currency="CNY",
            nullable=True,
        ),
        _field(
            "small_net",
            "float64",
            "Small-order net inflow",
            unit="CNY",
            currency="CNY",
            nullable=True,
        ),
        _field(
            "med_net",
            "float64",
            "Medium-order net inflow",
            unit="CNY",
            currency="CNY",
            nullable=True,
        ),
        _field(
            "large_net",
            "float64",
            "Large-order net inflow",
            unit="CNY",
            currency="CNY",
            nullable=True,
        ),
        _field(
            "super_net",
            "float64",
            "Super-large-order net inflow",
            unit="CNY",
            currency="CNY",
            nullable=True,
        ),
        _field("main_net_pct", "float64", "Main-force net inflow share", nullable=True),
        _field("source", "string", "Observed producer identifier"),
        _field("unit_amount", "string", "Amount unit", nullable=True),
    ]


def _ths_membership_fields(membership_name: str, membership_semantic: str) -> list[FieldContract]:
    return [
        _field("symbol", "string", "Canonical stock identifier"),
        _field("code", "string", "Exchange-local stock code"),
        _field("股票代码", "string", "Display stock code"),
        _field("股票简称", "string", "Display stock name"),
        _field(membership_name, "string", membership_semantic),
    ]


def _ext_directory_definition(
    dataset_id: str,
    title: str,
    grain: str,
    primary_key: list[str],
    fields: list[FieldContract],
    *,
    symbol_column: str | None,
    time_column: str | None,
    required_columns: tuple[str, ...],
    unit_version: str,
    partition_key: str | None = None,
) -> DatasetDefinition:
    return DatasetDefinition(
        _descriptor(
            dataset_id,
            title,
            ["reference"],
            grain,
            primary_key,
            fields,
            partition_keys=[partition_key] if partition_key else [],
            point_in_time=False,
            unit_version=unit_version,
        ),
        (f"ext_data/{dataset_id}",),
        None,
        None,
        "ext_data",
        symbol_column=symbol_column,
        time_column=time_column,
        partition_key=partition_key,
        required_columns=required_columns,
        unit_policy="reference",
        coverage_policy="on_demand",
    )


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
        coverage_policy="on_demand",
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
        ignored_parquet_names=("coverage.parquet", "verification.parquet"),
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
            "trading_calendar",
            "Trading calendar",
            ["reference"],
            "one row per exchange and calendar date",
            ["exchange", "trade_date"],
            [
                _field("exchange", "string", "Exchange code SH/SZ/BJ"),
                _field("trade_date", "date", "Calendar date"),
                _field("is_open", "bool", "Whether the exchange cash session is open"),
                _field(
                    "session_type",
                    "string",
                    "Session classification: normal/half_day/closed/holiday/special",
                ),
                _field(
                    "open_time",
                    "string",
                    "Local session open time HH:MM when open",
                    nullable=True,
                ),
                _field(
                    "close_time",
                    "string",
                    "Local session close time HH:MM when open",
                    nullable=True,
                ),
                _field("source", "string", "Producer identifier for the calendar row"),
                _field("as_of", "date", "Observation or publish date of the calendar run"),
            ],
            unit_version="trading_calendar_v1",
            point_in_time=False,
        ),
        ("reference/trading_calendar",),
        None,
        None,
        "reference",
        symbol_column=None,
        time_column="trade_date",
        lineage_ids=("trading_calendar",),
        required_columns=(
            "exchange",
            "trade_date",
            "is_open",
            "session_type",
            "open_time",
            "close_time",
            "source",
            "as_of",
        ),
        unit_policy="reference",
    ),
    DatasetDefinition(
        _descriptor(
            "valuation_daily",
            "Derived daily valuation",
            ["stock"],
            "one row per stock and trading day derived from local raw daily x PIT-safe shares",
            ["symbol", "trade_date"],
            [
                _field("symbol", "string", "Canonical stock identifier"),
                _field("trade_date", "date", "Trading day of the source daily partition"),
                _field("pe_ttm", "float64", "PE TTM; null without an admitted historical feed", nullable=True),
                _field("pb", "float64", "PB; null without an admitted historical feed", nullable=True),
                _field("ps_ttm", "float64", "PS TTM; null without an admitted historical feed", nullable=True),
                _field("pcf_ttm", "float64", "PCF TTM; null without an admitted historical feed", nullable=True),
                _field("total_mv", "float64", "Total market value from PIT-safe shares", unit="CNY", currency="CNY", nullable=True),
                _field("float_mv", "float64", "Float market value from PIT-safe shares", unit="CNY", currency="CNY", nullable=True),
                _field("total_share", "float64", "PIT-safe total shares", unit="share", nullable=True),
                _field("float_share", "float64", "PIT-safe float shares", unit="share", nullable=True),
                _field("close", "float64", "Raw unadjusted close", unit="CNY", currency="CNY"),
                _field("shares_pit_safe", "bool", "Whether strict PIT shares were available"),
                _field("shares_source", "string", "Source of the PIT-safe shares row", nullable=True),
                _field("source", "string", "Derivation identifier"),
                _field("fetched_at", "datetime", "Derivation time UTC naive"),
                _field("unit_note", "string", "Unit and derivation disclosure"),
                _field("history_guarantee", "string", "as_collected"),
                _field("unit_version", "string", "valuation_daily_v2"),
            ],
            partition_keys=["date"],
            point_in_time=False,
            unit_version="valuation_daily_v2",
        ),
        ("reference/valuation_daily",),
        None,
        None,
        "reference",
        time_column="trade_date",
        partition_key="date",
        required_columns=("symbol", "trade_date", "close", "shares_pit_safe", "unit_version"),
        unit_policy="reference",
        coverage_policy="on_demand",
    ),
    DatasetDefinition(
        _descriptor(
            "limit_up_events",
            "Derived EOD limit events",
            ["stock"],
            "one row per stock limit event and trading day derived from local raw daily board rules",
            ["symbol", "trade_date"],
            [
                _field("symbol", "string", "Canonical stock identifier"),
                _field("trade_date", "date", "Trading day of the source daily partition"),
                _field("state", "string", "limit_up_final/limit_down_final/broken_limit_up/broken_limit_down"),
                _field("board", "string", "SH_MAIN/SZ_MAIN/CHINEXT/STAR/BJ board classification"),
                _field("is_st", "bool", "Risk-warning marker from current name snapshot"),
                _field("st_history_guarantee", "string", "name_asof_snapshot_only"),
                _field("limit_pct", "float64", "Rule-based daily limit ratio", scale="ratio"),
                _field("prev_close", "float64", "Previous raw close", unit="CNY", currency="CNY"),
                _field("limit_up", "float64", "Rule-derived limit-up price", unit="CNY", currency="CNY"),
                _field("limit_down", "float64", "Rule-derived limit-down price", unit="CNY", currency="CNY"),
                _field("close", "float64", "Raw unadjusted close", unit="CNY", currency="CNY"),
                _field("high", "float64", "Raw unadjusted high", unit="CNY", currency="CNY", nullable=True),
                _field("low", "float64", "Raw unadjusted low", unit="CNY", currency="CNY", nullable=True),
                _field("first_seal", "string", "Not derivable from EOD daily; always null", nullable=True),
                _field("last_seal", "string", "Not derivable from EOD daily; always null", nullable=True),
                _field("break_count", "int64", "Not derivable from EOD daily; always null", nullable=True),
                _field("seal_fund", "float64", "Same-day sealed_l1 bid1 volume when present", nullable=True),
                _field("board_height", "int64", "Consecutive limit-ups from same-day enriched", nullable=True),
                _field("reason", "string", "Rule state echo; no upstream reason text"),
                _field("reason_text", "string", "Always null; no licensed reason source", nullable=True),
                _field("intraday_vs_final", "string", "final_eod"),
                _field("price_basis", "string", "raw_unadjusted"),
                _field("limit_basis", "string", "prev_close_rule"),
                _field("history_guarantee", "string", "eod_final_only; st_from_current_name_snapshot"),
                _field("unit_version", "string", "limit_up_events_v2"),
                _field("source_published_at", "datetime", "Derivation time UTC naive"),
                _field("first_seen_at", "datetime", "Derivation time UTC naive"),
                _field("source", "string", "Derivation identifier"),
            ],
            partition_keys=["date"],
            point_in_time=False,
            unit_version="limit_up_events_v2",
        ),
        ("reference/limit_up_events",),
        None,
        None,
        "reference",
        time_column="trade_date",
        partition_key="date",
        required_columns=("symbol", "trade_date", "state", "board", "limit_pct", "unit_version"),
        unit_policy="reference",
        coverage_policy="on_demand",
    ),
    DatasetDefinition(
        _descriptor(
            "index_membership_history",
            "Index membership observation history",
            ["index"],
            "one row per pool membership interval observed from local pools snapshots",
            ["pool_id", "symbol", "effective_from"],
            [
                _field("symbol", "string", "Canonical stock identifier"),
                _field("index_code", "string", "Index numeric code"),
                _field("index_symbol", "string", "Canonical index symbol", nullable=True),
                _field("effective_from", "date", "First observation date of membership"),
                _field("effective_to", "date", "Observed removal date; null while member", nullable=True),
                _field("source", "string", "Seed source chain"),
                _field("as_of", "date", "Pools snapshot observation date"),
                _field("first_seen_at", "datetime", "Derivation time UTC naive"),
                _field("pool_id", "string", "Local pool identifier"),
                _field("membership_basis", "string", "snapshot_seed/snapshot_diff; not official revisions"),
                _field("history_guarantee", "string", "as_collected"),
                _field("unit_version", "string", "index_membership_history_v2"),
            ],
            point_in_time=False,
            unit_version="index_membership_history_v2",
        ),
        ("reference/index_membership_history",),
        None,
        None,
        "reference",
        time_column="as_of",
        required_columns=(
            "symbol",
            "index_code",
            "effective_from",
            "pool_id",
            "membership_basis",
            "unit_version",
        ),
        unit_policy="reference",
        coverage_policy="on_demand",
    ),
    DatasetDefinition(
        _descriptor(
            "corporate_actions",
            "Corporate actions",
            ["stock"],
            "one row per corporate action event (sourced facts + adj-derived verification signals)",
            ["symbol", "action_id"],
            [
                _field("symbol", "string", "Canonical stock identifier"),
                _field("action_id", "string", "Stable event identity hash"),
                _field("action_type", "string", "dividend_cash/bonus/mixed/unknown/identity_marker"),
                _field("announce_date", "date", "Plan announce date from producer", nullable=True),
                _field("record_date", "date", "Equity record date", nullable=True),
                _field("ex_date", "date", "Ex-dividend date"),
                _field("pay_date", "date", "Pay date when disclosed", nullable=True),
                _field("cash_per_share", "float64", "Pre-tax cash per share", unit="CNY", currency="CNY", nullable=True),
                _field("stock_ratio", "float64", "Bonus+transfer shares per share", scale="ratio", nullable=True),
                _field("rights_ratio", "float64", "Rights issue ratio per share", scale="ratio", nullable=True),
                _field("currency", "string", "CNY/unknown"),
                _field("source_published_at", "datetime", "Producer publish observation UTC naive"),
                _field("first_seen_at", "datetime", "First local observation UTC naive"),
                _field("source", "string", "eastmoney_sharebonus_det/eastmoney_bonus_f10/adj_factor_derived/..."),
                _field("as_of", "date", "Collection date"),
                _field("verification_status", "string", "verified_events/quarantined/unverified", nullable=True),
                _field("is_verification_signal", "bool", "True for adj-derived signals; excluded from formal facts", nullable=True),
                _field("unit_version", "string", "corporate_actions_v2", nullable=True),
            ],
            point_in_time=False,
            unit_version="corporate_actions_v2",
        ),
        ("reference/corporate_actions",),
        None,
        None,
        "reference",
        time_column="ex_date",
        required_columns=(
            "symbol",
            "action_id",
            "action_type",
            "ex_date",
            "source",
            "as_of",
        ),
        unit_policy="reference",
        coverage_policy="on_demand",
    ),
    DatasetDefinition(
        _descriptor(
            "ext_data",
            "扩展数据余项",
            ["reference"],
            "opaque remainder of user-created ext_data tables",
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
    _ext_directory_definition(
        "ext_fund_flow_bk",
        "行业资金流快照",
        "one snapshot row per industry board",
        ["code", "as_of"],
        _fund_flow_snapshot_fields(),
        symbol_column="code",
        time_column="as_of",
        required_columns=("code", "name", "main_net", "as_of", "source"),
        unit_version="ext_fund_flow_bk_v1",
    ),
    _ext_directory_definition(
        "ext_fund_flow_bk_daily",
        "行业资金流日线",
        "one row per industry board and trading day",
        ["code", "date"],
        _fund_flow_daily_fields(),
        symbol_column="code",
        time_column="date",
        required_columns=("code", "name", "date", "main_net", "source"),
        unit_version="ext_fund_flow_bk_daily_v1",
        partition_key="date",
    ),
    _ext_directory_definition(
        "ext_fund_flow_concept",
        "概念资金流快照",
        "one snapshot row per concept board",
        ["code", "as_of"],
        _fund_flow_snapshot_fields(),
        symbol_column="code",
        time_column="as_of",
        required_columns=("code", "name", "main_net", "as_of", "source"),
        unit_version="ext_fund_flow_concept_v1",
    ),
    _ext_directory_definition(
        "ext_fund_flow_concept_daily",
        "概念资金流日线",
        "one row per concept board and trading day",
        ["code", "date"],
        _fund_flow_daily_fields(),
        symbol_column="code",
        time_column="date",
        required_columns=("code", "name", "date", "main_net", "source"),
        unit_version="ext_fund_flow_concept_daily_v1",
        partition_key="date",
    ),
    _ext_directory_definition(
        "ext_fund_flow_stock",
        "个股资金流",
        "one row per stock and trading day",
        ["symbol", "date"],
        _fund_flow_daily_fields(stock=True),
        symbol_column="symbol",
        time_column="date",
        required_columns=("symbol", "date", "main_net", "source"),
        unit_version="ext_fund_flow_stock_v1",
        partition_key="date",
    ),
    _ext_directory_definition(
        "ext_gn_ths",
        "扩展概念",
        "one membership snapshot row per stock",
        ["symbol"],
        _ths_membership_fields("所属概念", "THS concept membership"),
        symbol_column="symbol",
        time_column=None,
        required_columns=("symbol", "code", "股票代码", "股票简称", "所属概念"),
        unit_version="ext_gn_ths_v1",
    ),
    _ext_directory_definition(
        "ext_hy_ths",
        "扩展行业",
        "one membership snapshot row per stock",
        ["symbol"],
        _ths_membership_fields("所属同花顺行业", "THS industry membership"),
        symbol_column="symbol",
        time_column=None,
        required_columns=("symbol", "code", "股票代码", "股票简称", "所属同花顺行业"),
        unit_version="ext_hy_ths_v1",
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
            "stock_margin_trading",
            "个股融资融券",
            ["stock"],
            "one row per stock and trading day",
            ["symbol", "trade_date"],
            _margin_trading_fields(),
            point_in_time=False,
            unit_version="stock_margin_trading_v1",
        ),
        ("f10/stock_margin_trading",),
        None,
        None,
        "f10",
        time_column="trade_date",
        required_columns=(
            "symbol",
            "name",
            "market",
            "trade_date",
            "financing_balance",
            "financing_buy_amount",
            "financing_repayment_amount",
            "financing_net_buy_amount",
            "securities_lending_balance",
            "securities_lending_sell_volume",
            "securities_lending_repayment_volume",
            "securities_lending_balance_volume",
            "margin_balance",
            "source",
            "unit_version",
        ),
    ),
    DatasetDefinition(
        _descriptor(
            "market_pulse",
            "市场脉搏",
            ["index", "sector"],
            "one benchmark minute or sector event per record",
            ["trade_date", "record_type", "event_id"],
            _market_pulse_fields(),
            partition_keys=["trade_date"],
            point_in_time=False,
            unit_version="market_pulse_v1",
        ),
        ("market/pulse",),
        "public",
        "market_pulse",
        "indices",
        symbol_column="benchmark_symbol",
        time_column="trade_date",
        partition_key="trade_date",
        required_columns=(
            "record_type",
            "event_id",
            "trade_date",
            "event_time",
            "minute",
            "benchmark_symbol",
            "benchmark_name",
            "last_price",
            "change_ratio",
            "preclose",
            "open",
            "volume",
            "amount",
            "sector_code",
            "sector_name",
            "direction",
            "article_id",
            "source",
            "unit_version",
        ),
        coverage_policy="on_demand",
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
            unit_version="financial_cn_v2",
        ),
        ("financials/shares",),
        None,
        None,
        "financials",
        time_column="period_end",
        partition_key="period_end",
        required_columns=("symbol", "period_end"),
    ),
    DatasetDefinition(
        _descriptor(
            "hithink_limit_pool",
            "同花顺官方涨跌停池",
            ["stock"],
            "one official limit-up, limit-down, or limit-break row per stock and trading day",
            ["trade_date", "pool_kind", "symbol"],
            _hithink_limit_pool_fields(),
            partition_keys=["trade_date"],
            point_in_time=False,
            unit_version="hithink_limit_pool_v1",
        ),
        ("reference/hithink_limit_pool",),
        "hithink",
        "hithink_limit_pool",
        "reference",
        time_column="trade_date",
        partition_key="trade_date",
        required_columns=(
            "pool_kind",
            "symbol",
            "trade_date",
            "source",
            "unit_version",
        ),
        unit_policy="reference",
        coverage_policy="on_demand",
    ),
    DatasetDefinition(
        _descriptor(
            "hithink_dragon_tiger",
            "同花顺官方龙虎榜",
            ["stock"],
            "one official dragon-tiger board row per stock and trading day",
            ["trade_date", "board_type", "symbol"],
            _hithink_dragon_tiger_fields(),
            partition_keys=["trade_date"],
            point_in_time=False,
            unit_version="hithink_dragon_tiger_v1",
        ),
        ("reference/hithink_dragon_tiger",),
        "hithink",
        "hithink_dragon_tiger",
        "reference",
        time_column="trade_date",
        partition_key="trade_date",
        required_columns=(
            "symbol",
            "trade_date",
            "board_type",
            "source",
            "unit_version",
        ),
        unit_policy="reference",
        coverage_policy="on_demand",
    ),
    DatasetDefinition(
        _descriptor(
            "hithink_auction_snapshot",
            "同花顺官方集合竞价快照",
            ["stock"],
            "one official auction snapshot row per watchlist stock, trading day, and stage",
            ["trade_date", "symbol", "stage"],
            _hithink_auction_fields(),
            partition_keys=["trade_date"],
            point_in_time=False,
            unit_version="hithink_auction_snapshot_v1",
        ),
        ("reference/hithink_auction_snapshot",),
        "hithink",
        "hithink_auction_snapshot",
        "reference",
        time_column="trade_date",
        partition_key="trade_date",
        required_columns=(
            "symbol",
            "trade_date",
            "stage",
            "source",
            "unit_version",
        ),
        unit_policy="reference",
        coverage_policy="on_demand",
    ),
    DatasetDefinition(
        _descriptor(
            "hithink_valuation_snapshot",
            "同花顺官方最新估值快照",
            ["stock"],
            "one latest official valuation snapshot row per watchlist stock",
            ["symbol", "as_of"],
            _hithink_valuation_fields(),
            partition_keys=["as_of"],
            point_in_time=False,
            unit_version="hithink_valuation_snapshot_v1",
        ),
        ("reference/hithink_valuation_snapshot",),
        "hithink",
        "hithink_valuation_snapshot",
        "reference",
        time_column="as_of",
        partition_key="as_of",
        required_columns=(
            "symbol",
            "as_of",
            "source",
            "unit_version",
        ),
        unit_policy="reference",
        coverage_policy="on_demand",
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


def _is_ext_data_remainder(definition: DatasetDefinition) -> bool:
    return (
        definition.descriptor.dataset_id == "ext_data"
        and definition.schema_policy == "opaque_dynamic"
        and definition.roots == ("ext_data",)
    )


def _is_ext_data_directory_item(definition: DatasetDefinition) -> bool:
    if definition.descriptor.dataset_id == "ext_data":
        return False
    return all(
        root.startswith("ext_data/") and root.count("/") == 1 for root in definition.roots
    )


def _allows_ext_data_remainder_share(
    left: DatasetDefinition,
    right: DatasetDefinition,
) -> bool:
    return (
        _is_ext_data_remainder(left) and _is_ext_data_directory_item(right)
    ) or (_is_ext_data_remainder(right) and _is_ext_data_directory_item(left))


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
                if _roots_overlap(root, existing_root) and not (
                    _allows_depth5_share(root, existing_root, definition, existing)
                    or _allows_ext_data_remainder_share(definition, existing)
                ):
                    raise ValueError(f"root overlap is not allowed: {root}")
            roots[root] = definition


def get_dataset_definition(dataset_id: str) -> DatasetDefinition:
    for definition in DATASET_DEFINITIONS:
        if definition.descriptor.dataset_id == dataset_id:
            return definition
    raise KeyError(f"unknown dataset_id: {dataset_id}")


validate_dataset_definitions(DATASET_DEFINITIONS)
