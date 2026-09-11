# 如何把本轮变化安全应用到现行主树

本阶段**不要**执行下列步骤。独立复查复验通过、且用户明确授权写入主树后再做。

## 禁止

- 不要 `git reset` / `stash` / 用 HEAD 覆盖脏文件
- 不要把 overlay **整文件 copy** 进主树
- 不要用 `/Users/simon/备份/codex/20260907-154837-industry-fflow-daily-roll/files/` 覆盖四个源码绝对路径
- 不要用该备份（或返工备份）**整份覆盖**两台权威开发日志
- 不要把整个 `data/` 拷进主树或正式 `DATA_DIR`
- 不要在交易时段无准备地改 `backend/`（`--reload` 会重启 worker `15035`）
- 不要对正式 `DATA_DIR` 做真实 H5 回补

整文件 copy / 旧备份覆盖会抹掉本轮之外的源码，也会抹掉日志里至少已存在的 Phase B 追加：

- `docs/data-platform-development-log.md` 的 `ext_fund_flow_bk_daily_industry_roll_phase_b_20260907`
- `docs/workbench-development-log.md` 的 `industry_fundflow_daily_roll_freshness_20260907`

这两条相对 15:50 备份的漂移是 Phase B 自己写入的预期内容，不是“外部污染后应整份倒回”。

## 应用（只打本轮 diff）

目标文件（相对 `/Users/simon/Trading/one-trading`）：

1. `backend/app/services/free_sources/fund_flow.py`
2. `backend/app/jobs/daily_pipeline.py`
3. `backend/app/api/pipeline.py`
4. `backend/app/services/ext_data.py`
5. `frontend/src/components/SectorFundFlowPanel.tsx`
6. `frontend/src/lib/api.ts`

`api-v02.ts` 无逻辑差，不要打。

```bash
ROOT=/Users/simon/Trading/one-trading
TASK=$ROOT/docs/investigations/2026-09-07-industry-fflow-daily-roll
PATCH=$TASK/patches/phase-b-industry-fflow-daily-roll.diff

# 1) 现有差异：四原文件 + 两新增文件是否仍等于 baseline/SHA256.txt
shasum -a 256 \
  $ROOT/backend/app/services/free_sources/fund_flow.py \
  $ROOT/backend/app/jobs/daily_pipeline.py \
  $ROOT/backend/app/api/pipeline.py \
  $ROOT/backend/app/services/ext_data.py \
  $ROOT/frontend/src/components/SectorFundFlowPanel.tsx \
  $ROOT/frontend/src/lib/api.ts

# 2) dry-run。必须先成功，再真正 apply
cd $ROOT
patch --dry-run -p1 < "$PATCH"

# 3) 无漂移才真正打本轮 patch
patch -p1 < "$PATCH"
```

### 漂移时（三方，只加本轮差）

若某文件 SHA ≠ baseline，或 `patch --dry-run` 失败：

1. 不要整文件用 overlay/备份覆盖。
2. 对该文件做三方：`当前磁盘` / `baseline/<文件>` / `overlay/.../<文件>`。
3. 只把 **本轮 overlay−baseline 仍然缺失的 hunk** 合进去；保留此前已有改动和此后无关改动。
4. 可用 `diff -u baseline/<file> overlay/.../<file>` 对照本轮意图，再手工/点状应用。

## 回滚（只撤本轮 diff）

```bash
ROOT=/Users/simon/Trading/one-trading
TASK=$ROOT/docs/investigations/2026-09-07-industry-fflow-daily-roll
PATCH=$TASK/patches/phase-b-industry-fflow-daily-roll.diff

# 1) 先看现有差异，确认要撤的是本轮 hunk，不是整文件
diff -u $TASK/baseline/fund_flow.py $ROOT/backend/app/services/free_sources/fund_flow.py | head
# （其余五文件同样先看）

# 2) 反向 dry-run
cd $ROOT
patch --dry-run -R -p1 < "$PATCH"

# 3) 无漂移才反向 apply
patch -R -p1 < "$PATCH"
```

反向 dry-run 失败时：三方只撤本轮仍在的 hunk，保留此前及后续改动。禁止用 15:50 或 18:36 备份覆盖源码。

### 权威日志

- **只追加纠正历史**，不要 `cp` 备份日志覆盖当前文件。
- 若应用后需要更正状态，在原条目下追加一段；不要把文件倒回 15:50 备份。

## 热重载

改 `backend/` 前单独授权停/启 worker。本文件不授权重启。

## 隔离复跑（不改主树）

```bash
TASK=/Users/simon/Trading/one-trading/docs/investigations/2026-09-07-industry-fflow-daily-roll
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX=$TASK/.pycache
cd /Users/simon/Trading/one-trading/backend
.venv/bin/python -m pytest \
  $TASK/tests/test_industry_fflow_daily_roll.py \
  $TASK/tests/test_industry_fflow_phase_b_fixes.py \
  -o cache_dir=$TASK/.pytest_cache \
  --basetemp=$TASK/.pytest-tmp -q

cd /Users/simon/Trading/one-trading/frontend
pnpm exec vitest run --config $TASK/tests/vitest.overlay.ts
pnpm exec tsc --noEmit -p $TASK/tests/tsconfig.overlay-api.json
```

不要把 `review/tests/test_independent_findings.py` 当本轮通过门：那些用例故意断言旧 bug，改它们会让独立报告失真。
