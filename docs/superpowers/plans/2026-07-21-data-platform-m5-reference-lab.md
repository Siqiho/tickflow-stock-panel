# one-trading Data Platform M5 Reference Lab Plan

> **Mode:** Source Lab first. Isolated `DATA_DIR` only. No real `data/` publish, no paid provider, no remote merge, no deploy.

**Goal:** Establish the universal sync→publish protocol (M5.1) and prove batch-1 reference datasets (M5.2) with schema, unit, coverage, and fail-closed publish semantics before any formal write.

## Non-goals (this slice)

- Merge/rebase with `origin/main`
- Write or scan production `/Users/simon/Trading/one-trading/data`
- Enable TickFlow paid entitlements
- Backfill long daily history / financials / adj factors (later M5 batches)
- Migrate old `job_store/*.json`
- Auto-delete under storage limits

## Current baseline facts

- Local `main @ e224994` already has M0–M4 catalog/control plane/workbench.
- Instruments snapshot has `listing_date` but **no** `status` / `delist_date` history.
- Halt handling today is **bar-heuristic** (`filter_halt_days` on open/high==0), not a first-class status timeline.
- Trading calendar is **not** a formal dataset; trading-hours checks are hardcoded wall-clock helpers.
- Dual-doc index already marks calendar + listing/delisting as P0/P1 gaps; calendar must not be inferred from K-line presence.

## Delivery slices

### Slice A — Docs + contracts (this commit series)

1. Remote divergence audit (separate report).
2. This plan.
3. Spec: M5.1 publish protocol + batch-1 schemas/quality gates.

### Slice B — Protocol library (code, Lab-safe)

Implement under `backend/app/data_lab/`:

- `publish_protocol.py` — staging root, normalize hooks, PK dedupe, quality report, overlap compare, atomic publish, lineage, catalog artifact hooks, staging cleanup, empty-refuse, failure keeps last healthy.
- `schemas_reference.py` — canonical schemas + unit versions for:
  - `trading_calendar`
  - `instrument_status_history`
  - `listing_delisting_events`
- `quality_reference.py` — dataset-specific gates.
- Tests in `backend/tests/data_lab/` using tmp paths only.

### Slice C — Source Lab adapters (read-only samples)

- Deterministic fixture provider first (offline, CI-safe).
- Optional public calendar probe behind explicit flag / network tests (not required for unit green).
- Candidate producers (from dual docs, not yet admitted):
  - Exchange public calendars / AKShare trade calendar protocol intelligence
  - BaoStock / TickFlow instruments for list-delist shadows
  - Local instruments snapshot only as **seed**, never sole truth for delist history

### Slice D — Go/No-Go report

Produce `docs/superpowers/reports/2026-07-21-m5-reference-lab-go-no-go.md` with:

- schema/unit coverage results
- empty-overwrite protection proof
- overlap/idempotent publish proof
- source rights residual risks
- formal publish recommendation

## Dataset order (batch 1 only)

| # | dataset_id | Path (formal, later) | PK | First consumers |
|---|---|---|---|---|
| 1 | `trading_calendar` | `data/reference/trading_calendar/` | `exchange + trade_date` | backtest sessions, expected coverage |
| 2 | `instrument_status_history` | `data/reference/instrument_status_history/` | `symbol + effective_from + status` | halt/missing-day distinction |
| 3 | `listing_delisting_events` | `data/reference/listing_delisting_events/` | `symbol + event_type + event_date` | universe, delisted history |

## Acceptance for this Lab slice

- [x] Protocol refuses empty publish and preserves prior healthy artifact
- [x] Atomic replace via temp + `os.replace`
- [x] Lineage requires `unit_version`
- [x] Reference schemas enforce PK uniqueness and required enums
- [x] All tests use isolated temp dirs
- [x] No modification to production `data/` fingerprint
- [ ] Catalog definitions may be prepared, but formal registry publish to live catalog is optional and off by default until Go

## Follow-on (not this slice)

- Register three datasets into `DATASET_DEFINITIONS` + workbench cards after Go
- Wire provider jobs + schedule
- M5 batch 2 long daily history
- Remote integration branch work (independent track)


## Slice C/D execution note (2026-07-21)

- Real-source Lab executed against SZSE public calendar + local read-only shadows.
- Isolated lab_dir example: `/tmp/one-trading-m5-ref-lab-dWIXGI`
- Go/No-Go: `docs/superpowers/reports/2026-07-21-m5-reference-source-lab-go-no-go.md`
- Production publish remains **NO-GO**.
