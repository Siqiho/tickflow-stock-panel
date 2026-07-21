# M5.1 Publish Protocol + M5.2 Batch-1 Reference Schemas

**Status:** Lab contract  
**Date:** 2026-07-21  
**Baseline commit:** `e224994`

## M5.1 Universal sync → publish protocol

Every new dataset run executes exactly this pipeline. Lab and future production share the same code path; only the `data_dir` root differs.

```text
fetch → staging → normalize → dedupe → quality gates
     → overlap compare → atomic publish → lineage + artifacts
     → catalog state (optional) → cleanup staging
```

### Directory layout

```text
<data_dir>/.staging/<dataset_id>/<run_id>/
  raw/                     # optional opaque fetch payload
  normalized.parquet       # canonical frame candidate
  quality_report.json      # gate results
  meta.json                # run metadata
<data_dir>/<formal roots>/ # only after gates pass
<data_dir>/lineage/<dataset_id>/date=<as_of>/<run_id>.json
```

Notes:

- Staging root is `<data_dir>/.staging/...` (hidden), distinct from custom-provider `data/staging/custom` which remains staging-only with no auto-promote.
- Formal publish never reads production paths for write targets other than the dataset’s owned roots.

### Hard rules

1. **Empty must not overwrite.** If normalized row count is 0, abort before touching formal files.
2. **Failure keeps last healthy data.** Any exception after staging write leaves formal artifacts unchanged.
3. **Atomic publish.** Write to `*.tmp-<uuid>` then `os.replace` onto the formal path (reuse `atomic_write_parquet` / `atomic_write_json`).
4. **Primary-key dedupe.** Keep last by sort keys; duplicate PK after dedupe is a hard fail.
5. **Unit version required.** Lineage write fails closed without non-empty `unit_version`.
6. **Overlap compare.** When prior formal data exists, compare intersection on PK:
   - calendar: `is_open` disagreements are hard fail unless `allow_status_flip` explicitly set for Lab shadow
   - status history: conflicting overlapping intervals hard fail
   - listing events: same PK different payload hard fail
7. **Quality report persisted** even on failure (in staging) for operator debugging.
8. **Staging cleanup** only after successful publish + lineage write. Failed runs retain staging for inspection.
9. **No second source of truth.** Do not infer trading days solely from existing K-line partitions.
10. **Lab default sink** is isolated temp/DATA_DIR; production sink requires explicit operator approval outside this contract.

### Quality report shape

```json
{
  "dataset_id": "trading_calendar",
  "run_id": "...",
  "row_count": 0,
  "passed": false,
  "checks": [
    {"code": "not_empty", "passed": false, "detail": "0 rows"}
  ],
  "overlap": {"prior_rows": 0, "intersection": 0, "conflicts": 0},
  "unit_version": "trading_calendar_v1"
}
```

### Publish result shape

```json
{
  "ok": true,
  "dataset_id": "trading_calendar",
  "run_id": "...",
  "published_path": "...",
  "row_count": 123,
  "quality_report_path": "...",
  "lineage_path": "...",
  "kept_prior": false
}
```

On refusal/failure: `ok=false`, `kept_prior=true` when formal data existed.

## M5.2 Batch-1 schemas

Common conventions:

- Dates are ISO `YYYY-MM-DD` stored as Date (Polars) / string in JSON sidecars.
- Timestamps in lineage are timezone-aware ISO local/offset strings.
- `source` is the producer id (e.g. `lab_fixture`, `public_exchange_calendar`, `tickflow_instruments`).
- `as_of` is the observation/publish date of the run, not the event date.

### 1) `trading_calendar`

**Owned root:** `reference/trading_calendar/`  
**Formal file (v1):** `reference/trading_calendar/calendar.parquet`  
**unit_version:** `trading_calendar_v1`  
**grain:** one row per exchange and calendar date  
**primary key:** `exchange + trade_date`

| field | dtype | null | semantic |
|---|---|---|---|
| exchange | string | no | `SH` / `SZ` / `BJ` / `SSE` alias normalized to SH/SZ/BJ; use `XSHG`→SH, `XSHE`→SZ, `BSE`→BJ |
| trade_date | date | no | calendar date |
| is_open | bool | no | whether the exchange session is open for continuous auction products |
| session_type | string | no | `normal` \| `half_day` \| `closed` \| `holiday` \| `special` |
| open_time | string | yes | local `HH:MM` session open if open |
| close_time | string | yes | local `HH:MM` session close if open |
| source | string | no | producer id |
| as_of | date | no | run observation date |

**Gates:**

- not empty
- PK unique 100%
- `exchange` ∈ {SH,SZ,BJ}
- `session_type` enum valid
- if `is_open` then `session_type` ∈ {normal, half_day, special} and times present
- if not `is_open` then `session_type` ∈ {closed, holiday, special}
- date range contiguous check is **soft** (warn) because special closures may exist; missing weekends are expected only if rows are trading-day-only — v1 stores **all dates or trading days explicitly via `is_open`**; Lab fixture uses full date range with weekend `is_open=false`

### 2) `instrument_status_history`

**Owned root:** `reference/instrument_status_history/`  
**Formal file (v1):** `reference/instrument_status_history/status_history.parquet`  
**unit_version:** `instrument_status_history_v1`  
**grain:** one row per symbol status interval start  
**primary key:** `symbol + effective_from + status`

| field | dtype | null | semantic |
|---|---|---|---|
| symbol | string | no | canonical `NNNNNN.SH/SZ/BJ` |
| status | string | no | `trading` \| `suspended` \| `st` \| `star_st` \| `delisted` \| `unknown` |
| effective_from | date | no | inclusive start |
| effective_to | date | yes | exclusive end; null = open-ended |
| reason | string | yes | free text / code |
| source | string | no | producer id |
| as_of | date | no | observation date |

**Gates:**

- not empty (for full-market publish); Lab sample may be small but >0
- PK unique
- `effective_to` is null or `>= effective_from`
- no overlapping intervals for same symbol with conflicting status (hard)
- symbol pattern `[0-9]{6}\.(SH|SZ|BJ)`

### 3) `listing_delisting_events`

**Owned root:** `reference/listing_delisting_events/`  
**Formal file (v1):** `reference/listing_delisting_events/events.parquet`  
**unit_version:** `listing_delisting_events_v1`  
**grain:** one row per corporate listing lifecycle event  
**primary key:** `symbol + event_type + event_date`

| field | dtype | null | semantic |
|---|---|---|---|
| symbol | string | no | canonical symbol |
| event_type | string | no | `list` \| `delist` \| `relist` \| `code_change` |
| event_date | date | no | effective event date |
| name | string | yes | name at event |
| exchange | string | yes | SH/SZ/BJ |
| prior_symbol | string | yes | for `code_change` |
| source | string | no | producer id |
| as_of | date | no | observation date |

**Gates:**

- not empty for formal full publish
- PK unique
- `event_type` enum
- `list` events should not have `prior_symbol`; `code_change` should
- symbol pattern valid

## Relationship to existing systems

| Existing piece | Relationship |
|---|---|
| `atomic_io.atomic_write_parquet` | Used for formal publish |
| `atomic_io.write_lineage_record` | Used after successful publish |
| `data_catalog` scanner/definitions | Later registration; Lab can write formal files under isolated dir without live registry |
| `filter_halt_days` | Remains bar heuristic until status history is admitted; must not be deleted in this slice |
| instruments snapshot `listing_date` | Seed only; does not replace `listing_delisting_events` |
| custom `staging/custom` | Unrelated promote policy; do not auto-promote custom staging via M5.1 |

## Test matrix (Lab)

1. empty frame → publish refused, prior intact
2. valid calendar → published, lineage has unit_version
3. duplicate PK → refused
4. overlap conflict → refused, prior intact
5. second identical publish → idempotent row count, success
6. crash before replace (simulated) → prior intact, staging retained

## Explicit non-claims

Passing Lab tests does **not** mean:

- production reference data exists
- workbench shows the three datasets
- halt filters now use status history
- remote main integration is done
