import type { LimitLadderResult, LimitLadderStock, LimitLadderTier } from '@/lib/api'
import { fmtBigNum, fmtPct } from '@/lib/format'
import type { PageContextFocusOption, PageContextItem, PageContextSnapshot } from '@/lib/pageContext'

const MAX_LADDER_STOCKS = 24
const MAX_CONCEPTS = 8
const MAX_CONCEPT_STOCKS = 8

function stockLabel(stock: Pick<LimitLadderStock, 'symbol' | 'name'>) {
  return stock.name && stock.name !== stock.symbol
    ? `${stock.name} ${stock.symbol}`
    : stock.symbol
}

function stockDetail(stock: LimitLadderStock, direction: 'up' | 'down') {
  const parts: string[] = []
  if (stock.status) parts.push(stock.status)
  if (stock.change_pct != null) parts.push(fmtPct(stock.change_pct))
  const boards = direction === 'down' ? stock.consecutive_limit_downs : stock.consecutive_limit_ups
  if (boards != null) parts.push(direction === 'down' ? `${boards}连跌` : `${boards}板`)
  return parts.join(' · ') || undefined
}

export function buildLimitLadderPageContext(input: {
  data?: LimitLadderResult
  tiers: LimitLadderTier[]
  direction: 'up' | 'down'
  asOf: string
  filters: string[]
  selectedTag?: { fieldKey: 'concept' | 'industry'; tag: string } | null
  previewSymbol?: string | null
  previewName?: string
  empty?: boolean
}): PageContextSnapshot {
  const title = input.direction === 'down' ? '连跌梯队' : '连板梯队'
  const visibleStocks = input.tiers.flatMap(tier =>
    tier.stocks.map(stock => ({ tier: tier.boards, stock })),
  )
  const items: PageContextItem[] = []

  for (const tier of input.tiers.slice(0, 8)) {
    const names = tier.stocks.slice(0, 6).map(stock => stock.name || stock.symbol).join('、')
    items.push({
      label: input.direction === 'down'
        ? (tier.boards === 1 ? '首跌' : `${tier.boards}连跌`)
        : (tier.boards === 1 ? '首板' : `${tier.boards}板`),
      detail: `${tier.count} 只${names ? `，如 ${names}` : ''}`,
    })
  }

  for (const row of visibleStocks.slice(0, MAX_LADDER_STOCKS)) {
    items.push({
      label: stockLabel(row.stock),
      detail: stockDetail(row.stock, input.direction),
    })
  }

  const counts = input.data?.counts
  const summary = input.empty
    ? `当前日期暂无${title}数据`
    : `${input.asOf} ${title}，涨停 ${counts?.up ?? '—'} / 跌停 ${counts?.down ?? '—'}，当前可见 ${input.tiers.length} 个梯队、${visibleStocks.length} 只股票`

  const notes = [
    visibleStocks.length > MAX_LADDER_STOCKS
      ? `快照只带前 ${MAX_LADDER_STOCKS} 只可见股票，其余按梯队摘要保留`
      : undefined,
    input.previewSymbol
      ? `用户正在预览 ${input.previewName || input.previewSymbol} ${input.previewSymbol}`
      : undefined,
  ].filter((value): value is string => Boolean(value))

  return {
    route: '/limit-ladder',
    title,
    asOf: input.asOf || input.data?.as_of || null,
    summary,
    focus: input.selectedTag ? `${input.selectedTag.fieldKey === 'concept' ? '概念' : '行业'} ${input.selectedTag.tag}` : input.previewSymbol,
    filters: input.filters,
    items,
    notes,
    queryHint: 'limit_ladder',
    focusOptions: [
      { id: 'overview', label: '梯队总览', value: `${input.tiers.length} 个梯队` },
      { id: 'concepts', label: '概念分布', value: input.selectedTag?.fieldKey === 'concept' ? input.selectedTag.tag : null },
      { id: 'industries', label: '行业分布', value: input.selectedTag?.fieldKey === 'industry' ? input.selectedTag.tag : null },
      { id: 'ladder', label: title, value: `${visibleStocks.length} 只` },
      input.previewSymbol ? { id: 'preview', label: '当前预览', value: input.previewName || input.previewSymbol } : null,
    ].filter((option): option is { id: string; label: string; value: string | null } => Boolean(option)),
  }
}

type SectorKind = 'concept' | 'industry'

function buildSectorAnalysisPageContext(kind: SectorKind, input: {
  asOf?: string | null
  search: string
  sortMode: string
  levelLabel?: string
  totalGroups: number
  totalSymbols: number
  breadth: { up: number; down: number; flat: number }
  leading: Array<{ key: string; avgPct: number | null; count: number; leaderName?: string | null }>
  falling: Array<{ key: string; avgPct: number | null; count: number }>
  selected?: {
    key: string
    count: number
    avgPct: number | null
    heatScore: number
    totalAmount: number
    upCount: number
    downCount: number
    stocks: Array<{ symbol: string; name?: string | null; change_pct?: number | null; leaderScore?: number }>
  } | null
  selectedFocusId?: string | null
  topFlowName?: string | null
  hasTreemap?: boolean
  empty?: boolean
  hint?: string
}): PageContextSnapshot {
  const noun = kind === 'industry' ? '行业' : '概念'
  const title = kind === 'industry' ? '行业分析' : '概念分析'
  const route = kind === 'industry' ? '/industry-analysis' : '/concept-analysis'
  const queryHint = kind === 'industry' ? 'fund_flow_boards 或 market_snapshot' : 'fund_flow_concepts 或 market_snapshot'
  const selected = input.selected
  const strongestLabel = kind === 'industry' ? '最强行业' : '最强主线'
  const breadthLabel = kind === 'industry' ? '涨跌行业' : '涨跌板块'
  const focusOptions = [
    input.hasTreemap ? { id: 'treemap', label: `${noun}热力图`, value: selected?.key ?? `${input.totalGroups} 个${noun}` } : null,
    input.leading[0] ? { id: 'hero-strongest', label: strongestLabel, value: input.leading[0].key } : null,
    input.falling[0] ? { id: 'hero-risk', label: '最大风险', value: input.falling[0].key } : null,
    { id: 'hero-breadth', label: breadthLabel, value: `${input.breadth.up} / ${input.breadth.down}` },
    { id: 'hero-inflow', label: '主力净流入', value: input.topFlowName ?? null },
    { id: 'hero-leader', label: '龙头算法', value: '6 因子' },
    { id: 'fund-flow', label: `${noun}主力资金流向`, value: input.topFlowName ?? null },
    input.leading[0] ? { id: 'pulse-up', label: '领涨主线', value: input.leading[0].key } : null,
    input.falling[0] ? { id: 'pulse-down', label: '领跌方向', value: input.falling[0].key } : null,
    { id: 'matrix', label: `${noun}矩阵`, value: `${input.totalGroups} 个${noun}` },
    selected ? { id: 'focus', label: `当前${noun}`, value: selected.key } : null,
  ].filter((option): option is { id: string; label: string; value: string | null } => Boolean(option))
  const items: PageContextItem[] = []

  if (selected) {
    items.push({
      label: `当前${noun} ${selected.key}`,
      detail: `${selected.count} 只 · 均涨 ${fmtPct(selected.avgPct)} · 强度 ${selected.heatScore.toFixed(0)} · 成交 ${fmtBigNum(selected.totalAmount)} · ${selected.upCount}涨/${selected.downCount}跌`,
    })
    for (const stock of selected.stocks.slice(0, MAX_CONCEPT_STOCKS)) {
      items.push({
        label: stock.name && stock.name !== stock.symbol ? `${stock.name} ${stock.symbol}` : stock.symbol,
        detail: [fmtPct(stock.change_pct), stock.leaderScore != null ? `龙头分 ${stock.leaderScore.toFixed(0)}` : null].filter(Boolean).join(' · ') || undefined,
      })
    }
  }

  for (const item of input.leading.slice(0, MAX_CONCEPTS)) {
    items.push({
      label: `领涨 ${item.key}`,
      detail: `${item.count} 只 · ${fmtPct(item.avgPct)}${item.leaderName ? ` · 龙头 ${item.leaderName}` : ''}`,
    })
  }
  for (const item of input.falling.slice(0, 3)) {
    items.push({
      label: `领跌 ${item.key}`,
      detail: `${item.count} 只 · ${fmtPct(item.avgPct)}`,
    })
  }

  const summary = input.empty
    ? (input.hint || `当前没有可分析的${noun}数据`)
    : `${input.asOf ?? '最新'} ${title}${input.levelLabel ? ` · ${input.levelLabel}` : ''}，${input.totalGroups} 个${noun} / ${input.totalSymbols} 只标的，上涨 ${input.breadth.up} / 下跌 ${input.breadth.down}`

  return {
    route,
    title,
    asOf: input.asOf ?? null,
    summary,
    focus: selected?.key || input.search || null,
    focusOptions,
    selectedFocusId: input.selectedFocusId ?? (selected ? 'focus' : (input.hasTreemap ? 'treemap' : 'matrix')),
    filters: [
      input.levelLabel || null,
      input.search ? `搜索 ${input.search}` : null,
      `排序 ${input.sortMode}`,
    ].filter((value): value is string => Boolean(value)),
    items,
    notes: [
      input.totalGroups > MAX_CONCEPTS ? `${noun}矩阵只带最强 ${MAX_CONCEPTS} 条和当前选中${noun}` : undefined,
      selected && selected.stocks.length > MAX_CONCEPT_STOCKS
        ? `当前${noun}共 ${selected.count} 只，快照只带龙头分前 ${MAX_CONCEPT_STOCKS} 只`
        : undefined,
    ].filter((value): value is string => Boolean(value)),
    queryHint,
  }
}

export function buildConceptAnalysisPageContext(input: Parameters<typeof buildSectorAnalysisPageContext>[1]) {
  return buildSectorAnalysisPageContext('concept', input)
}

export function buildIndustryAnalysisPageContext(input: Parameters<typeof buildSectorAnalysisPageContext>[1]) {
  return buildSectorAnalysisPageContext('industry', input)
}

export function buildDashboardPageContext(input: {
  asOf?: string | null
  viewingNow?: boolean
  dataMode?: string | null
  indicatorsApprox?: boolean
  emotion?: { score?: number | null; label?: string | null; note?: string | null; partial?: boolean } | null
  breadth?: { up: number; down: number; flat: number; up_pct?: number; avg_pct?: number | null } | null
  limit?: { limit_up: number; limit_down: number; broken?: number; max_boards?: number; seal_rate?: number | null; source?: string | null; tiers?: Array<{ boards: number; count: number }> } | null
  amountTotal?: number | null
  indices?: Array<{ name?: string | null; symbol: string; change_pct?: number | null; last_price?: number | null }>
  conceptLeading?: Array<{ name: string; avg_pct: number; count: number; leader?: { name?: string | null; symbol?: string | null } | null }>
  industryLeading?: Array<{ name: string; avg_pct: number; count: number; leader?: { name?: string | null; symbol?: string | null } | null }>
  topGainers?: Array<{ symbol: string; name?: string | null; change_pct?: number | null }>
  topLosers?: Array<{ symbol: string; name?: string | null; change_pct?: number | null }>
  empty?: boolean
}): PageContextSnapshot {
  const items: PageContextItem[] = []
  if (input.emotion) {
    items.push({ label: '市场情绪', detail: [input.emotion.label ?? '—', input.emotion.score ?? '—', input.emotion.note].filter(Boolean).join(' · ') })
  }
  if (input.breadth) {
    items.push({
      label: '涨跌家数',
      detail: `${input.breadth.up}涨 / ${input.breadth.flat}平 / ${input.breadth.down}跌${input.breadth.up_pct != null ? ` · 上涨率 ${input.breadth.up_pct.toFixed(1)}%` : ''}`,
    })
  }
  if (input.limit) {
    const tiers = (input.limit.tiers ?? []).filter(t => t.boards >= 2).slice(0, 6)
    items.push({
      label: '涨停梯队',
      detail: `涨停 ${input.limit.limit_up} / 跌停 ${input.limit.limit_down} / 炸板 ${input.limit.broken ?? 0} · 最高 ${input.limit.max_boards ?? 0}板${input.limit.seal_rate != null ? ` · 封板率 ${input.limit.seal_rate.toFixed(0)}%` : ''}${input.limit.source === 'hithink_official_pool' ? ' · 同花顺官方池' : ''}`,
    })
    for (const tier of tiers) {
      items.push({ label: `${tier.boards}板`, detail: `${tier.count} 只` })
    }
  }
  for (const item of (input.indices ?? []).slice(0, 4)) {
    items.push({
      label: item.name || item.symbol,
      detail: [item.change_pct != null ? fmtPct(item.change_pct / 100) : null, item.last_price != null ? String(item.last_price) : null].filter(Boolean).join(' · ') || undefined,
    })
  }
  for (const item of (input.conceptLeading ?? []).slice(0, 5)) {
    items.push({
      label: `热门概念 ${item.name}`,
      detail: `${item.count} 只 · ${fmtPct(item.avg_pct)}${item.leader?.name ? ` · 龙头 ${item.leader.name}` : ''}`,
    })
  }
  for (const item of (input.industryLeading ?? []).slice(0, 5)) {
    items.push({
      label: `热门行业 ${item.name}`,
      detail: `${item.count} 只 · ${fmtPct(item.avg_pct)}${item.leader?.name ? ` · 龙头 ${item.leader.name}` : ''}`,
    })
  }
  for (const stock of (input.topGainers ?? []).slice(0, 5)) {
    items.push({
      label: `涨幅 ${(stock.name && stock.name !== stock.symbol) ? `${stock.name} ${stock.symbol}` : stock.symbol}`,
      detail: fmtPct(stock.change_pct),
    })
  }
  for (const stock of (input.topLosers ?? []).slice(0, 3)) {
    items.push({
      label: `跌幅 ${(stock.name && stock.name !== stock.symbol) ? `${stock.name} ${stock.symbol}` : stock.symbol}`,
      detail: fmtPct(stock.change_pct),
    })
  }

  const summary = input.empty
    ? '当前看板还没有可分析的市场总览'
    : `${input.asOf ?? '最新'} 市场看板${input.viewingNow ? ' · 当天' : ''}，情绪 ${input.emotion?.label ?? '—'} ${input.emotion?.score ?? '—'}，涨跌 ${input.breadth?.up ?? '—'}/${input.breadth?.down ?? '—'}，涨停 ${input.limit?.limit_up ?? '—'}/${input.limit?.limit_down ?? '—'}`

  const focusOptions: PageContextFocusOption[] = [
    { id: 'overview', label: '看板总览', value: input.emotion?.label ?? undefined },
    { id: 'indices', label: '指数条', value: input.indices?.[0]?.name ?? null },
    { id: 'kpis', label: '涨跌指标', value: input.breadth ? `${input.breadth.up} / ${input.breadth.down}` : null },
    { id: 'pulse', label: '市场脉搏', value: null },
    { id: 'breadth', label: '涨跌分布', value: input.breadth ? `${input.breadth.up}涨` : null },
    { id: 'radar', label: '情绪雷达', value: input.emotion?.label ?? null },
    { id: 'trend', label: '趋势强度', value: null },
    { id: 'hot-concept', label: '概念热度', value: input.conceptLeading?.[0]?.name ?? null },
    { id: 'hot-industry', label: '行业热度', value: input.industryLeading?.[0]?.name ?? null },
    { id: 'fund-flow', label: '板块资金流', value: null },
    { id: 'gainers', label: '涨幅榜', value: input.topGainers?.[0]?.name || input.topGainers?.[0]?.symbol || null },
    { id: 'losers', label: '跌幅榜', value: input.topLosers?.[0]?.name || input.topLosers?.[0]?.symbol || null },
    { id: 'turnover', label: '成交额榜', value: null },
    { id: 'active', label: '活跃换手', value: null },
    { id: 'limit', label: '涨停梯队', value: input.limit ? `涨停 ${input.limit.limit_up}` : null },
    { id: 'monitor', label: '监控中心', value: null },
  ]

  return {
    route: '/',
    title: '市场看板',
    asOf: input.asOf ?? null,
    summary,
    focus: input.conceptLeading?.[0]?.name || input.industryLeading?.[0]?.name || null,
    focusOptions,
    selectedFocusId: 'overview',
    filters: [
      input.dataMode === 'intraday_snapshot' ? '盘中快照' : null,
      input.indicatorsApprox ? '盘中近似指标' : null,
      input.viewingNow ? '查看当天' : (input.asOf ? `历史 ${input.asOf}` : null),
    ].filter((value): value is string => Boolean(value)),
    items,
    notes: [
      '快照只带看板当前可见的情绪、涨跌停、热门板块和榜单前几名',
      '需要完整连板或板块明细时，再查 limit_ladder / fund_flow_concepts / fund_flow_boards',
    ],
    queryHint: 'market_overview 或 limit_ladder',
  }
}

export function buildWatchlistPageContext(input: {
  asOf?: string | null
  total: number
  visible: number
  realtimeCount?: number
  pendingCount?: number
  viewMode: 'table' | 'card'
  filters?: string[]
  previewSymbol?: string | null
  previewName?: string
  rows: Array<{ symbol: string; name?: string | null; change_pct?: number | null; rt_pct?: number | null; rt_price?: number | null; close?: number | null }>
}): PageContextSnapshot {
  const items: PageContextItem[] = input.rows.slice(0, 12).map(row => ({
    label: row.name && row.name !== row.symbol ? `${row.name} ${row.symbol}` : row.symbol,
    detail: [fmtPct(row.rt_pct ?? row.change_pct), (row.rt_price ?? row.close) != null ? String(row.rt_price ?? row.close) : null].filter(Boolean).join(' · ') || undefined,
  }))
  return {
    route: '/watchlist',
    title: '自选股',
    asOf: input.asOf ?? null,
    summary: `自选 ${input.visible}/${input.total} 只${input.realtimeCount ? ` · 实时 ${input.realtimeCount}` : ''}${input.pendingCount ? ` · 待数据 ${input.pendingCount}` : ''}`,
    filters: [input.viewMode === 'card' ? '卡片视图' : '列表视图', ...(input.filters ?? [])],
    items,
    notes: input.total > 12 ? ['快照只带当前可见前 12 只'] : undefined,
    queryHint: 'watchlist',
    focusOptions: [
      { id: 'list', label: '自选列表', value: `${input.visible} 只` },
      input.filters?.length ? { id: 'filters', label: '当前筛选', value: input.filters[0] } : null,
      input.previewSymbol ? { id: 'preview', label: '当前预览', value: input.previewName || input.previewSymbol } : null,
    ].filter(Boolean) as PageContextFocusOption[],
  }
}

export function buildIndicesPageContext(input: {
  selectedSymbol?: string | null
  selectedName?: string | null
  selectedPct?: number | null
  selectedPrice?: number | null
  quoteCount?: number
  source?: string | null
  rangeStart?: string
  rangeEnd?: string
  dailyCount?: number
}): PageContextSnapshot {
  const selectedLabel = input.selectedName && input.selectedName !== input.selectedSymbol
    ? `${input.selectedName} ${input.selectedSymbol}`
    : (input.selectedSymbol ?? '未选择')
  return {
    route: '/indices',
    title: '指数',
    asOf: input.rangeEnd ?? null,
    summary: `指数 ${selectedLabel}${input.selectedPct != null ? ` · ${fmtPct(input.selectedPct / 100)}` : ''}${input.dailyCount ? ` · 日K ${input.dailyCount} 根` : ''}`,
    filters: [input.source ? `行情 ${input.source}` : null, input.rangeStart && input.rangeEnd ? `${input.rangeStart} 至 ${input.rangeEnd}` : null].filter((value): value is string => Boolean(value)),
    items: [
      { label: '当前指数', detail: [selectedLabel, input.selectedPrice != null ? String(input.selectedPrice) : null, fmtPct(input.selectedPct != null ? input.selectedPct / 100 : null)].filter(Boolean).join(' · ') },
      { label: '行情覆盖', detail: `${input.quoteCount ?? 0} 只` },
    ],
    queryHint: 'index_daily',
    focusOptions: [
      { id: 'list', label: '指数列表', value: `${input.quoteCount ?? 0} 只` },
      { id: 'chart', label: '指数日K', value: selectedLabel },
    ],
  }
}

export function buildReviewPageContext(input: {
  asOf?: string | null
  emotionLabel?: string | null
  emotionScore?: number | null
  up?: number
  down?: number
  limitUp?: number
  amount?: number | null
  requestedSymbol?: string | null
  requestedName?: string
  viewingTitle?: string | null
  generating?: boolean
}): PageContextSnapshot {
  return {
    route: '/review',
    title: 'AI 复盘',
    asOf: input.asOf ?? null,
    summary: `${input.asOf ?? '最新'} 复盘 · 情绪 ${input.emotionLabel ?? '—'}${input.emotionScore != null ? ` ${input.emotionScore}` : ''} · 涨跌 ${input.up ?? '—'}/${input.down ?? '—'}`,
    items: [
      { label: '市场摘要', detail: `涨 ${input.up ?? '—'} / 跌 ${input.down ?? '—'} · 涨停 ${input.limitUp ?? '—'} · 成交 ${fmtBigNum(input.amount)}` },
      input.requestedSymbol ? { label: '关注股票', detail: input.requestedName || input.requestedSymbol } : undefined,
      input.viewingTitle ? { label: '当前报告', detail: input.viewingTitle } : undefined,
    ].filter(Boolean) as PageContextItem[],
    queryHint: 'market_overview',
    focusOptions: [
      { id: 'summary', label: '市场摘要', value: input.emotionLabel ?? null },
      { id: 'report', label: input.generating ? '正在生成' : '复盘报告', value: input.viewingTitle ?? null },
      { id: 'history', label: '历史报告', value: null },
    ],
  }
}

export function buildScreenerPageContext(input: {
  asOf?: string | null
  strategyCount: number
  activeStrategy?: string | null
  hitCount: number
  showAll?: boolean
  previewSymbol?: string | null
  previewName?: string
  rows: Array<{ symbol: string; name?: string | null; score?: number | null; change_pct?: number | null }>
}): PageContextSnapshot {
  return {
    route: '/screener',
    title: '策略',
    asOf: input.asOf ?? null,
    summary: `策略池 ${input.strategyCount} 个 · ${input.showAll ? '全部命中' : (input.activeStrategy || '当前策略')} ${input.hitCount} 只`,
    filters: [input.showAll ? '全部策略' : input.activeStrategy || null].filter((value): value is string => Boolean(value)),
    items: input.rows.slice(0, 12).map(row => ({
      label: row.name && row.name !== row.symbol ? `${row.name} ${row.symbol}` : row.symbol,
      detail: [row.score != null ? `评分 ${row.score}` : null, fmtPct(row.change_pct)].filter(Boolean).join(' · ') || undefined,
    })),
    notes: input.hitCount > 12 ? ['快照只带命中前 12 只'] : undefined,
    queryHint: 'screener',
    focusOptions: [
      { id: 'pool', label: '策略池', value: `${input.strategyCount} 个` },
      { id: 'hits', label: '命中结果', value: `${input.hitCount} 只` },
      input.previewSymbol ? { id: 'preview', label: '当前预览', value: input.previewName || input.previewSymbol } : null,
    ].filter(Boolean) as PageContextFocusOption[],
  }
}

export function buildStockAnalysisPageContext(input: {
  symbol?: string | null
  name?: string
  close?: number | null
  bars?: number
  showHistory?: boolean
}): PageContextSnapshot {
  const label = input.name && input.symbol && input.name !== input.symbol ? `${input.name} ${input.symbol}` : (input.symbol || '未选择')
  return {
    route: '/stock-analysis',
    title: '个股分析',
    summary: input.symbol ? `${label}${input.close != null ? ` · 现价 ${input.close}` : ''}${input.bars ? ` · 日K ${input.bars} 根` : ''}` : '尚未选择个股',
    items: input.symbol ? [{ label: '当前个股', detail: label }] : [],
    queryHint: 'kline_daily',
    focusOptions: [
      { id: 'finder', label: '个股查找', value: label },
      { id: 'chart', label: '关键价位', value: input.symbol ?? null },
      { id: 'chips', label: '筹码分布', value: input.symbol ?? null },
      { id: 'flow', label: '个股资金流', value: input.symbol ?? null },
      { id: 'history', label: '历史报告', value: input.symbol ?? null },
    ].filter(Boolean) as PageContextFocusOption[],
  }
}

export function buildFinancialsPageContext(input: {
  symbol?: string | null
  name?: string
  available?: boolean
  provider?: string | null
}): PageContextSnapshot {
  const label = input.name && input.symbol && input.name !== input.symbol ? `${input.name} ${input.symbol}` : (input.symbol || '未选择')
  return {
    route: '/financials',
    title: '财务分析',
    summary: input.symbol ? `${label} 财务分析${input.provider ? ` · ${input.provider}` : ''}` : (input.available ? '财务数据已就绪，尚未选择个股' : '财务数据尚未同步'),
    items: input.symbol ? [{ label: '当前个股', detail: label }] : [],
    queryHint: 'financials',
    focusOptions: [
      { id: 'status', label: '数据概况', value: input.available ? '已就绪' : '未同步' },
      { id: 'search', label: '个股搜索', value: input.symbol ? label : null },
      { id: 'detail', label: '财务报表', value: input.symbol ? label : null },
      { id: 'history', label: '历史报告', value: null },
    ],
  }
}

export function buildRegimePageContext(input: {
  date?: string | null
  state?: string | null
  score?: number | null
  days?: number
  transitions?: number
}): PageContextSnapshot {
  return {
    route: '/regime',
    title: '市场环境',
    asOf: input.date ?? null,
    summary: `市场环境 ${input.state ?? '—'}${input.score != null ? ` · ${input.score} 分` : ''}${input.days ? ` · 近 ${input.days} 天` : ''}`,
    items: [
      { label: '最新状态', detail: [input.date, input.state, input.score != null ? `${input.score} 分` : null].filter(Boolean).join(' · ') },
      input.transitions != null ? { label: '状态转换', detail: `${input.transitions} 次` } : undefined,
    ].filter(Boolean) as PageContextItem[],
    queryHint: 'regime_history',
    focusOptions: [
      { id: 'latest', label: '最新状态', value: input.state ?? null },
      { id: 'timeline', label: '状态时间轴', value: input.days ? `近 ${input.days} 天` : null },
      { id: 'trend', label: '综合分趋势', value: null },
      { id: 'calendar', label: '日历热力图', value: null },
    ],
  }
}

export function buildTradingPageContext(input: {
  asOf?: string | null
  holdingCount: number
  totalCost?: number | null
  marketValue?: number | null
  pnl?: number | null
  holdings: Array<{ symbol: string; name?: string | null; quantity: number; pnl?: number | null }>
}): PageContextSnapshot {
  return {
    route: '/trading',
    title: '持仓',
    asOf: input.asOf ?? null,
    summary: `持仓 ${input.holdingCount} 只 · 市值 ${fmtBigNum(input.marketValue)} · 浮动盈亏 ${fmtBigNum(input.pnl)}`,
    items: input.holdings.slice(0, 12).map(row => ({
      label: row.name && row.name !== row.symbol ? `${row.name} ${row.symbol}` : row.symbol,
      detail: `${row.quantity} 股${row.pnl != null ? ` · 盈亏 ${fmtBigNum(row.pnl)}` : ''}`,
    })),
    queryHint: 'portfolio',
    focusOptions: [
      { id: 'summary', label: '持仓摘要', value: `${input.holdingCount} 只` },
      { id: 'holdings', label: '我的持仓', value: `${input.holdingCount} 只` },
    ],
  }
}

export function buildMonitorPageContext(input: {
  alertTotal: number
  rulesCount: number
  filter: string
}): PageContextSnapshot {
  return {
    route: '/monitor',
    title: '监控中心',
    summary: `触发记录 ${input.alertTotal} 条 · 规则 ${input.rulesCount} 条`,
    filters: [input.filter !== 'all' ? input.filter : null].filter((value): value is string => Boolean(value)),
    items: [
      { label: '触发记录', detail: `${input.alertTotal} 条` },
      { label: '监控规则', detail: `${input.rulesCount} 条` },
    ],
    queryHint: 'alerts',
    focusOptions: [
      { id: 'alerts', label: '触发记录', value: `${input.alertTotal} 条` },
      { id: 'rules', label: '监控规则', value: `${input.rulesCount} 条` },
    ],
  }
}
