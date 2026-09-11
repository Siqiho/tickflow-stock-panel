# Intentional leftover TickFlow contracts (round 12)

These paths stay TickFlow / public-mix by design. Do not "fail-close" them
in a later hardening round unless product explicitly changes the contract.

| Contract | Where | Why it stays |
| --- | --- | --- |
| After-hours default times | pipeline / scheduler | Ops schedule, not a mix-source bug |
| Undeclared daily / minute / full_minute / adj → TickFlow (logged) | `kline_sync` resolvers | First-run / leftover A-share install |
| Leftover TickFlow + no `Cap.ADJ_FACTOR` → public sina qfq | `sync_adj_factor`, live `fetch_adj_factor_single` | Free/none cannot serve factors |
| Leftover TickFlow adj reads may serve `route=public` tags | `adj_cache_usable` | Same leftover sina write path |
| TickFlow default depth empty → public L1 | `depth_service._call_depth_batch` | Sealed-board judgment on leftover |
| Leftover TickFlow depth reads may serve `route=public` tags | `depth_cache_usable` | Same leftover public-L1 write path |
| Leftover TickFlow single-symbol minute → public / watchlist TDX | `fetch_minute_single`, HTTP `/api/kline/minute` | View path when no custom minute |
| Declared minute *call* failure + TickFlow minute cap → TickFlow | `_try_custom_minute` | Entitled fallback after a live call error |
| Leftover TickFlow + free realtime → `mode=none` | `QuoteService.realtime_mode` | Must not silent-public |
| A-share / index / ETF instruments stay TickFlow | `instrument_sync` / index sync | No `instrument_provider`; first-run would collapse to DEMO |
| Lab `/api/free-ext` explicit public writes | `free_ext.py` | Lab is an explicit public write surface |
| Historical daily / enriched partitions until re-sync | `GET /api/kline/daily`, screener disk path | Switching daily source does not rewrite history; live overlay is snapshot-only when daily is custom |
| Quote snapshot overlay on daily HTTP | `_overlay_persisted_quote_candles` | Isolated live asset; labeled `is_quote_snapshot` |
| `.env` / auth | settings / secrets | Out of scope for routing hardening |

Closed in this round (not leftovers): pipeline/extend-history/minute-view refresh undoing DuckDB adj/minute/depth gates, `repo.get_minute` / `get_minute_batch` serving stale minute parquet, minute upsert mixing other-route bars, share-history raw parquet fallback, depth sealed provenance (boot/memory/SQL), ETF adj incremental start / `_load_etf_factors` scanning stale files, full-minute coverage treating stale TickFlow today as fresh.
