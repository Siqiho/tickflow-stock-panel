# Intentional leftover TickFlow contracts (round 25)

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

Closed in this round (not leftovers): backtest PanelCache reused leftover TickFlow after a daily switch; public financial depth probe leftover-globbed TickFlow income and picked light mode; catalog missing token (pre-round-23 DBs) kept serving leftover after a custom / unresolved switch; regime batch / enriched warmup omitted row-level leftover filter; DuckDB / screener ext timeseries leftover-unioned every partition; missing ext config fell back to ungated `ext_*` views; RPS dimension map cache ignored daily route; unknown `list_partition_dates` leftover-globbed any table. Leftover TickFlow still sees untagged partitions.
