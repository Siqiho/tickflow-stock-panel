import { useMemo, useState } from 'react'
import { GitBranch } from 'lucide-react'
import type { DataControlSummary, SyncRun } from '@/lib/api'
import { AdvancedDisclosure } from './AdvancedDisclosure'

type EventKind = 'sync' | 'catalog' | 'source' | 'query'
type HistoryFilter = 'all' | EventKind

type HistoryEvent = {
  id: string
  kind: EventKind
  title: string
  summary: string
  timestamp: string | null
  status: 'ok' | 'warning' | 'failed'
  advanced: Array<[string, string]>
  subjectId?: string
  runId?: string
}

const FILTERS: Array<{ id: HistoryFilter; label: string }> = [
  { id: 'all', label: '全部' },
  { id: 'sync', label: '数据同步' },
  { id: 'catalog', label: '目录扫描' },
  { id: 'source', label: '数据源失败' },
  { id: 'query', label: '消费者查询' },
]

function runEvent(run: SyncRun): HistoryEvent {
  const catalog = run.operation === 'catalog_rescan' || run.operation.includes('catalog')
  const status = run.status === 'failed' ? 'failed' : run.status === 'degraded' ? 'warning' : 'ok'
  return {
    id: `run:${run.run_id}`,
    kind: catalog ? 'catalog' : 'sync',
    title: `${catalog ? '目录扫描' : '数据同步'} · ${run.dataset_id}`,
    summary: `${run.status === 'succeeded' ? '成功' : run.status === 'failed' ? '失败' : run.status === 'degraded' ? '降级' : '进行中'} · 发布 ${run.rows_published.toLocaleString()} 行`,
    timestamp: run.finished_at ?? run.started_at,
    status,
    subjectId: run.dataset_id,
    runId: run.run_id,
    advanced: [
      ['run_id', run.run_id],
      ['内部操作', run.operation],
      ['Provider', run.provider ?? '未记录'],
      ['开始', run.started_at ?? '未记录'],
      ['结束', run.finished_at ?? '未记录'],
      ['错误代码', run.error_code ?? '无'],
      ['错误详情', run.error_message ?? '无'],
    ],
  }
}

function buildEvents(runs: SyncRun[], control?: DataControlSummary): HistoryEvent[] {
  const events = runs.map(runEvent)
  for (const health of control?.source_health ?? []) {
    if (health.consecutive_failures === 0) continue
    events.push({
      id: `source:${health.provider}:${health.operation}`,
      kind: 'source',
      title: '数据源失败 · 数据同步',
      summary: `连续失败 ${health.consecutive_failures} 次${health.cooldown_until ? ' · 当前处于冷却期' : ''}`,
      timestamp: health.last_failure_at,
      status: 'failed',
      subjectId: health.operation.startsWith('sync:') ? health.operation.slice('sync:'.length) : undefined,
      advanced: [
        ['Provider', health.provider],
        ['内部操作', health.operation],
        ['错误代码', health.last_error_code ?? '未记录'],
        ['冷却到', health.cooldown_until ?? '未设置'],
        ['最近成功', health.last_success_at ?? '未记录'],
      ],
    })
  }
  for (const audit of control?.query_audits ?? []) {
    events.push({
      id: `query:${audit.audit_id}`,
      kind: 'query',
      title: `消费者查询 · ${audit.dataset_id}`,
      summary: `${audit.status === 'succeeded' ? '成功' : '失败'} · ${audit.row_count.toLocaleString()} 行`,
      timestamp: audit.created_at,
      status: audit.status === 'succeeded' ? 'ok' : 'failed',
      subjectId: audit.dataset_id,
      advanced: [
        ['audit_id', audit.audit_id],
        ['内部调用', audit.tool_name || '未登记'],
        ['耗时', audit.duration_ms === null ? '未记录' : `${audit.duration_ms} ms`],
        ['错误代码', audit.error_code ?? '无'],
      ],
    })
  }
  return events.sort((left, right) => (right.timestamp ?? '').localeCompare(left.timestamp ?? ''))
}

export function DataOperationsHistory({
  runs,
  control,
  onTraceSource,
}: {
  runs: SyncRun[]
  control?: DataControlSummary
  onTraceSource?: (subjectId: string, runId?: string) => void
}) {
  const [filter, setFilter] = useState<HistoryFilter>('all')
  const [visibleLimit, setVisibleLimit] = useState(20)
  const events = useMemo(() => buildEvents(runs, control), [control, runs])
  const filteredEvents = filter === 'all' ? events : events.filter((event) => event.kind === filter)
  const visible = filteredEvents.slice(0, visibleLimit)

  return (
    <section aria-labelledby="data-operations-history-heading" className="rounded-card border border-border bg-surface p-4">
      <div>
        <h3 id="data-operations-history-heading" className="text-sm font-medium text-foreground">运行与访问记录</h3>
        <p className="mt-1 text-[11px] text-muted">同步、目录扫描、源失败与消费者查询统一查看</p>
      </div>
      <div className="mt-3 flex gap-1 overflow-x-auto pb-1" aria-label="运行记录类型筛选">
        {FILTERS.map((item) => (
          <button
            key={item.id}
            type="button"
            aria-pressed={filter === item.id}
            onClick={() => {
              setFilter(item.id)
              setVisibleLimit(20)
            }}
            className={`shrink-0 rounded-btn px-2.5 py-1.5 text-xs font-medium outline-none focus-visible:ring-2 focus-visible:ring-accent ${
              filter === item.id ? 'bg-foreground text-base' : 'border border-border bg-elevated text-secondary hover:text-foreground'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="mt-3 divide-y divide-border border-y border-border">
        {visible.map((event) => (
          <article key={event.id} className="py-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h4 className="text-xs font-medium text-foreground">{event.title}</h4>
                <p className="mt-1 text-[11px] text-secondary">{event.summary}</p>
              </div>
              <div className="flex items-center gap-2">
                {event.subjectId && (
                  <button
                    type="button"
                    onClick={() => onTraceSource?.(event.subjectId!, event.runId)}
                    className="inline-flex items-center gap-1 rounded-btn border border-accent/20 bg-accent/5 px-2 py-1 text-[10px] font-medium text-accent hover:bg-accent/10"
                    aria-label={`诊断并追踪 ${event.title}`}
                  >
                    <GitBranch aria-hidden="true" className="h-3 w-3" />诊断并追踪
                  </button>
                )}
                <span className={`rounded-btn px-2 py-1 text-[10px] font-medium ${
                  event.status === 'failed' ? 'bg-danger/10 text-danger' : event.status === 'warning' ? 'bg-warning/10 text-warning' : 'bg-elevated text-secondary'
                }`}>{event.status === 'failed' ? '失败' : event.status === 'warning' ? '需关注' : '正常'}</span>
                <time className="font-mono text-[10px] text-muted">{event.timestamp ?? '时间未记录'}</time>
              </div>
            </div>
            <AdvancedDisclosure className="mt-2">
              <dl className="grid gap-2 rounded-btn bg-base/50 p-3 text-[10px] sm:grid-cols-2">
                {event.advanced.map(([label, value]) => (
                  <div key={label}>
                    <dt className="text-muted">{label}</dt>
                    <dd className={`mt-0.5 break-all font-mono ${label.includes('错误') && value !== '无' ? 'text-danger' : 'text-foreground'}`}>{value}</dd>
                  </div>
                ))}
              </dl>
            </AdvancedDisclosure>
          </article>
        ))}
        {visible.length === 0 && <p className="py-8 text-center text-xs text-muted">此类型暂无记录</p>}
      </div>
      {visible.length < filteredEvents.length && (
        <button
          type="button"
          onClick={() => setVisibleLimit((value) => value + 20)}
          className="mt-3 w-full rounded-btn border border-border bg-elevated px-3 py-2 text-xs font-medium text-secondary hover:text-foreground"
        >
          再显示 {Math.min(20, filteredEvents.length - visible.length)} 条
        </button>
      )}
    </section>
  )
}
