import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'

import { IndustryTreemap } from '@/components/IndustryTreemap'

const chartMock = vi.hoisted(() => {
  const handlers = new Map<string, (payload: unknown) => void>()
  return {
    handlers,
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
    on: vi.fn((event: string, handler: (payload: unknown) => void) => handlers.set(event, handler)),
    off: vi.fn((event: string) => handlers.delete(event)),
  }
})

vi.mock('echarts', () => ({ init: vi.fn(() => chartMock) }))

beforeEach(() => {
  chartMock.handlers.clear()
  vi.clearAllMocks()
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    disconnect() {}
  })
})

it('renders a two-level treemap with explicit market and industry coverage', () => {
  render(
    <IndustryTreemap
      groups={[{
        key: '生物制品',
        count: 2,
        stocks: [
          { symbol: '688331.SH', name: '荣昌生物' },
          { symbol: '300142.SZ', name: '沃森生物' },
        ],
        metrics: {},
      }]}
      quoteMap={new Map([
        ['688331.SH', { symbol: '688331.SH', name: '荣昌生物', close: 99, change_pct: 0.1161, float_market_cap: 47_300_000_000 }],
      ])}
      selectedKey="生物制品"
      onSelect={vi.fn()}
      onStockClick={vi.fn()}
      asOf="2026-08-10"
      source="quote_snapshot+enriched"
      coverage={{
        instrument_rows: 5540,
        snapshot_rows: 5207,
        priced_rows: 5207,
        missing_rows: 333,
        coverage_pct: 93.99,
        markets: {},
      }}
    />,
  )

  expect(screen.getByText('大盘热力图')).toBeInTheDocument()
  expect(screen.getByText('行情 5,207 / 5,540')).toBeInTheDocument()
  expect(screen.getByText('行业着色 1 / 2')).toBeInTheDocument()
  expect(chartMock.setOption).toHaveBeenCalled()
  const option = chartMock.setOption.mock.calls.at(-1)?.[0]
  expect(option.series[0].type).toBe('treemap')
  expect(option.series[0].data[0].name).toBe('生物制品')
  expect(option.series[0].data[0].children).toHaveLength(1)
})

it('supports size switching and routes industry and stock clicks', () => {
  const onSelect = vi.fn()
  const onStockClick = vi.fn()
  render(
    <IndustryTreemap
      groups={[{
        key: '半导体',
        count: 1,
        stocks: [{ symbol: '688981.SH', name: '中芯国际' }],
        metrics: {},
      }]}
      quoteMap={new Map([
        ['688981.SH', { symbol: '688981.SH', name: '中芯国际', close: 90, change_pct: 0.035, amount: 2_000_000_000, float_market_cap: 500_000_000_000 }],
      ])}
      selectedKey={null}
      onSelect={onSelect}
      onStockClick={onStockClick}
    />,
  )

  fireEvent.click(screen.getByRole('button', { name: '成交额' }))
  expect(screen.getByRole('button', { name: '成交额' })).toHaveAttribute('aria-pressed', 'true')

  const click = chartMock.handlers.get('click')
  click?.({ data: { kind: 'industry', industry: '半导体' } })
  click?.({ data: { kind: 'stock', symbol: '688981.SH', name: '中芯国际' } })
  expect(onSelect).toHaveBeenCalledWith('半导体')
  expect(onStockClick).toHaveBeenCalledWith('688981.SH', '中芯国际')
})

it('opens a readable fullscreen view and exits with Escape', () => {
  render(
    <IndustryTreemap
      groups={[{
        key: '银行',
        count: 1,
        stocks: [{ symbol: '600036.SH', name: '招商银行' }],
        metrics: {},
      }]}
      quoteMap={new Map([
        ['600036.SH', { symbol: '600036.SH', name: '招商银行', close: 45, change_pct: 0.0028, float_market_cap: 802_672_000_000 }],
      ])}
      selectedKey="银行"
      onSelect={vi.fn()}
      onStockClick={vi.fn()}
    />,
  )

  fireEvent.click(screen.getByRole('button', { name: '最大化热力图' }))
  expect(screen.getByTestId('industry-treemap-fullscreen')).toBeInTheDocument()
  expect(screen.getByRole('dialog', { name: '大盘热力图' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '退出全屏热力图' })).toHaveFocus()
  expect(document.body.style.overflow).toBe('hidden')

  fireEvent.keyDown(window, { key: 'Escape' })
  expect(screen.queryByTestId('industry-treemap-fullscreen')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '最大化热力图' })).toBeInTheDocument()
  expect(document.body.style.overflow).toBe('')
})
