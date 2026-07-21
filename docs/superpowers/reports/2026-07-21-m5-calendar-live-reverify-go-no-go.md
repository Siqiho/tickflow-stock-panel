# M5 Trading Calendar Live Re-Verification Go/No-Go

- **Time:** 2026-07-21 22:07–22:08 CST
- **Baseline commits:** `14aeefc` (M5 Lab) + `4a07b4d` (second-source cross-check)
- **Lab root:** `/tmp/one-trading-m5-cal-live-reverify-upD8Xz`
- **Mode:** live SZSE + live Tencent only (no production write, no cache-as-primary)

## Why this re-run

Previous slice hit real network failures:

- SZSE monthList returned empty reply / disconnect
- Official SSE calendar/SOA unusable
- Dual-source long windows fell back to cache or Tencent-only

This pass re-probes connectivity and repeats full-window live dual checks so earlier conclusions are not left distorted by transient outage.

## Connectivity now

| Source | Now | Notes |
|---|---|---|
| SZSE monthList | **Live OK** (HTTP 200, ~70ms on probe) | Full 2025-01..2026-07 pull succeeded |
| Tencent fqkline SH/SZ | **Live OK** | Stable open-day series |
| Official SSE calendar/SOA | **Still unusable** | HTTP 200 but `SOA service is null` |

## Fresh SZSE live pull integrity

- Months requested: 19 (`2025-01` … `2026-07`)
- Missing months: **0**
- Raw day rows: **577**
- Unique calendar days: **577** (`2025-01-01` … `2026-07-31`)
- Open days in that raw month span: **382**
- Compared publish/cross-check end date in this re-run: **2026-07-21**

## Cache vs fresh live (audit of earlier session data)

Prior isolated cache:

`/tmp/one-trading-m5-ref-lab-dWIXGI/reference/trading_calendar/calendar.parquet`

Overlap span `2026-06-01` … `2026-07-31`:

| Metric | Result |
|---|---|
| Live SH open days | 44 |
| Cache SH open days | 44 |
| Equal? | **Yes** |
| only_live / only_cache | **[] / []** |

**Conclusion:** earlier cache was **not corrupted** by the outage. It was a valid snapshot; the problem was live fetch availability, not bad ingested values.

## Live dual-source windows (SZSE live, no cache primary)

| Window | SZSE live | Tencent SH | Tencent SZ | SH==SZ | SZSE==TX SH | Admission |
|---|---:|---:|---:|---|---|---|
| 2025-01-01…2025-12-31 | ok | ok | ok | equal | equal | `LAB_PASS_CANDIDATE_SECOND_SOURCE_OK` |
| 2026-01-01…2026-07-21 | ok | ok | ok | equal | equal | `LAB_PASS_CANDIDATE_SECOND_SOURCE_OK` |
| 2025-01-01…2026-07-21 | ok | ok | ok | equal | equal | `LAB_PASS_CANDIDATE_SECOND_SOURCE_OK` |
| 2026-06-01…2026-07-21 | ok | ok | ok | equal | equal | `LAB_PASS_CANDIDATE_SECOND_SOURCE_OK` |

### Direct full-window open-day counts (`2025-01-01` … `2026-07-21`)

| Series | Open days |
|---|---:|
| SZSE open | **374** |
| Tencent SH (`sh000001`) | **374** |
| Tencent SZ (`sz399001`) | **374** |
| only_szse | **0** |
| only_tx | **0** |

All four cross-check windows: **`ok=true`**.

## Session claim audit

| Earlier claim | After live re-verify |
|---|---|
| SZSE was down / flaky mid-session | **Confirmed real** (now recovered) |
| Prior Jun–Jul dual equality (36 days) | **Confirmed**; cache==fresh live |
| 2025 long-window only Tencent-partial | **Superseded** — live SZSE now available and fully matches |
| Official SSE second source done | **Still false** — SOA null remains |
| Production calendar written | **Still false** — `data/reference` absent |
| Listing/status formalized | **Still false** — not in this re-run scope |

## Go / No-Go (updated)

| Decision | Verdict |
|---|---|
| Trust earlier outage as network, not silent bad writes | **GO** |
| Trust SZSE monthList + Tencent proxy dual-check in Lab | **GO** (stronger than before) |
| Claim official SSE API integrated | **NO** |
| Discuss standalone `trading_calendar` production publish | **YES, with gates** (stronger evidence) |
| Write production `data/reference/trading_calendar` now | **NO_GO** without explicit approval + rights sign-off |
| Register workbench / switch runtime consumers now | **NO_GO** |

### Remaining gates before production publish can flip to GO

1. Explicit user approval to write production `data/`
2. Rights/ToS sign-off for SZSE (primary) and documentation that Tencent is proxy cross-check only
3. Lineage records producer + unit_version + as_of window
4. BJ expansion assumption remains explicit (no independent BJ calendar feed yet)
5. Optional: one more fresh live pull immediately before formal publish

## Safety

- Production `data/reference`: absent
- Production `data/.staging`: absent
- No deploy / no remote merge / no push in this re-verify

## Artifacts

- Machine summary: `docs/superpowers/reports/2026-07-21-m5-calendar-live-reverify-summary.json`
- Full-window detailed report copy: `docs/superpowers/reports/2026-07-21-m5-calendar-live-reverify-2025-2026.json`
- Isolated lab root: `/tmp/one-trading-m5-cal-live-reverify-upD8Xz`
