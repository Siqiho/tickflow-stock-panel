import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { MarketPulsePanel } from '@/components/MarketPulsePanel'
import { api, type MarketPulseResponse } from '@/lib/api'

const chartMock = vi.hoisted(() => ({
  setOption: vi.fn(),
  resize: vi.fn(),
  dispose: vi.fn(),
  on: vi.fn(),
  off: vi.fn(),
}))

vi.mock('echarts', () => ({
  init: vi.fn(() => chartMock),
  graphic: { LinearGradient: class {} },
}))

const pulseFixture: MarketPulseResponse = {
  available: true,
  requested_date: '2026-08-10',
  resolved_date: '2026-08-10',
  updated_at: '2026-08-10T15:01:00+08:00',
  benchmark: { symbol: '000001.SH', name: '上证指数' },
  points: [
    {
      event_id: 'minute:0930', trade_date: '2026-08-10', event_time: '2026-08-10T09:30:00', minute: 930,
      benchmark_symbol: '000001.SH', benchmark_name: '上证指数', last_price: 3943.8, change_ratio: 0.001,
      preclose: 3939.9, open: 3939.9, volume: 494_465_500, amount: 11_238_430_879,
      source: 'cls_market_pulse', unit_version: 'market_pulse_v1',
    },
    {
      event_id: 'minute:0931', trade_date: '2026-08-10', event_time: '2026-08-10T09:31:00', minute: 931,
      benchmark_symbol: '000001.SH', benchmark_name: '上证指数', last_price: 3945, change_ratio: 0.0013,
      preclose: 3939.9, open: 3939.9, volume: 12_000_000, amount: 500_000_000,
      source: 'cls_market_pulse', unit_version: 'market_pulse_v1',
    },
  ],
  events: [
    {
      event_id: 'event:1', trade_date: '2026-08-10', event_time: '2026-08-10T09:28:51', minute: 928,
      benchmark_symbol: '000001.SH', benchmark_name: '上证指数', sector_code: 'cls80427', sector_name: '影视',
      direction: 'up', article_id: 1, source: 'cls_market_pulse', unit_version: 'market_pulse_v1',
    },
    {
      event_id: 'event:2', trade_date: '2026-08-10', event_time: '2026-08-10T09:31:20', minute: 931,
      benchmark_symbol: '000001.SH', benchmark_name: '上证指数', sector_code: 'cls80428', sector_name: '航运',
      direction: 'up', article_id: 2, source: 'cls_market_pulse', unit_version: 'market_pulse_v1',
    },
  ],
  minute_rows: 2,
  event_rows: 2,
  source: 'local',
  producer: 'cls',
  unit_version: 'market_pulse_v1',
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <MarketPulsePanel tradeDate="2026-08-10" />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    disconnect() {}
  })
  vi.spyOn(api, 'marketPulse').mockResolvedValue(pulseFixture)
  vi.spyOn(api, 'syncMarketPulse').mockResolvedValue({
    requested_date: '2026-08-10', resolved_date: '2026-08-10', minute_rows: 2, event_rows: 1,
    rows_published: 3, artifact_path: 'market/pulse/date=2026-08-10/part.parquet',
    lineage_path: 'lineage/market_pulse/date=2026-08-10/run.json', catalog_refreshed: true,
  })
  vi.spyOn(api, 'indexMinute').mockResolvedValue({
    symbol: '399001.SZ', name: '深证成指', date: '2026-08-10', source: 'live',
    rows: [{ datetime: '2026-08-10T09:30:00', open: 1, high: 1, low: 1, close: 1, volume: 1, amount: 1 }],
  })
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

it('keeps local refresh separate from the explicit CLS sync action', async () => {
  renderPanel()
  expect(await screen.findByText('2 分钟')).toBeInTheDocument()
  expect(screen.queryByText('本地 market_pulse')).not.toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: '刷新本地' }))
  await waitFor(() => expect(api.marketPulse).toHaveBeenCalledTimes(2))
  expect(api.syncMarketPulse).not.toHaveBeenCalled()

  fireEvent.click(screen.getByRole('button', { name: '更新' }))
  await waitFor(() => expect(api.syncMarketPulse).toHaveBeenCalledWith('2026-08-10'))
  expect(screen.queryByText(/已写入/)).not.toBeInTheDocument()
})

it('lets the user choose a trade date without triggering an external sync', async () => {
  renderPanel()
  await screen.findByText('2 分钟')

  fireEvent.click(screen.getByRole('button', { name: /2026-08-10/ }))
  fireEvent.click(screen.getByRole('button', { name: '7' }))

  await waitFor(() => expect(api.marketPulse).toHaveBeenCalledWith('2026-08-07'))
  expect(api.syncMarketPulse).not.toHaveBeenCalled()

  fireEvent.click(screen.getByRole('button', { name: '更新' }))
  await waitFor(() => expect(api.syncMarketPulse).toHaveBeenCalledWith('2026-08-07'))
})

it('opens an inline event detail with concept, industry and explicit AI-review routes', async () => {
  renderPanel()
  const eventLabel = await screen.findByText('影视')
  fireEvent.click(eventLabel.closest('button')!)

  expect(screen.getByRole('link', { name: /在概念分析中查找/ })).toHaveAttribute('href', '/concept-analysis?focus=%E5%BD%B1%E8%A7%86')
  expect(screen.getByRole('link', { name: /在行业分析中查找/ })).toHaveAttribute('href', '/industry-analysis?focus=%E5%BD%B1%E8%A7%86')
  expect(screen.getByRole('link', { name: /带入 AI 复盘/ }).getAttribute('href')).toContain('/review?as_of=2026-08-10&focus=')
})

it('queries a comparison index only after the user changes the benchmark', async () => {
  renderPanel()
  await screen.findByText('市场脉搏')
  expect(api.indexMinute).not.toHaveBeenCalled()

  fireEvent.change(screen.getByLabelText('比较指数'), { target: { value: '399001.SZ' } })

  await waitFor(() => expect(api.indexMinute).toHaveBeenCalledWith('399001.SZ', '2026-08-10'))
  await screen.findByText('1 分钟')
  expect(screen.queryByText('即时指数查询，不写入')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '开始盘中回放' })).toBeInTheDocument()
})

it('labels every visible sector marker instead of thinning nearby dots', async () => {
  renderPanel()
  await screen.findByText('市场脉搏')
  await waitFor(() => expect(chartMock.setOption).toHaveBeenCalled())
  const option = chartMock.setOption.mock.calls.at(-1)?.[0] as { series?: Array<{ name?: string; data?: Array<{ labelText?: string; label?: { show?: boolean } }> }> }
  const scatter = option.series?.find(item => item.name === '板块异动')
  expect(scatter?.data?.map(item => item.labelText)).toEqual(['影视', '航运'])
  expect(scatter?.data?.every(item => item.label?.show)).toBe(true)
})
