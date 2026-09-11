import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { api } from '@/lib/api'
import { dashboardFeedStatus, formatDashboardFeedClock, invalidateDashboardModules, isLiveSnapshotQueryKey, liveOverviewRefetchMs, shanghaiIsTradingHours } from '@/lib/dashboardFeed'
import { quoteTickActivePrefixes } from '@/lib/queryKeys'
import { Dashboard } from '@/pages/Dashboard'

vi.mock('@/lib/useSharedQueries', () => ({
  useDataStatus: () => ({
    data: {
      daily: null,
      enriched: null,
      storage: { total_size_mb: 0 },
    },
  }),
  useCapabilities: () => ({ data: { capabilities: {}, features: {} } }),
  useSettings: () => ({
    data: {
      is_admin: false,
      mode: 'none',
      onboarding_completed: true,
    },
  }),
}))

vi.mock('@/components/SectorFundFlowPanel', () => ({
  SectorFundFlowPanel: ({ readOnly }: { readOnly?: boolean }) => (
    <div data-testid="sector-fund-flow" data-read-only={String(readOnly)} />
  ),
}))

const overviewFixture = {
  as_of: null,
  quote_status: { enabled: false, running: false, mode: 'full_market' },
  indices: [],
  breadth: { total: 0, up: 0, down: 0, flat: 0, up_pct: 0, down_pct: 0, strong_up: 0, strong_down: 0 },
  amount: { total: 0, avg: 0 },
  boards: [],
  limit: { limit_up: 0, broken: 0, failed: 0, limit_down: 0, max_boards: 0, seal_rate: null, tiers: [], ready: true },
  activity: { avg_turnover: 0, high_turnover: 0, high_vol_ratio: null, vol_ratio: null, vol_ready: false },
  emotion: { score: 50, label: '暂无' },
  distribution: [],
  radar: [],
  trend: { above_ma5: 0, above_ma5_pct: 0, above_ma20: 0, above_ma20_pct: 0, above_ma60: 0, above_ma60_pct: 0, new_high: 0, new_low: 0, ready: true, extremes_ready: true },
  concept_rank: { leading: [], lagging: [] },
  industry_rank: { leading: [], lagging: [] },
  top_gainers: [],
  top_losers: [],
  turnover_leaders: [],
  active_leaders: [],
}

beforeEach(() => {
  vi.spyOn(api, 'overviewMarket').mockResolvedValue(overviewFixture as never)
  vi.spyOn(api, 'pipelineJobs').mockResolvedValue({ active_id: null, jobs: [] })
  vi.spyOn(api, 'alertsList').mockResolvedValue({ alerts: [], total: 0 })
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
  sessionStorage.clear()
})

it('treats a past board date as historical even if the live poller is running', () => {
  expect(dashboardFeedStatus({
    viewedDate: '2026-08-25',
    today: '2026-08-26',
    dataMode: 'official',
    quoteRunning: true,
    isTradingHours: true,
  })).toEqual({ live: false, label: '历史', showAge: false })
})

it('shows live only for today while the intraday snapshot can still update', () => {
  expect(dashboardFeedStatus({
    viewedDate: '2026-08-26',
    today: '2026-08-26',
    dataMode: 'intraday_snapshot',
    quoteRunning: true,
    isTradingHours: true,
  })).toEqual({ live: true, label: '实时', showAge: true })
  expect(dashboardFeedStatus({
    viewedDate: '2026-08-26',
    today: '2026-08-26',
    dataMode: 'official',
    quoteRunning: true,
    isTradingHours: true,
  })).toEqual({ live: false, label: '非实时', showAge: false })
})

it('uses Shanghai session hours so lunch stays 非实时 and afternoon can return to 实时', () => {
  expect(shanghaiIsTradingHours(new Date('2026-08-27T03:52:00.000Z'))).toBe(false)
  expect(shanghaiIsTradingHours(new Date('2026-08-27T05:00:00.000Z'))).toBe(true)
  expect(shanghaiIsTradingHours(new Date('2026-08-27T07:10:00.000Z'))).toBe(false)
  expect(dashboardFeedStatus({
    viewedDate: '2026-08-27',
    today: '2026-08-27',
    dataMode: 'intraday_snapshot',
    quoteRunning: true,
    isTradingHours: true,
    now: new Date('2026-08-27T03:52:00.000Z'),
  })).toEqual({ live: false, label: '非实时', showAge: false })
  expect(dashboardFeedStatus({
    viewedDate: '2026-08-27',
    today: '2026-08-27',
    dataMode: 'intraday_snapshot',
    quoteRunning: true,
    isTradingHours: false,
    now: new Date('2026-08-27T05:00:00.000Z'),
  })).toEqual({ live: true, label: '实时', showAge: true })
})

it('keeps the live overview on the quote clock even if page SSE toggles are off', () => {
  expect(quoteTickActivePrefixes({ watchlist: true, 'limit-ladder': false, 'overview-market': false })).toEqual([
    'watchlist',
    'quote-status',
    'index-quotes',
    'overview-market',
    'screener',
  ])
  expect(liveOverviewRefetchMs({ live: true, intervalS: 15 })).toBe(15_000)
  expect(liveOverviewRefetchMs({ live: true, intervalS: 8 })).toBe(8_000)
  expect(liveOverviewRefetchMs({ live: false, intervalS: 15 })).toBe(false)
})

it('formats the live board clock as one snapshot interval plus age', () => {
  expect(formatDashboardFeedClock({
    live: true,
    showAge: true,
    intervalS: 15,
    ageMs: 8000,
  })).toBe('每 15 秒 · 已过 8s')
  expect(formatDashboardFeedClock({
    live: false,
    showAge: false,
    intervalS: 15,
    ageMs: 23000,
  })).toBe('—')
  expect(isLiveSnapshotQueryKey(['overview-market', 'latest'], '2026-08-26')).toBe(true)
  expect(isLiveSnapshotQueryKey(['overview-market', '2026-08-26'], '2026-08-26')).toBe(true)
  expect(isLiveSnapshotQueryKey(['overview-market', '2026-08-25'], '2026-08-26')).toBe(false)
})

it('does not show a live quote age when the board is on a historical day', async () => {
  vi.mocked(api.overviewMarket).mockResolvedValue({
    ...overviewFixture,
    as_of: '2026-08-25',
    data_mode: 'official',
    quote_status: { enabled: true, running: true, is_trading_hours: true, quote_age_ms: 23000, mode: 'full_market' },
  } as never)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter initialEntries={['/?as_of=2026-08-25']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <Dashboard />
      </QueryClientProvider>
    </MemoryRouter>,
  )

  expect(await screen.findByRole('heading', { name: '市场看板' })).toBeInTheDocument()
  expect(screen.getByText('历史')).toBeInTheDocument()
  expect(screen.queryByText('实时')).not.toBeInTheDocument()
  expect(screen.queryByText('23s')).not.toBeInTheDocument()
  expect(screen.queryByText(/每 15 秒/)).not.toBeInTheDocument()
})

it('shows the shared snapshot clock when today is still updating', async () => {
  vi.mocked(api.overviewMarket).mockResolvedValue({
    ...overviewFixture,
    as_of: '2026-08-26',
    data_mode: 'intraday_snapshot',
    quote_status: { enabled: true, running: true, is_trading_hours: true, quote_age_ms: 8000, interval_s: 15, mode: 'full_market' },
  } as never)
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.setSystemTime(new Date('2026-08-26T06:36:00.000Z'))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <Dashboard />
      </QueryClientProvider>
    </MemoryRouter>,
  )

  expect(await screen.findByText('每 15 秒 · 已过 8s')).toBeInTheDocument()
  expect(screen.getByText('实时')).toBeInTheDocument()
  vi.useRealTimers()
})

it('keeps server data controls and admin alerts out of the ordinary-user dashboard', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <Dashboard />
      </QueryClientProvider>
    </MemoryRouter>,
  )

  expect(await screen.findByRole('heading', { name: '市场看板' })).toBeInTheDocument()
  expect(screen.queryByText('监控中心')).not.toBeInTheDocument()
  expect(screen.queryByText(/获取行情数据/)).not.toBeInTheDocument()
  expect(screen.getByTestId('sector-fund-flow')).toHaveAttribute('data-read-only', 'true')
  await waitFor(() => {
    expect(api.pipelineJobs).not.toHaveBeenCalled()
    expect(api.alertsList).not.toHaveBeenCalled()
  })
})

it('keeps the limit-up KPI visible when the sealed correction popover opens', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <Dashboard />
      </QueryClientProvider>
    </MemoryRouter>,
  )

  expect(await screen.findByText('涨停 / 跌停')).toBeInTheDocument()
  expect(screen.getByText('封板率 —')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '查看真假涨停判定降级说明' }))
  expect(screen.getByRole('dialog', { name: '真假涨停判定降级' })).toBeInTheDocument()
  expect(screen.getByText('涨停 / 跌停')).toBeInTheDocument()
  expect(screen.getByText('封板率 —')).toBeInTheDocument()
})

it('labels same-day HiThink official pool on limit KPIs', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.setSystemTime(new Date('2026-08-26T06:36:00.000Z'))
  vi.mocked(api.overviewMarket).mockResolvedValue({
    ...overviewFixture,
    as_of: '2026-08-26',
    data_mode: 'intraday_snapshot',
    indicators_source: 'intraday_approx',
    indicators_approx: true,
    limit: {
      ...overviewFixture.limit,
      limit_up: 12,
      limit_down: 1,
      broken: 4,
      max_boards: 5,
      seal_rate: 75,
      ready: true,
      source: 'hithink_official_pool',
      source_as_of: '2026-08-26',
      tiers: [{ boards: 5, count: 1 }],
    },
  } as never)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <Dashboard />
      </QueryClientProvider>
    </MemoryRouter>,
  )

  expect(await screen.findByText(/今日同花顺官方池/)).toBeInTheDocument()
  expect(screen.getByText('同花顺官方池 · 封板率 75%')).toBeInTheDocument()
  expect(screen.getByText('官方池 · 梯队 1')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '涨停梯队' })).toBeInTheDocument()
  expect(screen.getByText('涨停 12')).toBeInTheDocument()
  vi.useRealTimers()
})

it('dashes unread intraday metrics and does not treat missing volume as 1.00', async () => {
  vi.mocked(api.overviewMarket).mockResolvedValue({
    ...overviewFixture,
    as_of: '2026-08-26',
    data_mode: 'intraday_snapshot',
    indicators_source: 'intraday_approx',
    indicators_approx: true,
    limit: { ...overviewFixture.limit, ready: false },
    activity: { avg_turnover: 1.2, high_turnover: 3, high_vol_ratio: null, vol_ratio: null, vol_ready: false },
    trend: { ...overviewFixture.trend, ready: false, extremes_ready: false, new_high: 0, new_low: 0 },
    radar: [
      { key: 'index', label: '指数', value: 60, ready: true },
      { key: 'money', label: '量能', value: null, ready: false },
    ],
    emotion: { score: 60, label: '偏暖', partial: true, ready_count: 1, note: '盘中部分维度不可用' },
  } as never)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <Dashboard />
      </QueryClientProvider>
    </MemoryRouter>,
  )

  expect(await screen.findByText('盘中部分维度不可用')).toBeInTheDocument()
  expect(screen.getByText('偏暖 · 60 · 部分')).toBeInTheDocument()
  expect(screen.getByText('量比盘后计算 · 高换手 3 · 放量占比 —')).toBeInTheDocument()
  expect(screen.getAllByText('盘后计算').length).toBeGreaterThanOrEqual(2)
  expect(screen.queryByText('1.00')).not.toBeInTheDocument()
  expect(screen.queryByText('50%')).not.toBeInTheDocument()
})

it('lets ordinary users refresh overview-backed dashboard cards without starting a pipeline', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <Dashboard />
      </QueryClientProvider>
    </MemoryRouter>,
  )

  expect(await screen.findByRole('heading', { name: '市场看板' })).toBeInTheDocument()
  const updateButtons = screen.getAllByRole('button', { name: '更新' })
  expect(updateButtons.length).toBeGreaterThanOrEqual(8)
  expect(screen.getByRole('button', { name: '刷新全部模块' })).toBeInTheDocument()
  vi.mocked(api.overviewMarket).mockResolvedValue({
    ...overviewFixture,
    concept_rank: {
      leading: [{ name: '只更新概念', count: 1, avg_pct: 0.08, up_count: 1, down_count: 0, amount: 0, leader: { name: '示例' } }],
      lagging: [],
    },
    industry_rank: {
      leading: [{ name: '不应出现的行业', count: 1, avg_pct: 0.07, up_count: 1, down_count: 0, amount: 0, leader: { name: '对照' } }],
      lagging: [],
    },
  } as never)
  const conceptUpdate = screen.getByRole('heading', { name: '概念热度' }).closest('section')?.querySelector('button[aria-label="更新"]')
  expect(conceptUpdate).toBeTruthy()
  fireEvent.click(conceptUpdate!)
  expect(await screen.findByText('只更新概念')).toBeInTheDocument()
  expect(screen.queryByText('不应出现的行业')).not.toBeInTheDocument()
  expect(await screen.findByText(/已更新 ·/)).toBeInTheDocument()
  await vi.advanceTimersByTimeAsync(3000)
  expect(screen.queryByText(/已更新 ·/)).not.toBeInTheDocument()
  expect(api.pipelineJobs).not.toHaveBeenCalled()
  vi.useRealTimers()
})

it('stretches the breadth, radar and trend dashboard modules to matching card heights', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <Dashboard />
      </QueryClientProvider>
    </MemoryRouter>,
  )

  await screen.findByRole('heading', { name: '市场看板' })
  const breadth = document.querySelector('[data-page-module="breadth"]')
  const radar = document.querySelector('[data-page-module="radar"]')
  const trend = document.querySelector('[data-page-module="trend"]')
  expect(breadth).toHaveClass('h-full')
  expect(radar).toHaveClass('h-full')
  expect(trend).toHaveClass('h-full')
  expect(breadth?.firstElementChild).toHaveClass('h-full')
  expect(radar?.firstElementChild).toHaveClass('h-full')
  expect(trend?.firstElementChild).toHaveClass('h-full')
})

it('invalidates local dashboard module queries and leaves official-pool keys alone', async () => {
  const seen: string[] = []
  await invalidateDashboardModules({
    invalidateQueries: async ({ predicate }) => {
      const keys = [
        ['overview-market', 'latest'],
        ['market-pulse', 'latest'],
        ['index-minute', '000001', '2026-08-27'],
        ['fund-flow-boards', 200],
        ['fund-flow-concepts', 200],
        ['fund-flow-boards-window', 5, 6],
        ['fund-flow-concepts-window', 5, 6],
        ['fund-flow-board-history', 'board', 'BK0475', 120],
        ['fund-flow-board-intraday', 'concept', 'BK0737', 'latest'],
        ['alerts', ''],
        ['data-status'],
        ['quote-status'],
        ['limit-ladder', '2026-08-27'],
        ['hithink-special', '2026-08-27'],
        ['pipeline-jobs'],
      ]
      for (const queryKey of keys) {
        if (predicate({ queryKey })) seen.push(String(queryKey[0]))
      }
    },
  })
  expect(seen).toEqual(expect.arrayContaining([
    'overview-market',
    'market-pulse',
    'index-minute',
    'fund-flow-boards',
    'fund-flow-concepts',
    'fund-flow-boards-window',
    'fund-flow-concepts-window',
    'fund-flow-board-history',
    'fund-flow-board-intraday',
    'alerts',
    'data-status',
    'quote-status',
    'limit-ladder',
  ]))
  expect(seen).not.toContain('hithink-special')
  expect(seen).not.toContain('pipeline-jobs')
})

it('header refresh reloads every dashboard module without upstream syncs', async () => {
  vi.spyOn(api, 'intradayRefresh').mockResolvedValue({ status: 'ok' } as never)
  vi.spyOn(api, 'marketPulse').mockResolvedValue({
    available: false,
    requested_date: null,
    resolved_date: null,
    points: [],
    events: [],
  } as never)
  vi.spyOn(api, 'fundFlowBoards').mockResolvedValue({ items: [] } as never)
  vi.spyOn(api, 'fundFlowConcepts').mockResolvedValue({ items: [] } as never)
  vi.spyOn(api, 'fundFlowBoardsWindow').mockResolvedValue({ items: [], days: 5 } as never)
  const syncPulse = vi.spyOn(api, 'syncMarketPulse').mockResolvedValue({} as never)
  const refreshBoards = vi.spyOn(api, 'fundFlowBoardsRefresh').mockResolvedValue({ items: [] } as never)
  const refreshConcepts = vi.spyOn(api, 'fundFlowConceptsRefresh').mockResolvedValue({ items: [] } as never)
  const pipelineRun = vi.spyOn(api, 'pipelineRun').mockResolvedValue({ job_id: 'x' } as never)
  const hithinkSync = vi.spyOn(api, 'syncHithinkSpecialData').mockResolvedValue({} as never)

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <Dashboard />
      </QueryClientProvider>
    </MemoryRouter>,
  )

  expect(await screen.findByRole('heading', { name: '市场看板' })).toBeInTheDocument()
  const overviewCalls = vi.mocked(api.overviewMarket).mock.calls.length
  const pulseCalls = vi.mocked(api.marketPulse).mock.calls.length
  fireEvent.click(screen.getByRole('button', { name: '刷新全部模块' }))
  await waitFor(() => {
    expect(vi.mocked(api.overviewMarket).mock.calls.length).toBeGreaterThan(overviewCalls)
    expect(vi.mocked(api.marketPulse).mock.calls.length).toBeGreaterThan(pulseCalls)
  })
  expect(syncPulse).not.toHaveBeenCalled()
  expect(refreshBoards).not.toHaveBeenCalled()
  expect(refreshConcepts).not.toHaveBeenCalled()
  expect(pipelineRun).not.toHaveBeenCalled()
  expect(hithinkSync).not.toHaveBeenCalled()
  expect(api.intradayRefresh).not.toHaveBeenCalled()
})

it('header refresh still syncs all local modules when today is 非实时', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.setSystemTime(new Date('2026-08-27T03:52:00.000Z'))
  const today = '2026-08-27'
  vi.spyOn(api, 'intradayRefresh').mockResolvedValue({ status: 'ok' } as never)
  vi.spyOn(api, 'marketPulse').mockResolvedValue({
    available: false,
    requested_date: today,
    resolved_date: today,
    points: [],
    events: [],
  } as never)
  const syncPulse = vi.spyOn(api, 'syncMarketPulse').mockResolvedValue({} as never)
  vi.mocked(api.overviewMarket).mockResolvedValue({
    ...overviewFixture,
    as_of: today,
    data_mode: 'official',
    quote_status: { enabled: true, running: true, is_trading_hours: false, interval_s: 15, quote_age_ms: 73 },
  } as never)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <Dashboard />
      </QueryClientProvider>
    </MemoryRouter>,
  )

  expect(await screen.findByText('非实时')).toBeInTheDocument()
  expect(screen.queryByText('实时')).not.toBeInTheDocument()
  expect(screen.queryByText('73ms')).not.toBeInTheDocument()
  const overviewCalls = vi.mocked(api.overviewMarket).mock.calls.length
  const pulseCalls = vi.mocked(api.marketPulse).mock.calls.length
  fireEvent.click(screen.getByRole('button', { name: '刷新全部模块' }))
  await waitFor(() => {
    expect(vi.mocked(api.overviewMarket).mock.calls.length).toBeGreaterThan(overviewCalls)
    expect(vi.mocked(api.marketPulse).mock.calls.length).toBeGreaterThan(pulseCalls)
  })
  expect(api.intradayRefresh).not.toHaveBeenCalled()
  expect(syncPulse).not.toHaveBeenCalled()
  expect(screen.getByText('非实时')).toBeInTheDocument()
})

it('header refresh pulls a live quote snapshot before reloading today modules', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.setSystemTime(new Date('2026-08-27T05:00:00.000Z'))
  const today = '2026-08-27'
  vi.spyOn(api, 'intradayRefresh').mockResolvedValue({ status: 'ok' } as never)
  vi.mocked(api.overviewMarket).mockResolvedValue({
    ...overviewFixture,
    as_of: today,
    data_mode: 'intraday_snapshot',
    quote_status: { enabled: true, running: true, is_trading_hours: true, interval_s: 15, quote_age_ms: 1000 },
  } as never)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <Dashboard />
      </QueryClientProvider>
    </MemoryRouter>,
  )

  expect(await screen.findByText('实时')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '刷新全部模块' }))
  await waitFor(() => {
    expect(api.intradayRefresh).toHaveBeenCalled()
  })
})
