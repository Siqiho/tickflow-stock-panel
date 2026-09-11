---
name: market-recap
description: Produce a structured A-share after-hours market recap.
version: 1.0.0
author: one-trading
license: proprietary
metadata:
  hermes:
    tags: [analysis, market, recap]
    category: one-trading
    related_skills:
      - stock-analysis
      - financial-analysis
---

# Market Recap Skill

Use this skill when the user wants an after-hours market recap. Reproduce the
existing one-trading market recap: a 15-year A-share strategist who turns
index structure, breadth, limit-up ladders, sector rotation, and emotion into
the next session's plan.

This skill does not save reports, refresh market data, or replace the review
page. It only tells Hermes how to query the same overview-family views and
write the same eight-section recap.

## When to Use

- The user asks how the market closed, what led, what failed, or how to
  position tomorrow.
- The request is about the whole tape, not one stock's financial quality.

Do not use this skill for a single-stock trading report or a company
financial-quality rating.

## Prerequisites

- `one_trading_data_catalog` and `one_trading_data_query` must be available.
- `market_overview` is the primary source and must share the dashboard
  `as_of` date.
- News is optional. If no news view is present, infer catalysts from tape
  shocks only. Do not invent headlines.

## How to Run

1. Query `market_overview`. If the user named a date, pass `as_of`.
2. If the overview is thin, add `limit_ladder`, `rps_rotation`,
   `fund_flow_boards`, and `fund_flow_concepts`. Use them to explain, not to
   contradict the overview date.
3. Optional: `index_quotes`, `market_pulse`, or `analysis_history` with
   `kind=review`. History is prior work, not today's tape.
4. If `market_overview` has no `as_of`, stop and say daily bars or index data
   are missing.
5. Write conclusions only. Do not narrate your method.
6. Write the report in the user language. Follow the structure below exactly.

## Quick Reference

| Need | View | Notes |
| --- | --- | --- |
| Index, breadth, emotion, sectors | `market_overview` | Required primary source |
| Limit-up ladder | `limit_ladder` | Highest boards and seal rate |
| Industry/concept strength | `rps_rotation` | Continuity, not just one-day spikes |
| Board/concept money flow | `fund_flow_boards`, `fund_flow_concepts` | Explain leadership |

Interpret amounts in the same units the view returns. Convert yuan to 亿元
when the overview does.

## Procedure

Write Markdown for the eight report sections. Target 1200-2000 Chinese characters.
Every judgment must cite a number. Do not recopy large raw tables, and do not
invent HTML, images, or extra code samples in the body.

After the disclaimer, if the overview or board/concept flow views contain at
least two numeric points, append exactly one fenced JSON chart spec. Skip the
chart if the series would mix dates or invent missing breadth numbers.

Use this shape only:

```json
{"type":"chart","chartType":"bar","title":"板块净流入","as_of":"2026-08-17","source":"fund_flow_concepts","unit":"","points":[{"label":"光通信","value":63.08},{"label":"CPO","value":38.8}]}
```

Rules for the chart spec:

- `type` must be `chart`.
- Prefer `bar` for board/concept net flow or up/down counts.
- Include `title`, `as_of` from `market_overview`, and `source` equal to the view used.
- `points` must be 2-12 real numbers copied from the queried views.
- Never output a template name without points. Never output raw HTML or images.

### 1. 一句话定调(1-2 句)

Name today's core conflict and state. End with 【明日基调:进攻 / 均衡 / 防守】.

### 2. 盘面总览

Cover Shanghai / Shenzhen / ChiNext, up/down counts, limit-up / broken-board /
limit-down structure, turnover, and the emotion label with one-sentence
evidence.

### 3. 指数结构

Who defended, who dragged, whether indexes moved together, nearby support or
resistance inferred from today's prints, and any volume-price divergence.

### 4. 板块主线

Leading boards and why they can continue; lagging boards and whether risk is
spreading; ladder height, seal rate, and broken-board rate as speculation
temperature.

### 5. 资金与情绪

Turnover regime, market breadth, MA participation, volume ratio, and whether
risk appetite is repairing or fading.

### 6. 消息催化

If news exists, keep only catalysts that change tomorrow's tape and mark
already priced versus still pending. If news is absent, infer from tape
shocks only. Do not write `[推断]` and do not invent a headline.

### 7. 明日交易计划

Give 进攻 / 均衡 / 防守, a coarse position range, what to follow or fade, and
one invalidation trigger such as an index level.

### 8. 风险提示

List the main watches. End with:

> 本报告由 AI 基于公开行情数据生成,仅供参考,不构成任何投资建议。交易有风险,入市需谨慎。

Rules:

0. Output conclusions only. No first-I-will method talk.
1. Cite numbers. Ban empty phrases.
2. Be directional. If the tape cannot support a call, say so.
3. Read index sync and volume first, then boards and emotion, then news.
4. Interpret tables; do not recopy them.
5. Every offensive plan needs an invalidation trigger.
6. Keep the recap scannable.

If the user named a focus, answer it inside this frame.

## Pitfalls

- Do not write a single-stock buy/sell map. That belongs to `stock-analysis`.
- Do not write a company quality rating. That belongs to `financial-analysis`.
- Do not claim this is the saved review-page report unless you read
  `analysis_history_report`.
- Do not mix dates from older pulse or fund-flow views into today's `as_of`.

## Verification

The answer cites `market_overview.as_of`, follows the eight headings, includes
the next-day stance and disclaimer, and does not invent news or missing
breadth numbers. If a chart spec is present, it is one JSON fence after the
disclaimer and its points come from the queried views.
