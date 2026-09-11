import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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
    is_admin: true,
  } as {
    mode: string
    ai_configured: boolean
    has_ai_key: boolean
    ai_model: string
    is_admin: boolean
  } | undefined,
  preferences: {
    realtime_quotes_enabled: true,
    indices_nav_pinned: true,
    sidebar_index_symbols: ['000001.SH'],
    realtime_watchlist_symbols: [] as string[],
    nav_order: [] as string[],
    nav_hidden: [] as string[],
  },
  unread: 0,
  quoteStatus: { running: true, is_trading_hours: true },
}))

vi.mock('@/lib/useQuoteStream', () => ({ useQuoteStream: vi.fn() }))
vi.mock('@/components/Toast', () => ({ ToastContainer: () => null }))
vi.mock('@/components/AlertToast', () => ({ AlertToastContainer: () => null }))
vi.mock('@/components/financials/AiAnalysisHost', () => ({ AiAnalysisHost: () => null }))
vi.mock('@/components/financials/AiReportBubble', () => ({ AiReportBubble: () => null }))
vi.mock('@/components/stock-analysis/StockAnalysisHost', () => ({ StockAnalysisHost: () => null }))
vi.mock('@/components/HermesPageAgentHost', () => ({ HermesPageAgentHost: () => <div data-testid="hermes-page-agent-host" /> }))
vi.mock('@/components/stock-analysis/StockAnalysisBubble', () => ({ StockAnalysisBubble: () => null }))
vi.mock('@/lib/monitorBadge', () => ({
  setCurrentTotal: vi.fn(),
  useUnreadAlerts: () => mockState.unread,
}))
vi.mock('@/lib/runtimeLogger', () => ({
  useRuntimeRouteLogger: vi.fn(),
  setRuntimeLogUploadEnabled: vi.fn(),
}))
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
    capabilities: vi.fn(async () => mockState.capabilities),
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
  mockState.capabilities.label = 'Pro'
  mockState.preferences.realtime_quotes_enabled = true
  mockState.preferences.realtime_watchlist_symbols = []
  mockState.preferences.nav_order = []
  mockState.preferences.nav_hidden = []
  mockState.unread = 0
  mockState.settings = {
    mode: 'tickflow',
    ai_configured: true,
    has_ai_key: true,
    ai_model: 'test-model',
    is_admin: true,
  }
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function renderLayout(initial = '/data') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <MemoryRouter
      initialEntries={[initial]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <QueryClientProvider client={client}>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/data" element={<div>数据内容</div>} />
            <Route path="/news" element={<div>资讯内容</div>} />
            <Route path="/" element={<div>看板内容</div>} />
            <Route path="/ai" element={<div>AI 内容</div>} />
            <Route path="/ai/hermes" element={<div>Hermes 内容</div>} />
            <Route path="/watchlist" element={<div>自选内容</div>} />
            <Route path="/screener" element={<div>策略内容</div>} />
            <Route path="/lots" element={<div>持仓内容</div>} />
            <Route path="/monitor" element={<div>监控内容</div>} />
            <Route path="/trading" element={<div>交易内容</div>} />
          </Route>
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('Layout mobile navigation', () => {
  it('places the menu first, version in the middle, and brand on the right', () => {
    renderLayout()

    const header = screen.getByTestId('mobile-header')
    const menu = screen.getByRole('button', { name: '打开导航' })
    const version = screen.getByTestId('mobile-version')
    const brand = screen.getByTestId('mobile-brand')

    expect(header.children[0]).toBe(menu)
    expect(header.children[1]).toBe(version)
    expect(header.children[2]).toBe(brand)
    expect(version).toHaveTextContent('v0.1.68')
    expect(brand).toHaveTextContent('onetrading')
    expect(screen.getByTestId('hermes-page-agent-host')).toBeInTheDocument()
  })

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
      'AI',
      '自选',
      '量化',
      '个股分析 Beta',
      '连板梯队',
      '概念分析',
      '行业分析',
      '财务分析',
      '交易',
      '市场环境',
      '复盘 Beta',
      '指数',
      '用户管理',
      '数据',
      '资讯',
    ]) {
      expect(within(dialog).getByRole('link', { name: label })).toBeInTheDocument()
    }
    expect(within(dialog).queryByRole('link', { name: '策略' })).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('link', { name: '回测' })).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('link', { name: '监控中心' })).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('link', { name: '持仓提醒' })).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('link', { name: '信号库' })).not.toBeInTheDocument()
    expect(within(dialog).getByRole('link', { name: '量化' })).toHaveAttribute('href', '/quant')
    expect(within(dialog).getByRole('link', { name: '交易' })).toHaveAttribute('href', '/trade')
    const userManagementLink = within(dialog).getByRole('link', { name: '用户管理' })
    const dataLink = within(dialog).getByRole('link', { name: '数据' })
    const newsLink = within(dialog).getByRole('link', { name: '资讯' })
    expect(userManagementLink.nextElementSibling).toBe(dataLink)
    expect(dataLink.nextElementSibling).toBe(newsLink)
    expect(newsLink).toHaveAttribute('href', '/news')
    expect(within(dialog).getByRole('link', { name: 'AI' })).toHaveAttribute('href', '/ai')

    fireEvent.click(within(dialog).getByRole('link', { name: '数据' }))
    expect(screen.queryByRole('dialog', { name: '移动导航' })).not.toBeInTheDocument()
  })

  it('keeps configuration in Settings and preserves realtime, index, and theme controls', async () => {
    renderLayout()

    fireEvent.click(screen.getByRole('button', { name: '打开导航' }))
    const dialog = screen.getByRole('dialog', { name: '移动导航' })

    expect(within(dialog).queryByRole('link', { name: /TickFlow/ })).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('link', { name: /AI 配置/ })).not.toBeInTheDocument()
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

  it('pins user management immediately before Data despite an older saved order', () => {
    mockState.preferences.nav_order = ['/admin/users', '/data', '/ai', '/watchlist']
    renderLayout()

    fireEvent.click(screen.getByRole('button', { name: '打开导航' }))
    const dialog = screen.getByRole('dialog', { name: '移动导航' })
    const navigation = within(dialog).getByRole('navigation', { name: '移动端主导航' })
    const links = within(navigation).getAllByRole('link')

    expect(links.at(-3)).toHaveTextContent('用户管理')
    expect(links.at(-2)).toHaveTextContent('数据')
    expect(links.at(-1)).toHaveTextContent('资讯')
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

  it('closes the menu when Free tier redirects an empty realtime watchlist', async () => {
    mockState.capabilities.label = 'Free'
    mockState.preferences.realtime_quotes_enabled = false
    renderLayout()

    fireEvent.click(screen.getByRole('button', { name: '打开导航' }))
    const dialog = screen.getByRole('dialog', { name: '移动导航' })
    fireEvent.click(within(dialog).getByRole('switch', { name: '实时行情开关' }))

    await waitFor(() => expect(screen.getByText('自选内容')).toBeInTheDocument())
    expect(screen.queryByRole('dialog', { name: '移动导航' })).not.toBeInTheDocument()
    expect(mockState.toggleQuotes).not.toHaveBeenCalled()
  })

  it('keeps shared data visible while hiding administrator navigation from an ordinary user', () => {
    mockState.settings = {
      mode: 'tickflow',
      ai_configured: true,
      has_ai_key: true,
      ai_model: 'test-model',
      is_admin: false,
    }
    renderLayout()

    fireEvent.click(screen.getByRole('button', { name: '打开导航' }))
    const dialog = screen.getByRole('dialog', { name: '移动导航' })

    expect(within(dialog).queryByRole('link', { name: '用户管理' })).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('link', { name: '监控中心' })).not.toBeInTheDocument()
    expect(within(dialog).getByRole('link', { name: '交易' })).toHaveAttribute('href', '/trade')
    expect(within(dialog).getByRole('link', { name: '数据' })).toHaveAttribute('href', '/data')
    expect(within(dialog).getByRole('link', { name: '自选' })).toBeInTheDocument()
  })

  it('keeps the trade group when only the old /trading item was hidden', () => {
    mockState.preferences.nav_hidden = ['/trading']
    renderLayout()

    fireEvent.click(screen.getByRole('button', { name: '打开导航' }))
    const dialog = screen.getByRole('dialog', { name: '移动导航' })
    expect(within(dialog).getByRole('link', { name: '交易' })).toBeInTheDocument()
  })

  it('hides the trade group when the new group id or every member is hidden', () => {
    mockState.preferences.nav_hidden = ['/trade']
    renderLayout()
    fireEvent.click(screen.getByRole('button', { name: '打开导航' }))
    expect(within(screen.getByRole('dialog', { name: '移动导航' })).queryByRole('link', { name: '交易' })).not.toBeInTheDocument()
  })

  it('hides the trade group when every legacy member was hidden', () => {
    mockState.preferences.nav_hidden = ['/monitor', '/lots', '/signals', '/abnormal', '/trading']
    renderLayout()
    fireEvent.click(screen.getByRole('button', { name: '打开导航' }))
    expect(within(screen.getByRole('dialog', { name: '移动导航' })).queryByRole('link', { name: '交易' })).not.toBeInTheDocument()
  })

  it('respects monitor_badge_enabled on the trade entry', () => {
    mockState.unread = 4
    localStorage.setItem('monitor_badge_enabled', '0')
    renderLayout('/lots')
    fireEvent.click(screen.getByRole('button', { name: '打开导航' }))
    expect(within(screen.getByRole('dialog', { name: '移动导航' })).getByRole('link', { name: '交易' })).not.toHaveTextContent('4')
    localStorage.removeItem('monitor_badge_enabled')
  })

  it('shows the monitor badge on 交易 except on the real monitor page', () => {
    mockState.unread = 4
    renderLayout('/lots')
    fireEvent.click(screen.getByRole('button', { name: '打开导航' }))
    expect(within(screen.getByRole('dialog', { name: '移动导航' })).getByRole('link', { name: /交易/ })).toHaveTextContent('4')

    fireEvent.click(within(screen.getByRole('dialog', { name: '移动导航' })).getByRole('button', { name: '关闭导航' }))
  })

  it('hides the monitor badge only while the monitor page is open', () => {
    mockState.unread = 4
    renderLayout('/monitor')
    fireEvent.click(screen.getByRole('button', { name: '打开导航' }))
    expect(within(screen.getByRole('dialog', { name: '移动导航' })).getByRole('link', { name: '交易' })).not.toHaveTextContent('4')
  })

  it('sets aria-current on desktop and mobile group entries while leaving leaf matching to NavLink', () => {
    const { unmount } = renderLayout('/screener')
    const desktop = screen.getByTestId('desktop-sidebar')
    expect(within(desktop).getByRole('link', { name: '量化' })).toHaveAttribute('aria-current', 'page')
    expect(within(desktop).getByRole('link', { name: '交易' })).not.toHaveAttribute('aria-current')
    expect(within(desktop).getByRole('link', { name: '看板' })).not.toHaveAttribute('aria-current')
    expect(within(desktop).getByRole('link', { name: 'AI' })).not.toHaveAttribute('aria-current')

    fireEvent.click(screen.getByRole('button', { name: '打开导航' }))
    const dialog = screen.getByRole('dialog', { name: '移动导航' })
    expect(within(dialog).getByRole('link', { name: '量化' })).toHaveAttribute('aria-current', 'page')
    expect(within(dialog).getByRole('link', { name: '交易' })).not.toHaveAttribute('aria-current')
    expect(within(dialog).getByRole('link', { name: '看板' })).not.toHaveAttribute('aria-current')
    unmount()

    renderLayout('/lots')
    expect(within(screen.getByTestId('desktop-sidebar')).getByRole('link', { name: '交易' })).toHaveAttribute('aria-current', 'page')
    expect(within(screen.getByTestId('desktop-sidebar')).getByRole('link', { name: '量化' })).not.toHaveAttribute('aria-current')
    fireEvent.click(screen.getByRole('button', { name: '打开导航' }))
    expect(within(screen.getByRole('dialog', { name: '移动导航' })).getByRole('link', { name: '交易' })).toHaveAttribute('aria-current', 'page')
  })

  it('keeps root exact and nested AI prefix aria-current on desktop and mobile', () => {
    const { unmount } = renderLayout('/')
    const desktopHome = screen.getByTestId('desktop-sidebar')
    expect(within(desktopHome).getByRole('link', { name: '看板' })).toHaveAttribute('aria-current', 'page')
    expect(within(desktopHome).getByRole('link', { name: '量化' })).not.toHaveAttribute('aria-current')
    fireEvent.click(screen.getByRole('button', { name: '打开导航' }))
    expect(within(screen.getByRole('dialog', { name: '移动导航' })).getByRole('link', { name: '看板' })).toHaveAttribute('aria-current', 'page')
    unmount()

    renderLayout('/ai/hermes')
    const desktopAi = screen.getByTestId('desktop-sidebar')
    expect(within(desktopAi).getByRole('link', { name: 'AI' })).toHaveAttribute('aria-current', 'page')
    expect(within(desktopAi).getByRole('link', { name: '看板' })).not.toHaveAttribute('aria-current')
    fireEvent.click(screen.getByRole('button', { name: '打开导航' }))
    expect(within(screen.getByRole('dialog', { name: '移动导航' })).getByRole('link', { name: 'AI' })).toHaveAttribute('aria-current', 'page')
  })

  it('does not reveal admin navigation while settings are still loading', () => {
    mockState.settings = undefined
    renderLayout()
    fireEvent.click(screen.getByRole('button', { name: '打开导航' }))
    const dialog = screen.getByRole('dialog', { name: '移动导航' })
    expect(within(dialog).queryByRole('link', { name: '用户管理' })).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('link', { name: '监控中心' })).not.toBeInTheDocument()
    expect(within(dialog).getByRole('link', { name: '交易' })).toBeInTheDocument()
  })
})
