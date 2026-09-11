# Android APK 响应式验收基线

最近维护：2026-08-10

适用范围：`/Users/simon/Trading/one-trading-release` 私有 Android APK 与其加载的发布版 Web 前端。本文不适用于 `/Users/simon/Trading/one-trading` 本地开发版，也不授权修改本地开发版。

## 1. 目标设备

| 设备状态 | 物理分辨率 | PPI | 屏幕 | 物理宽高比 | 等效验收视口（近似） |
| --- | ---: | ---: | ---: | ---: | ---: |
| OPPO Find N3 内屏展开 | 2440 × 2268 px | 约 426 | 7.82 英寸 | 约 1.08:1 | 约 916 × 852 dp |
| OPPO Find N5 内屏展开 | 2480 × 2248 px | 约 412 | 8.12 英寸 | 约 1.10:1 | 约 963 × 873 dp |

说明：

- 第三方资料可能按默认方向写成 `2268 × 2440` 或 `2248 × 2480`，仅宽高顺序不同。
- dp 为按 `px / (PPI / 160)` 计算的近似值；Android 实际可用区域还会受系统栏、显示缩放、WebView DPR 与横竖方向影响。
- 验收不能只输入物理像素。必须同时覆盖窄屏手机、约 916 × 852 dp、约 963 × 873 dp、普通桌面四类运行面。

## 2. 响应式规则

- 小于 768 CSS px：使用手机结构。顶栏为“菜单 — 版本号 — Logo”；设置导航移到内容上方；自选股宽表改为卡片列表；弹窗占满可用宽度并保留安全边距。
- 768–1023 CSS px：视为展开折叠屏/小平板。主导航可使用桌面侧栏，但设置页仍采用顶部导航与单列宽卡片，避免“侧栏套侧栏”压缩内容。
- 1024 CSS px 及以上：保持既有桌面双列和设置侧栏布局。
- 禁止通过缩小正文来掩盖容器失配。长标题、说明、能力名称和状态标签应正常换行；交互控件不得越出卡片。
- 主要触控目标在手机结构中至少 44 × 44 CSS px。
- WebView 尺寸变化和折叠/展开后必须重新计算布局；不能要求重启 APK 才恢复。

## 3. 本轮验收页面

- 移动顶栏：菜单位于左侧，版本号居中，Logo 位于右侧；菜单开关和焦点行为不变。
- 设置 / TickFlow：订阅档位、可用功能名称和额度不再逐字竖排或相互覆盖。
- 设置 / 实时监控：行情轮询、轮询间隔、自选股实时、连板梯队修正的卡片标题、徽标、按钮和滑杆不溢出。
- 自选股：标题和状态标签正常换行；搜索与操作区独立成行；手机默认列表不再依赖横向滚动查看名称和现价。
- 策略推荐库 / 策略池：弹窗宽度随屏幕变化；手机为上下分区，展开折叠屏和桌面恢复双栏。

## 4. 完成证据

每轮 Android 响应式改动至少保留：相关自动测试、生产构建、远端新资源身份、原生 Android AVD 手机竖屏截图，以及 N3/N5 等效展开视口截图或真实设备截图。只有代码和构建通过时，状态仍是“已实现”，不能写成“APK 已验收”。

## 5. 2026-08-10 验收记录

- 发布仓库：`/Users/simon/Trading/one-trading-release`；本地开发仓库未参与本轮修改。
- 前端全量测试：26 个测试文件、107 项通过。
- 生产构建：TypeScript 与 Vite 构建通过；保留项目既有动态/静态混合导入和 bundle 大小提醒。
- Zeabur 部署：`6a796ee34243c79e762cfd5c`，状态 `RUNNING`；远端最终资源为 `index-CrdYGVbn.js` 与 `index-CbGB3E5A.css`。
- 浏览器手机视口：411 × 891 CSS px，`body.scrollWidth === body.clientWidth === 411`；自选股搜索框 327px，使用手机卡片且不渲染宽表格。
- 浏览器折叠屏等效视口：N3 约 916 × 852，内容宽 628px；N5 约 963 × 873，内容宽 675px。两者无页面横向溢出，设置页均保持顶部导航和单列宽卡片。
- 原生 Android 目标：`emulator-5554`、`com.simon.onetrading`、`versionName=0.1.68`、冷启动；UI Automator 确认新顶栏顺序与设置/自选股/策略页面结构，应用过滤日志与 crash buffer 无本轮错误。
- AVD 截图：
  - `/Users/simon/.codex/visualizations/2026/08/08/019fe1fa-84a8-7de3-8a51-56bfcb069c5c/android-responsive-20260810/dashboard.png`
  - `/Users/simon/.codex/visualizations/2026/08/08/019fe1fa-84a8-7de3-8a51-56bfcb069c5c/android-responsive-20260810/settings-monitoring.png`
  - `/Users/simon/.codex/visualizations/2026/08/08/019fe1fa-84a8-7de3-8a51-56bfcb069c5c/android-responsive-20260810/watchlist.png`
  - `/Users/simon/.codex/visualizations/2026/08/08/019fe1fa-84a8-7de3-8a51-56bfcb069c5c/android-responsive-20260810/screener.png`
  - `/Users/simon/.codex/visualizations/2026/08/08/019fe1fa-84a8-7de3-8a51-56bfcb069c5c/android-responsive-20260810/strategy-store.png`
