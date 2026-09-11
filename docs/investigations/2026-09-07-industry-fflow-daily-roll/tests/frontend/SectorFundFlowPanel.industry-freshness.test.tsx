import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { api } from '@/lib/api'
import { SectorFundFlowPanel } from '@/components/SectorFundFlowPanel'

vi.mock('@/lib/useSharedQueries', () => ({
  useSettings: () => ({ data: { is_admin: true } }),
}))

beforeEach(() => {
  vi.spyOn(api, 'fundFlowConcepts').mockResolvedValue({
    ok: true,
    items: [
      { code: 'BK1106', name: '通信技术', main_net: 1, change_pct: 0.8, as_of: '2026-08-21 13:29:41' },
    ],
    count: 1,
  } as never)
  vi.spyOn(api, 'fundFlowConceptsWindow').mockResolvedValue({
    ok: true,
    kind: 'concept',
    window_days: 5,
    window_complete: true,
    window_label: '近5个交易日累计',
    trading_days: 5,
    start: '2026-08-25',
    end: '2026-08-31',
    snapshot_count: 504,
    covered_count: 504,
    full_count: 504,
    missing_count: 0,
    coverage_pct: 100,
    items: [{ code: 'BK1111', name: '五日概念累计', main_net: 1_000_000_000, days: 5, window_days: 5 }],
    missing: [],
    prior_available: true,
    source: 'ext_fund_flow_concept_daily',
    data_as_of: '2026-08-31',
    freshness_status: 'stale',
    freshness_note: '已陈旧',
  } as never)
  vi.spyOn(api, 'fundFlowConceptsHistoryRefresh').mockResolvedValue({ ok: true } as never)
  vi.spyOn(api, 'fundFlowConceptsRefresh').mockResolvedValue({ ok: true, items: [], count: 0 } as never)
  vi.spyOn(api, 'fundFlowBoards').mockResolvedValue({ ok: true, items: [], count: 0 } as never)
  vi.spyOn(api, 'fundFlowBoardsHistoryRefresh').mockResolvedValue({ ok: true } as never)
  vi.spyOn(api, 'fundFlowBoardsRefresh').mockResolvedValue({ ok: true, items: [], count: 0 } as never)
  vi.spyOn(api, 'fundFlowBoardsWindow').mockResolvedValue({
    ok: true,
    kind: 'board',
    window_days: 5,
    window_complete: true,
    window_label: '近5个交易日累计',
    trading_days: 5,
    start: '2026-08-25',
    end: '2026-08-31',
    snapshot_count: 128,
    covered_count: 128,
    full_count: 128,
    missing_count: 0,
    coverage_pct: 100,
    items: [{ code: 'BK0459', name: '元件', main_net: 1, days: 5, window_days: 5 }],
    missing: [],
    prior_available: true,
    source: 'ext_fund_flow_bk_daily',
  } as never)
})

afterEach(() => {
  vi.restoreAllMocks()
})

it('shows industry cutoff and unknown freshness without using kline as calendar', async () => {
  vi.mocked(api.fundFlowBoardsWindow).mockResolvedValue({
    ok: true,
    kind: 'board',
    window_days: 5,
    window_complete: true,
    window_label: '近5个交易日累计',
    trading_days: 5,
    start: '2026-08-25',
    end: '2026-08-31',
    snapshot_count: 128,
    covered_count: 128,
    full_count: 128,
    missing_count: 0,
    coverage_pct: 100,
    items: [{ code: 'BK0459', name: '元件', main_net: 1, days: 5, window_days: 5 }],
    missing: [],
    prior_available: true,
    source: 'ext_fund_flow_bk_daily',
    data_as_of: '2026-08-31',
    freshness_status: 'unknown',
    freshness_note: '无法确定（交易日历未覆盖到当日）',
    expected_trading_day: null,
    calendar_covers: false,
  } as never)

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <SectorFundFlowPanel kind="board" top={6} />
      </QueryClientProvider>
    </MemoryRouter>,
  )

  expect(await screen.findByText('数据截止 2026-08-31 · 无法确定 · 窗口完整')).toBeInTheDocument()
  expect(screen.queryByText(/2026-09-07/)).not.toBeInTheDocument()
})

it('keeps complete-window and stale-freshness as two judgments', async () => {
  vi.mocked(api.fundFlowBoardsWindow).mockResolvedValue({
    ok: true,
    kind: 'board',
    window_days: 63,
    window_complete: true,
    window_label: '近63个交易日累计',
    trading_days: 63,
    start: '2026-06-03',
    end: '2026-08-31',
    snapshot_count: 128,
    covered_count: 128,
    full_count: 128,
    missing_count: 0,
    coverage_pct: 100,
    items: [{ code: 'BK1033', name: '种植业', main_net: 1, days: 63, window_days: 63 }],
    missing: [],
    prior_available: true,
    source: 'ext_fund_flow_bk_daily',
    data_as_of: '2026-08-31',
    freshness_status: 'stale',
    freshness_note: '已陈旧',
    expected_trading_day: '2026-09-07',
    calendar_covers: true,
  } as never)

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <SectorFundFlowPanel kind="board" top={6} />
      </QueryClientProvider>
    </MemoryRouter>,
  )

  expect(await screen.findByText('数据截止 2026-08-31 · 已陈旧 · 窗口完整')).toBeInTheDocument()
  expect(screen.getByText(/满窗 128\/128/)).toBeInTheDocument()
})

it('does not show industry freshness copy on the concept panel', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <SectorFundFlowPanel kind="concept" top={8} />
      </QueryClientProvider>
    </MemoryRouter>,
  )

  expect(await screen.findByText('近5个交易日累计 · 概念日线窗口排名')).toBeInTheDocument()
  expect(screen.queryByText(/数据截止/)).not.toBeInTheDocument()
  expect(screen.queryByText(/无法确定/)).not.toBeInTheDocument()
  expect(screen.queryByText(/足够新/)).not.toBeInTheDocument()
  expect(screen.queryByText(/已陈旧/)).not.toBeInTheDocument()
})
