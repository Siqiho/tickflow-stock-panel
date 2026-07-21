/**
 * 运行日志面板 — 数据台后端 + 用户台前端统一事件流。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity,
  Eraser,
  Filter,
  Pause,
  Play,
  RefreshCw,
  ScrollText,
  Search,
} from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { api, type RuntimeLogItem } from '@/lib/api'
import { cn } from '@/lib/cn'
import { toast } from '@/components/Toast'
import { getRuntimeSessionId, logUiInfo } from '@/lib/runtimeLogger'

const SOURCE_OPTS = [
  { value: '', label: '全部来源' },
  { value: 'ui', label: '用户台 UI' },
  { value: 'backend', label: '数据台后端' },
  { value: 'access', label: 'HTTP 访问' },
] as const

const LEVEL_OPTS = [
  { value: '', label: '全部级别' },
  { value: 'DEBUG', label: 'DEBUG+' },
  { value: 'INFO', label: 'INFO+' },
  { value: 'WARNING', label: 'WARNING+' },
  { value: 'ERROR', label: 'ERROR+' },
] as const

const CATEGORY_OPTS = [
  { value: '', label: '全部分类' },
  { value: 'navigation', label: '页面导航' },
  { value: 'api', label: 'API 调用' },
  { value: 'access', label: 'HTTP' },
  { value: 'data', label: '数据' },
  { value: 'strategy', label: '策略' },
  { value: 'ai', label: 'AI' },
  { value: 'ui', label: '界面' },
  { value: 'lifecycle', label: '生命周期' },
  { value: 'system', label: '系统' },
  { value: 'server', label: '服务' },
] as const

function levelClass(level: string) {
  const l = (level || '').toUpperCase()
  if (l === 'ERROR' || l === 'CRITICAL') return 'text-bear'
  if (l === 'WARNING' || l === 'WARN') return 'text-amber-400'
  if (l === 'DEBUG') return 'text-muted'
  return 'text-accent'
}

function sourceBadge(source: string) {
  const s = (source || '').toLowerCase()
  if (s === 'ui') return 'bg-violet-500/15 text-violet-700 dark:text-violet-300 border-violet-500/30'
  if (s === 'access') return 'bg-sky-500/15 text-sky-700 dark:text-sky-300 border-sky-500/30'
  return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
}

function fmtTime(ts: string) {
  try {
    const d = new Date(ts)
    if (Number.isNaN(d.getTime())) return ts
    return d.toLocaleString('zh-CN', { hour12: false })
  } catch {
    return ts
  }
}

function changeText(ev: RuntimeLogItem): string | null {
  const ch = ev.change
  if (!ch || typeof ch !== 'object') return null
  const type = String((ch as any).type || '')
  if (type === 'route') {
    const from = (ch as any).from || '—'
    const to = (ch as any).to || ev.path || '—'
    return `路由变化: ${from} → ${to}`
  }
  if (type === 'api') {
    const method = (ch as any).method || ev.method || 'GET'
    const path = (ch as any).path || ev.path || ''
    const status = (ch as any).status ?? ev.status ?? '?'
    const req = (ch as any).request
    const reqHint = req ? ` · 请求体 ${typeof req === 'object' ? Object.keys(req).join(',') || 'object' : 'payload'}` : ''
    return `接口: ${method} ${path} → ${status}${reqHint}`
  }
  if (type === 'visibility') {
    return `可见性: ${(ch as any).state}`
  }
  try {
    return JSON.stringify(ch)
  } catch {
    return null
  }
}

export function SettingsRuntimeLogsPanel() {
  const [source, setSource] = useState('')
  const [level, setLevel] = useState('INFO')
  const [category, setCategory] = useState('')
  const [q, setQ] = useState('')
  const [qInput, setQInput] = useState('')
  const [events, setEvents] = useState<RuntimeLogItem[]>([])
  const [status, setStatus] = useState<Awaited<ReturnType<typeof api.runtimeLogsStatus>> | null>(null)
  const [loading, setLoading] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [clearing, setClearing] = useState(false)

  const selected = useMemo(
    () => events.find((e) => e.id === selectedId) || null,
    [events, selectedId],
  )

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [list, st] = await Promise.all([
        api.runtimeLogs({
          source: source || undefined,
          level: level || undefined,
          category: category || undefined,
          q: q || undefined,
          limit: 300,
        }),
        api.runtimeLogsStatus(),
      ])
      setEvents(list.events || [])
      setStatus(st)
      setSelectedId((prev) => {
        if (prev && (list.events || []).some((e) => e.id === prev)) return prev
        return list.events?.[0]?.id ?? null
      })
    } catch (e: any) {
      toast(e?.message || '加载运行日志失败', 'error')
    } finally {
      setLoading(false)
    }
  }, [source, level, category, q])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!autoRefresh) return
    const t = setInterval(() => {
      void load()
    }, 3000)
    return () => clearInterval(t)
  }, [autoRefresh, load])

  useEffect(() => {
    logUiInfo('打开运行日志面板', {
      source,
      level,
      category,
      session: getRuntimeSessionId(),
    })
    // 只在进入面板时记一次
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const onClear = async () => {
    if (!confirm('清空内存运行日志并截断磁盘日志文件？此操作不可恢复。')) return
    setClearing(true)
    try {
      await api.clearRuntimeLogs(false)
      toast('运行日志已清空', 'success')
      setEvents([])
      setSelectedId(null)
      await load()
    } catch (e: any) {
      toast(e?.message || '清空失败', 'error')
    } finally {
      setClearing(false)
    }
  }

  const fileSummary = useMemo(() => {
    if (!status?.files) return []
    return Object.entries(status.files)
      .filter(([, v]) => v)
      .map(([name, v]) => ({
        name,
        size: v ? `${(v.size_bytes / 1024).toFixed(1)} KB` : '—',
        mtime: v?.mtime || '',
      }))
  }, [status])

  return (
    <>
      <PageHeader
        title="运行日志"
        subtitle="数据台后端 + 用户台前端的统一运行轨迹，便于对照页面操作与接口变化"
      />

      <section className="rounded-card border border-border bg-surface p-4 mb-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 text-sm text-secondary">
            <Activity className="h-4 w-4 text-accent" />
            <span>
              缓冲 {status?.buffer_size ?? '—'} / {status?.buffer_capacity ?? '—'}
            </span>
            {status?.process_id && (
              <span className="font-mono text-[11px] text-muted">pid {status.process_id}</span>
            )}
          </div>
          <div className="flex-1" />
          <button
            type="button"
            onClick={() => setAutoRefresh((v) => !v)}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-btn border px-2.5 py-1.5 text-xs transition-colors',
              autoRefresh
                ? 'border-accent/40 bg-accent/10 text-accent'
                : 'border-border bg-elevated text-secondary hover:text-foreground',
            )}
          >
            {autoRefresh ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
            {autoRefresh ? '自动刷新中' : '已暂停'}
          </button>
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-elevated px-2.5 py-1.5 text-xs text-secondary hover:text-foreground disabled:opacity-50"
          >
            <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
            刷新
          </button>
          <button
            type="button"
            onClick={() => void onClear()}
            disabled={clearing}
            className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-elevated px-2.5 py-1.5 text-xs text-bear hover:bg-bear/10 disabled:opacity-50"
          >
            <Eraser className="h-3.5 w-3.5" />
            清空
          </button>
        </div>

        {status?.log_dir && (
          <div className="mt-3 text-[11px] text-muted font-mono break-all">
            落盘目录: {status.log_dir}
          </div>
        )}
        {fileSummary.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {fileSummary.map((f) => (
              <span
                key={f.name}
                className="rounded-btn border border-border bg-elevated px-2 py-1 text-[11px] text-secondary"
                title={f.mtime}
              >
                {f.name} · {f.size}
              </span>
            ))}
          </div>
        )}
      </section>

      <section className="rounded-card border border-border bg-surface p-4 mb-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-muted">
            <span className="inline-flex items-center gap-1"><Filter className="h-3 w-3" />来源</span>
            <select
              value={source}
              onChange={(e) => setSource(e.target.value)}
              className="h-8 min-w-[8rem] rounded-btn border border-border bg-base px-2 text-sm text-foreground"
            >
              {SOURCE_OPTS.map((o) => (
                <option key={o.value || 'all'} value={o.value}>{o.label}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">
            <span>级别</span>
            <select
              value={level}
              onChange={(e) => setLevel(e.target.value)}
              className="h-8 min-w-[8rem] rounded-btn border border-border bg-base px-2 text-sm text-foreground"
            >
              {LEVEL_OPTS.map((o) => (
                <option key={o.value || 'all'} value={o.value}>{o.label}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">
            <span>分类</span>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="h-8 min-w-[8rem] rounded-btn border border-border bg-base px-2 text-sm text-foreground"
            >
              {CATEGORY_OPTS.map((o) => (
                <option key={o.value || 'all'} value={o.value}>{o.label}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-1 min-w-[14rem] flex-col gap-1 text-xs text-muted">
            <span className="inline-flex items-center gap-1"><Search className="h-3 w-3" />搜索</span>
            <div className="flex gap-2">
              <input
                value={qInput}
                onChange={(e) => setQInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') setQ(qInput.trim())
                }}
                placeholder="路径 / 消息 / 变化内容"
                className="h-8 flex-1 rounded-btn border border-border bg-base px-2 text-sm text-foreground outline-none focus:border-accent"
              />
              <button
                type="button"
                onClick={() => setQ(qInput.trim())}
                className="h-8 rounded-btn border border-border bg-elevated px-3 text-xs text-secondary hover:text-foreground"
              >
                应用
              </button>
            </div>
          </label>
        </div>
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.4fr)_minmax(18rem,0.9fr)] gap-4">
        <section className="rounded-card border border-border bg-surface overflow-hidden min-h-[28rem]">
          <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
            <ScrollText className="h-4 w-4 text-accent" />
            <h3 className="text-sm font-medium text-foreground">事件流</h3>
            <span className="text-[11px] text-muted">{events.length} 条</span>
          </div>
          <div className="max-h-[38rem] overflow-auto">
            {events.length === 0 ? (
              <div className="p-8 text-center text-sm text-muted">
                {loading ? '加载中…' : '暂无日志。切换几个页面或点一次数据同步后再来看。'}
              </div>
            ) : (
              <table className="w-full text-left text-xs">
                <thead className="sticky top-0 bg-elevated/95 backdrop-blur border-b border-border text-muted">
                  <tr>
                    <th className="px-3 py-2 font-medium">时间</th>
                    <th className="px-2 py-2 font-medium">来源</th>
                    <th className="px-2 py-2 font-medium">级别</th>
                    <th className="px-2 py-2 font-medium">分类</th>
                    <th className="px-3 py-2 font-medium">消息 / 变化</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((ev) => {
                    const ch = changeText(ev)
                    const active = ev.id === selectedId
                    return (
                      <tr
                        key={ev.id}
                        onClick={() => setSelectedId(ev.id)}
                        className={cn(
                          'border-b border-border/60 cursor-pointer transition-colors',
                          active ? 'bg-accent/10' : 'hover:bg-elevated/60',
                        )}
                      >
                        <td className="px-3 py-2 font-mono text-[11px] text-secondary whitespace-nowrap align-top">
                          {fmtTime(ev.ts)}
                        </td>
                        <td className="px-2 py-2 align-top">
                          <span className={cn('inline-flex rounded border px-1.5 py-0.5 text-[10px]', sourceBadge(ev.source))}>
                            {ev.source}
                          </span>
                        </td>
                        <td className={cn('px-2 py-2 font-mono align-top', levelClass(ev.level))}>
                          {ev.level}
                        </td>
                        <td className="px-2 py-2 text-secondary align-top">{ev.category}</td>
                        <td className="px-3 py-2 align-top">
                          <div className="text-foreground">{ev.message}</div>
                          {ch && <div className="mt-0.5 text-[11px] text-accent/90">{ch}</div>}
                          {(ev.method || ev.path) && (
                            <div className="mt-0.5 font-mono text-[10px] text-muted">
                              {[ev.method, ev.path, ev.status != null ? `→ ${ev.status}` : '', ev.duration_ms != null ? `${ev.duration_ms}ms` : '']
                                .filter(Boolean)
                                .join(' ')}
                            </div>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section className="rounded-card border border-border bg-surface overflow-hidden min-h-[28rem]">
          <div className="border-b border-border px-4 py-2.5">
            <h3 className="text-sm font-medium text-foreground">事件详情</h3>
            <p className="text-[11px] text-muted mt-0.5">查看完整 change / detail，对照前后差异</p>
          </div>
          {!selected ? (
            <div className="p-6 text-sm text-muted">选择左侧一条日志查看详情</div>
          ) : (
            <div className="p-4 space-y-3 text-xs max-h-[38rem] overflow-auto">
              <div className="grid grid-cols-[5rem_1fr] gap-y-1.5 gap-x-2">
                <div className="text-muted">时间</div>
                <div className="font-mono text-secondary">{fmtTime(selected.ts)}</div>
                <div className="text-muted">来源</div>
                <div>{selected.source}</div>
                <div className="text-muted">级别</div>
                <div className={levelClass(selected.level)}>{selected.level}</div>
                <div className="text-muted">分类</div>
                <div>{selected.category}</div>
                <div className="text-muted">消息</div>
                <div className="text-foreground whitespace-pre-wrap break-words">{selected.message}</div>
                {selected.path && (
                  <>
                    <div className="text-muted">路径</div>
                    <div className="font-mono break-all">{selected.method} {selected.path}</div>
                  </>
                )}
                {selected.session_id && (
                  <>
                    <div className="text-muted">会话</div>
                    <div className="font-mono break-all text-secondary">{selected.session_id}</div>
                  </>
                )}
              </div>

              {selected.change && (
                <div>
                  <div className="mb-1 text-muted">变化 (change)</div>
                  <pre className="rounded-md bg-elevated border border-border px-2.5 py-2 text-[11px] font-mono text-secondary whitespace-pre-wrap break-all leading-relaxed">
                    {JSON.stringify(selected.change, null, 2)}
                  </pre>
                </div>
              )}
              {selected.detail && (
                <div>
                  <div className="mb-1 text-muted">细节 (detail)</div>
                  <pre className="rounded-md bg-elevated border border-border px-2.5 py-2 text-[11px] font-mono text-secondary whitespace-pre-wrap break-all leading-relaxed">
                    {JSON.stringify(selected.detail, null, 2)}
                  </pre>
                </div>
              )}
              <div>
                <div className="mb-1 text-muted">原始事件</div>
                <pre className="rounded-md bg-elevated border border-border px-2.5 py-2 text-[11px] font-mono text-secondary whitespace-pre-wrap break-all leading-relaxed">
                  {JSON.stringify(selected, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </section>
      </div>
    </>
  )
}
