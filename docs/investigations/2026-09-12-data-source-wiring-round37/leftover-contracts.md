# Intentional leftover TickFlow contracts (round 37)

These paths stay TickFlow / public-mix by design. Do not "fail-close" them
in a later hardening round unless product explicitly changes the contract.

| Contract | Where | Why it stays |
| --- | --- | --- |
| After-hours default times | pipeline / scheduler | Ops clock, not a mix-source bug. Leftover TickFlow minute / depth / full-minute / adj / financial / pool / trading-day-probe / watchlist-quote / full-market-quote *jobs* now skip after custom daily. FinancialScheduler *lifecycle* already stops. DepthService / QuoteService leftover *loops* now also stop |
| Leftover TickFlow + free realtime → `mode=none` | `QuoteService.realtime_mode` | Must not silent-public. Leftover TickFlow starter+ after custom daily is now also `none` |
| Leftover TickFlow daily + public realtime overlay | `_quote_overlay_allowed` | Default install (`daily=tickflow`, `realtime=public`); labeled `is_quote_snapshot`. Custom / unresolved daily still refuse |
| Leftover TickFlow single-symbol minute → public view | `minute_availability` / `fetch_minute_single` | View path when leftover TickFlow minute has no live TickFlow sync. Full-market leftover TickFlow minute no longer advertised after custom daily |
| Leftover TickFlow still sees untagged-only partitions | daily / minute / instruments / snapshots / adj / financials / enriched / catalog / reference / kline_loader | Pre-tag legacy files; same-day untagged extras beside tagged leftover are no longer mixed; unreadable leftovers no longer mint a calendar or fall back to untagged extras. Catalog / get_minute stay fail-loud. Catalog *instruments coverage* no longer leftover-serves after custom daily |
| Explicit `adj=public` / `depth5=public` / `financial=public` / `pool=public` | settings + `/api/free-ext` + corporate-actions `fetch_missing_adj` | User-selected public surface; leftover TickFlow Lab still refuses; leftover TickFlow adj no longer writes public sina |
| User ext extras stay visible beside leftover `part.parquet` | `latest_ext_parquet_files` / `usable_ext_snapshot_files` / ext factor frames / snapshot status / fund-flow HTTP / snapshot remount / snapshot DESCRIBE | Extras-blind close from earlier rounds; snapshot remount / DESCRIBE now skip unreadable extras. Leftover TickFlow `kline_ext` remount still prefers tagged leftover |
| Catalog / `/api/data` storage walks still see leftover files | `scanner.py` / `api/data._compute_storage` | Ops byte counts, not row-level mix. Do not treat as a silent-mix close |
| `.env` / auth | settings / secrets | Out of scope for routing hardening |

Closed in this round (not leftovers): capability labels for adj / depth / quote / minute after a custom or unresolved daily; DepthService leftover TickFlow lifecycle / `_depth_source` after a custom daily; QuoteService leftover TickFlow `realtime_mode` after a custom daily; settings route refresh leftover TickFlow depth / quote loops; leftover TickFlow `_find_universe_id` after a custom or unresolved daily; catalog instruments leftover-serve after a custom daily. Catalog / get_minute stay fail-loud.

Round 36 already closed: FinancialScheduler lifecycle after a custom or unresolved daily; ext remount stale leftover-union on unreadable / parse failure; snapshot DESCRIBE leftover-union of unreadable extras; leftover-part-only share-capital / public financial height fail-open when the gated reader throws; leftover TickFlow `_fetch_instruments_by_type` after a custom or unresolved daily; financial HTTP / capability status Cap.FINANCIAL live-TickFlow label after a custom daily; sector-monitor stamp leftover-glob of unreadable extras.
