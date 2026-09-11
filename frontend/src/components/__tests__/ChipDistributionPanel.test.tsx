import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { ChipDistributionPanel } from '@/components/ChipDistributionPanel'
import { api } from '@/lib/api'

const chartMock = vi.hoisted(() => ({
  setOption: vi.fn(),
  clear: vi.fn(),
  resize: vi.fn(),
  dispose: vi.fn(),
}))

vi.mock('echarts', () => ({ init: vi.fn(() => chartMock) }))

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

it('requests and labels the chip distribution for the selected K-line date', async () => {
  vi.spyOn(api, 'stockChips').mockResolvedValue({
    ok: true,
    data: {
      symbol: '301526.SZ',
      as_of: '2026-07-20',
      days: 2,
      bins: 10,
      current: 26.7,
      avg_cost: 28.5,
      median_cost: 28.2,
      profit_ratio: 0.32,
      min_price: 25.44,
      max_price: 34.99,
      sum_vol: 1000,
      cost70: { low_price: 26.0, high_price: 31.0, concentration: 0.1 },
      cost90: { low_price: 25.5, high_price: 33.0, concentration: 0.13 },
      items: [{ price: 26.7, vol: 1000, ratio: 1 }],
      source: 'local_daily_derived',
    },
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

  render(
    <QueryClientProvider client={client}>
      <ChipDistributionPanel symbol="301526.SZ" asOf="2026-07-20" />
    </QueryClientProvider>,
  )

  await waitFor(() => {
    expect(api.stockChips).toHaveBeenCalledWith('301526.SZ', 120, 80, '2026-07-20')
  })
  expect(await screen.findByText(/截至 2026-07-20/)).toBeInTheDocument()
})
