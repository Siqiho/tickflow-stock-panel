# 2026-09-12 QuantDB 估值只读 CLI 恢复与有界核验

主台：数据台。本目录是恢复后的有界核验证据，不是全市场扫描，也不是 API/Provider 实现。权威入口：

- `/Users/simon/Trading/one-trading/docs/data-platform-development-log.md#offline-valuation-readonly-contract`

恢复源（最终 post-P2，未改写）：

- `/Users/simon/备份/codex/20260911-restore-pre-cursor-before-20260911T224838/overwritten-or-removed/scripts/offline_valuation_query.py`
- `/Users/simon/备份/codex/20260911-restore-pre-cursor-before-20260911T224838/overwritten-or-removed/scripts/test_offline_valuation_query.py`

写前备份：`/Users/simon/备份/codex/20260912-offline-valuation-readonly-restore-before-wf1`

本轮未重扫 80G，未物理合并，未写原包或正式 `DATA_DIR`，未加载 StockDB 修复/前收盘 overlay，未改 2026-09-11 历史证据目录。四样本结果不得外推全市场、真值、单位或 PIT。

## 检查摘要

- 18-test：passed=True（`tests.txt` 记录 Ran 18 tests / OK）
- stdout 两次稳定：True sha=a7247052e5036e72f684563939b8a9f6a2e83a871fd9533ab45161cc8a84189b
- 26 个相关输入 before/after 不变：True
- `.env` sha 不变（未暴露内容）：True
- 2026-09-11 历史证据目录不变：True
