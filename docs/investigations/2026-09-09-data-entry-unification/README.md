# 数据入口融合（本轮实现）

- as_of: 2026-09-09
- 主台：用户台；次台：数据台（只读消费既有 API）
- 备份：`/Users/simon/备份/codex/2026-09-09-data-entry-unification`；IAB 三点修正前另拷 `/Users/simon/备份/codex/2026-09-09-data-entry-unification-iab-fixes`
- 状态：`implemented`。修正后唯一矩阵/只读态仍待总工。不是 verified / accepted。不声称修正后 IAB 或独立 review 已通过。

## 做了什么

侧栏 `/data` 总览成为唯一主入口。上方能力卡分开「谁提供 / 配置就绪 / 本地已有」。中间复用 `SettingsDataSourcesPanel`：在线提供方 + catalog 证据归组的本地采集源 + 未登记 + 管理员外部只读原包。点击来源看能力、匹配数据集、字段/单位、覆盖时间、`true_producers`。付费档位只在 TickFlow。`/settings?tab=data-sources` 重定向到 `/data?section=sources`（同页深链，不是第七个标签）。

映射在纯函数 `frontend/src/lib/dataSourceCatalog.ts`：只按 `catalog.provider`（`local_public`→`public`）归组；不用当前路由冒充历史来源；`public_feed` 等 lineage 不硬编码成公开源；无 provider 进未登记。

## 文件

- 改：`Data.tsx`、`Settings.tsx`、`settings/DataSources.tsx`、`settings/Keys.tsx`、`ControlPlaneSummary.tsx`、`ExternalReadOnlyData.tsx`、`dataSources.ts`、对应测试、`workbench-development-log.md`
- 新：`dataSourceCatalog.ts` / `.test.ts`、`SourceDatasetDetails.tsx`、`DataUnifiedSources.test.tsx`、本 README
- 未改：backend、`router.tsx`（设置页已重定向）、`DataPageCategoryNav.tsx`、`DatasetDetailDrawer.tsx`、锁文件

## 边界

- 普通用户：catalog + 矩阵 + 来源列表只读；不请求 provenance / 外置包 / 控制摘要；无套用/增源/密钥表单
- 原包：外部只读、仅两融、最多 20 条；不扫 80GB、不改 root
- TickFlow `none` 只影响 TickFlow 能力，不否定本地已有
- 本轮未跑整组测试/build/浏览器；控制器 finish 后跑声明 checks
- 检查阶段：页面测试选择器收到 heading / 来源卡 section / 已选详情 / `li` 行；去掉 Settings `TabKey` 与 DataSources `UnifiedSource` 未用类型。
- 2026-09-09/10 IAB 三点修正（未重跑整组）：去掉静态七卡，只留上游同组卡并写入配置就绪/本地已有；只读隐藏 TickFlow redetect；catalog loading/error 不再写成无关联。修正前已验：旧 `settings?tab=data-sources` → `/data?section=sources`；公开源 11 集、hithink 4 集可开字段 drawer，生产者为同花顺官方金融数据服务；原包 `300502.SZ` 20 条 `offline_quantdb` 截至 2026-08-26 空值—。

## 总工验收入口

1. `/data`：能力卡 + 来源卡同页
2. 点「公开源」：应看到 `stock_daily` 等 local_public 集，字段单位与覆盖时间；生产者来自 provenance，不是“公开源”四个字
3. 点「外部只读原包」：状态 + `300502.SZ` 两融查询，结果带 `source`
4. `/settings?tab=data-sources` 应落到 `/data?section=sources`
5. 普通账户：仍能读总览/目录，不能写提供方
