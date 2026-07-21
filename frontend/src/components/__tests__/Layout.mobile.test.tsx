import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { Layout } from '../Layout'

vi.mock('@/lib/useQuoteStream', () => ({ useQuoteStream: vi.fn() }))
vi.mock('@/components/Toast', () => ({ ToastContainer: () => null }))
vi.mock('@/components/AlertToast', () => ({ AlertToastContainer: () => null }))
vi.mock('@/components/financials/AiAnalysisHost', () => ({ AiAnalysisHost: () => null }))
vi.mock('@/components/financials/AiReportBubble', () => ({ AiReportBubble: () => null }))
vi.mock('@/components/stock-analysis/StockAnalysisHost', () => ({ StockAnalysisHost: () => null }))
vi.mock('@/components/stock-analysis/StockAnalysisBubble', () => ({ StockAnalysisBubble: () => null }))
vi.mock('@/lib/monitorBadge', () => ({
  setCurrentTotal: vi.fn(),
  useUnreadAlerts: () => 0,
}))
vi.mock('@/lib/runtimeLogger', () => ({ useRuntimeRouteLogger: vi.fn() }))
vi.mock('@/lib/theme', () => ({
  useThemeSync: vi.fn(),
  useTheme: () => ({
    theme: 'light',
    isDark: false,
    toggleTheme: vi.fn(),
  }),
}))
vi.mock('@/lib/useSharedQueries', () => ({
  useCapabilities: () => ({ data: { label: 'None', features: {}, capabilities: {} } }),
  useSettings: () => ({ data: { mode: 'none', ai_configured: false, has_ai_key: false } }),
  usePreferences: () => ({
    data: {
      realtime_quotes_enabled: false,
      indices_nav_pinned: false,
      nav_order: [],
      nav_hidden: [],
    },
  }),
  useQuoteStatus: () => ({ data: { running: false, is_trading_hours: false } }),
  useVersion: () => ({ data: { version: 'v0.1.68' } }),
}))
vi.mock('@/lib/useSharedMutations', () => ({
  useToggleRealtimeQuotes: () => ({ isPending: false, mutateAsync: vi.fn() }),
}))
vi.mock('@/lib/api', () => ({
  api: {
    alertsList: vi.fn(async () => ({ total: 0 })),
    analysisMenus: vi.fn(async () => ({ items: [] })),
    capabilities: vi.fn(async () => ({ label: 'None', features: {}, capabilities: {} })),
    indexQuotes: vi.fn(async () => ({ rows: [] })),
    intradayRefresh: vi.fn(async () => undefined),
    pipelineJobs: vi.fn(async () => ({ active_id: null, jobs: [] })),
  },
}))

function renderLayout() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <MemoryRouter
      initialEntries={['/data']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <QueryClientProvider client={client}>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/data" element={<div>数据内容</div>} />
          </Route>
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('Layout mobile navigation', () => {
  it('releases the content column below md and keeps every route reachable in a modal menu', () => {
    renderLayout()

    expect(screen.getByTestId('app-shell')).toHaveClass(
      'grid-cols-1',
      'grid-rows-[auto_1fr]',
      'md:grid-cols-[14rem_1fr]',
      'md:grid-rows-1',
    )
    expect(screen.getByTestId('desktop-sidebar')).toHaveClass('hidden', 'md:flex')
    expect(screen.getByRole('main')).toHaveClass('min-w-0')

    fireEvent.click(screen.getByRole('button', { name: '打开导航' }))
    const dialog = screen.getByRole('dialog', { name: '移动导航' })
    expect(within(dialog).getByRole('link', { name: '数据' })).toBeInTheDocument()
    expect(within(dialog).getByRole('link', { name: '财务分析' })).toBeInTheDocument()

    fireEvent.click(within(dialog).getByRole('link', { name: '数据' }))
    expect(screen.queryByRole('dialog', { name: '移动导航' })).not.toBeInTheDocument()
  })

  it('closes the mobile menu with Escape and restores the open control', () => {
    renderLayout()

    const openButton = screen.getByRole('button', { name: '打开导航' })
    fireEvent.click(openButton)
    expect(screen.getByRole('dialog', { name: '移动导航' })).toBeInTheDocument()

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog', { name: '移动导航' })).not.toBeInTheDocument()
    expect(openButton).toHaveFocus()
  })
})
