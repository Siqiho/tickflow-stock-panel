import { act, render } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { EChartsCandlestick, type OHLC } from '@/components/EChartsCandlestick'

const chartHarness = vi.hoisted(() => {
  const handlers = new Map<string, (event: unknown) => void>()
  const chart = {
    setOption: vi.fn(),
    dispatchAction: vi.fn(),
    getOption: vi.fn(() => ({ dataZoom: [{ start: 0, end: 100 }] })),
    on: vi.fn((event: string, handler: (payload: unknown) => void) => handlers.set(event, handler)),
    off: vi.fn((event: string) => handlers.delete(event)),
    resize: vi.fn(),
    dispose: vi.fn(),
  }
  return { handlers, chart, init: vi.fn(() => chart) }
})

vi.mock('echarts', () => ({ init: chartHarness.init }))

const data: OHLC[] = [
  { date: '2026-06-01', open: 10, high: 12, low: 9, close: 11, volume: 100 },
  { date: '2026-06-02', open: 11, high: 13, low: 10, close: 12, volume: 120 },
]

beforeEach(() => {
  chartHarness.handlers.clear()
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    disconnect() {}
  })
})

afterEach(() => {
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

it('publishes the hovered K-line date through the axis-pointer event', () => {
  const onDateHover = vi.fn()
  render(<EChartsCandlestick data={data} onDateHover={onDateHover} />)

  act(() => {
    chartHarness.handlers.get('updateAxisPointer')?.({ axesInfo: [{ axisDim: 'x', value: 0 }] })
  })

  expect(onDateHover).toHaveBeenCalledWith('2026-06-01')
})

it('keeps the crosshair lines but hides their empty axis-label boxes', () => {
  render(<EChartsCandlestick data={data} />)

  const option = chartHarness.chart.setOption.mock.calls
    .map(([next]) => next)
    .find(next => next?.axisPointer)

  expect(option.tooltip.axisPointer.type).toBe('cross')
  expect(option.tooltip.axisPointer.label.show).toBe(false)
  expect(option.axisPointer.label.show).toBe(false)
})
