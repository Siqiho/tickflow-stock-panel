# Isolated pytest (no network)

Command (from `backend/`, isolated `DATA_DIR`):

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round6 \
  .venv/bin/python -B -m pytest -q \
    tests/test_round_six_route_hardening.py \
    tests/test_intraday_burst_fault_isolation.py \
    tests/test_minute_refresh.py \
    tests/test_leftover_route_hardening.py \
    tests/test_remaining_provider_routes.py \
    tests/test_public_eod_daily_fallback.py \
    tests/test_adj_factor_provider_routing.py \
    tests/test_minute_routing.py \
    tests/test_minute_availability.py \
    tests/test_custom_depth_provider.py \
    tests/test_realtime_mode.py \
    tests/test_kline_detail_transport.py \
    tests/test_custom_daily_routing.py \
    tests/test_index_daily_routing.py \
    tests/test_custom_provider_indices.py \
    tests/test_intraday_monitor_signals.py \
    tests/test_capability_augment.py \
    tests/test_capability_matrix.py
```

Result: **195 passed**.

No `.env` read. No live network. Formal `DATA_DIR` / user Mac tree not touched.

`test_intraday_burst_fault_isolation` now collects (full-minute burst boundary restored). Minute-refresh tests write server prefs (`save_server` / `set_minute_refresh`) so they match the leftover TickFlow contracts on this tree.
