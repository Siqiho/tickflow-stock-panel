# Intentional leftover TickFlow contracts (round 30)

These paths stay TickFlow / public-mix by design. Do not "fail-close" them
in a later hardening round unless product explicitly changes the contract.

| Contract | Where | Why it stays |
| --- | --- | --- |
| After-hours default times | pipeline / scheduler | Ops clock, not a mix-source bug. Leftover TickFlow minute / depth / full-minute / adj *jobs* now skip after custom daily |
| Leftover TickFlow + free realtime → `mode=none` | `QuoteService.realtime_mode` | Must not silent-public |
| Leftover TickFlow daily + public realtime overlay | `_quote_overlay_allowed` | Default install (`daily=tickflow`, `realtime=public`); labeled `is_quote_snapshot`. Custom / unresolved daily still refuse |
| Leftover TickFlow still sees untagged-only partitions | daily / minute / instruments / snapshots | Pre-tag legacy files; same-day untagged extras beside tagged leftover are no longer mixed; unreadable leftovers no longer mint a calendar |
| Explicit `adj=public` / `depth5=public` | settings + `/api/free-ext` | User-selected public surface; leftover TickFlow Lab still refuses |
| `.env` / auth | settings / secrets | Out of scope for routing hardening |

Closed in this round (not leftovers): leftover TickFlow single-symbol public / TDX minute; leftover TickFlow minute / depth / full-minute / adj after a custom daily; unreadable leftover TickFlow *calendars* (reads / catalog / get_minute stay fail-loud); custom-route DuckDB remount no longer leftover-globs; HTTP ext leftover-glob of `instruments_ext`.

Round 29 already closed: remaining leftover TickFlow instrument readers after a custom daily switch (valuation / financial universe / public shares / quality coverage / ext lookup / enriched pipeline / HTTP names); pipeline leftover DuckDB remount; ST-symbol TTL leftover after a switch; Lab shadow leftover `part.parquet` / `extras[0]`; HTTP ext and fund-flow snapshot leftover-part-only reads.
