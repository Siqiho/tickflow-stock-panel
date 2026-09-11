# 2026-09-11 估值历史原包只读查询契约

主台：数据台。本目录是 4 样本只读对账与 P2 契约证据，不是权威状态。权威入口：

- `/Users/simon/Trading/one-trading/docs/data-platform-development-log.md#offline-valuation-readonly-contract`
- 既有包评估（2026-09-06 历史正文，本轮不改）：`/Users/simon/Trading/下载数据/stockdb_quantdb_integration_review_20260906/README.md`

新旧报告职责：本目录 + 数据台开发日志记录 2026-09-11 查询契约与 4 样本对账；外部 README 只保留 2026-09-06 包评估。本轮不写外部 README，也不把未更新的旧报告写成待用户决策或验收阻断。`external_readme_intended.md` / `external_readme.diff` 是**未应用 / 非本轮交付**的历史拟稿，仅供对照。

本轮未重扫 80G，未重做两融 API，未写正式 `DATA_DIR`，未加载 StockDB 修复/前收盘 overlay。修复前 12 测试与四样本不能充当本轮验收。

## 查询

```text
backend/.venv/bin/python -B scripts/offline_valuation_query.py --symbol 000001.SZ --start 2026-07-21 --end 2026-08-12 --limit 5
backend/.venv/bin/python -B scripts/offline_valuation_query.py --audit --summary
```

`--audit` / `--summary` 默认只打印，不写文件。详细证据只显式写到本目录。

## 4 样本（本轮实读，不是全市场）

| symbol | rows | dates | neg PE | NaN/Inf | dup | finite identity exact | units |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| 000001.SZ | 2588 | 2016-01-04..2026-08-27 | 0 | 0 | 0 | 2530/2530 | unknown/unverified |
| 000338.SZ | 2588 | 2016-01-04..2026-08-27 | 0 | 0 | 0 | 2530/2530 | unknown/unverified |
| 600519.SH | 2588 | 2016-01-04..2026-08-27 | 0 | 0 | 0 | 2530/2530 | unknown/unverified |
| 300750.SZ | 1995 | 2018-06-11..2026-08-27 | 0 | 0 | 0 | 1995/1995 | unknown/unverified |

`total_mv == close * total_capital` 只记有限值恒等式一致性，不证明股/元或万股/万元，不换算原值。`dividend_rate` 不凭外观确认 ratio/percent。全市场覆盖只引用 2026-09-06 盘点：by_symbol 5554 文件 / 10,770,127 行 / 2016-01-04..2026-08-27。

## 与项目 `valuation_daily` 重叠（2026-07-21..2026-08-12）

正式库窗口：`/Users/simon/Trading/one-trading/data/reference/valuation_daily`。不用 isolated-runtime 数据证明正式库缺数。

- 外包窗口键 68，项目 4 样本键 36，共同 36，项目独有 0。
- 2026-08-03..08-12 项目分区约 507–509 行（范围采集），这 4 只不在其中。
- `close` 36/36 原值相等。`pe_ttm`/`pb`/`ps_ttm`/`total_mv`/`total_share` 项目侧全 null（`valuation_daily_v2` 设计 + `shares_pit_safe=false`）。null 不等于外包值，也不填 0，不 overlay。
- 二源 close 相等不是行情真值，也不是 PIT 通过。

## P2 契约（本轮）

1. `valuation/` 与 `5_technical_derived` 父级 symlink 以及最终文件 symlink 越出 resolved root 一律 `valuation_offline_symlink_escape`。
2. 空/错 Symbol 与空 time 稳定拒绝，不补成 requested_symbol，不默默过滤。
3. `time` 仅 Date/Datetime，数值列仅支持数值或 null；错误类型与重复 null time 为 `invalid_schema` / `invalid_identity`，不泄漏 traceback。
4. 字符串日期严格 `YYYY-MM-DD`；import API 的 `date`/`datetime` 可保留。`limit` 拒绝 bool 与非整数截断。
5. 单位 `unknown/unverified`；已移除 `inferred_share_and_cny`。
6. `fields.original` 为文件真实列；optional 缺失与「项目有、外包没有」分开展示。

## 检查

`backend/.venv/bin/python -B scripts/test_offline_valuation_query.py -v`：18 passed / exit 0。夹具只在 temp。同参查询 `000001.SZ` 2026-07-21..2026-08-12 limit=5 两次稳定。

读前/读后 26 个实读源/对账/SQL 文件 size/mtime/SHA 不变，见 `input_hashes_compare.json`。

外部旧报告保持不动。`external_readme_intended.md` / `external_readme.diff` 醒目标记为未应用、非本轮交付。
