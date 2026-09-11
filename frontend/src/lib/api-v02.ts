/** Upstream v0.2.2 types that local api.ts did not have. */

export type AbnormalStatus = 'triggered' | 'edge' | 'watch'
export type IntradaySignalKey = 'limit_up' | 'broken' | 'recovery' | 'limit_down'
  | 'new_high' | 'new_low' | 'volume_surge'
export type MarketPhase = 'ice' | 'ignite' | 'rally' | 'climax' | 'ebb' | 'repair'
export const MARKET_PHASE_LABELS: Record<MarketPhase, string> = {
  ice: '冰点',
  ignite: '启动',
  rally: '主升',
  climax: '高潮',
  ebb: '退潮',
  repair: '修复',
}
export type MiningBudgetProfile = 'exploratory' | 'balanced' | 'strict'
export type MiningRunStatus =
  | 'queued'
  | 'running'
  | 'cancelling'
  | 'succeeded'
  | 'succeeded_with_budget_exhausted'
  | 'failed'
  | 'cancelled'
  | 'interrupted'
  | 'skipped_prerequisite'

export interface CustomSignalCondition {
  left: string
  op: string
  right: string
  leftDays?: number
  rightDays?: number
}

export interface ExtDataField {
  name: string
  dtype?: string
  sample?: unknown
}

export interface MinuteKlineRow {
  datetime: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount: number | null
}
export type ProviderField =
  | 'daily_data_provider'
  | 'adj_factor_provider'
  | 'minute_data_provider'
  | 'full_minute_data_provider'
  | 'depth5_data_provider'
  | 'realtime_data_provider'
  | 'financial_data_provider'
  | 'pool_provider'
export type ResearchCandidateKind = 'factor' | 'strategy'
export type ResearchCandidateStatus = 'pending' | 'validated' | 'rejected'
export type ScoringDirection = 'high' | 'low'
export type SectorKind = 'index' | 'concept' | 'industry'
export type StrategyNotifyEvent = 'buy_signal' | 'sell_signal' | 'pool_entry' | 'pool_exit'
export type StrategyBuildStreamEvent =
  | { type: 'meta'; strategy_id?: string; step?: number }
  | { type: 'delta'; content: string }
  | { type: 'result'; code: string; meta: Record<string, any>; valid: boolean; error: string | null }
  | { type: 'error'; message: string }

export interface AbnormalIntradayPayload {
  cache_date?: string | null
  counts?: Partial<Record<IntradaySignalKey, number>>
  rows?: AbnormalIntradayRow[]
}

export interface AbnormalIntradayRow {
  symbol: string
  name?: string | null
  close?: number | null
  change_pct?: number | null      // 今日涨跌幅 (小数制)
  amplitude?: number | null       // 日振幅 (小数制)
  vol_ratio_5d?: number | null    // 5日量比
  turnover_rate?: number | null   // 换手率 (百分数原值)
  consecutive_limit_ups?: number | null
  signals: IntradaySignalKey[]    // 命中信号 (按优先级排序)
}

export interface AbnormalOverview {
  asof: number
  cache_date: string | null
  bench_rt_pct: number
  includes_today: boolean
  rules: Array<{
    board: string
    st: boolean
    /** 各窗口双侧阈值 {up: 正向, down: 负向} (小数) */
    thresholds: Record<string, { up: number; down: number }>
    note: string
  }>
  counts: { triggered: number; edge: number; watch: number }
  rows: AbnormalRow[]
}

export interface AbnormalRow {
  symbol: string
  name: string | null
  board: string
  st: boolean
  close: number | null
  rt_pct: number | null
  windows: Record<string, AbnormalWindowInfo>
  max_closeness: number
  status: AbnormalStatus
}

export interface AbnormalWindowInfo {
  /** 实时偏离值 (小数) */
  value: number
  /** 该窗口阈值 (小数) — 后端已按偏离方向取对应侧 (严重异动负向更严) */
  threshold: number
  /** 接近度 |value|/threshold */
  closeness: number
}

export interface AuctionBenchmarkItem {
  thscode: string
  ticker?: string | null
  name?: string | null
  auction_pct?: number | null   // 竞价涨跌幅 (百分数原值, 如 9.97 = +9.97%)
  tags?: string[]               // 同花顺概念标签
  day0_oc?: number | null       // 当日开盘买→收盘卖 (小数制, 服务端由本地日K enrich)
  day0_pct?: number | null      // 当日全天涨跌幅 (小数制)
  d1_pct?: number | null        // 次日收盘→收盘 (小数制; 最新交易日无次日为 null)
}

export interface AuctionBenchmarkPayload {
  state: 'ok' | 'fallback_prev' | 'source_unavailable' | 'no_data'
  requested_date?: string | null
  trade_date?: string | null
  count?: number
  message?: string
  items?: AuctionBenchmarkItem[]
}

export interface AuthConfig {
  type: string
  token_env?: string | null
  header?: string
  param?: string
}

export interface CapabilityCandidate {
  name: string
  display: string
  kind: 'builtin' | 'plugin' | 'custom'
  available: boolean
  status: string
  note?: string | null
}

export interface CapabilityMatrix {
  tickflow_tier?: string                           // TickFlow 当前档位基础名 (none/free/...)
  capabilities: CapabilityRoute[]
}

export interface CapabilityRoute {
  id: string
  label: string
  desc: string
  field: ProviderField | null                    // null = 不可路由能力 (仅 TickFlow 提供)
  default: string
  tf_tier: string                                  // TickFlow 所需最低订阅档位
  tf_available: boolean                            // 当前 TickFlow 档位是否提供该能力
  usable: boolean                                  // 生效源当前能否真正提供 (各页能力门控的统一判定)
  current: string                                  // 原始偏好值
  current_display: string
  effective: string                                // 状态解析后的生效源；same_as_daily/public 别名会落到真实候选名
  effective_display: string
  candidates: CapabilityCandidate[]                // 当前可用候选 (按当前 TickFlow 档位过滤)
  pending: CapabilityCandidate[]                   // 声明了该能力但未就绪的源 (置灰提示)
}

export type ExternalReadonlyStatus = 'unconfigured' | 'inaccessible' | 'configured'

export interface ExternalReadonlySources {
  status: ExternalReadonlyStatus
  supported: { id: string; label: string }[]
  note: string
  root_path?: string | null
}

export interface MarginTradingRow {
  symbol?: string
  name?: string
  market?: string
  trade_date?: string | null
  financing_balance?: number | null
  financing_buy_amount?: number | null
  financing_repayment_amount?: number | null
  financing_net_buy_amount?: number | null
  securities_lending_balance?: number | null
  securities_lending_sell_volume?: number | null
  securities_lending_repayment_volume?: number | null
  securities_lending_balance_volume?: number | null
  margin_balance?: number | null
  source?: string | null
  unit_version?: string | null
}

export interface MarginTradingQueryResponse {
  data: MarginTradingRow[]
  count: number
  source: string
  unit_version?: string
  as_of?: string | null
  status: 'ok' | 'empty' | string
  missing_fields?: string[]
  note?: string
}

export interface CompositeChildInfo {
  id: string
  name: string
  source: string
  weight: number
}

export interface CustomSignalAIGenerateResult {
  name: string
  conditions: CustomSignalCondition[]
}

export interface CustomSignalFieldGroup {
  key: string
  label: string
  fields: { key: string; label: string }[]
}

export interface CustomSourceConfig {
  name: string
  display_name: string
  auth: AuthConfig
  datasets: Record<string, DatasetConfig>
}

export interface DataSourceItem {
  name: string
  display_name: string
  datasets: string[]
  path?: string | null
}

export interface DataSourceLoadError {
  name?: string
  path: string
  errors: string[]
}

export interface DataSourceTestResult {
  provider: string
  dataset: string
  rows: number
  columns: string[]
  preview: Record<string, unknown>[]
}

export interface DataSourcesResponse {
  builtin: DataSourceItem[]
  plugins: PluginDataSourceItem[]
  custom: DataSourceItem[]
  errors: DataSourceLoadError[]
  config_dir: string
}

export interface DatasetConfig {
  url: string
  method: string
  batch?: number | null
  rpm?: number | null
  response_path: string
  field_map: Record<string, string>
  transforms?: Record<string, string>
  symbols_param?: string
  start_param?: string
  end_param?: string
  asset_type_param?: string | null
  freq_param?: string | null
  timeout?: number | null
}

export interface DimensionIntradayPoint {
  time: string
  sector: number | null
  market: number | null
}

export interface DimensionIntradayResult {
  status: 'ok' | 'no_data' | 'empty'
  reason?: string | null
  date?: string | null
  basis?: 'prev_close' | 'first_close' | 'mixed' | null
  member_count?: number
  members_with_minute?: number
  points: DimensionIntradayPoint[]
}

export interface DimensionMembersResult {
  id: string
  label: string
  date: string | null
  field: string
  value: string
  total: number
  limit: number
  rows: Record<string, any>[]
}

export interface DragonTigerHotMoney {
  name?: string | null
  buying?: number | null                    // 席位合计净买入 (元)
  rows?: DragonTigerStockItem[] | null      // 关联股票 (字段同 stock item)
}

export interface DragonTigerPayload {
  state: 'ok' | 'fallback_prev' | 'source_unavailable' | 'no_data'
  source?: 'fuyao' | 'hithink_official' | string | null
  requested_date?: string | null
  trade_date?: string | null
  message?: string
  all?: { trade_date?: string | null; stock_count?: number | null; count?: number | null; stock_items?: DragonTigerStockItem[] }
  org?: { trade_date?: string | null; stock_count?: number | null; count?: number | null; stock_items?: DragonTigerStockItem[] }
  hot_money?: { trade_date?: string | null; count?: number | null; hot_money_items?: DragonTigerHotMoney[] }
}

export interface DragonTigerStockItem {
  thscode: string
  ticker?: string | null
  name?: string | null
  change?: number | null      // 当日涨跌幅 (小数制)
  net_value?: number | null   // 龙虎榜净买入 (元)
  net_rate?: number | null    // 净买占比 (小数制)
  buy_value?: number | null   // 买入额 (元)
  sell_value?: number | null  // 卖出额 (元)
  hot_rank?: number | null    // 同花顺人气排名 (小=靠前)
  range_days?: number | null  // 1=当日榜 3=3日榜
  hot_money_net_value?: number | null
  hot_money_item_net_value?: number | null  // 游资榜 rows 专用: 该席位在该股的净买入
  org_net_value?: number | null
  org_net_rate?: number | null
  org_buy_num?: number | null
  org_sell_num?: number | null
  concept_list?: { name?: string }[] | null
}

export interface ExtDataDetectUrlRequest {
  url: string
  method?: string
  headers?: Record<string, string>
  body?: string
  response_path?: string
  field_map?: Record<string, string>
}

export interface ExtDataDetectUrlResult {
  status: string
  total_rows: number
  response_path: string
  response_path_candidates: string[]
  fields: ExtDataField[]
  symbol_candidates: string[]
  code_candidates: string[]
  preview: Record<string, unknown>[]
}

export interface FactorBatchItem {
  factor_name: string
  label: string
  group: string
  ic_mean: number | null
  ir: number | null
  ic_win_rate: number | null
  long_short_return: number | null
  long_short_max_drawdown: number | null
  n_symbols: number
  n_dates: number
  elapsed_ms: number
  error: string | null
  t_naive?: number | null
  t_newey_west?: number | null
  nw_lag?: number | null
  p_value?: number | null
  q_value?: number | null
}

export interface FactorBatchResult {
  run_id: string
  config: Record<string, any>
  results: FactorBatchItem[]
  elapsed_ms: number
  n_symbols: number
  n_dates: number
  error: string | null
}

export interface MainlineFilter {
  min_members: number
  max_members: number
  blacklist: string[]
  exclude_st: boolean
}

export interface MainlineLeader {
  member: string
  top1_days: number
  avg_score: number
  max_boards: number
}

export interface MainlineMemberStat {
  member: string
  top5_days: number
  score_sum: number
  max_boards: number
  leader_symbol: string
}

export interface MainlineResult {
  rows: MainlineRow[]
  leaders: MainlineLeader[]
  membership_note: string
  filter: MainlineFilter
}

export interface MainlineRow {
  date: string
  kind: string
  member: string
  limit_up_count: number
  ge2_count: number
  max_boards: number
  boards_sum: number
  rungs_filled: number
  leader_symbol: string
  score: number
  rank: number
}

export interface MiningAvailability {
  asset_type: 'stock' | 'etf'
  budget_profile: MiningBudgetProfile
  trading_bars: number
  required_bars: number
  outer_folds: number
  required_outer_folds: number
  eligible: boolean
  available_start: string | null
  available_end: string | null
  effective_start: string | null
  effective_end: string | null
  suggested_start: string | null
}

export interface MiningCandidateGate {
  qualified: boolean
  reasons: string[]
}

export interface MiningCandidateRow {
  signature: string
  name: string
  kind: 'factor_combination' | 'existing_strategy'
  factor_names?: string[]
  strategy_id?: string | null
  regime_state?: string | null
  score: number | null
  oos_return: number | null
  oos_sharpe: number | null
  oos_max_drawdown: number | null
  oos_positive_fold_ratio: number | null
  oos_n_trades: number | null
  confidence: 'low' | 'standard' | 'high'
  valid_folds?: number | null
  skipped_folds?: number | null
  promoted_candidate_id?: string | null
  published_strategy_id?: string | null
  gate?: MiningCandidateGate | null
  folds?: MiningFoldRow[]
}

export interface MiningEvent {
  id: number
  type: string
  timestamp?: string
  payload?: Record<string, unknown>
  message?: string
}

export interface MiningFactorRow {
  factor_name: string
  label?: string
  direction: 1 | -1
  score: number | null
  ic_mean: number | null
  ir: number | null
  coverage: number | null
  turnover: number | null
  spread_return?: number | null
  spread_sharpe?: number | null
  selected: boolean
  excluded_reason?: string | null
}

export interface MiningFoldRow {
  fold: number
  label?: string
  train_start?: string
  train_end?: string
  test_start?: string
  test_end?: string
  selected_factors?: string[]
  total_return: number | null
  sharpe: number | null
  max_drawdown?: number | null
  n_trades?: number | null
  skipped?: boolean
  reason?: string | null
  evaluation_kind?: 'selected' | 'cross' | 'benchmark' | null
}

export interface MiningRegimeRow {
  state: 'overall' | 'strong' | 'range' | 'weak' | string
  label: string
  n_dates: number
  total_return: number | null
  sharpe: number | null
  max_drawdown: number | null
}

export interface MiningRequestSummary {
  asset_type: string
  budget_profile: string
  start: string | null
  end: string | null
  factor_count: number
  strategy_count: number
  commission_pct: number | null
  stamp_tax_pct: number | null
  slippage_bps: number | null
  correlation_threshold: number | null
}

export interface MiningRequestV1 {
  factor_names: string[]
  strategy_ids?: string[]
  symbols?: string[] | null
  asset_type?: 'stock' | 'etf'
  start?: string | null
  end?: string | null
  budget_profile?: MiningBudgetProfile
  commission_pct?: number
  stamp_tax_pct?: number
  slippage_bps?: number
  correlation_threshold?: number
  max_combination_factors?: number
  beam_width?: number
  max_finalists?: number
  force?: boolean
  auto_screening?: boolean
  auto?: boolean
}

export interface AutoScreening {
  profile: MiningBudgetProfile
  gate: { min_abs_ic: number; min_abs_ir: number; min_abs_t: number; max_q: number }
  screen_window: { start: string; end: string }
  n_total: number
  n_qualified: number
  pool: string[]
  pool_truncated: boolean
  qualified: Array<{
    factor_name: string
    label: string
    group: string
    ic: number | null
    ir: number | null
    t: number | null
    q: number | null
    direction: 1 | -1
  }>
  failed: Array<{
    factor_name: string
    label: string
    group: string
    ic: number | null
    ir: number | null
    t: number | null
    q: number | null
    reason: string
  }>
  reason_counts: Record<string, number>
  elapsed_ms: number
}

export interface MiningAutoStartPayload {
  asset_type?: 'stock' | 'etf'
  start?: string | null
  end?: string | null
  budget_profile?: MiningBudgetProfile
  correlation_threshold?: number
  force?: boolean
}

export interface MiningAutoStartResponse {
  started: boolean
  reason?: string
  run?: MiningRun
  screening?: AutoScreening
}

export interface MiningResult {
  run_id: string
  methodology_version: string
  algorithm_version: string
  data_as_of: string | null
  summary: MiningResultSummary
  request_summary?: MiningRequestSummary | null
  factors: MiningFactorRow[]
  correlation: {
    labels: string[]
    matrix: (number | null)[][]
    pair_counts?: (number | null)[][]
    threshold: number
  }
  regimes: MiningRegimeRow[]
  candidates: MiningCandidateRow[]
  folds: MiningFoldRow[]
  telemetry: MiningTelemetry
}

export interface MiningResultSummary {
  factor_count: number
  selected_factor_count: number
  candidate_count: number
  valid_fold_count: number
  skipped_fold_count: number
  confidence: 'low' | 'standard' | 'high'
  budget_exhausted?: boolean
  elapsed_ms?: number
  peak_rss_bytes?: number
}

export interface MiningRun {
  run_id: string
  signature: string
  status: MiningRunStatus
  request: MiningRequestV1 & { auto?: boolean; auto_screening?: boolean | AutoScreening }
  source?: 'manual' | 'scheduled' | 'auto'
  created_at: string
  updated_at: string
  started_at?: string | null
  finished_at?: string | null
  data_as_of?: string | null
  progress?: MiningRunProgress | null
  error?: string | null
  reused?: boolean
  summary?: MiningResultSummary | null
}

export interface MiningRunProgress {
  phase: string
  label?: string
  done?: number
  total?: number
  percent?: number
  elapsed_ms?: number
  message?: string
}

export interface MiningScheduleConfig {
  mining_schedule_enabled: boolean
  mining_schedule_weekday: number
  mining_budget_profile: Exclude<MiningBudgetProfile, 'exploratory'>
}

export interface MiningTelemetry {
  elapsed_ms?: number
  peak_rss_bytes?: number
  panel_scans?: number
  matrix_bytes?: number
  cache_hits?: number
  fold_reuses?: number
  serialized_result_bytes?: number
  phase_ms?: Record<string, number>
}

export interface MinuteKlineSession {
  date: string
  prev_close: number | null
  rows: MinuteKlineRow[]
}

export interface MonitorExtFieldItem {
  /** "configId.fieldName" */
  field: string
  /** 显示前N个标签, 0=不限制 */
  maxTags?: number
  /** 隐藏的位置 (0-based), 如 [0] 表示隐藏第一个 */
  hiddenIndices?: number[]
}

export interface PhaseSegment {
  phase: MarketPhase
  label: string
  start: string
  end: string
  days: number
  avg_height: number
  avg_first_board: number
  avg_ge2: number
  avg_promo: number | null
  avg_seal_rate: number
  top_mainlines: MainlineMemberStat[]
}

export interface PhaseSegments {
  segments: PhaseSegment[]
  total: number
}

export interface PluginDataSourceItem {
  name: string
  display_name: string
  datasets: string[]
  runtime: string          // node | python | none
  available: boolean       // 依赖是否已安装
  status: string           // 可用性原因 (供 UI 显示)
  description: string
  install_hint: string     // 未装依赖时显示的安装命令
  homepage?: string        // 插件官网/申请地址 (manifest 可选声明)
  api_key_env?: string     // 声明后设置页提供 Key 输入框 (先探后存)
  api_key_masked?: string  // 当前生效 Key 的脱敏串 (secrets.json 优先, .env 兜底; 与 TickFlow Key 同一展示契约)
}

export interface PluginKeyResult {
  ok: boolean
  reason?: string
  error?: string
  api_key_masked?: string
  plugin_available?: boolean
  plugin?: PluginDataSourceItem | null
}

export interface PriceLimitInfo {
  rate: number
  limit_up: number | null
  limit_down: number | null
  source: 'rule' | 'instrument'
}

export interface ResearchCandidate {
  id: string
  kind: ResearchCandidateKind
  name: string
  source_id: string
  config: Record<string, unknown>
  metrics: Record<string, number | string | boolean | null>
  data_as_of: string | null
  status: ResearchCandidateStatus
  created_at: string
  updated_at: string
}

export interface ResearchCandidateCreate {
  kind: ResearchCandidateKind
  name: string
  source_id: string
  config: Record<string, unknown>
  metrics: Record<string, number | string | boolean | null>
  data_as_of?: string | null
  status?: ResearchCandidateStatus
}

export interface ScreenerCachedResult {
  result: ScreenerResult | null
  today_ever_rows: Record<string, any> | null
  strategy_ids_by_symbol: Record<string, string[]>
  updated_at: number | null
}

export interface ScreenerCachedSummary {
  as_of: string | null
  results: Record<string, ScreenerResultSummary>
  today_ever_counts: Record<string, number>
  updated_at: number | null
}

export interface ScreenerResultSummary {
  total: number
  as_of: string
  computed_at?: number | null
}

export interface SectorMonitorTarget {
  key: string
  kind: SectorKind
  name: string
  symbol?: string
  source_id?: string
  field?: string
  source_field?: string
  value?: string
  level?: number | null
  available: boolean
  member_count: number
}

export interface StrategyBuildResult {
  code: string
  meta: Record<string, any>
  valid: boolean
  error: string | null
}

export interface StrategyCodeSaveResult {
  ok: boolean
  strategy_id: string
  source: 'ai' | 'custom' | 'composite'
  path: string
  meta: Record<string, any>
}

export interface StrategyLoadError {
  file: string
  error: string
}

export interface VDBasicFilter {
  price_min?: number | null                 // 股价下限 (元)
  price_max?: number | null                 // 股价上限 (元)
  market_cap_min?: number | null            // 总市值下限 (元)
  float_cap_min?: number | null             // 流通市值下限 (元)
  float_cap_max?: number | null             // 流通市值上限 (元)
  amount_min?: number | null                // 当日成交额下限 (元)
  exclude_st?: boolean                      // 剔除 ST
}

export interface WatchlistGroup {
  id: string
  name: string
  color: WatchlistGroupColor
}

export type WatchlistGroupColor =
  | 'sky'
  | 'blue'
  | 'indigo'
  | 'violet'
  | 'fuchsia'
  | 'rose'
  | 'orange'
  | 'amber'
  | 'lime'
  | 'emerald'
  | 'teal'
  | 'cyan'

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
  /** 支持的周期, 如 ['1d'] / ['1m'] (分钟策略) */
  timeframes?: string[]
}

export interface StrategyLoadError {
  file: string
  error: string
}

export interface ScreenerResult {
  as_of: string
  strategy: string | null
  rows: any[]
  total: number
  elapsed_ms: number
}

export interface ScreenerResultSummary {
  total: number
  as_of: string
  computed_at?: number | null
}

export interface ScreenerCachedSummary {
  as_of: string | null
  results: Record<string, ScreenerResultSummary>
  today_ever_counts: Record<string, number>
  updated_at: number | null
}

export interface ScreenerCachedResult {
  result: ScreenerResult | null
  today_ever_rows: Record<string, any> | null
  strategy_ids_by_symbol: Record<string, string[]>
  updated_at: number | null
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

export interface OverviewDimensionRankItem {
  name: string
  count: number
  avg_pct: number
  up_count: number
  down_count: number
  amount: number
  /** 该维度组首个命中的扩展字段 "configId.field" (成分股弹窗直连; 无扩展源时缺失) */
  source_field?: string | null
  leader?: {
    symbol?: string | null
    name?: string | null
    change_pct?: number | null
  } | null
}

export interface OverviewMarket {
  as_of: string | null
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
  limit: { limit_up: number; broken: number; failed: number; limit_down: number; max_boards: number; seal_rate?: number; tiers: { boards: number; count: number; stocks?: { symbol: string; name?: string; amount?: number }[] }[]; sealed_ready?: boolean; fake_up?: number; fake_down?: number }
  distribution: { label: string; count: number; pct: number }[]
  trend: { above_ma5: number; above_ma20: number; above_ma60: number; above_ma5_pct: number; above_ma20_pct: number; above_ma60_pct: number; new_high: number; new_low: number }
  activity: { avg_turnover: number; high_turnover: number; high_vol_ratio: number; vol_ratio: number }
  radar: { key: string; label: string; value: number }[]
  emotion: { score: number; label: string }
  top_gainers: MarketSnapshotRow[]
  top_losers: MarketSnapshotRow[]
  turnover_leaders: MarketSnapshotRow[]
  active_leaders: MarketSnapshotRow[]
  concept_rank: { leading: OverviewDimensionRankItem[]; lagging: OverviewDimensionRankItem[] }
  industry_rank: { leading: OverviewDimensionRankItem[]; lagging: OverviewDimensionRankItem[] }
}

// ===== 概念涨幅轮动矩阵 =====
// dates: 日期字符串列表(最新在最前);
