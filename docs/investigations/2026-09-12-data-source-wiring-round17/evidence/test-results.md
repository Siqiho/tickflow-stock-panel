# Isolated pytest (no network)

Command (from `backend/`, isolated `DATA_DIR`):

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round17 \
  .venv/bin/python -B -m pytest -q \
    tests/test_round_seventeen_route_hardening.py \
    tests/test_round_sixteen_route_hardening.py \
    tests/test_round_fifteen_route_hardening.py \
    tests/test_round_fourteen_route_hardening.py \
    tests/test_round_thirteen_route_hardening.py \
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
    tests/free_sources/test_adj_factor_public.py \
    tests/free_sources/test_financials_public.py \
    tests/test_financial_pit_e6.py \
    tests/test_corporate_actions_sync.py \
    tests/free_sources/test_share_capital_public.py \
    tests/test_adj_public_no_event.py \
    tests/test_quote_index_merge.py \
    tests/test_reference_derived.py \
    tests/test_enriched_full_rebuild.py \
    tests/test_regime_builder.py \
    tests/free_sources/test_free_ext_api.py \
    tests/test_market_mainline.py \
    tests/test_intraday_overview.py \
    tests/test_enriched_stale_price_partition.py \
    tests/test_data_integrity.py \
    tests/free_sources/test_daily_quality.py \
    tests/test_minute_range_api.py
```

Cloud environment result: pending isolated pytest in this turn.
