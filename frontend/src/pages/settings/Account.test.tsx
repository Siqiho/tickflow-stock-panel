import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, type AuthStatus } from '@/lib/api'
import { SettingsAccountPanel } from './Account'

function renderPanel(status: Promise<AuthStatus>) {
  vi.spyOn(api, 'authStatus').mockReturnValue(status)
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <SettingsAccountPanel />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('SettingsAccountPanel', () => {
  afterEach(() => vi.restoreAllMocks())

  it('shows a real loading state only while auth status is pending', () => {
    renderPanel(new Promise(() => undefined))

    expect(screen.getByText('加载中…')).toBeInTheDocument()
    expect(screen.queryByText('本地管理员')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '退出登录' })).not.toBeInTheDocument()
  })

  it('renders the passwordless local owner instead of staying on loading', async () => {
    renderPanel(Promise.resolve({
      configured: false,
      authenticated: false,
      multi_user: true,
      registration_enabled: false,
      user: null,
      ai_quota: null,
    }))

    expect(await screen.findByText('本地管理员')).toBeInTheDocument()
    expect(screen.getByText('尚未设置访问密码')).toBeInTheDocument()
    expect(screen.queryByText('加载中…')).not.toBeInTheDocument()
    expect(screen.queryByText('独立用户空间')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '退出登录' })).not.toBeInTheDocument()
    expect(screen.getByText('设置访问密码')).toBeInTheDocument()
    expect(screen.queryByPlaceholderText('当前密码')).not.toBeInTheDocument()
  })

  it('keeps the normal signed-in administrator controls', async () => {
    renderPanel(Promise.resolve({
      configured: true,
      authenticated: true,
      multi_user: true,
      user: { id: 'owner', username: 'admin', role: 'admin' },
      ai_quota: null,
    }))

    expect(await screen.findByText('admin')).toBeInTheDocument()
    expect(screen.getByText('服务器管理员')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '退出登录' })).toBeInTheDocument()
    expect(screen.getByText('修改密码')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('当前密码')).toBeInTheDocument()
  })

  it('shows an explicit error instead of a permanent loading label', async () => {
    renderPanel(Promise.reject(new Error('身份接口不可用')))

    expect(await screen.findByText('账号信息加载失败')).toBeInTheDocument()
    expect(screen.getByText('身份接口不可用')).toBeInTheDocument()
    expect(screen.queryByText('加载中…')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '退出登录' })).not.toBeInTheDocument()
  })
})
