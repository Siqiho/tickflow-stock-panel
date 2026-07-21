# M5 Reference Lab Go/No-Go

- **Time:** 2026-07-21 21:20 CST (approx)
- **Code baseline:** local `main` working tree on top of `e224994`
- **Scope completed this slice:** remote divergence audit + M5.1 protocol library + M5.2 batch-1 schemas/quality + offline Source Lab fixtures/tests
- **Not in scope:** production publish, catalog registry wiring, paid providers, remote merge, deploy

## Evidence

### A. Remote integration track

| Item | Result |
|---|---|
| Read-only fetch | yes (`origin/main` → `0ac6d6f`) |
| Divergence | local ahead **44** / remote ahead **207** |
| Dual-touched files | **105** |
| Blind pull/merge | **NO-GO** |
| Audit doc | `docs/superpowers/reports/2026-07-21-remote-main-divergence-audit.md` |

### B. M5.1 / M5.2 Lab track

| Item | Result |
|---|---|
| Plan | `docs/superpowers/plans/2026-07-21-data-platform-m5-reference-lab.md` |
| Spec | `docs/superpowers/specs/2026-07-21-m5-publish-protocol-and-reference-schemas.md` |
| Code | `backend/app/data_lab/` (`publish_protocol`, `schemas_reference`, `quality_reference`, `fixtures`) |
| Tests | `backend/tests/data_lab/` — **10 passed** |
| Ruff on new files | **0 diagnostics** |
| Production `data/reference` created? | **No** |
| Production `data/.staging` created? | **No** |
| Live ports 3011/3018 switched? | **No** |

### C. Protocol proofs (automated)

| Gate | Status |
|---|---|
| Empty frame refuses publish | PASS |
| Prior formal bytes preserved on empty/conflict/crash | PASS |
| Lineage requires/writes `unit_version` | PASS |
| Idempotent second publish | PASS |
| Calendar / status / listing sample publish in temp dir | PASS |
| Invalid symbol rejected | PASS |
| Duplicate identical PK deduped | PASS |
| Overlap `is_open` flip refused | PASS |

### D. Production data safety

Compared live `data/` to baseline backup tree/manifest:

- No `reference/` or `.staging/` from this work.
- Drift vs M0 baseline backup is **pre-existing operator activity** (extra lineage JSON under `kline_etf_*`, one `job_store` file, log growth) — **not** introduced by M5 Lab code.
- Git porcelain for this slice is only new Lab/docs paths (+ user `output/`).

## Go / No-Go decisions

| Decision | Verdict | Notes |
|---|---|---|
| Continue thematic remote integration branch later | **GO (planned, needs explicit approve to start branch work)** | Do not bulk-merge |
| Formal publish of reference datasets into production `data/` | **NO-GO** | Only offline fixtures proven; no admitted real producer yet |
| Register three datasets into live catalog/workbench | **NO-GO for now** | Wait for real-source Lab sample + rights gate |
| Keep developing Lab adapters / real public calendar probe in isolated DATA_DIR | **GO** | Next engineering step on product track |
| Use status history to replace `filter_halt_days` | **NO-GO** | Consumer switch only after formal data admitted |
| Deploy / push / paid provider | **NO-GO** | Unchanged policy |

## Residual risks / gaps

1. **No real producer admitted.** Fixtures prove protocol mechanics, not exchange calendar truth, halt timelines, or delist completeness (incl. BJ / historical codes).
2. **Source rights still open** for AKShare/BaoStock/exchange pages — dual-doc candidates only.
3. **Instruments snapshot** has `listing_date` but no status/delist history; cannot seed `instrument_status_history` honestly from it alone.
4. **Remote line keeps moving** (`v0.1.86`); integration cost rises with delay.
5. Frontend main `node_modules` still incomplete relative to M4 vitest gate (pre-existing); unrelated to this Lab slice.
6. Catalog `DATASET_DEFINITIONS` not yet extended — intentional to avoid UI implying formal data exists.

## Recommended next actions (in order)

1. **Product Lab:** implement read-only public calendar probe behind isolated DATA_DIR + network-marked tests; compare SH/SZ/(BJ if available) sample vs fixture shape; write producer admission note.
2. **Status/list-delist:** shadow extract from existing instruments + any free delist lists into Lab only; measure coverage holes.
3. **Only after producer Go:** register definitions, workbench cards, optional job entrypoints; still publish to isolated dir first, then explicit prod publish.
4. **Parallel track:** when you approve, open `integrate/origin-main-20260721` and port remote themes starting with security → docker → watchlist OCR → strategy/backtest → shared data files last.

## Claim boundary

- **Code implemented + automated Lab checks passed:** yes.
- **Target runtime / production reference data verified:** no.
- **Full closed-loop M5 batch-1 production admission:** no.
