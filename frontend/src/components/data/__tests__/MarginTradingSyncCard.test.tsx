import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { MarginTradingSyncCard } from '../MarginTradingSyncCard'
import { api } from '@/lib/api'

function renderCard(onTraceSource = vi.fn()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <MarginTradingSyncCard onTraceSource={onTraceSource} />
    </QueryClientProvider>,
  )
  return { client, onTraceSource }
}

afterEach(() => {
  vi.restoreAllMocks()
})

it('syncs normalized symbols and reports the published local rows', async () => {
  const sync = vi.spyOn(api, 'syncMarginTrading').mockResolvedValue({
    symbols_requested: 2,
    symbols_with_data: 1,
    empty_symbols: ['000001.SZ'],
    rows_fetched: 50,
    rows_published: 50,
    latest_trade_date: '2026-08-04',
    artifact_path: 'f10/stock_margin_trading/part.parquet',
    lineage_path: 'lineage/stock_margin_trading/date=2026-08-04/run.json',
    catalog_refreshed: true,
  })
  renderCard()

  fireEvent.change(screen.getByLabelText('融资融券股票代码'), {
    target: { value: '600519.SH, 000001.SZ' },
  })
  fireEvent.click(screen.getByRole('button', { name: '同步融资融券' }))

  await waitFor(() => {
    expect(sync).toHaveBeenCalledWith(['600519.SH', '000001.SZ'], 250)
  })
  expect(await screen.findByText(/已写入 50 行/)).toBeInTheDocument()
  expect(screen.getByText(/无数据：000001.SZ/)).toBeInTheDocument()
})

it('opens the truthful source trace instead of presenting go-stock as producer', () => {
  const { onTraceSource } = renderCard()

  fireEvent.click(screen.getByRole('button', { name: '查看融资融券来源' }))

  expect(onTraceSource).toHaveBeenCalledWith('stock_margin_trading')
  expect(screen.getByText(/东方财富单源/)).toBeInTheDocument()
  expect(screen.getByText(/go-stock 仅作为接口情报/)).toBeInTheDocument()
})
