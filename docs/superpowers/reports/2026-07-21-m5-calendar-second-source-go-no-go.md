# M5 Trading Calendar Second-Source Lab Go/No-Go

- **Time:** 2026-07-21 ~21:41 CST
- **Code baseline:** local `main` after `14aeefc` + this second-source slice
- **Lab root:** `/tmp/one-trading-m5-cal-xcheck-09mEbX`
- **Production write:** none

## What we re-checked (network included)

You were right to suspect network flakiness. This session observed:

| Endpoint | Result this session |
|---|---|
| SZSE monthList (live) | **Unstable** — empty reply / server disconnect (curl 52 / httpx RemoteProtocolError) |
| Official SSE calendar/SOA pages | **Unavailable** — earlier 404 / `SOA service is null` / SSL failures |
| Tencent `web.ifzq.gtimg.cn` fqkline `sh000001` / `sz399001` | **Stable** |

Therefore the dual-source run used:

1. **Primary:** SZSE calendar from **prior successful isolated Lab cache**  
   `/tmp/one-trading-m5-ref-lab-dWIXGI/reference/trading_calendar/calendar.parquet`  
   (live SZSE retried and failed; cache fallback explicit in report)
2. **Secondary (proxy, not official SSE API):** Tencent Shanghai Composite daily bar dates as SH open-day series; Shenzhen Component for SH/SZ identity

This is intentionally **not** claimed as “official SSE calendar API succeeded”.

## Cross-check results

### Window A — 2026-06-01 … 2026-07-21 (dual source)

| Check | Result |
|---|---|
| SZSE mode | `cache_parquet` (live failed) |
| Tencent SH open days | 36 |
| Tencent SZ open days | 36 |
| Tencent SH == SZ | **equal** |
| SZSE SH open == Tencent SH | **equal (36/36)** |
| SZSE weekend open rows | 0 |
| Admission | `LAB_PASS_CANDIDATE_SECOND_SOURCE_OK` |
| Discuss standalone prod publish | **DISCUSS_ONLY** |
| Production publish now | **NO_GO** |

### Window B — 2025-01-01 … 2025-12-31

| Check | Result |
|---|---|
| SZSE live/cache | unavailable for this long window (no 2025 cache) |
| Tencent SH | 243 open days |
| Tencent SZ | 243 open days |
| SH == SZ | **equal** |
| Dual-source SZSE vs Tencent | **not completed** |
| Admission | `LAB_PARTIAL_TENCENT_ONLY` |
| Discuss publish | **NO** |

### Window C — 2026-01-05 … 2026-07-21

| Check | Result |
|---|---|
| Tencent SH == SZ | **131 == 131** |
| SZSE vs Tencent dual overlap | only **2026-06-01..2026-07-21** (cache coverage) still **equal 36** |
| Full YTD dual-source with live SZSE | blocked by live SZSE outage |

## Rights / producer notes

- **SZSE monthList:** exchange public JSON; Lab-usable; production redistribution still needs explicit rights sign-off.
- **Tencent open days:** public quote derivative; good **cross-check proxy** for SH session open days; **not** an official SSE calendar rights basis.
- **Official SSE machine-readable calendar:** still missing in this environment.
- **BJ identity:** still only by A-share session expansion hypothesis from SZSE flags, not an independent BJ feed.

## Go / No-Go

| Decision | Verdict | Why |
|---|---|---|
| Keep Lab dual-check path (SZSE + Tencent proxy) | **GO** | Implemented, tested, reproducible in isolation |
| Claim “official SSE second source done” | **NO** | SSE official API not obtained |
| **Discuss** standalone production publish of `trading_calendar` only | **YES, with gates** | Dual-source agreement on latest dual span; SH/SZ proxy identity holds on 2025 and 2026 YTD |
| Actually write production `data/reference/trading_calendar` now | **NO-GO** | Rights sign-off, operator approval, live SZSE refetch preferred over cache-only, SSE official still absent, BJ not independently proven |
| Register catalog/workbench / replace consumers | **NO-GO** | Same gates |
| Listing/status formal publish | **NO-GO** | Out of scope; still shadow-only |

### Gates before a future standalone `trading_calendar` publish discussion can become GO

1. Explicit user approval to write production `data/`
2. Rights/ToS sign-off for chosen producer(s)
3. Prefer fresh live SZSE pull (not only cache) for the publish window
4. Record that secondary check is Tencent proxy unless/until official SSE feed is admitted
5. State BJ expansion assumption in dataset lineage/docs
6. No silent scope creep into listing/status

## Engineering delivered this slice

- `backend/app/data_lab/sources/tencent_calendar_probe.py`
- `backend/app/data_lab/sources/calendar_crosscheck.py`
- tests for mock probe + cross-check equal/mismatch
- reports under `docs/superpowers/reports/2026-07-21-m5-calendar-second-source-*`

## Verification

- `pytest tests/data_lab`: **24 passed, 1 skipped** (live SZSE optional skipped on outage)
- Ruff on new/touched data_lab files: clean
- Production `data/reference` / `data/.staging`: still absent

## Claim boundary

- **Second-source Lab cross-check implemented and run:** yes
- **Official SSE calendar API integrated:** no
- **Production calendar published:** no
