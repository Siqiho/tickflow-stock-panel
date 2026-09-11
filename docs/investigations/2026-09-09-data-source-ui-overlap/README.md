# 设置→数据源 与数据台 /data 重叠（只读）

- as_of: 2026-09-09
- 本地版本: v0.1.68（脏工作树；未核验远程最新版本）
- 主台: 数据台；次台: 用户台
- 已读: 任务声明文件，以及必要连带 `backend/app/tickflow/capabilities.py`、`backend/app/tickflow/policy.py`、`backend/app/data_catalog/{control_db,models,definitions,provenance,provenance_registry}.py`、`backend/app/api/stock_f10.py`、`backend/app/config.py`、`frontend/src/lib/api-v02.ts`、`frontend/src/pages/__tests__/Data.test.tsx`、`backend/tests/test_capability_{matrix,augment}.py`
- 未跑测试/构建/浏览器；未读 .env 全文；未更新三台12文件或开发日志。

## 结论

两页共用同一套偏好、密钥、插件/YAML 与 `DATA_DIR`，**不是两套数据库**。设置页是七项行情能力的写入口；数据台是本地存量、采集和控制面的写入口。截图「设置不可用 vs 数据台 TickFlow / 健康正常」是**口径混用**，不能据此宣称服务坏了。七项路由盖不住公开源旁路、Catalog、两融和 80GB 外置包。最小优化是页面分工 + 复用已有能力矩阵/能力增广 API，不必新建 Provider 基类或统一注册中心。

## 对照表

| 职责 | 设置→数据源 | 数据台 /data | 归类 |
| --- | --- | --- | --- |
| 七项能力路由 | 读写 `/api/settings/capability-matrix` 与 `PUT /preferences/data-providers` | 总览只印偏好名 | 重复展示；状态逻辑在设置 |
| 插件 / YAML / Key | 读写 data-sources、plugin-key、secrets | 只解析展示名 | 独立配置写 |
| 公开源财务 / 股票池 | 偏好 API 有字段，七项卡不列 `public` | 总览印 `financial_provider` / `pool_provider` | 重复展示，设置卡漏 public |
| 刷新同步 | 仅 reload YAML、重测档位 | 管道、目录扫描、两融/脉冲、清除 | 独立采集 |
| 健康 | 卡上 `usable` / `tf_available` | `source_health` 连续失败数 | 重复展示，两套状态逻辑 |
| 来源 / 存量 / 日志 | 无 Catalog | 目录、血缘、control.db、管道任务 | 独立存储功能 |
| 80GB 原包 | 无 | 扫描不含；GET 旁路 | 独立只读包 |

共用：`preferences` 服务端 JSON、`secrets_store`、`data/data_sources/*.yaml`、`app/plugins/*`、`DATA_DIR` Parquet、catalog SQLite。数据台多控制库与扫描索引，不是第二套源配置库。

## 截图冲突：字段被混为一谈

设置「能力不可用」来自矩阵 `usable`：生效源必须出现在当前候选里（`/Users/simon/Trading/one-trading/backend/app/data_providers/capabilities.py` 18–21、183；前端 `/Users/simon/Trading/one-trading/frontend/src/pages/settings/DataSources.tsx` 170、185–192）。TickFlow 只在档位达标时进候选；日K `tf_tier=none`，其余 starter/pro/expert（同文件 29–88、166–183）。偏好全是 tickflow 且档位 none/free 时，日K可用、其余不可用，与截图一致。`GET /api/settings/capability-matrix` 注入的是 getter 当前值（`/Users/simon/Trading/one-trading/backend/app/api/settings.py` 1783–1799）。

数据台「当前数据源」只拼 `prefs` 字段名，不看 `usable`，也不看真实请求返回的 `source`（`/Users/simon/Trading/one-trading/frontend/src/pages/Data.tsx` 451–464；`/Users/simon/Trading/one-trading/frontend/src/components/data/ControlPlaneSummary.tsx` 114–117）。因此可以同时印「复权 · TickFlow」和设置「能力不可用」。

第三套口径：`/api/capabilities` 对复权/财务会参考本地 Parquet 或 public 偏好（`/Users/simon/Trading/one-trading/backend/app/tickflow/capabilities.py` 195–216、231–242）。无 TickFlow quote 能力时，实时分支仍恒定 `quote_ok=True`、`source=local_public`（同文件 266–292），不以 public 偏好为必要条件；这也不能证明网络实时源当前连通。采集页用这份增广（`Data.tsx` 436–441），设置页不用。

「2 个正常」= `source_health` 中 `consecutive_failures === 0` 的行数（`ControlPlaneSummary.tsx` 89–111）。前端夹具正好是「2 个正常 · 1 个需关注」（`/Users/simon/Trading/one-trading/frontend/src/pages/__tests__/Data.test.tsx` 39–42、249）。当前 `app/` 生产代码只读该表（`/Users/simon/Trading/one-trading/backend/app/data_catalog/service.py` 311–319），未见写入调用；截图数字只说明控制库里有行，不能反推 TickFlow 在线或七项可用。Catalog `serving_ready` 是第四套：本地落库 + 质量（`service.py` 430–432）。

精确回退不一致（静态代码，不是运行故障）：矩阵测试写 `same_as_daily` 由 getter 自愈为 tickflow（`/Users/simon/Trading/one-trading/backend/tests/test_capability_matrix.py` 183–184），但 `get_adj_factor_provider()` 默认仍返回 `same_as_daily`（`/Users/simon/Trading/one-trading/backend/app/services/preferences.py` 220–231）；该值永不在候选里，矩阵 `usable=false`。设置页芯片仍把 `same_as_daily` 映射成日K源（`DataSources.tsx` 608–614），数据台总览不映射。`get_realtime_data_provider()` 未设置时默认 `public`（`preferences.py` 308–319），设置页「恢复默认」写 tickflow（`DataSources.tsx` 149–157）；`public` 也不进矩阵候选。`configured_provider` 只是 provenance 里 TickFlow 的 access 标签（`/Users/simon/Trading/one-trading/backend/app/data_catalog/provenance_registry.py` 21–27），不是实时探测字段。

`list_data_sources` 内置声明只列 daily/adj_factor/realtime/minute（`settings.py` 1771–1775），但不能推导 TickFlow 套用漏能力：TickFlow 套用走 `DEFAULT_ROUTING`，包含 depth5/financial（`DataSources.tsx` 149–157、657–658）；自定义源套用 PUT 包含 financial，未包含 depth5（665–671）。

## 七项路由盖不住什么

注册表只有这七项（`capabilities.py` 29–88）。`public` 在 `registry.get_provider` 与 free_sources 里工作（`/Users/simon/Trading/one-trading/backend/app/data_providers/registry.py` 14–17），但不进矩阵候选（`capabilities.py` 112–134）。Catalog 导航「41」对应静态 `DATASET_DEFINITIONS`（含 `stock_margin_trading`），扫描只走 `DATA_DIR`（`/Users/simon/Trading/one-trading/backend/app/data_catalog/scanner.py` 107–112）。托管/运行字节 = 该目录 managed + operational（`scanner.py` 819–838；`StorageBreakdownCard.tsx` 97–108），不含外置包。

两融：自有库 `data/f10/stock_margin_trading`；`GET /api/f10/margin-trading?source=offline_quantdb` 按标的读 `2_base_sector/margin_trading/<symbol>.parquet`（`/Users/simon/Trading/one-trading/backend/app/services/free_sources/margin_trading_public.py` 55–58、390–416、580–627；`/Users/simon/Trading/one-trading/backend/app/api/stock_f10.py` 32–50）。`offline_quantdb_root` 源码默认关闭（`/Users/simon/Trading/one-trading/backend/app/config.py` 183–185）。80GB 应标成「外置只读包」，不要全量导入、不扫包、不假装是七项通用行情。

## 三项最小建议

1. **先修状态口径（低成本）**。数据总览「当前数据源」改读已有 `GET /api/settings/capability-matrix`，必要时并上 `/api/capabilities` 的 `source`。每项写清：已配置 / 配置源及能力是否就绪 / 本地是否已有数据（后一项单独披露）。矩阵 `usable` 是配置与能力就绪，不是一次联网探测，不要写成「当前能否拉取」。不可用 `serving_ready` 替代「数据源健康」，它可另标「本地数据可用性」。`source_health` 没有近期采集证据则显示「采集健康未核验」，不将 0 失败写成探测通过。涉及 `Data.tsx`、`ControlPlaneSummary.tsx`；后端矩阵可不动。这是口径，不是重排；只复用已有 API，不展开新框架。

2. **再收展示重复（外观 + 流程）**。设置保留唯一写：路由、Key、插件、YAML。数据台总览改成只读摘要，链到 `/settings?tab=data-sources`。采集 / 目录 / 血缘 / 存储留在 `/data`。TickFlow Key 已是 `Keys.tsx` 的 `TickFlowKeySection`，不要再拆新页。

3. **不要扩七项**。公开源财务/股票池、两融、80GB 用现有偏好与 F10/来源追踪披露。不新建 Provider 基类、统一注册中心或迁库。页面分工 + 共用已有状态 API 足够。

## 测试覆盖（只读，未跑）

- `test_capability_matrix.py`：usable / 档位 / full_minute；未覆盖 public、same_as_daily 真 getter、两页对照。
- `test_capability_augment.py`：插件补授 `/api/capabilities`，与矩阵分离。
- `Data.test.tsx`：健康文案与公开源展示；不拉 capability-matrix。
- 无 Settings 数据源页对照测试。两融 offline 有独立 API 测试，与七项无关。

未改实现。

## 验收注

本次一次独立复核 PASS（`dd3c8916-1929-4028-b969-256924e49ea9`，独立 Cursor 会话 `bf5303b1-c04c-49b2-a794-05fef3b02e40`），已按返回意见收窄表述。Codex 在 2026-09-09 约 19:27+08 用内置浏览器只读核对了当前 3011 两页，与截图的状态差异一致，未点击套用/安装/同步/保存。本次仅评估未实施功能。Grok 4.6 + Extra High 为请求，vendor 返回未核验。
