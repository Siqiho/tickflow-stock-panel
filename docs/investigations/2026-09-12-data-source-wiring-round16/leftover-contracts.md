# Intentional leftover TickFlow contracts (round 16)

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
| Explicit `adj=public` / `depth5=public` / Lab leftover TickFlow | settings + `/api/free-ext` | User-selected public surface; custom/unresolved now refuse |
| `.env` / auth | settings / secrets | Out of scope for routing hardening |

Closed in this round (not leftovers): undeclared custom daily/minute/full_minute/adj → TickFlow, leftover TickFlow silent sina qfq (sync/live/read/write/labels), leftover TickFlow empty → public L1 (fetch/read/labels), Lab `/api/free-ext` public fetch/write after a custom or unresolved route switch, historical HTTP / screener / chips / overview reads of leftover daily/enriched until re-sync.
