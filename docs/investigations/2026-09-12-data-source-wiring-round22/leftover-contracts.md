# Intentional leftover TickFlow contracts (round 22)

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

Closed in this round (not leftovers): official trend overlay cache reused leftover TickFlow after a daily switch; HTTP minute-range / get_minute scanned the stock minute store for ETF symbols; DuckDB refresh helpers created leftover-visible raw globs before re-gate; legacy symbol-partition minute migration republished leftover TickFlow as untagged date files; stale `depth5` leftover shadowed current-route `sealed_l1`; shares append / historical-shares cache fail-opened on prefs throw or financial switch; regime history cache reused leftover after a daily switch; derived calendars leftover-globbed index / ETF / minute tables. Leftover TickFlow still sees untagged partitions.
