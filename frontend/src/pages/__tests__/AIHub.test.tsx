import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/lib/api'
import { AIHub } from '../AIHub'

vi.mock('@/lib/api', () => ({
  api: {
    financialReportsList: vi.fn(),
    stockAnalysisReportsList: vi.fn(),
    reviewReportsList: vi.fn(),
    pageAiReportsList: vi.fn(),
    strategyList: vi.fn(),
    settings: vi.fn(),
  },
}))

function renderPage(entry = '/ai') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  render(
    <MemoryRouter initialEntries={[entry]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <AIHub />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.mocked(api.financialReportsList).mockResolvedValue({ reports: [] })
  vi.mocked(api.stockAnalysisReportsList).mockResolvedValue({ reports: [] })
  vi.mocked(api.reviewReportsList).mockResolvedValue({ reports: [] })
  vi.mocked(api.pageAiReportsList).mockResolvedValue({ reports: [] })
  vi.mocked(api.strategyList).mockResolvedValue({ strategies: [] })
  vi.mocked(api.settings).mockResolvedValue({
    mode: 'free',
    tickflow_api_key_masked: '',
    has_tickflow_key: false,
    tier_label: 'Free',
    current_endpoint: '',
    probe_log: [],
    missing_caps: [],
    extras_caps: [],
    onboarding_completed: true,
    ai_provider: 'openai_compat',
    ai_base_url: '',
    ai_api_key_masked: '',
    has_ai_key: false,
    ai_model: '',
    ai_user_agent: '',
  })
})

describe('AIHub', () => {
  it('lists only the real AI functions and links to their existing work areas', () => {
    renderPage()

    expect(screen.getByRole('heading', { name: 'AI' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '功能目录' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: '历史记录' })).toHaveAttribute('aria-selected', 'false')
    expect(screen.getByRole('tab', { name: '个股分析' })).toHaveAttribute('aria-selected', 'false')
    expect(screen.getByRole('tab', { name: '复盘' })).toHaveAttribute('aria-selected', 'false')
    expect(screen.getByRole('tab', { name: '页面' })).toHaveAttribute('aria-selected', 'false')
    expect(screen.queryByRole('heading', { name: '历史记录' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: '打开Hermes Agent 对话' })).toHaveAttribute('href', '/ai/hermes')
    expect(screen.getByRole('link', { name: '打开AI 个股分析' })).toHaveAttribute('href', '/stock-analysis')
    expect(screen.getByRole('link', { name: '打开AI 财务分析' })).toHaveAttribute('href', '/financials')
    expect(screen.getByRole('link', { name: '打开AI 大盘复盘' })).toHaveAttribute('href', '/review')
    expect(screen.getByRole("link", { name: "打开AI 板块轮动分析" })).toHaveAttribute("href", "/concept-analysis")
    expect(screen.getByRole('link', { name: '打开AI 策略生成' })).toHaveAttribute('href', '/screener?ai=builder')
    expect(screen.getByRole('link', { name: 'AI 配置' })).toHaveAttribute('href', '/settings?tab=ai')

    expect(screen.queryByRole('link', { name: /行业分析/ })).not.toBeInTheDocument()
  })

  it('carries an incoming stock context to every AI capability', () => {
    renderPage('/ai?symbol=300502.SZ&name=%E6%96%B0%E6%98%93%E7%9B%9B')

    expect(screen.getByLabelText('当前分析股票')).toHaveTextContent('新易盛')
    expect(screen.getByLabelText('当前分析股票')).toHaveTextContent('300502.SZ')
    expect(screen.getByRole('link', { name: '打开AI 个股分析' })).toHaveAttribute(
      'href',
      '/stock-analysis?symbol=300502.SZ&name=%E6%96%B0%E6%98%93%E7%9B%9B',
    )
    expect(screen.getByRole('link', { name: '打开AI 财务分析' })).toHaveAttribute(
      'href',
      '/financials?symbol=300502.SZ&name=%E6%96%B0%E6%98%93%E7%9B%9B',
    )
    expect(screen.getByRole('link', { name: '打开AI 大盘复盘' })).toHaveAttribute(
      'href',
      '/review?symbol=300502.SZ&name=%E6%96%B0%E6%98%93%E7%9B%9B',
    )
    expect(screen.getByRole('link', { name: '打开AI 策略生成' })).toHaveAttribute(
      'href',
      '/screener?ai=builder&symbol=300502.SZ&name=%E6%96%B0%E6%98%93%E7%9B%9B',
    )
    expect(screen.getByRole('link', { name: '打开Hermes Agent 对话' })).toHaveAttribute(
      'href',
      '/ai/hermes?symbol=300502.SZ&name=%E6%96%B0%E6%98%93%E7%9B%9B',
    )
    expect(screen.getByText('继续分析 新易盛 · 300502.SZ')).toBeInTheDocument()
    expect(screen.getByText('围绕 新易盛 · 300502.SZ 继续对话')).toBeInTheDocument()
  })

  it('shows cloud subscription state without exposing a configuration link', async () => {
    vi.mocked(api.settings).mockResolvedValue({
      mode: 'free', tickflow_api_key_masked: '', has_tickflow_key: false, tier_label: 'Free', current_endpoint: '',
      probe_log: [], missing_caps: [], extras_caps: [], onboarding_completed: true,
      ai_provider: 'xai', ai_base_url: '', ai_api_key_masked: '', has_ai_key: true,
      ai_configured: true, ai_model: 'grok-4.5', ai_user_agent: '',
      ai_access: {
        mode: 'cloud_subscription', state: 'active', allowed: true, entitled: true, configured: true,
        provider: 'xai', model: 'grok-4.5', plan: 'AI Pro', message: '云端 Grok 已连接',
      },
    })

    renderPage()

    expect(await screen.findByText('云端 Grok 已连接')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'AI 配置' })).not.toBeInTheDocument()
    expect(screen.getByText(/AI Pro 订阅统一提供/)).toBeInTheDocument()
  })

  it('merges saved results, sorts reports by time, and builds exact deep links', async () => {
    vi.mocked(api.financialReportsList).mockResolvedValue({
      reports: [{
        id: 'finance-1',
        symbol: '002240.SZ',
        name: '盛新锂能',
        focus: '',
        content: '财务报告正文',
        summary: '现金流改善',
        periods: 8,
        created_at: '2026-08-01T23:50:36+08:00',
      }],
    })
    vi.mocked(api.stockAnalysisReportsList).mockResolvedValue({
      reports: [{
        id: 'stock-1',
        symbol: '300274.SZ',
        name: '阳光电源',
        focus: '',
        content: '个股报告正文',
        summary: '趋势仍强',
        created_at: '2026-08-01T22:00:00+08:00',
      }],
    })
    vi.mocked(api.reviewReportsList).mockResolvedValue({
      reports: [{
        id: 'review-1',
        as_of: '2026-07-31',
        focus: '',
        content: '复盘正文',
        summary: '指数震荡分化',
        emotion_label: '中性',
        created_at: '2026-07-31T15:30:00+08:00',
      }],
    })
    vi.mocked(api.strategyList).mockResolvedValue({
      strategies: [{
        id: 'ai-trend',
        name: 'AI 趋势策略',
        description: '识别趋势启动',
        tags: [],
        source: 'ai',
        version: '1.0',
        basic_filter: {},
        params: [],
        params_defaults: {},
        scoring: {},
        entry_signals: [],
        exit_signals: [],
        stop_loss: null,
        take_profit: null,
        trailing_stop: null,
        trailing_take_profit_activate: null,
        trailing_take_profit_drawdown: null,
        max_hold_days: null,
        alerts: [],
        order_by: 'score',
        descending: true,
        limit: 20,
      }],
    })

    renderPage()
    fireEvent.click(screen.getByRole('tab', { name: '历史记录' }))

    const historyLinks = await screen.findAllByRole('link', { name: /^查看.+历史：/ })
    expect(historyLinks.map(link => link.getAttribute('aria-label'))).toEqual([
      '查看财务分析历史：盛新锂能',
      '查看AI 策略历史：AI 趋势策略',
    ])

    expect(historyLinks[0].getAttribute('href')).toContain('/financials?')
    expect(historyLinks[0].getAttribute('href')).toContain('report=finance-1')
    expect(historyLinks[1]).toHaveAttribute('href', '/screener?strategy=ai-trend')

    fireEvent.click(screen.getByRole('button', { name: '财务 1' }))
    expect(screen.getByRole('link', { name: '查看财务分析历史：盛新锂能' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '查看个股分析历史：阳光电源' })).not.toBeInTheDocument()
  })

  it('shows one card per stock and opens that stock analysis history', async () => {
    vi.mocked(api.stockAnalysisReportsList).mockResolvedValue({
      reports: [
        {
          id: 'stock-new',
          symbol: '605289.SH',
          name: '罗曼股份',
          focus: '',
          content: '新报告',
          summary: '假突破后回落',
          created_at: '2026-08-19T14:04:50+08:00',
        },
        {
          id: 'stock-old',
          symbol: '605289.SH',
          name: '罗曼股份',
          focus: '',
          content: '旧报告',
          summary: '站上60日线',
          created_at: '2026-08-18T13:23:00+08:00',
        },
        {
          id: 'stock-other',
          symbol: '603261.SH',
          name: '立航科技',
          focus: '',
          content: '另一只',
          summary: '观察支撑',
          created_at: '2026-08-12T02:25:45+08:00',
        },
      ],
    })

    renderPage()
    fireEvent.click(screen.getByRole('tab', { name: '个股分析' }))

    expect(await screen.findByRole('heading', { name: '个股分析' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '个股 2' })).not.toBeInTheDocument()

    const stockLinks = await screen.findAllByRole('link', { name: /^查看个股分析历史：/ })
    expect(stockLinks.map(link => link.getAttribute('aria-label'))).toEqual([
      '查看个股分析历史：罗曼股份',
      '查看个股分析历史：立航科技',
    ])
    expect(stockLinks[0].getAttribute('href')).toContain('/stock-analysis?')
    expect(stockLinks[0].getAttribute('href')).toContain('symbol=605289.SH')
    expect(stockLinks[0].getAttribute('href')).toContain('report=stock-new')
    expect(screen.getByText(/共 2 份历史分析/)).toBeInTheDocument()
  })

  it('shows a useful empty state when no result has been saved yet', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('tab', { name: '历史记录' }))

    expect(await screen.findByText('还没有 AI 历史记录')).toBeInTheDocument()
    expect(screen.getByText('分析完成并保存后，会自动出现在这里。')).toBeInTheDocument()
  })

  it('keeps stock cards out of the shared history tab', async () => {
    vi.mocked(api.stockAnalysisReportsList).mockResolvedValue({
      reports: [{
        id: 'stock-1',
        symbol: '300274.SZ',
        name: '阳光电源',
        focus: '',
        content: '个股报告正文',
        summary: '趋势仍强',
        created_at: '2026-08-01T22:00:00+08:00',
      }],
    })
    renderPage('/ai?tab=history')
    expect(await screen.findByRole('heading', { name: '历史记录' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '查看个股分析历史：阳光电源' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /个股 / })).not.toBeInTheDocument()
  })

  it('opens history from the tab without showing the catalog', async () => {
    renderPage('/ai?tab=history')

    expect(screen.getByRole('tab', { name: '历史记录' })).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByText('还没有 AI 历史记录')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '打开Hermes Agent 对话' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'AI 功能目录' })).not.toBeInTheDocument()
  })

  it('keeps review and page cards out of the shared history tab', async () => {
    vi.mocked(api.reviewReportsList).mockResolvedValue({
      reports: [{
        id: 'review-1',
        as_of: '2026-07-31',
        emotion_label: '中性',
        summary: '震荡',
        focus: '',
        content: '复盘正文',
        created_at: '2026-07-31T16:00:00+08:00',
      }],
    })
    vi.mocked(api.pageAiReportsList).mockResolvedValue({
      reports: [{
        id: 'page-1',
        route: '/dashboard',
        title: '市场看板分析',
        as_of: '2026-08-20',
        focus: '情绪',
        summary: '页面分析摘要',
        content: '页面分析正文',
        created_at: '2026-08-20T16:00:00+08:00',
      }],
    })
    renderPage('/ai?tab=history')
    expect(await screen.findByRole('heading', { name: '历史记录' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '查看大盘复盘历史：2026-07-31 大盘复盘' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '查看页面分析历史：市场看板分析' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /复盘 / })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /页面 / })).not.toBeInTheDocument()
  })

  it('opens review history from the top-level tab', async () => {
    vi.mocked(api.reviewReportsList).mockResolvedValue({
      reports: [{
        id: 'review-1',
        as_of: '2026-07-31',
        emotion_label: '中性',
        summary: '震荡',
        focus: '',
        content: '复盘正文',
        created_at: '2026-07-31T16:00:00+08:00',
      }],
    })
    renderPage()
    fireEvent.click(screen.getByRole('tab', { name: '复盘' }))
    expect(await screen.findByRole('heading', { name: '复盘' })).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: '查看大盘复盘历史：2026-07-31 大盘复盘' })).toHaveAttribute('href', '/review?report=review-1')
    expect(screen.queryByRole('heading', { name: 'AI 功能目录' })).not.toBeInTheDocument()
  })

  it('opens page history from the top-level tab', async () => {
    vi.mocked(api.pageAiReportsList).mockResolvedValue({
      reports: [{
        id: 'page-1',
        route: '/dashboard',
        title: '市场看板分析',
        as_of: '2026-08-20',
        focus: '情绪',
        summary: '页面分析摘要',
        content: '页面分析正文',
        created_at: '2026-08-20T16:00:00+08:00',
      }],
    })
    renderPage('/ai?tab=page')
    expect(screen.getByRole('tab', { name: '页面' })).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByRole('heading', { name: '页面' })).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: '查看页面分析历史：市场看板分析' })).toHaveAttribute('href', '/dashboard?pageAi=page-1')
    expect(screen.queryByRole('heading', { name: 'AI 功能目录' })).not.toBeInTheDocument()
  })
})
