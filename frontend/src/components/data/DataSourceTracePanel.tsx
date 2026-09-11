import { useMemo, useState } from 'react'
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ExternalLink,
  GitBranch,
  Search,
  Server,
  Waypoints,
} from 'lucide-react'
import type {
  SourceProvenanceExplanation,
  SourceProvenanceGithubReference,
  SourceProvenanceRecord,
  SourceProvenanceResponse,
} from '@/lib/api'

type TraceFilter = 'all' | 'dataset' | 'extension' | 'attention'

const ROLE_LABELS: Record<string, string> = {
  host: '宿主基座',
  host_product_base: '宿主基座',
  endpoint_intelligence: '接口情报',
  endpoint_map: '接口情报',
  source_intelligence: '来源情报',
  field_semantics: '字段语义',
  local_fallback: '本地快照兜底',
  engineering_mechanism: '工程机制',
  protocol_reference: '协议参考',
  replacement_candidate: '替换候选',
  candidate: '替换候选',
  negative_evidence: '排除证据',
}

const LIFECYCLE_LABELS: Record<string, string> = {
  planned: '规划中',
  'source-verified': '来源已核验',
  source_verified: '来源已核验',
  isolated: '隔离验证',
  canary: '小范围试用',
  accepted: '已验收',
  production: '正式使用',
  blocked: '已阻塞',
  'no-go': '不准入',
  no_go: '不准入',
}

const FILTERS: Array<{ id: TraceFilter; label: string }> = [
  { id: 'all', label: '全部' },
  { id: 'dataset', label: '目录数据' },
  { id: 'extension', label: '扩展数据' },
  { id: 'attention', label: '需关注' },
]

// 「数据说明/提供内容」文案已迁移到后端 provenance_registry.SUBJECT_EXPLANATIONS,
// 由 /api/data/source-provenance 统一下发; 本地仅保留兜底, 防御旧后端或缺项。
function dataObjectExplanation(record: SourceProvenanceRecord): SourceProvenanceExplanation {
  if (record.explanation) return record.explanation
  return {
    category: record.subject_kind === 'extension' ? '扩展数据' : '目录数据',
    cadence: '结构以当前定义为准',
    description: `${record.title} 是数据台中已登记的${record.subject_kind === 'extension' ? '扩展数据对象' : '标准数据集'}。`,
    provides: '具体字段、粒度和时间范围以数据目录中的 Schema 与当前物理数据为准。',
  }
}

function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role.replaceAll('_', ' ')
}

function lifecycleLabel(value: string | null | undefined): string {
  if (!value) return '未使用控制库准入'
  return LIFECYCLE_LABELS[value] ?? value
}

function contributionList(value: string | string[]): string[] {
  return Array.isArray(value) ? value : value ? [value] : []
}

function githubSummary(reference: SourceProvenanceGithubReference): string {
  if (reference.runtime_dependency) return '当前运行时 Adapter'
  if (reference.roles.some((role) => ['local_fallback'].includes(role))) return '旧本地兜底对照；不是当前生产者'
  if (reference.roles.some((role) => ['host', 'host_product_base'].includes(role))) return '宿主与工程对照；运行时由本地代码持有'
  return 'Adapter 对照：说明这段代码当初对照谁写的，不是这块池子属于哪个仓库'
}

function attentionIssues(record: SourceProvenanceRecord) {
  return record.issues.filter((issue) => issue.severity === 'warning' || issue.severity === 'error')
}

function TraceStep({
  label,
  value,
  detail,
  warning = false,
  mono = false,
  breakAnywhere = false,
}: {
  label: string
  value: string
  detail?: string
  warning?: boolean
  mono?: boolean
  breakAnywhere?: boolean
}) {
  return (
    <li className="relative grid min-w-0 gap-1 overflow-hidden pb-5 pl-8 last:pb-0 before:absolute before:left-[0.55rem] before:top-4 before:h-[calc(100%-0.35rem)] before:w-px before:bg-border last:before:hidden">
      <span className={`absolute left-0 top-0.5 flex h-[1.15rem] w-[1.15rem] items-center justify-center rounded-full border ${
        warning ? 'border-warning/40 bg-warning/10 text-warning' : 'border-border bg-surface text-secondary'
      }`}>
        {warning ? <AlertTriangle aria-hidden="true" className="h-2.5 w-2.5" /> : <ArrowRight aria-hidden="true" className="h-2.5 w-2.5" />}
      </span>
      <span className="text-[10px] font-medium uppercase tracking-widest text-muted">{label}</span>
      <span className={`min-w-0 text-xs font-medium leading-relaxed text-foreground ${breakAnywhere ? 'break-all' : 'break-words'} ${mono ? 'font-mono text-[11px]' : ''}`}>{value}</span>
      {detail && <span className="break-all text-[10px] leading-relaxed text-secondary">{detail}</span>}
    </li>
  )
}

function GithubReferenceRow({ reference }: { reference: SourceProvenanceGithubReference }) {
  const contributions = contributionList(reference.contributions)
  return (
    <article className="py-4 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <a
            href={reference.repo_url}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex max-w-full items-center gap-1.5 break-all text-xs font-medium text-accent hover:underline"
          >
            {reference.name}
            <ExternalLink aria-hidden="true" className="h-3 w-3 shrink-0" />
          </a>
          <p className="mt-1 text-[10px] text-secondary">{githubSummary(reference)}</p>
        </div>
        <span className="rounded-btn bg-elevated px-2 py-1 text-[10px] text-secondary">
          {reference.evidence_level || '证据待补'}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {reference.roles.map((role) => (
          <span key={role} className="rounded-btn border border-border bg-base/60 px-2 py-1 text-[10px] text-secondary">
            {roleLabel(role)}
          </span>
        ))}
        <span className={`rounded-btn px-2 py-1 text-[10px] ${
          reference.runtime_dependency ? 'bg-warning/10 text-warning' : 'bg-accent/10 text-accent'
        }`}>
          {reference.runtime_dependency ? '运行时依赖' : '非运行时依赖'}
        </span>
      </div>

      {contributions.length > 0 && (
        <ul className="mt-3 space-y-1 text-[11px] leading-relaxed text-secondary">
          {contributions.map((contribution) => (
            <li key={contribution} className="flex gap-2">
              <span aria-hidden="true" className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-muted" />
              <span>{contribution}</span>
            </li>
          ))}
        </ul>
      )}

      <dl className="mt-3 grid gap-x-4 gap-y-1 text-[10px] sm:grid-cols-2">
        <div><dt className="text-muted">采用状态</dt><dd className="mt-0.5 font-mono text-secondary">{reference.adoption_status || '未登记'}</dd></div>
        <div><dt className="text-muted">审阅日期</dt><dd className="mt-0.5 font-mono text-secondary">{reference.reviewed_at || '待补'}</dd></div>
        <div className="sm:col-span-2">
          <dt className="text-muted">固定审阅点</dt>
          <dd className="mt-0.5 break-all font-mono text-secondary">
            {reference.commit_url ? (
              <a href={reference.commit_url} target="_blank" rel="noreferrer noopener" className="text-accent hover:underline">
                {reference.pinned_ref || reference.commit_url}
              </a>
            ) : reference.pinned_ref || '未固定；不能据此声称是最新版本'}
          </dd>
        </div>
      </dl>
    </article>
  )
}

function RecordDetail({ record, selectedRunId }: { record: SourceProvenanceRecord; selectedRunId?: string | null }) {
  const chain = record.local_chain
  const latestRun = chain.latest_run
  const issues = record.issues ?? []
  const explanation = dataObjectExplanation(record)
  const errorIssue = issues.find((issue) => issue.severity === 'error')
  const producerNames = record.true_producers.map((producer) => producer.name).join('、') || '真实生产者证据待补'
  const physicalPaths = chain.physical_paths.join('；') || '尚未发现物理产物'
  const adapterPaths = chain.adapter_paths.join('；') || 'Adapter 路径待登记'
  const alerts = attentionIssues(record)

  return (
    <div className="min-w-0">
      <div className="border-b border-border pb-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="font-mono text-[10px] text-muted">{record.subject_id}</p>
            <h3 className="mt-1 text-base font-semibold text-foreground">{record.title}</h3>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <span className="rounded-btn border border-border bg-base/60 px-2 py-1 text-[10px] text-secondary">{record.subject_kind === 'extension' ? '扩展数据' : '目录数据'}</span>
              <span className="rounded-btn border border-border bg-base/60 px-2 py-1 text-[10px] text-secondary">{explanation.category}</span>
              <span className="rounded-btn border border-border bg-base/60 px-2 py-1 text-[10px] text-secondary">{explanation.cadence}</span>
            </div>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <span className="rounded-btn bg-accent/10 px-2 py-1 text-[10px] font-medium text-accent">{lifecycleLabel(chain.lifecycle)}</span>
            <span className={`rounded-btn px-2 py-1 text-[10px] font-medium ${
              alerts.length > 0 ? 'bg-warning/10 text-warning' : 'bg-elevated text-secondary'
            }`}>{alerts.length > 0 ? `${alerts.length} 项需关注` : '证据链无告警'}</span>
          </div>
        </div>
        <dl className="mt-3 grid min-w-0 gap-x-4 gap-y-2 border-t border-border/70 pt-3 text-[11px] sm:grid-cols-[5rem_minmax(0,1fr)]">
          <dt className="text-muted">数据说明</dt>
          <dd className="max-w-[75ch] leading-relaxed text-foreground">{explanation.description}</dd>
          <dt className="text-muted">提供内容</dt>
          <dd className="max-w-[75ch] leading-relaxed text-secondary">{explanation.provides}</dd>
          <dt className="text-muted">当前状态</dt>
          <dd className="leading-relaxed text-secondary">{record.summary}</dd>
        </dl>
        {selectedRunId && (
          <p className="mt-3 rounded-btn border border-accent/20 bg-accent/5 px-3 py-2 text-[11px] text-secondary">
            当前由运行记录定位：<span className="break-all font-mono text-foreground">{selectedRunId}</span>
          </p>
        )}
      </div>

      <div className="grid min-w-0 gap-6 py-5 xl:grid-cols-[minmax(17rem,0.78fr)_minmax(0,1.5fr)] 2xl:grid-cols-[minmax(18rem,0.72fr)_minmax(30rem,1.45fr)_minmax(18rem,0.76fr)]">
        <section aria-labelledby="source-trace-chain-heading" className="min-w-0 xl:col-start-1 xl:row-start-1">
          <h4 id="source-trace-chain-heading" className="flex items-center gap-2 text-xs font-medium uppercase tracking-widest text-secondary">
            <Waypoints aria-hidden="true" className="h-3.5 w-3.5" />故障追踪链
          </h4>
          <ol className="mt-4">
            {errorIssue && <TraceStep label="当前异常" value={errorIssue.message} warning />}
            <TraceStep
              label="最近运行"
              value={latestRun ? `${latestRun.status} · ${latestRun.operation}` : '尚未记录匹配运行'}
              detail={latestRun ? `${latestRun.run_id}${latestRun.error_code ? ` · ${latestRun.error_code}` : ''}` : undefined}
              warning={latestRun?.status === 'failed'}
            />
            <TraceStep label="数据对象" value={record.title} detail={record.subject_id} />
            <TraceStep label="本地物理产物" value={physicalPaths} detail={chain.lineage_sources.length > 0 ? `lineage：${chain.lineage_sources.join('、')}` : '暂无匹配 lineage；不等于已验收或不可用'} warning={chain.materialized && chain.lineage_sources.length === 0} mono breakAnywhere />
            <TraceStep label="本地 Adapter / Module" value={adapterPaths} mono breakAnywhere />
            <TraceStep label="Provider" value={chain.providers.join('、') || '尚未登记'} />
            <TraceStep label="真实生产者" value={producerNames} detail="交易所、财经站点或服务。GitHub 仓库不是生产者，也不在这条故障链上" />
          </ol>
        </section>

        <div className="min-w-0 space-y-6 xl:col-start-2 xl:row-span-3 xl:row-start-1 2xl:col-start-2 2xl:row-span-2">
          <section aria-labelledby="real-producer-heading">
            <h4 id="real-producer-heading" className="flex items-center gap-2 text-xs font-medium uppercase tracking-widest text-secondary">
              <Server aria-hidden="true" className="h-3.5 w-3.5" />真实生产者与本地链路
            </h4>
            <div className="mt-3 divide-y divide-border rounded-btn border border-border px-3 text-[11px]">
              {record.true_producers.map((producer) => (
                <div key={producer.producer_id} className="grid gap-1 py-2.5 sm:grid-cols-[9rem_minmax(0,1fr)]">
                  <span className="min-w-0 font-medium text-foreground">{producer.name}</span>
                  <span className="min-w-0 break-words text-secondary">{producer.role}{producer.access ? ` · ${producer.access}` : ''}{producer.note ? ` · ${producer.note}` : ''}</span>
                </div>
              ))}
              {record.true_producers.length === 0 && <p className="py-3 text-muted">真实生产者证据尚未登记，页面不会用 GitHub 项目代替。</p>}
              <div className="grid gap-1 py-2.5 sm:grid-cols-[9rem_minmax(0,1fr)]"><span className="text-muted">物理位置</span><span className="break-all font-mono text-foreground">{physicalPaths}</span></div>
              <div className="grid gap-1 py-2.5 sm:grid-cols-[9rem_minmax(0,1fr)]"><span className="text-muted">服务状态</span><span className="text-foreground">{chain.serving_ready ? '当前可服务' : chain.materialized ? '已落库，尚未正式可用' : '尚未落库'}</span></div>
              <div className="grid gap-1 py-2.5 sm:grid-cols-[9rem_minmax(0,1fr)]"><span className="text-muted">已同步到</span><span className="font-mono text-foreground">{chain.checkpoint_watermark || chain.latest_time || '尚未记录'}</span></div>
            </div>
          </section>

          <section aria-labelledby="adapter-reference-heading">
            <div className="flex items-start gap-2">
              <GitBranch aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 text-secondary" />
              <div>
                <h4 id="adapter-reference-heading" className="text-xs font-medium uppercase tracking-widest text-secondary">Adapter 对照（GitHub）</h4>
                <p className="mt-1 text-[10px] leading-relaxed text-muted">说明这段 Adapter 当初对照谁写的。不是数据集父母，也不表示这块池子属于该仓库。</p>
              </div>
            </div>
            <div className="mt-3 divide-y divide-border rounded-btn border border-border p-3">
              {record.github_references.map((reference) => <GithubReferenceRow key={`${reference.project_id}:${reference.roles.join(':')}`} reference={reference} />)}
              {record.github_references.length === 0 && <p className="py-2 text-xs text-muted">尚未登记 Adapter 对照项目。这不是数据缺失，页面不会用 GitHub 代替真实生产者。</p>}
            </div>
          </section>
        </div>

        {record.replacement_candidates.length > 0 && (
          <section aria-labelledby="replacement-candidates-heading" className="min-w-0 xl:col-start-1 xl:row-start-2 2xl:col-start-3 2xl:row-start-1">
            <h4 id="replacement-candidates-heading" className="text-xs font-medium uppercase tracking-widest text-secondary">同类替换候选</h4>
            <p className="mt-1 text-[10px] leading-relaxed text-muted">用于后续比较和替换评估，不代表已经接入当前数据链。</p>
            <div className="mt-3 divide-y divide-border rounded-btn border border-border px-3 text-[11px]">
              {record.replacement_candidates.map((candidate) => (
                <div key={candidate.project_id} className="min-w-0 py-2.5">
                  <a href={candidate.repo_url} target="_blank" rel="noreferrer noopener" className="break-all font-medium text-accent hover:underline">{candidate.name}</a>
                  <p className="mt-1 break-words leading-relaxed text-secondary">{candidate.reason || contributionList(candidate.contributions).join('；') || '候选理由待补'}</p>
                  <p className="mt-1 break-all font-mono text-[10px] text-muted">{candidate.status || candidate.adoption_status}</p>
                </div>
              ))}
            </div>
          </section>
        )}

        {issues.length > 0 && (
          <section aria-labelledby="source-evidence-issues-heading" className={`min-w-0 xl:col-start-1 ${record.replacement_candidates.length > 0 ? 'xl:row-start-3' : 'xl:row-start-2'} 2xl:col-start-1 2xl:row-start-2`}>
            <h4 id="source-evidence-issues-heading" className="text-xs font-medium uppercase tracking-widest text-secondary">证据缺口与本地问题</h4>
            <p className="mt-1 text-[10px] leading-relaxed text-muted">先确认当前证据和本地故障，再判断是否需要更换来源。</p>
            <div className="mt-3 divide-y divide-border rounded-btn border border-border px-3 text-[11px]">
              {issues.map((issue) => (
                <div key={`${issue.code}:${issue.message}`} className="flex min-w-0 gap-2 py-2.5">
                  {issue.severity === 'error'
                    ? <AlertTriangle aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-danger" />
                    : issue.severity === 'warning'
                      ? <AlertTriangle aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
                      : <CheckCircle2 aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-secondary" />}
                  <div className="min-w-0"><p className="break-words leading-relaxed text-foreground">{issue.message}</p><p className="mt-0.5 break-all font-mono text-[10px] text-muted">{issue.code}</p></div>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  )
}

export function DataSourceTracePanel({
  data,
  error,
  selectedId,
  selectedRunId,
  onSelect,
}: {
  data?: SourceProvenanceResponse
  error?: Error | null
  selectedId?: string | null
  selectedRunId?: string | null
  onSelect: (subjectId: string) => void
}) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<TraceFilter>('all')
  const records = data?.records ?? []
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    return records.filter((record) => {
      if (filter === 'dataset' && record.subject_kind !== 'dataset') return false
      if (filter === 'extension' && record.subject_kind !== 'extension') return false
      if (filter === 'attention' && attentionIssues(record).length === 0) return false
      if (!normalized) return true
      return [
        record.subject_id,
        record.title,
        record.summary,
        ...record.true_producers.map((producer) => producer.name),
        ...record.github_references.map((reference) => reference.name),
      ].some((value) => value.toLowerCase().includes(normalized))
    })
  }, [filter, query, records])
  const selected = records.find((record) => record.subject_id === selectedId) ?? filtered[0] ?? records[0]

  return (
    <section aria-labelledby="source-provenance-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="source-provenance-heading" tabIndex={-1} className="flex items-center gap-2 text-base font-semibold text-foreground outline-none focus-visible:ring-2 focus-visible:ring-accent">
            <GitBranch aria-hidden="true" className="h-4 w-4 text-secondary" />来源追踪
          </h2>
          <p className="mt-1 text-xs text-muted">从本地故障追到真实生产者。GitHub 只说明 Adapter 对照，不当数据集父母。</p>
        </div>
        {data && (
          <div className="text-right text-[10px] text-muted">
            <p>{data.records.length} 个可追踪对象 · {data.missing_reference_count} 个映射待补</p>
            <p className="mt-1 font-mono">证据聚合 {data.generated_at}</p>
          </div>
        )}
      </div>

      <div className="mt-4 rounded-btn border border-accent/20 bg-accent/5 px-3 py-2 text-[11px] leading-relaxed text-secondary">
        <strong className="font-medium text-foreground">披露原则：</strong>真实生产者是 TickFlow、东财、腾讯/新浪等。GitHub 只解释这段 Adapter 当初对照谁写的，不能解释这块池子属于哪个仓库。
      </div>

      {data?.catalog_stale && (
        <div role="status" className="mt-3 flex items-center gap-2 rounded-btn border border-warning/30 bg-warning/5 px-3 py-2 text-xs text-warning">
          <AlertTriangle aria-hidden="true" className="h-3.5 w-3.5" />Catalog 状态可能过期；来源链仍显示，但不能把旧快照当作当前验收结论。
        </div>
      )}

      {error ? (
        <div role="alert" className="mt-4 rounded-card border border-danger/30 bg-danger/5 p-4 text-sm text-danger">来源追踪暂不可用：{error.message}</div>
      ) : !data ? (
        <div aria-busy="true" className="mt-4 rounded-card border border-border bg-surface p-5 text-sm text-muted">正在聚合本地来源证据</div>
      ) : records.length === 0 ? (
        <div className="mt-4 rounded-card border border-dashed border-border p-8 text-center text-sm text-muted">尚无可追踪对象</div>
      ) : (
        <div className="mt-4 grid min-h-[38rem] overflow-hidden rounded-card border border-border bg-surface lg:grid-cols-[18rem_minmax(0,1fr)] 2xl:grid-cols-[19rem_minmax(0,1fr)]">
          <aside className="min-w-0 overflow-x-hidden border-b border-border bg-base/30 p-3 lg:border-b-0 lg:border-r" aria-label="来源对象索引">
            <label className="relative block">
              <Search aria-hidden="true" className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
              <span className="sr-only">搜索来源对象</span>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="数据集、生产者或项目"
                className="h-8 w-full rounded-btn border border-border bg-surface pl-8 pr-2 text-xs text-foreground outline-none placeholder:text-muted focus:border-accent focus:ring-1 focus:ring-accent"
              />
            </label>
            <div className="mt-2 flex gap-1 overflow-x-auto pb-1" aria-label="来源对象筛选">
              {FILTERS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  aria-pressed={filter === item.id}
                  onClick={() => setFilter(item.id)}
                  className={`shrink-0 rounded-btn px-2 py-1 text-[10px] font-medium ${filter === item.id ? 'bg-foreground text-base' : 'border border-border bg-surface text-secondary'}`}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <div className="mt-3 max-h-[31rem] divide-y divide-border overflow-y-auto border-y border-border lg:max-h-[64rem]">
              {filtered.map((record) => {
                const active = selected?.subject_id === record.subject_id
                return (
                  <button
                    key={record.subject_id}
                    type="button"
                    aria-current={active ? 'true' : undefined}
                    onClick={() => onSelect(record.subject_id)}
                    className={`w-full px-2 py-2.5 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent ${active ? 'bg-accent/10' : 'hover:bg-elevated/60'}`}
                  >
                    <span className="flex items-start justify-between gap-2">
                      <span className="min-w-0">
                        <span className="block line-clamp-2 break-words text-xs font-medium leading-snug text-foreground">{record.title}</span>
                        <span className="mt-0.5 block truncate font-mono text-[10px] text-muted">{record.subject_id}</span>
                      </span>
                      {attentionIssues(record).length > 0 && <span className="shrink-0 rounded bg-warning/10 px-1.5 py-0.5 font-mono text-[9px] text-warning">{attentionIssues(record).length}</span>}
                    </span>
                    <span className="mt-1.5 block line-clamp-2 break-words text-[10px] leading-relaxed text-secondary">
                      {record.true_producers.map((producer) => producer.name).join(' / ') || '生产者待补'}
                    </span>
                  </button>
                )
              })}
              {filtered.length === 0 && <p className="px-2 py-8 text-center text-xs text-muted">没有匹配对象</p>}
            </div>
          </aside>
          <main className="min-w-0 overflow-hidden p-4 sm:p-5 xl:p-6">
            {selected && <RecordDetail record={selected} selectedRunId={selectedRunId} />}
          </main>
        </div>
      )}
    </section>
  )
}
