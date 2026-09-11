import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { StockAnalysis } from '@/pages/StockAnalysis'
import { api, type LevelType, type PriceLevel } from '@/lib/api'
import { StockAnalysisHost } from '@/components/stock-analysis/StockAnalysisHost'
import { resetStockAnalysisStore } from '@/lib/stockAnalysisStore'

function renderPage(entry = '/stock-analysis?symbol=300204.SZ&name=%E8%88%92%E6%B3%B0%E7%A5%9E') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  render(
    <MemoryRouter
      initialEntries={[entry]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <QueryClientProvider client={client}>
        <StockAnalysis />
        <StockAnalysisHost />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  localStorage.setItem(
    'last_stock:stock-analysis',
    JSON.stringify({ symbol: '000001.SZ', name: '平安银行' }),
  )
  vi.spyOn(api, 'klineDaily').mockResolvedValue({
    symbol: '300204.SZ',
    rows: [],
    source: 'none',
  })
  vi.spyOn(api, 'stockAnalysisLevels').mockResolvedValue({
    symbol: '300204.SZ',
    levels: {} as Record<LevelType, PriceLevel[]>,
    close: null,
    summary: '',
  })
  vi.spyOn(api, 'stockAnalysisReportsList').mockResolvedValue({ reports: [] })
})

afterEach(() => {
  resetStockAnalysisStore()
  localStorage.clear()
  vi.restoreAllMocks()
})

it('auto-selects the URL stock instead of the previously remembered stock', async () => {
  renderPage()

  const selectedStock = await screen.findByTitle('查看个股日 K 详情')
  expect(selectedStock).toHaveTextContent('舒泰神')
  expect(selectedStock).toHaveTextContent('300204.SZ')
  expect(await screen.findByRole('button', { name: '最近查看：舒泰神 300204.SZ' })).toHaveAttribute('aria-current', 'true')
  expect(screen.getByRole('button', { name: '最近查看：平安银行 000001.SZ' })).toBeInTheDocument()
  await waitFor(() => {
    expect(api.klineDaily).toHaveBeenCalledWith('300204.SZ', 250)
  })
})

it('restores the exact saved report from a history deep link', async () => {
  vi.mocked(api.stockAnalysisReportsList).mockResolvedValue({
    reports: [{
      id: 'sar-history-1',
      symbol: '300204.SZ',
      name: '舒泰神',
      focus: '',
      content: '深链恢复的个股报告正文',
      summary: '深链报告摘要',
      created_at: '2026-08-01T22:00:00+08:00',
    }],
  })

  renderPage('/stock-analysis?symbol=300204.SZ&name=%E8%88%92%E6%B3%B0%E7%A5%9E&report=sar-history-1')

  expect(await screen.findByText('深链恢复的个股报告正文')).toBeInTheDocument()
  expect(screen.getByText('深链报告摘要')).toBeInTheDocument()
  expect(screen.getByLabelText('该股票历史分析列表')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '返回分析' })).toHaveAttribute('aria-pressed', 'true')
})

it('removes the duplicate header stock and lets the recent module collapse', async () => {
  renderPage('/stock-analysis?symbol=002384.SZ&name=%E4%B8%9C%E5%B1%B1%E7%B2%BE%E5%AF%86')

  expect(screen.queryByTitle('继续查看 东山精密')).not.toBeInTheDocument()

  const collapse = await screen.findByRole('button', { name: '收起最近查看' })
  fireEvent.click(collapse)

  expect(screen.getByRole('button', { name: '展开最近查看' })).toHaveAttribute('aria-expanded', 'false')
  expect(screen.queryByRole('button', { name: '最近查看：东山精密 002384.SZ' })).not.toBeInTheDocument()
})

it('collapses the entire stock finder rail toward the left to release analysis width', async () => {
  renderPage('/stock-analysis?symbol=002384.SZ&name=%E4%B8%9C%E5%B1%B1%E7%B2%BE%E5%AF%86')

  const collapse = await screen.findByRole('button', { name: '向左收起股票侧栏' })
  const layout = screen.getByTestId('stock-analysis-page-layout')
  expect(layout).toHaveClass('lg:grid-cols-[18rem_minmax(0,1fr)]')
  expect(collapse).toHaveClass('h-7', 'w-7', 'rounded-md')
  expect(collapse).not.toHaveClass('rounded-full', 'shadow-sm')

  fireEvent.click(collapse)

  expect(screen.getByRole('button', { name: '展开股票侧栏' })).toHaveAttribute('aria-expanded', 'false')
  expect(layout).toHaveClass('lg:grid-cols-[2.75rem_minmax(0,1fr)]')
})

it('opens an exact dated report from an expanded recent stock', async () => {
  localStorage.setItem(
    'recent_stocks:stock-analysis',
    JSON.stringify([{ symbol: '002384.SZ', name: '东山精密' }]),
  )
  vi.mocked(api.stockAnalysisReportsList).mockResolvedValue({
    reports: [{
      id: 'sar-dongshan-before-holiday',
      symbol: '002384.SZ',
      name: '东山精密',
      focus: '节前风险与持仓计划',
      content: '东山精密节前某日的历史分析正文',
      summary: '节前缩量整理，关注关键支撑。',
      created_at: '2026-08-02T17:56:00+08:00',
    }],
  })

  renderPage('/stock-analysis?symbol=002384.SZ&name=%E4%B8%9C%E5%B1%B1%E7%B2%BE%E5%AF%86')

  fireEvent.click(await screen.findByRole('button', { name: '展开东山精密的历史报告' }))
  fireEvent.click(await screen.findByRole('button', { name: '查看东山精密历史报告：08-02 17:56' }))

  expect(await screen.findByText('东山精密节前某日的历史分析正文')).toBeInTheDocument()
  expect(screen.getByLabelText('该股票历史分析列表')).toBeInTheDocument()
})

it('loads saved reports on page entry and shows them through the header history toggle', async () => {
  vi.mocked(api.stockAnalysisReportsList).mockResolvedValue({
    reports: [{
      id: 'sar-dongshan-header-history',
      symbol: '002384.SZ',
      name: '东山精密',
      focus: '',
      content: '顶部历史入口打开的报告正文',
      summary: '顶部历史入口报告摘要',
      created_at: '2026-08-02T17:56:23+08:00',
    }],
  })

  renderPage('/stock-analysis?symbol=002384.SZ&name=%E4%B8%9C%E5%B1%B1%E7%B2%BE%E5%AF%86')

  fireEvent.click(screen.getByRole('button', { name: '历史报告' }))

  expect(await screen.findByText('顶部历史入口打开的报告正文')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '返回分析' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByLabelText('该股票历史分析列表')).toBeInTheDocument()
})

it('shows analysis progress on the recent-stock row instead of a floating bubble', async () => {
  const { startAnalysis } = await import('@/lib/stockAnalysisStore')
  let releaseStream: (() => void) | undefined
  const hold = new Promise<void>(resolve => { releaseStream = resolve })
  vi.spyOn(api, 'stockAnalyzeStream').mockImplementation(async function* () {
    yield { type: 'meta', summary: '分析中' }
    await hold
  })

  renderPage('/stock-analysis?symbol=605289.SH&name=%E7%BD%97%E6%9B%BC%E8%82%A1%E4%BB%BD')
  expect(await screen.findByRole('button', { name: '最近查看：罗曼股份 605289.SH' })).toBeInTheDocument()

  await startAnalysis('605289.SH', '罗曼股份')

  const analyzing = await screen.findByRole('button', { name: '正在分析：罗曼股份 605289.SH' })
  expect(analyzing).toHaveAttribute('aria-busy', 'true')
  expect(analyzing).toHaveTextContent('分析中')
  expect(screen.queryByTitle('个股分析中,点击恢复')).not.toBeInTheDocument()
  releaseStream?.()
})

