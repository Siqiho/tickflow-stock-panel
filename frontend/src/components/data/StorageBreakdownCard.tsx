import { Database, FolderSearch, GitBranch, HardDrive } from 'lucide-react'
import type { StorageBreakdown } from '@/lib/api'

export const STORAGE_CATEGORY_LABELS: Record<string, string> = {
  stocks: '股票',
  etfs: 'ETF',
  indices: '指数',
  quote_snapshot: '行情快照',
  sealed_l1: '封板 L1',
  depth5: '五档盘口',
  pools: '股票池',
  financials: '财务',
  f10: '股票 F10',
  ext_data: '扩展数据',
  reference: '参考数据',
  lineage: '血缘',
  job_store: '任务库',
  logs: '日志',
  user_data: '用户数据',
  control: '控制库',
  operational_other: '其他运行文件',
}

type StorageNav =
  | { kind: 'trace'; subjectId: string }
  | { kind: 'catalog'; group: string }

export const STORAGE_CATEGORY_NAV: Record<string, StorageNav> = {
  stocks: { kind: 'trace', subjectId: 'stock_daily' },
  etfs: { kind: 'catalog', group: 'etf' },
  indices: { kind: 'trace', subjectId: 'index_daily' },
  quote_snapshot: { kind: 'trace', subjectId: 'quote_snapshot' },
  sealed_l1: { kind: 'trace', subjectId: 'sealed_l1' },
  depth5: { kind: 'trace', subjectId: 'depth5' },
  pools: { kind: 'trace', subjectId: 'pools' },
  financials: { kind: 'catalog', group: 'finance' },
  f10: { kind: 'trace', subjectId: 'stock_margin_trading' },
  ext_data: { kind: 'catalog', group: 'ext' },
  reference: { kind: 'catalog', group: 'reference' },
}

export function storageCategoryTitle(key: string, fallback: string): string {
  return STORAGE_CATEGORY_LABELS[key] ?? fallback
}

export function formatCatalogBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  if (bytes < 1024) return `${Math.round(bytes)} B`

  const units = ['KiB', 'MiB', 'GiB', 'TiB']
  let value = bytes / 1024
  let unit = units[0]
  for (let index = 1; index < units.length && value >= 1024; index += 1) {
    value /= 1024
    unit = units[index]
  }
  const precision = value >= 100 ? 0 : 1
  return `${value.toFixed(precision).replace(/\.0$/, '')} ${unit}`
}

export function StorageBreakdownCard({
  storage,
  refreshedAt,
  isStale = false,
  headingLevel = 2,
  managedOnly = false,
  onTraceSource,
  onOpenCatalogGroup,
}: {
  storage: StorageBreakdown
  refreshedAt?: string | null
  isStale?: boolean
  headingLevel?: 2 | 3
  managedOnly?: boolean
  onTraceSource?: (subjectId: string) => void
  onOpenCatalogGroup?: (group: string) => void
}) {
  const Heading = headingLevel === 3 ? 'h3' : 'h2'
  const Container = headingLevel === 3 ? 'div' : 'section'
  const visibleCategories = managedOnly
    ? storage.categories.filter(category => category.kind === 'managed')
    : storage.categories
  return (
    <Container className="rounded-card border border-border bg-surface p-4" aria-labelledby="storage-breakdown-heading">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <Heading id="storage-breakdown-heading" className="flex items-center gap-2 text-sm font-medium text-foreground">
            <HardDrive aria-hidden="true" className="h-4 w-4 text-secondary" />
            本地存储
          </Heading>
          {refreshedAt && <p className="mt-1 text-[10px] text-muted">刷新时间 <span className="font-mono">{refreshedAt}</span></p>}
        </div>
        {isStale && <span className="rounded-btn bg-warning/10 px-2 py-1 text-[10px] font-medium text-warning">状态可能过期</span>}
      </div>

      <dl className={`mt-4 grid grid-cols-1 gap-2 ${managedOnly ? '' : 'sm:grid-cols-3'}`}>
        <div className="rounded-btn border border-border bg-base/40 p-3" data-testid="managed-storage">
          <dt className="text-[10px] text-muted">{managedOnly ? '共享市场数据' : '托管数据'}</dt>
          <dd className="mt-1 font-mono text-lg font-semibold tabular-nums">{formatCatalogBytes(storage.managed_data_bytes)}</dd>
        </div>
        {!managedOnly && <div className="rounded-btn border border-border bg-base/40 p-3" data-testid="operational-storage">
          <dt className="text-[10px] text-muted">运行数据</dt>
          <dd className="mt-1 font-mono text-lg font-semibold tabular-nums">{formatCatalogBytes(storage.operational_bytes)}</dd>
        </div>}
        {!managedOnly && <div className="rounded-btn border border-border bg-elevated/50 p-3" data-testid="total-storage">
          <dt className="text-[10px] text-muted">后端报告总量</dt>
          <dd className="mt-1 font-mono text-lg font-semibold tabular-nums">{formatCatalogBytes(storage.total_bytes)}</dd>
        </div>}
      </dl>

      <div className="mt-4 divide-y divide-border border-y border-border">
        {visibleCategories.map((category) => {
          const title = storageCategoryTitle(category.key, category.title)
          const nav = STORAGE_CATEGORY_NAV[category.key]
          return (
          <div key={category.key} className="grid grid-cols-[minmax(0,1fr)_auto_auto_auto] items-center gap-3 py-2 text-xs">
            <span className="flex min-w-0 items-center gap-2 text-secondary">
              <Database aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{title}</span>
            </span>
            <span className="font-mono tabular-nums text-muted">{category.files.toLocaleString()} 文件</span>
            <span className="font-mono tabular-nums text-foreground">{formatCatalogBytes(category.bytes)}</span>
            {nav?.kind === 'trace' && onTraceSource ? (
              <button
                type="button"
                onClick={() => onTraceSource(nav.subjectId)}
                aria-label={`追踪 ${title} 来源`}
                className="inline-flex items-center gap-1 rounded-btn px-1.5 py-1 text-[10px] font-medium text-accent hover:bg-accent/10"
              >
                <GitBranch aria-hidden="true" className="h-3 w-3" />
                来源
              </button>
            ) : nav?.kind === 'catalog' && onOpenCatalogGroup ? (
              <button
                type="button"
                onClick={() => onOpenCatalogGroup(nav.group)}
                aria-label={`打开 ${title} 目录`}
                className="inline-flex items-center gap-1 rounded-btn px-1.5 py-1 text-[10px] font-medium text-accent hover:bg-accent/10"
              >
                <FolderSearch aria-hidden="true" className="h-3 w-3" />
                目录
              </button>
            ) : <span aria-hidden="true" />}
          </div>
          )
        })}
        {visibleCategories.length === 0 && <p className="py-3 text-xs text-muted">暂无存储分类</p>}
      </div>
    </Container>
  )
}
