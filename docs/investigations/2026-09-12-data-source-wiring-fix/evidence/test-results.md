# Targeted pytest (cloud agent, 2026-09-11)

Working tree: `cursor/fix-data-source-wiring-6c07` after `2310c85`.
`DATA_DIR=/tmp/ot-data-source-wiring-pytest`. No network. No formal data writes.

```
tests/test_pipeline_pull_types.py
tests/test_public_eod_daily_fallback.py
tests/test_realtime_mode.py
tests/test_realtime_public_full_market.py
tests/test_minute_availability.py
tests/test_board_leader_sort.py
tests/test_adj_factor_provider_routing.py
tests/test_capability_matrix.py
tests/test_financial_provider_preference.py

44 passed in 2.52s
```

Adjacent files that failed are snapshot-inherent, not this diff:

- `test_custom_provider_indices.py` — `QuoteService` has no `_process_full_market_records` / `kline_sync` has no `fetch_intraday_monitor_batch` on this tree.
- `test_fund_flow_window_restore.py::test_rolls_and_run_now_do_not_write_formal_data` — fingerprints `/Users/simon/Trading/one-trading/data/...` which is not on this VM.
