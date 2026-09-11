import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { SettingsState } from '@/lib/api'
import { SettingsAIPanel } from './AI'

let settingsState: SettingsState

vi.mock('@/lib/useSharedQueries', () => ({
  useSettings: () => ({ data: settingsState }),
}))

function cloudSettings(): SettingsState {
  return {
    mode: 'free', tickflow_api_key_masked: '', has_tickflow_key: false, tier_label: 'Free', current_endpoint: '',
    probe_log: [], missing_caps: [], extras_caps: [], onboarding_completed: true,
    ai_provider: 'xai', ai_base_url: '', ai_api_key_masked: '', has_ai_key: false,
    ai_configured: false, ai_model: 'grok-4.5', ai_user_agent: '',
    ai_xai: { auth_type: 'server_managed', has_oauth: false, has_access_token: false, expired: false },
    ai_access: {
      mode: 'cloud_subscription', state: 'service_unavailable', allowed: false, entitled: true, configured: false,
      provider: 'xai', model: 'grok-4.5', plan: 'AI Pro', message: '云端 Grok 服务尚未完成配置', credential_source: null,
    },
  }
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><SettingsAIPanel /></QueryClientProvider>)
}

beforeEach(() => {
  settingsState = cloudSettings()
})

describe('cloud AI server login', () => {
  it('shows the server OAuth login only in a normal browser', () => {
    Object.defineProperty(window.navigator, 'userAgent', { configurable: true, value: 'Mozilla/5.0 Chrome/131.0' })
    renderPanel()

    expect(screen.getByRole('button', { name: '登录服务器 Grok' })).toBeInTheDocument()
    expect(screen.getByText(/持久化到私人 Zeabur 数据卷/)).toBeInTheDocument()
  })

  it('keeps the Android APK read-only', () => {
    Object.defineProperty(window.navigator, 'userAgent', { configurable: true, value: 'Mozilla/5.0 one-trading-android/0.1.68' })
    renderPanel()

    expect(screen.queryByRole('button', { name: /登录服务器 Grok/ })).not.toBeInTheDocument()
    expect(screen.getByText('订阅权限已识别，等待服务器管理员完成 Grok 登录。')).toBeInTheDocument()
  })

  it('shows 86game and Subrouter as extra hosted sources', () => {
    Object.defineProperty(window.navigator, 'userAgent', { configurable: true, value: 'Mozilla/5.0 Chrome/131.0' })
    settingsState = {
      ...cloudSettings(),
      ai_subscriptions: [
        {
          provider: 'xai', label: 'Grok', website: 'https://accounts.x.ai/', website_label: 'accounts.x.ai',
          description: 'Grok', base_url: 'https://api.x.ai/v1', default_model: 'grok-4.5',
          models: ['grok-4.5'], ready: false, active: true, model: 'grok-4.5', credential_source: null,
          message: '云端 Grok 服务尚未完成配置',
        },
        {
          provider: '86gamestore', label: '86game', website: 'https://api.86gamestore.com/', website_label: 'api.86gamestore.com',
          description: '86game', base_url: 'https://api.86gamestore.com/v1', default_model: 'gpt-5.6-sol',
          models: ['gpt-5.6-sol', 'gpt-5.6-terra'], ready: true, active: false, model: 'gpt-5.6-sol', credential_source: 'api_key',
          message: '云端 86game 已连接',
        },
        {
          provider: 'subrouter', label: 'Subrouter', website: 'https://subrouter.ai/', website_label: 'subrouter.ai',
          description: 'Subrouter', base_url: 'https://subrouter.ai/v1', default_model: 'gpt-5.6-sol',
          models: ['gpt-5.6-sol'], ready: true, active: false, model: 'gpt-5.6-sol', credential_source: 'api_key',
          message: '云端 Subrouter 已连接',
        },
      ],
    }
    renderPanel()

    expect(screen.getByText('订阅源')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '86game' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Subrouter' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '登录服务器 Grok' })).toBeInTheDocument()
  })
})
