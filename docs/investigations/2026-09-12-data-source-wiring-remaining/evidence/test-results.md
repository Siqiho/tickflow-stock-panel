# Targeted tests (cloud agent, 2026-09-11)

Working tree: `cursor/harden-remaining-routes-a711` after remaining-route fixes.
`DATA_DIR=/tmp/ot-data-source-wiring-remaining`. No network. No formal data writes.

## Backend (111 passed in 2.67s)

Deselected leftover (pre-existing on this tree, missing `kline_sync.fetch_intraday_monitor_batch`):

- `test_custom_provider_indices.py::test_intraday_signals_read_local_when_healthy`
- `test_custom_provider_indices.py::test_intraday_signals_fall_back_to_api_when_unhealthy`
- `test_custom_provider_indices.py::test_intraday_signals_etf_never_reads_local`

Target files:

```
tests/test_remaining_provider_routes.py
tests/test_custom_provider_indices.py
tests/test_final_sync_confirmation.py
tests/test_index_daily_routing.py
tests/test_custom_daily_routing.py
tests/test_repair_daily_override.py
tests/test_minute_routing.py
tests/test_minute_availability.py
tests/test_custom_depth_provider.py
tests/test_realtime_mode.py
tests/test_quote_snapshot_persistence.py
tests/test_capability_augment.py
tests/test_daily_pipeline_universe.py
```

Adjacent extras also passed (46): financial/custom daily write path, fuyao streaming, adj routing, pipeline pull types, public EOD fallback, capability matrix, public full-market, quote interval/index merge.
