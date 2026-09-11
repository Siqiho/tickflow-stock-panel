import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { StockFundFlowPanel } from '@/components/stock-analysis/StockFundFlowPanel'
import { api } from '@/lib/api'

const chartMock = vi.hoisted(() => ({
  setOption: vi.fn(),
  clear: vi.fn(),
  resize: vi.fn(),
  dispose: vi.fn(),
}))

const echartsInit = vi.hoisted(() => vi.fn(() => chartMock))

vi.mock('echarts', () => ({ init: echartsInit }))

const populatedResponse = {
  ok: true,
  symbol: '300204.SZ',
  count: 5,
  cached: true,
  rows: [
    { symbol: '300204.SZ', date: '2026-07-17', main_net: -200_000, main_net_pct: -0.6, source: 'eastmoney_fflow', unit_amount: 'yuan' },
    { symbol: '300204.SZ', date: '2026-07-20', main_net: 300_000, main_net_pct: 0.8, source: 'eastmoney_fflow', unit_amount: 'yuan' },
    { symbol: '300204.SZ', date: '2026-07-21', main_net: 400_000, main_net_pct: 1.1, source: 'eastmoney_fflow', unit_amount: 'yuan' },
    { symbol: '300204.SZ', date: '2026-07-22', main_net: 500_000, main_net_pct: 1.4, source: 'eastmoney_fflow', unit_amount: 'yuan' },
    { symbol: '300204.SZ', date: '2026-07-23', main_net: 1_000_000, main_net_pct: 3.21, source: 'eastmoney_fflow', unit_amount: 'yuan' },
  ],
}

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <StockFundFlowPanel symbol="300204.SZ" />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    disconnect() {}
  })
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

it('shows the selected stock fund-flow direction and trend', async () => {
  vi.spyOn(api, 'fundFlowStock').mockResolvedValue(populatedResponse)

  renderPanel()

  const latestMetric = (await screen.findByText('最新 · 07-23')).parentElement
  expect(latestMetric).not.toBeNull()
  expect(within(latestMetric!).getByText('+100万')).toBeInTheDocument()
  expect(screen.getByText('近5日流入占优')).toBeInTheDocument()
  expect(screen.getByText('4日连续净流入')).toBeInTheDocument()
  expect(api.fundFlowStock).toHaveBeenCalledWith('300204.SZ', 60)
  await waitFor(() => expect(chartMock.setOption).toHaveBeenCalled())
})

it('keeps external refresh explicit and reloads the local cache afterward', async () => {
  vi.spyOn(api, 'fundFlowStock')
    .mockResolvedValueOnce({ ok: true, symbol: '300204.SZ', rows: [], count: 0, cached: true })
    .mockResolvedValueOnce(populatedResponse)
  vi.spyOn(api, 'fundFlowStockRefresh').mockResolvedValue({
    ok: true,
    symbol: '300204.SZ',
    rows: 5,
    source: 'eastmoney_fflow',
  })

  renderPanel()

  expect(await screen.findByText('尚未缓存该股资金流')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '获取资金流' }))

  await waitFor(() => {
    expect(api.fundFlowStockRefresh).toHaveBeenCalledWith('300204.SZ')
    expect(api.fundFlowStock).toHaveBeenCalledTimes(2)
  })
  expect(await screen.findByText('最新 · 07-23')).toBeInTheDocument()
})

it('shows refresh failures without hiding the existing cached analysis', async () => {
  vi.spyOn(api, 'fundFlowStock').mockResolvedValue(populatedResponse)
  vi.spyOn(api, 'fundFlowStockRefresh').mockRejectedValue(new Error('东财接口超时'))

  renderPanel()

  expect(await screen.findByText('最新 · 07-23')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '更新' }))

  expect(await screen.findByText('更新失败：东财接口超时')).toBeInTheDocument()
  expect(screen.getByText('近5日流入占优')).toBeInTheDocument()
})

it('starts the cumulative line from the first visible trading day', async () => {
  const rows = Array.from({ length: 25 }, (_, index) => ({
    symbol: '300204.SZ',
    date: `2026-07-${String(index + 1).padStart(2, '0')}`,
    main_net: 10,
    main_net_pct: 0.1,
    source: 'eastmoney_fflow',
    unit_amount: 'yuan',
  }))
  vi.spyOn(api, 'fundFlowStock').mockResolvedValue({
    ok: true,
    symbol: '300204.SZ',
    count: rows.length,
    cached: true,
    rows,
  })

  renderPanel()

  await waitFor(() => expect(chartMock.setOption).toHaveBeenCalled())
  const option = chartMock.setOption.mock.calls.at(-1)?.[0] as {
    series: Array<{ data: number[] }>
  }
  expect(option.series[1].data[0]).toBe(10)
  expect(option.series[1].data.at(-1)).toBe(240)
})
