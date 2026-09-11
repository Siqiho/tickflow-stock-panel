import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { api } from '@/lib/api'
import { Trading } from '@/pages/Trading'


afterEach(() => vi.restoreAllMocks())


it('shows the isolated portfolio ledger and saves a holding to the current account', async () => {
  vi.spyOn(api, 'portfolioSnapshot').mockResolvedValue({
    as_of: '2026-08-11',
    summary: {
      holding_count: 1,
      priced_count: 1,
      total_cost: 1000,
      total_market_value: 1200,
      total_pnl: 200,
      total_pnl_pct: 0.2,
    },
    holdings: [{
      symbol: '600000.SH',
      name: '浦发银行',
      quantity: 100,
      avg_cost: 10,
      note: '独立持仓',
      close: 12,
      change_pct: 0.01,
      cost_value: 1000,
      market_value: 1200,
      pnl_amount: 200,
      pnl_pct: 0.2,
      created_at: '2026-08-11T00:00:00+00:00',
      updated_at: '2026-08-11T00:00:00+00:00',
    }],
  })
  const save = vi.spyOn(api, 'portfolioSaveHolding').mockResolvedValue({
    ok: true,
    holding: {} as never,
  })
  vi.spyOn(api, 'portfolioDeleteHolding').mockResolvedValue({ ok: true })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

  render(
    <QueryClientProvider client={client}>
      <Trading />
    </QueryClientProvider>,
  )

  expect(await screen.findByText('浦发银行')).toBeInTheDocument()
  expect(screen.getByText('这是当前账号的独立数据空间')).toBeInTheDocument()
  expect(screen.getByText(/来自所有用户共用的市场数据库/)).toBeInTheDocument()

  fireEvent.click(screen.getAllByRole('button', { name: '添加持仓' }).at(-1)!)
  fireEvent.change(screen.getByLabelText('股票代码'), { target: { value: '000001.SZ' } })
  fireEvent.change(screen.getByLabelText('持仓数量'), { target: { value: '200' } })
  fireEvent.change(screen.getByLabelText('平均成本'), { target: { value: '11.5' } })
  fireEvent.change(screen.getByLabelText('备注（可选）'), { target: { value: '用户自己的记录' } })
  fireEvent.click(screen.getAllByRole('button', { name: '添加持仓' }).at(-1)!)

  await waitFor(() => expect(save).toHaveBeenCalledWith({
    symbol: '000001.SZ',
    quantity: 200,
    avg_cost: 11.5,
    note: '用户自己的记录',
  }))
})
