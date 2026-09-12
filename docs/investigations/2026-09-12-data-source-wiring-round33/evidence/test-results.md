# 三十三轮隔离测试证据

环境：云 agent，`backend/.venv`（`uv sync --extra dev`），不读 `.env`，不写正式 `DATA_DIR`。

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round33 \
  .venv/bin/python -B -m pytest -q --tb=line \
    tests/test_round_thirty_three_route_hardening.py \
    tests/test_round_thirty_two_route_hardening.py \
    tests/test_round_thirty_one_route_hardening.py \
    tests/test_round_thirty_route_hardening.py \
    tests/test_round_twenty_nine_route_hardening.py \
    tests/test_round_twenty_eight_route_hardening.py \
    tests/test_data_integrity.py \
    tests/test_round_twenty_seven_route_hardening.py \
    tests/test_round_twenty_six_route_hardening.py \
    tests/test_round_twenty_five_route_hardening.py \
    tests/test_round_twenty_four_route_hardening.py \
    tests/test_round_twenty_three_route_hardening.py \
    tests/test_round_twenty_two_route_hardening.py \
    tests/test_round_twenty_one_route_hardening.py \
    tests/test_round_twenty_route_hardening.py \
    tests/test_round_nineteen_route_hardening.py \
    tests/test_round_eighteen_route_hardening.py \
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
    tests/test_leftover_route_hardening.py \
    tests/test_quote_snapshot_persistence.py \
    tests/test_kline_daily_quote_overlay.py \
    tests/test_market_snapshot_service.py \
    tests/test_reference_derived.py \
    tests/data_catalog/test_service.py \
    tests/data_catalog/test_scanner.py \
    tests/test_intraday_burst_fault_isolation.py \
    tests/test_minute_refresh.py \
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
    tests/test_capabilities_features.py \
    tests/test_financial_normalize.py \
    tests/free_sources/test_adj_factor_public.py \
    tests/free_sources/test_financials_public.py \
    tests/test_financial_pit_e6.py \
    tests/test_corporate_actions_sync.py \
    tests/free_sources/test_share_capital_public.py \
    tests/test_adj_public_no_event.py \
    tests/test_quote_index_merge.py \
    tests/test_enriched_full_rebuild.py \
    tests/test_regime_builder.py \
    tests/free_sources/test_free_ext_api.py \
    tests/test_market_mainline.py::TestComputeMainline \
    tests/test_intraday_overview.py \
    tests/test_enriched_stale_price_partition.py \
    tests/free_sources/test_daily_quality.py \
    tests/test_rps_rotation_map_cache.py \
    tests/test_market_overview_as_of.py \
    tests/test_auction_benchmark.py \
    tests/test_dragon_tiger.py \
    tests/test_abnormal_moves.py \
    tests/test_kline_read_failure.py \
    tests/test_minute_range_api.py \
    tests/test_engineering_closure.py \
    tests/test_strategy_cache.py \
    tests/test_screener_cache_api.py \
    tests/test_instrument_sync_guard.py \
    tests/test_minute_fallback_gate_http.py \
    tests/data_lab/test_shadow_coverage.py \
    tests/test_financial_p1.py \
    tests/free_sources/test_hithink_finance.py
```

结果：`1069 passed, 47 warnings`（隔离 `DATA_DIR=/tmp/ot-data-source-wiring-round33`）。

Round-thirty-three tests cover in-memory instrument caches no longer leftover-glob mixing untagged extras, leftover-part-only enriched / minute / adj / financial remounts still serving extras-only leftover TickFlow, leftover TickFlow trading-day probe skipping after custom daily, leftover TickFlow corporate-actions no longer writing public sina, user-ext factor extras staying visible, unreadable hithink date markers skipping, leftover TickFlow + free realtime `mode=none`, leftover TickFlow daily + public realtime overlay kept, untagged-only leftover still served, after-hours default clock times unchanged. Catalog / get_minute stay fail-loud on leftover TickFlow.
