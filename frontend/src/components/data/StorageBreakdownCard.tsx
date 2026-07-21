import { Database, HardDrive } from 'lucide-react'
import type { StorageBreakdown } from '@/lib/api'

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
}: {
  storage: StorageBreakdown
  refreshedAt?: string | null
  isStale?: boolean
  headingLevel?: 2 | 3
}) {
  const Heading = headingLevel === 3 ? 'h3' : 'h2'
  const Container = headingLevel === 3 ? 'div' : 'section'
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

      <dl className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
        <div className="rounded-btn border border-border bg-base/40 p-3" data-testid="managed-storage">
          <dt className="text-[10px] text-muted">托管数据</dt>
          <dd className="mt-1 font-mono text-lg font-semibold tabular-nums">{formatCatalogBytes(storage.managed_data_bytes)}</dd>
        </div>
        <div className="rounded-btn border border-border bg-base/40 p-3" data-testid="operational-storage">
          <dt className="text-[10px] text-muted">运行数据</dt>
          <dd className="mt-1 font-mono text-lg font-semibold tabular-nums">{formatCatalogBytes(storage.operational_bytes)}</dd>
        </div>
        <div className="rounded-btn border border-border bg-elevated/50 p-3" data-testid="total-storage">
          <dt className="text-[10px] text-muted">后端报告总量</dt>
          <dd className="mt-1 font-mono text-lg font-semibold tabular-nums">{formatCatalogBytes(storage.total_bytes)}</dd>
        </div>
      </dl>

      <div className="mt-4 divide-y divide-border border-y border-border">
        {storage.categories.map((category) => (
          <div key={category.key} className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 py-2 text-xs">
            <span className="flex min-w-0 items-center gap-2 text-secondary">
              <Database aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{category.title}</span>
            </span>
            <span className="font-mono tabular-nums text-muted">{category.files.toLocaleString()} 文件</span>
            <span className="font-mono tabular-nums text-foreground">{formatCatalogBytes(category.bytes)}</span>
          </div>
        ))}
        {storage.categories.length === 0 && <p className="py-3 text-xs text-muted">暂无存储分类</p>}
      </div>
    </Container>
  )
}
