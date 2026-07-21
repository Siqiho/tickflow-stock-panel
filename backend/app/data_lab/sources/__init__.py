"""Real-source Lab adapters. Network optional; production data_dir never defaulted."""
from .calendar_probe import build_trading_calendar_from_szse, fetch_szse_month_calendar
from .shadow_coverage import (
    build_listing_events_from_instruments,
    build_status_history_shadow,
    compare_calendar_to_kline_partitions,
    summarize_listing_coverage,
    summarize_status_shadow,
)

__all__ = [
    "build_listing_events_from_instruments",
    "build_status_history_shadow",
    "build_trading_calendar_from_szse",
    "compare_calendar_to_kline_partitions",
    "fetch_szse_month_calendar",
    "summarize_listing_coverage",
    "summarize_status_shadow",
]
