import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Database, GitBranch, Loader2 } from 'lucide-react'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'

function parseSymbols(value: string): string[] {
  return Array.from(new Set(
    value
      .split(/[\s,，;；]+/)
      .map((symbol) => symbol.trim().toUpperCase())
      .filter(Boolean),
  ))
}

export function MarginTradingSyncCard({
  onTraceSource,
}: {
  onTraceSource?: (subjectId: string) => void
}) {
  const queryClient = useQueryClient()
  const [value, setValue] = useState('')
  const symbols = parseSymbols(value)
  const sync = useMutation({
    mutationFn: () => api.syncMarginTrading(symbols, 250),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: QK.dataCatalog }),
        queryClient.invalidateQueries({ queryKey: QK.dataCatalogDataset('stock_margin_trading') }),
        queryClient.invalidateQueries({ queryKey: QK.dataCatalogSchema('stock_margin_trading') }),
        queryClient.invalidateQueries({ queryKey: QK.dataCatalogRuns('stock_margin_trading') }),
        queryClient.invalidateQueries({ queryKey: QK.dataCatalogRuns() }),
        queryClient.invalidateQueries({ queryKey: QK.dataControlSummary }),
      ])
    },
  })

  return (
    <section className="rounded-card border border-border bg-surface p-4" aria-labelledby="margin-trading-sync-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 id="margin-trading-sync-heading" className="flex items-center gap-2 text-sm font-medium text-foreground">
            <Database aria-hidden="true" className="h-4 w-4 text-secondary" />
            个股融资融券
          </h3>
          <p className="mt-1 text-[11px] text-muted">东方财富单源 · 个股日级 · 金额为人民币元，融券量为股</p>
        </div>
        <button
          type="button"
          onClick={() => onTraceSource?.('stock_margin_trading')}
          aria-label="查看融资融券来源"
          className="inline-flex items-center gap-1 rounded-btn px-2 py-1 text-[11px] font-medium text-accent hover:bg-accent/10"
        >
          <GitBranch aria-hidden="true" className="h-3.5 w-3.5" />
          来源追踪
        </button>
      </div>

      <p className="mt-3 rounded-btn border border-border/70 bg-base/40 px-3 py-2 text-[11px] leading-relaxed text-secondary">
        go-stock 仅作为接口情报；采集、规范化、存储和查询由 one-trading 自有 Adapter 持有。
      </p>

      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <input
          type="text"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          aria-label="融资融券股票代码"
          placeholder="输入股票代码，例如 600519.SH、300502.SZ"
          className="min-w-0 flex-1 rounded-btn border border-border bg-base px-3 py-2 text-xs text-foreground outline-none placeholder:text-muted focus:border-accent"
        />
        <button
          type="button"
          onClick={() => sync.mutate()}
          disabled={symbols.length === 0 || sync.isPending}
          className="inline-flex items-center justify-center gap-1.5 rounded-btn bg-accent px-3 py-2 text-xs font-medium text-base disabled:opacity-40"
        >
          {sync.isPending && <Loader2 aria-hidden="true" className="h-3.5 w-3.5 animate-spin" />}
          {sync.isPending ? '同步中…' : '同步融资融券'}
        </button>
      </div>

      {sync.isSuccess && (
        <div role="status" className="mt-3 rounded-btn border border-success/30 bg-success/5 px-3 py-2 text-xs text-success">
          已写入 {sync.data.rows_published.toLocaleString()} 行
          {sync.data.latest_trade_date ? ` · 最新 ${sync.data.latest_trade_date}` : ''}
          {sync.data.empty_symbols.length > 0 ? ` · 无数据：${sync.data.empty_symbols.join('、')}` : ''}
        </div>
      )}
      {sync.isError && (
        <div role="alert" className="mt-3 rounded-btn border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">
          同步失败：{sync.error instanceof Error ? sync.error.message : '融资融券数据源暂时不可用'}
        </div>
      )}
    </section>
  )
}
