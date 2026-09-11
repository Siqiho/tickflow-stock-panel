// 后端 API 客户端 — 全项目统一入口
//
// Dev:Vite 代理 /api 到 :3018
// Prod:同源(FastAPI 托管前端 dist)

import { toast } from '@/components/Toast'
import { logApiCall } from '@/lib/runtimeLogger'
import type { MarketPhase, MonitorExtFieldItem } from './api-v02'
const BASE = ''

// 后端错误 detail 可能是字符串, 也可能是 {code, message} 等对象;
// 必须归一化为字符串, 否则对象会被塞进 toast/JSX 渲染并击穿整个路由树。
function errorDetailToText(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object') {
    const obj = detail as Record<string, unknown>
    if (typeof obj.message === 'string' && obj.message) return obj.message
    if (typeof obj.detail === 'string' && obj.detail) return obj.detail
    try { return JSON.stringify(detail) } catch { return '' }
  }
  return ''
}

function extractErrorMessage(rawBody: string, fallback: string): string {
  try {
    const parsed = JSON.parse(rawBody) as Record<string, unknown>
    return errorDetailToText(parsed.detail ?? parsed.message ?? '') || fallback
  } catch {
    return fallback
  }
}

function summarizeRequestBody(body: BodyInit | null | undefined): unknown {
  if (body == null) return undefined
  if (typeof body !== 'string') {
    if (typeof FormData !== 'undefined' && body instanceof FormData) return { type: 'FormData' }
    return { type: typeof body }
  }
  if (body.length > 800) return body.slice(0, 800) + '…'
  try {
    const parsed = JSON.parse(body) as Record<string, unknown>
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(parsed || {})) {
      const key = k.toLowerCase()
      if (key.includes('password') || key.includes('secret') || key.includes('token') || key.includes('api_key')) {
        out[k] = '***'
      } else {
        out[k] = v
      }
    }
    return out
  } catch {
    return body
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = init?.body instanceof FormData
  const headers: Record<string, string> = {}
  if (!isFormData) headers['Content-Type'] = 'application/json'
  const method = (init?.method || 'GET').toUpperCase()
  const started = performance.now()
  const reqBody = method === 'GET' || method === 'HEAD' ? undefined : summarizeRequestBody(init?.body ?? null)
  try {
    const res = await fetch(`${BASE}${path}`, { ...init, headers })
    const duration_ms = performance.now() - started
    if (!res.ok) {
      const msg = extractErrorMessage(await res.text(), `${res.status} ${res.statusText}`)
      logApiCall({
        method,
        path,
        status: res.status,
        ok: false,
        duration_ms,
        requestBody: reqBody,
        error: msg,
      })
      // 401 (未登录/会话过期) 不弹 toast — 由全局认证拦截器统一跳登录页, 避免刷屏
      if (res.status !== 401) toast(msg, 'error')
      throw new Error(msg)
    }
    logApiCall({
      method,
      path,
      status: res.status,
      ok: true,
      duration_ms,
      requestBody: reqBody,
    })
    return res.json() as Promise<T>
  } catch (err) {
    const duration_ms = performance.now() - started
    // 已在 !res.ok 分支记录过的 Error 不再重复
    if (!(err instanceof Error && (err as any)._apiLogged)) {
      // network failures only
      if (!(err instanceof Error && err.message && !err.message.includes(' '))) {
        /* fallthrough */
      }
    }
    // 仅对真正的网络异常补一条(非我们 throw 的业务 Error)
    if (err instanceof TypeError) {
      logApiCall({
        method,
        path,
        ok: false,
        duration_ms,
        requestBody: reqBody,
        error: err.message,
      })
    }
    throw err
  }
}


// ===== Runtime logs =====
export interface RuntimeLogItem {
  id: string
  ts: string
  source: string
  level: string
  category: string
  message: string
  process_id?: string
  logger?: string
  session_id?: string
  path?: string
  method?: string
  status?: number
  duration_ms?: number
  detail?: Record<string, unknown>
  change?: Record<string, unknown>
}

// ===== Capabilities =====
export interface CapabilityLimits {
  rpm: number | null
  batch: number | null
  subscribe: number | null
  view_only?: boolean
}

export type FeatureAvailability = {
  available: boolean
  status: string
  reason?: string | null
  reason_code?: string
  capability?: Record<string, boolean>
  user_enabled?: boolean | null
  full_market_sync_allowed?: boolean
  single_symbol_fallback?: string | null
  fallback_hint?: string | null
  view_available?: boolean
  source?: string
  mode?: string
  fallback?: string | null
}

export type CapabilitiesResponse = {
  label: string
  capabilities: Record<string, CapabilityLimits & { source?: string; local?: boolean }>
  features?: {
    daily?: FeatureAvailability
    minute?: FeatureAvailability
    adj_factor?: FeatureAvailability & { source?: string }
    financial?: FeatureAvailability & { source?: string }
    depth?: FeatureAvailability
    quote?: FeatureAvailability
    websocket?: FeatureAvailability
  }
  daily?: FeatureAvailability
  minute?: FeatureAvailability
  /** convenience mirrors of features.* for UI */
  financial?: FeatureAvailability & { source?: string }
  adj_factor?: FeatureAvailability & { source?: string }
  depth?: FeatureAvailability
  quote?: FeatureAvailability
  websocket?: FeatureAvailability
}

// ===== Financials =====
export interface FinancialStatus {
  provider?: string
  local_ready?: boolean

  available: boolean
  tables: Record<string, { rows: number; symbols: number }>
  last_sync: Record<string, string>
  /** 服务端是否正在同步(手动触发)——驱动"同步中"UI 并防重复点击 */
  syncing?: boolean
}

export interface FinancialMetricRecord {
  symbol?: string
  period_end: string
  announce_date?: string | null
  eps_basic?: number | null
  eps_diluted?: number | null
  bps?: number | null
  ocfps?: number | null
  roe?: number | null
  roe_diluted?: number | null
  roa?: number | null
  gross_margin?: number | null
  net_margin?: number | null
  debt_to_asset_ratio?: number | null
  revenue_yoy?: number | null
  net_income_yoy?: number | null
  operating_cash_to_revenue?: number | null
  inventory_turnover?: number | null
  [key: string]: any
}

export interface FinancialIncomeRecord {
  symbol?: string
  period_end: string
  announce_date?: string | null
  revenue?: number | null
  operating_cost?: number | null
  operating_profit?: number | null
  total_profit?: number | null
  net_income?: number | null
  net_income_attributable?: number | null
  basic_eps?: number | null
  diluted_eps?: number | null
  [key: string]: any
}

export interface FinancialBalanceSheetRecord {
  symbol?: string
  period_end: string
  announce_date?: string | null
  total_assets?: number | null
  total_current_assets?: number | null
  cash_and_equivalents?: number | null
  total_liabilities?: number | null
  total_equity?: number | null
  equity_attributable?: number | null
  [key: string]: any
}

export interface FinancialSharesRecord {
  symbol?: string
  period_end: string
  announce_date?: string | null
  total_shares?: number | null
  float_shares?: number | null
  source?: string | null
}

export interface FinancialCashFlowRecord {
  symbol?: string
  period_end: string
  announce_date?: string | null
  net_operating_cash_flow?: number | null
  net_investing_cash_flow?: number | null
  net_financing_cash_flow?: number | null
  capex?: number | null
  net_cash_change?: number | null
  [key: string]: any
}

export interface MarginTradingSyncResponse {
  symbols_requested: number
  symbols_with_data: number
  empty_symbols: string[]
  rows_fetched: number
  rows_published: number
  latest_trade_date: string | null
  artifact_path: string
  lineage_path: string
  catalog_refreshed: boolean
}

/** AI 财务分析历史报告 */
export interface AiFinancialReport {
  id: string
  symbol: string
  name: string
  focus: string
  content: string
  periods?: number
  summary?: string
  created_at: string
}

// ===== 个股分析 =====
export type LevelType = 'sr' | 'pivot' | 'extreme' | 'boll' | 'keltner_s' | 'keltner_m' | 'keltner_l' | 'atr_stop' | 'gap' | 'fib' | 'round'

export interface PriceLevel {
  value: number
  label: string
  type: LevelType
  side: 'resistance' | 'support' | 'neutral'
  strength?: 'strong' | 'medium' | 'weak'
  /** 档位(仅 pivot 有):0=P, 1=R1/S1, 2=R2/S2, 3=R3/S3。前端按"显示到第几档"过滤。 */
  rank?: number
}

/** 带状曲线指标(布林带/Keltner/ATR)的每日时间序列,与 dates 对齐。 */
export interface LevelSeries {
  boll?: { upper: (number | null)[]; lower: (number | null)[]; mid?: (number | null)[] }
  keltner_s?: { upper: (number | null)[]; lower: (number | null)[] }
  keltner_m?: { upper: (number | null)[]; lower: (number | null)[] }
  keltner_l?: { upper: (number | null)[]; lower: (number | null)[] }
  atr?: { stop_loss: (number | null)[]; take_profit: (number | null)[] }
}

export interface StockLevels {
  levels: Record<LevelType, PriceLevel[]>
  close: number | null
  summary: string
  symbol: string
  /** dates 与 series 对齐;前端按自身 rows 的日期映射,缺失填 null */
  dates?: string[]
  series?: LevelSeries
}

export interface AiStockReport {
  id: string
  symbol: string
  name: string
  focus: string
  content: string
  summary?: string
  close?: number | null
  levels?: Record<LevelType, PriceLevel[]>
  created_at: string
}

export interface AiPageReport {
  id: string
  title: string
  route: string
  as_of?: string | null
  focus: string
  summary?: string
  content: string
  session_id?: string
  created_at: string
}

// ===== Kline =====
export interface MinuteKlineRow {
  datetime: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount: number
}

export interface KlineRow {
  symbol?: string
  date: string
  open: number
  high: number
  low: number
  close: number
  volume?: number
  prev_close?: number | null
  change_amount?: number | null
  change_pct?: number
  ma5?: number | null
  ma20?: number | null
  ma60?: number | null
  macd_dif?: number | null
  macd_dea?: number | null
  macd_hist?: number | null
  rsi_14?: number | null
  vol_ratio_5d?: number | null
  [key: string]: any
}

// ===== Watchlist =====
export interface WatchlistEntry {
  symbol: string
  added_at: string
  note?: string
  name?: string | null
  group_ids?: string[]
  group_id?: string | null
}

export interface Quote {
  symbol: string
  price?: number
  pct?: number
  close?: number
  change_pct?: number
  [key: string]: any
}

export interface IndexInstrument {
  symbol: string
  name?: string | null
  code?: string | null
  asset_type?: 'index'
  [key: string]: any
}

export interface IndexQuote {
  symbol: string
  name?: string | null
  last_price?: number | null
  close?: number | null
  prev_close?: number | null
  change_pct?: number | null
  change_amount?: number | null
  open?: number | null
  high?: number | null
  low?: number | null
  volume?: number | null
  amount?: number | null
  timestamp?: number | null
  [key: string]: any
}

// ===== Screener =====
export interface ScreenerStrategy {
  id: string
  name: string
  description: string
  source?: string
  timeframes?: string[]
  asset_types?: string[]
}

export interface ScreenerResult {
  as_of: string
  strategy: string | null
  rows: any[]
  total: number
  elapsed_ms: number
}

export interface MarketSnapshotRow {
  symbol: string
  name?: string | null
  close?: number | null
  change_pct?: number | null
  amount?: number | null
  volume?: number | null
  turnover_rate?: number | null
  vol_ratio_5d?: number | null
  total_shares?: number | null
  float_shares?: number | null
  market_cap?: number | null
  float_market_cap?: number | null
  consecutive_limit_ups?: number | null
  [key: string]: any
}

export interface MarketSnapshotCoverageMarket {
  instruments: number
  priced: number
  coverage_pct: number
}

export interface MarketSnapshotCoverage {
  instrument_rows: number
  snapshot_rows: number
  priced_rows: number
  missing_rows: number
  coverage_pct: number
  markets: Record<string, MarketSnapshotCoverageMarket>
}

export interface MarketSnapshotResponse {
  as_of: string | null
  source: 'quote_snapshot+enriched' | 'quote_snapshot' | 'enriched' | 'none'
  fetched_at?: string | null
  scope?: string | null
  quality_status?: string[]
  coverage: MarketSnapshotCoverage
  rows: MarketSnapshotRow[]
}

export interface OverviewDimensionRankItem {
  name: string
  count: number
  avg_pct: number
  up_count: number
  down_count: number
  amount: number
  leader?: {
    symbol?: string | null
    name?: string | null
    change_pct?: number | null
  } | null
}

export interface OverviewMarket {
  as_of: string | null
  data_mode?: 'official' | 'intraday_snapshot' | null
  official_as_of?: string | null
  snapshot_as_of?: string | null
  available_as_of?: string | null
  indicators_source?: 'official' | 'intraday_approx' | null
  indicators_approx?: boolean
  quote_status: {
    enabled?: boolean
    running?: boolean
    quote_age_ms?: number | null
    is_trading_hours?: boolean
    [key: string]: any
  }
  indices: IndexQuote[]
  breadth: {
    total: number
    up: number
    down: number
    flat: number
    up_pct: number
    down_pct: number
    avg_pct?: number | null
    median_pct?: number | null
    strong_up?: number
    strong_down?: number
  }
  amount: { total: number; avg: number }
  boards: { board: string; count: number; up: number; down: number; up_pct: number; amount: number }[]
  limit: { limit_up: number; broken: number; failed: number; limit_down: number; max_boards: number; seal_rate?: number | null; tiers: { boards: number; count: number }[]; sealed_ready?: boolean; fake_up?: number; fake_down?: number; ready?: boolean; source?: 'official' | 'intraday_approx' | 'hithink_official_pool' | null; source_as_of?: string | null }
  distribution: { label: string; count: number; pct: number }[]
  trend: { above_ma5: number; above_ma20: number; above_ma60: number; above_ma5_pct: number; above_ma20_pct: number; above_ma60_pct: number; new_high: number; new_low: number; ready?: boolean; extremes_ready?: boolean }
  activity: { avg_turnover: number; high_turnover: number; high_vol_ratio: number | null; vol_ratio: number | null; vol_ready?: boolean }
  radar: { key: string; label: string; value: number | null; ready?: boolean }[]
  emotion: { score: number; label: string; partial?: boolean; ready_count?: number; note?: string | null }
  top_gainers: MarketSnapshotRow[]
  top_losers: MarketSnapshotRow[]
  turnover_leaders: MarketSnapshotRow[]
  active_leaders: MarketSnapshotRow[]
  concept_rank: { leading: OverviewDimensionRankItem[]; lagging: OverviewDimensionRankItem[] }
  industry_rank: { leading: OverviewDimensionRankItem[]; lagging: OverviewDimensionRankItem[] }
}

export interface MarketPulsePoint {
  event_id: string
  trade_date: string
  event_time: string
  minute: number
  benchmark_symbol: string
  benchmark_name: string
  last_price: number
  change_ratio: number
  preclose: number
  open: number
  volume: number
  amount: number
  source: string
  unit_version: string
}

export interface MarketPulseEvent {
  event_id: string
  trade_date: string
  event_time: string
  minute: number
  benchmark_symbol: string
  benchmark_name: string
  sector_code: string
  sector_name: string
  direction: 'up' | 'down'
  article_id: number
  source: string
  unit_version: string
}

export interface MarketPulseResponse {
  available: boolean
  requested_date: string | null
  resolved_date: string | null
  updated_at: string | null
  benchmark: { symbol: string; name: string }
  points: MarketPulsePoint[]
  events: MarketPulseEvent[]
  minute_rows: number
  event_rows: number
  source: 'local'
  producer: 'cls'
  unit_version: 'market_pulse_v1'
}

export interface MarketPulseSyncResult {
  requested_date: string
  resolved_date: string
  minute_rows: number
  event_rows: number
  rows_published: number
  artifact_path: string
  lineage_path: string
  catalog_refreshed: boolean
}

export type HithinkSyncTarget = 'limit_pool' | 'dragon_tiger' | 'auction' | 'valuation'

export interface HithinkDatasetPublishStats {
  dataset_id: string
  rows_published: number
  artifact_path: string
  lineage_path: string
  extra: Record<string, unknown>
}

export interface HithinkLocalQueryResponse {
  available: boolean
  dataset_id: string
  requested_date: string | null
  resolved_date: string | null
  rows: Record<string, unknown>[]
  row_count: number
  source: 'local'
  producer: 'hithink_fuyao'
  unit_version: string
  volume_unit?: 'lot' | null
  amount_unit?: 'CNY'
  history_guarantee?: 'latest_snapshot_only'
}

export interface HithinkSyncResult {
  requested_date: string
  resolved_date: string
  rows_published: number
  datasets: HithinkDatasetPublishStats[]
  catalog_refreshed: string[]
  source: 'hithink_fuyao'
}

// ===== 概念涨幅轮动矩阵 =====
// dates: 日期字符串列表(最新在最前); columns: {日期: [[概念名, 涨幅小数], ...]} 每列各自降序
export interface RpsRotationData {
  dates: string[]
  columns: Record<string, [string, number][]>
  concept_count: number
}

// ===== 大盘复盘 =====
export interface AiReviewReport {
  id: string
  as_of: string
  focus?: string
  content: string
  summary?: string
  emotion_score?: number | null
  emotion_label?: string
  created_at: string
}

// ===== Strategy Engine =====
export interface StrategyParamDef {
  id: string
  label: string
  type: 'float' | 'int' | 'select' | 'bool'
  default: number | string | boolean
  min?: number
  max?: number
  step?: number
  options?: string[]
}

export interface StrategyDetail {
  composite_children?: { strategy_id: string; weight: number }[] | null
  id: string
  name: string
  description: string
  tags: string[]
  source: 'builtin' | 'custom' | 'ai'
  version: string
  basic_filter: Record<string, any>
  params: StrategyParamDef[]
  params_defaults: Record<string, any>
  scoring: Record<string, number>
  scoring_directions?: Record<string, 'high' | 'low' | string>
  execution_backend?: string
  asset_types?: string[]
  timeframes?: string[]
  entry_signals: string[]
  exit_signals: string[]
  stop_loss: number | null
  take_profit: number | null
  trailing_stop: number | null
  trailing_take_profit_activate: number | null
  trailing_take_profit_drawdown: number | null
  max_hold_days: number | null
  display_limit?: number
  alerts: { field: string; op?: string; value?: number; message: string }[]
  order_by: string
  descending: boolean
  limit: number
  rules?: string
  owner_user_id?: string | null
}

// ===== Custom Signals (自定义信号) =====
export interface CustomSignalCondition {
  left: string     // 字段名
  op: string       // > >= < <= == !=
  right: string    // "field:xxx" 或数字字符串
  leftDays?: number
  rightDays?: number
}

export interface CustomSignal {
  id: string
  name: string
  kind: 'entry' | 'exit' | 'both'
  conditions: CustomSignalCondition[]
  enabled: boolean
}

export interface CustomSignalOptions {
  fields: { key: string; label: string }[]
  operators: string[]
  kinds: { key: string; label: string }[]
}

// ===== Monitor (监控规则 + 触发记录) =====
export interface MonitorCondition {
  field: string
  op: string              // truth | > >= < <= == !=
  value?: number | null   // op 非 truth 时必填
}

export interface MonitorRule {
  id: string
  name: string
  enabled: boolean
  type: 'strategy' | 'signal' | 'price' | 'market' | 'abnormal' | 'sector' | 'volume_delta'
  scope: 'symbols' | 'all' | 'sector' | 'watchlist_group'
  symbols: string[]
  sector?: string | null
  group_id?: string | null
  strategy_id?: string | null
  asset_type?: 'stock' | 'etf' | 'index' | string | null
  direction: 'entry' | 'exit' | 'both' | 'up' | 'down'
  conditions: MonitorCondition[]
  logic: 'and' | 'or'
  cooldown_seconds: number
  severity: 'info' | 'warn' | 'critical'
  message: string
  webhook_url?: string
  webhook_enabled?: boolean
  webhook_channels?: string[]
  runtime_warning?: string | null
  created_at?: string
  threshold_pct?: number | null
  threshold_amount?: number | null
  threshold_volume?: number | null
  window_minutes?: number | null
  sector_trigger?: string | null
  sector_targets?: Array<{ key?: string; kind?: string; name?: string; code?: string } | string>
  abnormal_window?: string | number | null
  metric?: string | null
  basic_filter?: Record<string, unknown> | null
  score_min?: number | null
  score_max?: number | null
  notify_events?: string[]
}

export interface MonitorRuleOptions {
  threshold_fields: { key: string; label: string }[]
  builtin_signals: { key: string; label: string }[]
  custom_signals: { key: string; label: string }[]
  operators: string[]
  types: { key: string; label: string }[]
  scopes: { key: string; label: string }[]
  logics: { key: string; label: string }[]
  severities: { key: string; label: string }[]
  directions: { key: string; label: string }[]
}

export interface AlertEvent {
  ts: number
  rule_id?: string
  rule_name?: string
  source: string
  type: string
  symbol?: string
  name?: string | null
  message: string
  price?: number | null
  change_pct?: number | null
  signals?: string[]
  severity?: string
  strategy_id?: string
  conditions?: MonitorCondition[]
  logic?: 'and' | 'or'
}

/** 生成监控规则 id (时间戳 + 随机后缀), 用户无需手动填写。 */
export function genRuleId(): string {
  const ts = Date.now().toString(36)
  const rand = Math.random().toString(36).slice(2, 6)
  return `mr_${ts}_${rand}`
}

// ===== Limit Ladder =====
export interface LimitLadderStock {
  symbol: string
  name?: string | null
  close?: number | null
  change_pct?: number | null
  consecutive_limit_ups?: number | null
  consecutive_limit_downs?: number | null
  status?: 'limit_up' | 'broken' | 'failed' | 'limit_down' | 'recovery' | null
  /** 五档 sealed: real=真封板, fake=假涨停(已归炸板), pending=待确认, null=降级/无能力 */
  sealed_status?: 'real' | 'fake' | 'pending' | null
  /** 封单量(买一/卖一量), 仅真封板有值 */
  sealed_vol?: number | null
}

export interface LimitLadderTier {
  boards: number
  count: number
  stocks: LimitLadderStock[]
}

export interface LimitLadderResult {
  as_of: string
  tiers: LimitLadderTier[]
  /** 双方向涨跌停计数(修正后, 不论当前 direction) */
  counts?: { up: number; down: number }
  /** 双方向涨跌停原始计数(修正前, 供弹窗对比) */
  counts_raw?: { up: number; down: number }
  /** sealed 数据是否就绪(false→前端显示降级标识) */
  sealed_ready?: boolean
  /** sealed 数据 age(秒), null=盘后定版或无数据 */
  sealed_age?: number | null
  /** sealed 修正统计: real=真封板, fake=假涨停(归炸板), pending=待确认 */
  sealed_counts?: { real: number; fake: number; pending: number }
  /** 涨停侧 sealed 明细 */
  sealed_counts_up?: { real: number; fake: number; pending: number }
  /** 跌停侧 sealed 明细 */
  sealed_counts_down?: { real: number; fake: number; pending: number }
}

// ===== Backtest =====
export interface BacktestResult {
  run_id: string
  config: any
  stats: Record<string, any>
  equity_curve: { date: string; value: number }[]
  trades: any[]
  per_symbol_stats: { symbol: string; total_return: number }[]
}

// ===== Factor Backtest =====
export interface FactorColumn {
  id: string
  label: string
  group: string
  desc: string
}

export interface GroupStat {
  group: number
  label: string
  total_return: number
  annual_return: number
  max_drawdown: number
  sharpe: number
  win_rate: number
}

export interface FactorBacktestResult {
  run_id: string
  config: Record<string, any>
  ic_mean: number | null
  ic_std: number | null
  ir: number | null
  ic_win_rate: number | null
  ic_series: { date: string; ic: number }[]
  group_stats: GroupStat[]
  group_nav: Record<string, any>[]
  long_short_stats: Record<string, any>
  long_short_nav: { date: string; value: number }[]
  elapsed_ms: number
  n_symbols: number
  n_dates: number
  error: string | null
}

// ===== Strategy Backtest =====
export interface StrategyBacktestTrade {
  symbol: string
  name?: string
  entry_date: string
  exit_date: string
  entry_price: number
  exit_price: number
  pnl_pct: number
  duration: number
  exit_reason: string
  shares?: number
  lots?: number
  position_pct?: number
  entry_value?: number
  exit_value?: number
  pnl_amount?: number
  entry_score?: number | null
  entry_signal_date?: string | null
  exit_signal_date?: string | null
  blocked_exit_days?: number
}

export interface StrategyBacktestResult {
  run_id: string
  config: Record<string, any>
  stats: Record<string, any>
  equity_curve: { date: string; value: number; cash?: number; positions?: number; exposure?: number }[]
  drawdown_curve: { date: string; value: number }[]
  benchmark_curve?: { date: string; value: number; close?: number; name?: string; symbol?: string }[]
  trades: StrategyBacktestTrade[]
  per_symbol_stats: {
    symbol: string
    n_trades: number
    total_return: number
    win_rate: number
    best: number
    worst: number
  }[]
  strategy_info: {
    id: string
    name: string
    description: string
    entry_signals: string[]
    exit_signals: string[]
    stop_loss: number | null
    take_profit: number | null
    trailing_stop: number | null
    trailing_take_profit_activate: number | null
    trailing_take_profit_drawdown: number | null
    score_min: number | null
    score_max: number | null
    max_hold_days: number | null
    source: string
  }
  elapsed_ms: number
  error: string | null
}

export interface StrategyBacktestHistoryItem {
  run_id: string
  saved_at: string
  strategy_id: string
  strategy_name: string
  strategy_source?: string | null
  strategy_owner_user_id: string
  start?: string | null
  end?: string | null
  total_return?: number | null
  trade_count: number
  error?: string | null
}

// ===== Portfolio (per-account ledger; no order execution) =====
export interface PortfolioHolding {
  symbol: string
  name?: string | null
  quantity: number
  avg_cost: number
  note: string
  close?: number | null
  change_pct?: number | null
  cost_value: number
  market_value?: number | null
  pnl_amount?: number | null
  pnl_pct?: number | null
  created_at: string
  updated_at: string
}

export interface PortfolioSnapshot {
  as_of: string | null
  holdings: PortfolioHolding[]
  summary: {
    holding_count: number
    priced_count: number
    total_cost: number
    total_market_value: number | null
    total_pnl: number | null
    total_pnl_pct: number | null
  }
}

// ===== Settings =====

/** 端点发现清单 —— 对应 tickflow.org/endpoints.json */
export interface EndpointItem {
  id: string
  url: string
  label: string
  region?: string
  description?: string
  premium?: boolean
}

export interface EndpointManifest {
  version?: number
  description?: string
  healthPath?: string
  /** 每端点测试轮数,用于 /health 多轮探测取中位数 */
  testRounds?: number
  endpoints: EndpointItem[]
  /** 数据来源:remote=远程拉取 / fallback=内置回退列表 */
  source?: 'remote' | 'fallback'
}

export interface AiSubscriptionSource {
  provider: string
  label: string
  website: string
  website_label: string
  description: string
  base_url: string
  default_base_url?: string
  default_model: string
  models: string[]
  ready: boolean
  active: boolean
  model: string
  credential_source?: 'server_oauth' | 'api_key' | null
  message: string
  has_api_key?: boolean
  api_key_masked?: string
}

export interface SettingsState {
  mode: 'none' | 'free' | 'api_key'
  tickflow_api_key_masked: string
  has_tickflow_key: boolean
  tier_label: string
  current_endpoint: string
  probe_log: string[]
  missing_caps: string[]
  extras_caps: string[]
  is_admin?: boolean
  credential_management?: 'owner' | 'admin_only'
  // 首次使用引导
  onboarding_completed: boolean
  // AI 配置
  ai_provider: string
  ai_base_url: string
  ai_api_key_masked: string
  has_ai_key: boolean
  ai_configured?: boolean
  ai_model: string
  ai_codex_command?: string
  ai_user_agent: string
  ai_access?: {
    mode: 'self_hosted' | 'cloud_subscription'
    state: 'active' | 'not_configured' | 'subscription_required' | 'service_unavailable'
    allowed: boolean
    entitled: boolean
    configured: boolean
    provider: string
    model: string
    plan?: string | null
    message: string
    credential_source?: 'server_oauth' | 'api_key' | null
  }
  ai_subscriptions?: AiSubscriptionSource[]
  ai_xai?: {
    auth_type?: string | null
    has_oauth?: boolean
    has_access_token?: boolean
    expires_at?: number | null
    expired?: boolean
  }
}

/** 保存 TickFlow Key 的响应(先探后存) */
export interface SaveTickflowKeyResult {
  ok: boolean
  /** ok=false 且 key 无效时的原因标识,前端据此提示「Key 无效」 */
  reason?: 'invalid'
  error?: string
  mode?: 'none' | 'free' | 'api_key'
  tier_label?: string
  current_endpoint?: string
  tickflow_api_key_masked?: string
  capabilities_count?: number
}


export type RegimeState = 'strong' | 'lean_strong' | 'range' | 'lean_weak' | 'weak'

export const REGIME_STATE_LABELS: Record<RegimeState, string> = {
  strong: '强势',
  lean_strong: '偏强',
  range: '震荡',
  lean_weak: '偏弱',
  weak: '弱势',
}

export const REGIME_STATE_COLORS: Record<RegimeState, string> = {
  strong: '#ef4444',
  lean_strong: '#f97316',
  range: '#6b7280',
  lean_weak: '#3b82f6',
  weak: '#10b981',
}

export const MARKET_PHASE_COLORS: Record<MarketPhase, string> = {
  ice: '#38bdf8',
  ignite: '#f59e0b',
  rally: '#ef4444',
  climax: '#d946ef',
  ebb: '#14b8a6',
  repair: '#94a3b8',
}

export const MARKET_PHASE_ORDER: MarketPhase[] = ['ice', 'ignite', 'rally', 'climax', 'ebb', 'repair']

export interface RegimeRow {
  date: string
  state: RegimeState
  score: number
  limit_up: number
  limit_down: number
  broken_limit: number
  max_consecutive: number
  seal_rate: number
  up_count: number
  down_count: number
  up_ratio: number
  index_pct: number
  above_ma20_pct: number
  total_amount: number
  avg_turnover: number
  avg_pct?: number
  median_pct?: number
  strong_up_pct?: number
  strong_down_pct?: number
  phase?: 'ice' | 'ignite' | 'rally' | 'climax' | 'ebb' | 'repair' | null
  first_board?: number | null
  ge2_count?: number | null
  promo_rate?: number | null
  promo_pool?: number | null
  ladder_completeness?: number | null
  profit_score?: number
  speculation_score?: number
  resilience_score?: number
  trend_score?: number
}

export interface RegimeHistory {
  rows: RegimeRow[]
  total: number
}

export interface RegimeStateItem {
  state: RegimeState
  label: string
  count: number
  pct: number
}

export interface RegimeStates {
  distribution: RegimeStateItem[]
  days: number
}

export interface RegimeCoverage {
  rows: number
  earliest_date: string | null
  latest_date: string | null
}

export interface WecomBotStatus {
  enabled: boolean
  running: boolean
  connected: boolean
  bot_id_configured: boolean
  secret_configured: boolean
  last_error: string
}

export interface WatchlistImportCandidate {
  code: string
  symbol: string | null
  name: string | null
  matched: boolean
  already_in_watchlist: boolean
}

export interface WatchlistImportResult {
  provider: string
  codes: string[]
  candidates: WatchlistImportCandidate[]
  matched_count: number
  unmatched_count: number
}

export interface Preferences {
  realtime_quotes_enabled: boolean
  indices_nav_pinned: boolean
  minute_sync_enabled: boolean
  minute_sync_days: number
  daily_data_provider?: string
  adj_factor_provider?: string
  financial_provider?: string
  financial_data_provider?: string
  pool_provider?: string
  minute_data_provider?: string
  realtime_data_provider?: string
  depth5_data_provider?: string
  watchlist_groups_in_nav?: boolean
  minute_refresh_enabled?: boolean
  minute_refresh_interval?: number
  minute_intraday_refresh?: boolean
  minute_intraday_refresh_interval?: number
  data_source_job_timeout_s?: number
  data_source_long_job_timeout_s?: number
  mining_schedule_enabled?: boolean
  mining_schedule_weekday?: number
  mining_budget_profile?: 'exploratory' | 'balanced' | 'strict'
  realtime_watchlist_symbols?: string[]
  realtime_pull_stock?: boolean
  realtime_pull_etf?: boolean
  realtime_pull_index?: boolean
  realtime_index_mode?: 'core' | 'all'
  realtime_index_symbols?: string[]
  pipeline_pull_a_share: boolean
  pipeline_pull_etf: boolean
  pipeline_pull_index: boolean
  pipeline_universe_scope?: string
  public_data_scope?: string
  financial_max_periods?: number
  pipeline_index_symbols: string
  pipeline_schedule: { hour: number; minute: number }
  pipeline_regime_enabled?: boolean
  regime_batch_days?: number
  regime_warmup_days?: number
  wecom_bot_id?: string
  wecom_bot_secret?: string
  wecom_bot_enabled?: boolean
  instruments_schedule: { hour: number; minute: number }
  enriched_batch_size: number
  index_daily_batch_size: number
  limit_ladder_monitor_enabled: boolean
  depth_polling_interval: number
  depth_finalize_time: { hour: number; minute: number }
  review_schedule: { enabled: boolean; hour: number; minute: number }
  review_push_channels: string[]
  sse_refresh_pages: Record<string, boolean>
  strategy_monitor_enabled: boolean
  strategy_monitor_ids: string[]
  system_notify_enabled: boolean
  feishu_webhook_url?: string
  feishu_webhook_secret?: string
  wecom_webhook_url?: string
  webhook_enabled_default?: boolean
  webhook_default_channels?: string[]
  monitor_ext_fields?: {
    concept?: MonitorExtFieldItem | null
    industry?: MonitorExtFieldItem | null
  }
  sidebar_index_symbols: string[]
  nav_order: string[]
  nav_hidden: string[]
  screener_auto_run: boolean
}

// ===== Strategy Alert =====
export interface StrategyAlertEvent {
  source: 'strategy' | 'depth'
  type: string
  strategy_id?: string
  symbol?: string
  name?: string | null
  message: string
  price?: number | null
  change_pct?: number | null
  signals?: string[]
}

// ===== Data catalog =====
export type QualityStatus = 'unknown' | 'healthy' | 'degraded' | 'failed'
export type RunStatus = 'pending' | 'running' | 'succeeded' | 'degraded' | 'failed'

export interface DatasetAvailability {
  provider_supported: boolean
  entitled: boolean
  local_materialized: boolean
  serving_ready: boolean
  reason_code: string | null
}

export interface FieldContract {
  name: string
  dtype: string
  semantic: string
  unit: string | null
  scale: string | null
  currency: string | null
  timezone: string | null
  nullable: boolean
}

export interface DatasetDescriptor {
  dataset_id: string
  title: string
  asset_types: string[]
  grain: string
  primary_key: string[]
  partition_keys: string[]
  schema_version: string
  unit_version: string
  point_in_time: boolean
  adjustment: string | null
  availability: DatasetAvailability
  fields: FieldContract[]
}

export interface DatasetState {
  dataset_id: string
  schema_version: string
  unit_version: string
  quality_status: QualityStatus
  row_count: number
  symbol_count: number
  expected_symbol_count: number | null
  earliest_time: string | null
  latest_time: string | null
  managed_bytes: number
  last_run_id: string | null
  updated_at: string
  payload: Record<string, unknown>
}

export interface MarketCoverage {
  market: 'SH' | 'SZ' | 'BJ' | 'OTHER'
  symbol_count: number
  expected_symbol_count: number | null
  ratio: number | null
}

export interface LineageSummary {
  run_id: string | null
  source: string
  fetched_at: string | null
  unit_version: string
  quality_status: QualityStatus
  scope: string | null
  artifact_path: string | null
  row_count: number | null
}

export interface StorageCategory {
  key: string
  title: string
  kind: 'managed' | 'operational'
  bytes: number
  files: number
}

export interface StorageBreakdown {
  managed_data_bytes: number
  operational_bytes: number
  total_bytes: number
  categories: StorageCategory[]
}

export interface DatasetCatalogEntry {
  descriptor: DatasetDescriptor
  state: DatasetState
  provider: string | null
  coverage: MarketCoverage[]
  lineage: LineageSummary[]
  depth5_available: boolean
}

export interface CatalogResponse {
  datasets: DatasetCatalogEntry[]
  storage: StorageBreakdown
  refreshed_at: string | null
  stale: boolean
}

export type SourceProvenanceSubjectKind = 'dataset' | 'extension'
export type SourceProvenanceIssueSeverity = 'info' | 'warning' | 'error'

export interface SourceProvenanceProducer {
  producer_id: string
  name: string
  kind: string
  role: string
  access?: string | null
  note?: string | null
}

export interface SourceProvenanceRun {
  run_id: string
  status: string
  operation: string
  provider?: string | null
  error_code?: string | null
  error_message?: string | null
  finished_at?: string | null
}

export interface SourceProvenanceLocalChain {
  providers: string[]
  adapter_paths: string[]
  physical_paths: string[]
  lineage_sources: string[]
  lifecycle?: string | null
  quality_status?: string | null
  materialized: boolean
  serving_ready: boolean
  latest_time?: string | null
  checkpoint_watermark?: string | null
  latest_run?: SourceProvenanceRun | null
}

export interface SourceProvenanceGithubReference {
  project_id: string
  name: string
  repo_url: string
  pinned_ref?: string | null
  commit_url?: string | null
  reviewed_at?: string | null
  roles: string[]
  contributions: string | string[]
  runtime_dependency: boolean
  adoption_status: string
  evidence_level: string
}

export interface SourceProvenanceCandidate extends SourceProvenanceGithubReference {
  status?: string
  reason?: string
}

export interface SourceProvenanceIssue {
  code: string
  severity: SourceProvenanceIssueSeverity
  message: string
}

export interface SourceProvenanceExplanation {
  category: string
  cadence: string
  description: string
  provides: string
}

export interface SourceProvenanceRecord {
  subject_id: string
  subject_kind: SourceProvenanceSubjectKind
  title: string
  explanation?: SourceProvenanceExplanation | null
  summary: string
  true_producers: SourceProvenanceProducer[]
  local_chain: SourceProvenanceLocalChain
  github_references: SourceProvenanceGithubReference[]
  replacement_candidates: SourceProvenanceCandidate[]
  issues: SourceProvenanceIssue[]
}

export interface SourceProvenanceResponse {
  generated_at: string
  catalog_refreshed_at: string | null
  catalog_stale: boolean
  records: SourceProvenanceRecord[]
  missing_reference_count: number
}

export interface SyncRun {
  run_id: string
  dataset_id: string
  provider: string | null
  operation: string
  started_at: string | null
  finished_at: string | null
  status: RunStatus
  rows_fetched: number
  rows_published: number
  quality_status: QualityStatus
  error_code: string | null
  error_message: string | null
}

export interface CatalogSchemaResponse {
  dataset_id: string
  schema_version: string
  unit_version: string
  fields: FieldContract[]
}

export interface CatalogRunsResponse {
  dataset_id: string | null
  runs: SyncRun[]
}

export interface DataSourceHealth {
  provider: string
  operation: string
  last_success_at: string | null
  last_failure_at: string | null
  consecutive_failures: number
  cooldown_until: string | null
  last_error_code: string | null
}

export interface DatasetControlPolicy {
  dataset_id: string
  phase: string
  max_lag_trading_days: number | null
  sync_mode: string | null
  schedule_cron: string | null
  supports_backfill: boolean
  supports_repair: boolean
  updated_at: string | null
}

export interface DataSyncCheckpoint {
  dataset_id: string
  scope: string
  watermark: string | null
  updated_at: string | null
  cursor: Record<string, unknown>
  last_success_run_id: string | null
}

export interface DataQueryAudit {
  audit_id: string
  created_at: string
  dataset_id: string
  tool_name: string | null
  row_count: number
  duration_ms: number | null
  status: string
  error_code: string | null
}

export interface UnregisteredPhysicalData {
  key: string
  title: string
  relative_path: string
  files: number
  bytes: number
  updated_at: string | null
}

export interface DataControlSummary {
  generated_at: string
  catalog_refreshed_at: string | null
  catalog_stale: boolean
  source_health: DataSourceHealth[]
  dataset_policies: DatasetControlPolicy[]
  sync_checkpoints: DataSyncCheckpoint[]
  query_audits: DataQueryAudit[]
  unregistered_physical: UnregisteredPhysicalData[]
  physical_scan_scope: 'reference'
}

// ===== API surface =====
export interface AuthUser {
  id: string
  username: string
  role: 'admin' | 'user'
}

export interface AuthQuota {
  metric: string
  day: string
  limit: number
  used: number
  remaining: number
}

export interface AuthStatus {
  configured: boolean
  authenticated: boolean
  multi_user?: boolean
  registration_enabled?: boolean
  invite_required?: boolean
  user?: AuthUser | null
  ai_quota?: AuthQuota | null
}

export interface HermesAgentStatus {
  connected: boolean
  profile: string | null
  isolation?: 'dedicated_profile'
  gateway_kind?: 'managed_local' | 'unavailable'
  gateway_running?: boolean
  gateway_startable?: boolean
  can_start_gateway?: boolean
  model?: string
  model_source?: 'server_grok_subscription' | 'server_subscription'
  model_plan?: string
  model_subscription_active?: boolean
  api_model?: string
  version?: string
  enabled_toolsets?: string[]
  memory_enabled?: boolean
  memory_provider?: string | null
  enabled_mcp_servers?: string[]
  enabled_skills?: string[]
  lieflat_charts_enabled?: boolean
  data_tool_enabled?: boolean
  data_view_count?: number
  message?: string
  detail?: string
}

export interface HermesSession {
  id: string
  title?: string | null
  preview?: string | null
  model?: string | null
  started_at?: number | null
  last_active?: number | null
  message_count?: number | null
}

export interface HermesMessage {
  id?: string
  role: 'user' | 'assistant' | 'tool' | 'system'
  content: string
  timestamp?: number | null
}

export type AdminProfileRuntimeStatus = 'ready' | 'not_ready' | 'unavailable' | 'disabled'

export interface AdminUserSummary {
  id: string
  username: string
  role: 'admin' | 'user'
  status: string
  ai_daily_limit: number | null
  created_at: number
  updated_at: number
  profile_name?: string | null
  profile_status?: 'pending' | 'ready' | 'error' | null
  profile_last_error?: string | null
  profile_updated_at?: number | null
  ai_requests_today: number
  ai_requests_7d: number
  active_login_sessions: number
  last_login_at?: number | null
  conversation_count: number | null
  last_conversation_at?: number | null
  conversation_count_capped: boolean
  profile_runtime_status: AdminProfileRuntimeStatus
  strategy_count?: number
}

export interface AdminUserStrategySummary {
  id: string
  name: string
  description: string
  source: 'ai' | 'custom'
  rules: string
  updated_at: string
}

export interface AdminUsersPayload {
  users: AdminUserSummary[]
  summary: {
    total_accounts: number
    regular_users: number
    active_users_today: number
    ai_requests_today: number
    profiles_ready: number
  }
}

export interface HermesChatEvent {
  type: 'meta' | 'delta' | 'tool' | 'error' | 'done'
  session_id?: string
  content?: string
  message?: string
  name?: string
  status?: string
  usage?: Record<string, unknown>
  runtime?: Record<string, unknown>
}



import type {
  AbnormalIntradayPayload,
  AbnormalIntradayRow,
  AbnormalOverview,
  AbnormalRow,
  AbnormalStatus,
  AbnormalWindowInfo,
  AuctionBenchmarkItem,
  AuctionBenchmarkPayload,
  AuthConfig,
  CapabilityCandidate,
  CapabilityMatrix,
  CapabilityRoute,
  CompositeChildInfo,
  CustomSignalAIGenerateResult,
  CustomSignalFieldGroup,
  CustomSourceConfig,
  DataSourceItem,
  DataSourceLoadError,
  DataSourceTestResult,
  DataSourcesResponse,
  DatasetConfig,
  DimensionIntradayPoint,
  DimensionIntradayResult,
  DimensionMembersResult,
  DragonTigerHotMoney,
  DragonTigerPayload,
  DragonTigerStockItem,
  ExtDataDetectUrlRequest,
  ExtDataDetectUrlResult,
  FactorBatchItem,
  FactorBatchResult,
  IntradaySignalKey,
  MainlineFilter,
  MainlineLeader,
  MainlineMemberStat,
  MainlineResult,
  MainlineRow,
  MiningAvailability,
  MiningBudgetProfile,
  MiningCandidateGate,
  MiningCandidateRow,
  MiningEvent,
  MiningFactorRow,
  MiningFoldRow,
  MiningRegimeRow,
  MiningRequestSummary,
  MiningRequestV1,
  MiningResult,
  MiningResultSummary,
  MiningRun,
  MiningRunProgress,
  MiningRunStatus,
  MiningScheduleConfig,
  MiningTelemetry,
  MinuteKlineSession,
  PhaseSegment,
  PhaseSegments,
  PluginDataSourceItem,
  PluginKeyResult,
  PriceLimitInfo,
  ProviderField,
  ResearchCandidate,
  ResearchCandidateCreate,
  ResearchCandidateKind,
  ResearchCandidateStatus,
  ScoringDirection,
  ScreenerCachedResult,
  ScreenerCachedSummary,
  ScreenerResultSummary,
  SectorKind,
  SectorMonitorTarget,
  StrategyBuildResult,
  StrategyBuildStreamEvent,
  StrategyCodeSaveResult,
  StrategyLoadError,
  StrategyNotifyEvent,
  VDBasicFilter,
  WatchlistGroup,
  WatchlistGroupColor,
} from './api-v02'
export type {
  AbnormalIntradayPayload,
  AbnormalIntradayRow,
  AbnormalOverview,
  AbnormalRow,
  AbnormalStatus,
  AbnormalWindowInfo,
  AuctionBenchmarkItem,
  AuctionBenchmarkPayload,
  AuthConfig,
  CapabilityCandidate,
  CapabilityMatrix,
  CapabilityRoute,
  CompositeChildInfo,
  CustomSignalAIGenerateResult,
  CustomSignalFieldGroup,
  CustomSourceConfig,
  DataSourceItem,
  DataSourceLoadError,
  DataSourceTestResult,
  DataSourcesResponse,
  DatasetConfig,
  DimensionIntradayPoint,
  DimensionIntradayResult,
  DimensionMembersResult,
  DragonTigerHotMoney,
  DragonTigerPayload,
  DragonTigerStockItem,
  ExtDataDetectUrlRequest,
  ExtDataDetectUrlResult,
  FactorBatchItem,
  FactorBatchResult,
  IntradaySignalKey,
  MainlineFilter,
  MainlineLeader,
  MainlineMemberStat,
  MainlineResult,
  MainlineRow,
  MarketPhase,
  MiningAvailability,
  MiningBudgetProfile,
  MiningCandidateGate,
  MiningCandidateRow,
  MiningEvent,
  MiningFactorRow,
  MiningFoldRow,
  MiningRegimeRow,
  MiningRequestSummary,
  MiningRequestV1,
  MiningResult,
  MiningResultSummary,
  MiningRun,
  MiningRunProgress,
  MiningRunStatus,
  MiningScheduleConfig,
  MiningTelemetry,
  MinuteKlineSession,
  MonitorExtFieldItem,
  PhaseSegment,
  PhaseSegments,
  PluginDataSourceItem,
  PluginKeyResult,
  PriceLimitInfo,
  ProviderField,
  ResearchCandidate,
  ResearchCandidateCreate,
  ResearchCandidateKind,
  ResearchCandidateStatus,
  ScoringDirection,
  ScreenerCachedResult,
  ScreenerCachedSummary,
  ScreenerResultSummary,
  SectorKind,
  SectorMonitorTarget,
  StrategyBuildResult,
  StrategyBuildStreamEvent,
  StrategyCodeSaveResult,
  StrategyLoadError,
  StrategyNotifyEvent,
  VDBasicFilter,
  WatchlistGroup,
  WatchlistGroupColor,
}
export { MARKET_PHASE_LABELS } from './api-v02'

export const api = {
  health: () => request<{
    status: string
    version: string
    mode: string
    release_channel?: string
    build_sha?: string
  }>('/health'),

  // ===== Per-account Hermes Agent =====
  hermesAgentStatus: () =>
    request<HermesAgentStatus>('/api/hermes-agent/status'),

  hermesStartGateway: () =>
    request<{ ok: boolean; started: boolean; already_running: boolean; pid?: number | null; base_url?: string; message?: string }>(
      '/api/hermes-agent/gateway/start',
      { method: 'POST' },
    ),

  hermesCreateSession: (title = '') =>
    request<{ session: HermesSession }>('/api/hermes-agent/sessions', {
      method: 'POST',
      body: JSON.stringify({ title }),
    }),

  hermesSessions: () =>
    request<{ sessions: HermesSession[] }>('/api/hermes-agent/sessions'),

  // ===== Administrator-only account insight =====
  adminUsers: () =>
    request<AdminUsersPayload>('/api/admin/users'),

  adminUserStrategies: (userId: string) =>
    request<{ user: AuthUser; strategies: AdminUserStrategySummary[] }>(
      `/api/admin/users/${encodeURIComponent(userId)}/strategies`,
    ),

  adminUserSessions: (userId: string) =>
    request<{ user: AuthUser; sessions: HermesSession[]; has_more: boolean }>(
      `/api/admin/users/${encodeURIComponent(userId)}/conversations`,
    ),

  adminUserMessages: (userId: string, sessionId: string) =>
    request<{ user: AuthUser; session_id: string; messages: HermesMessage[] }>(
      `/api/admin/users/${encodeURIComponent(userId)}/conversations/${encodeURIComponent(sessionId)}/messages`,
    ),

  hermesRenameSession: (sessionId: string, title: string) =>
    request<{ session: HermesSession }>(
      `/api/hermes-agent/sessions/${encodeURIComponent(sessionId)}`,
      {
        method: 'PATCH',
        body: JSON.stringify({ title }),
      },
    ),

  hermesDeleteSession: (sessionId: string) =>
    request<{ object: string; id: string; deleted: boolean }>(
      `/api/hermes-agent/sessions/${encodeURIComponent(sessionId)}`,
      { method: 'DELETE' },
    ),

  hermesSessionMessages: (sessionId: string) =>
    request<{ session_id: string; messages: HermesMessage[] }>(
      `/api/hermes-agent/sessions/${encodeURIComponent(sessionId)}/messages`,
    ),

  async *hermesChatStream(sessionId: string, message: string): AsyncGenerator<HermesChatEvent> {
    const res = await fetch(
      `/api/hermes-agent/sessions/${encodeURIComponent(sessionId)}/chat`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      },
    )
    if (!res.ok) {
      const errorMessage = extractErrorMessage(await res.text(), `${res.status} ${res.statusText}`)
      toast(errorMessage, 'error')
      throw new Error(errorMessage)
    }
    if (!res.body) throw new Error('Hermes 响应无 body')

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        const value = line.trim()
        if (!value) continue
        try { yield JSON.parse(value) as HermesChatEvent } catch { /* ignore */ }
      }
    }
    if (buffer.trim()) {
      try { yield JSON.parse(buffer.trim()) as HermesChatEvent } catch { /* ignore */ }
    }
  },

  // ===== Auth (访问认证) =====
  authStatus: () =>
    request<AuthStatus>('/api/auth/status'),
  authSetup: (password: string) =>
    request<{ ok: boolean }>('/api/auth/setup', {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),
  authLogin: (password: string, username?: string) =>
    request<{ ok: boolean; authenticated: boolean; user: AuthUser | null }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username: username?.trim() || undefined, password }),
    }),
  authRegister: (username: string, password: string, inviteCode = '') =>
    request<{ ok: boolean; user: AuthUser }>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username: username.trim(), password, invite_code: inviteCode }),
    }),
  authLogout: () =>
    request<{ ok: boolean }>('/api/auth/logout', { method: 'POST' }),
  authChangePassword: (oldPassword: string, newPassword: string) =>
    request<{ ok: boolean }>('/api/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
    }),

  settings: () => request<SettingsState>('/api/settings'),
  saveTickflowKey: (api_key: string) =>
    request<SaveTickflowKeyResult>('/api/settings/tickflow-key', {
      method: 'POST',
      body: JSON.stringify({ api_key }),
    }),
  clearTickflowKey: () =>
    request<any>('/api/settings/tickflow-key', { method: 'DELETE' }),

  /** 标记首次使用向导完成（持久化到后端 preferences） */
  completeOnboarding: () =>
    request<{ ok: boolean; onboarding_completed: boolean }>(
      '/api/settings/onboarding/complete', { method: 'POST' },
    ),

  /** 保存 AI 配置 */
  saveAiSettings: (ai: { provider?: string; base_url?: string; api_key?: string; model?: string; codex_command?: string; user_agent?: string }) =>
    request<{ ok: boolean; ai_provider?: string; ai_model?: string; ai_codex_command?: string; ai_configured?: boolean; ai_xai?: SettingsState['ai_xai'] }>('/api/settings/ai', {
      method: 'POST',
      body: JSON.stringify(ai),
    }),

  /** 一键清空 AI 配置(保留自定义 UA) */
  clearAiSettings: () =>
    request<{ ok: boolean }>('/api/settings/ai', { method: 'DELETE' }),

  /** xAI SuperGrok 设备码登录 — 发起 */
  xaiDeviceStart: () =>
    request<{
      device_code: string
      user_code: string
      verification_uri: string
      verification_uri_complete?: string
      expires_in: number
      interval: number
    }>('/api/settings/ai/xai/device/start', { method: 'POST' }),

  /** xAI SuperGrok 设备码登录 — 轮询完成 */
  xaiDevicePoll: (body: { device_code: string; interval?: number; expires_in?: number; model?: string }) =>
    request<{
      ok: boolean
      status?: 'pending' | 'authorized'
      slow_down?: boolean
      ai_provider?: string
      ai_model?: string
      ai_configured?: boolean
      ai_xai?: SettingsState['ai_xai']
    }>(
      '/api/settings/ai/xai/device/poll',
      { method: 'POST', body: JSON.stringify(body) },
    ),

  xaiStatus: () =>
    request<NonNullable<SettingsState['ai_xai']>>('/api/settings/ai/xai/status'),

  xaiLogout: () =>
    request<{ ok: boolean; ai_xai?: SettingsState['ai_xai'] }>('/api/settings/ai/xai/session', { method: 'DELETE' }),

  selectAiSubscription: (ai: { provider: string; model?: string }) =>
    request<{
      ok: boolean
      ai_provider?: string
      ai_model?: string
      ai_configured?: boolean
      ai_access?: SettingsState['ai_access']
      ai_subscriptions?: AiSubscriptionSource[]
      ai_xai?: SettingsState['ai_xai']
    }>('/api/settings/ai/subscription', {
      method: 'POST',
      body: JSON.stringify(ai),
    }),

  saveAiSubscriptionSource: (ai: {
    provider: string
    base_url?: string
    api_key?: string | null
    clear_api_key?: boolean
  }) =>
    request<{
      ok: boolean
      provider?: string
      base_url?: string
      has_api_key?: boolean
      api_key_masked?: string
      ai_subscriptions?: AiSubscriptionSource[]
      ai_access?: SettingsState['ai_access']
    }>('/api/settings/ai/subscription/source', {
      method: 'POST',
      body: JSON.stringify(ai),
    }),

  testAiSubscription: (ai: {
    provider: string
    model?: string
    base_url?: string
    api_key?: string
  }) =>
    request<{
      ok: boolean
      provider?: string
      label?: string
      model?: string
      base_url?: string
      response?: string
      error?: string
    }>('/api/settings/ai/subscription/test', {
      method: 'POST',
      body: JSON.stringify(ai),
    }),

  preferences: () => request<Preferences>('/api/settings/preferences'),
  updateMinuteSync: (enabled: boolean, days: number) =>
    request<Preferences>('/api/settings/preferences/minute-sync', {
      method: 'PUT',
      body: JSON.stringify({ minute_sync_enabled: enabled, minute_sync_days: days }),
    }),
  updatePipelineUniverseScope: (scope: string) =>
    request<{ pipeline_universe_scope: string; label?: string }>('/api/settings/preferences/pipeline-universe-scope', {
      method: 'PUT',
      body: JSON.stringify({ scope }),
    }),
  updatePublicDataScope: (scope: string) =>
    request<{ public_data_scope: string; label?: string }>('/api/settings/preferences/public-data-scope', {
      method: 'PUT',
      body: JSON.stringify({ scope }),
    }),
  updateFinancialMaxPeriods: (financial_max_periods: number) =>
    request<{ financial_max_periods: number }>('/api/settings/preferences/financial-max-periods', {
      method: 'PUT',
      body: JSON.stringify({ financial_max_periods }),
    }),
  updatePipelinePullTypes: (cfg: Partial<Pick<Preferences, 'pipeline_pull_a_share' | 'pipeline_pull_etf' | 'pipeline_pull_index'>>) =>
    request<{
      pipeline_pull_a_share: boolean
      pipeline_pull_etf: boolean
      pipeline_pull_index: boolean
    }>('/api/settings/preferences/pipeline-pull-types', {
      method: 'PUT',
      body: JSON.stringify(cfg),
    }),
  updatePipelineIndexSymbols: (symbols: string) =>
    request<{ pipeline_index_symbols: string }>('/api/settings/preferences/pipeline-index-symbols', {
      method: 'PUT',
      body: JSON.stringify({ symbols }),
    }),
  updateRealtimeQuotes: (enabled: boolean) =>
    request<{ realtime_quotes_enabled: boolean; realtime_allowed?: boolean; mode?: string; error?: string }>('/api/settings/preferences/realtime-quotes', {
      method: 'PUT',
      body: JSON.stringify({ realtime_quotes_enabled: enabled }),
    }),
  updateRealtimeQuoteScope: (cfg: Partial<Pick<Preferences, 'realtime_pull_stock' | 'realtime_pull_etf' | 'realtime_pull_index' | 'realtime_index_mode' | 'realtime_index_symbols'>>) =>
    request<Partial<Preferences>>('/api/settings/preferences/realtime-quote-scope', {
      method: 'PUT',
      body: JSON.stringify(cfg),
    }),
  updateIndicesNavPinned: (pinned: boolean) =>
    request<{ indices_nav_pinned: boolean }>('/api/settings/preferences/indices-nav-pinned', {
      method: 'PUT',
      body: JSON.stringify({ indices_nav_pinned: pinned }),
    }),
  quoteStatus: () =>
    request<{
      enabled: boolean
      running: boolean
      mode?: 'none' | 'watchlist' | 'full_market'
      realtime_allowed?: boolean
      interval_s: number
      symbol_count: number
      watchlist_symbol_count?: number
      index_symbol_count?: number
      etf_symbol_count?: number
      quote_age_ms: number | null
      is_trading_hours: boolean
      last_fetch_ms: number | null
    }>('/api/intraday/status'),
  quoteInterval: () =>
    request<{ interval: number; min_interval: number; max_interval: number }>(
      '/api/settings/preferences/quote-interval',
    ),
  updateQuoteInterval: (interval: number) =>
    request<{ interval: number; min_interval: number; max_interval: number }>(
      '/api/settings/preferences/quote-interval',
      { method: 'PUT', body: JSON.stringify({ interval }) },
    ),
  intradayRefresh: () => request<{ status: string }>('/api/intraday/refresh', { method: 'POST' }),
  indexQuotes: (symbols?: string[]) =>
    request<{ rows: IndexQuote[]; count: number; source?: string }>(
      `/api/intraday/indices${symbols?.length ? `?symbols=${encodeURIComponent(symbols.join(','))}` : ''}`,
    ),
  updateRealtimeMonitorConfig: (cfg: {
    sse_refresh_pages?: Record<string, boolean>
    strategy_monitor_enabled?: boolean
    strategy_monitor_ids?: string[]
    sidebar_index_symbols?: string[]
    screener_auto_run?: boolean
    monitor_ext_fields?: {
      concept?: MonitorExtFieldItem | null
      industry?: MonitorExtFieldItem | null
    }
  }) =>
    request<{
      sse_refresh_pages: Record<string, boolean>
      strategy_monitor_enabled: boolean
      strategy_monitor_ids: string[]
      sidebar_index_symbols: string[]
      screener_auto_run: boolean
    }>('/api/settings/preferences/realtime-monitor', {
      method: 'PUT',
      body: JSON.stringify(cfg),
    }),
  updateSystemNotify: (enabled: boolean) =>
    request<{ system_notify_enabled: boolean }>('/api/settings/preferences/system-notify', {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    }),
  updateFeishuWebhook: (url: string, secret: string = '') =>
    request<{ feishu_webhook_url: string; feishu_webhook_secret: string }>('/api/settings/preferences/feishu-webhook', {
      method: 'PUT',
      body: JSON.stringify({ url, secret }),
    }),
  updateWebhookDefault: (enabled: boolean) =>
    request<{ webhook_enabled_default: boolean }>('/api/settings/preferences/webhook-enabled-default', {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    }),
  updatePipelineSchedule: (hour: number, minute: number) =>
    request<{ hour: number; minute: number }>('/api/settings/preferences/pipeline-schedule', {
      method: 'PUT',
      body: JSON.stringify({ hour, minute }),
    }),
  updateReviewSchedule: (enabled: boolean, hour: number, minute: number) =>
    request<{ enabled: boolean; hour: number; minute: number }>('/api/settings/preferences/review-schedule', {
      method: 'PUT',
      body: JSON.stringify({ enabled, hour, minute }),
    }),
  updateReviewPush: (channels: string[]) =>
    request<{ review_push_channels: string[] }>('/api/settings/preferences/review-push', {
      method: 'PUT',
      body: JSON.stringify({ channels }),
    }),
  updateDepthPollingInterval: (interval: number) =>
    request<{ depth_polling_interval: number }>('/api/settings/preferences/depth-polling-interval', {
      method: 'PUT',
      body: JSON.stringify({ interval }),
    }),
  updateLimitLadderMonitor: (enabled: boolean) =>
    request<{ limit_ladder_monitor_enabled: boolean }>('/api/settings/preferences/limit-ladder-monitor', {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    }),
  runLimitLadderFix: () =>
    request<{ ok: boolean; count: number; msg: string }>('/api/settings/preferences/limit-ladder-monitor/run', {
      method: 'POST',
    }),
  updateDepthFinalizeTime: (hour: number, minute: number) =>
    request<{ hour: number; minute: number }>('/api/settings/preferences/depth-finalize-time', {
      method: 'PUT',
      body: JSON.stringify({ hour, minute }),
    }),
  saveNavOrder: (nav_order: string[]) =>
    request<{ nav_order: string[] }>('/api/settings/preferences/nav-order', {
      method: 'PUT',
      body: JSON.stringify({ nav_order }),
    }),
  saveNavHidden: (nav_hidden: string[]) =>
    request<{ nav_hidden: string[] }>('/api/settings/preferences/nav-hidden', {
      method: 'PUT',
      body: JSON.stringify({ nav_hidden }),
    }),
  updateInstrumentsSchedule: (hour: number, minute: number) =>
    request<{ hour: number; minute: number }>('/api/settings/preferences/instruments-schedule', {
      method: 'PUT',
      body: JSON.stringify({ hour, minute }),
    }),
  updateEnrichedBatchSize: (size: number) =>
    request<{ enriched_batch_size: number }>('/api/settings/preferences/enriched-batch-size', {
      method: 'PUT',
      body: JSON.stringify({ size }),
    }),
  updateIndexDailyBatchSize: (size: number) =>
    request<{ index_daily_batch_size: number }>('/api/settings/preferences/index-daily-batch-size', {
      method: 'PUT',
      body: JSON.stringify({ size }),
    }),

  // 自选列表列配置
  watchlistColumns: () =>
    request<{ columns: any[] | null }>('/api/settings/preferences/watchlist-columns'),
  updateWatchlistColumns: (columns: any[]) =>
    request<{ columns: any[] }>('/api/settings/preferences/watchlist-columns', {
      method: 'PUT',
      body: JSON.stringify({ columns }),
    }),

  // 策略结果列表列配置
  screenerResultColumns: () =>
    request<{ columns: any[] | null }>('/api/settings/preferences/screener-result-columns'),
  updateScreenerResultColumns: (columns: any[]) =>
    request<{ columns: any[] }>('/api/settings/preferences/screener-result-columns', {
      method: 'PUT',
      body: JSON.stringify({ columns }),
    }),

  capabilities: () => request<CapabilitiesResponse>('/api/capabilities'),
  version: async () => {
    const result = await request<{ version: string }>('/health')
    return {
      version: result.version.startsWith('v') ? result.version : `v${result.version}`,
    }
  },

  // ===== 运行日志 =====
  runtimeLogsStatus: () =>
    request<{
      configured: boolean
      process_id: string
      log_dir: string | null
      buffer_size: number
      buffer_capacity: number
      latest_ts: string | null
      files: Record<string, { path: string; size_bytes: number; mtime: string } | null>
    }>('/api/runtime-logs/status'),
  runtimeLogs: (params?: {
    source?: string
    level?: string
    category?: string
    q?: string
    limit?: number
    after_id?: string
  }) => {
    const sp = new URLSearchParams()
    if (params?.source) sp.set('source', params.source)
    if (params?.level) sp.set('level', params.level)
    if (params?.category) sp.set('category', params.category)
    if (params?.q) sp.set('q', params.q)
    if (params?.limit != null) sp.set('limit', String(params.limit))
    if (params?.after_id) sp.set('after_id', params.after_id)
    const qs = sp.toString()
    return request<{
      events: RuntimeLogItem[]
      count: number
      process_id: string
      log_dir: string | null
      latest_ts: string | null
    }>(`/api/runtime-logs${qs ? `?${qs}` : ''}`)
  },
  clearRuntimeLogs: (keepFiles = false) =>
    request<{ ok: boolean; truncated_files: string[] }>(
      `/api/runtime-logs?keep_files=${keepFiles ? 'true' : 'false'}`,
      { method: 'DELETE' },
    ),

  redetectCapabilities: () =>
    request<CapabilitiesResponse>('/api/capabilities/redetect', { method: 'POST' }),

  klineDaily: (symbol: string, days = 120, dateRange?: { start: string; end: string }, extColumns?: string) =>
    request<{
      symbol: string
      name?: string
      stock_info?: { name?: string; total_shares?: number; float_shares?: number; ext?: Record<string, unknown> }
      rows: KlineRow[]
      source?: string
      quote_overlay?: {
        applied: boolean
        row_count: number
        latest_date: string | null
        latest_source: string | null
        latest_fetched_at: string | null
      }
    }>(
      (dateRange
        ? `/api/kline/daily?symbol=${encodeURIComponent(symbol)}&start_date=${dateRange.start}&end_date=${dateRange.end}`
        : `/api/kline/daily?symbol=${encodeURIComponent(symbol)}&days=${days}`)
      + (extColumns ? `&ext_columns=${encodeURIComponent(extColumns)}` : ''),
    ),
  klineDailyBatch: (symbols: string[], days = 12) =>
    request<{ data: Record<string, KlineRow[]> }>('/api/kline/daily-batch', {
      method: 'POST',
      body: JSON.stringify({ symbols, days }),
    }),
  instrumentSearch: (q: string, limit = 20, assetTypes?: string) =>
    request<{ results: { symbol: string; name: string; code: string; asset_type?: string }[] }>(
      `/api/kline/instruments/search?q=${encodeURIComponent(q)}&limit=${limit}${assetTypes ? `&asset_types=${encodeURIComponent(assetTypes)}` : ''}`,
    ),

  /** 批量查股票名称 (传入 symbol 列表, 返回 {symbol: name}) */
  instrumentNames: (symbols: string[]) =>
    request<{ names: Record<string, string> }>('/api/kline/instruments/names', {
      method: 'POST',
      body: JSON.stringify(symbols),
    }),
  klineMinute: (symbol: string, date?: string, live?: boolean) =>
    request<{
      symbol: string
      name?: string
      stock_info?: { name?: string; total_shares?: number; float_shares?: number }
      date: string | null
      rows: MinuteKlineRow[]
      source?: 'local' | 'live' | 'none'
      provider?: string
      persisted?: boolean
      quality?: Record<string, unknown>
      prev_close?: number | null
      asset_type?: 'stock' | 'etf' | 'index'
    }>(
      `/api/kline/minute?symbol=${encodeURIComponent(symbol)}${date ? `&date=${date}` : ''}${live ? '&live=1' : ''}`,
    ),
  indexList: () => request<{ results: IndexInstrument[]; count: number }>('/api/index/list'),
  indexSearch: (q: string, limit = 20) =>
    request<{ results: IndexInstrument[] }>(
      `/api/index/search?q=${encodeURIComponent(q)}&limit=${limit}`,
    ),
  indexDaily: (symbol: string, days = 120, dateRange?: { start: string; end: string }) =>
    request<{
      symbol: string
      name?: string
      index_info?: IndexInstrument
      rows: KlineRow[]
      source?: string
    }>(
      dateRange
        ? `/api/index/daily?symbol=${encodeURIComponent(symbol)}&start_date=${dateRange.start}&end_date=${dateRange.end}`
        : `/api/index/daily?symbol=${encodeURIComponent(symbol)}&days=${days}`,
    ),
  indexMinute: (symbol: string, date?: string) =>
    request<{
      symbol: string
      name?: string
      index_info?: IndexInstrument
      date: string | null
      rows: MinuteKlineRow[]
      source?: string
    }>(
      `/api/index/minute?symbol=${encodeURIComponent(symbol)}${date ? `&date=${date}` : ''}`,
    ),
  syncIndexInstruments: () =>
    request<{ status: string; count: number }>('/api/index/sync_instruments', { method: 'POST' }),
  syncIndexDaily: (days = 365) =>
    request<{ status: string; index_count: number; rows_written: number }>(
      `/api/index/sync_daily?days=${days}`,
      { method: 'POST' },
    ),
  syncSymbol: (symbol: string, days = 250) =>
    request<{ symbol: string; rows_written: number }>(
      `/api/kline/sync?symbol=${encodeURIComponent(symbol)}&days=${days}`,
      { method: 'POST' },
    ),
  syncMinute: () =>
    request<{ status: string; job_id: string }>('/api/kline/sync_minute', { method: 'POST' }),
  extendHistory: (value: number, unit: 'day' | 'month' | 'year') =>
    request<{ status: string; job_id: string }>('/api/kline/extend_history', {
      method: 'POST',
      body: JSON.stringify({ value, unit }),
    }),
  extendMinuteHistory: (value: number, unit: 'day' | 'month') =>
    request<{ status: string; job_id: string }>('/api/kline/extend_minute_history', {
      method: 'POST',
      body: JSON.stringify({ value, unit }),
    }),
  rebuildEnriched: () =>
    request<{ status: string; job_id: string }>('/api/kline/rebuild_enriched', {
      method: 'POST',
    }),

  watchlistList: () => request<{ symbols: WatchlistEntry[] }>('/api/watchlist'),
  watchlistAdd: (symbol: string, note = '', groupId?: string | null) =>
    request<{ symbols: WatchlistEntry[] }>('/api/watchlist', {
      method: 'POST',
      body: JSON.stringify({ symbol, note, group_id: groupId ?? null }),
    }),
  watchlistBatchAdd: (symbols: string[], note = '', groupId?: string | null) =>
    request<{ symbols: WatchlistEntry[]; added: number }>('/api/watchlist/batch', {
      method: 'POST',
      body: JSON.stringify({ symbols, note, group_id: groupId ?? null }),
    }),
  watchlistRemove: (symbol: string) =>
    request<{ symbols: WatchlistEntry[] }>(
      `/api/watchlist/${encodeURIComponent(symbol)}`,
      { method: 'DELETE' },
    ),
  watchlistMoveToTop: (symbol: string) =>
    request<{ symbols: WatchlistEntry[] }>(
      `/api/watchlist/${encodeURIComponent(symbol)}/top`,
      { method: 'POST' },
    ),
  watchlistClear: () =>
    request<{ removed: number }>('/api/watchlist', { method: 'DELETE' }),
  watchlistQuotes: () => request<{ quotes: Quote[] }>('/api/watchlist/quotes'),
  watchlistEnriched: (extColumns?: string) =>
    request<{
      rows: any[]
      as_of: string | null
      realtime_as_of?: string | null
      realtime_count?: number
      elapsed_ms: number
    }>(
      extColumns
        ? `/api/watchlist/enriched?ext_columns=${encodeURIComponent(extColumns)}`
        : '/api/watchlist/enriched',
    ),

  screenerStrategies: (_assetType?: 'stock' | 'etf' | 'index', _timeframe: '1d' | '1m' | 'all' = 'all') =>
    request<{ presets: ScreenerStrategy[]; owner_user_id?: string; load_errors?: StrategyLoadError[] }>('/api/screener/strategies'),
  screenerStrategiesForOwner: (ownerUserId: string) =>
    request<{ presets: ScreenerStrategy[]; owner_user_id?: string }>(
      `/api/screener/strategies?owner_user_id=${encodeURIComponent(ownerUserId)}`,
    ),
  screenerRunPreset: (strategy_id: string, pool?: string[], asOf?: string, extColumns?: string, ownerUserId?: string, _assetType?: string) =>
    request<ScreenerResult>('/api/screener/run_preset', {
      method: 'POST',
      body: JSON.stringify({ strategy_id, owner_user_id: ownerUserId ?? null, pool, as_of: asOf ?? null, ext_columns: extColumns || null }),
    }),
  screenerRunCustom: (conditions: string[], orderBy?: string, limit = 30, pool?: string[], extColumns?: string) =>
    request<ScreenerResult>('/api/screener/run', {
      method: 'POST',
      body: JSON.stringify({ conditions, order_by: orderBy, limit, pool, ext_columns: extColumns || null }),
    }),
  screenerRunAll: (asOf?: string, strategyIds?: string[], extColumns?: string) =>
    request<{ as_of: string | null; results: Record<string, { total: number; as_of: string; rows: any[] }> }>(
      '/api/screener/run_all', { method: 'POST', body: JSON.stringify({ as_of: asOf ?? null, strategy_ids: strategyIds ?? null, ext_columns: extColumns || null }) },
    ),
  screenerCached: (extColumns?: string) =>
    request<{ as_of: string | null; results: Record<string, { total: number; as_of: string; rows: any[] }>; today_ever_matched: Record<string, string[]> | null; today_ever_rows: Record<string, Record<string, any>> | null; updated_at: number | null }>(
      extColumns
        ? `/api/screener/cached?ext_columns=${encodeURIComponent(extColumns)}`
        : '/api/screener/cached',
    ),
  marketSnapshot: () =>
    request<MarketSnapshotResponse>('/api/screener/market-snapshot'),
  overviewMarket: (asOf?: string) => request<OverviewMarket>(`/api/overview/market${asOf ? `?as_of=${asOf}` : ''}`),
  marketPulse: (tradeDate?: string | null) =>
    request<MarketPulseResponse>(
      `/api/market-pulse${tradeDate ? `?trade_date=${encodeURIComponent(tradeDate)}` : ''}`,
    ),
  syncMarketPulse: (tradeDate?: string | null) =>
    request<MarketPulseSyncResult>('/api/market-pulse/sync', {
      method: 'POST',
      body: JSON.stringify({ trade_date: tradeDate || null }),
    }),
  hithinkLimitPool: (tradeDate?: string | null) =>
    request<HithinkLocalQueryResponse>(
      '/api/hithink/limit-pool' + (tradeDate ? '?trade_date=' + encodeURIComponent(tradeDate) : ''),
    ),
  hithinkDragonTiger: (tradeDate?: string | null) =>
    request<HithinkLocalQueryResponse>(
      '/api/hithink/dragon-tiger' + (tradeDate ? '?trade_date=' + encodeURIComponent(tradeDate) : ''),
    ),
  hithinkAuctionSnapshot: (tradeDate?: string | null) =>
    request<HithinkLocalQueryResponse>(
      '/api/hithink/auction-snapshot' + (tradeDate ? '?trade_date=' + encodeURIComponent(tradeDate) : ''),
    ),
  hithinkValuationSnapshot: (asOf?: string | null) =>
    request<HithinkLocalQueryResponse>(
      '/api/hithink/valuation-snapshot' + (asOf ? '?as_of=' + encodeURIComponent(asOf) : ''),
    ),
  syncHithinkSpecialData: (tradeDate?: string | null, include?: HithinkSyncTarget[]) =>
    request<HithinkSyncResult>('/api/hithink/sync', {
      method: 'POST',
      body: JSON.stringify({ trade_date: tradeDate || null, include: include ?? null }),
    }),


  // 概念/行业涨幅轮动矩阵: 每列(日期)各自把所有成员按当天涨幅从高到低排序
  rpsRotation: (days: number, kind: 'concept' | 'industry' = 'concept', level?: number) => {
    const params = new URLSearchParams({ days: String(days), kind })
    if (kind === 'industry' && level) params.set('level', String(level))
    return request<RpsRotationData>(`/api/rps/rotation?${params.toString()}`)
  },

  /**
   * AI 板块轮动分析 — 流式调用(NDJSON,与财务/个股/复盘同协议)。
   * meta 里带 days / summary,供前端先渲染主线摘要。
   */
  async *rotationAnalyzeStream(
    days: number,
    focus = '',
    kind: 'concept' | 'industry' = 'concept',
    level?: number,
  ): AsyncGenerator<{
    type: 'meta' | 'delta' | 'error' | 'done'
    days?: number
    summary?: string
    content?: string
    message?: string
  }> {
    const res = await fetch('/api/rps/rotation-analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ days, focus, kind, level: kind === 'industry' ? level : undefined }),
    })
    if (!res.ok) {
      const msg = extractErrorMessage(await res.text(), `${res.status} ${res.statusText}`)
      toast(msg, 'error')
      throw new Error(msg)
    }
    if (!res.body) throw new Error('响应无 body')

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split("\n")
      buf = lines.pop() ?? ''
      for (const line of lines) {
        const s = line.trim()
        if (!s) continue
        try { yield JSON.parse(s) } catch { /* ignore */ }
      }
    }
    if (buf.trim()) {
      try { yield JSON.parse(buf.trim()) } catch { /* ignore */ }
    }
  },


  updatePipelineRegimeEnabled: (enabled: boolean) =>
    request<{ pipeline_regime_enabled: boolean }>('/api/settings/preferences/pipeline-regime-enabled', {
      method: 'POST',
      body: JSON.stringify({ pipeline_regime_enabled: enabled }),
    }),
  updateRegimeBatchParams: (params: { batch_days?: number; warmup_days?: number }) =>
    request<{ regime_batch_days: number; regime_warmup_days: number }>('/api/settings/preferences/regime-batch-params', {
      method: 'POST',
      body: JSON.stringify(params),
    }),
  repairDaily: (startDate: string) =>
    request<{ ok: boolean; repaired?: number; message?: string }>('/api/data/repair-daily', {
      method: 'POST',
      body: JSON.stringify({ start_date: startDate }),
    }),
  watchlistOcrStatus: () =>
    request<{ provider: string; available: boolean }>('/api/watchlist/ocr-status'),
  watchlistImportImage: async (file: File, signal?: AbortSignal, _quiet = false) => {
    const body = new FormData()
    body.append('file', file)
    const res = await fetch('/api/watchlist/import-image', { method: 'POST', body, signal })
    if (!res.ok) {
      const msg = extractErrorMessage(await res.text(), `${res.status} ${res.statusText}`)
      toast(msg, 'error')
      throw new Error(msg)
    }
    return res.json() as Promise<WatchlistImportResult>
  },
  regimeHistory: (start?: string, end?: string, limit?: number) => {
    const params = new URLSearchParams()
    if (start) params.set('start', start)
    if (end) params.set('end', end)
    if (limit) params.set('limit', String(limit))
    const qs = params.toString()
    return request<RegimeHistory>(`/api/regime/history${qs ? `?${qs}` : ''}`)
  },
  regimeLatest: () => request<{ row: RegimeRow | null }>('/api/regime/latest'),
  regimeStates: (days = 60) => request<RegimeStates>(`/api/regime/states?days=${days}`),
  dimensionMembers: async (_configId: string, _opts?: { field?: string; value?: string; date?: string | null; limit?: number }) => ({ members: [] as any[], rows: [] as any[], total: 0, label: '', date: null as string | null }),
  regimeCoverage: () => request<RegimeCoverage>('/api/regime/coverage'),
  regimeRecompute: (start?: string, end?: string) => {
    const params = new URLSearchParams()
    if (start) params.set('start', start)
    if (end) params.set('end', end)
    const qs = params.toString()
    return request<{ ok: boolean; computed: number }>(`/api/regime/recompute${qs ? `?${qs}` : ''}`, { method: 'POST' })
  },
  strategySaveComposite: (payload: Record<string, unknown>) =>
    request<{ ok: boolean; id?: string; strategy_id?: string }>('/api/strategies/composite/save', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  limitLadder: (asOf?: string, extColumns?: string, direction?: 'up' | 'down') => {
    const params = new URLSearchParams()
    if (asOf) params.set('as_of', asOf)
    if (extColumns) params.set('ext_columns', extColumns)
    if (direction === 'down') params.set('direction', 'down')
    const qs = params.toString()
    return request<LimitLadderResult>(
      `/api/screener/limit-ladder${qs ? `?${qs}` : ''}`,
    )
  },

  backtestStatus: () => request<{ available: boolean }>('/api/backtest/status'),

  backtestRun: (payload: {
    symbols: string[]
    entries: string[]
    exits: string[]
    start?: string
    end?: string
    stop_loss_pct?: number
    max_hold_days?: number
    matching?: 'close_t' | 'open_t+1'
  }) =>
    request<BacktestResult>('/api/backtest/run', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  factorColumns: () =>
    request<{ columns: FactorColumn[] }>('/api/backtest/factor/columns'),

  factorRun: (payload: {
    factor_name: string
    symbols?: string[] | null
    start?: string | null
    end?: string | null
    n_groups?: number
    rebalance?: 'daily' | 'weekly' | 'monthly'
    weight?: 'equal' | 'factor_weight'
    fees_pct?: number
    slippage_bps?: number
  }) =>
    request<FactorBacktestResult>('/api/backtest/factor/run', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  strategyBacktestRun: (payload: {
    strategy_id: string
    strategy_owner_user_id?: string | null
    symbols?: string[] | null
    start?: string | null
    end?: string | null
    params?: Record<string, any> | null
    overrides?: Record<string, any> | null
    matching?: 'close_t' | 'open_t+1'
    entry_fill?: 'close_t' | 'open_t+1' | null
    exit_fill?: 'close_t' | 'open_t+1' | null
    fees_pct?: number
    slippage_bps?: number
    max_positions?: number
    initial_capital?: number
    position_sizing?: 'equal' | 'score_weight'
  }) =>
    request<StrategyBacktestResult>('/api/backtest/strategy/run', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  strategyBacktestHistory: (limit = 30) =>
    request<{ runs: StrategyBacktestHistoryItem[] }>(
      `/api/backtest/strategy/history?limit=${Math.max(1, Math.min(100, limit))}`,
    ),

  strategyBacktestHistoryGet: (runId: string) =>
    request<StrategyBacktestResult & { saved_at: string; strategy_owner_user_id: string }>(
      `/api/backtest/strategy/history/${encodeURIComponent(runId)}`,
    ),

  strategyBacktestHistoryDelete: (runId: string) =>
    request<{ ok: boolean }>(
      `/api/backtest/strategy/history/${encodeURIComponent(runId)}`,
      { method: 'DELETE' },
    ),

  portfolioSnapshot: () => request<PortfolioSnapshot>('/api/portfolio'),

  portfolioSaveHolding: (holding: { symbol: string; quantity: number; avg_cost: number; note?: string }) =>
    request<{ ok: boolean; holding: PortfolioHolding }>('/api/portfolio/holdings', {
      method: 'POST',
      body: JSON.stringify(holding),
    }),

  portfolioDeleteHolding: (symbol: string) =>
    request<{ ok: boolean }>(`/api/portfolio/holdings/${encodeURIComponent(symbol)}`, {
      method: 'DELETE',
    }),

  pipelineRun: () => request<{ job_id: string; reused: boolean }>(
    '/api/pipeline/run', { method: 'POST' },
  ),
  pipelineJob: (id: string) => request<PipelineJob>(`/api/pipeline/jobs/${id}`),
  pipelineJobs: (limit = 20) =>
    request<{ active_id: string | null; jobs: PipelineJobSummary[] }>(
      `/api/pipeline/jobs?limit=${limit}`,
    ),

  dataReadiness: () => request<DataReadiness>('/api/overview/data-readiness'),
  dataStatus: () => request<DataStatus>('/api/data/status'),
  dataClear: () => request<{ deleted_files: number }>('/api/data/clear', { method: 'POST' }),
  enrichedSchema: (table: string) => request<EnrichedField[]>(`/api/data/schema/${table}`),
  dataControlSummary: () => request<DataControlSummary>('/api/data/control-summary'),
  dataSourceProvenance: () => request<SourceProvenanceResponse>('/api/data/source-provenance'),
  dataCatalog: () => request<CatalogResponse>('/api/data/catalog'),
  dataCatalogDataset: (datasetId: string) =>
    request<DatasetCatalogEntry>(`/api/data/catalog/${encodeURIComponent(datasetId)}`),
  dataCatalogSchema: (datasetId: string) =>
    request<CatalogSchemaResponse>(`/api/data/catalog/${encodeURIComponent(datasetId)}/schema`),
  dataCatalogRuns: (datasetId?: string) =>
    request<CatalogRunsResponse>(
      `/api/data/runs${datasetId === undefined ? '' : `?dataset_id=${encodeURIComponent(datasetId)}`}`,
    ),
  rescanDataCatalog: (datasetId?: string) =>
    request<CatalogResponse>(
      `/api/data/catalog/rescan${datasetId === undefined ? '' : `?dataset_id=${encodeURIComponent(datasetId)}`}`,
      { method: 'POST' },
    ),

  testEndpoint: (url: string, rounds?: number) =>
    request<{
      ok: boolean
      url: string
      rounds: number
      success: number
      median_ms: number | null
      min_ms?: number | null
      max_ms?: number | null
      /** 兼容旧字段,等于 median_ms */
      latency_ms?: number | null
      error?: string
    }>(
      '/api/settings/test_endpoint', {
        method: 'POST',
        body: JSON.stringify({ url, rounds }),
      },
    ),

  // 端点发现 —— 后端代理拉取 tickflow.org/endpoints.json(前端无法跨域直连)
  listEndpoints: () =>
    request<EndpointManifest>('/api/settings/endpoints'),

  switchEndpoint: (url: string) =>
    request<{ ok: boolean; current_endpoint: string; error?: string }>(
      '/api/settings/switch_endpoint', {
        method: 'POST',
        body: JSON.stringify({ url }),
      },
    ),


  // ===== 筹码分布（本地日K近似） =====
  stockChips: (symbol: string, days = 120, bins = 80, asOf?: string) =>
    request<ChipDistributionResponse>(
      `/api/free/chips/${encodeURIComponent(symbol)}?days=${days}&bins=${bins}${asOf ? `&as_of=${encodeURIComponent(asOf)}` : ''}`,
    ),

  // ===== 主力资金流（行业/概念板块） =====
  fundFlowBoards: (top = 30) =>
    request<FundFlowListResponse>(`/api/free/fund-flow/boards?top=${top}`),
  fundFlowBoardsRefresh: () =>
    request<FundFlowListResponse>('/api/free/fund-flow/boards/refresh', { method: 'POST' }),
  fundFlowConcepts: (top = 30) =>
    request<FundFlowListResponse>(`/api/free/fund-flow/concepts?top=${top}`),
  fundFlowConceptsRefresh: () =>
    request<FundFlowListResponse>('/api/free/fund-flow/concepts/refresh', { method: 'POST' }),
  fundFlowStock: (symbol: string, limit = 60) =>
    request<{ ok: boolean; symbol: string; rows: any[]; count: number; cached?: boolean }>(
      `/api/free/fund-flow/stock/${encodeURIComponent(symbol)}?limit=${limit}`,
    ),
  fundFlowStockRefresh: (symbol: string) =>
    request<{ ok: boolean; symbol: string; rows: number; source?: string }>(
      `/api/free/fund-flow/stock/${encodeURIComponent(symbol)}/refresh`,
      { method: 'POST' },
    ),

  /** 行业 Top 流入/流出日线历史回补（东财 dataapi 排名 + flowlens daykline） */
  fundFlowBoardsWindow: (days = 63, top = 8) =>
    request<FundFlowWindowResponse>(`/api/free/fund-flow/boards/window?days=${days}&top=${top}`),
  fundFlowConceptsWindow: (days = 63, top = 8) =>
    request<FundFlowWindowResponse>(`/api/free/fund-flow/concepts/window?days=${days}&top=${top}`),
  fundFlowBoardsHistoryRefresh: (topN = 20, limit = 60) =>
    request<FundFlowHistoryRefreshResponse>(
      `/api/free/fund-flow/boards/history/refresh?top_n=${topN}&limit=${limit}`,
      { method: 'POST' },
    ),
  /** 概念 Top 流入/流出日线历史回补（东财 dataapi 排名 + daykline） */
  fundFlowConceptsHistoryRefresh: (topN = 20, limit = 60) =>
    request<FundFlowHistoryRefreshResponse>(
      `/api/free/fund-flow/concepts/history/refresh?top_n=${topN}&limit=${limit}`,
      { method: 'POST' },
    ),
  fundFlowBoardHistory: (
    code: string,
    opts?: { kind?: 'board' | 'concept'; limit?: number; refresh?: boolean },
  ) => {
    const kind = opts?.kind ?? 'board'
    const limit = opts?.limit ?? 120
    const refresh = opts?.refresh ? 'true' : 'false'
    return request<FundFlowBoardHistoryResponse>(
      `/api/free/fund-flow/board/${encodeURIComponent(code)}/history?kind=${kind}&limit=${limit}&refresh=${refresh}`,
    )
  },
  fundFlowBoardIntraday: (
    code: string,
    opts?: { kind?: 'board' | 'concept'; refresh?: boolean; tradeDate?: string },
  ) => {
    const kind = opts?.kind ?? 'board'
    const refresh = opts?.refresh ? 'true' : 'false'
    const qs = new URLSearchParams({ kind, refresh })
    if (opts?.tradeDate) qs.set('trade_date', opts.tradeDate)
    return request<FundFlowBoardIntradayResponse>(
      `/api/free/fund-flow/board/${encodeURIComponent(code)}/intraday?${qs.toString()}`,
    )
  },

  // ===== 扩展数据 =====
  extDataList: () =>
    request<{ items: ExtDataConfig[] }>('/api/ext-data'),

  extDataRows: (id: string, opts?: { date?: string; limit?: number; columns?: string[] }) => {
    const qs = new URLSearchParams()
    if (opts?.date) qs.set('date', opts.date)
    if (opts?.limit) qs.set('limit', String(opts.limit))
    if (opts?.columns?.length) qs.set('columns', opts.columns.join(','))
    const suffix = qs.toString()
    return request<ExtDataRowsResult>(`/api/ext-data/${encodeURIComponent(id)}/rows${suffix ? `?${suffix}` : ''}`)
  },

  analysisMenus: () =>
    request<{ items: AnalysisMenu[] }>('/api/analysis-menus'),

  analysisMenu: (id: string) =>
    request<AnalysisMenu>(`/api/analysis-menus/${encodeURIComponent(id)}`),

  analysisMenuSave: (id: string, body: Omit<AnalysisMenu, 'id' | 'created_at' | 'updated_at' | 'builtin'>) =>
    request<AnalysisMenu>(`/api/analysis-menus/${encodeURIComponent(id)}`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  analysisMenuReorder: (ids: string[]) =>
    request<{ items: AnalysisMenu[] }>('/api/analysis-menus/reorder', {
      method: 'POST',
      body: JSON.stringify({ ids }),
    }),

  analysisMenuDelete: (id: string) =>
    request<{ status: string }>(`/api/analysis-menus/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  extDataCreate: (body: { id: string; label: string; mode: 'snapshot' | 'timeseries'; fields: { name: string; dtype: string; label: string }[]; description?: string; symbol_map?: Record<string, string>; code_map?: Record<string, string> }) =>
    request<ExtDataConfig>('/api/ext-data', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  extDataUpdate: (id: string, body: { label?: string; fields?: { name: string; dtype: string; label: string }[]; description?: string }) =>
    request<ExtDataConfig>(`/api/ext-data/${id}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

  extDataDelete: (id: string) =>
    request<{ status: string }>(`/api/ext-data/${id}`, { method: 'DELETE' }),

  extDataUpload: (id: string, file: File, snapshotDate?: string) => {
    const fd = new FormData()
    fd.append('file', file)
    return request<{ status: string; rows: number; date: string }>(
      `/api/ext-data/${id}/upload${snapshotDate ? `?snapshot_date=${snapshotDate}` : ''}`,
      { method: 'POST', body: fd },
    )
  },

  extDataIngest: (id: string, body: { date?: string; rows: Record<string, unknown>[] }) =>
    request<{ status: string; rows: number; date: string }>(
      `/api/ext-data/${id}/ingest`,
      { method: 'POST', body: JSON.stringify(body) },
    ),

  extDataSchemaAll: () =>
    request<{ items: { id: string; label: string; mode: string; columns: { name: string; type: string; label: string }[] }[] }>('/api/ext-data/schema-all'),

  extDataPullConfig: (id: string, body: {
    url: string; method?: string; headers?: Record<string, string>; body?: string;
    response_path?: string; field_map?: Record<string, string>;
    schedule_minutes?: number; enabled?: boolean;
  }) =>
    request<{ status: string; pull: PullConfig }>(
      `/api/ext-data/${id}/pull`,
      { method: 'PUT', body: JSON.stringify(body) },
    ),

  extDataPullTest: (id: string) =>
    request<{ status: string; total_rows: number; preview: Record<string, unknown>[]; has_symbol: boolean }>(
      `/api/ext-data/${id}/pull/test`,
      { method: 'POST' },
    ),

  extDataPullRun: (id: string) =>
    request<{ status: string; rows: number; date: string }>(
      `/api/ext-data/${id}/pull/run`,
      { method: 'POST' },
    ),

  // 内置预设 (概念/行业) 手动获取数据: 走结构转换, 保证 schema 一致
  extDataPresetFetch: (id: string) =>
    request<{ status: string; rows: number }>(
      `/api/ext-data/presets/${id}/fetch`,
      { method: 'POST' },
    ),

  extDataDetectFields: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return request<{ fields: { name: string; dtype: string; label: string }[]; rows: number; symbol_candidates: string[]; code_candidates: string[] }>(
      '/api/ext-data/detect-fields',
      { method: 'POST', body: fd },
    )
  },

  extDataFixSymbol: (id: string) =>
    request<{ status: string; fixed_files: number }>(
      `/api/ext-data/${id}/fix-symbol`,
      { method: 'POST' },
    ),

  // ===== 股票 F10 =====
  syncMarginTrading: (symbols: string[], rowsPerSymbol = 250) =>
    request<MarginTradingSyncResponse>('/api/f10/margin-trading/sync', {
      method: 'POST',
      body: JSON.stringify({ symbols, rows_per_symbol: rowsPerSymbol }),
    }),

  // ===== Financials =====
  financialStatus: () =>
    request<FinancialStatus>('/api/financials/status'),

  financialMetrics: (symbol?: string) =>
    request<{ data: FinancialMetricRecord[] }>(
      `/api/financials/metrics${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ''}`,
    ),

  financialIncome: (symbol?: string) =>
    request<{ data: FinancialIncomeRecord[] }>(
      `/api/financials/income${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ''}`,
    ),

  financialBalanceSheet: (symbol?: string) =>
    request<{ data: FinancialBalanceSheetRecord[] }>(
      `/api/financials/balance-sheet${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ''}`,
    ),

  financialCashFlow: (symbol?: string) =>
    request<{ data: FinancialCashFlowRecord[] }>(
      `/api/financials/cash-flow${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ''}`,
    ),

  financialShares: (symbol?: string) =>
    request<{ data: FinancialSharesRecord[] }>(
      `/api/financials/shares${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ''}`,
    ),

  /** 触发财务数据同步(后台异步执行,接口立即返回 started 状态) */
  financialSync: (table: string) =>
    request<{ status: string; synced: { started: boolean; reason?: string } }>(
      `/api/financials/sync/${table}`, { method: 'POST' },
    ),

  /** AI 分析报告 CRUD */
  financialReportsList: () =>
    request<{ reports: AiFinancialReport[] }>('/api/financials/reports'),

  financialReportSave: (r: {
    symbol: string; name?: string; focus?: string; content: string
    periods?: number; summary?: string
  }) =>
    request<{ ok: boolean; report: AiFinancialReport }>('/api/financials/reports', {
      method: 'POST', body: JSON.stringify(r),
    }),

  financialReportDelete: (reportId: string) =>
    request<{ ok: boolean }>(`/api/financials/reports/${encodeURIComponent(reportId)}`, { method: 'DELETE' }),

  /**
   * AI 财务分析 — 流式调用。
   *
   * 返回一个可逐行读取的 async generator,每行是 JSON:
   *   {type:"meta",symbol,summary,periods}
   *   {type:"delta",content:"..."}    ← 文本片段,逐个累加
   *   {type:"error",message:"..."}
   *   {type:"done"}
   *
   * 用 ReadableStream 解析(而非 SSE EventSource),支持 POST body 且更简单。
   */
  async *financialAnalyzeStream(symbol: string, focus?: string): AsyncGenerator<{
    type: 'meta' | 'delta' | 'error' | 'done'
    symbol?: string
    summary?: string
    periods?: number
    content?: string
    message?: string
  }> {
    const res = await fetch('/api/financials/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, focus: focus ?? '' }),
    })
    if (!res.ok) {
      const msg = extractErrorMessage(await res.text(), `${res.status} ${res.statusText}`)
      toast(msg, 'error')
      throw new Error(msg)
    }
    if (!res.body) throw new Error('响应无 body')

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      // 按行分割(保留最后不完整的行在 buf)
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        const s = line.trim()
        if (!s) continue
        try {
          yield JSON.parse(s)
        } catch {
          // 忽略无法解析的行
        }
      }
    }
    // 处理残余
    if (buf.trim()) {
      try { yield JSON.parse(buf.trim()) } catch { /* ignore */ }
    }
  },

  // ===== 个股分析 =====
  stockAnalysisLevels: (symbol: string, days = 120) =>
    request<StockLevels>(`/api/stock-analysis/levels?symbol=${encodeURIComponent(symbol)}&days=${days}`),


  pageAiReportsList: () =>
    request<{ reports: AiPageReport[] }>('/api/page-ai/reports'),

  pageAiReportGet: (reportId: string) =>
    request<{ report: AiPageReport }>(`/api/page-ai/reports/${encodeURIComponent(reportId)}`),

  pageAiReportSave: (r: {
    title: string
    route?: string
    as_of?: string | null
    focus?: string
    summary?: string
    content: string
    session_id?: string
  }) =>
    request<{ ok: boolean; report: AiPageReport }>('/api/page-ai/reports', {
      method: 'POST', body: JSON.stringify(r),
    }),
  stockAnalysisReportsList: () =>
    request<{ reports: AiStockReport[] }>('/api/stock-analysis/reports'),

  stockAnalysisReportSave: (r: {
    symbol: string; name?: string; focus?: string; content: string
    summary?: string; close?: number | null
    levels?: Record<LevelType, PriceLevel[]>
  }) =>
    request<{ ok: boolean; report: AiStockReport }>('/api/stock-analysis/reports', {
      method: 'POST', body: JSON.stringify(r),
    }),

  stockAnalysisReportDelete: (reportId: string) =>
    request<{ ok: boolean }>(`/api/stock-analysis/reports/${encodeURIComponent(reportId)}`, { method: 'DELETE' }),

  /**
   * AI 个股四维分析 — 流式调用(NDJSON,与财务分析同协议)。
   * meta 里额外带 levels(关键价位)供图表回放。
   */
  async *stockAnalyzeStream(symbol: string, focus?: string): AsyncGenerator<{
    type: 'meta' | 'delta' | 'error' | 'done'
    symbol?: string
    summary?: string
    levels?: Record<LevelType, PriceLevel[]>
    close?: number | null
    content?: string
    message?: string
  }> {
    const res = await fetch('/api/stock-analysis/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, focus: focus ?? '' }),
    })
    if (!res.ok) {
      const msg = extractErrorMessage(await res.text(), `${res.status} ${res.statusText}`)
      toast(msg, 'error')
      throw new Error(msg)
    }
    if (!res.body) throw new Error('响应无 body')

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        const s = line.trim()
        if (!s) continue
        try { yield JSON.parse(s) } catch { /* ignore */ }
      }
    }
    if (buf.trim()) {
      try { yield JSON.parse(buf.trim()) } catch { /* ignore */ }
    }
  },

  // ===== 大盘复盘 =====
  reviewReportsList: () =>
    request<{ reports: AiReviewReport[] }>('/api/market-recap/reports'),

  reviewReportSave: (r: {
    as_of: string; focus?: string; content: string
    summary?: string; emotion_score?: number | null; emotion_label?: string
  }) =>
    request<{ ok: boolean; report: AiReviewReport }>('/api/market-recap/reports', {
      method: 'POST', body: JSON.stringify(r),
    }),

  reviewReportDelete: (reportId: string) =>
    request<{ ok: boolean }>(`/api/market-recap/reports/${encodeURIComponent(reportId)}`, { method: 'DELETE' }),

  /**
   * AI 大盘复盘 — 流式调用(NDJSON,与个股/财务分析同协议)。
   * meta 里带 as_of / emotion_score / emotion_label / summary,供前端先渲染信号灯。
   */
  async *reviewStream(asOf?: string, focus?: string): AsyncGenerator<{
    type: 'meta' | 'delta' | 'error' | 'done'
    as_of?: string
    emotion_score?: number
    emotion_label?: string
    summary?: string
    content?: string
    message?: string
  }> {
    const res = await fetch('/api/market-recap/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ as_of: asOf ?? null, focus: focus ?? '' }),
    })
    if (!res.ok) {
      const msg = extractErrorMessage(await res.text(), `${res.status} ${res.statusText}`)
      toast(msg, 'error')
      throw new Error(msg)
    }
    if (!res.body) throw new Error('响应无 body')

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        const s = line.trim()
        if (!s) continue
        try { yield JSON.parse(s) } catch { /* ignore */ }
      }
    }
    if (buf.trim()) {
      try { yield JSON.parse(buf.trim()) } catch { /* ignore */ }
    }
  },

  // ===== Strategy Engine =====
  strategyList: (ownerUserId?: string) =>
    request<{ strategies: StrategyDetail[]; owner_user_id?: string }>(
      `/api/strategies${ownerUserId ? `?owner_user_id=${encodeURIComponent(ownerUserId)}` : ''}`,
    ),

  strategyGet: (id: string, ownerUserId?: string) =>
    request<StrategyDetail>(
      `/api/strategies/${encodeURIComponent(id)}${ownerUserId ? `?owner_user_id=${encodeURIComponent(ownerUserId)}` : ''}`,
    ),

  strategyRun: (strategyId: string, params?: Record<string, any>, asOf?: string, pool?: string[], ownerUserId?: string) =>
    request<ScreenerResult>('/api/strategies/run', {
      method: 'POST',
      body: JSON.stringify({ strategy_id: strategyId, owner_user_id: ownerUserId ?? null, params, as_of: asOf ?? null, pool }),
    }),

  strategyRunAll: (asOf?: string) =>
    request<{ as_of: string | null; results: Record<string, { total: number; as_of: string }> }>(
      '/api/strategies/run-all',
      { method: 'POST', body: JSON.stringify({ as_of: asOf ?? null }) },
    ),

  strategySaveConfig: (strategyId: string, overrides: Record<string, any>) =>
    request<{ ok: boolean }>('/api/strategies/config', {
      method: 'POST',
      body: JSON.stringify({ strategy_id: strategyId, overrides }),
    }),

  strategyResetConfig: (strategyId: string) =>
    request<{ ok: boolean }>(`/api/strategies/config/${strategyId}`, { method: 'DELETE' }),

  /** 删除自定义策略（内置策略不可删除） */
  strategyDelete: (strategyId: string) =>
    request<{ ok: boolean }>(`/api/strategies/user/${encodeURIComponent(strategyId)}`, { method: 'DELETE' }),

  strategyReload: () =>
    request<{ ok: boolean; count: number }>('/api/strategies/reload', { method: 'POST' }),

  // ===== Custom Signals (自定义信号) =====
  customSignalsList: () =>
    request<{ signals: CustomSignal[] }>('/api/custom-signals'),

  customSignalsOptions: () =>
    request<CustomSignalOptions>('/api/custom-signals/options'),

  customSignalSave: (signal: CustomSignal) =>
    request<{ ok: boolean; signal: CustomSignal }>('/api/custom-signals', {
      method: 'POST',
      body: JSON.stringify(signal),
    }),

  customSignalDelete: (id: string) =>
    request<{ ok: boolean }>(`/api/custom-signals/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  // ===== Monitor Rules (监控规则) =====
  monitorRulesList: () =>
    request<{ rules: MonitorRule[] }>('/api/monitor-rules'),

  monitorRuleOptions: () =>
    request<MonitorRuleOptions>('/api/monitor-rules/options'),

  monitorRuleSave: (rule: MonitorRule) =>
    request<{ ok: boolean; rule: MonitorRule }>('/api/monitor-rules', {
      method: 'POST',
      body: JSON.stringify(rule),
    }),

  monitorRuleDelete: (id: string) =>
    request<{ ok: boolean }>(`/api/monitor-rules/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  /** 生成演示监控规则 (Dev 页用) */
  monitorRuleSeed: () =>
    request<{ ok: boolean; generated: number }>('/api/monitor-rules/seed', { method: 'POST' }),

  // ===== Alerts (触发记录) =====
  alertsList: (params?: { days?: number; limit?: number; source?: string; type?: string; extColumns?: string }) => {
    const qs = new URLSearchParams()
    if (params?.days) qs.set('days', String(params.days))
    if (params?.limit) qs.set('limit', String(params.limit))
    if (params?.source) qs.set('source', params.source)
    if (params?.type) qs.set('type', params.type)
    if (params?.extColumns) qs.set('ext_columns', params.extColumns)
    const s = qs.toString()
    return request<{ alerts: AlertEvent[]; total: number }>(`/api/alerts${s ? `?${s}` : ''}`)
  },

  alertsClear: () =>
    request<{ ok: boolean; cleared: number }>('/api/alerts', { method: 'DELETE' }),

  alertDelete: (ts: number) =>
    request<{ ok: boolean }>(`/api/alerts/${ts}`, { method: 'DELETE' }),

  /** 生成演示触发记录 (Dev 页用) */
  alertSeed: (count = 12, recent = true) =>
    request<{ ok: boolean; generated: number }>(`/api/alerts/seed?count=${count}&recent=${recent}`, { method: 'POST' }),

  /** 检查 AI 配置状态 */
  strategyAiStatus: () =>
    request<{ configured: boolean; has_key: boolean; has_model: boolean; provider?: string; access_state?: string; message?: string }>('/api/strategies/ai/status'),

  /** 测试 AI 连通性 */
  strategyAiTest: () =>
    request<{ ok: boolean; error?: string; model?: string; response?: string; usage?: { prompt: number; completion: number } }>(
      '/api/strategies/ai/test',
      { method: 'POST' },
    ),

  /** 获取策略源文件内容 */
  strategyGetSource: (id: string, ownerUserId?: string) =>
    request<{ code: string; source: string }>(
      `/api/strategies/${encodeURIComponent(id)}/source${ownerUserId ? `?owner_user_id=${encodeURIComponent(ownerUserId)}` : ''}`,
    ),
  strategyBuild: (step: number, payload: Record<string, any>) =>
    request<{ code: string; meta: Record<string, any>; valid: boolean; error: string | null }>(
      '/api/strategies/build',
      { method: 'POST', body: JSON.stringify({ step, ...payload }) },
    ),

  /** 保存 AI 生成的策略文件 */
  strategySaveCode: (strategyId: string, code: string) =>
    request<{ ok: boolean; path: string; strategy?: Record<string, any> }>('/api/strategies/ai/save', {
      method: 'POST',
      body: JSON.stringify({ strategy_id: strategyId, code }),
    }),


  // ===== Upstream v0.2.2 API extras =====

  dataSources: () => request<DataSourcesResponse>('/api/settings/data-sources'),

  capabilityMatrix: () => request<CapabilityMatrix>('/api/settings/capability-matrix'),

  dataSource: (name: string) => request<CustomSourceConfig>(`/api/settings/data-sources/${encodeURIComponent(name)}`),

  saveDataSource: (config: CustomSourceConfig) =>
    request<DataSourcesResponse>('/api/settings/data-sources', {
      method: 'POST',
      body: JSON.stringify(config),
    }),

  deleteDataSource: (name: string) =>
    request<DataSourcesResponse>(`/api/settings/data-sources/${encodeURIComponent(name)}`, { method: 'DELETE' }),

  reloadDataSources: () => request<DataSourcesResponse>('/api/settings/data-sources/reload', { method: 'POST' }),

  installPlugin: (name: string) => {
    // npm install 可能耗时较长, 用 6 分钟超时
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 360_000)
    return request<DataSourcesResponse & { install_ok: boolean; install_message: string }>(
      `/api/settings/plugins/${encodeURIComponent(name)}/install`,
      { method: 'POST', signal: controller.signal },
    ).finally(() => clearTimeout(timer))
  },

  uninstallPlugin: (name: string) =>
    request<DataSourcesResponse & { uninstall_ok: boolean; uninstall_message: string }>(
      `/api/settings/plugins/${encodeURIComponent(name)}/install`,
      { method: 'DELETE' },
    ),

  savePluginKey: (plugin: string, apiKey: string) => {
    // 先探后存: 后端会用候选 Key 实探一次, 探测超时 10s + 余量
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 30_000)
    return request<PluginKeyResult>('/api/settings/plugin-key', {
      method: 'POST',
      body: JSON.stringify({ plugin, api_key: apiKey }),
      signal: controller.signal,
    }).finally(() => clearTimeout(timer))
  },

  clearPluginKey: (plugin: string) =>
    request<PluginKeyResult>(`/api/settings/plugin-key/${encodeURIComponent(plugin)}`, { method: 'DELETE' }),

  testDataSource: (
    provider: string,
    dataset: string,
    symbols?: string[],
    config?: CustomSourceConfig,
  ) =>
    request<DataSourceTestResult>('/api/settings/data-sources/test', {
      method: 'POST',
      body: JSON.stringify({ provider, dataset, symbols, config }),
    }),

  updateDataProviders: (cfg: Partial<Pick<Preferences, ProviderField>>) =>
    request<Pick<Preferences, ProviderField>>(
      '/api/settings/preferences/data-providers',
      { method: 'PUT', body: JSON.stringify(cfg) },
    ),

  updateDataSourceJobTimeouts: (dataSourceJobTimeoutS: number, dataSourceLongJobTimeoutS: number) =>
    request<Pick<Preferences, 'data_source_job_timeout_s' | 'data_source_long_job_timeout_s'>>(
      '/api/settings/preferences/data-source-job-timeouts',
      {
        method: 'PUT',
        body: JSON.stringify({
          data_source_job_timeout_s: dataSourceJobTimeoutS,
          data_source_long_job_timeout_s: dataSourceLongJobTimeoutS,
        }),
      },
    ),

  minuteRefreshStatus: () =>
    request<{
      available: boolean
      enabled?: boolean
      running?: boolean
      interval_seconds?: number
      capability_ok?: boolean
      custom_provider_active?: boolean
      in_trading_hours?: boolean
      gate_reason?: string | null
      rounds?: number
      last_round_at?: number | null
      last_round_ms?: number | null
      last_rows?: number
      last_symbols?: number
      last_requests?: number
      next_round_at?: number | null
      last_error?: string | null
    }>('/api/settings/minute-refresh/status'),

  updateWatchlistGroupsInNav: (enabled: boolean) =>
    request<{ watchlist_groups_in_nav: boolean }>('/api/settings/preferences/watchlist-groups-in-nav', {
      method: 'PUT',
      body: JSON.stringify({ watchlist_groups_in_nav: enabled }),
    }),

  updateWecomWebhook: (url: string) =>
    request<{ wecom_webhook_url: string }>('/api/settings/preferences/wecom-webhook', {
      method: 'PUT',
      body: JSON.stringify({ url }),
    }),

  updateWecomBot: (botId: string, secret: string, enabled: boolean = true) =>
    request<{
      wecom_bot_id: string
      wecom_bot_secret: string
      wecom_bot_enabled: boolean
      wecom_bot_status: WecomBotStatus
    }>('/api/settings/preferences/wecom-bot', {
      method: 'PUT',
      body: JSON.stringify({ bot_id: botId, secret, enabled }),
    }),

  toggleWecomBot: (enabled: boolean) =>
    request<{ wecom_bot_enabled: boolean; wecom_bot_status: WecomBotStatus }>('/api/settings/preferences/wecom-bot-toggle', {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    }),

  updateWebhookDefaultChannels: (channels: string[]) =>
    request<{ webhook_default_channels: string[] }>('/api/settings/preferences/webhook-default-channels', {
      method: 'PUT',
      body: JSON.stringify({ channels }),
    }),

  klineMinuteBatch: (symbols: string[], date?: string) =>
    request<{ data: Record<string, MinuteKlineRow[]> }>('/api/kline/minute-batch', {
      method: 'POST',
      body: JSON.stringify({ symbols, date }),
    }),

  klineMinuteRange: (symbol: string, days = 10) =>
    request<{
      symbol: string
      name?: string
      asset_type: 'stock' | 'etf' | 'index'
      requested_days: number
      sessions: MinuteKlineSession[]
      source: 'local' | 'none'
    }>(
      `/api/kline/minute-range?symbol=${encodeURIComponent(symbol)}&days=${days}`,
    ),

  syncMinuteSingle: (symbol: string, days?: number) =>
    request<{ status: string; symbol: string; rows: number }>('/api/kline/sync_minute_single', {
      method: 'POST',
      body: JSON.stringify({ symbol, ...(days != null ? { days } : {}) }),
    }),

  clearMinute: () =>
    request<{ status: string; removed: number }>('/api/kline/clear_minute', {
      method: 'POST',
      body: JSON.stringify({ confirm: true }),
    }),

  watchlistGroups: () =>
    request<{ groups: WatchlistGroup[] }>('/api/watchlist/groups'),

  watchlistGroupCreate: (name: string, color: WatchlistGroupColor) =>
    request<{ groups: WatchlistGroup[]; group: WatchlistGroup }>('/api/watchlist/groups', {
      method: 'POST',
      body: JSON.stringify({ name, color }),
    }),

  watchlistGroupRename: (groupId: string, name: string, color: WatchlistGroupColor) =>
    request<{ groups: WatchlistGroup[] }>(
      `/api/watchlist/groups/${encodeURIComponent(groupId)}`,
      { method: 'PUT', body: JSON.stringify({ name, color }) },
    ),

  watchlistGroupReorder: (orderedIds: string[]) =>
    request<{ groups: WatchlistGroup[] }>('/api/watchlist/groups/reorder', {
      method: 'PUT',
      body: JSON.stringify({ ordered_ids: orderedIds }),
    }),

  watchlistGroupDelete: (groupId: string) =>
    request<{ groups: WatchlistGroup[]; symbols: WatchlistEntry[] }>(
      `/api/watchlist/groups/${encodeURIComponent(groupId)}`,
      { method: 'DELETE' },
    ),

  watchlistGroupClear: (groupId: string) =>
    request<{ symbols: WatchlistEntry[] }>(
      `/api/watchlist/groups/${encodeURIComponent(groupId)}/clear`,
      { method: 'POST' },
    ),

  watchlistSetGroup: (symbol: string, groupId: string | null) =>
    request<{ symbols: WatchlistEntry[] }>(
      `/api/watchlist/${encodeURIComponent(symbol)}/group`,
      { method: 'PUT', body: JSON.stringify({ group_id: groupId }) },
    ),

  watchlistGroupAddMember: (groupId: string, symbol: string) =>
    request<{ symbols: WatchlistEntry[] }>(
      `/api/watchlist/groups/${encodeURIComponent(groupId)}/members/${encodeURIComponent(symbol)}`,
      { method: 'POST' },
    ),

  watchlistGroupRemoveMember: (groupId: string, symbol: string) =>
    request<{ symbols: WatchlistEntry[] }>(
      `/api/watchlist/groups/${encodeURIComponent(groupId)}/members/${encodeURIComponent(symbol)}`,
      { method: 'DELETE' },
    ),

  screenerCachedSummary: () =>
    request<ScreenerCachedSummary>('/api/screener/cached-summary'),

  screenerCachedResult: (strategyId: string, extColumns?: string) =>
    request<ScreenerCachedResult>(
      extColumns
        ? `/api/screener/cached-result/${encodeURIComponent(strategyId)}?ext_columns=${encodeURIComponent(extColumns)}`
        : `/api/screener/cached-result/${encodeURIComponent(strategyId)}`,
    ),

  regimePhases: (start?: string, end?: string) => {
    const params = new URLSearchParams()
    if (start) params.set('start', start)
    if (end) params.set('end', end)
    const qs = params.toString()
    return request<PhaseSegments>(`/api/regime/phases${qs ? `?${qs}` : ''}`)
  },

  regimeMainline: (start?: string, end?: string, top = 10, kind: 'concept' | 'industry' = 'concept') => {
    const params = new URLSearchParams({ top: String(top), kind })
    if (start) params.set('start', start)
    if (end) params.set('end', end)
    return request<MainlineResult>(`/api/regime/mainline?${params.toString()}`)
  },

  regimeMainlineRecompute: () =>
    request<{ ok: boolean; rows: number }>('/api/regime/mainline/recompute', { method: 'POST' }),

  mainlineFilterUpdate: (payload: { min_members?: number; max_members?: number; blacklist?: string[]; exclude_st?: boolean }) =>
    request<MainlineFilter>('/api/settings/preferences/mainline-filter', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  factorBatch: (payload: {
    factor_names: string[]
    symbols?: string[] | null
    start?: string | null
    end?: string | null
    n_groups?: number
    rebalance?: 'daily' | 'weekly' | 'monthly'
    weight?: 'equal' | 'factor_weight'
    fees_pct?: number
    slippage_bps?: number
    asset_type?: 'stock' | 'etf' | 'index'
  }) =>
    request<FactorBatchResult>('/api/backtest/factor/batch', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  miningRuns: () =>
    request<{ items: MiningRun[] }>('/api/backtest/mining/runs'),

  miningAvailability: (params: {
    assetType: 'stock' | 'etf'
    budgetProfile: MiningBudgetProfile
    start?: string
    end?: string
  }) => {
    const query = new URLSearchParams({
      asset_type: params.assetType,
      budget_profile: params.budgetProfile,
    })
    if (params.start) query.set('start', params.start)
    if (params.end) query.set('end', params.end)
    return request<MiningAvailability>(`/api/backtest/mining/availability?${query}`)
  },

  miningRun: (runId: string) =>
    request<MiningRun>(`/api/backtest/mining/runs/${encodeURIComponent(runId)}`),

  miningStart: (payload: MiningRequestV1) =>
    request<MiningRun>('/api/backtest/mining/runs', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  miningResult: (runId: string) =>
    request<MiningResult>(`/api/backtest/mining/runs/${encodeURIComponent(runId)}/result`),

  miningCancel: (runId: string) =>
    request<MiningRun>(`/api/backtest/mining/runs/${encodeURIComponent(runId)}/cancel`, {
      method: 'POST',
    }),

  miningPromote: (runId: string, signature: string) =>
    request<ResearchCandidate>(
      `/api/backtest/mining/runs/${encodeURIComponent(runId)}/candidates/${encodeURIComponent(signature)}/promote`,
      { method: 'POST' },
    ),

  miningPublish: (runId: string, signature: string) =>
    request<{ ok: boolean; strategy_id: string }>(
      `/api/backtest/mining/runs/${encodeURIComponent(runId)}/candidates/${encodeURIComponent(signature)}/publish`,
      { method: 'POST' },
    ),

  miningConfig: () =>
    request<MiningScheduleConfig>('/api/backtest/mining/config'),

  updateMiningConfig: (payload: Partial<MiningScheduleConfig>) =>
    request<MiningScheduleConfig>('/api/backtest/mining/config', {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  researchCandidates: () =>
    request<{ items: ResearchCandidate[] }>('/api/backtest/candidates'),

  researchCandidateCreate: (payload: ResearchCandidateCreate) =>
    request<ResearchCandidate>('/api/backtest/candidates', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  researchCandidateUpdate: (
    id: string,
    payload: { name?: string; status?: ResearchCandidateStatus },
  ) =>
    request<ResearchCandidate>(`/api/backtest/candidates/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  researchCandidateDelete: (id: string) =>
    request<{ ok: boolean }>(`/api/backtest/candidates/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    }),

  refreshCache: () => request<{ ok: boolean }>('/api/data/refresh-cache', { method: 'POST' }),

  dimensionIntraday: (id: string, opts: { field: string; value: string; date?: string }) => {
    const qs = new URLSearchParams({ field: opts.field, value: opts.value })
    if (opts.date) qs.set('date', opts.date)
    return request<DimensionIntradayResult>(`/api/ext-data/${encodeURIComponent(id)}/dimension-intraday?${qs.toString()}`)
  },

  extDataDetectUrl: (body: ExtDataDetectUrlRequest) =>
    request<ExtDataDetectUrlResult>('/api/ext-data/detect-url', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  dragonTiger: (date?: string) =>
    request<DragonTigerPayload>(
      `/api/market-recap/dragon-tiger${date ? `?date=${encodeURIComponent(date)}` : ''}`,
    ),

  auctionBenchmark: (date?: string) =>
    request<AuctionBenchmarkPayload>(
      `/api/market-recap/auction-benchmark${date ? `?date=${encodeURIComponent(date)}` : ''}`,
    ),

  strategyPatchConfig: (strategyId: string, overrides: Record<string, any>) =>
    request<{ ok: boolean }>('/api/strategies/config', {
      method: 'PATCH',
      body: JSON.stringify({ strategy_id: strategyId, overrides }),
    }),

  customSignalsAiGenerate: (description: string) =>
    request<CustomSignalAIGenerateResult>('/api/custom-signals/ai/generate', {
      method: 'POST',
      body: JSON.stringify({ description }),
    }),

  abnormalOverview: (minCloseness = 0.5, limit = 200) =>
    request<AbnormalOverview>(
      `/api/abnormal/overview?min_closeness=${minCloseness}&limit=${limit}`,
    ),

  abnormalIntraday: (limit = 500) =>
    request<AbnormalIntradayPayload>(`/api/abnormal/intraday?limit=${limit}`),

  monitorRuleTestLadder: () =>
    request<{
      ok: boolean
      as_of: string
      sealed_count: number
      triggered: Array<{
        rule_id: string; rule_name: string; symbol: string; name?: string
        type: string; message: string; severity: string
        sealed_value: number; sealed_metric: string
        current_sealed_vol?: number; current_sealed_amount?: number
      }>
      not_triggered: Array<{
        rule_id: string; rule_name: string; symbol: string
        metric: string; threshold: number; current_value: number | null
        current_sealed_vol?: number; current_sealed_amount?: number | null
        reason: string
      }>
    }>('/api/monitor-rules/test-ladder', { method: 'POST' }),

  monitorRuleTriggerLadder: () =>
    request<{
      ok: boolean
      triggered: number
      events: Array<{ symbol: string; name: string; message: string }>
    }>('/api/monitor-rules/trigger-ladder', { method: 'POST' }),

  strategyValidateCode: (payload: { code: string; strategy_id?: string; name?: string; description?: string }) =>
    request<StrategyBuildResult>('/api/strategies/code/validate', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  strategySaveCodeV2: (payload: {
    strategy_id: string
    code: string
    target_source: 'ai' | 'custom'
    mode: 'create' | 'update'
    name?: string
    description?: string
  }) =>
    request<StrategyCodeSaveResult>('/api/strategies/code/save', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

}

// ===== Pipeline =====
export interface PipelineJob {
  id: string
  status: 'pending' | 'running' | 'succeeded' | 'degraded' | 'failed'
  stage: string
  progress: number          // 0-100 整体进度
  stage_pct: number         // 0-100 当前阶段内进度
  log: { ts: string; stage: string; msg: string }[]
  started_at: string | null
  finished_at: string | null
  duration_s: number | null
  result: {
    universe_size: number
    daily_days: number
    adj_factor_symbols: number
    enriched_days: number
    index_count?: number
    index_daily_rows?: number
    minute_rows: number
    minute_sync?: {
      status?: string
      reason?: string | null
      reason_code?: string
      user_enabled?: boolean
      rows?: number
      fallback_hint?: string | null
    }
    skipped_stages?: string[]
    quality?: {
      ok: boolean
      date?: string | null
      issues?: Array<{ code: string; message?: string; count?: number; market?: string }>
      metrics?: Record<string, unknown>
    } | null
  } | null
  error: string | null
}

export type PipelineJobSummary = Omit<PipelineJob, 'log'>

// ===== Data status =====
interface TableStats {
  rows: number
  earliest_date: string | null
  latest_date: string | null
  symbols_covered: number
  trading_days: number
}

export interface DataReadiness {
  daily: Pick<TableStats, 'earliest_date' | 'latest_date' | 'trading_days'> | null
  enriched: Pick<TableStats, 'earliest_date' | 'latest_date' | 'trading_days'> | null
}

interface InstrumentsStats {
  rows: number
  symbols_covered: number
  latest_as_of: string | null
  named: number
}

export interface DataStatus {
  daily: TableStats | null
  enriched: TableStats | null
  quote_snapshot?: Pick<TableStats, 'earliest_date' | 'latest_date' | 'trading_days'> | null
  index_daily: TableStats | null
  index_enriched: TableStats | null
  index_instruments: InstrumentsStats | null
  etf_daily: TableStats | null
  etf_enriched: TableStats | null
  etf_instruments: InstrumentsStats | null
  minute: TableStats | null
  adj_factor: TableStats | null
  instruments: InstrumentsStats | null
  financials: { rows: number; symbols?: number; tables?: Record<string, { rows: number; symbols: number }> } | null
  storage: {
    daily_files: number
    daily_size_mb: number
    enriched_files: number
    enriched_size_mb: number
    index_daily_files?: number
    index_daily_size_mb?: number
    index_enriched_files?: number
    index_enriched_size_mb?: number
    index_instruments_files?: number
    index_instruments_size_mb?: number
    etf_daily_files?: number
    etf_daily_size_mb?: number
    etf_enriched_files?: number
    etf_enriched_size_mb?: number
    etf_instruments_files?: number
    etf_instruments_size_mb?: number
    etf_adj_factor_files?: number
    etf_adj_factor_size_mb?: number
    minute_files: number
    minute_size_mb: number
    adj_factor_files: number
    adj_factor_size_mb: number
    instruments_files: number
    instruments_size_mb: number
    financials_files?: number
    financials_size_mb?: number
    ext_data_files?: number
    ext_data_size_mb?: number
    total_size_mb: number
  }
  next_pipeline_run: string | null
  next_instruments_run: string | null
  last_pipeline_run: string | null
  last_instruments_run: string | null
  checked_at: string
}

export interface EnrichedField {
  name: string
  type: string
  desc: string
}


// ===== 主力资金流（东财公开接口缓存） =====
export interface ChipCostRange {
  low_price: number
  high_price: number
  concentration: number
}

export interface ChipBinItem {
  price: number
  vol: number
  ratio: number
}

export interface ChipDistribution {
  symbol: string
  as_of?: string | null
  days: number
  bins: number
  current: number
  avg_cost: number
  median_cost: number
  profit_ratio: number
  min_price: number
  max_price: number
  sum_vol: number
  cost70: ChipCostRange
  cost90: ChipCostRange
  items: ChipBinItem[]
  method?: string
  disclaimer?: string
  source?: string
}

export interface ChipDistributionResponse {
  ok: boolean
  data: ChipDistribution
}

export interface FundFlowItem {
  code?: string | null
  name: string
  main_net: number | null
  change_pct?: number | null
  rank?: number | null
  as_of?: string | null
  kind?: string | null
  source?: string | null
  unit_amount?: string | null
  days?: number | null
  window_days?: number | null
  coverage_pct?: number | null
}

export interface FundFlowListResponse {
  ok: boolean
  items: FundFlowItem[]
  count: number
  cached?: boolean
  rows?: number
  source?: string
}

export interface FundFlowWindowResponse {
  ok: boolean
  kind: 'board' | 'concept'
  window_days: number
  requested_days?: number
  window_complete?: boolean
  window_label: string
  trading_days: number
  start?: string | null
  end?: string | null
  prior_start?: string | null
  prior_end?: string | null
  snapshot_count: number
  covered_count: number
  full_count?: number
  missing_count: number
  coverage_pct: number
  items: FundFlowItem[]
  missing: Array<{ code?: string | null; name?: string | null; days?: number | null }>
  prior_available: boolean
  prior_note?: string | null
  window_note?: string | null
  source?: string
}

export interface FundFlowHistoryPoint {
  code?: string
  name?: string
  date: string
  main_net: number | null
  small_net?: number | null
  med_net?: number | null
  large_net?: number | null
  super_net?: number | null
  main_net_pct?: number | null
  source?: string | null
  unit_amount?: string | null
}

export interface FundFlowIntradayPoint {
  code?: string
  name?: string
  timestamp?: string
  time?: string
  date?: string
  main_net: number | null
  small_net?: number | null
  med_net?: number | null
  large_net?: number | null
  super_net?: number | null
  source?: string | null
  unit_amount?: string | null
}

export interface FundFlowHistoryRefreshResponse {
  ok: boolean
  kind: string
  ranking_count: number
  selected: number
  history_codes: string[]
  history_points: number
  failed?: Array<{ code: string; error: string }>
  source?: string
}

export interface FundFlowBoardHistoryResponse {
  ok: boolean
  code: string
  kind: string
  rows: FundFlowHistoryPoint[]
  count: number
  cached?: boolean
  source?: string
  warning?: string
}

export interface FundFlowBoardIntradayResponse {
  ok: boolean
  code: string
  kind: string
  name?: string
  trade_date?: string
  updated_time?: string
  points: FundFlowIntradayPoint[]
  count: number
  cached?: boolean
  source?: string
  warning?: string
}

// ===== 扩展数据 =====
export interface ExtDataField {
  name: string
  dtype: string
  label: string
}

export interface PullConfig {
  url: string
  method: string
  headers?: Record<string, string>
  body?: string | null
  response_path: string
  field_map?: Record<string, string>
  schedule_minutes: number
  enabled: boolean
  last_run?: string | null
  last_status?: string | null
  last_message?: string | null
  last_rows?: number | null
  next_run?: string | null
}

export interface ExtDataConfig {
  id: string
  label: string
  mode: 'snapshot' | 'timeseries'
  fields: ExtDataField[]
  description?: string
  symbol_map?: Record<string, string>
  code_map?: Record<string, string>
  created_at: string
  updated_at: string
  latest_sync_date?: string | null
  date_range?: string[] | null
  pull?: PullConfig | null
}

export interface ExtDataRowsResult {
  id: string
  label: string
  mode: 'snapshot' | 'timeseries'
  date: string | null
  total: number
  limit: number
  fields: ExtDataField[]
  rows: Record<string, any>[]
}

export interface AnalysisColumn {
  field: string
  label?: string
  type?: 'string' | 'number' | 'percent' | 'amount' | 'date'
  width?: number | null
  sortable?: boolean
  precision?: number | null
  format?: string | null
  aggregate?: 'count' | 'avg' | 'sum' | 'min' | 'max' | null
  visible?: boolean
}

export interface AnalysisMenu {
  id: string
  label: string
  icon: string
  data_source: string
  template: 'dimension_rank' | 'ranking' | 'table'
  dimension_field?: string | null
  rank_field?: string | null
  group_columns: AnalysisColumn[]
  detail_columns: AnalysisColumn[]
  default_sort?: { field: string; order: 'asc' | 'desc' } | null
  visible: boolean
  order: number
  created_at?: string | null
  updated_at?: string | null
  builtin?: boolean
}
