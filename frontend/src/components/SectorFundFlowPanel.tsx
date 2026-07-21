/**
 * 行业/概念主力资金流向面板
 * 数据来源：/api/free/fund-flow/{boards|concepts}（东财 dataapi 优先，push2 clist 兜底）
 * 按主力净流入 main_net 排序，展示净流入 TOP 与净流出 TOP。
 */
import { useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDownRight, ArrowUpRight, Landmark, Layers3, Loader2, RefreshCw, Wallet } from 'lucide-react'
import { api, type FundFlowItem } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { fmtBigNum } from '@/lib/format'
import { cn } from '@/lib/cn'

export type SectorFundFlowKind = 'board' | 'concept' | 'both'

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

function moneyTone(v: number | null | undefined) {
  const x = n(v)
  if (x == null || x === 0) return 'text-muted'
  return x > 0 ? 'text-bull' : 'text-bear'
}

function splitFlow(items: FundFlowItem[], limit: number) {
  const scored = items
    .map(item => ({ ...item, main_net: n(item.main_net) }))
    .filter(item => item.main_net != null && String(item.name || '').trim()) as Array<FundFlowItem & { main_net: number }>

  const inflow = [...scored].sort((a, b) => b.main_net - a.main_net).filter(x => x.main_net > 0).slice(0, limit)
  const outflow = [...scored].sort((a, b) => a.main_net - b.main_net).filter(x => x.main_net < 0).slice(0, limit)
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
                          className={cn('h-full rounded-full', tone === 'in' ? 'bg-bull/70' : 'bg-bear/70')}
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
  className,
}: {
  kind: 'board' | 'concept'
  title: string
  top?: number
  dense?: boolean
  className?: string
}) {
  const queryClient = useQueryClient()
  // 拉取足够多的排名，才能同时覆盖净流入 TOP 与净流出 TOP
  const fetchTop = 200
  const queryKey = kind === 'board' ? QK.fundFlowBoards(fetchTop) : QK.fundFlowConcepts(fetchTop)
  const listFn = kind === 'board' ? api.fundFlowBoards : api.fundFlowConcepts
  const refreshFn = kind === 'board' ? api.fundFlowBoardsRefresh : api.fundFlowConceptsRefresh
  const Icon = kind === 'board' ? Landmark : Layers3

  const query = useQuery({
    queryKey,
    queryFn: () => listFn(fetchTop),
    staleTime: 60_000,
  })

  const refresh = useMutation({
    mutationFn: refreshFn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey })
    },
  })

  const historyRefresh = useMutation({
    mutationFn: () =>
      kind === 'board'
        ? api.fundFlowBoardsHistoryRefresh(20, 60)
        : api.fundFlowConceptsHistoryRefresh(20, 60),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey })
    },
  })

  const split = useMemo(() => splitFlow(query.data?.items ?? [], top), [query.data?.items, top])
  const empty = !query.isLoading && split.total === 0
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
            主力净流入排名 · 东财 dataapi（与 go-stock 一致，可回补近N日）
            {split.asOf ? <span className="ml-1 font-mono">· {split.asOf}</span> : null}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending || query.isFetching || historyRefresh.isPending}
            className="inline-flex items-center gap-1 rounded-btn border border-border bg-elevated px-2 py-1 text-[11px] text-secondary transition-colors hover:text-foreground disabled:opacity-50"
            title="刷新主力资金流排名"
          >
            {refresh.isPending || query.isFetching ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
            刷新
          </button>
          <button
            type="button"
            onClick={() => historyRefresh.mutate()}
            disabled={historyRefresh.isPending || refresh.isPending}
            className="inline-flex items-center gap-1 rounded-btn border border-border bg-elevated px-2 py-1 text-[11px] text-secondary transition-colors hover:text-foreground disabled:opacity-50"
            title="回补近60日 Top 流入/流出日线历史"
          >
            {historyRefresh.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Layers3 className="h-3 w-3" />}
            近N日
          </button>
        </div>
      </div>

      {historyRefresh.isSuccess ? (
        <div className="mb-2 rounded-lg border border-bull/20 bg-bull/5 px-2 py-1 text-[10px] text-secondary">
          日线回补完成：{historyRefresh.data?.selected ?? 0} 个板块 · {historyRefresh.data?.history_points ?? 0} 点
          {historyRefresh.data?.failed?.length ? ` · 失败 ${historyRefresh.data.failed.length}` : ''}
          {historyRefresh.data?.source ? ` · 来源 ${historyRefresh.data.source}` : ''}
        </div>
      ) : null}
      {historyRefresh.isError ? (
        <div className="mb-2 text-[11px] text-bear">{(historyRefresh.error as Error)?.message || '近N日回补失败'}</div>
      ) : null}
      {query.isLoading ? (
        <div className="flex items-center justify-center gap-2 py-10 text-[12px] text-muted">
          <Loader2 className="h-4 w-4 animate-spin" /> 加载资金流...
        </div>
      ) : empty ? (
        <div className="rounded-lg border border-dashed border-border bg-elevated/20 px-3 py-6 text-center">
          <div className="text-[12px] text-secondary">尚未缓存主力资金流</div>
          <div className="mt-1 text-[11px] text-muted">点击刷新从东财拉取行业/概念主力净流入排名</div>
          <button
            type="button"
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending}
            className="mt-3 inline-flex items-center gap-1.5 rounded-btn border border-accent/40 bg-accent/10 px-3 py-1.5 text-[12px] text-accent hover:bg-accent/15 disabled:opacity-50"
          >
            {refresh.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            立即获取
          </button>
          {refresh.isError ? (
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
}: {
  kind?: SectorFundFlowKind
  top?: number
  className?: string
  dense?: boolean
}) {
  if (kind === 'both') {
    return (
      <div className={cn('grid grid-cols-1 gap-3 xl:grid-cols-2', className)}>
        <SingleKindPanel kind="concept" title="概念主力资金流向" top={top} dense={dense} />
        <SingleKindPanel kind="board" title="行业主力资金流向" top={top} dense={dense} />
      </div>
    )
  }
  return (
    <SingleKindPanel
      kind={kind}
      title={kind === 'board' ? '行业主力资金流向' : '概念主力资金流向'}
      top={top}
      dense={dense}
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
