import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { BarChart3, GitBranch, Loader2 } from 'lucide-react'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'

function todayInShanghai(): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date())
}

export function MarketPulseSyncCard({ onTraceSource }: { onTraceSource?: (subjectId: string) => void }) {
  const queryClient = useQueryClient()
  const [tradeDate, setTradeDate] = useState(todayInShanghai)
  const sync = useMutation({
    mutationFn: () => api.syncMarketPulse(tradeDate),
    onSuccess: async (result) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: QK.marketPulse(result.resolved_date) }),
        queryClient.invalidateQueries({ queryKey: QK.marketPulse() }),
        queryClient.invalidateQueries({ queryKey: QK.dataCatalog }),
        queryClient.invalidateQueries({ queryKey: QK.dataCatalogDataset('market_pulse') }),
        queryClient.invalidateQueries({ queryKey: QK.dataCatalogSchema('market_pulse') }),
        queryClient.invalidateQueries({ queryKey: QK.dataCatalogRuns('market_pulse') }),
        queryClient.invalidateQueries({ queryKey: QK.dataCatalogRuns() }),
        queryClient.invalidateQueries({ queryKey: QK.dataControlSummary }),
      ])
    },
  })

  return (
    <section className="rounded-card border border-border bg-surface p-4" aria-labelledby="market-pulse-sync-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 id="market-pulse-sync-heading" className="flex items-center gap-2 text-sm font-medium text-foreground">
            <BarChart3 aria-hidden="true" className="h-4 w-4 text-secondary" />
            市场脉搏
          </h3>
          <p className="mt-1 text-[11px] text-muted">财联社单源 · 上证指数分钟点 + 板块异动 · Asia/Shanghai</p>
        </div>
        <button
          type="button"
          onClick={() => onTraceSource?.('market_pulse')}
          aria-label="查看市场脉搏来源"
          className="inline-flex items-center gap-1 rounded-btn px-2 py-1 text-[11px] font-medium text-accent hover:bg-accent/10"
        >
          <GitBranch aria-hidden="true" className="h-3.5 w-3.5" />来源追踪
        </button>
      </div>
      <p className="mt-3 rounded-btn border border-border/70 bg-base/40 px-3 py-2 text-[11px] leading-relaxed text-secondary">
        查询只读本地 Parquet；只有点击下方同步按钮才访问财联社。分时和板块事件必须来自同一请求日期，不做静默交易日回退。
      </p>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <input
          type="date"
          value={tradeDate}
          max={todayInShanghai()}
          onChange={(event) => setTradeDate(event.target.value)}
          aria-label="市场脉搏交易日期"
          className="rounded-btn border border-border bg-base px-3 py-2 text-xs text-foreground outline-none focus:border-accent"
        />
        <button
          type="button"
          onClick={() => sync.mutate()}
          disabled={!tradeDate || sync.isPending}
          className="inline-flex items-center justify-center gap-1.5 rounded-btn bg-accent px-3 py-2 text-xs font-medium text-base disabled:opacity-40"
        >
          {sync.isPending && <Loader2 aria-hidden="true" className="h-3.5 w-3.5 animate-spin" />}
          {sync.isPending ? '同步中…' : '同步市场脉搏'}
        </button>
      </div>
      {sync.isSuccess && (
        <div role="status" className="mt-3 rounded-btn border border-success/30 bg-success/5 px-3 py-2 text-xs text-success">
          已写入 {sync.data.rows_published.toLocaleString()} 行 · 分钟 {sync.data.minute_rows} · 事件 {sync.data.event_rows} · 日期 {sync.data.resolved_date}
        </div>
      )}
      {sync.isError && (
        <div role="alert" className="mt-3 rounded-btn border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">
          同步失败：{sync.error instanceof Error ? sync.error.message : '财联社市场脉搏暂时不可用'}
        </div>
      )}
    </section>
  )
}
