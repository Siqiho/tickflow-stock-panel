# WP2 总览 scope/date/availability

层：数据台 overview 装配 + 用户台看板/Layout 语义。跨层但只动声明白名单。

状态：代码/测试已落地并经本执行端检查。独立 review `f4889223-1dcd-4362-9dd1-97e8ff9c5455` 虽 PASS，但总工将该审查列出的 lineage 残余 P2 提升为本包必修并已最小修复。IAB 仍待 Codex / runtime owner 刷新 3018。不是 user accepted / production。

WP1 已工程验收，见 `docs/investigations/2026-09-11-dashboard-data-acceptance/chief-acceptance.md`。本包不重开 WP1。WP3 未做。

## 旧失败 / 续接

- 旧 wf `69099e44-2698-4bba-bb68-4375ac0aa05e` blocked。子 `f8f506d5-7e2b-42ac-b46a-1b8c8751d85d` session=null / candidate=null，Failed to initialize session services，零检查零实现。
- 开工 baseline `0ba231b2e76c0dac4afebd0b0c7ceaa7c94ba81a1556128f4e38d1d37a640eba`：17 声明文件当时与当前相同，无旧 WP2 实现可复用。
- 失败任务 `dce105e3-ad1e-40eb-907e-d0fc68971e79`：HTTP/2 CANCEL，session `30ba043c-25f8-4d8a-b212-a9125293ec46`，candidate `010200b5bfcdc050ea221e2032f0c870ce5e53869b73bc299318859bb3c849f7`。Codex 核 22 文件 SHA 与该 candidate 一致后本轮续接，不重做已正确实现。

## Before 原因

`quote_snapshot` 5 条旧样本（无 scope 元信息）被当成全市场合计：4/0/1、55.72 亿。缺 coverage 时 UI 不标范围。Layout.mobile 缺 `mode` 的 mock 被期望成「全市场」。

## 契约（已核源码）

- 只认声明元信息：parquet/lineage `scope=full_market` 才 `trusted_full_market`。不按行数猜。混合/缺 scope → unknown。
- 正式日 `data_mode=official` 可合计，`scope=official`，`trusted_full_market=false`，日期不漂到 today。
- 自选 / 未知 / 空：`breadth`/`amount` 为 JSON `null`，UI 主 KPI 为 —；样本 4/0/1 与 55.72 亿只在 `coverage.sample` / 警告横幅。
- 旧 API：多一个 `coverage` 对象；原字段名不变。TS `OverviewMarket.breadth` 仍是 `number`，以免白名单外 `Review.tsx` 因 `null` 破编译；运行时仍发 `null`，Dashboard 以 `coverage.market_totals_ok === true` 开门。
- realtime_mode 未改：TickFlow none/free=`none`，public=`full_market`。
- 今日可信全市场仍 15s；历史静止。资金流/脉搏/官方池节奏未改。

## 本轮收尾相对续接 candidate 的最小改动

- 未知范围文案「范围未知」改为「未知」，避免「范围 范围未知」。
- 覆盖警告加 `role="status"`；Dashboard.scope 按横幅/KPI 查询，不删契约断言。
- 补缺 `coverage` 对象测例。Layout.mobile mock 类型含可选 `mode`。
- 补工作台条目；数据台条目写上检查数。

## lineage 残余 P2（总工提升为本包必修）

独立 review `f4889223` 结论 PASS，并把 `_latest_quote_lineage` 同日按 mtime 取任意 `quote_snapshot` 记录标为残余 P2（本包当时不必改）。总工未接受该缺口，要求 fail-closed：只有匹配股票快照的 lineage 可参与 coverage。

- 优先认 payload `asset_type=stock`。
- 兼容旧记录：无 `asset_type`，但 `target_artifact` 明确指向 `quote_snapshot/asset_type=stock/date=目标日`。
- `asset_type` 非 stock、目标路径不匹配、缺乏足够身份的记录均不可授予 `full_market`。
- 不按行数猜。不改显式 stock parquet scope 优先 / 混合 scope → unknown。
- 不改 repository writer、frontend、shared/formal data、服务、调度或 provider。
- 改前备份：`/Users/simon/备份/codex/20260911-175435-overview-scope-lineage-p2-before`

## 检查（本执行端亲眼看见）

上一轮续接检查（candidate `c79a1b12…` / 任务 `0238cce4`）：pytest 五文件 27 passed；vitest 43；tsc 0；vite `/tmp` 成功。

本轮 lineage P2 最小修复后，本执行端亲眼看见：

```
cd backend
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-overview-scope-pytest-data REGEN_BACKEND_DATA=no \
  .venv/bin/python -B -m pytest -q tests/test_overview_scope.py
# 12 passed, 1 warning in 0.38s

PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-overview-scope-pytest-data REGEN_BACKEND_DATA=no \
  .venv/bin/python -B -m pytest -q \
  tests/test_overview_scope.py tests/test_intraday_overview.py \
  tests/test_market_overview_as_of.py tests/test_quote_service_interval.py \
  tests/test_quote_service_watchlist_union.py
# 30 passed, 4 warnings in 0.50s
```

前端 6 个 WP2 文件 SHA 与 `0238cce4` / `c79a1b12…` 一致，本轮无 frontend diff，复用其 43 / tsc exit 0 / vite `/tmp` 证据，未机械重跑。

隔离 repro（仅 `/tmp`）：

```
backend/.venv/bin/python docs/investigations/2026-09-11-overview-scope-fix/scripts/repro-old-quote-5-sample.py \
  --data-dir /tmp/ot-overview-scope-repro --print-overview
# coverage.scope=unknown, market_totals_ok=false, breadth/amount=null,
# sample 4/0/1 amount_total=5572000000
```

未重启 3011/3018。未写 shared `DATA_DIR`。隔离缺全日 K 不作正式库缺数证据。

## 备份 / fixture / runtime

- 改前备份：`/Users/simon/备份/codex/20260911-170040-overview-scope-fix-before`（README 有效）
- TEST-ONLY fixture：`docs/investigations/2026-09-11-overview-scope-fix/fixtures/`
- 3018 须由 owner `01a07a79-1c8e-73e0-af8f-85939177bb8b` 刷新。本执行端不能声称当前 runtime 已是新代码。

## 资讯任务：Layout.mobile

失败不是资讯回归。共享 Layout 缺 `mode` 的 mock 曾被断言「实时行情 · 全市场」。产品：缺 mode →「未知」；`none` →「未开启」；显式 `full_market` →「全市场」。本包给全市场测例补了明确 mock，并加未知/`none` 验证。
