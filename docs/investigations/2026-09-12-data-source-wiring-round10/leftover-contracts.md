# Intentional leftover TickFlow contracts (round 10)

These paths stay TickFlow / public-mix by design. Do not "fail-close" them
in a later hardening round unless product explicitly changes the contract.

| Contract | Where | Why it stays |
| --- | --- | --- |
| After-hours default times | pipeline / scheduler | Ops schedule, not a mix-source bug |
| Undeclared daily / minute / full_minute / adj → TickFlow (logged) | `kline_sync` resolvers | First-run / leftover A-share install |
| Leftover TickFlow + no `Cap.ADJ_FACTOR` → public sina qfq | `sync_adj_factor`, live `fetch_adj_factor_single` | Free/none cannot serve factors |
| TickFlow default depth empty → public L1 | `depth_service._call_depth_batch` | Sealed-board judgment on leftover |
| Leftover TickFlow single-symbol minute → public / watchlist TDX | `fetch_minute_single`, HTTP `/api/kline/minute` | View path when no custom minute |
| Declared minute *call* failure + TickFlow minute cap → TickFlow | `_try_custom_minute` | Entitled fallback after a live call error |
| Leftover TickFlow + free realtime → `mode=none` | `QuoteService.realtime_mode` | Must not silent-public |
| A-share / index / ETF instruments stay TickFlow | `instrument_sync` / index sync | No `instrument_provider`; first-run would collapse to DEMO |
| Lab `/api/free-ext` explicit public writes | `free_ext.py` | Lab is an explicit public write surface |
| Historical daily / enriched partitions until re-sync | `GET /api/kline/daily`, screener | Switching daily source does not rewrite history; live overlay is snapshot-only when daily is custom |
| DuckDB financial views still scan raw parquet | `repository` view refresh | `get_financial_df` is gated; SQL views are a later catalog change |
| `.env` / auth | settings / secrets | Out of scope for routing hardening |

Closed in this round (not leftovers): TickFlow/custom realtime writing canonical `kline_daily` under custom daily, `sync_daily_by_quotes` bypass of the pipeline gate, stale minute parquet after `minute_data_provider` switch, monitor full_minute → `minute_data_provider` TickFlow mix, public adj `or pipeline_universe` widen, depth `_has_capability` always-true, stale financial parquet after `financial_provider` switch.
