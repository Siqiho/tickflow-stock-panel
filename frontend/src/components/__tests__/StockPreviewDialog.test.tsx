import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { StockPreviewDialog } from '@/components/StockPreviewDialog'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}{location.search}</output>
}

function renderDialog() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  })
  client.setQueryData(QK.capabilities, { capabilities: {}, features: {} })

  render(
    <MemoryRouter
      initialEntries={['/watchlist']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <QueryClientProvider client={client}>
        <Routes>
          <Route
            path="/watchlist"
            element={(
              <StockPreviewDialog
                symbol="300204.SZ"
                name="舒泰神"
                onClose={() => undefined}
                showAnalysisAction
              />
            )}
          />
          <Route path="/ai" element={<LocationProbe />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-08-05T12:00:00+08:00'))
  vi.spyOn(api, 'watchlistList').mockResolvedValue({ symbols: [] })
  vi.spyOn(api, 'klineDaily').mockResolvedValue({ symbol: '300204.SZ', rows: [], source: 'none' })
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

it('opens the AI hub with the selected watchlist stock context', async () => {
  renderDialog()

  fireEvent.click(await screen.findByRole('link', { name: 'AI 分析' }))

  expect(screen.getByTestId('location')).toHaveTextContent(
    '/ai?symbol=300204.SZ&name=%E8%88%92%E6%B3%B0%E7%A5%9E',
  )
})

it('offers expanded K-line history ranges and requests the selected range', async () => {
  renderDialog()

  for (const label of ['1月', '3月', '半年', '1年', '3年', '5年', '全部']) {
    expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
  }

  fireEvent.click(screen.getByRole('button', { name: '3年' }))
  await waitFor(() => {
    expect(vi.mocked(api.klineDaily).mock.calls.some(([, , range]) => (
      range?.start === '2023-08-05' && range.end === '2026-08-05'
    ))).toBe(true)
  })

  fireEvent.click(screen.getByRole('button', { name: '全部' }))
  await waitFor(() => {
    expect(vi.mocked(api.klineDaily).mock.calls.some(([, , range]) => (
      range?.start === '1990-01-01' && range.end === '2026-08-05'
    ))).toBe(true)
  })
})
