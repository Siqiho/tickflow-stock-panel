import { afterEach, describe, expect, it } from 'vitest'

import {
  clearPageContext,
  composePageContextMessage,
  formatPageContextPrompt,
  getPageContext,
  selectPageContextFocus,
  setPageContext,
} from '@/lib/pageContext'
import {
  buildConceptAnalysisPageContext,
  buildDashboardPageContext,
  buildIndustryAnalysisPageContext,
  buildLimitLadderPageContext,
  buildWatchlistPageContext,
  buildIndicesPageContext,
  buildReviewPageContext,
  buildScreenerPageContext,
  buildStockAnalysisPageContext,
  buildFinancialsPageContext,
  buildRegimePageContext,
  buildTradingPageContext,
  buildMonitorPageContext,
} from '@/lib/pageContextSnapshots'

afterEach(() => {
  clearPageContext()
})

describe('page context snapshots', () => {
  it('keeps the latest registered page and formats a bounded prompt', () => {
    const snapshot = buildLimitLadderPageContext({
      direction: 'up',
      asOf: '2026-08-18',
      filters: ['limit_up', 'main', '概念'],
      selectedTag: { fieldKey: 'concept', tag: '算力' },
      data: {
        as_of: '2026-08-18',
        tiers: [],
        counts: { up: 41, down: 6 },
      },
      tiers: [
        {
          boards: 3,
          count: 2,
          stocks: [
            { symbol: '000001.SZ', name: '平安银行', status: 'limit_up', change_pct: 0.1, consecutive_limit_ups: 3 },
            { symbol: '600519.SH', name: '贵州茅台', status: 'limit_up', change_pct: 0.1, consecutive_limit_ups: 3 },
          ],
        },
      ],
    })

    setPageContext(snapshot)
    expect(getPageContext()?.title).toBe('连板梯队')

    const prompt = formatPageContextPrompt(snapshot)
    expect(prompt).toContain('当前页面：连板梯队')
    expect(prompt).toContain('当前分析模块：概念 算力')
    expect(prompt).toContain('平安银行 000001.SZ')
    expect(prompt).toContain('limit_ladder')

    const message = composePageContextMessage(snapshot, '今天最强的是哪一梯队？')
    expect(message).toContain('用户问题：今天最强的是哪一梯队？')
    expect(message).toContain('3板')
  })

  it('summarizes the selected concept instead of dumping the whole matrix', () => {
    const snapshot = buildConceptAnalysisPageContext({
      asOf: '2026-08-18',
      search: '算力',
      sortMode: 'heat',
      totalGroups: 86,
      totalSymbols: 420,
      breadth: { up: 51, down: 28, flat: 7 },
      leading: [{ key: '算力', avgPct: 0.042, count: 18, leaderName: '中际旭创' }],
      falling: [{ key: '地产', avgPct: -0.021, count: 22 }],
      selected: {
        key: '算力',
        count: 18,
        avgPct: 0.042,
        heatScore: 81.2,
        totalAmount: 12_000_000_000,
        upCount: 14,
        downCount: 3,
        stocks: [
          { symbol: '300308.SZ', name: '中际旭创', change_pct: 0.1, leaderScore: 88 },
          { symbol: '300502.SZ', name: '新易盛', change_pct: 0.08, leaderScore: 76 },
        ],
      },
    })

    const prompt = formatPageContextPrompt(snapshot)
    expect(prompt).toContain('当前页面：概念分析')
    expect(prompt).toContain('当前分析模块：')
    expect(prompt).toContain('中际旭创 300308.SZ')
    expect(prompt).toContain('领跌 地产')
    expect(prompt).toContain('fund_flow_concepts')
  })
  it('summarizes the selected industry the same way as concept analysis', () => {
    const snapshot = buildIndustryAnalysisPageContext({
      asOf: '2026-08-19',
      search: '半导体',
      sortMode: 'heat',
      levelLabel: '2级行业',
      totalGroups: 40,
      totalSymbols: 380,
      breadth: { up: 22, down: 14, flat: 4 },
      leading: [{ key: '半导体', avgPct: 0.031, count: 24, leaderName: '中芯国际' }],
      falling: [{ key: '房地产', avgPct: -0.018, count: 18 }],
      selected: {
        key: '半导体',
        count: 24,
        avgPct: 0.031,
        heatScore: 74.5,
        totalAmount: 8_000_000_000,
        upCount: 18,
        downCount: 5,
        stocks: [{ symbol: '688981.SH', name: '中芯国际', change_pct: 0.06, leaderScore: 82 }],
      },
    })
    const prompt = formatPageContextPrompt(snapshot)
    expect(prompt).toContain('当前页面：行业分析')
    expect(prompt).toContain('当前分析模块：')
    expect(prompt).toContain('中芯国际 688981.SH')
    expect(prompt).toContain('fund_flow_boards')
  })

  it('summarizes the dashboard overview instead of dumping every panel', () => {
    const snapshot = buildDashboardPageContext({
      asOf: '2026-08-19',
      viewingNow: true,
      dataMode: 'official',
      emotion: { score: 62, label: '偏强' },
      breadth: { up: 2800, down: 1400, flat: 300, up_pct: 62.2 },
      limit: { limit_up: 41, limit_down: 6, broken: 12, max_boards: 7, seal_rate: 78, tiers: [{ boards: 3, count: 5 }] },
      conceptLeading: [{ name: '算力', avg_pct: 0.04, count: 18, leader: { name: '中际旭创' } }],
      industryLeading: [{ name: '半导体', avg_pct: 0.03, count: 24, leader: { name: '中芯国际' } }],
      topGainers: [{ symbol: '300308.SZ', name: '中际旭创', change_pct: 0.1 }],
    })
    const prompt = formatPageContextPrompt(snapshot)
    expect(prompt).toContain('当前页面：市场看板')
    expect(prompt).toContain('市场情绪')
    expect(prompt).toContain('热门概念 算力')
    expect(prompt).toContain('3板')
    expect(prompt).toContain('market_overview')
  })

  it('lets the user switch analysis modules from the page snapshot', () => {
    const snapshot = buildIndustryAnalysisPageContext({
      asOf: '2026-08-19',
      search: '',
      sortMode: 'heat',
      levelLabel: '2级行业',
      totalGroups: 40,
      totalSymbols: 380,
      breadth: { up: 22, down: 14, flat: 4 },
      leading: [{ key: '半导体', avgPct: 0.031, count: 24, leaderName: '中芯国际' }],
      falling: [{ key: '房地产', avgPct: -0.018, count: 18 }],
      selected: {
        key: '半导体',
        count: 24,
        avgPct: 0.031,
        heatScore: 74.5,
        totalAmount: 8_000_000_000,
        upCount: 18,
        downCount: 5,
        stocks: [{ symbol: '688981.SH', name: '中芯国际', change_pct: 0.06, leaderScore: 82 }],
      },
      selectedFocusId: 'focus',
      hasTreemap: true,
      topFlowName: '风电设备',
    })
    setPageContext(snapshot)
    expect(getPageContext()?.selectedFocusIds).toEqual([])
    selectPageContextFocus('focus')
    expect(getPageContext()?.focus).toContain('当前行业')
    selectPageContextFocus('pulse-up')
    expect(getPageContext()?.selectedFocusIds).toEqual(['focus', 'pulse-up'])
    expect(getPageContext()?.focus).toContain('当前行业')
    expect(getPageContext()?.focus).toContain('领涨主线')
    expect(formatPageContextPrompt(getPageContext()!)).toContain('当前分析模块：')
    expect(formatPageContextPrompt(getPageContext()!)).toContain('领涨主线')
  })

  it('covers the remaining market-data pages with selectable modules', () => {
    expect(buildWatchlistPageContext({
      total: 8,
      visible: 8,
      viewMode: 'table',
      rows: [{ symbol: '600000.SH', name: '浦发银行', change_pct: 0.02 }],
    }).title).toBe('自选股')
    expect(buildIndicesPageContext({ selectedSymbol: '000001.SH', selectedName: '上证指数', quoteCount: 4 }).focusOptions?.map(o => o.id)).toContain('chart')
    expect(buildReviewPageContext({ asOf: '2026-08-19', emotionLabel: '偏强', up: 2800, down: 1400 }).title).toBe('AI 复盘')
    expect(buildScreenerPageContext({ strategyCount: 3, hitCount: 12, rows: [{ symbol: '300308.SZ', name: '中际旭创' }] }).focusOptions?.some(o => o.id === 'hits')).toBe(true)
    expect(buildStockAnalysisPageContext({ symbol: '600519.SH', name: '贵州茅台' }).route).toBe('/stock-analysis')
    expect(buildFinancialsPageContext({ symbol: '600000.SH', name: '浦发银行', available: true }).focusOptions?.map(o => o.id)).toContain('detail')
    expect(buildRegimePageContext({ date: '2026-08-19', state: '偏强', score: 72, days: 250 }).title).toBe('市场环境')
    expect(buildTradingPageContext({ holdingCount: 1, holdings: [{ symbol: '600000.SH', quantity: 100 }] }).route).toBe('/trading')
    expect(buildMonitorPageContext({ alertTotal: 4, rulesCount: 2, filter: 'all' }).focusOptions?.map(o => o.id)).toEqual(['alerts', 'rules'])
    expect(buildDashboardPageContext({ asOf: '2026-08-19', emotion: { label: '偏强', score: 62 }, topGainers: [{ symbol: '300308.SZ', name: '中际旭创' }] }).focusOptions?.map(o => o.id)).toContain('pulse')
  })

})
