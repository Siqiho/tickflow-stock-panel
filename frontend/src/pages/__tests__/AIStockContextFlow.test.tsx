import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { StockPreviewDialog } from '@/components/StockPreviewDialog'
import { api, type LevelType, type PriceLevel } from '@/lib/api'
import { AIHub } from '@/pages/AIHub'
import { StockAnalysis } from '@/pages/StockAnalysis'

function renderFlow() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

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
                symbol="300502.SZ"
                name="新易盛"
                onClose={() => undefined}
                showAnalysisAction
              />
            )}
          />
          <Route path="/ai" element={<AIHub />} />
          <Route path="/stock-analysis" element={<StockAnalysis />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  localStorage.clear()
  vi.spyOn(api, 'watchlistList').mockResolvedValue({ symbols: [] })
  vi.spyOn(api, 'klineDaily').mockResolvedValue({
    symbol: '300502.SZ',
    rows: [],
    source: 'none',
  })
  vi.spyOn(api, 'stockAnalysisLevels').mockResolvedValue({
    symbol: '300502.SZ',
    levels: {} as Record<LevelType, PriceLevel[]>,
    close: null,
    summary: '',
  })
  vi.spyOn(api, 'financialReportsList').mockResolvedValue({ reports: [] })
  vi.spyOn(api, 'stockAnalysisReportsList').mockResolvedValue({ reports: [] })
  vi.spyOn(api, 'reviewReportsList').mockResolvedValue({ reports: [] })
  vi.spyOn(api, 'strategyList').mockResolvedValue({ strategies: [] })
})

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

it('carries a watchlist stock through the AI hub and adds it to recently viewed stocks', async () => {
  renderFlow()

  fireEvent.click(await screen.findByRole('link', { name: 'AI 分析' }))

  const stockFeature = await screen.findByRole('link', { name: '打开AI 个股分析' })
  expect(stockFeature).toHaveAttribute(
    'href',
    '/stock-analysis?symbol=300502.SZ&name=%E6%96%B0%E6%98%93%E7%9B%9B',
  )

  fireEvent.click(stockFeature)

  const selectedStock = await screen.findByTitle('查看个股日 K 详情')
  expect(selectedStock).toHaveTextContent('新易盛')
  expect(selectedStock).toHaveTextContent('300502.SZ')
  expect(screen.getByRole('button', { name: '最近查看：新易盛 300502.SZ' })).toBeInTheDocument()
})
