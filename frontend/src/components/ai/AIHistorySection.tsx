import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import type { LucideIcon } from 'lucide-react'
import {
  AlertTriangle,
  ArrowUpRight,
  BookOpenCheck,
  Bot,
  FileText,
  History,
  RefreshCw,
  ScanSearch,
  TrendingUp,
} from 'lucide-react'

import {
  api,
  type AiFinancialReport,
  type AiPageReport,
  type AiReviewReport,
  type AiStockReport,
  type StrategyDetail,
} from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'

type HistoryKind = 'stock' | 'financial' | 'review' | 'strategy' | 'page'
type HistoryFilter = 'all' | HistoryKind
type HistoryTone = 'blue' | 'purple' | 'emerald' | 'amber' | 'violet'

interface AIHistoryItem {
  key: string
  kind: HistoryKind
  kindLabel: string
  title: string
  subject: string
  summary: string
  createdAt?: string
  to: string
  icon: LucideIcon
  tone: HistoryTone
}

interface AIHistoryResult {
  items: AIHistoryItem[]
  failedSections: string[]
}

interface SettledValue<T> {
  value: T | null
  failed: boolean
}

const FILTERS: { id: HistoryFilter; label: string }[] = [
  { id: 'all', label: '全部' },
  { id: 'stock', label: '个股' },
  { id: 'financial', label: '财务' },
  { id: 'review', label: '复盘' },
  { id: 'strategy', label: '策略' },
  { id: 'page', label: '页面' },
]

const TOP_LEVEL_HISTORY_KINDS = new Set<HistoryKind>(['stock', 'review', 'page'])
const HISTORY_ONLY_FILTERS = FILTERS.filter(item => !TOP_LEVEL_HISTORY_KINDS.has(item.id as HistoryKind))

const HISTORY_TONES: Record<HistoryTone, { icon: string; badge: string; border: string }> = {
  blue: {
    icon: 'bg-blue-500/10 text-blue-600 ring-blue-400/20 dark:text-blue-300',
    badge: 'border-blue-400/20 bg-blue-500/10 text-blue-600 dark:text-blue-300',
    border: 'hover:border-blue-400/35',
  },
  purple: {
    icon: 'bg-purple-500/10 text-purple-600 ring-purple-400/20 dark:text-purple-300',
    badge: 'border-purple-400/20 bg-purple-500/10 text-purple-600 dark:text-purple-300',
    border: 'hover:border-purple-400/35',
  },
  emerald: {
    icon: 'bg-emerald-500/10 text-emerald-600 ring-emerald-400/20 dark:text-emerald-300',
    badge: 'border-emerald-400/20 bg-emerald-500/10 text-emerald-600 dark:text-emerald-300',
    border: 'hover:border-emerald-400/35',
  },
  amber: {
    icon: 'bg-amber-500/10 text-amber-600 ring-amber-400/20 dark:text-amber-300',
    badge: 'border-amber-400/20 bg-amber-500/10 text-amber-600 dark:text-amber-300',
    border: 'hover:border-amber-400/35',
  },
  violet: {
    icon: 'bg-violet-500/10 text-violet-600 ring-violet-400/20 dark:text-violet-300',
    badge: 'border-violet-400/20 bg-violet-500/10 text-violet-600 dark:text-violet-300',
    border: 'hover:border-violet-400/35',
  },
}

async function settle<T>(load: () => Promise<T>): Promise<SettledValue<T>> {
  try {
    return { value: await load(), failed: false }
  } catch {
    return { value: null, failed: true }
  }
}

function withQuery(pathname: string, params: Record<string, string | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value) search.set(key, value)
  }
  const query = search.toString()
  return query ? `${pathname}?${query}` : pathname
}

function formatArchivedAt(iso?: string): string {
  if (!iso) return '已保存到策略池'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function reportSummary(summary: string | undefined, focus: string | undefined, fallback: string): string {
  return summary?.trim() || focus?.trim() || fallback
}

function mapFinancialReport(report: AiFinancialReport): AIHistoryItem {
  return {
    key: `financial:${report.id}`,
    kind: 'financial',
    kindLabel: '财务分析',
    title: report.name?.trim() || report.symbol,
    subject: `${report.symbol}${report.periods ? ` · ${report.periods} 期财务数据` : ''}`,
    summary: reportSummary(report.summary, report.focus, '已生成 AI 财务分析报告'),
    createdAt: report.created_at,
    to: withQuery('/financials', {
      symbol: report.symbol,
      name: report.name,
      report: report.id,
    }),
    icon: FileText,
    tone: 'purple',
  }
}

function groupStockReports(reports: AiStockReport[]): AIHistoryItem[] {
  const groups = new Map<string, AiStockReport[]>()
  for (const report of reports) {
    const symbol = report.symbol.trim().toUpperCase()
    const group = groups.get(symbol) ?? []
    group.push(report)
    groups.set(symbol, group)
  }

  return [...groups.values()].map((group) => {
    const latest = [...group].sort((left, right) => {
      const leftTime = new Date(left.created_at).getTime()
      const rightTime = new Date(right.created_at).getTime()
      return rightTime - leftTime
    })[0]
    const count = group.length
    return {
      key: `stock:${latest.symbol}`,
      kind: 'stock',
      kindLabel: '个股分析',
      title: latest.name?.trim() || latest.symbol,
      subject: latest.symbol,
      summary: count > 1
        ? `共 ${count} 份历史分析 · 最近 ${reportSummary(latest.summary, latest.focus, '已生成 AI 个股综合分析报告')}`
        : reportSummary(latest.summary, latest.focus, '已生成 AI 个股综合分析报告'),
      createdAt: latest.created_at,
      to: withQuery('/stock-analysis', {
        symbol: latest.symbol,
        name: latest.name,
        report: latest.id,
      }),
      icon: TrendingUp,
      tone: 'blue',
    }
  })
}

function mapReviewReport(report: AiReviewReport): AIHistoryItem {
  return {
    key: `review:${report.id}`,
    kind: 'review',
    kindLabel: '大盘复盘',
    title: `${report.as_of} 大盘复盘`,
    subject: report.emotion_label?.trim() || '盘后复盘报告',
    summary: reportSummary(report.summary, report.focus, '已生成 AI 大盘复盘报告'),
    createdAt: report.created_at,
    to: withQuery('/review', { report: report.id }),
    icon: BookOpenCheck,
    tone: 'emerald',
  }
}


function mapPageReport(report: AiPageReport): AIHistoryItem {
  const route = report.route || '/'
  return {
    key: `page:${report.id}`,
    kind: 'page',
    kindLabel: '页面分析',
    title: report.title?.trim() || '页面分析',
    subject: [report.as_of, report.focus].filter(Boolean).join(' · ') || route,
    summary: reportSummary(report.summary, report.focus, '已保存当前页 AI 分析，含图表与正文'),
    createdAt: report.created_at,
    to: withQuery(route, { pageAi: report.id }),
    icon: Bot,
    tone: 'violet',
  }
}
function mapStrategy(strategy: StrategyDetail): AIHistoryItem {
  return {
    key: `strategy:${strategy.id}`,
    kind: 'strategy',
    kindLabel: 'AI 策略',
    title: strategy.name,
    subject: `${strategy.id} · v${strategy.version}`,
    summary: strategy.description?.trim() || '已保存到现有策略池',
    to: withQuery('/screener', { strategy: strategy.id }),
    icon: ScanSearch,
    tone: 'amber',
  }
}

async function fetchAIHistory(): Promise<AIHistoryResult> {
  const [financial, stock, review, strategies, pages] = await Promise.all([
    settle(() => api.financialReportsList()),
    settle(() => api.stockAnalysisReportsList()),
    settle(() => api.reviewReportsList()),
    settle(() => api.strategyList()),
    settle(() => api.pageAiReportsList()),
  ])

  const failedSections = [
    financial.failed ? '财务分析' : '',
    stock.failed ? '个股分析' : '',
    review.failed ? '大盘复盘' : '',
    strategies.failed ? 'AI 策略' : '',
    pages.failed ? '页面分析' : '',
  ].filter(Boolean)

  if (failedSections.length === 5) {
    throw new Error('AI 历史记录暂时无法读取')
  }

  const items = [
    ...(financial.value?.reports ?? []).map(mapFinancialReport),
    ...groupStockReports(stock.value?.reports ?? []),
    ...(review.value?.reports ?? []).map(mapReviewReport),
    ...(strategies.value?.strategies ?? []).filter(strategy => strategy.source === 'ai').map(mapStrategy),
    ...(pages.value?.reports ?? []).map(mapPageReport),
  ]

  items.sort((left, right) => {
    const leftTime = left.createdAt ? new Date(left.createdAt).getTime() : Number.NEGATIVE_INFINITY
    const rightTime = right.createdAt ? new Date(right.createdAt).getTime() : Number.NEGATIVE_INFINITY
    if (leftTime !== rightTime) return rightTime - leftTime
    return left.title.localeCompare(right.title, 'zh-CN')
  })

  return { items, failedSections }
}

export function AIHistorySection({
  lockedFilter,
  hideFilters = false,
  title,
  subtitle,
}: {
  lockedFilter?: HistoryFilter
  hideFilters?: boolean
  title?: string
  subtitle?: string
} = {}) {
  const [filter, setFilter] = useState<HistoryFilter>(lockedFilter ?? 'all')
  const activeFilter = lockedFilter ?? filter
  const visibleFilters = hideFilters || (lockedFilter && lockedFilter !== 'all') ? [] : HISTORY_ONLY_FILTERS
  const historyQuery = useQuery({
    queryKey: QK.aiHistory,
    queryFn: fetchAIHistory,
    staleTime: 5_000,
    refetchOnMount: 'always',
    refetchInterval: 10_000,
  })

  const allItems = useMemo(() => historyQuery.data?.items ?? [], [historyQuery.data?.items])
  const visibleItems = useMemo(() => {
    if (activeFilter === 'all') return allItems.filter(item => !TOP_LEVEL_HISTORY_KINDS.has(item.kind))
    return allItems.filter(item => item.kind === activeFilter)
  }, [activeFilter, allItems])

  const counts = useMemo(() => {
    const next: Record<HistoryFilter, number> = {
      all: allItems.length,
      stock: 0,
      financial: 0,
      review: 0,
      strategy: 0,
      page: 0,
    }
    for (const item of allItems) next[item.kind] += 1
    if (!lockedFilter || lockedFilter === 'all') {
      next.all = allItems.filter(item => !TOP_LEVEL_HISTORY_KINDS.has(item.kind)).length
    }
    return next
  }, [allItems, lockedFilter])

  return (
    <section aria-labelledby="ai-history-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-500/10 text-purple-600 ring-1 ring-purple-400/20 dark:text-purple-300">
              <History className="h-4 w-4" />
            </div>
            <div>
              <h2 id="ai-history-title" className="text-base font-semibold text-foreground">{title ?? '历史记录'}</h2>
              <p className="mt-0.5 text-xs text-muted">{subtitle ?? '完成并保存的 AI 结果会集中显示在这里'}</p>
            </div>
          </div>
        </div>
        <button
          type="button"
          onClick={() => historyQuery.refetch()}
          disabled={historyQuery.isFetching}
          className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-surface px-2.5 py-1.5 text-xs text-secondary transition-colors hover:text-foreground disabled:cursor-wait disabled:opacity-60"
        >
          <RefreshCw className={cn('h-3.5 w-3.5', historyQuery.isFetching && 'animate-spin')} />
          刷新
        </button>
      </div>

      {visibleFilters.length > 0 ? (
      <div className="mt-3 flex max-w-full gap-1.5 overflow-x-auto pb-1" aria-label="历史记录分类">
        {visibleFilters.map(item => (
          <button
            key={item.id}
            type="button"
            aria-pressed={activeFilter === item.id}
            onClick={() => setFilter(item.id)}
            className={cn(
              'inline-flex shrink-0 items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors',
              activeFilter === item.id
                ? 'border-purple-400/30 bg-purple-500/10 text-purple-600 dark:text-purple-300'
                : 'border-border bg-surface text-muted hover:text-secondary',
            )}
          >
            {item.label}
            <span className="font-mono text-[10px] opacity-70">{counts[item.id]}</span>
          </button>
        ))}
      </div>
      ) : null}

      {historyQuery.data?.failedSections.length ? (
        <div className="mt-3 flex items-start gap-2 rounded-btn border border-amber-400/25 bg-amber-400/[0.06] px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{historyQuery.data.failedSections.join('、')}的历史暂未读取，其余记录仍可使用。</span>
        </div>
      ) : null}

      {historyQuery.isPending ? (
        <div className="mt-3 grid gap-3 md:grid-cols-2" aria-label="正在读取历史记录">
          {[0, 1, 2, 3].map(index => (
            <div key={index} className="h-32 animate-pulse rounded-card border border-border bg-surface" />
          ))}
        </div>
      ) : historyQuery.isError ? (
        <div className="mt-3 rounded-card border border-dashed border-border bg-surface px-5 py-10 text-center">
          <AlertTriangle className="mx-auto h-7 w-7 text-amber-500" />
          <h3 className="mt-3 text-sm font-medium text-foreground">历史记录暂时无法读取</h3>
          <p className="mt-1 text-xs text-muted">可以稍后刷新，不影响各分析页面继续生成报告。</p>
        </div>
      ) : visibleItems.length === 0 ? (
        <div className="mt-3 rounded-card border border-dashed border-border bg-surface px-5 py-10 text-center">
          <History className="mx-auto h-7 w-7 text-muted" />
          <h3 className="mt-3 text-sm font-medium text-foreground">
            {activeFilter === 'all' ? '还没有 AI 历史记录' : `还没有${FILTERS.find(item => item.id === activeFilter)?.label}记录`}
          </h3>
          <p className="mt-1 text-xs text-muted">分析完成并保存后，会自动出现在这里。</p>
        </div>
      ) : (
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          {visibleItems.map(item => {
            const tone = HISTORY_TONES[item.tone]
            const Icon = item.icon
            return (
              <Link
                key={item.key}
                to={item.to}
                aria-label={`查看${item.kindLabel}历史：${item.title}`}
                className={cn(
                  'group flex min-h-32 items-start gap-3 rounded-card border border-border bg-surface p-4 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md',
                  tone.border,
                )}
              >
                <div className={cn('flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ring-1', tone.icon)}>
                  <Icon className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <span className={cn('inline-flex rounded-full border px-1.5 py-0.5 text-[9px] font-semibold', tone.badge)}>
                        {item.kindLabel}
                      </span>
                      <h3 className="mt-1.5 truncate text-sm font-semibold text-foreground">{item.title}</h3>
                    </div>
                    <ArrowUpRight className="mt-1 h-4 w-4 shrink-0 text-muted transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-foreground" />
                  </div>
                  <div className="mt-0.5 truncate font-mono text-[10px] text-muted">{item.subject}</div>
                  <p className="mt-2 line-clamp-2 text-xs leading-5 text-secondary">{item.summary}</p>
                  <div className="mt-2 text-[10px] text-muted">{formatArchivedAt(item.createdAt)}</div>
                </div>
              </Link>
            )
          })}
        </div>
      )}
    </section>
  )
}
