# Upstream Transplant Checklists Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce two executable, non-overlapping upstream transplant checklists—(A) data-related only and (B) user-layer UI only—so future agents can cherry-pick without blind merges.

**Architecture:** Do not merge upstream wholesale. Map each upstream feature to local path, commit/tag range, dependencies, conflict risk with one-trading free_sources / owned-market-data and go-stock Web/RPC. Deliverable is documentation + verification gates, not code merge in this plan.

**Tech Stack:** git tag/diff audit, Markdown checklists, existing local trees under `/Users/simon/Trading/one-trading` and `/Users/simon/Trading/go-stock`.

**Status: DELIVERED** checklist at `/Users/simon/Trading/上游移植清单-数据相关与用户层UI-2026-07-17.md`

**Status anchors (2026-07-17):**
- User layer local: one-trading `VERSION=v0.1.64` / HEAD `edcffcf` vs upstream tickflow `v0.1.85` / `origin/main 34eaba3`
- Data layer local: go-stock pin `v2026.06.19.6-release` (`40444c7`) + Web mods vs upstream `v2026.07.10.1-release` (`11c2fa0`)
- Prior audit: `/Users/simon/Trading/上游更新核查-用户层与数据层-2026-07-17.md`
- free_sources worktree (optional data track peer): `one-trading/.worktrees/free-ext-data-p0p1`

---

### Task 1: Track A — Data-related transplant checklist

**Files:**
- Create: `/Users/simon/Trading/上游移植清单-数据相关与用户层UI-2026-07-17.md` (Track A section)
- Reference: tickflow `v0.1.64..v0.1.85`, go-stock `v2026.06.19.6-release..v2026.07.10.1-release`

- [x] **Step 1: Enumerate data features only**

Include:
1. tickflow custom HTTP data source
2. tickflow stock-sdk plugin (optional, compliance-gated)
3. tickflow minute-K redo + minute backtest plumbing
4. tickflow ETF data path (not just UI labels)
5. tickflow ext-data pull defaults / schema cast fixes
6. go-stock auction + MAC capital flow (verify local parity)
7. go-stock ETF search/IsOnExchangeFund (verify local parity)
8. go-stock TDX incremental calibration
9. go-stock concept tags (data model + API)
10. Explicit EXCLUDE of pure UI/Agent from Track A

- [x] **Step 2: For each item write: source commits/tags, upstream paths, local target paths, already-local?, deps, risk, verification**

- [x] **Step 3: Order Track A by priority P0/P1/P2 and no-paywall preference**

---

### Task 2: Track B — User-layer UI transplant checklist

**Files:**
- Same deliverable markdown (Track B section)

- [x] **Step 1: Enumerate UI-only / product-shell features**

Include:
1. Data source settings pages (UI shell only if provider already exists)
2. Minute sync config UI
3. Walk-forward / optimizer panels
4. Voice broadcast UI wiring
5. Screener intraday column / dashboard polish
6. go-stock all-tab table view / measure / wave drawing
7. go-stock Feishu bot / DeepAgents (Agent UX; optional sub-track B2)
8. Explicit EXCLUDE of data-provider code from Track B

- [x] **Step 2: Map files + conflict notes with local branding/Web shim**

- [x] **Step 3: Order Track B after Track A data prerequisites where needed**

---

### Task 3: Polish gates and anti-goals

- [x] **Step 1: Write hard anti-goals** (no blind merge; no TickFlow paid pretence; no vendor GPL wholesale; no dual provider systems without decision)
- [x] **Step 2: Verification matrix** per track
- [x] **Step 3: Suggested next execution waves** (Wave 1/2/3)

---

## Spec Coverage

| User need | Task |
|---|---|
| 只合数据相关清单 | Task 1 |
| 只合用户层 UI 清单 | Task 2 |
| 优化打磨 / 可执行 | Task 3 |

## Out of Scope This Plan

- Actually merging upstream into main
- Enabling stock-sdk by default
- TickFlow Pro minute full-market without key
