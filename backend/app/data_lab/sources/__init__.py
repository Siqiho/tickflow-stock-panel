"""Real-source Lab adapters. Network optional; production data_dir never defaulted."""

from .calendar_crosscheck import CalendarCrosscheckConfig, run_calendar_second_source_crosscheck
from .calendar_probe import build_trading_calendar_from_szse, fetch_szse_month_calendar
from .shadow_coverage import (
    build_listing_events_from_instruments,
    build_status_history_shadow,
    compare_calendar_to_kline_partitions,
    summarize_listing_coverage,
    summarize_status_shadow,
)
from .tencent_calendar_probe import fetch_tencent_open_days

__all__ = [
    "CalendarCrosscheckConfig",
    "build_listing_events_from_instruments",
    "build_status_history_shadow",
    "build_trading_calendar_from_szse",
    "compare_calendar_to_kline_partitions",
    "fetch_szse_month_calendar",
    "fetch_tencent_open_days",
    "run_calendar_second_source_crosscheck",
    "summarize_listing_coverage",
    "summarize_status_shadow",
]
