import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api, type SettingsState } from '@/lib/api'
import { HermesAgentChat } from '../HermesAgentChat'

const chartMock = vi.hoisted(() => ({
  setOption: vi.fn(),
  resize: vi.fn(),
  dispose: vi.fn(),
}))

vi.mock('echarts', () => ({
  init: vi.fn(() => chartMock),
}))

vi.mock('@/components/StockPreviewDialog', () => ({
  StockPreviewDialog: ({ symbol, onClose }: { symbol: string | null; onClose: () => void }) => (
    symbol ? (
      <div role="dialog" aria-label={`${symbol} 行情预览`}>
        <span>{symbol}</span>
        <button type="button" onClick={onClose}>关闭预览</button>
      </div>
    ) : null
  ),
}))

let settingsState: SettingsState

vi.mock('@/lib/useSharedQueries', () => ({
  useSettings: () => ({ data: settingsState }),
}))

vi.mock('@/lib/api', () => ({
  api: {
    hermesAgentStatus: vi.fn(),
    hermesCreateSession: vi.fn(),
    hermesSessions: vi.fn(),
    hermesRenameSession: vi.fn(),
    hermesDeleteSession: vi.fn(),
    hermesSessionMessages: vi.fn(),
    hermesChatStream: vi.fn(),
    pageAiReportSave: vi.fn(),
    pageAiReportGet: vi.fn(),
    selectAiSubscription: vi.fn(),
    saveAiSubscriptionSource: vi.fn(),
    testAiSubscription: vi.fn(),
    hermesStartGateway: vi.fn(),
  },
}))

function cloudSettings(overrides: Partial<SettingsState> = {}): SettingsState {
  return {
    mode: 'free',
    tickflow_api_key_masked: '',
    has_tickflow_key: false,
    tier_label: 'Free',
    current_endpoint: '',
    probe_log: [],
    missing_caps: [],
    extras_caps: [],
    onboarding_completed: true,
    is_admin: false,
    ai_provider: 'xai',
    ai_base_url: '',
    ai_api_key_masked: '',
    has_ai_key: true,
    ai_configured: true,
    ai_model: 'grok-4.5',
    ai_user_agent: '',
    ai_xai: { auth_type: 'server_managed', has_oauth: false, has_access_token: false, expired: false },
    ai_access: {
      mode: 'cloud_subscription',
      state: 'active',
      allowed: true,
      entitled: true,
      configured: true,
      provider: 'xai',
      model: 'grok-4.5',
      plan: 'Grok 云订阅',
      message: '云端 Grok 已连接',
      credential_source: 'api_key',
    },
    ai_subscriptions: [
      {
        provider: 'xai',
        label: 'Grok',
        website: 'https://accounts.x.ai/',
        website_label: 'accounts.x.ai',
        description: 'Grok',
        base_url: 'https://api.x.ai/v1',
        default_model: 'grok-4.5',
        models: ['grok-4.5', 'grok-4.20'],
        ready: true,
        active: true,
        model: 'grok-4.5',
        credential_source: 'api_key',
        message: '云端 Grok 已连接',
        default_base_url: 'https://api.x.ai/v1',
        has_api_key: true,
        api_key_masked: 'serv••••••cret',
      },
      {
        provider: '86gamestore',
        label: '86game',
        website: 'https://api.86gamestore.com/',
        website_label: 'api.86gamestore.com',
        description: '86game',
        base_url: 'https://api.86gamestore.com/v1',
        default_model: 'gpt-5.6-sol',
        models: ['gpt-5.6-sol', 'gpt-5.6-terra'],
        ready: true,
        active: false,
        model: 'gpt-5.6-sol',
        credential_source: 'api_key',
        message: '云端 86game 已连接',
        has_api_key: true,
        api_key_masked: '86ga••••••cret',
        default_base_url: 'https://api.86gamestore.com/v1',
      },
    ],
    ...overrides,
  }
}

function renderPage(entry = '/ai/hermes') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <HermesAgentChat />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  settingsState = cloudSettings()
  vi.mocked(api.hermesAgentStatus).mockResolvedValue({
    connected: true,
    profile: 'one-trading',
    model: 'grok-4.5',
    model_source: 'server_grok_subscription',
    model_plan: 'Grok 云订阅',
    model_subscription_active: true,
    memory_enabled: true,
    memory_provider: 'holographic',
    enabled_mcp_servers: ['one-trading-data'],
    enabled_skills: ['lieflat-charts'],
    lieflat_charts_enabled: true,
    data_tool_enabled: true,
    data_view_count: 68,
    enabled_toolsets: ['memory', 'session_search'],
  })
  vi.mocked(api.hermesCreateSession).mockResolvedValue({
    session: { id: 'api_test', title: null },
  })
  vi.mocked(api.hermesSessions).mockResolvedValue({
    sessions: [
      {
        id: 'api_history',
        title: '市场数据复盘',
        preview: '请总结今天的市场表现',
        message_count: 4,
        last_active: 1_786_367_567,
      },
    ],
  })
  vi.mocked(api.hermesRenameSession).mockImplementation(async (sessionId, title) => ({
    session: { id: sessionId, title },
  }))
  vi.mocked(api.hermesDeleteSession).mockImplementation(async sessionId => ({
    object: 'hermes.session.deleted',
    id: sessionId,
    deleted: true,
  }))
  vi.mocked(api.hermesSessionMessages).mockResolvedValue({
    session_id: 'api_test',
    messages: [],
  })
  vi.mocked(api.hermesChatStream).mockImplementation(async function* () {
    yield { type: 'delta', content: '你好，我是你的 one-trading 助理。' }
    yield { type: 'done', session_id: 'api_test' }
  })
  vi.mocked(api.pageAiReportSave).mockResolvedValue({
    ok: true,
    report: {
      id: 'par_test',
      title: '连板梯队',
      route: '/limit-ladder',
      focus: '',
      content: '已保存',
      created_at: '2026-08-19T12:00:00',
    },
  })
})

describe('HermesAgentChat', () => {
  it('waits for a connected status before loading sessions or persisted history', async () => {
    localStorage.setItem('one-trading.hermes.session-id', 'stale-session')
    vi.mocked(api.hermesAgentStatus).mockResolvedValue({
      connected: false,
      profile: null,
      message: '多用户 Hermes Agent 尚未启用',
    })

    renderPage()

    expect(await screen.findByRole('alert')).toHaveTextContent('多用户 Hermes Agent 尚未启用')
    expect(api.hermesSessions).not.toHaveBeenCalled()
    expect(api.hermesSessionMessages).not.toHaveBeenCalled()
    expect(localStorage.getItem('one-trading.hermes.session-id')).toBe('stale-session')
  })

  it('shows the gateway-down reason instead of a generic Profile error', async () => {
    vi.mocked(api.hermesAgentStatus).mockResolvedValue({
      connected: false,
      profile: 'ot-owner',
      model: 'grok-4.5',
      model_source: 'server_grok_subscription',
      model_plan: 'Grok',
      model_subscription_active: true,
      message: 'Hermes multiplex gateway 当前未运行',
      detail: 'All connection attempts failed',
    })

    renderPage()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Hermes multiplex gateway 当前未运行')
    expect(alert).toHaveTextContent('All connection attempts failed')
    expect(api.hermesSessions).not.toHaveBeenCalled()
  })

  it('lets an administrator start the local multiplex gateway from Agent settings', async () => {
    settingsState = cloudSettings({ is_admin: true })
    vi.mocked(api.hermesAgentStatus)
      .mockResolvedValueOnce({
        connected: false,
        profile: 'ot-owner',
        model: 'gpt-5.6-sol',
        model_source: 'server_subscription',
        model_plan: 'Subrouter',
        model_subscription_active: true,
        gateway_kind: 'managed_local',
        gateway_running: false,
        gateway_startable: true,
        can_start_gateway: true,
        message: 'Hermes multiplex gateway 当前未运行',
        detail: 'All connection attempts failed',
      })
      .mockResolvedValue({
        connected: true,
        profile: 'ot-owner',
        model: 'gpt-5.6-sol',
        model_source: 'server_subscription',
        model_plan: 'Subrouter',
        model_subscription_active: true,
        gateway_kind: 'managed_local',
        gateway_running: true,
        gateway_startable: false,
        can_start_gateway: false,
        memory_enabled: true,
        memory_provider: 'holographic',
        data_tool_enabled: true,
        data_view_count: 75,
      })
    vi.mocked(api.hermesStartGateway).mockResolvedValue({
      ok: true,
      started: true,
      already_running: false,
      pid: 12410,
      base_url: 'http://127.0.0.1:8651',
      message: '内部网关已启动',
    })

    renderPage()
    fireEvent.click(screen.getByRole('button', { name: '打开 Agent 设置' }))
    const startButtons = await screen.findAllByRole('button', { name: '启动内部网关' })
    expect(startButtons.length).toBeGreaterThan(0)
    fireEvent.click(startButtons[0])

    await waitFor(() => {
      expect(api.hermesStartGateway).toHaveBeenCalled()
      expect(screen.getByText('Profile 已连接')).toBeInTheDocument()
    })
    expect(screen.queryByRole('button', { name: '启动内部网关' })).not.toBeInTheDocument()
  })

  it('does not offer gateway start to a regular user', async () => {
    vi.mocked(api.hermesAgentStatus).mockResolvedValue({
      connected: false,
      profile: 'ot-owner',
      model: 'gpt-5.6-sol',
      model_source: 'server_subscription',
      model_plan: 'Subrouter',
      model_subscription_active: true,
      gateway_kind: 'managed_local',
      gateway_running: false,
      gateway_startable: true,
      can_start_gateway: false,
      message: 'Hermes multiplex gateway 当前未运行',
    })

    renderPage()
    fireEvent.click(screen.getByRole('button', { name: '打开 Agent 设置' }))
    expect(await screen.findByText('内部网关未运行')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '启动内部网关' })).not.toBeInTheDocument()
  })

  it('creates a dedicated session and streams a reply through the user console', async () => {
    renderPage()

    expect(screen.queryByText('Profile 已连接')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '打开 Agent 设置' }))
    expect(await screen.findByText('Profile 已连接')).toBeInTheDocument()
    expect(screen.getByText('长期记忆')).toBeInTheDocument()
    expect(screen.getByText('Holographic')).toBeInTheDocument()
    expect(screen.getByText('服务器统一 Grok 订阅 · Grok 云订阅')).toBeInTheDocument()
    expect(screen.getByText('用户台数据')).toBeInTheDocument()
    expect(screen.getByText('68 个只读视图')).toBeInTheDocument()
    expect(screen.getByText('图表 Skill')).toBeInTheDocument()
    expect(screen.getByText('Lieflat Charts')).toBeInTheDocument()
    expect(await screen.findByText('市场数据复盘')).toBeInTheDocument()
    expect(screen.getByText('开始和你的专属 Agent 对话')).toBeInTheDocument()
    expect(screen.getByText('稳定关注面会记入当前账户 Profile，新对话会先读；分析框架和出图规则不会被自动改。')).toBeInTheDocument()
    expect(screen.getByTestId('hermes-composer')).toBeInTheDocument()

    fireEvent.change(screen.getByRole('textbox', { name: '发送给 Hermes Agent 的消息' }), {
      target: { value: '你好，请介绍一下你自己。' },
    })
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }))

    await waitFor(() => {
      expect(screen.getByLabelText('你的消息')).toHaveTextContent('你好，请介绍一下你自己。')
      expect(screen.getByLabelText('Hermes 的回复')).toHaveTextContent('你好，我是你的 one-trading 助理。')
    })
    expect(api.hermesCreateSession).toHaveBeenCalledTimes(1)
    expect(api.hermesCreateSession).toHaveBeenCalledWith('')
    expect(api.hermesChatStream).toHaveBeenCalledWith('api_test', '你好，请介绍一下你自己。')
    expect(localStorage.getItem('one-trading.hermes.session-id')).toBe('api_test')
    await waitFor(() => {
      expect(api.hermesRenameSession).toHaveBeenCalledWith(
        'api_test',
        expect.stringContaining('你好，请介绍一下你自己。'),
      )
    })
  })

  it('switches to a saved session from the history rail', async () => {
    vi.mocked(api.hermesSessionMessages).mockImplementation(async sessionId => ({
      session_id: sessionId,
      messages: [
        { role: 'user', content: '请总结今天的市场表现' },
        { role: 'assistant', content: '市场整体偏暖。' },
      ],
    }))
    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: '切换到历史对话：市场数据复盘' }))

    await waitFor(() => {
      expect(api.hermesSessionMessages).toHaveBeenCalledWith('api_history')
      expect(screen.getByLabelText('Hermes 的回复')).toHaveTextContent('市场整体偏暖。')
    })
    expect(localStorage.getItem('one-trading.hermes.session-id')).toBe('api_history')
  })

  it('collapses the history rail and remembers the preference', async () => {
    renderPage()

    expect(await screen.findByText('市场数据复盘')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '折叠历史对话栏' }))

    expect(localStorage.getItem('one-trading.hermes.history-collapsed')).toBe('1')
    expect(screen.getByRole('button', { name: '展开历史对话栏' })).toHaveAttribute('aria-expanded', 'false')
  })

  it('renames a saved conversation from its three-dot menu', async () => {
    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: '打开“市场数据复盘”对话菜单' }))
    fireEvent.click(screen.getByRole('menuitem', { name: '重命名' }))
    fireEvent.change(screen.getByLabelText('重命名对话标题'), {
      target: { value: '收盘复盘' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存对话标题' }))

    await waitFor(() => {
      expect(api.hermesRenameSession).toHaveBeenCalledWith('api_history', '收盘复盘')
      expect(screen.getByText('收盘复盘')).toBeInTheDocument()
    })
  })

  it('requires confirmation before deleting a saved conversation', async () => {
    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: '切换到历史对话：市场数据复盘' }))
    expect(localStorage.getItem('one-trading.hermes.session-id')).toBe('api_history')
    fireEvent.click(await screen.findByRole('button', { name: '打开“市场数据复盘”对话菜单' }))
    fireEvent.click(screen.getByRole('menuitem', { name: '删除对话' }))
    expect(screen.getByRole('dialog', { name: '确认删除“市场数据复盘”对话' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '确认删除“市场数据复盘”对话' }))

    await waitFor(() => {
      expect(api.hermesDeleteSession).toHaveBeenCalledWith('api_history')
      expect(screen.queryByText('市场数据复盘')).not.toBeInTheDocument()
    })
    expect(localStorage.getItem('one-trading.hermes.session-id')).toBeNull()
    expect(screen.getByText('开始和你的专属 Agent 对话')).toBeInTheDocument()
  })

  it('keeps regular users from changing the shared model', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: '打开 Agent 设置' }))

    expect(await screen.findByText('由管理员统一配置，当前账户不能修改。')).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: '选择模型提供商' })).not.toBeInTheDocument()
    expect(screen.getByText('服务器统一 Grok 订阅 · Grok 云订阅')).toBeInTheDocument()
  })

  it('lets an administrator switch the shared provider and model', async () => {
    settingsState = cloudSettings({ is_admin: true })
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: '打开 Agent 设置' }))

    const provider = await screen.findByRole('combobox', { name: '选择模型提供商' })
    const model = screen.getByRole('combobox', { name: '选择模型' })
    expect(provider).toHaveValue('xai')
    expect(model).toHaveValue('grok-4.5')
    expect(screen.getByText(/先保存 URL\/Key，再测试连通/)).toBeInTheDocument()

    fireEvent.change(provider, { target: { value: '86gamestore' } })
    expect(model).toHaveValue('gpt-5.6-sol')
    vi.mocked(api.selectAiSubscription).mockResolvedValue({
      ok: true,
      ai_provider: '86gamestore',
      ai_model: 'gpt-5.6-sol',
    })
    fireEvent.click(screen.getByRole('button', { name: '应用到全部账户' }))

    await waitFor(() => {
      expect(api.selectAiSubscription).toHaveBeenCalledWith({
        provider: '86gamestore',
        model: 'gpt-5.6-sol',
      })
    })
  })

  it('lets an administrator probe the selected provider before applying', async () => {
    settingsState = cloudSettings({ is_admin: true })
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: '打开 Agent 设置' }))

    const provider = await screen.findByRole('combobox', { name: '选择模型提供商' })
    fireEvent.change(provider, { target: { value: '86gamestore' } })
    vi.mocked(api.testAiSubscription).mockResolvedValue({
      ok: true,
      provider: '86gamestore',
      label: '86game',
      model: 'gpt-5.6-sol',
      response: 'OK',
    })
    fireEvent.click(screen.getByRole('button', { name: '测试连通' }))

    await waitFor(() => {
      expect(api.testAiSubscription).toHaveBeenCalledWith({
        provider: '86gamestore',
        model: 'gpt-5.6-sol',
        base_url: 'https://api.86gamestore.com/v1',
        api_key: undefined,
      })
      expect(screen.getByText('连通成功 · 86game · gpt-5.6-sol')).toBeInTheDocument()
    })
    expect(api.selectAiSubscription).not.toHaveBeenCalled()
  })

  it('keeps a failed prompt and resends it without duplicating the user bubble', async () => {
    let calls = 0
    vi.mocked(api.hermesChatStream).mockImplementation(async function* () {
      calls += 1
      if (calls === 1) {
        yield {
          type: 'error',
          message: 'API call failed after 3 retries: Our servers are currently overloaded. Please try again later.',
        }
        return
      }
      yield { type: 'delta', content: '已重新发送。' }
      yield { type: 'done', session_id: 'api_test' }
    })
    renderPage()

    expect(await screen.findByText('市场数据复盘')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: '发送给 Hermes Agent 的消息' }), {
      target: { value: '请对 300750.SZ 宁德时代做一次个股技术核对' },
    })
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }))

    expect(await screen.findByLabelText('Hermes 发送失败')).toHaveTextContent('API call failed after 3 retries')
    expect(screen.getByRole('button', { name: '重新发送这条指令' })).toBeInTheDocument()
    expect(screen.getAllByLabelText('你的消息')).toHaveLength(1)
    expect(screen.queryByLabelText('Hermes 的回复')).not.toBeInTheDocument()
    expect(api.hermesChatStream).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: '重新发送这条指令' }))

    await waitFor(() => {
      expect(api.hermesChatStream).toHaveBeenCalledTimes(2)
      expect(screen.getByLabelText('Hermes 的回复')).toHaveTextContent('已重新发送。')
    })
    expect(api.hermesChatStream).toHaveBeenNthCalledWith(
      2,
      'api_test',
      '请对 300750.SZ 宁德时代做一次个股技术核对',
    )
    expect(screen.getAllByLabelText('你的消息')).toHaveLength(1)
    expect(screen.queryByRole('button', { name: '重新发送这条指令' })).not.toBeInTheDocument()
    expect(api.hermesCreateSession).toHaveBeenCalledTimes(1)
  })

  it('lets a stored overloaded reply resend the last user instruction', async () => {
    localStorage.setItem('one-trading.hermes.session-id', 'api_history')
    vi.mocked(api.hermesSessionMessages).mockResolvedValue({
      session_id: 'api_history',
      messages: [
        { role: 'user', content: '请对 300750.SZ 宁德时代做一次个股技术核对' },
        {
          role: 'assistant',
          content: 'API call failed after 3 retries: Our servers are currently overloaded. Please try again later.',
        },
      ],
    })
    vi.mocked(api.hermesChatStream).mockImplementation(async function* () {
      yield { type: 'delta', content: '已重新发送。' }
      yield { type: 'done', session_id: 'api_history' }
    })
    renderPage()

    expect(await screen.findByLabelText('Hermes 发送失败')).toHaveTextContent('API call failed after 3 retries')
    fireEvent.click(screen.getByRole('button', { name: '重新发送这条指令' }))

    await waitFor(() => {
      expect(api.hermesChatStream).toHaveBeenCalledWith(
        'api_history',
        '请对 300750.SZ 宁德时代做一次个股技术核对',
      )
      expect(screen.getByLabelText('Hermes 的回复')).toHaveTextContent('已重新发送。')
    })
    expect(screen.getAllByLabelText('你的消息')).toHaveLength(1)
    expect(screen.queryByLabelText('Hermes 发送失败')).not.toBeInTheDocument()
    expect(api.hermesCreateSession).not.toHaveBeenCalled()
  })

  it('lets an administrator save provider URL and key from Agent settings', async () => {
    settingsState = cloudSettings({ is_admin: true })
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: '打开 Agent 设置' }))

    const provider = await screen.findByRole('combobox', { name: '选择模型提供商' })
    fireEvent.change(provider, { target: { value: '86gamestore' } })
    fireEvent.change(screen.getByLabelText('模型提供商 URL'), {
      target: { value: 'https://api.86gamestore.com/v1' },
    })
    fireEvent.change(screen.getByLabelText('模型 API Key'), {
      target: { value: 'new-86game-key' },
    })
    vi.mocked(api.saveAiSubscriptionSource).mockResolvedValue({
      ok: true,
      provider: '86gamestore',
      base_url: 'https://api.86gamestore.com/v1',
      has_api_key: true,
      api_key_masked: 'new-••••••-key',
    })
    fireEvent.click(screen.getByRole('button', { name: '保存提供商配置' }))

    await waitFor(() => {
      expect(api.saveAiSubscriptionSource).toHaveBeenCalledWith({
        provider: '86gamestore',
        base_url: 'https://api.86gamestore.com/v1',
        api_key: 'new-86game-key',
      })
      expect(screen.getByText('已保存 86game 的 URL/Key')).toBeInTheDocument()
    })
  })

  it('prefills an incoming stock context in a new conversation without sending it', async () => {
    localStorage.setItem('one-trading.hermes.session-id', 'api_history')
    renderPage('/ai/hermes?symbol=603261.SH&name=%E7%AB%8B%E8%88%AA%E7%A7%91%E6%8A%80')

    const composer = await screen.findByLabelText('发送给 Hermes Agent 的消息')
    expect(composer).toHaveValue('请分析 立航科技 603261.SH')
    expect(screen.getByLabelText('当前分析股票')).toHaveTextContent('立航科技')
    expect(screen.getByLabelText('当前分析股票')).toHaveTextContent('603261.SH')
    expect(screen.getByLabelText('当前分析股票')).toHaveTextContent('已放入新对话')
    expect(screen.getByLabelText('当前分析股票')).toHaveTextContent('稳定关注面会记入当前账户 Profile')
    expect(screen.queryByLabelText('你的消息')).not.toBeInTheDocument()
    expect(api.hermesSessionMessages).not.toHaveBeenCalled()
    expect(api.hermesChatStream).not.toHaveBeenCalled()
    expect(api.hermesCreateSession).not.toHaveBeenCalled()
    expect(localStorage.getItem('one-trading.hermes.session-id')).toBeNull()
  })

  it('keeps Agent settings open until the user clicks outside or closes it', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: '打开 Agent 设置' }))
    expect(await screen.findByRole('region', { name: 'Agent 设置详情' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '重新检查连接' }))
    expect(screen.getByRole('region', { name: 'Agent 设置详情' })).toBeInTheDocument()

    fireEvent.pointerDown(screen.getByRole('textbox', { name: '发送给 Hermes Agent 的消息' }))
    expect(screen.queryByRole('region', { name: 'Agent 设置详情' })).not.toBeInTheDocument()
  })


  it('starts a fresh conversation when embedded instead of restoring the last session', async () => {
    localStorage.setItem('one-trading.hermes.session-id', 'api_history')
    const { setPageContext, clearPageContext } = await import('@/lib/pageContext')
    setPageContext({
      route: '/concept-analysis',
      title: '概念分析',
      asOf: '2026-08-19',
      summary: '概念分析样板',
      items: [],
    })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/concept-analysis']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <HermesAgentChat embedded />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(await screen.findByText('询问当前概念分析')).toBeInTheDocument()
    expect(screen.queryByLabelText('你的消息')).not.toBeInTheDocument()
    expect(api.hermesSessionMessages).not.toHaveBeenCalled()
    expect(localStorage.getItem('one-trading.hermes.session-id')).toBe('api_history')
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }))
    await waitFor(() => {
      expect(api.hermesCreateSession).toHaveBeenCalledWith('')
      expect(api.hermesChatStream).toHaveBeenCalled()
    })
    expect(localStorage.getItem('one-trading.hermes.session-id')).toBe('api_history')
    clearPageContext()
  })

  it('attaches the current page snapshot when embedded, but keeps the visible bubble short', async () => {
    const { setPageContext, clearPageContext } = await import('@/lib/pageContext')
    setPageContext({
      route: '/limit-ladder',
      title: '连板梯队',
      asOf: '2026-08-18',
      summary: '2026-08-18 连板梯队，涨停 41 / 跌停 6',
      focus: '概念 算力',
      filters: ['limit_up', 'main'],
      items: [{ label: '3板', detail: '2 只，如 平安银行、贵州茅台' }],
      queryHint: 'limit_ladder',
    })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/limit-ladder']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <HermesAgentChat embedded />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(await screen.findByLabelText('当前页面快照')).toHaveTextContent('连板梯队')
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }))
    await waitFor(() => {
      expect(api.hermesChatStream).toHaveBeenCalled()
    })
    const sent = vi.mocked(api.hermesChatStream).mock.calls[0][1]
    expect(sent).toContain('当前页面：连板梯队')
    expect(sent).toContain('limit_ladder')
    expect(screen.getByLabelText('你的消息')).toHaveTextContent('请阅读当前连板梯队')
    expect(screen.getByLabelText('你的消息')).not.toHaveTextContent('limit_ladder')
    clearPageContext()
  })

  it('renders assistant markdown and reserved chart blocks instead of raw markup', async () => {
    vi.mocked(api.hermesSessionMessages).mockResolvedValue({
      session_id: 'api_history',
      messages: [
        { role: 'user', content: '画一下资金流' },
        {
          role: 'assistant',
          content: [
            '## 结论',
            '资金流入占优。',
            '```json',
            '{"type":"chart","template":"F1","view":"rung-bars","as_of":"2026-08-17","source":"market_overview","title":"主力净流入","points":[{"label":"光通信","value":63.08},{"label":"CPO","value":38.8}]}',
            '```',
          ].join('\n'),
        },
      ],
    })
    localStorage.setItem('one-trading.hermes.session-id', 'api_history')
    renderPage()

    const reply = await screen.findByLabelText('Hermes 的回复')
    expect(reply).toHaveTextContent('结论')
    expect(reply).toHaveTextContent('资金流入占优。')
    expect(reply).not.toHaveTextContent('## 结论')
    expect(screen.getByLabelText('Hermes 图表块')).toHaveTextContent('主力净流入')
    expect(screen.getByRole('img', { name: '主力净流入' })).toBeInTheDocument()
    expect(screen.queryByText('当前对话框还不直接渲染 HTML 或图片')).not.toBeInTheDocument()
  })

  it('turns official stock codes in assistant replies into clickable previews', async () => {
    vi.mocked(api.hermesSessionMessages).mockResolvedValue({
      session_id: 'api_history',
      messages: [
        { role: 'user', content: '请对 605289.SH 罗曼股份做一次核对' },
        {
          role: 'assistant',
          content: '当前关注 **605289.SH** 罗曼股份，同时对比 `300750.SZ`。',
        },
      ],
    })
    localStorage.setItem('one-trading.hermes.session-id', 'api_history')
    renderPage()

    const reply = await screen.findByLabelText('Hermes 的回复')
    expect(reply).toHaveTextContent('605289.SH')
    expect(reply).toHaveTextContent('300750.SZ')
    expect(screen.queryByRole('dialog', { name: '605289.SH 行情预览' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '查看 605289.SH 行情' }))
    expect(screen.getByRole('dialog', { name: '605289.SH 行情预览' })).toBeInTheDocument()
    expect(screen.getByRole('dialog', { name: '605289.SH 行情预览' })).toHaveTextContent('605289.SH')

    fireEvent.click(screen.getByRole('button', { name: '查看 300750.SZ 行情' }))
    expect(screen.getByRole('dialog', { name: '300750.SZ 行情预览' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: '605289.SH 行情预览' })).not.toBeInTheDocument()

    const userBubble = screen.getByLabelText('你的消息')
    expect(userBubble).toHaveTextContent('605289.SH')
    expect(userBubble.querySelector('button')).toBeNull()
  })

  it('quotes a selected reply excerpt into the next message', async () => {
    renderPage()
    expect(await screen.findByText('市场数据复盘')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: '发送给 Hermes Agent 的消息' }), {
      target: { value: '请先总结市场。' },
    })
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }))
    const reply = await screen.findByLabelText('Hermes 的回复')
    expect(reply).toHaveTextContent('你好，我是你的 one-trading 助理。')

    const original = window.getSelection
    window.getSelection = () => ({
      isCollapsed: false,
      toString: () => 'one-trading 助理',
      anchorNode: reply,
      focusNode: reply,
      removeAllRanges: () => {},
    }) as unknown as Selection
    const bubble = reply.querySelector('div.rounded-btn') ?? reply
    fireEvent.mouseUp(bubble)
    window.getSelection = original

    expect(screen.queryByLabelText('选中文本操作')).not.toBeInTheDocument()
    const capsule = await screen.findByLabelText('引用原文')
    expect(capsule).toHaveTextContent('1 条引用')
    const markButton = await screen.findByRole('button', { name: '查看第 1 条引用' })
    expect(markButton.closest('mark')).toHaveTextContent('one-trading 助理')
    const inlineInput = await screen.findByLabelText('第 1 条引用的追问')
    expect(screen.getByRole('button', { name: '删除第 1 条引用' })).toBeInTheDocument()
    fireEvent.mouseEnter(capsule)
    expect(screen.getByLabelText('引用预览')).toHaveTextContent('one-trading 助理')

    fireEvent.change(inlineInput, { target: { value: '这段是什么意思？' } })
    fireEvent.click(screen.getByRole('button', { name: '发送第 1 条引用' }))

    await waitFor(() => {
      expect(api.hermesChatStream).toHaveBeenLastCalledWith(
        'api_test',
        '引用：\n1. one-trading 助理\n\n这段是什么意思？',
      )
    })
    expect(screen.queryByLabelText('引用原文')).not.toBeInTheDocument()
  })

  it('removes an in-text quote from the inline composer', async () => {
    renderPage()
    expect(await screen.findByText('市场数据复盘')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: '发送给 Hermes Agent 的消息' }), {
      target: { value: '请先总结市场。' },
    })
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }))
    const reply = await screen.findByLabelText('Hermes 的回复')

    const original = window.getSelection
    window.getSelection = () => ({
      isCollapsed: false,
      toString: () => 'one-trading 助理',
      anchorNode: reply,
      focusNode: reply,
      removeAllRanges: () => {},
    }) as unknown as Selection
    const bubble = reply.querySelector('div.rounded-btn') ?? reply
    fireEvent.mouseUp(bubble)
    window.getSelection = original

    expect(await screen.findByLabelText('第 1 条引用的追问')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '删除第 1 条引用' }))
    expect(screen.queryByLabelText('第 1 条引用的追问')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('引用原文')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '查看第 1 条引用' })).not.toBeInTheDocument()
  })

  it('keeps the inline quote composer inside the AI panel while dragging', async () => {
    renderPage()
    expect(await screen.findByText('市场数据复盘')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: '发送给 Hermes Agent 的消息' }), {
      target: { value: '请先总结市场。' },
    })
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }))
    const reply = await screen.findByLabelText('Hermes 的回复')

    const original = window.getSelection
    window.getSelection = () => ({
      isCollapsed: false,
      toString: () => 'one-trading 助理',
      anchorNode: reply,
      focusNode: reply,
      removeAllRanges: () => {},
    }) as unknown as Selection
    const bubble = reply.querySelector('div.rounded-btn') ?? reply
    fireEvent.mouseUp(bubble)
    window.getSelection = original

    const composer = await screen.findByRole('dialog', { name: '第 1 条引用的追问框' })
    const bounds = screen.getByTestId('hermes-bounds').getBoundingClientRect()
    const handle = screen.getByLabelText('拖动第 1 条引用的追问框')
    fireEvent.pointerDown(handle, { pointerId: 1, clientX: 40, clientY: 40, button: 0 })
    fireEvent.pointerMove(handle, { pointerId: 1, clientX: 4000, clientY: 4000 })
    fireEvent.pointerUp(handle, { pointerId: 1, clientX: 4000, clientY: 4000 })
    const box = composer.getBoundingClientRect()
    expect(box.left).toBeGreaterThanOrEqual(bounds.left)
    expect(box.right).toBeLessThanOrEqual(bounds.right + 1)
    expect(box.top).toBeGreaterThanOrEqual(bounds.top)
    expect(box.bottom).toBeLessThanOrEqual(bounds.bottom + 1)
  })

  it('saves an embedded page analysis after the reply finishes', async () => {
    const { setPageContext, clearPageContext } = await import('@/lib/pageContext')
    setPageContext({
      route: '/limit-ladder',
      title: '连板梯队',
      asOf: '2026-08-19',
      summary: '连板梯队样板',
      items: [],
    })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/limit-ladder']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <HermesAgentChat embedded />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    fireEvent.click(await screen.findByRole('button', { name: '发送消息' }))
    await waitFor(() => {
      expect(api.pageAiReportSave).toHaveBeenCalled()
    })
    expect(screen.queryByRole('link', { name: '查看历史' })).not.toBeInTheDocument()
    expect(screen.getByLabelText('当前页面快照')).toHaveTextContent('连板梯队')
    expect(screen.getByLabelText('当前页面快照')).not.toHaveTextContent('结构化快照')
    clearPageContext()
  })

})
