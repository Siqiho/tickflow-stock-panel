"""Canonical schemas for M5 batch-1 reference datasets."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl


@dataclass(frozen=True)
class ReferenceDatasetSchema:
    dataset_id: str
    unit_version: str
    owned_root: str
    formal_relpath: str
    primary_key: tuple[str, ...]
    required_columns: tuple[str, ...]
    dtypes: dict[str, pl.DataType]
    enums: dict[str, frozenset[str]]


def _calendar_schema() -> ReferenceDatasetSchema:
    return ReferenceDatasetSchema(
        dataset_id="trading_calendar",
        unit_version="trading_calendar_v1",
        owned_root="reference/trading_calendar",
        formal_relpath="reference/trading_calendar/calendar.parquet",
        primary_key=("exchange", "trade_date"),
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
        dtypes={
            "exchange": pl.Utf8,
            "trade_date": pl.Date,
            "is_open": pl.Boolean,
            "session_type": pl.Utf8,
            "open_time": pl.Utf8,
            "close_time": pl.Utf8,
            "source": pl.Utf8,
            "as_of": pl.Date,
        },
        enums={
            "exchange": frozenset({"SH", "SZ", "BJ"}),
            "session_type": frozenset({"normal", "half_day", "closed", "holiday", "special"}),
        },
    )


def _status_schema() -> ReferenceDatasetSchema:
    return ReferenceDatasetSchema(
        dataset_id="instrument_status_history",
        unit_version="instrument_status_history_v1",
        owned_root="reference/instrument_status_history",
        formal_relpath="reference/instrument_status_history/status_history.parquet",
        primary_key=("symbol", "effective_from", "status"),
        required_columns=(
            "symbol",
            "status",
            "effective_from",
            "effective_to",
            "reason",
            "source",
            "as_of",
        ),
        dtypes={
            "symbol": pl.Utf8,
            "status": pl.Utf8,
            "effective_from": pl.Date,
            "effective_to": pl.Date,
            "reason": pl.Utf8,
            "source": pl.Utf8,
            "as_of": pl.Date,
        },
        enums={
            "status": frozenset({"trading", "suspended", "st", "star_st", "delisted", "unknown"}),
        },
    )


def _listing_schema() -> ReferenceDatasetSchema:
    return ReferenceDatasetSchema(
        dataset_id="listing_delisting_events",
        unit_version="listing_delisting_events_v1",
        owned_root="reference/listing_delisting_events",
        formal_relpath="reference/listing_delisting_events/events.parquet",
        primary_key=("symbol", "event_type", "event_date"),
        required_columns=(
            "symbol",
            "event_type",
            "event_date",
            "name",
            "exchange",
            "prior_symbol",
            "source",
            "as_of",
        ),
        dtypes={
            "symbol": pl.Utf8,
            "event_type": pl.Utf8,
            "event_date": pl.Date,
            "name": pl.Utf8,
            "exchange": pl.Utf8,
            "prior_symbol": pl.Utf8,
            "source": pl.Utf8,
            "as_of": pl.Date,
        },
        enums={
            "event_type": frozenset({"list", "delist", "relist", "code_change"}),
            "exchange": frozenset({"SH", "SZ", "BJ"}),
        },
    )


def _corporate_actions_schema() -> ReferenceDatasetSchema:
    """移植自 7019d03; unit_version 对齐现有物理行的 corporate_actions_v2。"""
    return ReferenceDatasetSchema(
        dataset_id="corporate_actions",
        unit_version="corporate_actions_v2",
        owned_root="reference/corporate_actions",
        formal_relpath="reference/corporate_actions/actions.parquet",
        primary_key=("symbol", "action_id"),
        required_columns=(
            "symbol",
            "action_id",
            "action_type",
            "announce_date",
            "record_date",
            "ex_date",
            "pay_date",
            "cash_per_share",
            "stock_ratio",
            "rights_ratio",
            "currency",
            "source_published_at",
            "first_seen_at",
            "source",
            "as_of",
        ),
        dtypes={
            "symbol": pl.Utf8,
            "action_id": pl.Utf8,
            "action_type": pl.Utf8,
            "announce_date": pl.Date,
            "record_date": pl.Date,
            "ex_date": pl.Date,
            "pay_date": pl.Date,
            "cash_per_share": pl.Float64,
            "stock_ratio": pl.Float64,
            "rights_ratio": pl.Float64,
            "currency": pl.Utf8,
            "source_published_at": pl.Datetime(time_unit="us"),
            "first_seen_at": pl.Datetime(time_unit="us"),
            "source": pl.Utf8,
            "as_of": pl.Date,
        },
        enums={
            "action_type": frozenset(
                {
                    "dividend_cash",
                    "dividend_stock",
                    "split",
                    "reverse_split",
                    "rights_issue",
                    "bonus",
                    "mixed",
                    "unknown",
                    "identity_marker",
                }
            ),
            "currency": frozenset({"CNY", "unknown"}),
        },
    )


TRADING_CALENDAR_SCHEMA = _calendar_schema()
INSTRUMENT_STATUS_HISTORY_SCHEMA = _status_schema()
LISTING_DELISTING_EVENTS_SCHEMA = _listing_schema()
CORPORATE_ACTIONS_SCHEMA = _corporate_actions_schema()

REFERENCE_DATASETS: dict[str, ReferenceDatasetSchema] = {
    TRADING_CALENDAR_SCHEMA.dataset_id: TRADING_CALENDAR_SCHEMA,
    INSTRUMENT_STATUS_HISTORY_SCHEMA.dataset_id: INSTRUMENT_STATUS_HISTORY_SCHEMA,
    LISTING_DELISTING_EVENTS_SCHEMA.dataset_id: LISTING_DELISTING_EVENTS_SCHEMA,
    CORPORATE_ACTIONS_SCHEMA.dataset_id: CORPORATE_ACTIONS_SCHEMA,
}


def get_reference_schema(dataset_id: str) -> ReferenceDatasetSchema:
    try:
        return REFERENCE_DATASETS[dataset_id]
    except KeyError as exc:
        raise KeyError(f"unknown reference dataset_id: {dataset_id}") from exc
