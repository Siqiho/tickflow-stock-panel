# Targeted tests (cloud agent, 2026-09-11)

Working tree: `cursor/harden-provider-routing-4003` after the provider-routing commit.
`DATA_DIR=/tmp/ot-data-source-wiring-providers`. No network. No formal data writes.

## Backend (71 passed in 3.34s)

```
tests/test_index_daily_routing.py
tests/test_financial_custom_routing.py
tests/test_data_source_write_path.py
tests/test_custom_daily_routing.py
tests/test_fuyao_daily_streaming_sync.py
tests/test_adj_factor_provider_routing.py
tests/test_pipeline_pull_types.py
tests/test_public_eod_daily_fallback.py
tests/test_realtime_mode.py
tests/test_capability_matrix.py
tests/test_capability_augment.py
tests/test_minute_availability.py
tests/test_financial_provider_preference.py
```

Adjacent extras also passed (10): `test_realtime_public_full_market.py`, `test_board_leader_sort.py`, `test_capabilities_features.py`, `test_custom_depth_provider.py`.

## Frontend (44 passed in 5.69s)

```
src/lib/dataSources.test.ts
src/lib/dataSourceCatalog.test.ts
src/pages/__tests__/DataUnifiedSources.test.tsx
src/pages/__tests__/Data.test.tsx
```
