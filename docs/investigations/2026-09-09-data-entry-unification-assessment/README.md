# 数据入口融合评估（比较判断，未实施）

- as_of: 2026-09-09
- 本地版本: v0.1.68（脏工作树；只读本地 git，未核验远端）
- 主台：用户台；次台：数据台
- 本轮不是 GitHub 远端审阅。只读当前调用链与上两轮 overlap/convergence；未跑测试/构建/浏览器；未改十二份权威文件或开发日志。
- 本地 git 线索：`DataSources` 来自能力矩阵/设置页（如 `b4aa591`）；`/data` 为本地工作台重组（`bc80dce`）。不声称 GitHub 最新。

## 结论

**单一用户主入口应留侧栏 `/data`。** 设置「数据源」是上游提供方写面板，盖不住本地数据台；`/data` 是存量/采集/追踪工作台，但写入口仍在设置页。上一轮只统一矩阵口径并加「去设置」跳转，两处入口仍在，不满足「融合成一处」。

须分开三层：用户入口（侧栏 `/data` vs 设置 tab）、组件代码（`SettingsDataSourcesPanel` 可挪、勿复制）、底层服务（preferences、secrets、YAML、插件、Parquet、control.db 本就一套）。合入口只动前两层；不要为合入口删数据库或 80GB 原包。

建议（未实施）：把现成面板嵌进 `/data` 一个管理员标签，`/settings?tab=data-sources` 重定向到该页。TickFlow Key/档位探测留在「设置 → 数据密钥」。不要复制第二套 DataSources / Provider / registry。

设置页不能单独完整替代：无目录、采集、运行记录、来源追踪、托管存储、外置只读查询；非管理员也读不到侧栏目录。`/data` 不嵌面板也不能单独替代：无 YAML 增删、插件发现/安装、七项能力点选。

## 对照

| 项 | 上游设置页 | 本地 `/data` | 融合时 |
| --- | --- | --- | --- |
| 新增/编辑/删除 HTTP YAML | `DataSourceEditor` + POST/DELETE | 无 | 直接复用面板 |
| 插件发现/安装/插件 Key | `list_plugins` + install / plugin-key | 无 | 复用 |
| 七项能力选择 | `CapabilityRoutingSection` 写矩阵 | 总览只读同一矩阵 | 写留面板；总览收成摘要 |
| TickFlow Key / 档位 | `Keys.tsx` 真写入；DataSources 仅文案 | 无 | Key 仍留设置 |
| 存储 / catalog / 采集 / 记录 / 追踪 | 无 | 本页标签 | 本地保留 |
| 80GB 原包 | 无 | `ExternalReadOnlyData` + F10 | 本地保留只读 |

共用前端：`api.ts` 的 `dataSources` / `capabilityMatrix`（约 3754–3816 行），`QK.dataSources` / `QK.capabilityMatrix`；`api-v02.ts` 无副本。总览与写面板已打同一 queryKey，嵌入后不必复制请求。档位是 TickFlow 提供方权限，不是全台总开关：`build_capability_matrix(..., tickflow_tier)` 只决定 TickFlow 是否进 `candidates`（`capabilities.py` 191–215、234 行）。路由到可用插件时 `usable` 仍可为真。自定义 HTTP 编辑器字段是日K/复权/实时/分钟/全量分钟（`DataSourceEditor.tsx` 12–21 行），不写 `offline_quantdb_root`。原包只 `stat` 配置根、两融按标的最多 20 条（`data.py` 926–968；`stock_f10.py` 32–50；`ExternalReadOnlyData.tsx` 47–50 行）。**注册插件 ≠ 数据落库 ≠ 全包可查 ≠ 付费才能用本地已有数据。** `full_minute` 本地 `field=None`，不可路由（`capabilities.py` 83–91 行）。自定义「套用」未带 `depth5`（`DataSources.tsx` 653–659 行），属既有缺口，合入口不必新开层。

## 嵌入是否可行（事实）

`SettingsDataSourcesPanel({ highlight } = {})`（`DataSources.tsx` 583 行）无 `useOutletContext` / `useSearchParams`。设置壳也未传 `highlight`（`Settings.tsx` 90–92 行只给 Monitoring）。面板自持 query/mutation，嵌进 Data 不必复制 API。`TickFlowKeySection`（`Keys.tsx` 359–370 行）已是「去数据密钥」说明，不是表单，尚无 `Link`。旧 URL：`router.tsx` 141 行已有 `settings/keys` → `tab=account`，可同样重定向 `tab=data-sources`。管理员：设置 tab `adminOnly`（`Settings.tsx` 29 行）；Data 写段已 `isAdmin`（`Data.tsx` 180–182、507、584 行）；P2 后外置包按 admin 挂载。`authorization.py` 对 `/api/data` 默认管理员，catalog/status 只读例外（13–31、80–92 行）；设置写接口走默认拒绝，GET 矩阵总览已在用。

反向把整页 Data 塞进设置：设置已 11 个 tab；Data 含采集/清除/追踪；非管理员会失去侧栏只读目录。代价明显高于嵌一块现成面板。

## 导航建议（未实施）

侧栏只留「数据」。管理员标签平铺一排：总览、数据源、目录、采集与同步、运行记录、来源追踪；「上游工具」可仍放最后，不新开层。总览主路径改链本页数据源标签。设置去掉「数据源」tab 或只做重定向。数据密钥仍在设置。采集/记录/追踪保持可达。不新增 Provider/DB/配置副本，不复制两套 DataSources。

## 若实施：最小文件与验收

- `DataPageCategoryNav.tsx` 增 section + `Data.tsx` 的 `SECTION_QUERY` / `isAdmin` 挂载
- `router.tsx` 或 `Settings.tsx`：`tab=data-sources` → `/data?section=sources`
- `dataSources.ts` 常量、`ControlPlaneSummary.tsx` 链接、`Data.test.tsx` href（现 324、734 行）
- 可选：`TickFlowKeySection` 加到 `tab=account` 的 `Link`；文档入口句
- 不改 `capabilities.py` / `preferences.py` / `authorization.py` / catalog / F10

最少验收（本轮未跑）：管理员唯一写页可增删套用，矩阵与总览同缓存；非管理员只见总览/目录且不请求外置包；旧设置 URL 落地；采集/记录/追踪仍在；none 档本地已有日K仍标「本地已有」；原包仍只读两融。

## 限制

未覆盖插件运行时、采集管道内部、80GB 目录实测。文档仍写「设置 -> 数据源」。`list_data_sources` builtin 只报 4 项数据集（`settings.py` 1771–1775 行），与七项矩阵不一致，属展示债，不是两套库。本文件是建议，未实施。
