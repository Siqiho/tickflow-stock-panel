import { useState } from 'react'
import {
  CalendarDays,
  ChevronDown,
  ChevronUp,
  Clock3,
  History,
  Loader2,
  RotateCcw,
  TrendingUp,
} from 'lucide-react'

import type { StockRef } from '@/lib/useLastStock'
import type { ActiveTask, HistoryReport } from '@/lib/stockAnalysisStore'
import { restoreDialog } from '@/lib/stockAnalysisStore'
import { cn } from '@/lib/cn'

interface Props {
  stocks: StockRef[]
  currentSymbol?: string
  analyzingTasks?: ActiveTask[]
  reports: HistoryReport[]
  reportsLoaded: boolean
  reportsLoadFailed: boolean
  onSelect: (symbol: string, name: string) => void
  onOpenReport: (report: HistoryReport) => void
  onRetryReports: () => void
}

export function RecentStockList({
  stocks,
  currentSymbol,
  analyzingTasks = [],
  reports = [],
  reportsLoaded = false,
  reportsLoadFailed = false,
  onSelect,
  onOpenReport,
  onRetryReports,
}: Props) {
  const [collapsed, setCollapsed] = useState(false)
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null)

  return (
    <section
      aria-labelledby="recent-stocks-title"
      className={cn(
        'overflow-hidden rounded-card border border-border/60 bg-surface/40',
        !collapsed && 'min-h-48',
      )}
    >
      <button
        type="button"
        aria-label={collapsed ? '展开最近查看' : '收起最近查看'}
        aria-expanded={!collapsed}
        onClick={() => setCollapsed(value => !value)}
        className={cn(
          'group flex w-full items-center justify-between px-3 py-2.5 text-left transition-colors hover:bg-elevated/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-sky-400/40',
          !collapsed && 'border-b border-border/50',
        )}
      >
        <div className="flex items-center gap-2">
          <Clock3 className="h-3.5 w-3.5 text-sky-500" />
          <h2 id="recent-stocks-title" className="text-xs font-medium text-foreground">最近查看</h2>
        </div>
        <div className="flex items-center gap-1 text-muted">
          {!reportsLoaded && !reportsLoadFailed ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
          <span className="flex h-7 w-7 items-center justify-center rounded-md transition-colors group-hover:bg-base/70 group-hover:text-foreground">
            {collapsed ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronUp className="h-3.5 w-3.5" />}
          </span>
        </div>
      </button>

      {collapsed ? null : reportsLoadFailed ? (
        <div className="px-4 py-5 text-center">
          <p className="text-xs text-muted">历史报告暂时无法读取</p>
          <button
            type="button"
            onClick={onRetryReports}
            className="mt-2 inline-flex items-center gap-1 text-[11px] text-sky-600 hover:text-sky-500 dark:text-sky-300"
          >
            <RotateCcw className="h-3 w-3" />
            重新读取
          </button>
        </div>
      ) : stocks.length === 0 ? (
        <div className="px-4 py-8 text-center">
          <Clock3 className="mx-auto h-6 w-6 text-muted/50" />
          <p className="mt-2 text-xs text-muted">查看过的股票会显示在这里</p>
        </div>
      ) : (
        <div className="max-h-[calc(100vh-15rem)] space-y-1 overflow-y-auto p-2">
          {stocks.map(stock => {
            const active = stock.symbol === currentSymbol
            const analyzingTask = analyzingTasks.find(task => task.symbol === stock.symbol)
            const stockReports = reports.filter(report => report.symbol === stock.symbol)
            const reportsExpanded = expandedSymbol === stock.symbol
            return (
              <div key={stock.symbol}>
                <div className={cn(
                  'flex items-center rounded-lg border transition-colors',
                  active
                    ? 'border-sky-400/30 bg-sky-500/10'
                    : 'border-transparent hover:border-border/60 hover:bg-elevated/60',
                )}>
                  <button
                    type="button"
                    aria-label={analyzingTask ? `正在分析：${stock.name} ${stock.symbol}` : `最近查看：${stock.name} ${stock.symbol}`}
                    aria-current={active ? 'true' : undefined}
                    aria-busy={analyzingTask ? true : undefined}
                    onClick={() => {
                      if (analyzingTask) {
                        restoreDialog(analyzingTask.id)
                        return
                      }
                      onSelect(stock.symbol, stock.name)
                    }}
                    className="group flex min-w-0 flex-1 items-center gap-2.5 px-2.5 py-2 text-left"
                  >
                    <span className={cn(
                      'flex h-7 w-7 shrink-0 items-center justify-center rounded-md',
                      analyzingTask || active ? 'bg-sky-500/15 text-sky-600 dark:text-sky-300' : 'bg-elevated text-muted',
                    )}>
                      {analyzingTask
                        ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        : <TrendingUp className="h-3.5 w-3.5" />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-xs font-medium text-foreground">{stock.name}</span>
                      <span className="mt-0.5 block font-mono text-[10px] text-muted">{stock.symbol}</span>
                    </span>
                    {analyzingTask ? (
                      <span className="shrink-0 rounded-full bg-sky-500/10 px-1.5 py-0.5 text-[9px] font-medium text-sky-600 dark:text-sky-300">
                        分析中
                      </span>
                    ) : active ? (
                      <span className="shrink-0 rounded-full bg-sky-500/10 px-1.5 py-0.5 text-[9px] font-medium text-sky-600 dark:text-sky-300">
                        当前
                      </span>
                    ) : null}
                  </button>

                  {reportsLoaded && stockReports.length > 0 ? (
                    <button
                      type="button"
                      aria-label={`${reportsExpanded ? '收起' : '展开'}${stock.name}的历史报告`}
                      aria-expanded={reportsExpanded}
                      onClick={() => setExpandedSymbol(reportsExpanded ? null : stock.symbol)}
                      className="mr-1.5 inline-flex h-7 shrink-0 items-center gap-1 rounded-md px-1.5 text-[10px] tabular-nums text-muted transition-colors hover:bg-base/70 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/40"
                    >
                      <History className="h-3 w-3" />
                      <span>{stockReports.length}</span>
                      {reportsExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                    </button>
                  ) : null}
                </div>

                {reportsExpanded ? (
                  <div className="ml-5 mt-1 space-y-1 border-l border-border/60 pl-2">
                    {stockReports.map(report => {
                      const archivedAt = formatArchivedAt(report.created_at)
                      return (
                        <button
                          key={report.id}
                          type="button"
                          aria-label={`查看${stock.name}历史报告：${archivedAt}`}
                          onClick={() => onOpenReport(report)}
                          className="group flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-elevated"
                        >
                          <CalendarDays className="mt-0.5 h-3 w-3 shrink-0 text-sky-500" />
                          <span className="min-w-0 flex-1">
                            <span className="block font-mono text-[10px] text-secondary">{archivedAt}</span>
                            <span className="mt-0.5 block truncate text-[10px] text-muted group-hover:text-secondary">
                              {report.summary || report.focus || '点击查看完整报告'}
                            </span>
                          </span>
                        </button>
                      )
                    })}
                  </div>
                ) : null}
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}

function formatArchivedAt(iso: string): string {
  const matched = iso.match(/^\d{4}-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/)
  if (!matched) return iso
  return `${matched[1]}-${matched[2]} ${matched[3]}:${matched[4]}`
}
