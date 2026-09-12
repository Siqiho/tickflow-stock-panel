# Intentional leftover TickFlow contracts (round 31)

These paths stay TickFlow / public-mix by design. Do not "fail-close" them
in a later hardening round unless product explicitly changes the contract.

| Contract | Where | Why it stays |
| --- | --- | --- |
| After-hours default times | pipeline / scheduler | Ops clock, not a mix-source bug. Leftover TickFlow minute / depth / full-minute / adj / financial / pool *jobs* now skip after custom daily |
| Leftover TickFlow + free realtime → `mode=none` | `QuoteService.realtime_mode` | Must not silent-public |
| Leftover TickFlow daily + public realtime overlay | `_quote_overlay_allowed` | Default install (`daily=tickflow`, `realtime=public`); labeled `is_quote_snapshot`. Custom / unresolved daily still refuse |
| Leftover TickFlow still sees untagged-only partitions | daily / minute / instruments / snapshots | Pre-tag legacy files; same-day untagged extras beside tagged leftover are no longer mixed; unreadable leftovers no longer mint a calendar or fall back to untagged extras |
| Explicit `adj=public` / `depth5=public` / `financial=public` / `pool=public` | settings + `/api/free-ext` | User-selected public surface; leftover TickFlow Lab still refuses |
| `.env` / auth | settings / secrets | Out of scope for routing hardening |

Closed in this round (not leftovers): unreadable leftover TickFlow daily / minute probes (calendars / catalog / usable reads stay fail-closed); unreadable tagged leftover no longer falls back to untagged extras; leftover TickFlow `kline_ext` remount / date-range after a custom daily; unreadable leftover `kline_ext` date markers; leftover TickFlow financial / pool jobs after a custom or unresolved daily.

Round 30 already closed: leftover TickFlow single-symbol public / TDX minute; leftover TickFlow minute / depth / full-minute / adj after a custom daily; unreadable leftover TickFlow *calendars* (reads / catalog / get_minute stay fail-loud on direct leftover reads); custom-route DuckDB remount no longer leftover-globs; HTTP ext leftover-glob of `instruments_ext`.
