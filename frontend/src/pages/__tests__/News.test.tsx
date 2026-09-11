import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/lib/api'
import { News } from '../News'

const marketFixture = {
  timezone: 'Asia/Shanghai',
  sources: {
    cls: {
      source: 'cls' as const,
      label: '财联社电报',
      ok: true,
      error: null,
      items: [{
        id: 'cls:1',
        source: '财联社电报',
        title: '央行加息',
        content: '利好',
        time: '10:00:01',
        data_time: '2026-09-09T10:00:01+08:00',
        url: 'https://www.cls.cn/telegraph/1',
        subjects: ['宏观'],
        stocks: [],
        is_red: true,
        sentiment: '看涨',
      }],
    },
    sina: {
      source: 'sina' as const,
      label: '新浪财经',
      ok: false,
      error: 'timeout',
      preserved: true,
      items: [{
        id: 'sina:1',
        source: '新浪财经',
        title: '旧快讯',
        content: '上次数据',
        time: '09:00:00',
        data_time: '2026-09-09T09:00:00+08:00',
        url: '',
        subjects: [],
        stocks: [],
        is_red: false,
        sentiment: '中性',
      }],
    },
    foreign: {
      source: 'foreign' as const,
      label: '外媒',
      ok: true,
      error: null,
      items: [],
    },
  },
}

function renderNews(initial = '/news') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <MemoryRouter initialEntries={[initial]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path="/news" element={<News />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  )
  return client
}

describe('News page', () => {
  beforeEach(() => {
    vi.spyOn(api, 'newsMarket').mockResolvedValue(marketFixture)
    vi.spyOn(api, 'newsRefreshMarket').mockResolvedValue(marketFixture)
    vi.spyOn(api, 'newsPolicy').mockResolvedValue({
      items: [{ title: '能源局发布新能源政策', url: 'https://www.nea.gov.cn/a', date: '2026-09-08', source: '国家能源局' }],
      total: 1,
      page: 1,
      page_size: 100,
      has_more: false,
      search_mode: false,
      department: '',
      keyword: '',
    })
    vi.spyOn(api, 'newsDepartments').mockResolvedValue({
      departments: [{ name: '国家能源局', url: 'https://www.nea.gov.cn/' }],
      count: 1,
      ok: true,
    })
    vi.spyOn(api, 'newsKeyDepartments').mockResolvedValue({
      departments: ['国家能源局'],
      is_default: false,
      defaults: ['中国人民银行'],
    })
    vi.spyOn(api, 'newsRefreshPolicy').mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 100,
      has_more: false,
      search_mode: false,
      department: '',
      keyword: '',
    })
    vi.spyOn(api, 'newsRefreshDepartments').mockResolvedValue({
      departments: [{ name: '国家能源局', url: 'https://www.nea.gov.cn/' }],
      count: 1,
      ok: true,
    })
    vi.spyOn(api, 'newsSaveKeyDepartments').mockResolvedValue({
      departments: ['国家能源局'],
      is_default: false,
      defaults: ['中国人民银行'],
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders three market columns and keeps a failed source visible', async () => {
    renderNews()
    expect(await screen.findByRole('heading', { name: '资讯' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '市场快讯' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '政策信息' })).toBeInTheDocument()
    expect(await screen.findByText('央行加息')).toBeInTheDocument()
    expect(screen.getByText('本源失败，仍显示上次数据')).toBeInTheDocument()
    expect(screen.getByText('旧快讯')).toBeInTheDocument()
    expect(screen.getByText('外媒')).toBeInTheDocument()
  })

  it('refreshes one market source with POST', async () => {
    renderNews()
    await screen.findByText('央行加息')
    fireEvent.click(screen.getByRole('button', { name: '刷新财联社电报' }))
    await waitFor(() => {
      expect(api.newsRefreshMarket).toHaveBeenCalledWith('cls')
    })
  })

  it('searches stored policy locally without posting', async () => {
    renderNews('/news?tab=policy')
    expect(await screen.findByText('能源局发布新能源政策')).toBeInTheDocument()
    fireEvent.change(screen.getByPlaceholderText('关键词搜索历史政策'), { target: { value: '新能源' } })
    fireEvent.click(screen.getByRole('button', { name: '搜索' }))
    await waitFor(() => {
      expect(api.newsPolicy).toHaveBeenCalled()
    })
    expect(api.newsRefreshPolicy).not.toHaveBeenCalled()
    const lastCall = vi.mocked(api.newsPolicy).mock.calls.at(-1)?.[0]
    expect(lastCall?.keyword).toBe('新能源')
  })

  it('keeps the stored-search keyword when changing department', async () => {
    renderNews('/news?tab=policy')
    await screen.findByText('能源局发布新能源政策')
    fireEvent.change(screen.getByPlaceholderText('关键词搜索历史政策'), { target: { value: '新能源' } })
    fireEvent.click(screen.getByRole('button', { name: '搜索' }))
    fireEvent.click(screen.getByRole('button', { name: '国家能源局' }))
    await waitFor(() => {
      const calls = vi.mocked(api.newsPolicy).mock.calls.map(call => call[0])
      expect(calls.some(opts => opts?.department === '国家能源局' && opts?.keyword === '新能源')).toBe(true)
    })
    expect(api.newsRefreshPolicy).not.toHaveBeenCalled()
    expect(screen.getByPlaceholderText('关键词搜索历史政策')).toHaveValue('新能源')
  })

  it('refreshing policy uses POST and keeps department filter', async () => {
    renderNews('/news?tab=policy')
    await screen.findByText('能源局发布新能源政策')
    fireEvent.click(screen.getByRole('button', { name: '国家能源局' }))
    fireEvent.click(screen.getByRole('button', { name: /刷新/ }))
    await waitFor(() => {
      expect(api.newsRefreshPolicy).toHaveBeenCalledWith('国家能源局')
    })
  })

  // jsdom cannot compute real viewport geometry. This is a class-contract
  // regression only; chief IAB must verify >=320px visible results at 678x863.
  it('keeps a single-column policy results min-height contract so the sidebar cannot crush the list', async () => {
    renderNews('/news?tab=policy')
    expect(await screen.findByText('能源局发布新能源政策')).toBeInTheDocument()

    const search = screen.getByPlaceholderText('关键词搜索历史政策')
    const results = search.closest('section')
    expect(results).toBeTruthy()
    expect(results).toHaveClass('min-h-[20rem]', 'lg:min-h-0')

    const grid = results?.parentElement
    expect(grid).toBeTruthy()
    expect(grid).toHaveClass(
      'grid-cols-1',
      'grid-rows-[minmax(0,auto)_minmax(20rem,1fr)]',
      'max-lg:overflow-y-auto',
      'lg:grid-cols-[13rem_minmax(0,1fr)]',
      'lg:grid-rows-none',
    )

    const aside = grid?.querySelector('aside')
    expect(aside).toBeTruthy()
    expect(aside).toHaveClass('max-lg:max-h-[min(22rem,40vh)]', 'max-lg:overflow-y-auto')

    expect(screen.getByRole('button', { name: '自定义重点部门' })).toBeInTheDocument()
    expect(screen.getByPlaceholderText('搜索全部部门')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /刷新/ })).toBeInTheDocument()
    expect(screen.getByText('2026-09-08')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '原文' })).toBeInTheDocument()
  })
})
