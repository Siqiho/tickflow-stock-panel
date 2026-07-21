"""Daily kline quality gate for free-api partitions."""
from __future__ import annotations



from app.services.free_sources.daily_quality import run_daily_quality_check as _run

# Re-export for plan path
run_daily_quality_check = _run

__all__ = ["run_daily_quality_check"]
