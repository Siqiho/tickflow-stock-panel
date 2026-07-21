import { History } from 'lucide-react'
import { useId } from 'react'
import type { SyncRun } from '@/lib/api'
import { QUALITY_LABELS } from './DatasetCatalogCard'

const RUN_STATUS_LABELS: Record<SyncRun['status'], string> = {
  pending: '等待中',
  running: '运行中',
  succeeded: '成功',
  degraded: '降级',
  failed: '失败',
}

function timeOrUnknown(value: string | null): string {
  return value ?? '未声明'
}

export function DatasetRunHistory({ runs }: { runs: SyncRun[] }) {
  const headingId = useId()

  return (
    <section aria-labelledby={headingId}>
      <h3 id={headingId} className="flex items-center gap-2 text-xs font-medium uppercase tracking-widest text-secondary">
        <History aria-hidden="true" className="h-3.5 w-3.5" />
        最近运行
      </h3>
      <div className="mt-3 space-y-2">
        {runs.map((run) => (
          <article key={run.run_id} className="rounded-btn border border-border bg-base/40 p-3 text-[11px]">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="font-mono text-xs font-medium text-foreground">{run.run_id}</p>
                <p className="mt-0.5 text-muted">{run.operation}</p>
              </div>
              <span className={`rounded-btn px-2 py-1 font-medium ${
                run.status === 'failed' ? 'bg-danger/10 text-danger' : run.status === 'degraded' ? 'bg-warning/10 text-warning' : 'bg-elevated text-secondary'
              }`}>{RUN_STATUS_LABELS[run.status]}</span>
            </div>
            <dl className="mt-3 grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
              <div><dt className="text-muted">开始</dt><dd className="mt-0.5 break-all font-mono">{timeOrUnknown(run.started_at)}</dd></div>
              <div><dt className="text-muted">结束</dt><dd className="mt-0.5 break-all font-mono">{timeOrUnknown(run.finished_at)}</dd></div>
              <div><dt className="text-muted">获取 / 发布</dt><dd className="mt-0.5 font-mono tabular-nums">{run.rows_fetched.toLocaleString()} / {run.rows_published.toLocaleString()}</dd></div>
              <div><dt className="text-muted">质量</dt><dd className="mt-0.5">{QUALITY_LABELS[run.quality_status]}</dd></div>
              {run.provider && <div><dt className="text-muted">Provider</dt><dd className="mt-0.5 break-all font-mono">{run.provider}</dd></div>}
              {run.error_code && <div><dt className="text-muted">错误代码</dt><dd className="mt-0.5 break-all font-mono text-danger">{run.error_code}</dd></div>}
            </dl>
            {run.error_message && (
              <p className="mt-3 line-clamp-2 break-words rounded-btn bg-danger/5 px-2 py-1.5 text-danger" title={run.error_message}>
                {run.error_message}
              </p>
            )}
          </article>
        ))}
        {runs.length === 0 && <p className="rounded-btn border border-dashed border-border p-3 text-xs text-muted">暂无运行记录</p>}
      </div>
    </section>
  )
}
