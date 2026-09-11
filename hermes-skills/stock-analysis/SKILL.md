---
name: stock-analysis
description: Produce a four-dimension A-share stock trading report.
version: 1.0.0
author: one-trading
license: proprietary
metadata:
  hermes:
    tags: [analysis, stock, trading]
    category: one-trading
    related_skills:
      - financial-analysis
      - market-recap
---

# Stock Analysis Skill

Use this skill when the user wants a single-stock trading report. Reproduce the
existing one-trading stock analyzer: a 15-year A-share trader who leads with
price action, then checks fundamentals. Do not invent a new report shape.

This skill does not place orders, save reports, refresh data, or replace the
stock-analysis page. It only tells Hermes how to query approved user-console
data and write the same six-section report.

## When to Use

- The user asks to analyze, review, or judge one stock.
- The request is about buy/sell zones, trend, support/resistance, or whether to
  watch, probe, hold, reduce, or avoid.
- The stock may arrive as a code, name, watchlist item, or recent context.

Do not use this skill for a full financial-quality rating, a market-wide recap,
or strategy-code generation.

## Prerequisites

- `one_trading_data_catalog` and `one_trading_data_query` must be available.
- Resolve an official symbol such as `300274.SZ` before writing the report.
- If the symbol is ambiguous, search first. Do not guess.

## How to Run

1. If the symbol is unknown, query `instrument_search` with the user text.
2. Query `stock_daily_analysis` with `symbol`, `days=90`, and `max_items=180`.
   Read `returned` / `available` / `first_date` / `last_date` first. Use those
   completed bars for the technical section. Do not query wide `stock_daily`.
   may truncate a larger window and return the wrong dates.
3. Query `stock_levels` with the same `symbol`.
4. Query `financial_metrics` and `financial_income` with the same `symbol`.
   Use only the latest two periods. If either view is empty, treat fundamentals
   as unavailable.
5. Optional context only: `stock_quotes`, `stock_fund_flow`, or
   `analysis_history` for this symbol. History is prior work, not live data.
6. Write the report in the user language. Follow the structure below exactly.

## Quick Reference

| Need | View | Notes |
| --- | --- | --- |
| Daily bars and indicators | `stock_daily_analysis` | `days=90`, `max_items=180` |
| Support and resistance | `stock_levels` | Required for buy/stop prices |
| Light fundamentals | `financial_metrics`, `financial_income` | Latest 2 periods only |
| Name or code lookup | `instrument_search` | Do not guess the symbol |

Required daily fields when present: `date`, `open`, `high`, `low`, `close`,
`volume`, `change_pct`, `ma5`, `ma10`, `ma20`, `ma60`, `macd_dif`, `macd_dea`,
`macd_hist`, `kdj_k`, `kdj_d`, `kdj_j`, `rsi_6`, `rsi_14`, `rsi_24`,
`boll_upper`, `boll_mid`, `boll_lower`, `atr_14`, `vol_ratio_5d`,
`turnover_rate`, `consecutive_limit_ups`, plus limit-up, MACD, MA, volume, and
Bollinger signals.

## Procedure

Write Markdown for the six report sections. Target 1000-1800 Chinese characters.
Every claim must cite a number from the queried views. Do not invent HTML, images,
or extra code samples in the body.

After the disclaimer, if the queried views contain at least two numeric points
that help the user see the tape, append exactly one fenced JSON chart spec. Skip
the chart if daily bars are missing or the series would be invented.

Use this shape only:

```json
{"type":"chart","chartType":"line","title":"近端收盘","as_of":"2026-08-14","source":"stock_daily_analysis","unit":"","points":[{"label":"07-10","value":12.3},{"label":"08-14","value":13.1}]}
```

Rules for the chart spec:

- `type` must be `chart`.
- `chartType` is `line` for closes / moving averages, `bar` for volume or net flow.
- Include `title`, `as_of` or last bar date, and `source` equal to the view used.
- `points` must be 2-24 real numbers copied from the queried rows. Prefer recent
  `date` + `close` from `stock_daily_analysis`.
- Never output a template name without points. Never output raw HTML or images.

### 1. 一句话定调(1-2 句)

State the technical condition and trading character. End with
【操作建议:观望 / 轻仓试探 / 逢低吸纳 / 持有 / 减仓 / 规避】.

### 2. 技术面分析(核心维度)

Cover trend, structure, indicator signals, and volume-price behavior. Cite
values such as MA alignment, MACD cross, RSI, Bollinger position, and volume
ratio.

### 3. 关键价位(买卖区间)

List first/second resistance and support with strength. Give a concrete buy
zone and stop based on `stock_levels`. Do not invent prices.

### 4. 基本面与财务面(辅助验证)

Keep this to 2-4 sentences: ROE/gross margin quality, growth, and whether
fundamentals confirm or contradict the tape.

If financial views are empty, write exactly:

> 财务面分析能力正在接入中。当前版本(Free)未同步该标的的财务报表,基本面维度暂无法评估。
> 技术面分析不依赖财务数据,以下结论依然有效;升级套餐或等待财务数据同步后可补充本维度。

Never fabricate ROE, growth, or other financial numbers.

### 5. 消息面(价量异动推断)

There is no news feed. Infer only from tape shocks and label them `[推断]`.
If the tape is quiet, say so. Do not invent headlines.

### 6. 综合研判与操作建议

Name the stage, compare downside to support versus upside to resistance, give
aggressive / balanced / conservative actions, and list the invalidation signal.

End with:

> 本报告由 AI 基于公开行情与财务数据生成,仅供参考,不构成任何投资建议。交易有风险,入市需谨慎。

Rules:

1. Tape first, fundamentals second.
2. Cite numbers. Ban empty phrases.
3. Be directional. If data cannot support a call, say so.
4. Put buy/stop prices on the provided levels.
5. Every buy idea needs a stop.
6. Keep the report scannable.

If the user named a focus, add one short response to that focus without
breaking the six sections.

## Pitfalls

- Do not write a CFA-style quality rating. That belongs to `financial-analysis`.
- Do not write a market-wide recap. That belongs to `market-recap`.
- Do not call missing page APIs, save a report, or claim this is the saved
  page report unless you actually read `analysis_history_report`.
- If `stock_daily_analysis.returned` is 0, stop and say local daily bars are missing.
- Do not fall back to wide `stock_daily` to pad 180 days.

## Verification

The answer names the official symbol, cites `as_of` or bar dates from the
queried views, follows the six headings, includes the disclaimer, and does not
invent financials or news. If a chart spec is present, it is one JSON fence after
the disclaimer and its points come from the queried views.
