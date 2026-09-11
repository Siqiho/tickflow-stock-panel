import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FolderOpen, Search } from 'lucide-react'
import { api } from '@/lib/api'
import {
  EXTERNAL_READONLY_SOURCES_QK,
  MARGIN_TRADING_QUERY_LIMIT,
  classifyMarginQueryError,
  formatMissingValue,
  marginQueryErrorLabel,
} from '@/lib/dataSources'

const STATUS_LABEL = {
  unconfigured: '未配置',
  inaccessible: '目录不可访问',
  configured: '已配置',
} as const

export function ExternalReadOnlyData({
  isAdmin = false,
  initialSymbol = '',
  compact = false,
  idPrefix = 'offline-margin',
}: {
  isAdmin?: boolean
  initialSymbol?: string
  compact?: boolean
  idPrefix?: string
}) {
  const headingId = `${idPrefix}-heading`
  const symbolInputId = `${idPrefix}-symbol`
  const meta = useQuery({
    queryKey: EXTERNAL_READONLY_SOURCES_QK,
    queryFn: api.externalReadonlySources,
    enabled: isAdmin,
  })
  const [symbol, setSymbol] = useState(initialSymbol)
  const [submitted, setSubmitted] = useState('')

  const query = useQuery({
    queryKey: ['offline-margin-trading', submitted],
    queryFn: () => api.getMarginTrading({
      symbol: submitted,
      source: 'offline_quantdb',
      limit: MARGIN_TRADING_QUERY_LIMIT,
    }),
    enabled: Boolean(submitted),
    retry: false,
  })

  const status = meta.data?.status
  const canQuery = status === 'configured'
  const queryError = query.error ? classifyMarginQueryError(query.error) : null
  const resultOwnedByDraft = Boolean(submitted) && symbol.trim() === submitted
  const showError = Boolean(resultOwnedByDraft && query.isError && queryError)
  const showEmpty = Boolean(resultOwnedByDraft && !query.isError && query.isSuccess && query.data?.status === 'empty')
  const showTable = Boolean(resultOwnedByDraft && !query.isError && query.isSuccess && query.data && query.data.status !== 'empty')
  const missingFields = showTable ? query.data?.missing_fields ?? [] : []

  const submitQuery = (next: string) => {
    if (!next || !canQuery) return
    if (next === submitted) {
      void query.refetch()
      return
    }
    setSubmitted(next)
  }

  const onSymbolChange = (value: string) => {
    setSymbol(value)
    if (value.trim() !== submitted) {
      setSubmitted('')
    }
  }

  return (
    <section
      aria-labelledby={headingId}
      className={compact
        ? 'border-t border-border/70 pt-3'
        : 'rounded-card border border-border bg-surface p-4'}
    >
      {!compact && (
        <div className="flex items-start gap-2">
          <FolderOpen aria-hidden="true" className="mt-0.5 h-4 w-4 text-secondary" />
          <div>
            <h3 id={headingId} className="text-sm font-medium text-foreground">外部只读数据</h3>
            <p className="mt-1 text-[11px] text-muted">
              只读外置包，目前仅支持两融按标的查询；不是全包已入库，也不计入上方托管存储。
            </p>
          </div>
        </div>
      )}
      {compact && (
        <h3 id={headingId} className="sr-only">外部只读数据</h3>
      )}

      {meta.isError ? (
        <p role="alert" className={`${compact ? 'mt-0' : 'mt-3'} rounded-btn bg-danger/5 px-3 py-2 text-xs text-danger`}>
          外部只读状态暂不可用：{(meta.error as Error).message}
        </p>
      ) : meta.isLoading ? (
        <p className={`${compact ? 'mt-0' : 'mt-3'} text-xs text-muted`}>正在读取外置包配置</p>
      ) : (
        <div className={`${compact ? 'mt-0' : 'mt-3'} space-y-2 text-xs`}>
          <p>
            <span className="text-muted">配置状态：</span>
            <span className={status === 'configured' ? 'text-foreground' : 'text-warning'}>
              {status ? STATUS_LABEL[status] : '无记录'}
            </span>
            <span className="text-muted"> · 目前支持：两融</span>
            {status === 'configured' ? (
              <span className="text-muted"> · 已配置不代表全部数据可读</span>
            ) : null}
          </p>
          {isAdmin && meta.data?.root_path ? (
            <details className="rounded-btn border border-border bg-elevated/40 px-3 py-2">
              <summary className="cursor-pointer text-muted">配置路径（管理员）</summary>
              <p className="mt-2 break-all font-mono text-[11px] text-secondary">{meta.data.root_path}</p>
            </details>
          ) : null}
        </div>
      )}

      <form
        className="mt-3 flex flex-wrap items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          submitQuery(symbol.trim())
        }}
      >
        <label className="sr-only" htmlFor={symbolInputId}>两融股票代码</label>
        <input
          id={symbolInputId}
          value={symbol}
          onChange={(event) => onSymbolChange(event.target.value)}
          placeholder="例如 600519.SH"
          disabled={!canQuery}
          className="w-40 rounded-btn border border-border bg-elevated px-2 py-1.5 text-xs"
        />
        <button
          type="submit"
          disabled={!canQuery || !symbol.trim() || query.isFetching}
          className="inline-flex items-center gap-1 rounded-btn border border-border bg-elevated px-3 py-1.5 text-xs text-secondary hover:text-foreground disabled:opacity-40"
        >
          <Search aria-hidden="true" className="h-3.5 w-3.5" />
          {query.isFetching ? '查询中…' : '查询两融'}
        </button>
      </form>

      {!submitted ? (
        <p className="mt-3 text-[11px] text-muted">截止按标的查询获取。</p>
      ) : null}
      {resultOwnedByDraft && query.isFetching ? (
        <p className="mt-3 text-xs text-muted">正在查询两融</p>
      ) : null}
      {showError ? (
        <p role="alert" className="mt-3 text-xs text-warning">
          {marginQueryErrorLabel(queryError!)}
          {(query.error as Error).message ? `：${(query.error as Error).message}` : ''}
        </p>
      ) : null}
      {showEmpty ? (
        <p role="status" className="mt-3 text-xs text-secondary">
          {marginQueryErrorLabel('empty')}
          {' · '}来源 {formatMissingValue(query.data?.source)}
          {' · '}截止日 {formatMissingValue(query.data?.as_of)}
        </p>
      ) : null}
      {showTable ? (
        <div className="mt-3 overflow-x-auto">
          <p className="mb-2 text-[11px] text-muted">
            来源 {query.data!.source} · 截止日 {formatMissingValue(query.data!.as_of)} · 最多 {MARGIN_TRADING_QUERY_LIMIT} 条 · 金额单位元 · 数量单位股
          </p>
          {missingFields.length > 0 ? (
            <p className="mb-2 text-[11px] text-muted">缺字段：{missingFields.join('、')}</p>
          ) : null}
          <table className="min-w-full text-left text-xs">
            <thead>
              <tr className="border-b border-border text-muted">
                <th className="py-2 pr-3 font-medium">日期</th>
                <th className="py-2 pr-3 font-medium">融资余额</th>
                <th className="py-2 pr-3 font-medium">融券余额</th>
                <th className="py-2 pr-3 font-medium">融券余量</th>
                <th className="py-2 font-medium">来源</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {query.data!.data.slice(0, MARGIN_TRADING_QUERY_LIMIT).map((row, index) => (
                <tr key={`${row.symbol}-${row.trade_date}-${index}`}>
                  <td className="py-2 pr-3 font-mono text-foreground">{formatMissingValue(row.trade_date)}</td>
                  <td className="py-2 pr-3 font-mono text-secondary">{formatMissingValue(row.financing_balance)}</td>
                  <td className="py-2 pr-3 font-mono text-secondary">{formatMissingValue(row.securities_lending_balance)}</td>
                  <td className="py-2 pr-3 font-mono text-secondary">{formatMissingValue(row.securities_lending_balance_volume)}</td>
                  <td className="py-2 text-secondary">{formatMissingValue(row.source)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}
