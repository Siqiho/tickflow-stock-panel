/**
 * 行业/概念主力资金流向面板
 * 数据来源：/api/free/fund-flow/{boards|concepts}（东财 dataapi 优先，push2 clist 兜底）
 * 按主力净流入 main_net 排序，展示净流入 TOP 与净流出 TOP。
 */
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDownRight, ArrowUpRight, ChevronDown, CloudDownload, Landmark, Layers3, Loader2, RefreshCw, Wallet } from 'lucide-react'
import { SourceTraceButton } from '@/components/SourceTraceButton'
import { api, type FundFlowItem, type FundFlowWindowResponse } from '@/lib/api'
import { useSettings } from '@/lib/useSharedQueries'
import { SOURCE_TRACE } from '@/lib/sourceTraceSubjects'
import { QK } from '@/lib/queryKeys'
import { fmtBigNum } from '@/lib/format'
import { cn } from '@/lib/cn'

export type SectorFundFlowKind = 'board' | 'concept' | 'both'

const HISTORY_WINDOWS = [
  { id: '1d', label: '1 天', days: 1 },
  { id: '5d', label: '5 天', days: 5 },
  { id: '1w', label: '1 周', days: 5 },
  { id: '2w', label: '半个月', days: 10 },
  { id: '1m', label: '1 个月', days: 21 },
  { id: '1q', label: '1 个季度', days: 63 },
  { id: '6m', label: '半年', days: 126 },
  { id: '1y', label: '1 年', days: 250 },
] as const

type HistoryWindowId = (typeof HISTORY_WINDOWS)[number]['id']
const DEFAULT_HISTORY_WINDOW: HistoryWindowId = '5d'
/** 行业/概念窗口累计只开到已回补满窗的最长档；半年/1 年仍回退当日快照。 */
const BOARD_WINDOW_MAX_DAYS = 63

function n(v: number | null | undefined) {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

/** 东财板块涨跌幅多为百分点（如 2.35 = +2.35%），不是小数。 */
function fmtBoardPct(v: number | null | undefined) {
  const x = n(v)
  if (x == null) return '—'
  return `${x >= 0 ? '+' : ''}${x.toFixed(2)}%`
}

function pctTone(v: number | null | undefined) {
  const x = n(v)
  if (x == null || x === 0) return 'text-muted'
  return x > 0 ? 'text-bull' : 'text-bear'
}

function industryWindowFreshnessLine(windowData: FundFlowWindowResponse) {
  const asOf = windowData.data_as_of || windowData.end || '—'
  const statusText = windowData.freshness_status === 'fresh'
    ? '足够新'
    : windowData.freshness_status === 'stale'
      ? '已陈旧'
      : '无法确定'
  const completeText = windowData.window_complete === false ? '窗口不完整' : '窗口完整'
  return `数据截止 ${asOf} · ${statusText} · ${completeText}`
}

function moneyTone(v: number | null | undefined) {
  const x = n(v)
  if (x == null || x === 0) return 'text-muted'
  return x > 0 ? 'text-bull' : 'text-bear'
}

function splitFlow(items: FundFlowItem[], limit: number) {
  const scored = items
    .map(item => ({ ...item, main_net: n(item.main_net) }))
    .filter(item => item.main_net != null && String(item.name || '').trim()) as Array<FundFlowItem & { main_net: number }>

  const inflow = [...scored].sort((a, b) => b.main_net - a.main_net).slice(0, limit)
  const used = new Set(inflow.map(item => String(item.code || item.name)))
  const outflow = [...scored]
    .sort((a, b) => a.main_net - b.main_net)
    .filter(item => !used.has(String(item.code || item.name)))
    .slice(0, limit)
  return { inflow, outflow, asOf: scored[0]?.as_of ?? null, total: scored.length }
}

function FlowColumn({
  title,
  tone,
  rows,
}: {
  title: string
  tone: 'in' | 'out'
  rows: Array<FundFlowItem & { main_net: number }>
}) {
  const Icon = tone === 'in' ? ArrowUpRight : ArrowDownRight
  const headClass = tone === 'in' ? 'text-bull' : 'text-bear'
  return (
    <div className="min-w-0">
      <div className={cn('mb-1.5 flex items-center gap-1 text-[11px] font-medium', headClass)}>
        <Icon className="h-3.5 w-3.5" />
        {title}
      </div>
      <div className="space-y-1">
        {rows.length === 0 ? (
          <div className="rounded-lg border border-border/60 bg-elevated/40 px-2 py-3 text-center text-[11px] text-muted">暂无数据</div>
        ) : (
          rows.map((row, idx) => {
            const maxAbs = Math.max(...rows.map(r => Math.abs(r.main_net)), 1)
            const width = Math.max(8, Math.round((Math.abs(row.main_net) / maxAbs) * 100))
            return (
              <div key={`${row.code || row.name}-${idx}`} className="rounded-lg border border-border/50 bg-elevated/30 px-2 py-1.5">
                <div className="flex items-center gap-2">
                  <span className="w-4 shrink-0 text-[10px] text-muted">{idx + 1}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-[12px] font-medium text-foreground">{row.name}</span>
                      <span className={cn('shrink-0 font-mono text-[11px] tabular-nums', moneyTone(row.main_net))}>
                        {fmtBigNum(row.main_net)}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center gap-2">
                      <div className="h-1 flex-1 overflow-hidden rounded-full bg-border/60">
                        <div
                          className={cn(
                            'h-full rounded-full',
                            row.main_net > 0 ? 'bg-bull/70' : row.main_net < 0 ? 'bg-bear/70' : 'bg-border/60',
                          )}
                          style={{ width: `${width}%` }}
                        />
                      </div>
                      <span className={cn('w-14 shrink-0 text-right font-mono text-[10px] tabular-nums', pctTone(row.change_pct))}>
                        {fmtBoardPct(row.change_pct)}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

function SingleKindPanel({
  kind,
  title,
  top = 8,
  dense = false,
  readOnly = false,
  className,
}: {
  kind: 'board' | 'concept'
  title: string
  top?: number
  dense?: boolean
  readOnly?: boolean
  className?: string
}) {
  const queryClient = useQueryClient()
  const settings = useSettings()
  const isAdmin = settings.data?.is_admin === true
  // 拉取足够多的排名，才能同时覆盖净流入 TOP 与净流出 TOP
  const fetchTop = 200
  const queryKey = kind === 'board' ? QK.fundFlowBoards(fetchTop) : QK.fundFlowConcepts(fetchTop)
  const listFn = kind === 'board' ? api.fundFlowBoards : api.fundFlowConcepts
  const refreshFn = kind === 'board' ? api.fundFlowBoardsRefresh : api.fundFlowConceptsRefresh
  const Icon = kind === 'board' ? Landmark : Layers3
  const [historyWindow, setHistoryWindow] = useState<HistoryWindowId>(DEFAULT_HISTORY_WINDOW)
  const [historyMenuOpen, setHistoryMenuOpen] = useState(false)
  const selectedWindow = HISTORY_WINDOWS.find(item => item.id === historyWindow) ?? HISTORY_WINDOWS.find(item => item.id === DEFAULT_HISTORY_WINDOW)!
  const wantsWindow = selectedWindow.days <= BOARD_WINDOW_MAX_DAYS
  const kindLabel = kind === 'board' ? '行业' : '概念'

  const query = useQuery({
    queryKey,
    queryFn: () => listFn(fetchTop),
    staleTime: 60_000,
  })
  const windowQuery = useQuery({
    queryKey: kind === 'board'
      ? QK.fundFlowBoardsWindow(selectedWindow.days, top)
      : QK.fundFlowConceptsWindow(selectedWindow.days, top),
    queryFn: () => kind === 'board'
      ? api.fundFlowBoardsWindow(selectedWindow.days, top)
      : api.fundFlowConceptsWindow(selectedWindow.days, top),
    enabled: wantsWindow,
    staleTime: 30_000,
  })

  const refresh = useMutation({
    mutationFn: refreshFn,
    onSuccess: () => {
      setRefreshStamp(new Date().toISOString())
      queryClient.invalidateQueries({ queryKey })
    },
  })

  const historyRefresh = useMutation({
    mutationFn: () =>
      kind === 'board'
        ? api.fundFlowBoardsHistoryRefresh(200, selectedWindow.days)
        : api.fundFlowConceptsHistoryRefresh(20, selectedWindow.days),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey })
      queryClient.invalidateQueries({
        queryKey: kind === 'board'
          ? QK.fundFlowBoardsWindow(selectedWindow.days, top)
          : QK.fundFlowConceptsWindow(selectedWindow.days, top),
      })
      setHistoryMenuOpen(false)
      setHistoryStamp(Date.now())
    },
  })

  const [refreshStamp, setRefreshStamp] = useState<string | null>(null)
  const [historyStamp, setHistoryStamp] = useState<number | null>(null)
  useEffect(() => {
    if (!refresh.isSuccess || !refreshStamp) return
    const timer = window.setTimeout(() => {
      setRefreshStamp(null)
      refresh.reset()
    }, 3000)
    return () => window.clearTimeout(timer)
  }, [refresh.isSuccess, refreshStamp, refresh])
  useEffect(() => {
    if (!historyStamp) return
    const timer = window.setTimeout(() => {
      setHistoryStamp(null)
      historyRefresh.reset()
    }, 3000)
    return () => window.clearTimeout(timer)
  }, [historyStamp, historyRefresh.reset])
  const windowData = windowQuery.data as FundFlowWindowResponse | undefined
  const useWindowRanking = wantsWindow && windowData?.window_complete !== false
  const split = useMemo(() => {
    const rankingItems = useWindowRanking ? (windowData?.items ?? []) : (query.data?.items ?? [])
    return splitFlow(rankingItems, top)
  }, [useWindowRanking, windowData?.items, query.data?.items, top])
  const empty = !(wantsWindow ? windowQuery.isLoading : query.isLoading) && split.total === 0
  const topIn = split.inflow[0]
  const topOut = split.outflow[0]

  return (
    <section className={cn('rounded-card border border-border bg-surface/80 p-2.5', className)}>
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 text-[12px] font-semibold text-foreground">
            <Wallet className="h-3.5 w-3.5 text-accent" />
            <Icon className="h-3.5 w-3.5 text-muted" />
            <span className="truncate">{title}</span>
          </div>
          <div className="mt-0.5 text-[10px] text-muted">
            {useWindowRanking
              ? `${windowData?.window_label ?? `近${selectedWindow.days}个交易日累计`} · ${kindLabel}日线窗口排名`
              : `当日快照 · ${selectedWindow.label}窗口数据不足`}
            {useWindowRanking
              ? <span className="ml-1 font-mono">· {windowData?.start ?? '—'} ~ {windowData?.end ?? '—'}</span>
              : (split.asOf ? <span className="ml-1 font-mono">· {split.asOf}</span> : null)}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <SourceTraceButton subjects={kind === 'board' ? SOURCE_TRACE.industryFundFlow : SOURCE_TRACE.conceptFundFlow} />
          {!readOnly && <>
          <button
            type="button"
            onClick={() => {
              if (isAdmin) refresh.mutate()
              else query.refetch()
            }}
            disabled={refresh.isPending || query.isFetching || historyRefresh.isPending}
            aria-label="更新"
            className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-btn text-muted transition-colors hover:bg-elevated hover:text-foreground disabled:opacity-50"
            title="更新主力资金流排名"
          >
            {refresh.isPending || query.isFetching ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CloudDownload className="h-3.5 w-3.5" />}
          </button>
          <div className="relative">
            <button
              type="button"
              onClick={() => setHistoryMenuOpen(open => !open)}
              disabled={historyRefresh.isPending || refresh.isPending}
              aria-haspopup="menu"
              aria-expanded={historyMenuOpen}
              className="inline-flex items-center gap-1 rounded-btn border border-border bg-elevated px-2 py-1 text-[11px] text-secondary transition-colors hover:text-foreground disabled:opacity-50"
              title={`按${selectedWindow.label}窗口看${kindLabel}累计排名`}
            >
              {historyRefresh.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Layers3 className="h-3 w-3" />}
              {selectedWindow.label}
              <ChevronDown className="h-3 w-3 opacity-70" />
            </button>
            {historyMenuOpen ? (
              <div
                role="menu"
                className="absolute right-0 z-20 mt-1 min-w-[7.5rem] rounded-lg border border-border bg-surface p-1 shadow-lg"
              >
                {HISTORY_WINDOWS.map(item => (
                  <button
                    key={item.id}
                    type="button"
                    role="menuitem"
                    disabled={historyRefresh.isPending || refresh.isPending}
                    onClick={() => {
                      setHistoryWindow(item.id)
                      setHistoryMenuOpen(false)
                    }}
                    className={cn(
                      'flex w-full items-center justify-between rounded-md px-2 py-1 text-left text-[11px] transition-colors',
                      item.id === selectedWindow.id
                        ? 'bg-accent/10 text-accent'
                        : 'text-secondary hover:bg-elevated hover:text-foreground',
                    )}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          </>}
        </div>
      </div>

      {refresh.isSuccess && refreshStamp ? (
        <div className="mb-2 rounded-lg border border-bull/20 bg-bull/5 px-2 py-1 font-mono text-[10px] text-secondary">
          已更新 · {new Date(refreshStamp).toLocaleString('zh-CN', { hour12: false })}
        </div>
      ) : refresh.isError ? (
        <div className="mb-2 text-[11px] text-bear">{(refresh.error as Error)?.message || '更新失败'}</div>
      ) : refresh.isPending ? (
        <div className="mb-2 text-[10px] text-muted">正在更新…</div>
      ) : null}
      {historyRefresh.isSuccess && historyStamp ? (
        <div className="mb-2 rounded-lg border border-bull/20 bg-bull/5 px-2 py-1 text-[10px] text-secondary">
          {selectedWindow.label}回补完成：{historyRefresh.data?.selected ?? 0} 个板块 · {historyRefresh.data?.history_points ?? 0} 点
          {historyRefresh.data?.failed?.length ? ` · 失败 ${historyRefresh.data.failed.length}` : ''}
          {historyRefresh.data?.source ? ` · 来源 ${historyRefresh.data.source}` : ''}
        </div>
      ) : null}
      {historyRefresh.isError ? (
        <div className="mb-2 text-[11px] text-bear">{(historyRefresh.error as Error)?.message || '近N日回补失败'}</div>
      ) : null}
      {!useWindowRanking ? (
        <div className="mb-2 text-[10px] text-muted">窗口数据不足，当前仍显示当日快照，不能当作{selectedWindow.label}完整累计榜</div>
      ) : null}
      {useWindowRanking && windowData ? (
        <div className="mb-2 text-[10px] text-muted">
          {windowData.window_complete === false ? '窗口数据不足 · ' : ''}
          覆盖 {windowData.covered_count}/{windowData.snapshot_count} 只{kindLabel}日线
          {windowData.full_count != null ? ` · 满窗 ${windowData.full_count}/${windowData.snapshot_count}` : ''}
          {windowData.missing_count ? ` · 缺 ${windowData.missing_count} 只` : ''}
        </div>
      ) : null}
      {kind === 'board' && windowData ? (
        <div className="mb-2 text-[10px] text-muted">{industryWindowFreshnessLine(windowData)}</div>
      ) : null}
      {(useWindowRanking ? windowQuery.isLoading : query.isLoading) ? (

        <div className="flex items-center justify-center gap-2 py-10 text-[12px] text-muted">
          <Loader2 className="h-4 w-4 animate-spin" /> 加载资金流...
        </div>
      ) : empty ? (
        <div className="rounded-lg border border-dashed border-border bg-elevated/20 px-3 py-6 text-center">
          <div className="text-[12px] text-secondary">尚未缓存主力资金流</div>
          <div className="mt-1 text-[11px] text-muted">
            {readOnly ? '等待管理员更新服务器共享数据' : (useWindowRanking ? '先回补行业日线，再按窗口累计排名' : '点击刷新从东财拉取行业/概念主力净流入排名')}
          </div>
          {!readOnly && <button
            type="button"
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending}
            className="mt-3 inline-flex items-center gap-1.5 rounded-btn border border-accent/40 bg-accent/10 px-3 py-1.5 text-[12px] text-accent hover:bg-accent/15 disabled:opacity-50"
          >
            {refresh.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            立即获取
          </button>}
          {!readOnly && refresh.isError ? (
            <div className="mt-2 text-[11px] text-bear">{(refresh.error as Error)?.message || '刷新失败'}</div>
          ) : null}
        </div>
      ) : (
        <>
          {!dense && (
            <div className="mb-2 grid grid-cols-2 gap-2">
              <div className="rounded-lg border border-bull/20 bg-bull/5 px-2.5 py-1.5">
                <div className="text-[10px] text-muted">最大净流入</div>
                <div className="truncate text-[12px] font-semibold text-foreground">{topIn?.name ?? '—'}</div>
                <div className={cn('font-mono text-[11px] tabular-nums', moneyTone(topIn?.main_net))}>{fmtBigNum(topIn?.main_net)}</div>
              </div>
              <div className="rounded-lg border border-bear/20 bg-bear/5 px-2.5 py-1.5">
                <div className="text-[10px] text-muted">最大净流出</div>
                <div className="truncate text-[12px] font-semibold text-foreground">{topOut?.name ?? '—'}</div>
                <div className={cn('font-mono text-[11px] tabular-nums', moneyTone(topOut?.main_net))}>{fmtBigNum(topOut?.main_net)}</div>
              </div>
            </div>
          )}
          <div className={cn('grid gap-3', dense ? 'grid-cols-1' : 'grid-cols-1 sm:grid-cols-2')}>
            <FlowColumn title="净流入 TOP" tone="in" rows={split.inflow} />
            <FlowColumn title="净流出 TOP" tone="out" rows={split.outflow} />
          </div>
        </>
      )}
    </section>
  )
}

export function SectorFundFlowPanel({
  kind = 'both',
  top = 8,
  className,
  dense = false,
  readOnly = false,
}: {
  kind?: SectorFundFlowKind
  top?: number
  className?: string
  dense?: boolean
  readOnly?: boolean
}) {
  if (kind === 'both') {
    return (
      <div className={cn('grid grid-cols-1 gap-3 xl:grid-cols-2', className)}>
        <SingleKindPanel kind="concept" title="概念主力资金流向" top={top} dense={dense} readOnly={readOnly} />
        <SingleKindPanel kind="board" title="行业主力资金流向" top={top} dense={dense} readOnly={readOnly} />
      </div>
    )
  }
  return (
    <SingleKindPanel
      kind={kind}
      title={kind === 'board' ? '行业主力资金流向' : '概念主力资金流向'}
      top={top}
      dense={dense}
      readOnly={readOnly}
      className={className}
    />
  )
}

/** 供 Hero 等位置读取当前最大净流入板块名称 */
export function useTopFundFlowName(kind: 'board' | 'concept') {
  const top = 200
  const query = useQuery({
    queryKey: kind === 'board' ? QK.fundFlowBoards(top) : QK.fundFlowConcepts(top),
    queryFn: () => (kind === 'board' ? api.fundFlowBoards(top) : api.fundFlowConcepts(top)),
    staleTime: 60_000,
  })
  return useMemo(() => {
    const items = query.data?.items ?? []
    const best = [...items]
      .map(item => ({ name: String(item.name || '').trim(), main_net: n(item.main_net) }))
      .filter(x => x.name && x.main_net != null)
      .sort((a, b) => (b.main_net as number) - (a.main_net as number))[0]
    return {
      name: best?.name ?? null,
      mainNet: best?.main_net ?? null,
      isLoading: query.isLoading,
      hasData: !!best,
    }
  }, [query.data?.items, query.isLoading])
}
