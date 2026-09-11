import { ArrowUpRight, GitBranch } from 'lucide-react'
import type { DatasetCatalogEntry, QualityStatus } from '@/lib/api'
import { AvailabilityBadge } from './AvailabilityBadge'
import {
  lifecycleText,
  materializationText,
  type DatasetControlFacts,
} from './ControlPlaneSummary'
import { CoverageBar } from './CoverageBar'
import { formatCatalogBytes } from './StorageBreakdownCard'

export const QUALITY_LABELS: Record<QualityStatus, string> = {
  healthy: '健康',
  degraded: '降级',
  failed: '失败',
  unknown: '未知',
}

export function catalogDisplayTitle(entry: DatasetCatalogEntry): string {
  return entry.descriptor.dataset_id === 'sealed_l1' ? '封板 L1' : entry.descriptor.title
}

function displayValue(value: string | null): string {
  return value ?? '未声明'
}

export function DatasetCatalogCard({
  entry,
  onOpen,
  control,
  controlStale = false,
  onTraceSource,
}: {
  entry: DatasetCatalogEntry
  onOpen?: (entry: DatasetCatalogEntry) => void
  control?: DatasetControlFacts
  controlStale?: boolean
  onTraceSource?: (subjectId: string) => void
}) {
  const { descriptor, state } = entry
  const title = catalogDisplayTitle(entry)
  const quality = QUALITY_LABELS[state.quality_status]

  return (
    <article className="flex min-w-0 flex-col rounded-card border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-medium text-foreground">{title}</h3>
          <p className="mt-1 truncate font-mono text-[10px] text-muted">
            {descriptor.asset_types.join(', ')} · {descriptor.grain}
          </p>
        </div>
        <span className={`rounded-btn px-2 py-1 text-[10px] font-medium ${
          state.quality_status === 'failed'
            ? 'bg-danger/10 text-danger'
            : state.quality_status === 'degraded'
              ? 'bg-warning/10 text-warning'
              : 'bg-elevated text-secondary'
        }`}>{quality}</span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-1.5">
        <AvailabilityBadge kind="provider_supported" value={descriptor.availability.provider_supported} />
        <AvailabilityBadge kind="entitled" value={descriptor.availability.entitled} />
        <AvailabilityBadge kind="local_materialized" value={descriptor.availability.local_materialized} />
        <AvailabilityBadge kind="serving_ready" value={descriptor.availability.serving_ready} />
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5 text-[10px]">
        {control?.policy ? (
          <span className="rounded-btn bg-accent/10 px-2 py-1 font-medium text-accent">
            {lifecycleText(control.policy, controlStale)}
          </span>
        ) : null}
        <span className="rounded-btn bg-elevated px-2 py-1 text-secondary">
          {materializationText(entry, controlStale)}
        </span>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 border-y border-border py-3 text-[10px]">
        <div><dt className="text-muted">行数</dt><dd className="mt-0.5 font-mono text-xs tabular-nums">{state.row_count.toLocaleString()}</dd></div>
        <div><dt className="text-muted">标的</dt><dd className="mt-0.5 font-mono text-xs tabular-nums">{state.symbol_count.toLocaleString()}</dd></div>
        <div><dt className="text-muted">最早</dt><dd className="mt-0.5 font-mono text-xs">{displayValue(state.earliest_time)}</dd></div>
        <div><dt className="text-muted">最新</dt><dd className="mt-0.5 font-mono text-xs">{displayValue(state.latest_time)}</dd></div>
        <div className="col-span-2"><dt className="text-muted">更新时间</dt><dd className="mt-0.5 break-all font-mono text-xs">{state.updated_at}</dd></div>
        <div className="col-span-2"><dt className="text-muted">本地大小</dt><dd className="mt-0.5 font-mono text-xs tabular-nums">{formatCatalogBytes(state.managed_bytes)}</dd></div>
      </dl>

      <div className="mt-3">
        <CoverageBar coverage={entry.coverage} />
      </div>

      <div className={`mt-4 grid gap-2 ${onTraceSource ? 'grid-cols-2' : 'grid-cols-1'}`}>
        <button
          type="button"
          onClick={() => onOpen?.(entry)}
          className="inline-flex items-center justify-center gap-1.5 rounded-btn border border-border bg-elevated/50 px-3 py-2 text-xs font-medium text-secondary outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
          aria-label={`查看 ${title} 详情`}
        >
          查看详情
          <ArrowUpRight aria-hidden="true" className="h-3.5 w-3.5" />
        </button>
        {onTraceSource && <button
          type="button"
          onClick={() => onTraceSource?.(descriptor.dataset_id)}
          className="inline-flex items-center justify-center gap-1.5 rounded-btn border border-accent/20 bg-accent/5 px-3 py-2 text-xs font-medium text-accent outline-none transition-colors hover:bg-accent/10 focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
          aria-label={`追踪 ${title} 来源`}
        >
          追踪来源
          <GitBranch aria-hidden="true" className="h-3.5 w-3.5" />
        </button>}
      </div>
    </article>
  )
}
