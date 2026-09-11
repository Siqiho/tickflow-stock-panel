# Implementation — 2026-09-12 fund-flow window chain restore

Layer: 数据台续接（概念 H5 roll + `run_now`）+ 用户台可见门槛。Agent 台未动。

State: source restored + focused tests + read-only retained-data match. Not `accepted` / `production`. Chief IAB pending.

## Pre-change inventory

After the 2026-09-10 00:19 restore, current source already had:

- industry `roll_industry_daily_from_h5` with 180s cooperative deadline
- `aggregate_board_window` for board/concept, concept 90% completeness
- calendar-derived industry freshness (`assess_industry_window_freshness`)
- readers for existing formal concept Parquet

Missing versus retained 9/10–9/11 evidence:

- `roll_concept_daily_from_h5`, `.concept_daily_roll.lock`, 720s budget, stable-code `ok`
- `run_now` industry-then-concept isolation / `concept_fund_flow_daily`
- frontend kind-specific max: board 126 / concept 63 (source still used a shared 63)

Formal data already present and left unread-write: industry H5 max `2026-09-10` 128/128; concept H5 max `2026-09-10` 504/504; calendar 2007 rows `2025-01-01`–`2026-10-31` covering 2026-09-12. Calendar freshness helpers matched historical contract; no calendar patch.

## Backup

`/Users/simon/备份/codex/20260912-015545-fund-flow-window-chain-restore-before`

README lists each absolute original path, SHA-256, and timestamp. No `.env`, accounts, formal data, or secrets copied.

## Behavior restored

- Concept roll reuses the industry H5 path with `kind=concept`: snapshot universe, `h5_only=True`, filter `eastmoney_fflow_day`, `atomic=True` merge into `ext_fund_flow_concept_daily`.
- Independent thread lock + file lock. Industry lock/180s unchanged.
- Concept `ok` uses codes that already had the previous local max date (stable universe). New themes do not block.
- `run_now` emits industry then concept, then done. Industry timeout/failure still runs concept. Either roll error does not flip `quality` / `daily_days`.
- `request_industry_roll_cancel` also sets the concept cancel event so existing `cancel_job` (pipeline.py unchanged) stops both. `request_concept_roll_cancel` remains independent.
- Frontend: `BOARD_WINDOW_MAX_DAYS = { board: 126, concept: 63 }`. Industry 126 fetches the window API. Industry 250 and concept 126/250 never request. Incomplete windows stay on the daily snapshot with the existing insufficient-history line.

## Scheduler / real continuation boundary

- `start_scheduler` / cron registration / default 15:30 timing not edited.
- Real roll, real pipeline, and scheduler fire were not run.
- Historic 2026-09-10 15:30 job `f7864b8bdd` (industry+concept both to 9/10) is reference only and was **not reverified** after this restore.
- Scheduler firing and real continuation stay unverified. Do not claim production.

## Checks

See `evidence/test-results.md`. Backend 36 passed (exit 0). Frontend 15 passed (exit 0). Verifier `all_match=true` (exit 0).

## Limits

- `pipeline.py` not in write scope; cancel wiring uses `request_industry_roll_cancel` setting both events.
- No tsc/vite/browser/IAB this turn.
- No network, no backfill, no official `DATA_DIR` writes.
- Dashboard overview / Starter+ / factors / deployment excluded.
