# Remote `origin/main` Divergence Audit (Read-Only)

- **Audit time:** 2026-07-21 21:12 CST
- **Local HEAD:** `e224994` (`main`) — `fix(ui): close mobile nav on quote redirect`
- **Remote HEAD after fetch:** `0ac6d6f` (`origin/main`) — `修复分析报告复制按钮兼容性`
- **Merge-base:** `d4a834e` — `Normalize OpenAI-compatible AI base URLs (#35)`
- **Divergence:** local **ahead 44** / remote **ahead 207**
  - Pre-fetch count was ahead 44 / behind 188; fetch advanced remote by ~19 commits.
- **Authors (local-only):** Simon (44)
- **Authors (remote-only, top):** shy3130 (majority), wshy, im47cn, Gundy, community PRs
- **Scope of this audit:** read-only `git fetch` + diff inventory. **No merge, rebase, pull, push, deploy, or live DATA_DIR write.**

## Executive judgment

This is a **high-risk divergent history**, not a casual fast-forward. Blind `git pull` / `git merge origin/main` on local `main` is **No-Go**.

Recommended shape:

1. Keep local `main` as the **M0–M4 data-platform line of truth**.
2. Create a dedicated integration branch later (only with explicit approval), e.g. `integrate/origin-main-20260721`.
3. Import remote changes **by theme** (strategy/backtest/docker/watchlist/monitor), not as one bulk merge.
4. Preserve local-only data-platform modules as additive; surgically reconcile the 105 dual-touched files.

## Quantitative map

| Metric | Count |
|---|---:|
| Local-only commits | 44 |
| Remote-only commits | 207 |
| Local-only files changed since merge-base | 154 |
| Remote-only files changed since merge-base | 197 |
| Files changed on **both** sides | **105** |

### Dual-touched top-level buckets

| Top-level | Dual-touched files |
|---|---:|
| `backend/` | 50 |
| `frontend/` | 45 |
| `docs/` | 4 |
| root tooling (`.env.example`, workflows, ignore, `dev.*`, compose) | 5 |

### Local-only high-value assets (must not be lost)

These exist only on the local line and are the core of M0–M4:

- `backend/app/data_catalog/**` (SQLite control plane, scanner, API, definitions)
- `backend/app/data_providers/{public_provider,registry,unit_contracts}.py`
- `backend/app/services/atomic_io.py`
- `backend/tests/data_catalog/**`, unit/provider/atomic tests
- `frontend/src/components/data/*Catalog*`, drawer/history/storage panels + Vitest coverage
- `frontend/src/lib/dataCatalog*` (+ tests), eslint/vitest gate files
- `docs/superpowers/**` local plans/specs/reports
- packaging rename artifacts (`one-trading.spec` / `.iss`), `PRODUCT.md`, `tiers.yaml`

### Remote-only themes (message keyword counts, approximate)

| Theme | Remote commit hits |
|---|---:|
| strategy | 20 |
| AI | 14 |
| Docker | 13 |
| backtest / walk-forward | 9 / 8 |
| data (general fixes) | 9 |
| ext-data | 7 |
| minute-k | 6 |
| watchlist (+ OCR import) | 6 |
| monitor / quote / voice | 5 / 4 / 4 |
| security (strategy RCE) | 1 notable cluster |
| matrix-native backtest | PR #130 cluster |

Remote is product-feature heavy: strategy builder, backtest engine/matrix, Docker/Codex CLI mounts, watchlist screenshot OCR, monitor/voice/intraday polish, security hardenings, version bumps toward `v0.1.86`.

## Critical dual-touched paths (surgical merge required)

These files changed on **both** histories and will almost certainly conflict semantically, not just textually:

### Data plane / workbench

| Path | Local intent | Remote intent | Risk |
|---|---|---|---|
| `frontend/src/pages/Data.tsx` | Large M4 workbench rewrite (−956/+465 vs base) | Incremental panels/config (+107/−8) | **Critical** — remote hunks must be ported into new workbench sections, not reverse the rewrite |
| `backend/app/api/data.py` | Catalog/status control-plane hooks | Parallel data API fixes | **High** |
| `backend/app/main.py` | Lifespan catalog init + local runtime | Docker/Codex/runtime additions | **High** |
| `backend/app/services/kline_sync.py` | Correctness/public EOD fallback (+213/−18) | Larger remote sync evolution (+522/−103) | **Critical** |
| `backend/app/jobs/daily_pipeline.py` | Quality-status / catalog mirror hooks | Pipeline behavior fixes | **High** |
| `backend/app/services/pipeline_jobs.py` | Run mirroring into SQLite | Job orchestration changes | **High** |
| `backend/app/tickflow/repository.py` + policy/client/capabilities/rate_limits | Unit/lineage/correctness | Feature + limit changes | **High** |
| `backend/app/data_providers/{base,normalizer,tickflow_provider,custom/*}.py` | Unit contracts + staging boundaries | Custom source / provider evolution | **High** — local unit fail-closed must win |
| `frontend/src/lib/api.ts`, `queryKeys.ts`, `Layout.tsx` | Catalog client + responsive nav | Feature API/nav additions | **High** |
| `frontend/package.json` + lockfile | Vitest/Testing Library/ESLint gate | Upstream dependency drift | **High** — reinstall/reconcile deliberately |
| `frontend/src/components/data/{DepthConfigCard,MinuteSyncConfig,StatCard}.tsx` | Kept/adapted under workbench | Remote panel behavior | **Medium-High** |

### Adjacent product surfaces also dual-touched

- Strategy / backtest: `backend/app/strategy/*`, `backend/app/backtest/*`, screener dialogs, `StrategyBacktest.tsx`
- Financials UI/API, indices, monitor, settings, watchlist
- Root: `.gitignore`, `.env.example`, `dev.sh`/`dev.ps1`, `docker-compose.yml`, release workflow

## Conflict strategy (recommended, not executed)

### Do **not**

- `git pull` / `git merge origin/main` directly onto local `main`
- Force-push either side
- “Accept theirs” on `Data.tsx`, `data_catalog`, unit contracts, or atomic IO
- Deploy or switch ports 3011/3018 during integration

### Do

1. **Freeze product baseline:** local `main @ e224994` remains the runnable M0–M4 baseline.
2. **Open integration branch from local main** when approved:
   - `git branch integrate/origin-main-20260721 e224994`
3. **Import remote by theme patches**, preferred order:
   1. Security fixes (strategy RCE / import whitelist)
   2. Docker/runtime non-UI plumbing
   3. Watchlist OCR (isolated module — lower data-plane coupling)
   4. Monitor/voice/intraday UX
   5. Strategy/backtest/matrix engine
   6. Shared data sync files last (`kline_sync`, `daily_pipeline`, providers)
4. For each dual-touched file:
   - start from **local** version when file is data-platform critical;
   - cherry-pick or manually port remote behavior;
   - add a focused regression test per ported behavior.
5. Reconcile frontend deps once on the integration branch (`pnpm install`), then re-run Vitest/ESLint/build.
6. Keep real `data/` fingerprint checks before/after; integration must not rewrite market data.

### Suggested decision matrix

| Outcome needed | Choice |
|---|---|
| Keep data workbench + catalog as source of truth | Local wins on catalog modules + `Data.tsx` structure |
| Need upstream strategy/backtest/docker features | Port onto integration branch theme-by-theme |
| Need a clean GitHub main later | After integration green: PR/push from integration branch, not raw local main rewrite |
| Need M5 data growth now | Can proceed on local main **in Lab isolation** without waiting for full remote integration |

## Go / No-Go

| Action | Status | Why |
|---|---|---|
| Blind pull/merge `origin/main` into local `main` | **NO-GO** | 207 vs 44 divergence, 105 dual-touched files, semantic conflicts in data plane |
| Force-push local main | **NO-GO** | Would discard substantial upstream community/product work |
| Create integration branch + thematic port (later, explicit approve) | **GO (planned)** | Only safe path to combine lines |
| Continue M5 Source Lab on local main with isolated `DATA_DIR` | **GO** | No dependency on remote merge; no production data write |
| Deploy / switch live 3011·3018 | **NO-GO** until integration or explicit sole-baseline decision | Runtime identity not re-verified against upstream |

## Residual risks

- Remote continues to move (`v0.1.86` tag already present); counts will drift if fetch is repeated later.
- `kline_sync.py` and `Data.tsx` are the two likeliest multi-hour manual merges.
- Frontend on local main still has incomplete installed `node_modules` relative to the M4 test gate; integration should install deps deliberately rather than borrow trees.
- Custom HTTP provider exists on both sides with different evolution; unit/staging fail-closed rules from local must remain authoritative.

## Next documents / work

1. This audit (complete).
2. M5.1 universal publish protocol + M5.2 batch-1 reference schemas (Lab only).
3. Isolated Source Lab + Go/No-Go for formal reference-data publish (no real `data/` write until explicit approval).
