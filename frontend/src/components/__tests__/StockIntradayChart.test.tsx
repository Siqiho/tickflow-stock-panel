import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { StockIntradayChart } from '@/components/StockIntradayChart'
import { api } from '@/lib/api'

function renderChart() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <StockIntradayChart symbol="301526.SZ" date="2026-06-29" height={320} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.spyOn(api, 'klineMinute').mockResolvedValue({
    symbol: '301526.SZ',
    date: '2026-06-29',
    rows: [],
    source: 'none',
  })
  vi.spyOn(api, 'extendMinuteHistory').mockResolvedValue({ status: 'started', job_id: 'unused' })
})

afterEach(() => {
  vi.restoreAllMocks()
})

it('retries only the selected symbol and date instead of starting the Pro+ batch job', async () => {
  renderChart()

  fireEvent.click(await screen.findByRole('button', { name: '重新读取该日分时' }))

  await waitFor(() => expect(api.klineMinute).toHaveBeenCalledTimes(2))
  expect(api.klineMinute).toHaveBeenLastCalledWith('301526.SZ', '2026-06-29')
  expect(api.extendMinuteHistory).not.toHaveBeenCalled()
})
