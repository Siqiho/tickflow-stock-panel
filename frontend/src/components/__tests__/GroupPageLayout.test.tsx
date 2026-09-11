import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { GroupEntryRedirect, GroupPageLayout } from '../GroupPageLayout'

const mockState = vi.hoisted(() => ({
  settings: { is_admin: true } as { is_admin?: boolean } | undefined,
  settingsLoading: false,
  preferences: {
    nav_order: [] as string[],
    nav_hidden: [] as string[],
  },
}))

vi.mock('@/lib/useSharedQueries', () => ({
  useSettings: () => ({
    data: mockState.settings,
    isLoading: mockState.settingsLoading,
  }),
  usePreferences: () => ({ data: mockState.preferences }),
}))

function ChildProbe({ label }: { label: string }) {
  const location = useLocation()
  return (
    <>
      <div>{label}</div>
      <div data-testid="group-child-location">
        {JSON.stringify({
          pathname: location.pathname,
          search: location.search,
          hash: location.hash,
          state: location.state,
        })}
      </div>
    </>
  )
}

function renderGroup(initial: string | { pathname: string; search?: string; hash?: string; state?: unknown }) {
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
          <Route path="/quant" element={<GroupEntryRedirect groupId="quant" />} />
          <Route element={<GroupPageLayout groupId="quant" />}>
            <Route path="/screener" element={<ChildProbe label="策略页" />} />
            <Route path="/backtest" element={<ChildProbe label="回测页" />} />
            <Route path="/factors" element={<ChildProbe label="因子页" />} />
          </Route>
          <Route path="/trade" element={<GroupEntryRedirect groupId="trade" />} />
          <Route element={<GroupPageLayout groupId="trade" />}>
            <Route path="/monitor" element={<div>监控页</div>} />
            <Route path="/lots" element={<div>持仓页</div>} />
            <Route path="/signals" element={<div>信号页</div>} />
            <Route path="/abnormal" element={<div>异动页</div>} />
            <Route path="/trading" element={<div>交易页</div>} />
          </Route>
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('GroupPageLayout', () => {
  beforeEach(() => {
    mockState.settings = { is_admin: true }
    mockState.settingsLoading = false
    mockState.preferences.nav_hidden = []
  })

  it('keeps child query and hash when switching is path-based, not ?tab=', async () => {
    renderGroup('/backtest?tab=robustness#section')
    expect(await screen.findByRole('link', { name: '回测' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: '策略' })).not.toHaveAttribute('aria-current')
    expect(screen.getByTestId('group-child-location')).toHaveTextContent('/backtest')
    expect(screen.getByTestId('group-child-location')).toHaveTextContent('?tab=robustness')
    expect(screen.getByTestId('group-child-location')).toHaveTextContent('#section')
    expect(screen.getByTestId('group-page-tabs')).toHaveClass('overflow-x-auto')
    expect(screen.getByTestId('group-page-layout')).toHaveClass('h-full', 'min-h-0', 'overflow-hidden')
    expect(screen.queryByRole('tab')).not.toBeInTheDocument()
  })

  it('keeps search, hash, and state when clicking the already-active group tab', () => {
    renderGroup({
      pathname: '/factors',
      search: '?tab=library',
      hash: '#row',
      state: { from: 'mining' },
    })
    fireEvent.click(screen.getByRole('link', { name: '因子' }))
    expect(JSON.parse(screen.getByTestId('group-child-location').textContent ?? '')).toEqual({
      pathname: '/factors',
      search: '?tab=library',
      hash: '#row',
      state: { from: 'mining' },
    })
    expect(screen.getByRole('link', { name: '因子' })).toHaveAttribute('aria-current', 'page')
  })

  it('sends an inactive group tab to a bare path without carrying ?tab= or state', () => {
    renderGroup({
      pathname: '/factors',
      search: '?tab=library',
      hash: '#row',
      state: { from: 'mining' },
    })
    fireEvent.click(screen.getByRole('link', { name: '策略' }))
    expect(screen.getByText('策略页')).toBeInTheDocument()
    expect(JSON.parse(screen.getByTestId('group-child-location').textContent ?? '')).toEqual({
      pathname: '/screener',
      search: '',
      hash: '',
      state: null,
    })
  })

  it('sends /quant to the first visible quant tab', async () => {
    renderGroup('/quant')
    expect(await screen.findByText('策略页')).toBeInTheDocument()
  })

  it('sends an admin /trade landing to monitor', async () => {
    renderGroup('/trade')
    expect(await screen.findByText('监控页')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '监控中心' })).toHaveAttribute('aria-current', 'page')
  })

  it('does not expose monitor to a non-admin trade landing', async () => {
    mockState.settings = { is_admin: false }
    renderGroup('/trade')
    expect(await screen.findByText('持仓页')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '监控中心' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: '风控 · 异动监控' })).toBeInTheDocument()
  })

  it('waits for settings before showing admin trade tabs', () => {
    mockState.settings = undefined
    mockState.settingsLoading = true
    renderGroup('/trade')
    expect(screen.getByText('加载中…')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '监控中心' })).not.toBeInTheDocument()
    expect(screen.queryByText('监控页')).not.toBeInTheDocument()
  })

  it('hides a legacy member tab without dropping the rest of the group', async () => {
    mockState.preferences.nav_hidden = ['/signals']
    renderGroup('/lots')
    expect(await screen.findByText('持仓页')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '信号库' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: '持仓提醒' })).toBeInTheDocument()
  })

  it('lands on the next visible trade tab when monitor is hidden', async () => {
    mockState.preferences.nav_hidden = ['/monitor']
    renderGroup('/trade')
    expect(await screen.findByText('持仓页')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '监控中心' })).not.toBeInTheDocument()
  })
})
