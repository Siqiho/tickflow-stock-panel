---
name: financial-analysis
description: Produce a CFA-style A-share financial quality report.
version: 1.0.0
author: one-trading
license: proprietary
metadata:
  hermes:
    tags: [analysis, financial, quality]
    category: one-trading
    related_skills:
      - stock-analysis
      - market-recap
---

# Financial Analysis Skill

Use this skill when the user wants a company financial-quality report. Reproduce
the existing one-trading financial analyzer: a 15-year A-share CFA/CPA writing
for professional investors. The output is a quality rating, not a buy/sell call.

This skill does not save reports, refresh financials, or replace the financials
page. It only tells Hermes how to query the four financial tables and write the
same five-section report.

## When to Use

- The user asks about earnings quality, cash generation, leverage, growth, or
  whether the company is financially healthy.
- The request is about one listed company, not the whole market.

Do not use this skill for tape-first trading advice or a market recap.

## Prerequisites

- `one_trading_data_catalog` and `one_trading_data_query` must be available.
- Resolve an official symbol before writing the report.
- All four tables may be incomplete. Empty tables are data gaps, not a reason
  to invent numbers.

## How to Run

1. If the symbol is unknown, query `instrument_search`.
2. Query `financial_metrics`, `financial_income`, `financial_balance_sheet`,
   and `financial_cash_flow` with that `symbol`.
3. Keep the latest four periods, newest first. Amounts are in yuan; ratio
   fields are percentage points.
4. Optional: `financial_status` or `stock_financial_snapshot` only to explain
   coverage. Do not let a snapshot replace the four tables.
5. If every table is empty, stop. Say the financials are missing and the user
   needs to sync them first.
6. Write the report in the user language. Follow the structure below exactly.

## Quick Reference

| Need | View | Notes |
| --- | --- | --- |
| Profitability and growth | `financial_metrics`, `financial_income` | Latest 4 periods |
| Leverage and liquidity | `financial_balance_sheet` | Latest 4 periods |
| Cash conversion | `financial_cash_flow` | Compare with net profit |
| Coverage | `financial_status` | Explain gaps, do not fill them |

Judge with A-share common sense: ROE above 15% is strong, debt-to-asset above
70% is elevated, gross margin below 20% is weak.

## Procedure

Write Markdown for the five report sections. Target 800-1500 Chinese characters.
Every judgment must cite a figure and compare periods when more than one period
exists. Do not invent HTML, images, or extra code samples in the body.

After the disclaimer, if at least two comparable period figures exist, append
exactly one fenced JSON chart spec. Skip the chart when the series would be
invented or a required field is missing.

Use this shape only:

```json
{"type":"chart","chartType":"bar","title":"营收对比","as_of":"2025-12-31","source":"financial_income","unit":"","points":[{"label":"2024","value":120.5},{"label":"2025","value":138.2}]}
```

Rules for the chart spec:

- `type` must be `chart`.
- Prefer `bar` for period comparisons such as revenue, net profit, or ROE.
- Include `title`, period-end `as_of`, and `source` equal to the view used.
- `points` must be 2-8 real numbers copied from the queried tables.
- Never output a template name without points. Never output raw HTML or images.

### 1. 核心摘要(1-2 句)

Give the financial portrait: earnings quality, growth energy, and balance-sheet
health. End with 【综合评级:★★★☆☆】 using 1-5 stars.

### 2. 亮点(2-3 条)

List the strongest positive signals. Lead each item with a bold phrase and a
number.

### 3. 风险提示(2-3 条)

List the main risks: receivables, inventory, cash/profit mismatch, or rising
debt. Prefer caution over silence.

### 4. 分项诊断

Use a table with columns 维度 / 关键指标 / 判断:

- 盈利能力: ROE / ROA / 毛利率 / 净利率
- 成长性: 营收同比 / 净利润同比
- 偿债能力: 资产负债率 / 流动比率
- 现金流: 经营现金流净额 / 与净利润匹配度
- 营运效率: 存货周转率 when present

Each judgment is one of 优秀 / 良好 / 一般 / 偏弱 / 警惕, plus one sentence of
evidence.

### 5. 综合评估与展望

In 2-3 short paragraphs, state whether the company is 优秀 / 稳健 / 承压 /
恶化, name the driver, and say what to watch next. End with an investment
reference class: 高质量蓝筹 / 稳健成长 / 周期波动 / 财务承压 / 高风险.

End with:

> 本报告由 AI 基于公开财务数据生成,仅供参考,不构成任何投资建议。

Rules:

1. Cite numbers. Ban empty phrases.
2. Use multiple periods to show improvement or deterioration.
3. Cross-check operating cash versus profit, margin versus expenses, and debt
   versus assets.
4. If a field is missing, write 数据不足,无法判断. Never invent it.
5. Stay compact and scannable.

If the user named a focus, answer it inside this frame.

## Pitfalls

- Do not give buy/sell zones or stops. That belongs to `stock-analysis`.
- Do not recap the whole market. That belongs to `market-recap`.
- Do not claim this is a saved page report unless you read
  `analysis_history_report`.
- Do not use only one period when four periods are present.

## Verification

The answer names the official symbol, cites period ends from the queried
tables, follows the five headings, includes the star rating and disclaimer, and
contains no invented financials. If a chart spec is present, it is one JSON fence
after the disclaimer and its points come from the queried tables.
