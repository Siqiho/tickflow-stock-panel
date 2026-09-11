# Isolated pytest (no network)

Command (from `backend/`, isolated `DATA_DIR`):

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round12 \
  .venv/bin/python -B -m pytest -q \
    tests/test_round_twelve_route_hardening.py \
    tests/test_round_eleven_route_hardening.py \
    tests/test_round_ten_route_hardening.py \
    tests/test_round_nine_route_hardening.py \
    tests/test_round_eight_route_hardening.py \
    tests/test_round_seven_route_hardening.py \
    tests/test_round_six_route_hardening.py \
    tests/test_intraday_burst_fault_isolation.py \
    tests/test_minute_refresh.py \
    tests/test_leftover_route_hardening.py \
    tests/test_remaining_provider_routes.py \
    tests/test_financial_custom_routing.py \
    tests/test_daily_pipeline_universe.py \
    tests/test_public_eod_daily_fallback.py \
    tests/test_adj_factor_provider_routing.py \
    tests/test_minute_routing.py \
    tests/test_minute_availability.py \
    tests/test_custom_depth_provider.py \
    tests/test_realtime_mode.py \
    tests/test_custom_daily_routing.py \
    tests/test_index_daily_routing.py \
    tests/test_capability_matrix.py \
    tests/test_data_source_write_path.py \
    tests/test_capability_augment.py \
    tests/test_realtime_public_full_market.py \
    tests/test_financial_shares.py \
    tests/test_custom_provider_indices.py \
    tests/test_intraday_monitor_signals.py \
    tests/test_kline_detail_transport.py \
    tests/test_kline_minute_api.py \
    tests/test_quote_snapshot_persistence.py \
    tests/test_universe_scope.py \
    tests/test_universe_scope_csi1800.py \
    tests/free_sources/test_pools_public.py \
    tests/test_capabilities_features.py \
    tests/test_financial_normalize.py \
    tests/free_sources/test_adj_factor_public.py
```

Result: **369 passed**.

No `.env` read. No live network. Formal `DATA_DIR` / user Mac tree not touched.

Round-twelve tests cover pipeline/extend-history/minute-view refresh not undoing adj/minute gates, `repo.get_minute` / `get_minute_batch` rejecting stale TickFlow under custom minute (untagged leftover TickFlow still serves), minute write replacing other-route partitions, share-history fail-closed on gated-reader failure, adj incremental start / ETF factor load ignoring stale custom files, depth sealed provenance (stale TickFlow rejected for custom; leftover public-L1 tags still valid; memory cache dropped after a route switch), full-minute coverage treating stale TickFlow today as missing, and leftover TickFlow contracts (mode=none, undeclared daily, prefs-unreadable persist/overlay block).
