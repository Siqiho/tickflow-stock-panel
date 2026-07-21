import { GitBranch } from 'lucide-react'
import { useId } from 'react'
import type { DatasetCatalogEntry } from '@/lib/api'
import { QUALITY_LABELS } from './DatasetCatalogCard'

function valueOrUnknown(value: string | number | null): string {
  return value == null ? '未声明' : typeof value === 'number' ? value.toLocaleString() : value
}

export function QualityLineagePanel({ entry }: { entry: DatasetCatalogEntry }) {
  const reasonCode = entry.descriptor.availability.reason_code
  const headingId = useId()

  return (
    <section aria-labelledby={headingId}>
      <h3 id={headingId} className="flex items-center gap-2 text-xs font-medium uppercase tracking-widest text-secondary">
        <GitBranch aria-hidden="true" className="h-3.5 w-3.5" />
        质量与血缘
      </h3>
      <dl className="mt-3 grid grid-cols-1 gap-2 text-xs sm:grid-cols-3">
        <div><dt className="text-muted">质量</dt><dd className="mt-0.5 font-medium">{QUALITY_LABELS[entry.state.quality_status]}</dd></div>
        <div><dt className="text-muted">Provider</dt><dd className="mt-0.5 break-all font-mono">{valueOrUnknown(entry.provider)}</dd></div>
        <div><dt className="text-muted">原因代码</dt><dd className="mt-0.5 break-all font-mono">{valueOrUnknown(reasonCode)}</dd></div>
      </dl>

      <div className="mt-3 space-y-2">
        {entry.lineage.map((item, index) => (
          <article key={`${item.run_id ?? 'lineage'}-${index}`} className="rounded-btn border border-border bg-base/40 p-3">
            <dl className="grid grid-cols-1 gap-x-4 gap-y-2 text-[11px] sm:grid-cols-2">
              <div><dt className="text-muted">来源</dt><dd className="mt-0.5 break-all font-mono">{item.source}</dd></div>
              <div><dt className="text-muted">Run</dt><dd className="mt-0.5 break-all font-mono">{valueOrUnknown(item.run_id)}</dd></div>
              <div><dt className="text-muted">获取时间</dt><dd className="mt-0.5 break-all font-mono">{valueOrUnknown(item.fetched_at)}</dd></div>
              <div><dt className="text-muted">单位版本</dt><dd className="mt-0.5 break-all font-mono">{item.unit_version}</dd></div>
              <div><dt className="text-muted">质量</dt><dd className="mt-0.5">{QUALITY_LABELS[item.quality_status]}</dd></div>
              <div><dt className="text-muted">范围</dt><dd className="mt-0.5 break-all font-mono">{valueOrUnknown(item.scope)}</dd></div>
              <div className="sm:col-span-2"><dt className="text-muted">产物</dt><dd className="mt-0.5 break-all font-mono">{valueOrUnknown(item.artifact_path)}</dd></div>
              <div><dt className="text-muted">行数</dt><dd className="mt-0.5 font-mono tabular-nums">{valueOrUnknown(item.row_count)}</dd></div>
            </dl>
          </article>
        ))}
        {entry.lineage.length === 0 && <p className="rounded-btn border border-dashed border-border p-3 text-xs text-muted">暂无血缘记录</p>}
      </div>
    </section>
  )
}
