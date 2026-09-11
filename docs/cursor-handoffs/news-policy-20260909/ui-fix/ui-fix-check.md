# 资讯政策页窄屏布局 UI fix-check

- 层：用户台（`one-trading/frontend`）。未改数据台/后端/权限。
- 执行者：本轮唯一写入 Cursor。不是独立 UI 复核，也不是 Codex IAB。
- 请求/配置模型：Grok 4.6 Extra High。供应商 actual **未核验**。
- 备份：`/Users/simon/备份/codex/news-policy-ui-fix-20260909-182318`
- 数据独立复核：task `5613e51d` 技术 PASS，原样 `data-review-finish.json`。附加 UI 核对 PING 超时，**不在此 PASS 范围**。
- `7d39a518` / `c89fcd1c` 保持失败。`1eab309c` 超时不是通过。
- fingerprint `35b397ea…` 仅历史。当前 candidate 以 controller 为准。
- **不是** accepted / production / verified browser。

## 主审证据（改前）

- URL：`http://127.0.0.1:3041/news?tab=policy`
- viewport：678x863
- 点央行后 AX 15 条，视觉正文不可读
- 结果 SECTION `flex min-h-0 flex-col overflow-hidden rounded-card...` rect `{x:12,y:861,w:654,h:2}`
- 上级 grid 单列 h739；侧栏占满可用高度

## 最小差异

`PolicyPanel.tsx` 仅 class：

- 根 grid：`grid-rows-[minmax(0,auto)_minmax(20rem,1fr)]` + `max-lg:overflow-y-auto`；`lg:grid-cols-[13rem_minmax(0,1fr)]` + `lg:grid-rows-none` 保持两列
- 侧栏：`max-lg:max-h-[min(22rem,40vh)] max-lg:overflow-y-auto`（82 部门仍在，可滚）
- 结果 SECTION：`min-h-[20rem]`（320px）+ `lg:min-h-0`

`News.tsx` 未改。未改 props / API / 缓存 / 取数 / 定时 / 路由 / 导航 / 用户偏好。未装依赖。未启动外部 Chrome/Playwright。未重跑后端。未改 `runtime.json`。

## 测试（亲眼看到）

```
pnpm exec vitest run \
  src/pages/__tests__/News.test.tsx \
  src/lib/__tests__/navGroups.test.ts \
  src/components/__tests__/Layout.mobile.test.tsx
→ Test Files 3 passed / Tests 33 passed
```

News 6（含新增 class 契约）、navGroups 8、Layout.mobile 19。Layout 既有 `data-sources` queryFn stderr，不是本轮失败。

jsdom **不能**验证 678x863 真实几何；契约只锁 class。最终几何由主审 IAB 验结果区 >=320px 与可见列表。未跑 frontend build（controller 会跑）。

## 当前运行身份

| 面 | PID | 说明 |
| --- | --- | --- |
| 3041 | **97951** | Vite，HMR；未重启 |
| 3048 | **97934** | 无 reload，`DATA_DIR=news-isolated-20260909`，后台关；未重启 |
| 3011 / 3018 | 3528 / 3510 | 未动 |

## 仍待

- Codex IAB 真实几何（结果列表/日期/原文/搜索/刷新可读，>=320px）
- 独立 UI 复核
- 桌面 lg 两列无多余横向溢出（本执行端未在浏览器看）
