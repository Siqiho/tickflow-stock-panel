import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import {
  Bell,
  BookOpenCheck,
  ChevronLeft,
  ChevronRight,
  Copy,
  Download,
  ExternalLink,
  History as HistoryIcon,
  LineChart,
  Loader2,
  RotateCcw,
  Sparkles,
} from 'lucide-react'
import { MarkdownRenderer } from '@/components/financials/MarkdownRenderer'
import { cn } from '@/lib/cn'
import { PageHeader } from '@/components/PageHeader'
import { PageContextModule } from '@/components/PageContextModule'
import { clearPageContext, setPageContext } from '@/lib/pageContext'
import { buildStockAnalysisPageContext } from '@/lib/pageContextSnapshots'
import { EmptyState } from '@/components/EmptyState'
import { StockFinancialSearch } from '@/components/financials/StockFinancialSearch'
import { StockPreviewDialog } from '@/components/StockPreviewDialog'
import { ChipDistributionPanel } from '@/components/ChipDistributionPanel'
import { AnalysisKChart, type PriceLevel, type LevelType } from '@/components/stock-analysis/AnalysisKChart'
import { ResizableAnalysisLayout } from '@/components/stock-analysis/ResizableAnalysisLayout'
import { StockFundFlowPanel } from '@/components/stock-analysis/StockFundFlowPanel'
import { RecentStockList } from '@/components/stock-analysis/RecentStockList'
import { api } from '@/lib/api'
import { useLastStock } from '@/lib/useLastStock'
import { QK } from '@/lib/queryKeys'
import { toast } from '@/components/Toast'
import {
  startAnalysis, findTodayReport, useHistoryReports, useActiveTasks,
  loadHistory,
  type HistoryReport,
} from '@/lib/stockAnalysisStore'

/**
 * 个股分析页 —— 日 K + 关键价位(压力/支撑/密集区/枢轴/前高前低)+ AI 四维分析。
 *
 * 与财务分析页的区别:
 *  - 以【行情 + 关键价位】为视觉主体(专用日 K 图表,不复用个股对话框图表)
 *  - AI 分析输出买卖区间 / 操作建议(非财务质量评级)
 *  - 报告胶囊用蓝色系,与财务分析(紫色)并存
 */
export function StockAnalysis() {
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedSymbol = (searchParams.get('symbol') ?? '').trim().toUpperCase()
  const requestedName = (searchParams.get('name') ?? '').trim()
  const requestedReport = (searchParams.get('report') ?? '').trim()
  const [symbol, setSymbol] = useState<string>(requestedSymbol)
  const [name, setName] = useState<string>(requestedName || requestedSymbol)
  const [checking, setChecking] = useState(false)
  const [confirmReport, setConfirmReport] = useState<{ id: string; created_at: string; focus: string } | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [previewSymbol, setPreviewSymbol] = useState<string | null>(null)
  const [historyLoadFailed, setHistoryLoadFailed] = useState(false)
  const { recent: recentStocks, remember: rememberStock } = useLastStock('stock-analysis')
  const { reports: historyReports, loaded: historyLoaded } = useHistoryReports()
  const analyzingTasks = useActiveTasks().filter(task => task.phase === 'loading' || task.phase === 'streaming')
  const recentWithAnalyzing = [
    ...analyzingTasks
      .filter(task => !recentStocks.some(stock => stock.symbol === task.symbol))
      .map(task => ({ symbol: task.symbol, name: task.name || task.symbol })),
    ...recentStocks,
  ]

  useEffect(() => {
    let cancelled = false
    loadHistory(true).then(loaded => {
      if (!cancelled) setHistoryLoadFailed(!loaded)
    })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!requestedSymbol) return
    const nextName = requestedName || requestedSymbol
    setSymbol(requestedSymbol)
    setName(nextName)
    setShowHistory(false)
    setConfirmReport(null)
    rememberStock(requestedSymbol, nextName)
  }, [rememberStock, requestedName, requestedSymbol])

  useEffect(() => {
    if (!requestedReport) return
    setShowHistory(true)
  }, [requestedReport])

  const onSelect = (sym: string, nm: string) => {
    const nextSymbol = sym.trim().toUpperCase()
    const nextName = nm.trim() || nextSymbol
    const nextParams = new URLSearchParams({ symbol: nextSymbol, name: nextName })
    setSearchParams(nextParams, { replace: true })
    setSymbol(nextSymbol)
    setName(nextName)
    setShowHistory(false)
    setConfirmReport(null)
    rememberStock(nextSymbol, nextName)
  }

  const retryHistoryReports = () => {
    setHistoryLoadFailed(false)
    loadHistory(true).then(loaded => setHistoryLoadFailed(!loaded))
  }

  const openSavedReport = async (report: HistoryReport) => {
    const known = historyReports.some(item => item.id === report.id)
    if (!known) {
      const loaded = await loadHistory(true)
      if (!loaded) {
        toast('这份个股分析报告已不存在', 'error')
        return
      }
    }
    const nextName = report.name?.trim() || report.symbol
    setSearchParams(new URLSearchParams({
      symbol: report.symbol,
      name: nextName,
      report: report.id,
    }), { replace: true })
    setSymbol(report.symbol)
    setName(nextName)
    setShowHistory(true)
    setConfirmReport(null)
    rememberStock(report.symbol, nextName)
  }

  const handleAnalyze = async () => {
    if (!symbol || checking) return
    setChecking(true)
    try {
      // 当日已分析过 → 二次确认(查看今日报告 / 重新分析)
      const today = await findTodayReport(symbol)
      if (today) {
        setConfirmReport({ id: today.id, created_at: today.created_at, focus: today.focus })
      } else {
        await doAnalysis()
      }
    } catch {
      await doAnalysis()
    } finally {
      setChecking(false)
    }
  }

  const doAnalysis = async () => {
    const r = await startAnalysis(symbol, name)
    if (r.error) toast(r.error, 'error')
  }

  useEffect(() => {
    if (!showHistory || !symbol || !historyLoaded || requestedReport) return
    const latest = historyReports.find(report => report.symbol === symbol)
    if (latest) void openSavedReport(latest)
  }, [historyLoaded, historyReports, requestedReport, showHistory, symbol])

  useEffect(() => {
    setPageContext(buildStockAnalysisPageContext({
      symbol,
      name,
      showHistory,
    }))
    return () => clearPageContext('/stock-analysis')
  }, [name, showHistory, symbol])

  return (
    <>
      <PageHeader
        title="个股分析"
        titleExtra={
          <span className="inline-flex items-center rounded-full border border-amber-400/30 bg-amber-400/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-amber-400">
            Beta
          </span>
        }
        subtitle="日 K · 关键价位 · AI 四维分析(技术 / 基本面 / 财务 / 消息面)"
        right={symbol ? (
          <button
            type="button"
            aria-pressed={showHistory}
            onClick={() => setShowHistory(value => !value)}
            className="inline-flex items-center gap-1.5 rounded-btn border border-border px-3 py-1.5 text-xs text-secondary transition-colors hover:bg-elevated hover:text-foreground"
          >
            {showHistory ? <LineChart className="h-3.5 w-3.5" /> : <HistoryIcon className="h-3.5 w-3.5" />}
            {showHistory ? '返回分析' : '历史报告'}
          </button>
        ) : null}
      />

      <div className="w-full max-w-[1800px] px-4 py-5 sm:px-6 lg:px-8 lg:py-6">
        <div
          data-testid="stock-analysis-page-layout"
          className={`grid items-start gap-6 transition-[grid-template-columns] duration-200 ease-out ${
            sidebarCollapsed
              ? 'lg:grid-cols-[2.75rem_minmax(0,1fr)]'
              : 'lg:grid-cols-[18rem_minmax(0,1fr)]'
          }`}
        >
          <PageContextModule id="finder"><aside className="relative lg:sticky lg:top-4" aria-label="股票查找与最近查看">
            {sidebarCollapsed ? (
              <div className="hidden h-11 items-center justify-center lg:flex">
                <StockSidebarToggle collapsed onToggle={() => setSidebarCollapsed(false)} />
              </div>
            ) : null}

            <div
              id="stock-analysis-finder-panel"
              className={`space-y-3 ${sidebarCollapsed ? 'lg:hidden' : ''}`}
            >
              <StockFinancialSearch
                onSelect={onSelect}
                trailingAction={(
                  <StockSidebarToggle collapsed={false} onToggle={() => setSidebarCollapsed(true)} />
                )}
              />
              <RecentStockList
                stocks={recentWithAnalyzing}
                currentSymbol={symbol}
                analyzingTasks={analyzingTasks}
                reports={historyReports}
                reportsLoaded={historyLoaded}
                reportsLoadFailed={historyLoadFailed}
                onSelect={onSelect}
                onOpenReport={openSavedReport}
                onRetryReports={retryHistoryReports}
              />
            </div>
          </aside></PageContextModule>

          <div className="min-w-0 space-y-6">
            {symbol && (
              <div className="flex flex-wrap items-center gap-3">
                <button
                  onClick={() => setPreviewSymbol(symbol)}
                  title="查看个股日 K 详情"
                  className="group flex items-center gap-2 rounded-md px-1.5 py-0.5 text-sm transition-colors hover:bg-elevated"
                >
                  <span className="font-medium text-foreground transition-colors group-hover:text-sky-700 dark:group-hover:text-sky-300">{name || symbol}</span>
                  <span className="font-mono text-[10px] text-muted">{symbol}</span>
                  <ExternalLink className="h-3 w-3 text-muted opacity-0 transition-opacity group-hover:opacity-100" />
                </button>
                <button
                  onClick={handleAnalyze}
                  disabled={checking}
                  className="inline-flex items-center gap-1.5 rounded-btn border border-sky-400/30 bg-gradient-to-r from-sky-500/25 to-blue-500/15 px-3 py-1.5 text-xs font-medium text-sky-700 transition-all hover:from-sky-500/35 hover:to-blue-500/25 disabled:cursor-not-allowed disabled:opacity-40 dark:text-sky-300"
                >
                  {checking ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                  AI 个股分析
                </button>
                <button
                  onClick={() => toast('点位提醒功能开发中,敬请期待', 'error')}
                  className="inline-flex items-center gap-1.5 rounded-btn border border-border/40 bg-elevated/40 px-3 py-1.5 text-xs font-medium text-muted transition-all hover:border-border/70 hover:text-secondary"
                  title="当价格触及关键价位时提醒(开发中)"
                >
                  <Bell className="h-3.5 w-3.5" />
                  点位提醒
                  <span className="rounded-full bg-amber-400/15 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wider text-amber-400">
                    开发中
                  </span>
                </button>
              </div>
            )}

            {!symbol ? (
              <EmptyState
                icon={LineChart}
                title="选择一只股票开始分析"
                hint="搜索代码或名称,查看日 K 与关键价位,并可让 AI 进行技术面 / 基本面 / 财务面 / 消息面四维综合分析。"
              />
            ) : showHistory ? (
              <PageContextModule id="history"><HistoryWorkspace
                symbol={symbol}
                name={name}
                reports={historyReports}
                loaded={historyLoaded}
                loadFailed={historyLoadFailed}
                requestedReportId={requestedReport}
                onOpenReport={openSavedReport}
                onRetry={retryHistoryReports}
              /></PageContextModule>
            ) : (
              <StockAnalysisBoard symbol={symbol} />
            )}
          </div>
        </div>
      </div>

      {/* 二次确认:已有历史报告 */}
      {confirmReport && (
        <ConfirmModal
          report={confirmReport}
          onView={() => {
            const report = historyReports.find(item => item.id === confirmReport.id)
            if (report) void openSavedReport(report)
            else setShowHistory(true)
            setConfirmReport(null)
          }}
          onRedo={async () => { setConfirmReport(null); await doAnalysis() }}
          onClose={() => setConfirmReport(null)}
        />
      )}

      {/* 个股日 K 详情对话框(点击名称/代码打开) */}
      <StockPreviewDialog
        symbol={previewSymbol}
        name={previewSymbol === symbol ? name : undefined}
        triggerInfo={null}
        onClose={() => setPreviewSymbol(null)}
      />
    </>
  )
}

function StockSidebarToggle({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const label = collapsed ? '展开股票侧栏' : '向左收起股票侧栏'
  return (
    <button
      type="button"
      aria-label={label}
      aria-expanded={!collapsed}
      aria-controls="stock-analysis-finder-panel"
      title={collapsed ? label : '向左收起，扩大分析区域'}
      onClick={onToggle}
      className={`hidden h-7 w-7 shrink-0 items-center justify-center rounded-md transition-colors hover:bg-elevated hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/40 lg:inline-flex ${
        collapsed ? 'bg-elevated/70 text-secondary' : 'text-muted'
      }`}
    >
      {collapsed
        ? <ChevronRight className="h-3.5 w-3.5" />
        : <ChevronLeft className="h-3.5 w-3.5" />}
    </button>
  )
}

// ===== 分析看板:日 K + 关键价位 =====
function StockAnalysisBoard({ symbol }: { symbol: string }) {
  const kline = useQuery({
    queryKey: ['kline', symbol, ''],
    queryFn: () => api.klineDaily(symbol, 250),
    enabled: !!symbol,
    staleTime: 60_000,
  })

  const levelsQ = useQuery({
    queryKey: QK.stockLevels(symbol),
    queryFn: () => api.stockAnalysisLevels(symbol, 250),
    enabled: !!symbol,
    staleTime: 60_000,
  })

  if (kline.isLoading) {
    return <div className="flex items-center justify-center py-20"><Loader2 className="h-5 w-5 animate-spin text-muted" /></div>
  }

  const rows = kline.data?.rows ?? []
  if (rows.length === 0) {
    return <EmptyState icon={LineChart} title="暂无日 K 数据" hint="该标的尚未同步日 K,请先在数据页或自选页同步。" />
  }

  const levels = (levelsQ.data?.levels ?? {}) as Record<LevelType, PriceLevel[]>

  // 涨跌色:最后一根 K 线收 vs 前一根收(无前日则按开收判断)
  const last = rows[rows.length - 1]
  const prev = rows[rows.length - 2]
  const curClose = levelsQ.data?.close
  const isUp = prev ? (last.close >= prev.close) : (last.close >= last.open)

  const main = (
    <PageContextModule id="chart"><div className="overflow-hidden rounded-card border border-border/60 bg-surface/40">
      <div className="border-b border-border/40 px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <LineChart className="h-4 w-4 shrink-0 text-sky-400" />
            <span className="text-sm font-medium text-foreground">关键价位分析</span>
          </div>
          <div className="flex shrink-0 items-baseline gap-2">
            <span className="text-[10px] text-muted">{rows.length} 个交易日</span>
            <span className="text-[10px] text-muted/60">·</span>
            <span className="text-[10px] text-muted">当前价</span>
            <span className={`font-mono text-base font-bold ${isUp ? 'text-bull' : 'text-bear'}`}>
              {curClose?.toFixed(2) ?? '—'}
            </span>
          </div>
        </div>
      </div>
      <div className="p-3">
        <AnalysisKChart
          rows={rows}
          levels={levels}
          series={levelsQ.data?.series}
          seriesDates={levelsQ.data?.dates}
          defaultLevelTypes={['sr', 'pivot', 'keltner_s']}
          height={480}
        />
      </div>
    </div></PageContextModule>
  )

  const rail = (
    <aside className="grid min-w-0 gap-4 md:grid-cols-2 xl:grid-cols-1" aria-label="个股辅助分析">
      <PageContextModule id="chips"><ChipDistributionPanel
        symbol={symbol}
        height={430}
        days={120}
        linkedPrice={curClose ?? last.close}
        className="rounded-card border border-border/60 bg-surface/55 p-3"
      />
      </PageContextModule>
      <PageContextModule id="flow"><StockFundFlowPanel
        symbol={symbol}
        height={360}
        limit={60}
        className="rounded-card border border-border/60 bg-surface/55 p-3"
      /></PageContextModule>
    </aside>
  )

  return (
    <ResizableAnalysisLayout main={main} rail={rail} />
  )
}

// ===== 历史报告工作区:左侧完整分析,右侧股票报告列表 =====
function HistoryWorkspace({
  symbol,
  name,
  reports,
  loaded,
  loadFailed,
  requestedReportId,
  onOpenReport,
  onRetry,
}: {
  symbol: string
  name: string
  reports: HistoryReport[]
  loaded: boolean
  loadFailed: boolean
  requestedReportId?: string
  onOpenReport: (report: HistoryReport) => void
  onRetry: () => void
}) {
  const mine = reports.filter(r => r.symbol === symbol)
  const viewing = mine.find(r => r.id === requestedReportId) ?? mine[0] ?? null

  if (loadFailed) {
    return (
      <div className="rounded-card border border-dashed border-border bg-surface px-5 py-12 text-center">
        <HistoryIcon className="mx-auto h-7 w-7 text-muted" />
        <h2 className="mt-3 text-sm font-medium text-foreground">历史报告暂时无法读取</h2>
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 inline-flex items-center gap-1.5 rounded-btn border border-border px-3 py-1.5 text-xs text-secondary hover:bg-elevated hover:text-foreground"
        >
          <RotateCcw className="h-3.5 w-3.5" />
          重新读取
        </button>
      </div>
    )
  }
  if (!loaded) {
    return (
      <div className="flex items-center justify-center gap-2 py-20 text-xs text-muted">
        <Loader2 className="h-5 w-5 animate-spin" />
        正在读取历史报告
      </div>
    )
  }
  if (mine.length === 0) {
    return <EmptyState icon={HistoryIcon} title="暂无历史报告" hint={`还没有 ${name || symbol} 的个股分析报告,点击「AI 个股分析」生成第一份。`} />
  }

  const copyReport = async () => {
    if (!viewing?.content) return
    try {
      await navigator.clipboard.writeText(viewing.content)
      toast('已复制完整分析', 'success')
    } catch {
      toast('复制失败', 'error')
    }
  }
  const downloadReport = () => {
    if (!viewing?.content) return
    const blob = new Blob([viewing.content], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${viewing.name || viewing.symbol}-个股分析-${viewing.created_at.slice(0, 10)}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_18rem]">
      <section className="overflow-hidden rounded-card border border-border bg-surface/80" aria-label="历史分析正文">
        <div className="flex items-center justify-between border-b border-border bg-gradient-to-r from-sky-500/5 to-transparent px-4 py-2.5">
          <div className="flex min-w-0 items-center gap-1.5">
            <BookOpenCheck className="h-3.5 w-3.5 shrink-0 text-sky-500" />
            <h2 className="truncate text-xs font-medium text-foreground">
              历史分析 · {viewing.name || viewing.symbol} · {fmtRelative(viewing.created_at)}
            </h2>
          </div>
          <div className="flex items-center gap-1">
            <button type="button" onClick={copyReport} className="inline-flex items-center gap-1 rounded-btn bg-elevated px-2 py-1 text-[11px] text-secondary transition-colors hover:bg-elevated/70 hover:text-foreground" title="复制全文">
              <Copy className="h-3 w-3" />复制
            </button>
            <button type="button" onClick={downloadReport} className="inline-flex items-center gap-1 rounded-btn bg-elevated px-2 py-1 text-[11px] text-secondary transition-colors hover:bg-elevated/70 hover:text-foreground" title="下载为 Markdown">
              <Download className="h-3 w-3" />下载
            </button>
          </div>
        </div>
        <div className="max-h-[calc(100vh-16rem)] overflow-y-auto px-5 py-4">
          {viewing.focus ? (
            <p className="mb-3 rounded-btn bg-sky-500/8 px-3 py-2 text-[11px] text-secondary">关注点：{viewing.focus}</p>
          ) : null}
          <div className="prose prose-invert max-w-none">
            <MarkdownRenderer content={viewing.content} />
          </div>
        </div>
      </section>

      <aside className="overflow-hidden rounded-card border border-border bg-surface/80" aria-label="该股票历史分析列表">
        <div className="flex items-center gap-1.5 border-b border-border bg-gradient-to-r from-sky-500/5 to-transparent px-3 py-2.5">
          <HistoryIcon className="h-3.5 w-3.5 text-sky-500" />
          <span className="text-xs font-medium text-foreground">历史分析</span>
          <span className="font-mono text-[10px] text-muted">({mine.length})</span>
        </div>
        <div className="max-h-[calc(100vh-16rem)] space-y-1 overflow-y-auto p-2">
          {mine.map(r => {
            const active = r.id === viewing.id
            return (
              <button
                key={r.id}
                type="button"
                aria-current={active ? 'true' : undefined}
                aria-label={`查看历史报告：${r.name || r.symbol} ${r.created_at}`}
                onClick={() => onOpenReport(r)}
                className={cn(
                  'group flex w-full items-start gap-2 rounded-lg px-2 py-2 text-left transition-colors',
                  active ? 'bg-sky-500/10 ring-1 ring-sky-400/20' : 'hover:bg-elevated/60',
                )}
              >
                <div className={cn(
                  'mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded font-mono text-[10px] font-bold tabular-nums',
                  active ? 'bg-sky-500/15 text-sky-600 dark:text-sky-300' : 'bg-elevated text-muted',
                )}>
                  {r.close != null ? r.close.toFixed(0) : '报'}
                </div>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5">
                    <span className="truncate text-[11px] font-medium text-foreground">{r.name || r.symbol}</span>
                    <span className="font-mono text-[10px] text-secondary">{fmtRelative(r.created_at)}</span>
                  </span>
                  <span className="mt-0.5 block truncate text-[10px] text-muted">
                    {r.summary || r.focus || '点击查看完整分析'}
                  </span>
                </span>
              </button>
            )
          })}
        </div>
      </aside>
    </div>
  )
}

// ===== 二次确认弹窗 =====
function ConfirmModal({ report, onView, onRedo, onClose }: {
  report: { id: string; created_at: string; focus: string }
  onView: () => void
  onRedo: () => void
  onClose: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" onClick={onClose}>
      <div
        className="w-full max-w-sm bg-surface border border-border rounded-2xl p-5 shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 mb-2">
          <HistoryIcon className="h-4 w-4 text-sky-400" />
          <span className="text-sm font-medium text-foreground">该个股已有分析报告</span>
        </div>
        <p className="text-xs text-secondary leading-relaxed mb-1">
          最近一次报告生成于 <span className="text-foreground">{fmtRelative(report.created_at)}</span>。
        </p>
        {report.focus && <p className="text-xs text-muted mb-1">关注点: {report.focus}</p>}
        <p className="text-xs text-muted mb-4">可直接查看历史,或重新生成一份新报告。</p>
        <div className="flex gap-2">
          <button onClick={onView}
            className="flex-1 h-8 rounded-lg bg-elevated border border-border text-xs text-secondary hover:text-foreground transition-colors">
            查看历史
          </button>
          <button onClick={onRedo}
            className="flex-1 h-8 rounded-lg bg-gradient-to-r from-sky-500/20 to-blue-500/15 border border-sky-400/30 text-xs text-sky-700 dark:text-sky-300 hover:from-sky-500/30 transition-all">
            重新分析
          </button>
        </div>
      </div>
    </div>
  )
}

function fmtRelative(iso: string): string {
  try {
    const t = new Date(iso).getTime()
    const diff = Date.now() - t
    if (diff < 60_000) return '刚刚'
    if (diff < 3600_000) return `${Math.floor(diff / 60_000)} 分钟前`
    if (diff < 86400_000) return `${Math.floor(diff / 3600_000)} 小时前`
    if (diff < 7 * 86400_000) return `${Math.floor(diff / 86400_000)} 天前`
    return new Date(iso).toLocaleDateString('zh-CN')
  } catch { return iso }
}
