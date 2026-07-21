# M5 Reference Source Lab — Real Producer Probe Go/No-Go

- **Time:** 2026-07-21 21:30 CST
- **Code baseline:** local `main` working tree atop `e224994` (+ uncommitted M5 Lab modules)
- **Isolated lab_dir:** `/tmp/one-trading-m5-ref-lab-dWIXGI`
- **Read-only source_data_dir:** `/Users/simon/Trading/one-trading/data`
- **Machine JSON:** `docs/superpowers/reports/2026-07-21-m5-reference-source-lab-report.json`
- **Production write:** none (`data/reference` and `data/.staging` absent after run)

## What ran

1. Public **SZSE month calendar** HTTP probe for `2026-06` + `2026-07`
2. Normalize → quality → atomic publish into **isolated** lab_dir via M5.1 protocol
3. Shadow compare open days vs local `kline_daily` partitions
4. Listing events shadow from local `instruments/instruments.parquet`
5. Status history shadow from recent daily partitions (halt-bar heuristic + missing-symbol fallback)
6. Automated tests: **21 passed**, new files Ruff clean

## Results by dataset

### 1) `trading_calendar` — **LAB_PASS_CANDIDATE**

| Item | Value |
|---|---|
| Producer | `szse_month_list` |
| Endpoint | `http://www.szse.cn/api/report/exchange/onepersistenthour/monthList?month=YYYY-MM` |
| Window | 2026-06-01 … 2026-07-21 |
| Raw days | 61 |
| Open days (unique) | 44 |
| Published rows | 183 (= 61 × SH/SZ/BJ expansion) |
| Weekend open rows | 0 |
| Publish | OK + lineage `trading_calendar_v1` |
| vs local kline (SH span) | open days 36 / partitions 36 / **coverage 1.0** |
| open missing partition | 0 |
| closed-but-has-partition | 0 |
| fixture weekend-only vs public (14d overlap) | 0 `is_open` disagreements in this window |

**Notes**

- SH/SZ/BJ rows are an **explicit expansion** from SZSE open flags (A-share cash session hypothesis), not three independent exchange feeds.
- One weekday closed day observed in window: `2026-06-19` (`holiday`) — public calendar carries non-weekend closures that weekend-only fixtures cannot invent.
- Still missing for production: ToS/rights admission, SSE second-source cross-check, BJ special-session verification, longer history.

### 2) `listing_delisting_events` — **LAB_SHADOW_ONLY**

| Item | Value |
|---|---|
| Producer | `local_instruments_snapshot_shadow` (read-only) |
| Instruments total | 5529 (SH 2308 / SZ 2893 / BJ 328) |
| Events built | 5528 `list` only |
| Coverage vs instruments | 99.98% |
| Sentinel `listing_date=1970-01-01` | 1 (dropped) |
| `delist` / `relist` / `code_change` | **0 / 0 / 0** |
| Publish into lab | OK |

**Blockers for production**

- Snapshot has no delist/relist/code-change history
- Cannot reconstruct dead names from current universe alone
- Sentinel listing dates exist and must be rejected (already rejected in Lab)
- Needs a real lifecycle producer (exchange/list office / admitted free source), not instruments seed alone

### 3) `instrument_status_history` — **LAB_SHADOW_ONLY**

| Item | Value |
|---|---|
| Primary heuristic | open==0 & high==0 bars |
| Finding | **0** such rows in last 120 local daily partitions (production already strips halt bars before write) |
| Fallback | missing from daily partition vs instruments listed on/before day |
| Sample | last 8 partitions; capped 500 symbols |
| Rows published in lab | 467 |
| Symbols | 343 |
| Date span | 2026-07-10 … 2026-07-21 |
| Publish into lab | OK |

**Blockers for production**

- Not an exchange status feed
- Missing-symbol fallback confounds halt / incomplete sync / new listing lag / delist
- No ST/*ST transition timeline
- No terminal `delisted` state from bars alone
- Public halt endpoints probed in this session were unstable/empty (SZSE report catalogs timeout/empty; several EM calendar/suspend report names 9501)

## Public endpoint reconnaissance (this session)

| Candidate | Result |
|---|---|
| SZSE monthList calendar | **Stable 200**, usable Lab producer |
| Sina `klc_td_sh.js` | 404 |
| EM `RPTA_WEB_TRADEDATE` | 9501 report missing |
| EM suspend custom report | 9501 filter/config issues |
| SZSE status report catalogs | timeout / empty metadata |
| EM push2 clist (listing date field f26) | works for some names; not used as formal listing producer this slice |

## Go / No-Go

| Action | Verdict |
|---|---|
| Keep using SZSE calendar inside isolated Lab / tests | **GO** |
| Formal publish `trading_calendar` into production `data/reference` | **NO-GO** until rights + SSE/BJ verification + longer history gate |
| Formal publish listing/status reference datasets | **NO-GO** (shadow only) |
| Register three datasets in live catalog/workbench now | **NO-GO** (would over-claim readiness) |
| Replace `filter_halt_days` with status history | **NO-GO** |
| Write production `data/` / deploy / paid providers / remote merge | **NO-GO** |

## Evidence paths

- Code: `backend/app/data_lab/` (`sources/calendar_probe.py`, `sources/shadow_coverage.py`, `lab_runner.py`, protocol/schemas)
- Tests: `backend/tests/data_lab/` — 21 passed
- Isolated artifacts: `/tmp/one-trading-m5-ref-lab-dWIXGI/reference/**`
- JSON report copy: `docs/superpowers/reports/2026-07-21-m5-reference-source-lab-report.json`

## Recommended next steps

1. **Calendar production track (still gated):** add SSE second-source Lab cross-check; document rights decision; extend history window; only then propose production publish + catalog registration for `trading_calendar` alone.
2. **Listing lifecycle track:** find/admit a real delist/list event producer (not instruments snapshot); keep shadow seed for coverage diffs only.
3. **Status track:** find exchange halt/resume feed; do not promote missing-symbol shadow.
4. Independent remote-integration track remains unchanged (ahead 44 / behind 207; no bulk pull).

## Claim boundary

- **Code + isolated real-source Lab run + automated tests:** yes
- **Production reference data exists / workbench shows it / runtime switched:** no
