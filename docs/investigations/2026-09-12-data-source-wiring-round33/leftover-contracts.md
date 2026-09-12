# Intentional leftover TickFlow contracts (round 33)

These paths stay TickFlow / public-mix by design. Do not "fail-close" them
in a later hardening round unless product explicitly changes the contract.

| Contract | Where | Why it stays |
| --- | --- | --- |
| After-hours default times | pipeline / scheduler | Ops clock, not a mix-source bug. Leftover TickFlow minute / depth / full-minute / adj / financial / pool / trading-day-probe *jobs* now skip after custom daily |
| Leftover TickFlow + free realtime → `mode=none` | `QuoteService.realtime_mode` | Must not silent-public |
| Leftover TickFlow daily + public realtime overlay | `_quote_overlay_allowed` | Default install (`daily=tickflow`, `realtime=public`); labeled `is_quote_snapshot`. Custom / unresolved daily still refuse |
| Leftover TickFlow still sees untagged-only partitions | daily / minute / instruments / snapshots / adj / financials / enriched | Pre-tag legacy files; same-day untagged extras beside tagged leftover are no longer mixed; unreadable leftovers no longer mint a calendar or fall back to untagged extras. Catalog / get_minute stay fail-loud |
| Explicit `adj=public` / `depth5=public` / `financial=public` / `pool=public` | settings + `/api/free-ext` + corporate-actions `fetch_missing_adj` | User-selected public surface; leftover TickFlow Lab still refuses; leftover TickFlow adj no longer writes public sina |
| User ext extras stay visible beside leftover `part.parquet` | `latest_ext_parquet_files` / `usable_ext_snapshot_files` / ext factor frames | Extras-blind close from earlier rounds; factor snapshot / timeseries now read extras too. Leftover TickFlow `kline_ext` remount still prefers tagged leftover |
| `.env` / auth | settings / secrets | Out of scope for routing hardening |

Closed in this round (not leftovers): in-memory instrument caches no longer leftover-glob untagged extras; leftover-part-only enriched / minute / adj / financial remounts still serve extras-only leftover TickFlow; leftover TickFlow trading-day probe after a custom or unresolved daily; leftover TickFlow corporate-actions `fetch_missing_adj` public sina; unreadable hithink date markers. Catalog / get_minute stay fail-loud.

Round 32 already closed: unreadable tagged leftover no longer falls back to untagged extras in instruments / financials / depth / leftover TickFlow `kline_ext`; leftover TickFlow DuckDB views no longer coalesce-mix untagged extras beside tagged leftover; leftover TickFlow adj / minute-batch / monitor / burst jobs after a custom or unresolved daily; unreadable user-ext date markers.
