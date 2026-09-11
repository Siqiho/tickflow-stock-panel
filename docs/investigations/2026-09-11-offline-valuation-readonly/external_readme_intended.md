# 未应用 / 非本轮交付

本文与 `external_readme.diff` 只是 2026-09-11 首次落地时拟追加到外部旧报告的历史草稿。

**本轮（P2）不再尝试写入、也不把未更新旧报告写成待用户决策或验收阻断。**

外部旧报告保持不动：

`/Users/simon/Trading/下载数据/stockdb_quantdb_integration_review_20260906/README.md`

本轮权威增量只在：

- `/Users/simon/Trading/one-trading/docs/data-platform-development-log.md#offline-valuation-readonly-contract`
- `/Users/simon/Trading/one-trading/docs/investigations/2026-09-11-offline-valuation-readonly/`

新旧报告职责：外部 README 保留 2026-09-06 包评估正文；one-trading 本包目录与数据台日志记录 2026-09-11 查询契约。下面两段未落地，仅供对照。

## 顶部指针

> 2026-09-11 增量指针（不改下方 2026-09-06 历史证据正文）：估值历史原包只读查询契约与 4 样本对账见 one-trading `docs/data-platform-development-log.md#offline-valuation-readonly-contract` 与 `docs/investigations/2026-09-11-offline-valuation-readonly/`。本轮未重扫 80G、未重做两融 API、未写正式 DATA_DIR。

## 文末第 9 节

## 9. 2026-09-11 估值历史原包只读增量

本小节是增量指针，不修改第 1–8 节 2026-09-06 历史证据。权威工程状态见 one-trading `docs/data-platform-development-log.md#offline-valuation-readonly-contract`。

只读查询：`scripts/offline_valuation_query.py`，默认 root=`/Users/simon/Trading/下载数据/quant_data`，仅 `5_technical_derived/valuation/<symbol>.parquet`。4 样本实读 `000001.SZ`/`000338.SZ`/`600519.SH`/`300750.SZ`。与项目 `data/reference/valuation_daily` 在 2026-07-21..2026-08-12 并排对账：共同键 36，`close` 全相等；项目 PE/PB/PS/市值/股本为 null，不视为相等、不填 0、不 overlay。未重扫 80G，未执行修复 SQL overlay，未改源文件。
