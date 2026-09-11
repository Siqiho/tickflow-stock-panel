import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AdminUsers } from '@/pages/AdminUsers'
import { api } from '@/lib/api'


describe('administrator user console', () => {
  afterEach(() => vi.restoreAllMocks())

  it('shows AI usage and reads one user Profile without a reason gate', async () => {
    vi.spyOn(api, 'adminUsers').mockResolvedValue({
      summary: {
        total_accounts: 2,
        regular_users: 1,
        active_users_today: 1,
        ai_requests_today: 3,
        profiles_ready: 1,
      },
      users: [
        {
          id: 'owner',
          username: 'admin',
          role: 'admin',
          status: 'active',
          ai_daily_limit: null,
          created_at: 100,
          updated_at: 100,
          profile_name: 'ot-owner',
          profile_status: 'ready',
          ai_requests_today: 0,
          ai_requests_7d: 0,
          active_login_sessions: 1,
          conversation_count: 2,
          conversation_count_capped: false,
          profile_runtime_status: 'ready',
          strategy_count: 0,
        },
        {
          id: 'usr_alice',
          username: 'alice',
          role: 'user',
          status: 'active',
          ai_daily_limit: 20,
          created_at: 100,
          updated_at: 100,
          profile_name: 'ot-usr_alice',
          profile_status: 'ready',
          ai_requests_today: 3,
          ai_requests_7d: 8,
          active_login_sessions: 1,
          last_login_at: 150,
          conversation_count: 1,
          last_conversation_at: 200,
          conversation_count_capped: false,
          profile_runtime_status: 'ready',
          strategy_count: 1,
        },
      ],
    })
    const sessions = vi.spyOn(api, 'adminUserSessions').mockResolvedValue({
      user: { id: 'usr_alice', username: 'alice', role: 'user' },
      sessions: [{
        id: 'session-1',
        title: '如何分析这只股票？',
        preview: '如何分析这只股票？',
        message_count: 2,
        last_active: 200,
      }],
      has_more: false,
    })
    const messages = vi.spyOn(api, 'adminUserMessages').mockResolvedValue({
      user: { id: 'usr_alice', username: 'alice', role: 'user' },
      session_id: 'session-1',
      messages: [
        { id: 'u1', role: 'user', content: '如何分析这只股票？', timestamp: 201 },
        { id: 'a1', role: 'assistant', content: '可以先分析基本面。', timestamp: 202 },
      ],
    })
    const userStrategies = vi.spyOn(api, 'adminUserStrategies').mockResolvedValue({
      user: { id: 'usr_alice', username: 'alice', role: 'user' },
      strategies: [{
        id: 'ai_alpha',
        name: '站上均线',
        description: '收盘价高于 MA20',
        source: 'ai',
        rules: '收盘价高于二十日均线',
        updated_at: '2026-08-11T06:00:00+00:00',
      }],
    })

    render(<AdminUsers />)

    expect((await screen.findAllByText('alice')).length).toBeGreaterThanOrEqual(1)
    expect((await screen.findAllByText('账号正常')).length).toBeGreaterThanOrEqual(1)
    const readButton = screen.getByRole('button', { name: '读取历史对话' })
    expect(readButton).toBeEnabled()
    expect(screen.queryByText(/审查原因|审查记录|填写原因/)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '读取用户策略' }))
    await waitFor(() => expect(userStrategies).toHaveBeenCalledWith('usr_alice'))
    expect(await screen.findByText('站上均线')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /管理员回测/ })).toHaveAttribute(
      'href',
      '/backtest?strategy_id=ai_alpha&strategy_owner_user_id=usr_alice',
    )

    fireEvent.click(readButton)

    await waitFor(() => expect(sessions).toHaveBeenCalledWith('usr_alice'))
    fireEvent.click(await screen.findByRole('button', { name: /如何分析这只股票/ }))
    await waitFor(() => expect(messages).toHaveBeenCalledWith(
      'usr_alice',
      'session-1',
    ))
    expect(await screen.findByText('可以先分析基本面。')).toBeInTheDocument()
  })
})
