import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { api } from '@/lib/api'
import { Review } from '@/pages/Review'


beforeEach(() => {
  vi.spyOn(api, 'overviewMarket').mockResolvedValue({
    as_of: '2026-08-03',
    quote_status: {},
    indices: [],
    breadth: { total: 0, up: 0, down: 0, flat: 0, up_pct: 0, down_pct: 0 },
    amount: { total: 0, avg: 0 },
    boards: [],
    limit: { limit_up: 0, broken: 0, failed: 0, limit_down: 0, max_boards: 0, tiers: [] },
    distribution: [],
    trend: { above_ma5: 0, above_ma20: 0, above_ma60: 0, above_ma5_pct: 0, above_ma20_pct: 0, above_ma60_pct: 0, new_high: 0, new_low: 0 },
    activity: { avg_turnover: 0, high_turnover: 0, high_vol_ratio: 0, vol_ratio: 0 },
    radar: [],
    emotion: { score: 50, label: '中性' },
    top_gainers: [],
    top_losers: [],
    turnover_leaders: [],
    active_leaders: [],
    concept_rank: { leading: [], lagging: [] },
    industry_rank: { leading: [], lagging: [] },
  })
  vi.spyOn(api, 'reviewReportsList').mockResolvedValue({ reports: [] })
  vi.spyOn(api, 'marketPulse').mockResolvedValue({
    available: false,
    requested_date: '2026-08-03',
    resolved_date: '2026-08-03',
    updated_at: null,
    benchmark: { symbol: '000001.SH', name: '上证指数' },
    points: [],
    events: [],
    minute_rows: 0,
    event_rows: 0,
    source: 'local',
    producer: 'cls',
    unit_version: 'market_pulse_v1',
  })
  vi.spyOn(api, 'preferences').mockResolvedValue({} as Awaited<ReturnType<typeof api.preferences>>)
})


afterEach(() => {
  vi.restoreAllMocks()
})


it('keeps AI review focus as a blank local input when a stock is only in the query string', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter
      initialEntries={['/review?symbol=300502.SZ&name=%E6%96%B0%E6%98%93%E7%9B%9B']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <QueryClientProvider client={client}>
        <Review />
      </QueryClientProvider>
    </MemoryRouter>,
  )

  expect(await screen.findByText('AI 复盘')).toBeInTheDocument()
  expect(screen.queryByLabelText('复盘关注股票')).not.toBeInTheDocument()
  const focus = await screen.findByPlaceholderText(/补充复盘关注点/)
  expect(focus).toHaveValue('')
})
