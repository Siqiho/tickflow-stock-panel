import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SettingsMenuSettingsPanel } from '../MenuSettings'

const mockState = vi.hoisted(() => ({
  settings: { is_admin: true } as { is_admin?: boolean } | undefined,
  preferences: {
    nav_order: [] as string[],
    nav_hidden: [] as string[],
  },
  saveHidden: vi.fn(async (hidden: string[]) => ({ nav_hidden: hidden })),
}))

vi.mock('@/lib/useSharedQueries', () => ({
  useSettings: () => ({ data: mockState.settings }),
  usePreferences: () => ({ data: mockState.preferences }),
}))

vi.mock('@/lib/api', () => ({
  api: {
    analysisMenus: vi.fn(async () => ({ items: [{ id: 'ext-one', label: '扩展一', visible: true }] })),
    saveNavOrder: vi.fn(async (order: string[]) => ({ nav_order: order })),
    saveNavHidden: (hidden: string[]) => mockState.saveHidden(hidden),
  },
}))

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <SettingsMenuSettingsPanel />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('SettingsMenuSettingsPanel groups', () => {
  beforeEach(() => {
    mockState.settings = { is_admin: true }
    mockState.preferences.nav_order = []
    mockState.preferences.nav_hidden = []
    mockState.saveHidden.mockClear()
    localStorage.removeItem('monitor_badge_enabled')
  })

  it('shows merged group entries instead of the old member pages', async () => {
    renderPanel()
    expect(await screen.findByText('量化')).toBeInTheDocument()
    expect(screen.getAllByText('交易')[0]).toBeInTheDocument()
    expect(screen.queryByText('/screener')).not.toBeInTheDocument()
    expect(screen.queryByText('/monitor')).not.toBeInTheDocument()
    expect(screen.getByText('/quant')).toBeInTheDocument()
    expect(screen.getByText('/trade')).toBeInTheDocument()
    expect(await screen.findByText('扩展一')).toBeInTheDocument()
  })

  it('does not treat a leftover /trading hide as hiding the whole trade group', async () => {
    mockState.preferences.nav_hidden = ['/trading']
    renderPanel()
    expect(await screen.findByText('/trade')).toBeInTheDocument()
    const tradeRow = screen.getByText('/trade').closest('div')?.parentElement
    expect(tradeRow).not.toHaveTextContent('已隐藏')
    expect(screen.getByRole('button', { name: '恢复 交易' })).toBeInTheDocument()
  })

  it('can restore a fully hidden group and points the badge switch at /trade', async () => {
    mockState.preferences.nav_hidden = ['/monitor', '/lots', '/signals', '/abnormal', '/trading']
    renderPanel()
    const tradeId = await screen.findByText('/trade')
    expect(tradeId.closest('div')).toHaveTextContent('已隐藏')
    fireEvent.click(screen.getAllByTitle('显示')[0])
    await waitFor(() => expect(mockState.saveHidden).toHaveBeenCalled())
    const saved = mockState.saveHidden.mock.calls.at(-1)?.[0] as string[]
    expect(saved).not.toContain('/trade')
    expect(saved).not.toContain('/lots')
    fireEvent.click(screen.getByTitle('关闭数字提示'))
    expect(localStorage.getItem('monitor_badge_enabled')).toBe('0')
  })

  it('keeps monitor recovery out of a non-admin menu', async () => {
    mockState.settings = { is_admin: false }
    mockState.preferences.nav_hidden = ['/monitor']
    renderPanel()
    expect(await screen.findByText('/trade')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '恢复 监控中心' })).not.toBeInTheDocument()
    expect(screen.queryByText('用户管理')).not.toBeInTheDocument()
  })
})
