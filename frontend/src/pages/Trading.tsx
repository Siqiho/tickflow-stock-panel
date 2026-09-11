import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  BriefcaseBusiness,
  Loader2,
  Pencil,
  Plus,
  ShieldCheck,
  Trash2,
  WalletCards,
  X,
} from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { PageContextModule } from '@/components/PageContextModule'
import { clearPageContext, setPageContext } from '@/lib/pageContext'
import { buildTradingPageContext } from '@/lib/pageContextSnapshots'
import { EmptyState } from '@/components/EmptyState'
import { api, type PortfolioHolding } from '@/lib/api'
import { cn } from '@/lib/cn'

const QUERY_KEY = ['portfolio', 'snapshot'] as const

function money(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function percent(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${(value * 100).toFixed(2)}%`
}

function pnlClass(value?: number | null) {
  if (value == null || value === 0) return 'text-secondary'
  return value > 0 ? 'text-rose-400' : 'text-emerald-400'
}

type FormState = { symbol: string; quantity: string; avgCost: string; note: string }
const EMPTY_FORM: FormState = { symbol: '', quantity: '', avgCost: '', note: '' }

export function Trading() {
  const queryClient = useQueryClient()
  const portfolio = useQuery({ queryKey: QUERY_KEY, queryFn: api.portfolioSnapshot })
  const [formOpen, setFormOpen] = useState(false)
  const [editingSymbol, setEditingSymbol] = useState('')
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [formError, setFormError] = useState('')

  const refresh = () => queryClient.invalidateQueries({ queryKey: QUERY_KEY })
  const save = useMutation({
    mutationFn: () => api.portfolioSaveHolding({
      symbol: form.symbol.trim().toUpperCase(),
      quantity: Number(form.quantity),
      avg_cost: Number(form.avgCost),
      note: form.note.trim(),
    }),
    onSuccess: async () => {
      await refresh()
      setFormOpen(false)
      setEditingSymbol('')
      setForm(EMPTY_FORM)
      setFormError('')
    },
    onError: cause => setFormError(cause instanceof Error ? cause.message : '保存持仓失败'),
  })
  const remove = useMutation({
    mutationFn: (symbol: string) => api.portfolioDeleteHolding(symbol),
    onSuccess: refresh,
  })

  const summary = portfolio.data?.summary
  const holdings = portfolio.data?.holdings ?? []
  const cards = useMemo(() => [
    { label: '持仓数量', value: String(summary?.holding_count ?? 0), hint: '独立于其他用户' },
    { label: '持仓成本', value: `¥ ${money(summary?.total_cost)}`, hint: '按平均成本计算' },
    { label: '最新市值', value: `¥ ${money(summary?.total_market_value)}`, hint: portfolio.data?.as_of ? `行情 ${portfolio.data.as_of}` : '暂无行情' },
    { label: '浮动盈亏', value: `¥ ${money(summary?.total_pnl)}`, hint: percent(summary?.total_pnl_pct), pnl: summary?.total_pnl },
  ], [portfolio.data?.as_of, summary])

  const openCreate = () => {
    setEditingSymbol('')
    setForm(EMPTY_FORM)
    setFormError('')
    setFormOpen(true)
  }

  const openEdit = (holding: PortfolioHolding) => {
    setEditingSymbol(holding.symbol)
    setForm({
      symbol: holding.symbol,
      quantity: String(holding.quantity),
      avgCost: String(holding.avg_cost),
      note: holding.note ?? '',
    })
    setFormError('')
    setFormOpen(true)
  }

  const submit = () => {
    if (!/^\d{6}\.(SH|SZ|BJ)$/i.test(form.symbol.trim())) {
      setFormError('请输入带交易所后缀的股票代码，例如 600000.SH')
      return
    }
    if (!Number.isInteger(Number(form.quantity)) || Number(form.quantity) <= 0) {
      setFormError('持仓数量必须是正整数')
      return
    }
    if (!Number.isFinite(Number(form.avgCost)) || Number(form.avgCost) <= 0) {
      setFormError('平均成本必须是正数')
      return
    }
    save.mutate()
  }

  useEffect(() => {
    setPageContext(buildTradingPageContext({
      asOf: portfolio.data?.as_of ?? null,
      holdingCount: summary?.holding_count ?? holdings.length,
      totalCost: summary?.total_cost ?? null,
      marketValue: summary?.total_market_value ?? null,
      pnl: summary?.total_pnl ?? null,
      holdings: holdings.map(item => ({
        symbol: item.symbol,
        name: item.name,
        quantity: item.quantity,
        pnl: item.pnl_amount ?? null,
      })),
    }))
    return () => clearPageContext('/trading')
  }, [holdings, portfolio.data?.as_of, summary])

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="持仓"
        subtitle="个人持仓账本 · 共用市场行情 · 不连接券商、不执行下单"
        right={(
          <button
            type="button"
            onClick={openCreate}
            className="inline-flex min-h-9 items-center gap-1.5 rounded-btn bg-accent px-3 text-xs font-medium text-white hover:bg-accent/90"
          >
            <Plus className="h-3.5 w-3.5" />添加持仓
          </button>
        )}
      />

      <div className="flex-1 space-y-4 overflow-auto px-4 py-4 sm:px-6 md:px-8 md:py-6">
        <div className="flex items-start gap-3 rounded-card border border-accent/20 bg-accent/[0.06] p-4 text-sm">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
          <div>
            <div className="font-medium text-foreground">这是当前账号的独立数据空间</div>
            <p className="mt-1 text-xs leading-relaxed text-secondary">
              持仓数量、成本和备注只属于当前用户；股票名称、收盘价和涨跌幅来自所有用户共用的市场数据库。
            </p>
          </div>
        </div>

        {portfolio.isError && (
          <div role="alert" className="flex items-center gap-2 rounded-btn bg-danger/10 px-3 py-2 text-xs text-danger">
            <AlertTriangle className="h-4 w-4" />{portfolio.error instanceof Error ? portfolio.error.message : '读取持仓失败'}
          </div>
        )}

        <PageContextModule id="summary"><div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          {cards.map(card => (
            <div key={card.label} className="rounded-card border border-border bg-surface p-3.5">
              <div className="text-xs text-muted">{card.label}</div>
              <div className={cn('mt-2 font-mono text-lg font-semibold text-foreground', pnlClass(card.pnl))}>{card.value}</div>
              <div className="mt-1 text-[10px] text-muted">{card.hint}</div>
            </div>
          ))}
        </div>

        </PageContextModule>
        <PageContextModule id="holdings"><section className="overflow-hidden rounded-card border border-border bg-surface">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <BriefcaseBusiness className="h-4 w-4 text-accent" />我的持仓
            </div>
            <span className="text-[10px] text-muted">已定价 {summary?.priced_count ?? 0}/{summary?.holding_count ?? 0}</span>
          </div>

          {portfolio.isLoading ? (
            <div className="grid min-h-56 place-items-center text-xs text-muted">
              <span><Loader2 className="mr-2 inline h-4 w-4 animate-spin" />读取个人持仓…</span>
            </div>
          ) : holdings.length === 0 ? (
            <div className="py-10">
              <EmptyState
                icon={WalletCards}
                title="还没有持仓记录"
                hint="添加股票代码、数量和平均成本后，系统会用共享行情计算最新市值与浮动盈亏。"
              />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[860px] text-left text-xs">
                <thead className="bg-base/50 text-muted">
                  <tr>
                    <th className="px-4 py-2.5 font-medium">股票</th>
                    <th className="px-3 py-2.5 text-right font-medium">数量</th>
                    <th className="px-3 py-2.5 text-right font-medium">平均成本</th>
                    <th className="px-3 py-2.5 text-right font-medium">最新价</th>
                    <th className="px-3 py-2.5 text-right font-medium">市值</th>
                    <th className="px-3 py-2.5 text-right font-medium">浮动盈亏</th>
                    <th className="px-3 py-2.5 font-medium">备注</th>
                    <th className="px-4 py-2.5 text-right font-medium">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {holdings.map(holding => (
                    <tr key={holding.symbol} className="hover:bg-elevated/40">
                      <td className="px-4 py-3">
                        <div className="font-medium text-foreground">{holding.name || holding.symbol}</div>
                        <div className="mt-0.5 font-mono text-[10px] text-muted">{holding.symbol}</div>
                      </td>
                      <td className="px-3 py-3 text-right font-mono text-secondary">{holding.quantity.toLocaleString('zh-CN')}</td>
                      <td className="px-3 py-3 text-right font-mono text-secondary">{money(holding.avg_cost)}</td>
                      <td className="px-3 py-3 text-right">
                        <div className="font-mono text-foreground">{money(holding.close)}</div>
                        <div className={cn('mt-0.5 font-mono text-[10px]', pnlClass(holding.change_pct))}>{percent(holding.change_pct)}</div>
                      </td>
                      <td className="px-3 py-3 text-right font-mono text-foreground">{money(holding.market_value)}</td>
                      <td className={cn('px-3 py-3 text-right font-mono', pnlClass(holding.pnl_amount))}>
                        <div>{money(holding.pnl_amount)}</div>
                        <div className="mt-0.5 text-[10px]">{percent(holding.pnl_pct)}</div>
                      </td>
                      <td className="max-w-[16rem] truncate px-3 py-3 text-secondary" title={holding.note}>{holding.note || '—'}</td>
                      <td className="px-4 py-3">
                        <div className="flex justify-end gap-1">
                          <button type="button" onClick={() => openEdit(holding)} aria-label={`编辑 ${holding.symbol}`} className="rounded p-1.5 text-muted hover:bg-accent/10 hover:text-accent">
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                          <button
                            type="button"
                            aria-label={`删除 ${holding.symbol}`}
                            disabled={remove.isPending}
                            onClick={() => { if (window.confirm(`删除 ${holding.symbol} 的持仓记录？`)) remove.mutate(holding.symbol) }}
                            className="rounded p-1.5 text-muted hover:bg-danger/10 hover:text-danger disabled:opacity-40"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section></PageContextModule>
      </div>

      {formOpen && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" onClick={event => { if (event.target === event.currentTarget) setFormOpen(false) }}>
          <div className="w-full max-w-md rounded-card border border-border bg-surface shadow-2xl">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <span className="text-sm font-medium text-foreground">{editingSymbol ? '编辑持仓' : '添加持仓'}</span>
              <button type="button" onClick={() => setFormOpen(false)} aria-label="关闭持仓编辑" className="rounded p-1 text-muted hover:bg-elevated"><X className="h-4 w-4" /></button>
            </div>
            <div className="space-y-3 p-4">
              <label className="block text-xs text-secondary">
                股票代码
                <input value={form.symbol} disabled={Boolean(editingSymbol)} onChange={event => setForm(current => ({ ...current, symbol: event.target.value.toUpperCase() }))} placeholder="600000.SH" className="mt-1.5 h-9 w-full rounded-input border border-border bg-base px-3 font-mono text-sm text-foreground outline-none focus:border-accent disabled:opacity-60" />
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="block text-xs text-secondary">
                  持仓数量
                  <input type="number" min="1" step="1" value={form.quantity} onChange={event => setForm(current => ({ ...current, quantity: event.target.value }))} placeholder="100" className="mt-1.5 h-9 w-full rounded-input border border-border bg-base px-3 text-sm text-foreground outline-none focus:border-accent" />
                </label>
                <label className="block text-xs text-secondary">
                  平均成本
                  <input type="number" min="0.000001" step="0.01" value={form.avgCost} onChange={event => setForm(current => ({ ...current, avgCost: event.target.value }))} placeholder="10.50" className="mt-1.5 h-9 w-full rounded-input border border-border bg-base px-3 text-sm text-foreground outline-none focus:border-accent" />
                </label>
              </div>
              <label className="block text-xs text-secondary">
                备注（可选）
                <textarea value={form.note} maxLength={240} rows={3} onChange={event => setForm(current => ({ ...current, note: event.target.value }))} placeholder="记录持仓理由或计划" className="mt-1.5 w-full resize-y rounded-input border border-border bg-base px-3 py-2 text-sm text-foreground outline-none focus:border-accent" />
              </label>
              {formError && <div role="alert" className="rounded-btn bg-danger/10 px-3 py-2 text-xs text-danger">{formError}</div>}
            </div>
            <div className="flex justify-end gap-2 border-t border-border px-4 py-3">
              <button type="button" onClick={() => setFormOpen(false)} className="h-9 rounded-btn border border-border px-3 text-xs text-secondary hover:text-foreground">取消</button>
              <button type="button" disabled={save.isPending} onClick={submit} className="inline-flex h-9 items-center gap-1.5 rounded-btn bg-accent px-4 text-xs font-medium text-white disabled:opacity-50">
                {save.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}{editingSymbol ? '保存修改' : '添加持仓'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
