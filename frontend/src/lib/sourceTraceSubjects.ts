/** 用户台数据板块到数据台 subject_id 的只读映射。 */
export type SourceTraceSubject = {
  id: string
  label: string
}

export const SOURCE_TRACE = {
  quoteSnapshot: [{ id: 'quote_snapshot', label: '统一行情快照' }],
  stockEnriched: [{ id: 'stock_enriched', label: '股票增强日线' }],
  stockDaily: [{ id: 'stock_daily', label: '股票日线行情' }],
  marketOverview: [
    { id: 'quote_snapshot', label: '统一行情快照' },
    { id: 'stock_enriched', label: '股票增强日线' },
  ],
  conceptMembership: [{ id: 'ext_gn_ths', label: '概念归属' }],
  industryMembership: [{ id: 'ext_hy_ths', label: '行业归属' }],
  conceptAnalysis: [
    { id: 'ext_gn_ths', label: '概念归属' },
    { id: 'quote_snapshot', label: '统一行情快照' },
  ],
  industryAnalysis: [
    { id: 'ext_hy_ths', label: '行业归属' },
    { id: 'quote_snapshot', label: '统一行情快照' },
  ],
  industryHeatmap: [
    { id: 'ext_hy_ths', label: '行业归属' },
    { id: 'quote_snapshot', label: '统一行情快照' },
    { id: 'stock_enriched', label: '股票增强日线' },
  ],
  conceptFundFlow: [{ id: 'ext_fund_flow_concept', label: '概念资金流快照' }],
  industryFundFlow: [{ id: 'ext_fund_flow_bk', label: '行业资金流快照' }],
  stockFundFlow: [{ id: 'ext_fund_flow_stock', label: '个股资金流' }],
  marketPulse: [{ id: 'market_pulse', label: '市场脉搏' }],
  hithinkLimitPool: [{ id: 'hithink_limit_pool', label: '同花顺官方涨跌停池' }],
  limitUpEvents: [{ id: 'limit_up_events', label: '涨跌停事件' }],
  limitLadder: [
    { id: 'limit_up_events', label: '涨跌停事件' },
    { id: 'ext_gn_ths', label: '概念归属' },
    { id: 'ext_hy_ths', label: '行业归属' },
  ],
  financials: [
    { id: 'financial_metrics', label: '财务指标' },
    { id: 'financial_income', label: '利润表' },
    { id: 'financial_balance_sheet', label: '资产负债表' },
    { id: 'financial_cash_flow', label: '现金流量表' },
    { id: 'financial_shares', label: '股本结构' },
  ],
  watchlist: [
    { id: 'quote_snapshot', label: '统一行情快照' },
    { id: 'stock_enriched', label: '股票增强日线' },
  ],
  indices: [
    { id: 'index_instruments', label: '指数基础资料' },
    { id: 'index_daily', label: '指数日线行情' },
  ],
  screener: [{ id: 'stock_enriched', label: '股票增强日线' }],
  chips: [{ id: 'stock_daily', label: '股票日线行情' }],
} as const satisfies Record<string, readonly SourceTraceSubject[]>

export function sourceTracePath(subjectId: string): string {
  return `/data?section=source-trace&trace=${encodeURIComponent(subjectId)}`
}
