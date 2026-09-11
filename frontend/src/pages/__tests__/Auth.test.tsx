import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Auth } from '@/pages/Auth'
import { api } from '@/lib/api'


function renderAuth() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route path="/login" element={<Auth />} />
          <Route path="/admin/users" element={<div>管理员专属界面</div>} />
          <Route path="/" element={<div>普通用户工作台</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}


describe('multi-user auth', () => {
  afterEach(() => vi.restoreAllMocks())

  it('offers public registration only when the server enables it', async () => {
    localStorage.setItem('strategy-draft', '{"owner":"previous-user"}')
    vi.spyOn(api, 'authStatus').mockResolvedValue({
      configured: true,
      authenticated: false,
      multi_user: true,
      registration_enabled: true,
      invite_required: false,
    })
    const register = vi.spyOn(api, 'authRegister').mockResolvedValue({
      ok: true,
      user: { id: 'usr_1', username: 'alice', role: 'user' },
    })

    renderAuth()
    fireEvent.click(await screen.findByText('没有账号？创建一个'))
    fireEvent.change(screen.getByPlaceholderText('用户名（3-32 位）'), { target: { value: 'alice' } })
    fireEvent.change(screen.getByPlaceholderText('访问密码'), { target: { value: 'abc123' } })
    fireEvent.change(screen.getByPlaceholderText('再次输入密码'), { target: { value: 'abc123' } })
    fireEvent.click(screen.getByRole('button', { name: '注册并进入' }))

    await waitFor(() => expect(register).toHaveBeenCalledWith('alice', 'abc123', ''))
    await waitFor(() => expect(localStorage.getItem('strategy-draft')).toBeNull())
  })

  it('keeps registration hidden when the deployment gate is disabled', async () => {
    vi.spyOn(api, 'authStatus').mockResolvedValue({
      configured: true,
      authenticated: false,
      multi_user: true,
      registration_enabled: false,
    })

    renderAuth()

    expect(await screen.findByText('登录访问')).toBeInTheDocument()
    expect(screen.queryByText('没有账号？创建一个')).not.toBeInTheDocument()
  })

  it('uses the shared login form and sends the administrator to the dedicated interface', async () => {
    vi.spyOn(api, 'authStatus').mockResolvedValue({
      configured: true,
      authenticated: false,
      multi_user: true,
      registration_enabled: true,
    })
    const login = vi.spyOn(api, 'authLogin').mockResolvedValue({
      ok: true,
      authenticated: true,
      user: { id: 'owner', username: 'admin', role: 'admin' },
    })

    renderAuth()
    fireEvent.change(
      await screen.findByPlaceholderText('用户名（管理员与普通用户均需填写）'),
      { target: { value: 'admin' } },
    )
    fireEvent.change(screen.getByPlaceholderText('访问密码'), { target: { value: 'owner-secret' } })
    fireEvent.click(screen.getByRole('button', { name: '登录' }))

    await waitFor(() => expect(login).toHaveBeenCalledWith('owner-secret', 'admin'))
    expect(await screen.findByText('管理员专属界面')).toBeInTheDocument()
  })
})
