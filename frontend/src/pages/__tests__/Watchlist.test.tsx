import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { api } from '@/lib/api'
import { BUILTIN_COLUMNS } from '@/lib/watchlist-columns'
import { Watchlist } from '@/pages/Watchlist'


function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <Watchlist />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}


beforeEach(() => {
  localStorage.clear()
  vi.spyOn(api, 'watchlistList').mockResolvedValue({
    symbols: [
      { symbol: '300502.SZ', name: '新易盛', note: '', added_at: '' },
      { symbol: '301526.SZ', name: '国际复材', note: '', added_at: '' },
      { symbol: '300204.SZ', name: '舒泰神', note: '', added_at: '' },
    ],
  })
  vi.spyOn(api, 'watchlistGroups').mockResolvedValue({ groups: [] })
  vi.spyOn(api, 'watchlistEnriched').mockResolvedValue({
    as_of: '2026-08-03',
    elapsed_ms: 1,
    rows: [
      { symbol: '300502.SZ', name: '新易盛', close: null },
      { symbol: '301526.SZ', name: '国际复材', close: 28.88, change_pct: 0.2 },
      { symbol: '300204.SZ', name: '舒泰神', close: null },
    ],
  })
  vi.spyOn(api, 'watchlistColumns').mockResolvedValue({ columns: null })
  vi.spyOn(api, 'quoteStatus').mockResolvedValue({
    running: false,
    mode: 'none',
    watchlist_symbol_count: 0,
  } as Awaited<ReturnType<typeof api.quoteStatus>>)
  vi.spyOn(api, 'klineDailyBatch').mockResolvedValue({ data: {} })
  vi.spyOn(api, 'instrumentSearch').mockImplementation(async (query) => ({
    results: query === '国际复材'
      ? [{ symbol: '301526.SZ', name: '国际复材', code: '301526' }]
      : [],
  }))
})


afterEach(() => {
  localStorage.clear()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})


it('shows the complete watchlist and labels missing enrichment as pending data', async () => {
  renderPage()

  expect(await screen.findByText('新易盛')).toBeInTheDocument()
  expect(screen.getByText('国际复材')).toBeInTheDocument()
  expect(screen.getByText('舒泰神')).toBeInTheDocument()
  expect(screen.getByText('自选股')).toBeInTheDocument()
  expect(screen.getByText('只').parentElement).toHaveTextContent('3')
  expect(screen.getByText('待数据 2')).toBeInTheDocument()
  expect(screen.queryByText(/已过滤/)).not.toBeInTheDocument()
})


it('shows realtime snapshot values and still counts null close as pending', async () => {
  vi.mocked(api.watchlistColumns).mockResolvedValue({
    columns: BUILTIN_COLUMNS.map(column => (
      column.id === 'builtin:change_amount'
        ? { ...column, visible: true }
        : column
    )),
  })
  vi.mocked(api.watchlistEnriched).mockResolvedValue({
    as_of: '2026-08-03',
    realtime_as_of: '2026-08-04T11:39:42+08:00',
    realtime_count: 1,
    elapsed_ms: 1,
    rows: [
      {
        symbol: '300502.SZ',
        name: '新易盛',
        close: null,
        change_amount: -4.11,
        rt_price: 440.88,
        rt_pct: 0.11875761,
        rt_change_amount: 52.10,
        rt_amount: 20_331_840_000,
      },
      { symbol: '301526.SZ', name: '国际复材', close: 28.88, change_pct: 0.2 },
      { symbol: '300204.SZ', name: '舒泰神', close: null },
    ],
  })

  renderPage()

  expect(await screen.findByText('440.88')).toBeInTheDocument()
  expect(screen.getByText('+11.88%')).toBeInTheDocument()
  // Local still renders the enriched change_amount cell; it does not hide it for rt_*.
  expect(screen.getByText('-4.11')).toBeInTheDocument()
  expect(screen.getByText('待数据 2')).toBeInTheDocument()
  expect(screen.queryByText('实时 1')).not.toBeInTheDocument()
})


it('searches the instrument catalog by Chinese stock name', async () => {
  renderPage()

  const input = screen.getByPlaceholderText('搜索…')
  fireEvent.change(input, { target: { value: '国际复材' } })

  await waitFor(() => expect(api.instrumentSearch).toHaveBeenCalledWith('国际复材', 20, 'stock,etf,index'))
  expect(screen.getAllByRole('button', { name: /301526\.SZ\s+国际复材/ }).length).toBeGreaterThan(0)
})

it('switches to card view from the toolbar instead of auto-matching a phone viewport', async () => {
  renderPage()

  expect(await screen.findByText('新易盛')).toBeInTheDocument()
  expect(screen.getByRole('table')).toBeInTheDocument()

  fireEvent.click(screen.getByTitle('卡片视图'))

  await waitFor(() => {
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
  expect(screen.getByText('新易盛')).toBeInTheDocument()
  expect(screen.queryByTestId('watchlist-mobile-cards')).not.toBeInTheDocument()
})
