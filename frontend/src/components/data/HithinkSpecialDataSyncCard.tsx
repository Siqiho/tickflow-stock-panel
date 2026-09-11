import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { GitBranch, Landmark, Loader2 } from 'lucide-react'
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

const DATASET_IDS = [
  'hithink_limit_pool',
  'hithink_dragon_tiger',
  'hithink_auction_snapshot',
  'hithink_valuation_snapshot',
] as const

export function HithinkSpecialDataSyncCard({
  onTraceSource,
}: {
  onTraceSource?: (subjectId: string) => void
}) {
  const queryClient = useQueryClient()
  const [tradeDate, setTradeDate] = useState(todayInShanghai)
  const sync = useMutation({
    mutationFn: () => api.syncHithinkSpecialData(tradeDate),
    onSuccess: async (result) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: QK.hithinkSpecial(result.resolved_date) }),
        queryClient.invalidateQueries({ queryKey: QK.hithinkSpecial() }),
        queryClient.invalidateQueries({ queryKey: QK.dataCatalog }),
        ...DATASET_IDS.flatMap((datasetId) => [
          queryClient.invalidateQueries({ queryKey: QK.dataCatalogDataset(datasetId) }),
          queryClient.invalidateQueries({ queryKey: QK.dataCatalogSchema(datasetId) }),
          queryClient.invalidateQueries({ queryKey: QK.dataCatalogRuns(datasetId) }),
        ]),
        queryClient.invalidateQueries({ queryKey: QK.dataCatalogRuns() }),
        queryClient.invalidateQueries({ queryKey: QK.dataControlSummary }),
      ])
    },
  })

  return (
    <section className="rounded-card border border-border bg-surface p-4" aria-labelledby="hithink-special-sync-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 id="hithink-special-sync-heading" className="flex items-center gap-2 text-sm font-medium text-foreground">
            <Landmark aria-hidden="true" className="h-4 w-4 text-secondary" />
            同花顺官方特色数据
          </h3>
          <p className="mt-1 text-[11px] text-muted">官方单源 · 涨跌停三池 / 龙虎榜 / 自选竞价 / 自选最新估值 · Asia/Shanghai</p>
        </div>
        <button
          type="button"
          onClick={() => onTraceSource?.('hithink_limit_pool')}
          aria-label="查看同花顺官方特色数据来源"
          className="inline-flex items-center gap-1 rounded-btn px-2 py-1 text-[11px] font-medium text-accent hover:bg-accent/10"
        >
          <GitBranch aria-hidden="true" className="h-3.5 w-3.5" />来源追踪
        </button>
      </div>
      <p className="mt-3 rounded-btn border border-border/70 bg-base/40 px-3 py-2 text-[11px] leading-relaxed text-secondary">
        这是四张独立官方参考表，写进 data/reference/hithink_limit_pool、hithink_dragon_tiger、hithink_auction_snapshot、hithink_valuation_snapshot，在数据目录「参考数据」分组查看。不是 TickFlow 日线，也不覆盖派生 limit_up_events / valuation_daily。查询只读本地；竞价量单位为手；估值只表示最新快照。只有点击下方同步按钮才访问同花顺官方服务，不做自动调度。
      </p>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <input
          type="date"
          value={tradeDate}
          max={todayInShanghai()}
          onChange={(event) => setTradeDate(event.target.value)}
          aria-label="同花顺官方特色数据交易日期"
          className="rounded-btn border border-border bg-base px-3 py-2 text-xs text-foreground outline-none focus:border-accent"
        />
        <button
          type="button"
          onClick={() => sync.mutate()}
          disabled={!tradeDate || sync.isPending}
          className="inline-flex items-center justify-center gap-1.5 rounded-btn bg-accent px-3 py-2 text-xs font-medium text-base disabled:opacity-40"
        >
          {sync.isPending && <Loader2 aria-hidden="true" className="h-3.5 w-3.5 animate-spin" />}
          {sync.isPending ? '同步中…' : '同步官方特色数据'}
        </button>
      </div>
      {sync.isSuccess && (
        <div role="status" className="mt-3 rounded-btn border border-success/30 bg-success/5 px-3 py-2 text-xs text-success">
          已写入独立官方参考表 {sync.data.rows_published.toLocaleString()} 行 · 日期 {sync.data.resolved_date}
          {sync.data.datasets.map((item) => ` · ${item.dataset_id} ${item.rows_published}`).join("")}
          。落点 reference/hithink_*，不覆盖 kline_daily / limit_up_events / valuation_daily。
        </div>
      )}
      {sync.isError && (
        <div role="alert" className="mt-3 rounded-btn border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">
          同步失败：{sync.error instanceof Error ? sync.error.message : '同花顺官方特色数据暂时不可用'}
        </div>
      )}
    </section>
  )
}
