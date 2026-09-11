import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
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
      { code: 'BK0001', name: '创新医疗服务', main_net: -1, change_pct: -3.4, as_of: '2026-08-21 13:29:41' },
    ],
    count: 2,
  } as never)
  vi.spyOn(api, 'fundFlowConceptsHistoryRefresh').mockResolvedValue({
    ok: true,
    kind: 'concept',
    ranking_count: 2,
    selected: 2,
    history_codes: ['BK1106'],
    history_points: 126,
    failed: [],
    source: 'eastmoney_daykline',
  } as never)
  vi.spyOn(api, 'fundFlowBoards').mockResolvedValue({ ok: true, items: [], count: 0 } as never)
  vi.spyOn(api, 'fundFlowBoardsWindow').mockResolvedValue({
    ok: true,
    kind: 'board',
    window_days: 5,
    window_complete: true,
    window_label: '近5个交易日累计',
    trading_days: 5,
    start: '2026-04-01',
    end: '2026-08-21',
    snapshot_count: 0,
    covered_count: 0,
    missing_count: 0,
    coverage_pct: 0,
    items: [],
    missing: [],
    prior_available: false,
    source: 'ext_fund_flow_bk_daily',
  } as never)
  vi.spyOn(api, 'fundFlowBoardsHistoryRefresh').mockResolvedValue({ ok: true } as never)
  vi.spyOn(api, 'fundFlowBoardsRefresh').mockResolvedValue({ ok: true, items: [], count: 0 } as never)
  vi.spyOn(api, 'fundFlowConceptsRefresh').mockResolvedValue({ ok: true, items: [], count: 0 } as never)
  vi.spyOn(api, 'fundFlowConceptsWindow').mockResolvedValue({
    ok: true,
    kind: 'concept',
    window_days: 5,
    requested_days: 5,
    window_complete: false,
    window_label: '近5个交易日累计',
    trading_days: 5,
    start: '2026-08-25',
    end: '2026-08-31',
    snapshot_count: 504,
    covered_count: 77,
    full_count: 41,
    missing_count: 427,
    coverage_pct: 15.3,
    items: [],
    missing: [],
    prior_available: false,
    window_note: '窗口数据不足',
    source: 'ext_fund_flow_concept_daily',
  } as never)
})

afterEach(() => {
  vi.restoreAllMocks()
})

it('lets the user pick a history window instead of a fixed 60-day backfill', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <SectorFundFlowPanel kind="concept" top={8} />
      </QueryClientProvider>
    </MemoryRouter>,
  )

  const trigger = await screen.findByRole('button', { name: /5 天/ })
  expect(trigger).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /近N日/ })).not.toBeInTheDocument()

  fireEvent.click(trigger)
  expect(screen.getByRole('menuitem', { name: '半个月' })).toBeInTheDocument()
  expect(screen.getByRole('menuitem', { name: '1 周' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('menuitem', { name: '半年' }))

  expect(await screen.findByText(/当日快照 · 半年窗口数据不足/)).toBeInTheDocument()
  expect(api.fundFlowConceptsHistoryRefresh).not.toHaveBeenCalled()
})

it('keeps incomplete concept windows on the daily snapshot', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <SectorFundFlowPanel kind="concept" top={8} />
      </QueryClientProvider>
    </MemoryRouter>,
  )

  expect(await screen.findByText(/当日快照 · 5 天窗口数据不足/)).toBeInTheDocument()
  expect(screen.getAllByText('通信技术').length).toBeGreaterThan(0)
  fireEvent.click(await screen.findByRole('button', { name: /5 天/ }))
  fireEvent.click(screen.getByRole('menuitem', { name: '1 个季度' }))
  expect(await screen.findByText(/当日快照 · 1 个季度窗口数据不足/)).toBeInTheDocument()
  expect(screen.getAllByText('通信技术').length).toBeGreaterThan(0)
  expect(api.fundFlowConceptsHistoryRefresh).not.toHaveBeenCalled()
})

it('ranks industry boards by selected window totals instead of the daily snapshot', async () => {
  vi.mocked(api.fundFlowBoards).mockResolvedValue({
    ok: true,
    items: [
      { code: 'BK0448', name: '通信设备', main_net: 7548600000, change_pct: 0.99, as_of: '2026-08-21 13:57:18' },
      { code: 'BK0459', name: '元件', main_net: 3726300000, change_pct: 0.98, as_of: '2026-08-21 13:57:18' },
    ],
    count: 2,
  } as never)
  vi.mocked(api.fundFlowBoardsWindow).mockResolvedValue({
    ok: true,
    kind: 'board',
    window_days: 5,
    window_label: '近5个交易日累计',
    trading_days: 5,
    start: '2026-04-01',
    end: '2026-08-21',
    snapshot_count: 128,
    covered_count: 72,
    missing_count: 56,
    coverage_pct: 56.3,
    window_complete: true,
    full_count: 72,
    items: [
      { code: 'BK0003', name: '窗口累计第一', main_net: 12_000_000_000, days: 63, window_days: 63 },
      { code: 'BK0004', name: '窗口累计流出', main_net: -8_000_000_000, days: 40, window_days: 63 },
    ],
    missing: [{ code: 'BK0005', name: '缺口行业', days: 0 }],
    prior_available: false,
    prior_note: '窗口外数据不足',
    source: 'ext_fund_flow_bk_daily',
  } as never)

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <SectorFundFlowPanel kind="board" top={8} />
      </QueryClientProvider>
    </MemoryRouter>,
  )

  expect(await screen.findByText('近5个交易日累计 · 行业日线窗口排名')).toBeInTheDocument()
  expect(await screen.findByText(/覆盖 72\/128 只行业日线/)).toBeInTheDocument()
  expect(screen.getByText(/满窗 72\/128/)).toBeInTheDocument()
  expect(screen.getAllByText('窗口累计第一').length).toBeGreaterThan(0)
  expect(screen.queryByText('通信设备')).not.toBeInTheDocument()
  expect(screen.getByText(/覆盖 72\/128 只行业日线/)).toBeInTheDocument()
})

it('keeps incomplete quarter and year industry ranks on the daily snapshot', async () => {
  vi.mocked(api.fundFlowBoards).mockResolvedValue({
    ok: true,
    items: [
      { code: 'BK0448', name: '通信设备', main_net: 7548600000, change_pct: 0.99, as_of: '2026-08-21 13:57:18' },
      { code: 'BK0475', name: '化学制药', main_net: -3204000000, change_pct: -1.1, as_of: '2026-08-21 13:57:18' },
    ],
    count: 2,
  } as never)
  vi.mocked(api.fundFlowBoardsWindow).mockResolvedValue({
    ok: true,
    kind: 'board',
    window_days: 63,
    requested_days: 63,
    window_complete: false,
    window_label: '近63个交易日累计',
    trading_days: 63,
    start: '2026-04-01',
    end: '2026-08-21',
    snapshot_count: 128,
    covered_count: 72,
    missing_count: 56,
    coverage_pct: 56.3,
    items: [{ code: 'BK0428', name: '电力', main_net: 21703000000, days: 63, window_days: 63 }],
    missing: [],
    prior_available: false,
    window_note: '窗口数据不足',
    source: 'ext_fund_flow_bk_daily',
  } as never)

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <SectorFundFlowPanel kind="board" top={8} />
      </QueryClientProvider>
    </MemoryRouter>,
  )

  fireEvent.click(await screen.findByRole('button', { name: /5 天/ }))
  fireEvent.click(screen.getByRole('menuitem', { name: '1 个季度' }))
  expect(await screen.findByText(/当日快照 · 1 个季度窗口数据不足/)).toBeInTheDocument()
  expect(screen.getAllByText('通信设备').length).toBeGreaterThan(0)
  expect(screen.queryByText('电力')).not.toBeInTheDocument()

  fireEvent.click(await screen.findByRole('button', { name: /1 个季度/ }))
  fireEvent.click(screen.getByRole('menuitem', { name: '1 年' }))
  expect(await screen.findByText(/当日快照 · 1 年窗口数据不足/)).toBeInTheDocument()
})

it('opens a complete industry quarter window instead of the daily snapshot', async () => {
  vi.mocked(api.fundFlowBoards).mockResolvedValue({
    ok: true,
    items: [
      { code: 'BK0448', name: '通信设备', main_net: 7548600000, change_pct: 0.99, as_of: '2026-08-21 13:57:18' },
      { code: 'BK0475', name: '化学制药', main_net: -3204000000, change_pct: -1.1, as_of: '2026-08-21 13:57:18' },
    ],
    count: 2,
  } as never)
  vi.mocked(api.fundFlowBoardsWindow).mockImplementation(async (days?: number) => {
    if ((days ?? 0) >= 63) {
      return {
        ok: true,
        kind: 'board',
        window_days: 63,
        requested_days: 63,
        window_complete: true,
        window_label: '近63个交易日累计',
        trading_days: 63,
        start: '2026-05-27',
        end: '2026-08-26',
        snapshot_count: 128,
        covered_count: 128,
        full_count: 128,
        missing_count: 0,
        coverage_pct: 100,
        items: [{ code: 'BK0428', name: '电力', main_net: 21703000000, days: 63, window_days: 63 }],
        missing: [],
        prior_available: true,
        source: 'ext_fund_flow_bk_daily',
      } as never
    }
    return {
      ok: true,
      kind: 'board',
      window_days: 5,
      window_complete: true,
      window_label: '近5个交易日累计',
      trading_days: 5,
      start: '2026-08-20',
      end: '2026-08-26',
      snapshot_count: 128,
      covered_count: 128,
      full_count: 128,
      missing_count: 0,
      coverage_pct: 100,
      items: [{ code: 'BK0003', name: '窗口累计第一', main_net: 12_000_000_000, days: 5, window_days: 5 }],
      missing: [],
      prior_available: true,
      source: 'ext_fund_flow_bk_daily',
    } as never
  })

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <SectorFundFlowPanel kind="board" top={8} />
      </QueryClientProvider>
    </MemoryRouter>,
  )

  fireEvent.click(await screen.findByRole('button', { name: /5 天/ }))
  fireEvent.click(screen.getByRole('menuitem', { name: '1 个季度' }))
  expect(await screen.findByText('近63个交易日累计 · 行业日线窗口排名')).toBeInTheDocument()
  expect(await screen.findByText(/满窗 128\/128/)).toBeInTheDocument()
  expect(screen.getAllByText('电力').length).toBeGreaterThan(0)
  expect(screen.queryByText('通信设备')).not.toBeInTheDocument()
})

it('fills the industry inflow column to top N even when few boards are net-positive', async () => {
  vi.mocked(api.fundFlowBoardsWindow).mockResolvedValue({
    ok: true,
    kind: 'board',
    window_days: 63,
    requested_days: 63,
    window_complete: true,
    window_label: '近63个交易日累计',
    trading_days: 63,
    start: '2026-06-02',
    end: '2026-08-26',
    snapshot_count: 128,
    covered_count: 128,
    full_count: 128,
    missing_count: 0,
    coverage_pct: 100,
    items: [
      { code: 'BK0732', name: '贵金属', main_net: 1_841_000_000, days: 63, window_days: 63 },
      { code: 'BK1249', name: '焦炭Ⅱ', main_net: 41_270_000, days: 63, window_days: 63 },
      { code: 'BK0006', name: '累计第三', main_net: -10_000_000, days: 63, window_days: 63 },
      { code: 'BK0007', name: '累计第四', main_net: -20_000_000, days: 63, window_days: 63 },
      { code: 'BK0008', name: '累计第五', main_net: -30_000_000, days: 63, window_days: 63 },
      { code: 'BK0009', name: '累计第六', main_net: -40_000_000, days: 63, window_days: 63 },
      { code: 'BK1036', name: '半导体', main_net: -340_871_000_000, days: 63, window_days: 63 },
    ],
    missing: [],
    prior_available: true,
    source: 'ext_fund_flow_bk_daily',
  } as never)

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <SectorFundFlowPanel kind="board" top={6} />
      </QueryClientProvider>
    </MemoryRouter>,
  )

  fireEvent.click(await screen.findByRole('button', { name: /5 天/ }))
  fireEvent.click(screen.getByRole('menuitem', { name: '1 个季度' }))
  expect(await screen.findByText('累计第六')).toBeInTheDocument()
  expect(screen.getByText('累计第三')).toBeInTheDocument()
  expect(screen.getAllByText('贵金属').length).toBeGreaterThan(0)
  expect(screen.getAllByText('半导体').length).toBeGreaterThan(0)
})

it('opens a complete concept quarter window instead of the daily snapshot', async () => {
  vi.mocked(api.fundFlowConceptsWindow).mockImplementation(async (days?: number) => {
    if ((days ?? 0) >= 63) {
      return {
        ok: true,
        kind: 'concept',
        window_days: 63,
        requested_days: 63,
        window_complete: true,
        window_label: '近63个交易日累计',
        trading_days: 63,
        start: '2026-06-02',
        end: '2026-08-28',
        snapshot_count: 504,
        covered_count: 504,
        full_count: 504,
        missing_count: 0,
        coverage_pct: 100,
        items: [{ code: 'BK1009', name: '窗口概念第一', main_net: 9_000_000_000, days: 63, window_days: 63 }],
        missing: [],
        prior_available: true,
        source: 'ext_fund_flow_concept_daily',
      } as never
    }
    return {
      ok: true,
      kind: 'concept',
      window_days: 5,
      window_complete: true,
      window_label: '近5个交易日累计',
      trading_days: 5,
      start: '2026-08-25',
      end: '2026-08-28',
      snapshot_count: 504,
      covered_count: 504,
      full_count: 504,
      missing_count: 0,
      coverage_pct: 100,
      items: [{ code: 'BK1111', name: '五日概念累计', main_net: 1_000_000_000, days: 5, window_days: 5 }],
      missing: [],
      prior_available: true,
      source: 'ext_fund_flow_concept_daily',
    } as never
  })

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <SectorFundFlowPanel kind="concept" top={8} />
      </QueryClientProvider>
    </MemoryRouter>,
  )

  expect(await screen.findByText('近5个交易日累计 · 概念日线窗口排名')).toBeInTheDocument()
  fireEvent.click(await screen.findByRole('button', { name: /5 天/ }))
  fireEvent.click(screen.getByRole('menuitem', { name: '1 个季度' }))
  expect(await screen.findByText('近63个交易日累计 · 概念日线窗口排名')).toBeInTheDocument()
  expect(await screen.findByText(/满窗 504\/504/)).toBeInTheDocument()
  expect(screen.getAllByText('窗口概念第一').length).toBeGreaterThan(0)
  expect(screen.queryByText('通信技术')).not.toBeInTheDocument()
})

