import type {
  CapabilityMatrix,
  CapabilityRoute,
  CatalogResponse,
  DataControlSummary,
  DataSourcesResponse,
  DatasetCatalogEntry,
} from './api'

export const DATA_SOURCES_SETTINGS_HREF = '/data?section=sources'
export const DATA_KEYS_SETTINGS_HREF = '/settings?tab=account'
export const EXTERNAL_READONLY_SOURCES_QK = ['external-readonly-sources'] as const
export const MARGIN_TRADING_QUERY_LIMIT = 20

export const CAPABILITY_LOCAL_DATASETS: Record<string, string[]> = {
  daily: ['stock_daily'],
  adj_factor: ['stock_adj_factor'],
  realtime: ['quote_snapshot'],
  minute: ['stock_minute'],
  depth5: ['depth5'],
  financial: ['financial_metrics'],
}

export function findDataSource(
  sources: DataSourcesResponse | undefined,
  name: string | undefined,
) {
  if (!sources || !name) return undefined
  return sources.builtin.find(source => source.name === name)
    ?? sources.plugins.find(source => source.name === name)
    ?? sources.custom.find(source => source.name === name)
}

const PUBLIC_FINANCIAL_ALIASES = new Set(['public', 'eastmoney', 'em', 'free'])
const PUBLIC_ADJ_ALIASES = new Set(['public', 'sina', 'sina_qfq', 'free'])

export function isPublicFinancialProvider(name: string | undefined): boolean {
  return PUBLIC_FINANCIAL_ALIASES.has((name || '').trim().toLowerCase())
}

export function isPublicAdjFactorProvider(name: string | undefined): boolean {
  return PUBLIC_ADJ_ALIASES.has((name || '').trim().toLowerCase())
}

export function displaySourceName(name: string | undefined): string {
  if (!name) return '未配置'
  if (name === 'tickflow') return 'TickFlow'
  if (name === 'public' || name === 'local_public') return '公开源'
  if (name === 'same_as_daily') return '跟随日K'
  return name
}

export type CatalogReadState = 'loading' | 'error' | 'ready'

export function catalogLocalDataLabel(
  catalog: CatalogResponse | undefined,
  datasetIds: string[] | undefined,
  catalogState: CatalogReadState,
): string {
  if (catalogState === 'loading') return '正在读取'
  if (catalogState === 'error') return '目录暂不可用'
  if (!datasetIds || datasetIds.length === 0) return '目录无独立数据集'
  const entries = catalog?.datasets ?? []
  const matched = datasetIds
    .map((id) => entries.find((entry) => entry.descriptor.dataset_id === id))
    .filter((entry): entry is DatasetCatalogEntry => Boolean(entry))
  if (matched.length === 0) return '目录无记录'
  const hasLocal = matched.some((entry) => {
    if (entry.descriptor.availability.local_materialized) return true
    return (entry.state.row_count ?? 0) > 0
  })
  return hasLocal ? '本地已有' : '尚未落库'
}

export function collectionHealthLabel(summary?: DataControlSummary | null): {
  text: string
  warning: boolean
  unverified: boolean
} {
  if (!summary) {
    return { text: '正在读取', warning: false, unverified: false }
  }
  const rows = summary.source_health
  if (rows.length === 0) {
    return { text: '采集健康未核验（控制库无采集记录）', warning: false, unverified: true }
  }
  const withSuccess = rows.filter((row) => Boolean(row.last_success_at))
  const withFail = rows.filter((row) => row.consecutive_failures > 0)
  if (withSuccess.length === 0) {
    return { text: '采集健康未核验（无近期成功采集记录）', warning: withFail.length > 0, unverified: true }
  }
  return {
    text: `控制库采集记录：${withSuccess.length} 条有成功时间 · ${withFail.length} 条连续失败（不是在线探测）`,
    warning: withFail.length > 0,
    unverified: false,
  }
}

export type CapabilityStatusRow = {
  id: string
  label: string
  configuredSource: string
  ready: boolean
  readyLabel: string
  localDataLabel: string
}

export function capabilityStatusRows(
  matrix: CapabilityMatrix | undefined,
  catalog: CatalogResponse | undefined,
  catalogState: CatalogReadState,
): CapabilityStatusRow[] {
  return (matrix?.capabilities ?? []).map((cap: CapabilityRoute) => ({
    id: cap.id,
    label: cap.label,
    configuredSource: cap.current === cap.effective
      ? cap.current_display
      : `${cap.current_display}（生效 ${cap.effective_display}）`,
    ready: cap.usable,
    readyLabel: cap.usable ? '配置已就绪' : '配置未就绪',
    localDataLabel: catalogLocalDataLabel(catalog, CAPABILITY_LOCAL_DATASETS[cap.id], catalogState),
  }))
}

export type MarginQueryErrorKind =
  | 'unconfigured'
  | 'not_found'
  | 'empty'
  | 'invalid_schema'
  | 'unreadable'
  | 'invalid_request'
  | 'read_error'

export function classifyMarginQueryError(error: unknown): MarginQueryErrorKind {
  const text = error instanceof Error ? error.message : String(error ?? '')
  const lower = text.toLowerCase()
  if (lower.includes('unconfigured') || lower.includes('not configured')) return 'unconfigured'
  if (lower.includes('not found')) return 'not_found'
  if (lower.includes('missing columns') || lower.includes('invalid_schema') || lower.includes('missing trade date')) {
    return 'invalid_schema'
  }
  if (lower.includes('unreadable')) return 'unreadable'
  if (lower.includes('invalid a-share') || lower.includes('invalid_request')) return 'invalid_request'
  return 'read_error'
}

export function marginQueryErrorLabel(kind: MarginQueryErrorKind): string {
  switch (kind) {
    case 'unconfigured':
      return '原包未配置，未查询'
    case 'not_found':
      return '没有该标的的两融文件'
    case 'empty':
      return '文件可读，但当前条件没有记录'
    case 'invalid_schema':
      return '两融文件字段不完整'
    case 'unreadable':
      return '两融文件无法读取'
    case 'invalid_request':
      return '股票代码无效'
    default:
      return '读取失败'
  }
}

export function formatMissingValue(value: unknown): string {
  if (value == null || value === '') return '—'
  return String(value)
}
