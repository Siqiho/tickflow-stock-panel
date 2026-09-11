/**
 * 集中管理所有 React Query key。
 *
 * - 新增查询只需在此加一行，所有消费方自动引用。
 * - SSE invalidation 基于 SSE_INVALIDATE_PREFIXES 列表，新增 key 无需改 useQuoteStream。
 */

// ===== Query Key 工厂 =====

export const QK = {
  // 全局 / 共享 (Layout 预取)
  capabilities:   ['capabilities'] as const,
  settings:       ['settings'] as const,
  endpoints:      ['endpoints'] as const,
  version:        ['version'] as const,
  preferences:    ['preferences'] as const,
  dataSources:    ['data-sources'] as const,
  capabilityMatrix: ['capability-matrix'] as const,
  quoteStatus:    ['quote-status'] as const,
  quoteInterval:  ['quote-interval'] as const,
  overviewMarket: (asOf?: string) => ['overview-market', asOf ?? 'latest'] as const,
  marketPulse:    (tradeDate?: string | null) => ['market-pulse', tradeDate ?? 'latest'] as const,
  hithinkSpecial: (tradeDate?: string | null) => ['hithink-special', tradeDate ?? 'latest'] as const,
  newsMarket:     ['news-market'] as const,
  newsPolicy:     (department = '', keyword = '', page = 1) =>
                    ['news-policy', department, keyword, page] as const,
  newsDepartments: ['news-departments'] as const,
  newsKeyDepartments: ['news-key-departments'] as const,
  indexQuotes:    ['index-quotes'] as const,
  indexList:      ['index-list'] as const,

  // Watchlist
  watchlist:            ['watchlist'] as const,
  watchlistGroups:      ['watchlist-groups'] as const,
  watchlistQuotes:      ['watchlist-quotes'] as const,
  watchlistEnriched:    (ext?: string) => ['watchlist-enriched', ext] as const,
  watchlistKlineBatch:  (symbols: string) => ['watchlist-kline-batch', symbols] as const,
  minuteBatch:          (symbols: string) => ['minute-batch', symbols] as const,
  abnormalOverview:     (minCloseness: number, limit: number) => ['abnormal-overview', minCloseness, limit] as const,
  abnormalIntraday:     (limit: number) => ['abnormal-intraday', limit] as const,
  instrumentSearch:     (q: string, assetTypes?: string) => ['instrument-search', q, assetTypes ?? 'stock'] as const,

  // Screener
  screener:             ['screener'] as const,
  screenerStrategies:   (assetType?: string) => ['screener-strategies', assetType ?? 'all'] as const,
  screenerCached:       (asOf?: string, ext?: string) => ['screener-cached', asOf ?? '', ext ?? ''] as const,
  screenerCachedSummary: ['screener-cached-summary'] as const,
  screenerCachedResult: (strategyId: string, asOf?: string, ext?: string) =>
    ['screener-cached-result', strategyId, asOf ?? '', ext ?? ''] as const,
  screenerKlineBatch:   (symbols: string) => ['screener-kline-batch', symbols] as const,
  marketSnapshot:       ['market-snapshot'] as const,
  limitLadder:          (asOf?: string) => ['limit-ladder', asOf] as const,

  // Backtest
  backtestStatus:       ['backtest-status'] as const,
  factorColumns:        ['backtest-factor-columns'] as const,
  factorLibrary:        (assetType: string) => ['factors-library', assetType] as const,
  miningRuns:           ['backtest-mining-runs'] as const,
  miningAvailability:   (assetType: string, profile: string, start: string, end: string) =>
                          ['backtest-mining-availability', assetType, profile, start, end] as const,
  miningRun:            (id: string) => ['backtest-mining-run', id] as const,
  miningResult:         (id: string) => ['backtest-mining-result', id] as const,
  miningConfig:         ['backtest-mining-config'] as const,
  researchCandidates:   ['research-candidates'] as const,
  strategyLinkOptions:  (assetType?: 'stock' | 'etf') => assetType
    ? ['strategy-link-options', assetType] as const
    : ['strategy-link-options'] as const,
  strategyDetail:       (id: string) => ['strategy-detail', id] as const,

  // Data / Pipeline
  dataReadiness:        ['data-readiness'] as const,
  dataStatus:           ['data-status'] as const,
  dataCatalog:          ['data-catalog'] as const,
  dataControlSummary:   ['data-control-summary'] as const,
  dataSourceProvenance: ['data-source-provenance'] as const,
  dataCatalogDataset:   (id: string) => ['data-catalog', 'dataset', id] as const,
  dataCatalogSchema:    (id: string) => ['data-catalog', 'schema', id] as const,
  dataCatalogRuns:      (id?: string) => id === undefined
    ? ['data-catalog', 'runs', 'all'] as const
    : ['data-catalog', 'runs', 'dataset', id] as const,
  pipelineJobs:         ['pipeline-jobs'] as const,
  pipelineJob:          (id: string) => ['pipeline-job', id] as const,
  extData:              ['ext-data'] as const,
  extDataRows:          (id: string, date?: string, limit?: number, columns?: string) => ['ext-data-rows', id, date, limit, columns] as const,
  analysisMenus:        ['analysis-menus'] as const,
  analysisMenu:         (id: string) => ['analysis-menu', id] as const,

  // Kline
  kline:                (symbol: string, start: string, end: string, extColumns?: string) =>
                           ['kline', symbol, start, end, extColumns ?? ''] as const,
  klineLatest:          (symbol: string) => ['kline-latest', symbol] as const,
  stockLevels:          (symbol: string, days?: number) => ['stock-levels', symbol, days ?? 120] as const,
  klineMinute:          (symbol: string, date: string) =>
                             ['kline-minute', symbol, date] as const,
  klineMinuteRange:     (symbol: string, days: number) =>
                             ['kline-minute-range', symbol, days] as const,
  indexDaily:           (symbol: string, start: string, end: string) =>
                             ['index-daily', symbol, start, end] as const,
  indexMinute:          (symbol: string, date: string) =>
                             ['index-minute', symbol, date] as const,

  // Schema
  extDataSchemaAll:     ['ext-data-schema-all'] as const,
  stockChips:           (symbol: string, days = 120, bins = 80, asOf?: string | null) =>
                           ['stock-chips', symbol, days, bins, asOf || 'latest'] as const,
  fundFlowBoards:       (top = 30) => ['fund-flow-boards', top] as const,
  fundFlowBoardsWindow: (days = 63, top = 8) => ['fund-flow-boards-window', days, top] as const,
  fundFlowConcepts:     (top = 30) => ['fund-flow-concepts', top] as const,
  fundFlowConceptsWindow: (days = 63, top = 8) => ['fund-flow-concepts-window', days, top] as const,
  fundFlowBoardHistory: (code: string, kind: 'board' | 'concept' = 'board', limit = 120) =>
    ['fund-flow-board-history', kind, code, limit] as const,
  fundFlowBoardIntraday:(code: string, kind: 'board' | 'concept' = 'board', tradeDate?: string) =>
    ['fund-flow-board-intraday', kind, code, tradeDate || 'latest'] as const,
  tableSchema:          (table: string) => ['table-schema', table] as const,

  // Custom Signals
  customSignals:        ['custom-signals'] as const,
  customSignalsOptions: ['custom-signals-options'] as const,

  // Monitor (监控规则 + 触发记录)
  monitorRules:         ['monitor-rules'] as const,
  monitorRuleOptions:   ['monitor-rule-options'] as const,
  lots:                 ['lots'] as const,
  lotsKline:            (symbols: string) => ['lots-kline', symbols] as const,
  alerts:               (source?: string) => ['alerts', source ?? ''] as const,

  // AI 大盘复盘
  reviewReports:        ['review-reports'] as const,
  aiHistory:            ['ai-history'] as const,

  // 概念涨幅轮动矩阵
  rpsRotation:          (days: number, kind: 'concept' | 'industry' = 'concept', level?: number) => ['rps-rotation', kind, level ?? 0, days] as const,
  regimeHistory:        (limit?: number) => ['regime-history', limit ?? 0] as const,
  regimeLatest:         ['regime-latest'] as const,
  regimeStates:         (days: number) => ['regime-states', days] as const,
  regimeCoverage:       ['regime-coverage'] as const,
  regimePhases:         (start?: string, end?: string) => ['regime-phases', start ?? '', end ?? ''] as const,
  regimeMainline:       (kind: string, start?: string, end?: string) => ['regime-mainline', kind, start ?? '', end ?? ''] as const,
  dimensionIntraday:    (id: string, field: string, value: string, date?: string) => ['dimension-intraday', id, field, value, date] as const,
  dimensionMembers:     (configId: string, field: string, value: string, date?: string | null) => ['dimension-members', configId, field, value, date ?? ''] as const,
} as const

// ===== SSE 应该 invalidate 的 key 前缀列表 =====
// 新增需要 SSE 推送的查询，只需在此加一行

// 行情一轮只作废快照总览及相关实时页。市场脉搏、资金流、官方池、告警不在此列。
export const SSE_INVALIDATE_PREFIXES = [
  'watchlist',
  'quote-status',
  'index-quotes',
  'overview-market',
  'limit-ladder',
  'screener',
] as const

/** 看板显示「实时」时，这两类查询必须跟报价钟走，不受页面 SSE 开关关掉。 */
export const ALWAYS_SSE_QUOTE_PREFIXES = ['quote-status', 'overview-market'] as const

export function quoteTickActivePrefixes(
  pages?: Record<string, boolean> | null,
): readonly string[] {
  return SSE_INVALIDATE_PREFIXES.filter((prefix) => {
    if ((ALWAYS_SSE_QUOTE_PREFIXES as readonly string[]).includes(prefix)) return true
    if (!pages) return true
    return pages[prefix] !== false
  })
}
