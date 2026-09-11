# Intentional leftover TickFlow contracts (round 21)

These paths stay TickFlow / public-mix by design. Do not "fail-close" them
in a later hardening round unless product explicitly changes the contract.

| Contract | Where | Why it stays |
| --- | --- | --- |
| After-hours default times | pipeline / scheduler | Ops schedule, not a mix-source bug |
| Declared minute *call* failure + TickFlow minute cap → TickFlow | `_try_custom_minute` | Entitled fallback after a live call error |
| Leftover TickFlow single-symbol minute → public / watchlist TDX | `fetch_minute_single`, HTTP `/api/kline/minute` | View path when no custom minute |
| Leftover TickFlow + free realtime → `mode=none` | `QuoteService.realtime_mode` | Must not silent-public |
| A-share / index / ETF instruments stay TickFlow | `instrument_sync` / index sync | No `instrument_provider`; first-run would collapse to DEMO |
| Quote snapshot overlay on daily HTTP | `_overlay_persisted_quote_candles` | Isolated live asset; labeled `is_quote_snapshot` |
| Explicit `adj=public` / `depth5=public` / Lab leftover TickFlow | settings + `/api/free-ext` | User-selected public surface; custom/unresolved still refuse |
| `.env` / auth | settings / secrets | Out of scope for routing hardening |

Closed in this round (not leftovers): leftover minute schema poison on repo/HTTP scans; live enriched full-rebuild leftover glob; index benchmark leftover glob + route-blind cache; overview / SSE index DuckDB leftover quotes; minute null-datetime leftover wipe; live publish / daily write resolve throw; adj status leftover SQL row counts; abnormal / RPS / overview process caches missing daily route; HTTP minute-range leftover getter / index stock-store mix; single-symbol minute persist leaving leftover DuckDB view; UTC/Shanghai dirty index today stacked into bench momentum; live index-quote cache reused after a realtime-provider switch. Leftover TickFlow still sees untagged partitions.
