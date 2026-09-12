# Intentional leftover TickFlow contracts (round 29)

These paths stay TickFlow / public-mix by design. Do not "fail-close" them
in a later hardening round unless product explicitly changes the contract.

| Contract | Where | Why it stays |
| --- | --- | --- |
| After-hours default times | pipeline / scheduler | Ops clock, not a mix-source bug. TickFlow instrument / index *jobs* now skip after custom daily |
| Leftover TickFlow single-symbol minute → public / watchlist TDX | `fetch_minute_single`, HTTP `/api/kline/minute` | View path when leftover TickFlow minute has no custom source |
| Leftover TickFlow + free realtime → `mode=none` | `QuoteService.realtime_mode` | Must not silent-public |
| Leftover TickFlow still sees untagged-only partitions | daily / minute / instruments / snapshots | Pre-tag legacy files; same-day untagged extras beside tagged leftover are no longer mixed |
| Unreadable leftover TickFlow date markers | daily / minute / snapshot probes | Integrity / catalog / get_minute still fail-loud on corrupt leftover TickFlow |
| Explicit `adj=public` / `depth5=public` | settings + `/api/free-ext` | User-selected public surface; leftover TickFlow Lab now refuses |
| `.env` / auth | settings / secrets | Out of scope for routing hardening |

Closed in this round (not leftovers): remaining leftover TickFlow instrument readers after a custom daily switch (valuation / financial universe / public shares / quality coverage / ext lookup / enriched pipeline / HTTP names); pipeline leftover DuckDB remount; ST-symbol TTL leftover after a switch; Lab shadow leftover `part.parquet` / `extras[0]`; HTTP ext and fund-flow snapshot leftover-part-only reads.

Round 28 already closed: entitled TickFlow minute fallback after a declared custom *call* failure; leftover TickFlow instruments / index / ETF universe after a custom daily switch (sync + universe / DuckDB / mainline / OCR / corporate-actions); quote-snapshot overlay onto custom / unresolved daily; Lab leftover TickFlow public sina; leftover TickFlow concat of untagged extras beside tagged leftover extras.
