# Test results — 2026-09-12 fund-flow window chain restore

Backup: `/Users/simon/备份/codex/20260912-015545-fund-flow-window-chain-restore-before`

Interpreter: `/Users/simon/Trading/one-trading/backend/.venv/bin/python`

No real H5/network, no `run_now` against official `DATA_DIR`, no scheduler enable, no service start/stop.

## Backend focused

```
ONE_TRADING_DISABLE_BACKGROUND=1 PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-fflow-window-restore-pytest
cd /Users/simon/Trading/one-trading/backend
.venv/bin/python -m pytest -p no:cacheprovider \
  tests/free_sources/test_fund_flow_window_restore.py \
  tests/free_sources/test_fund_flow.py -q --tb=short
```

- exit: **0**
- count: **36 passed**, 1 warning (`ext_factors.py` SyntaxWarning, pre-existing, unrelated)
- `test_fund_flow_window_restore.py`: 7 passed
- `test_fund_flow.py`: 29 passed (file hash unchanged)

## Frontend focused

```
cd /Users/simon/Trading/one-trading/frontend
npx vitest run \
  src/components/__tests__/SectorFundFlowPanel.history.test.tsx \
  src/components/__tests__/SectorFundFlowPanel.industry-freshness.test.tsx
```

- exit: **0**
- count: **15 passed** (2 files; history 11, freshness 4)
- duration: 1.99s

## Formal Parquet vs service (read-only)

```
ONE_TRADING_DISABLE_BACKGROUND=1 PYTHONDONTWRITEBYTECODE=1
cd /Users/simon/Trading/one-trading/backend
.venv/bin/python \
  /Users/simon/Trading/one-trading/docs/investigations/2026-09-12-fund-flow-window-chain-restore/verify_parquet_windows.py
```

- exit: **0**
- `all_match`: **true**
- windows: industry 5/63/126, concept 5/63
- output: `evidence/parquet-vs-service.json`

## Not run / not claimed

- real `roll_concept_daily_from_h5` / `roll_industry_daily_from_h5` against official data
- `daily_pipeline.run_now` on official `DATA_DIR`
- scheduler fire / 15:30 continuation (historic 9/10 15:30 evidence not reverified)
- tsc / vite / Codex in-app browser / IAB
