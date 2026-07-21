import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Loader2 } from 'lucide-react'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'

type PullKey = 'pipeline_pull_a_share' | 'pipeline_pull_etf' | 'pipeline_pull_index'

const PULL_ITEMS: { key: PullKey; label: string; desc: string; defaultOn: boolean }[] = [
  { key: 'pipeline_pull_a_share', label: 'A股', desc: '沪深京 A 股日K', defaultOn: true },
  { key: 'pipeline_pull_index', label: '指数', desc: '主要市场指数(默认全量约 600 只)', defaultOn: true },
  { key: 'pipeline_pull_etf', label: 'ETF', desc: '场内交易基金(约 1500 只,首次较慢)', defaultOn: false },
]

const SCOPE_OPTIONS: { value: string; label: string; hint: string }[] = [
  { value: 'ALL', label: '全A', hint: 'instruments / 全市场' },
  { value: 'CSI300', label: '沪深300', hint: '约 300 只' },
  { value: 'CSI500', label: '中证500', hint: '约 500 只（与300不重叠）' },
  { value: 'CSI800', label: '中证800', hint: '沪深300∪中证500，约 800 只' },
  { value: 'SSE50', label: '上证50', hint: '约 50 只' },
  { value: 'WATCHLIST', label: '自选', hint: '仅 watchlist' },
]

export function PipelineScopeConfig() {
  const qc = useQueryClient()
  const prefs = useQuery({ queryKey: QK.preferences, queryFn: api.preferences })

  const pullMut = useMutation({
    mutationFn: (cfg: Partial<Record<PullKey, boolean>>) => api.updatePipelinePullTypes(cfg),
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.preferences }),
  })
  const pipeScopeMut = useMutation({
    mutationFn: (scope: string) => api.updatePipelineUniverseScope(scope),
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.preferences }),
  })
  const pubScopeMut = useMutation({
    mutationFn: (scope: string) => api.updatePublicDataScope(scope),
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.preferences }),
  })
  const periodsMut = useMutation({
    mutationFn: (n: number) => api.updateFinancialMaxPeriods(n),
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.preferences }),
  })

  const busy = pullMut.isPending || pipeScopeMut.isPending || pubScopeMut.isPending || periodsMut.isPending
  const pipeScope = (prefs.data?.pipeline_universe_scope || 'ALL').toUpperCase()
  const pubScope = (prefs.data?.public_data_scope || 'CSI300').toUpperCase()
  const maxPeriods = prefs.data?.financial_max_periods ?? 12

  return (
    <div className="space-y-5">
      <section className="space-y-2">
        <div className="text-sm font-medium text-foreground">资产类型</div>
        <div className="space-y-2">
          {PULL_ITEMS.map((item) => {
            const on = Boolean(prefs.data?.[item.key] ?? item.defaultOn)
            const locked = item.key === 'pipeline_pull_a_share'
            return (
              <label
                key={item.key}
                className={`flex items-start gap-3 rounded-lg border px-3 py-2.5 ${
                  locked ? 'opacity-80' : 'cursor-pointer hover:bg-muted/40'
                }`}
              >
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={on}
                  disabled={locked || busy || prefs.isLoading}
                  onChange={(e) => {
                    if (locked) return
                    pullMut.mutate({ [item.key]: e.target.checked })
                  }}
                />
                <span className="min-w-0">
                  <span className="block text-sm font-medium">{item.label}</span>
                  <span className="block text-xs text-muted-foreground">{item.desc}</span>
                </span>
                {on ? <Check className="ml-auto h-4 w-4 shrink-0 text-emerald-600" /> : null}
              </label>
            )
          })}
        </div>
      </section>

      <section className="space-y-2">
        <div className="text-sm font-medium text-foreground">管道标的范围</div>
        <p className="text-xs text-muted-foreground">
          影响盘后日 K 主标的池。默认全 A；选沪深300可显著加快 free 档试跑。
        </p>
        <div className="flex flex-wrap gap-2">
          {SCOPE_OPTIONS.map((opt) => {
            const active = pipeScope === opt.value
            return (
              <button
                key={opt.value}
                type="button"
                disabled={busy || prefs.isLoading}
                onClick={() => pipeScopeMut.mutate(opt.value)}
                className={`rounded-md border px-2.5 py-1.5 text-xs transition-colors ${
                  active
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border text-muted-foreground hover:bg-muted/50'
                }`}
                title={opt.hint}
              >
                {opt.label}
              </button>
            )
          })}
        </div>
      </section>

      <section className="space-y-2">
        <div className="text-sm font-medium text-foreground">免费复权/财务范围</div>
        <p className="text-xs text-muted-foreground">
          public 源默认同步范围。CSI300 成本低；要覆盖中证500请选「中证800」(300∪500)，勿只选 CSI500 以免日更丢掉已有 300。
        </p>
        <div className="flex flex-wrap gap-2">
          {SCOPE_OPTIONS.map((opt) => {
            const active = pubScope === opt.value
            return (
              <button
                key={opt.value}
                type="button"
                disabled={busy || prefs.isLoading}
                onClick={() => pubScopeMut.mutate(opt.value)}
                className={`rounded-md border px-2.5 py-1.5 text-xs transition-colors ${
                  active
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border text-muted-foreground hover:bg-muted/50'
                }`}
                title={opt.hint}
              >
                {opt.label}
              </button>
            )
          })}
        </div>
      </section>


      <section className="space-y-2">
        <div className="text-sm font-medium text-foreground">财务报告期数量</div>
        <p className="text-xs text-muted-foreground">
          public 财务每次拉取的报告期数（默认 12，约 3 年季度）。越大越全、越慢。
        </p>
        <div className="flex flex-wrap gap-2">
          {[4, 8, 12, 20, 32].map((n) => {
            const active = maxPeriods === n
            return (
              <button
                key={n}
                type="button"
                disabled={busy || prefs.isLoading}
                onClick={() => periodsMut.mutate(n)}
                className={`rounded-md border px-2.5 py-1.5 text-xs transition-colors ${
                  active
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border text-muted-foreground hover:bg-muted/50'
                }`}
              >
                {n} 期
              </button>
            )
          })}
        </div>
      </section>

      {busy ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          保存中…
        </div>
      ) : null}
    </div>
  )
}
