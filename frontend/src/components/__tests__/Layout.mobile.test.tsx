import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Layout } from '../Layout'

const mockState = vi.hoisted(() => ({
  toggleTheme: vi.fn(),
  toggleQuotes: vi.fn(async () => undefined),
  capabilities: {
    label: 'Pro',
    features: { quote: { available: true } },
    capabilities: { 'quote.by_symbol': true },
  },
  settings: {
    mode: 'tickflow',
    ai_configured: true,
    has_ai_key: true,
    ai_model: 'test-model',
  },
  preferences: {
    realtime_quotes_enabled: true,
    indices_nav_pinned: true,
    sidebar_index_symbols: ['000001.SH'],
    nav_order: [],
    nav_hidden: [],
  },
  quoteStatus: { running: true, is_trading_hours: true },
}))

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
    toggleTheme: mockState.toggleTheme,
  }),
}))
vi.mock('@/lib/useSharedQueries', () => ({
  useCapabilities: () => ({ data: mockState.capabilities }),
  useSettings: () => ({ data: mockState.settings }),
  usePreferences: () => ({ data: mockState.preferences }),
  useQuoteStatus: () => ({ data: mockState.quoteStatus }),
  useVersion: () => ({ data: { version: 'v0.1.68' } }),
}))
vi.mock('@/lib/useSharedMutations', () => ({
  useToggleRealtimeQuotes: () => ({ isPending: false, mutateAsync: mockState.toggleQuotes }),
}))
vi.mock('@/lib/api', () => ({
  api: {
    alertsList: vi.fn(async () => ({ total: 0 })),
    analysisMenus: vi.fn(async () => ({ items: [] })),
    capabilities: vi.fn(async () => ({ label: 'None', features: {}, capabilities: {} })),
    indexQuotes: vi.fn(async () => ({
      rows: [{ symbol: '000001.SH', name: '上证指数', last_price: 3012.34, change_pct: 0.56 }],
    })),
    intradayRefresh: vi.fn(async () => undefined),
    pipelineJobs: vi.fn(async () => ({ active_id: null, jobs: [] })),
  },
}))

beforeEach(() => {
  mockState.toggleTheme.mockClear()
  mockState.toggleQuotes.mockClear()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

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
    for (const label of [
      '看板',
      '自选',
      '策略',
      '回测',
      '个股分析 Beta',
      '连板梯队',
      '概念分析',
      '行业分析',
      '财务分析',
      '监控中心',
      '复盘 Beta',
      '指数',
      '交易',
      '数据',
    ]) {
      expect(within(dialog).getByRole('link', { name: label })).toBeInTheDocument()
    }

    fireEvent.click(within(dialog).getByRole('link', { name: '数据' }))
    expect(screen.queryByRole('dialog', { name: '移动导航' })).not.toBeInTheDocument()
  })

  it('preserves tier, AI, realtime, index, settings, and theme controls on mobile', async () => {
    renderLayout()

    fireEvent.click(screen.getByRole('button', { name: '打开导航' }))
    const dialog = screen.getByRole('dialog', { name: '移动导航' })

    expect(within(dialog).getByRole('link', { name: /TickFlow/ })).toHaveAttribute(
      'href',
      '/settings?tab=account',
    )
    expect(within(dialog).getByRole('link', { name: /AI 配置/ })).toHaveAttribute(
      'href',
      '/settings?tab=ai',
    )
    expect(within(dialog).getByText('实时行情 · 全市场')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: '实时监控设置' })).toBeInTheDocument()
    const quoteSwitch = within(dialog).getByRole('switch', { name: '实时行情开关' })
    expect(quoteSwitch).toHaveAttribute('aria-checked', 'true')
    fireEvent.click(quoteSwitch)
    expect(mockState.toggleQuotes).toHaveBeenCalledWith(false)
    expect(await within(dialog).findByText('上证指数')).toBeInTheDocument()

    fireEvent.click(within(dialog).getByRole('button', { name: '切换到暗色模式' }))
    expect(mockState.toggleTheme).toHaveBeenCalledTimes(1)
    expect(within(dialog).getByRole('link', { name: /设置/ })).toHaveAttribute('href', '/settings')
  })

  it('makes the background inert and traps focus inside the modal dialog', () => {
    renderLayout()

    fireEvent.click(screen.getByRole('button', { name: '打开导航' }))
    const dialog = screen.getByRole('dialog', { name: '移动导航' })
    const closeButton = within(dialog).getByRole('button', { name: '关闭导航' })
    const themeButton = within(dialog).getByRole('button', { name: '切换到暗色模式' })

    expect(closeButton).toHaveFocus()
    expect(screen.getByTestId('mobile-header')).toHaveAttribute('inert')
    expect(screen.getByTestId('app-main')).toHaveAttribute('inert')

    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
    expect(themeButton).toHaveFocus()
    fireEvent.keyDown(document, { key: 'Tab' })
    expect(closeButton).toHaveFocus()
  })

  it('closes from the backdrop and restores the opener', () => {
    renderLayout()

    const openButton = screen.getByRole('button', { name: '打开导航' })
    fireEvent.click(openButton)
    fireEvent.click(screen.getByTestId('mobile-navigation-backdrop'))

    expect(screen.queryByRole('dialog', { name: '移动导航' })).not.toBeInTheDocument()
    expect(openButton).toHaveFocus()
    expect(screen.getByRole('main')).not.toHaveAttribute('inert')
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

  it('closes an open mobile menu when crossing into the desktop breakpoint', () => {
    let onChange: ((event: MediaQueryListEvent) => void) | undefined
    const mediaQuery = {
      matches: false,
      media: '(min-width: 768px)',
      onchange: null,
      addEventListener: vi.fn((_type: string, listener: (event: MediaQueryListEvent) => void) => {
        onChange = listener
      }),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }
    vi.stubGlobal('matchMedia', vi.fn(() => mediaQuery))
    renderLayout()

    fireEvent.click(screen.getByRole('button', { name: '打开导航' }))
    expect(screen.getByRole('dialog', { name: '移动导航' })).toBeInTheDocument()

    act(() => onChange?.({ matches: true } as MediaQueryListEvent))
    expect(screen.queryByRole('dialog', { name: '移动导航' })).not.toBeInTheDocument()
  })
})
