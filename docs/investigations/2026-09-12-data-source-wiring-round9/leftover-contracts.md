# Intentional leftover TickFlow contracts (round 9)

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
| `.env` / auth | settings / secrets | Out of scope for routing hardening |

Closed in this round (not leftovers): stale pool cache, ALL-scope `CN_Equity_A` / DEMO under custom pool, live adj skip when sync already uses sina, minute persist prefs throw, undeclared depth/realtime capability lies, `watchlist.fetch_quotes` ignoring realtime prefs.
