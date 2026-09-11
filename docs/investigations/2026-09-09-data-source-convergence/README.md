# 数据源总览口径收敛（实现说明）

- as_of: 2026-09-09
- 主台：用户台（现有 `/data` 展示）
- 次台：数据台（只读元数据/状态接口）
- 固定调查依据：`docs/investigations/2026-09-09-data-source-ui-overlap/README.md`
- 不重做调查，不读旧 Session，不更新三台计划或 GitHub 记录。
- 本地状态：用户台 `data_source_overview_status_20260909` = `implemented`；数据台 `4.22` = `implemented`。待总工 UI 验收。本文件不声称 accepted/production，也不声称独立复核 pass。
- 独立 review `80c2ba5d-d20c-4fc9-8337-808e964ffb81` 发现一项 P2：`Data.tsx` 无条件挂载 `ExternalReadOnlyData`，非管理员会请求管理员限定的 `/api/data/external-readonly-sources` 并得到 403。已按现有 `isAdmin` 条件挂载修正。
- 控制器原声明检查：32 前端、25 后端 + build passed。真实 3011 界面验收此前因 3018 设置接口连接超时未完成（总工 21:22+08）。3018 运行面已于 21:34+08 恢复，见文末；仍待总工 IAB，不声称验收完成。

## 做了什么

1. `/data` 总览「当前数据源状态」改读原生 `GET /api/settings/capability-matrix`。每项分开写：配置源、配置/能力是否就绪（`usable`）、本地是否已有数据（Catalog `local_materialized` / 行数）。`usable` 不写成「当前能否拉取」。
2. `source_health` 0 失败行数不再显示成「N 个正常」。无近期 `last_success_at` 则「采集健康未核验」。
3. 矩阵状态映射：`same_as_daily` 按跟随日K解析生效源；`public` 只进入实际已实现的复权/实时/财务候选。不改 getter 默认值、偏好持久化或网络 fallback。日K/分钟/五档/全量分钟不放行 public。
4. `/settings?tab=data-sources` 仍是唯一提供方/Key/插件写入口。总览只读摘要并链到该页。原 `tab=account` 泛「配置」链接改为数据源。Key 仍复用 Keys 页，admin 权限不变。
5. 总览单列「外部只读数据」：`GET /api/data/external-readonly-sources` 只 `stat` 配置根，状态为未配置/目录不可访问/已配置，目前只支持两融。查询走既有 `GET /api/f10/margin-trading?source=offline_quantdb&symbol=...`，最多 20 条。不写回、不同步、不静默 fallback、不扫 80GB。

## 精确改动

既有文件（已备份 `/Users/simon/备份/codex/20260909-210317-data-source-convergence`）：

- `backend/app/data_providers/capabilities.py`
- `backend/app/api/data.py`
- `backend/tests/test_capability_matrix.py`
- `frontend/src/lib/dataSources.ts` / `dataSources.test.ts`
- `frontend/src/lib/api.ts` / `api-v02.ts`
- `frontend/src/pages/Data.tsx` / `__tests__/Data.test.tsx`
- `frontend/src/pages/settings/DataSources.tsx`
- `frontend/src/components/data/ControlPlaneSummary.tsx`
- `docs/workbench-development-log.md`
- `docs/data-platform-development-log.md`

新文件：

- `backend/tests/test_external_sources_metadata.py`
- `frontend/src/components/data/ExternalReadOnlyData.tsx`
- `frontend/src/components/data/__tests__/ExternalReadOnlyData.test.tsx`
- 本 README

未改：`preferences.py` 默认值、`stock_f10.py` 默认 local 行为、`config.py`、Catalog 扫描范围、托管存储合计、真实路由 fallback。`settings.py` 的 matrix 注入保持用现有 getters。

## 测试范围

允许更新的声明测试；未删除/跳过既有断言来掩盖回归。新测试只用临时 fixture。

- 后端：`test_capability_matrix.py`（含 public / same_as_daily / 日K 不放行 public）
- 后端：`test_external_sources_metadata.py`（缺配置/缺目录/已配置/拒绝路径/非管理员不回路径）
- 前端：`dataSources.test.ts`、`ExternalReadOnlyData.test.tsx`、`Data.test.tsx`（健康口径、none 档 + 本地已有、matrix 失败、原生配置跳转）

不要重跑旧 38 tests / 原包 3 股票对照 / 全仓 tests。控制器声明的 3 条 checks 由控制器在实现结束后跑一次。

## 用现有 3011 验收

- 前端 `http://127.0.0.1:3011/data`，后端 `3018`。不要杀/启动/重启服务；Vite / uvicorn `--reload` 若在跑会自己加载。
- 总览应看到能力表、采集健康未核验或控制库记录（不是「N 个正常」）、`去设置 → 数据源`。
- none/free 档且本地已有日K时：日K可就绪，其他 TickFlow 项未就绪，本地数据单独一列。
- 外部只读：按本机是否配置 `OFFLINE_QUANTDB_ROOT` 显示三态之一；管理员可展开路径。查询一标的，最多 20 条；空记录与缺文件/坏字段分开。
- 设置页能力卡的 public / 跟随日K展示应与总览同一矩阵。

## 备份 / 回滚

- 备份：`/Users/simon/备份/codex/20260909-210317-data-source-convergence`
- 回滚既有文件：从该目录 `files/one-trading/` 拷回对应路径。
- 回滚新文件：删除上面列出的新文件。
- 不 reset/checkout/pull，以免覆盖无关脏改动。

## 接口与 UI 限制

- 元数据接口不接受 `path`/`root` 查询参数。
- 不把 `/api/capabilities` 的 `local_public` 恒真当成联网成功。
- 不把本地文件存在当成采集就绪，不用 `serving_ready` 替代数据源健康。
- 80GB 只是用户近似称呼，不硬编码为实测容量。
- 不新增 Provider 基类/注册中心/状态总线，不装依赖，不迁 Tailwind 4 / daisyUI。

## 本地 3018 运行面恢复（2026-09-09 21:34 +08）

- 上一轮已停卡住的 supervisor 3510 / worker 74916；本轮 `lsof` 确认 3018 无监听、`/health` 连接失败后，按原 cwd `/Users/simon/Trading/one-trading/backend`、原命令 `.venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 3018` 追加 `output/logs/backend-promo-20260909.log` 拉起，`start_new_session` 脱离任务进程组。
- 新 supervisor PID **80814**（PPID=1，21:34:10 +08），reload worker 80837，监听 `*:3018`。3011 Vite 3528 未动。
- 独立核验：`GET /health` HTTP **200**，`version=0.1.68`；重启标记后日志有 `Application startup complete`。
- `GET /api/settings` 与 `GET /api/data/external-readonly-sources` 无会话均为 HTTP **401**（已响应，不再超时）；未输出密钥/路径/正文。metadata 状态因此未取到。
- README 改前备份仍为 `/Users/simon/备份/codex/20260909-213048-3018-runtime-recovery`，未另造备份或审查文档。待总工 IAB。本文件不声称 accepted/production。
