# Targeted tests (cloud agent, 2026-09-11)

Working tree: `cursor/harden-leftover-routes-cce3` after leftover-route fixes.
`DATA_DIR=/tmp/ot-data-source-wiring-leftover`. No network. No formal data writes.

## Backend (163 passed in 3.33s)

Target files:

```
tests/test_leftover_route_hardening.py
tests/test_intraday_monitor_signals.py
tests/test_custom_provider_indices.py
tests/test_remaining_provider_routes.py
tests/test_adj_factor_provider_routing.py
tests/test_realtime_mode.py
tests/test_minute_availability.py
tests/test_minute_routing.py
tests/test_custom_daily_routing.py
tests/test_index_daily_routing.py
tests/test_financial_custom_routing.py
tests/test_custom_depth_provider.py
tests/test_capability_augment.py
tests/test_quote_snapshot_persistence.py
tests/test_realtime_public_full_market.py
tests/test_kline_detail_transport.py
tests/test_repair_daily_override.py
tests/test_capability_matrix.py
```

Previously deselected `test_custom_provider_indices` intraday-signal cases and
`test_intraday_monitor_signals` collection now run: `fetch_intraday_monitor_batch`
and `_inject_intraday_signals` are present. Entitled TickFlow minute fallback
(`test_kline_detail_transport`) still passes. Leftover TickFlow + free realtime
stays `mode=none`.

Not in this gate (pre-existing leftover, not this round's routing contract):
`test_monitor_index.py` index-rule / empty-stock evaluate-round cases.
