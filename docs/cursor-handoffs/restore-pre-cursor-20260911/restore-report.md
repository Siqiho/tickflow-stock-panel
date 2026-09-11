# Restore report: one-trading to pre-2026-09-09 05:12 official

as_of: 2026-09-11T23:11+08:00  
phase: local restore executed; Codex IAB main-path passed; independent review pass  
Codex IAB 主路径已通过（转录，非本执行端观察）。后台任务限制仍保留。Not user acceptance. Not daily-run equivalent.

## What phase1 already did (not re-run)

Write-before backup (recoverable):

`/Users/simon/备份/codex/20260911-restore-pre-cursor-before-20260911T224838`

Trash unique dir:

`/Users/simon/.Trash/one-trading-restore-pre-cursor-20260911-20260911T224838`

| Item | Count / evidence |
| --- | --- |
| SOURCE target | **1537** = A 1497 + B fill **40** (`frontend/src/components/data/**` including tests) |
| A-only extra product files | 0 |
| A/B core hash mismatch | 0 (logs excluded) |
| Restore overwrite/missing | **206** |
| Unchanged already-old | **1327** |
| New product source moved to trash | **176** + 2 generated tsbuildinfo = 178 in `trash-list.json` |
| SOURCE hash verify after copy | **1533/1533** (4 preserve: `.env` + 3 current logs) |
| B-fill verified on disk | **40/40** |
| Leftover trash paths | 0 |
| Old deps copied | official `.venv` Polars **1.40.1**, `node_modules` realpath official, not sandbox symlink |
| Owned 3011/3018 stopped | backend 64083, isolated vite 98187; Hermes 973 kept |

A physical miss of the 40 files: A `official-source` has **no** directory named `data` (it treated `frontend/src/components/data` as runtime data). B still has those 40 source files. Android source A/B both 86 files, identical. Nested runtime `data/` was not used as the exclusion for product `components/data`.

## This turn (phase2) — remaining steps only

Did **not** redo backup, restore copy, or trash moves. Did **not** empty directories.

1. Confirmed backup/trash/deps/data still present; parquet identity **5770 = 5770**.
2. Spot-checked SOURCE hashes (main.py, vite.config.ts, B `ActiveJobCard` / `catalogFixtures`, frontend src samples) — all match manifest.
3. Frontend `tsc -b` exit **0**. `vite build` exit **0**. Dist `index-Cp8DqVcD.js` sha256 `f60da483c131d8b8e5a50ef8abe73e6cd9e4c699c9906359a3a03c49a36a23a5`.
4. Moved tsc-emitted `frontend/vite.config.js` + `.d.ts` into the existing trash `derived-cache/` so live 3011 loads `vite.config.ts`.
5. Isolated backend: `DATA_DIR=/tmp/ot-restore-pytest-20260911`. Import `app.main` exit **0**. Pytest 4 files: **46 passed, 12 errors**. The 12 errors are `tests/test_preferences_cache.py` calling `preferences._invalidate_cache` which the restored old `preferences.py` does not have. That pair is already in A (05:12 tree). **Not patched.**
6. Official 3011/3018 started. First backend PID 5688 inherited leftover test `DATA_DIR` and was replaced. Current official backend has **no** `DATA_DIR` override.

## Runtime now (Codex IAB main path already transcribed; wrapper/background limits retained)

| Role | PID | PPID | Listen | cwd | Identity |
| --- | ---: | ---: | --- | --- | --- |
| Backend verify wrapper | **5762** | 1 | 127.0.0.1:3018 | `one-trading/backend` | official `.venv` python; `v0.1.68`; wrapper below |
| Frontend official vite | **5690** | 1 | 127.0.0.1:3011 | `one-trading/frontend` | official `node_modules/vite`; **no** isolated config |
| Hermes | **973** | 1 | (untouched) | — | do not touch |

Start (recoverable; not `./dev.sh`):

```text
# backend — verification wrapper, not daily-run
cd /Users/simon/Trading/one-trading/backend
/Users/simon/Trading/one-trading/backend/.venv/bin/python -B \
  /Users/simon/Trading/one-trading/docs/cursor-handoffs/restore-pre-cursor-20260911/verify-start-wrapper.py

# frontend — official vite
cd /Users/simon/Trading/one-trading/frontend
/Users/simon/Trading/one-trading/frontend/node_modules/vite/bin/vite.js \
  --host 127.0.0.1 --port 3011 --strictPort
```

Wrapper path: `verify-start-wrapper.py`. Process env only: `ONE_TRADING_HERMES_RUNTIME_ENABLED=false`, `ONE_TRADING_HERMES_MULTIUSER_ENABLED=false`, empty `AI_*` keys. Does **not** edit `.env`. Old code has no safe switch for scheduler / ext_pull / depth / minute_refresh / TickFlow probe; wrapper no-ops those. **This is not daily-run.**

Daily-run difference: schedulers, quote/depth boot, ext_pull.refresh, minute_refresh, builtin preset ensure, mining recover, and capability re-probe would run. Official `capabilities.json` is schema 5 / label None, so even daily-run would skip TickFlow probe if cache is kept.

## Smoke (HTTP only; no login / no fixture user)

| URL | HTTP | Note |
| --- | ---: | --- |
| `http://127.0.0.1:3018/health` | 200 | `version=0.1.68` `mode=none` |
| `http://127.0.0.1:3018/api/health` | 404 | old API has no this route |
| `http://127.0.0.1:3018/api/settings` | 401 | 未登录；auth not lowered |
| `http://127.0.0.1:3018/api/overview/market` | 401 | same |
| `http://127.0.0.1:3011/` | 200 | official Vite HTML (`react-refresh`), not isolated sandbox page |

Vite proxy `ECONNREFUSED` in the frontend log is from the few seconds between killing 5688 and 5762 listen. Not treated as product failure.

## Preserved

- `data/` Parquet 5770 unchanged vs write-before identity
- `preferences.json` sha256 `45a0612d01d25f3376aff38bedac9d908c2eeefc033081976fa88fac2f39323a` (same as backup)
- `capabilities.json` sha256 `1088d2bf92b97601bf5127e736ea849a3f1391448ed9c9f6468f91b9e99ef523` (same)
- `identity.sqlite3` / `catalog.sqlite3` integrity_check=ok; catalog `user_version=2`, `dataset_state=45` (startup rescan skipped)
- `.env` 0600, not overwritten
- Current three development logs appended only; not replaced from A/B
- `docs/cursor-handoffs/`, `docs/investigations/`
- Workspace `AGENTS.md` and 12 authority files not overwritten
- Git HEAD `31216dda527cd4ec177b9cbf6fd1c524dbadbe82`
- `.git/index` restored to original bytes `b69739e11d4f0895bfd284dd0b1d409574d55e92e68569f298c7c1ab567e25fd` after `git status` stat refresh. Code rollback ≠ index rollback; staged listing kept.

## Residual risk

- 3018 is wrapper-started, not `uvicorn app.main:app` daily-run.
- Old tree inherent: `test_preferences_cache.py` vs missing `_invalidate_cache`.
- Capability cache is None-tier; paid TickFlow key in `.env` is unused while cache/wrapper hold.
- Independent browser / IAB is for Codex. This report does not claim page acceptance.
- First accidental isolated-DATA_DIR start (5688) is dead; official data hashes unchanged.

## Logs / artifacts

- `dry-run.json`, `source-manifest.json`, `restore-list.json` (206), `trash-list.json` (178), `b-fill-40.json`
- `phase1-summary.json`, `verify-source.json`
- `frontend-tsc.log`, `frontend-vite-build.log`, `backend-isolated-tests.log`
- `backend-verify-3018.log`, `frontend-official-3011.log`, `runtime-smoke.json`
- `verify-start-wrapper.py`

## Codex IAB + independent review (restore-docs-wording-20260911-close)

以下 Codex 实测为转录，不是本执行端观察。

- 恢复到 2026-09-09 05:12 升级前。SOURCE **1533/1533** 哈希通过。**206** 还原 / **176** 新增移 Trash / **40** 从 9/8（B）补全。`.env` 与现有数据保留。
- 前端 `tsc` / `vite build` 通过。后端隔离测试 **46 passed, 12 errors**：12 个属于旧备份 `tests/test_preferences_cache.py` 调用不存在的 `preferences._invalidate_cache`，不修旧版。
- 3011/3018 为验证 wrapper，后台任务暂停，不是日常全功能验收。
- Codex IAB：3011 旧版看板 9/9，5468 股票 + 241 分钟脉搏 + 行业资金流 128/128；`/data` 目录展示 8,214,828 条日线，打开 Stock daily bars 详情成功；浏览器 error logs `[]`。后续数据仍保留。
- 独立只读 review `aca6de45-3dcf-4aa3-8b86-12c80cef1590`，session `b09672e5-80b9-4d25-b8ee-eefdedf1f63c`，完成 **success/pass**：无恢复阻断、384 extras 仅 docs 资料、176 已 trash、12 errors 旧版固有。
- review 请求 Grok 4.6 Extra High 配置 acknowledgement 有；实际返回模型/effort 未核验。
- 实现任务传输超时，不写 workflow 成功。
