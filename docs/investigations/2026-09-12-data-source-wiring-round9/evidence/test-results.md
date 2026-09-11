# Isolated pytest (no network)

Command (from `backend/`, isolated `DATA_DIR`):

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round9 \
  .venv/bin/python -B -m pytest -q \
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
    tests/test_universe_scope.py \
    tests/test_universe_scope_csi1800.py \
    tests/free_sources/test_pools_public.py \
    tests/test_capabilities_features.py
```

Result: **305 passed**.

No `.env` read. No live network. Formal `DATA_DIR` / user Mac tree not touched.

Round-nine tests cover daily/minute/quote prefs fail-closed, watchlist TDX leftover vs declared-custom skip, custom financial scope, pool apply-source / dedicated PUT / delete, stale pool cache provenance, custom pool `get_constituents`, ALL-scope and pipeline/extend-history DEMO fail-closed under custom pool, live adj leftover+no-cap public sina parity, minute persist/monitor prefs fail-closed, undeclared depth/realtime capability labels, `watchlist.fetch_quotes` TickFlow-only, and leftover TickFlow contracts (mode=none, undeclared daily, entitled TickFlow adj).
