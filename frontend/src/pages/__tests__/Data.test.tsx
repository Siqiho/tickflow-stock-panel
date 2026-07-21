import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { catalogFixture, failedRun } from '@/components/data/__tests__/catalogFixtures'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { Data } from '../Data'

const statusFixture = {
  daily: null,
  enriched: null,
  index_daily: null,
  index_enriched: null,
  index_instruments: null,
  etf_daily: null,
  etf_enriched: null,
  etf_instruments: null,
  minute: null,
  adj_factor: null,
  instruments: null,
  financials: null,
  storage: {
    daily_files: 0, daily_size_mb: 0, enriched_files: 0, enriched_size_mb: 0,
    minute_files: 0, minute_size_mb: 0, adj_factor_files: 0, adj_factor_size_mb: 0,
    instruments_files: 0, instruments_size_mb: 0, total_size_mb: 0,
  },
  next_pipeline_run: null,
  next_instruments_run: null,
  last_pipeline_run: null,
  last_instruments_run: null,
  checked_at: '2026-07-21T08:31:00Z',
}

function createClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } },
  })
  client.setQueryData(QK.capabilities, { capabilities: {}, features: {} })
  client.setQueryData(QK.settings, { mode: 'api_key', tier_label: 'Local', current_endpoint: '' })
  client.setQueryData(QK.preferences, {
    minute_sync_enabled: false,
    pipeline_schedule: { hour: 15, minute: 30 },
    instruments_schedule: { hour: 9, minute: 10 },
  })
  client.setQueryData(QK.quoteStatus, { running: false, is_trading_hours: false, interval_s: 10 })
  client.setQueryData(QK.quoteInterval, { interval: 10, min_interval: 5, max_interval: 60 })
  client.setQueryData(QK.dataStatus, statusFixture)
  client.setQueryData(QK.pipelineJobs, { active_id: null, jobs: [] })
  client.setQueryData(QK.extData, { items: [] })
  return client
}

const unselectedCatalogKeys = [
  QK.dataCatalogDataset('etf_daily'),
  QK.dataCatalogSchema('etf_daily'),
  QK.dataCatalogRuns('etf_daily'),
]

function seedUnselectedCatalogQueries(client: QueryClient) {
  for (const queryKey of unselectedCatalogKeys) client.setQueryData(queryKey, { preserved: true })
  return unselectedCatalogKeys.map(() => vi.fn(async () => ({ refetched: true })))
}

function expectUnselectedCatalogQueriesFresh(
  client: QueryClient,
  queryFns: ReturnType<typeof seedUnselectedCatalogQueries>,
) {
  unselectedCatalogKeys.forEach((queryKey, index) => {
    expect(client.getQueryState(queryKey)?.isInvalidated).toBe(false)
    expect(queryFns[index]).not.toHaveBeenCalled()
  })
}

function expectUnselectedCatalogQueriesRefetched(
  queryFns: ReturnType<typeof seedUnselectedCatalogQueries>,
) {
  queryFns.forEach((queryFn) => expect(queryFn).toHaveBeenCalled())
}

function UnselectedCatalogProbe({ queryFns }: { queryFns: ReturnType<typeof seedUnselectedCatalogQueries> }) {
  useQuery({ queryKey: unselectedCatalogKeys[0], queryFn: queryFns[0] })
  useQuery({ queryKey: unselectedCatalogKeys[1], queryFn: queryFns[1] })
  useQuery({ queryKey: unselectedCatalogKeys[2], queryFn: queryFns[2] })
  return null
}

function renderData(
  client = createClient(),
  unselectedQueryFns?: ReturnType<typeof seedUnselectedCatalogQueries>,
) {
  return {
    client,
    ...render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <QueryClientProvider client={client}>
          <Data />
          {unselectedQueryFns && <UnselectedCatalogProbe queryFns={unselectedQueryFns} />}
        </QueryClientProvider>
      </MemoryRouter>,
    ),
  }
}

beforeEach(() => {
  localStorage.clear()
  vi.spyOn(api, 'dataCatalog').mockResolvedValue(catalogFixture)
  vi.spyOn(api, 'dataCatalogRuns').mockResolvedValue({ dataset_id: null, runs: [failedRun] })
  vi.spyOn(api, 'rescanDataCatalog').mockResolvedValue(catalogFixture)
  vi.spyOn(api, 'dataCatalogDataset').mockImplementation(async (id) => (
    catalogFixture.datasets.find((entry) => entry.descriptor.dataset_id === id)!
  ))
  vi.spyOn(api, 'dataCatalogSchema').mockImplementation(async (id) => ({
    dataset_id: id,
    schema_version: 'v1',
    unit_version: 'cn_market_v1',
    fields: [],
  }))
  vi.spyOn(api, 'syncIndexDaily').mockResolvedValue({ status: 'ok', index_count: 1, rows_written: 1 })
  vi.spyOn(api, 'dataClear').mockResolvedValue({ deleted_files: 1 })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Data workbench integration', () => {
  it('renders exactly four level-2 workbench regions in required DOM order', async () => {
    renderData()

    await screen.findByRole('heading', { name: 'ETF daily bars' })
    expect(screen.getAllByRole('heading', { level: 2 }).map((heading) => heading.textContent)).toEqual([
      '数据系统状态',
      '数据集目录',
      '同步和维护操作',
      '同步历史与质量问题',
    ])
    const regionNames = ['数据系统状态', '数据集目录', '同步和维护操作', '同步历史与质量问题']
    const regions = regionNames.map((name) => screen.getByRole('region', { name }))
    expect(regions.map((region) => region.getAttribute('aria-labelledby')))
      .toEqual(['data-system-status-heading', 'data-catalog-region-heading', 'data-maintenance-heading', 'data-history-heading'])
    for (let index = 0; index < regions.length - 1; index += 1) {
      expect(regions[index].compareDocumentPosition(regions[index + 1]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    }
  })

  it('keeps every explicit maintenance entry available after removing StatCard inference', async () => {
    renderData()
    const region = await screen.findByRole('region', { name: '同步和维护操作' })

    for (const name of [
      '立即同步', '数据范围', '新建扩展数据', '测试端点', '目录显示设置',
      '日 K 历史扩展', '重建 Enriched', '指数手动获取', '分钟 K 设置', '清除数据',
    ]) {
      expect(within(region).getByRole('button', { name })).toBeInTheDocument()
    }
    expect(within(region).getByRole('heading', { name: '实时行情' })).toBeInTheDocument()
    expect(within(region).getByRole('heading', { name: '自动调度' })).toBeInTheDocument()
  })

  it('filters only copied render data and still executes the same catalog query', async () => {
    localStorage.setItem('data-card-visible', JSON.stringify({ etf: false }))
    renderData()

    await waitFor(() => expect(api.dataCatalog).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('heading', { name: 'ETF daily bars' })).not.toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: '封板 L1' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Five-level order book' })).not.toBeInTheDocument()
  })

  it('rescans only through the local POST API, preserves stale results, and invalidates explicit keys', async () => {
    vi.mocked(api.rescanDataCatalog).mockResolvedValue({ ...catalogFixture, stale: true })
    const { client } = renderData()
    const invalidate = vi.spyOn(client, 'invalidateQueries')

    fireEvent.click(await screen.findByRole('button', { name: '重新扫描本地目录' }))

    await waitFor(() => expect(api.rescanDataCatalog).toHaveBeenCalledWith())
    expect((await screen.findAllByText('状态可能过期')).length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { name: 'Stock daily bars' })).toBeInTheDocument()
    expect(invalidate).toHaveBeenCalled()
    expect(invalidate.mock.calls.every(([filters]) => Boolean(filters && 'queryKey' in filters))).toBe(true)
  })

  it('invalidates the full catalog prefix when a pipeline reaches a terminal state', async () => {
    const client = createClient()
    const unselectedQueryFns = seedUnselectedCatalogQueries(client)
    client.setQueryData(QK.pipelineJobs, { active_id: 'job-1', jobs: [] })
    vi.spyOn(api, 'pipelineJob').mockResolvedValue({
      id: 'job-1',
      status: 'degraded',
      stage: 'quality',
      progress: 100,
      stage_pct: 100,
      log: [],
      started_at: '2026-07-21T08:00:00Z',
      finished_at: '2026-07-21T08:01:00Z',
      duration_s: 60,
      result: {
        universe_size: 1,
        daily_days: 1,
        adj_factor_symbols: 0,
        enriched_days: 1,
        minute_rows: 0,
      },
      error: null,
    })
    const invalidate = vi.spyOn(client, 'invalidateQueries')

    renderData(client, unselectedQueryFns)

    await waitFor(() => expect(api.pipelineJob).toHaveBeenCalledWith('job-1'))
    await waitFor(() => {
      const invalidatedKeys = invalidate.mock.calls.map(([filters]) => filters?.queryKey)
      expect(invalidatedKeys).toContainEqual(QK.dataStatus)
      expect(invalidatedKeys).toContainEqual(QK.dataCatalog)
      expect(invalidatedKeys).toContainEqual(QK.pipelineJobs)
    })
    expect(invalidate.mock.calls.every(([filters]) => Boolean(filters && 'queryKey' in filters))).toBe(true)
    await waitFor(() => expectUnselectedCatalogQueriesRefetched(unselectedQueryFns))
  })

  it('normalizes 36 months to one year before calculating index sync days', async () => {
    const client = createClient()
    client.setQueryData(QK.capabilities, { capabilities: { 'kline.daily.batch': {} }, features: {} })
    client.setQueryData(QK.dataStatus, {
      ...statusFixture,
      daily: {
        rows: 1,
        earliest_date: '2026-01-01',
        latest_date: '2026-07-21',
        symbols_covered: 1,
        trading_days: 1,
      },
      index_daily: {
        rows: 1,
        earliest_date: '2026-01-01',
        latest_date: '2026-07-21',
        symbols_covered: 1,
        trading_days: 1,
      },
    })
    renderData(client)

    fireEvent.click(await screen.findByRole('button', { name: '指数手动获取' }))
    const modalHeading = screen.getByRole('heading', { name: '指数 · 手动获取' })
    const modal = modalHeading.parentElement?.parentElement
    expect(modal).not.toBeNull()
    const plus = within(modal!).getByRole('button', { name: '+' })
    for (let count = 6; count < 36; count += 1) fireEvent.click(plus)
    expect(within(modal!).getByText('36')).toBeInTheDocument()

    fireEvent.click(within(modal!).getByRole('button', { name: '年' }))
    expect(within(modal!).queryByText('36')).not.toBeInTheDocument()
    expect(within(modal!).getByText('1')).toBeInTheDocument()
    fireEvent.click(within(modal!).getByRole('button', { name: '获取数据' }))

    await waitFor(() => expect(api.syncIndexDaily).toHaveBeenCalledTimes(1))
    const expectedTarget = new Date('2026-01-01')
    expectedTarget.setDate(expectedTarget.getDate() - 365)
    const expectedDays = Math.min(5000, Math.max(30, Math.ceil((Date.now() - expectedTarget.getTime()) / 86_400_000) + 1))
    expect(api.syncIndexDaily).toHaveBeenCalledWith(expectedDays)
    expect(expectedDays).toBeLessThan(5000)
  })

  it('keeps unrelated catalog children fresh after index sync', async () => {
    const client = createClient()
    const unselectedQueryFns = seedUnselectedCatalogQueries(client)
    client.setQueryData(QK.capabilities, { capabilities: { 'kline.daily.batch': {} }, features: {} })
    client.setQueryData(QK.dataStatus, {
      ...statusFixture,
      daily: {
        rows: 1,
        earliest_date: '2026-01-01',
        latest_date: '2026-07-21',
        symbols_covered: 1,
        trading_days: 1,
      },
      index_daily: {
        rows: 1,
        earliest_date: '2026-01-01',
        latest_date: '2026-07-21',
        symbols_covered: 1,
        trading_days: 1,
      },
    })
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    renderData(client, unselectedQueryFns)

    fireEvent.click(await screen.findByRole('button', { name: '指数手动获取' }))
    fireEvent.click(screen.getByRole('button', { name: '获取数据' }))

    await waitFor(() => expect(api.syncIndexDaily).toHaveBeenCalledTimes(1))
    await waitFor(() => expectUnselectedCatalogQueriesFresh(client, unselectedQueryFns))
    const invalidatedKeys = invalidate.mock.calls.map(([filters]) => filters?.queryKey)
    for (const datasetId of ['index_instruments', 'etf_instruments', 'index_daily', 'index_enriched']) {
      expect(invalidatedKeys).toContainEqual(QK.dataCatalogDataset(datasetId))
      expect(invalidatedKeys).toContainEqual(QK.dataCatalogSchema(datasetId))
      expect(invalidatedKeys).toContainEqual(QK.dataCatalogRuns(datasetId))
    }
  })

  it('invalidates the full catalog prefix after destructive clear', async () => {
    const client = createClient()
    const unselectedQueryFns = seedUnselectedCatalogQueries(client)
    renderData(client, unselectedQueryFns)

    fireEvent.click(await screen.findByRole('button', { name: '清除数据' }))
    fireEvent.click(screen.getAllByRole('button', { name: '清除数据' }).at(-1)!)

    await waitFor(() => expect(api.dataClear).toHaveBeenCalledTimes(1))
    await waitFor(() => expectUnselectedCatalogQueriesRefetched(unselectedQueryFns))
  })

  it('keeps maintenance and legacy history usable when catalog and run queries fail', async () => {
    vi.mocked(api.dataCatalog).mockRejectedValue(new Error('catalog offline'))
    vi.mocked(api.dataCatalogRuns).mockRejectedValue(new Error('runs offline'))
    renderData()

    expect(await screen.findByRole('alert', { name: '数据目录错误' })).toHaveTextContent('catalog offline')
    expect(await screen.findByRole('alert', { name: '运行历史错误' })).toHaveTextContent('runs offline')
    expect(screen.getByRole('button', { name: '立即同步' })).toBeInTheDocument()
    expect(screen.getByText(/暂无同步记录/)).toBeInTheDocument()
  })

  it('keeps the selected catalog entry visible and degrades detail/schema/run failures inline', async () => {
    vi.mocked(api.dataCatalogDataset).mockRejectedValue(new Error('detail offline'))
    vi.mocked(api.dataCatalogSchema).mockRejectedValue(new Error('schema offline'))
    vi.mocked(api.dataCatalogRuns).mockImplementation(async (id) => {
      if (id) throw new Error('dataset runs offline')
      return { dataset_id: null, runs: [] }
    })
    renderData()

    fireEvent.click(await screen.findByRole('button', { name: '查看 Stock daily bars 详情' }))

    const dialog = await screen.findByRole('dialog', { name: 'Stock daily bars 详情' })
    const alert = await within(dialog).findByRole('alert')
    expect(alert).toHaveTextContent('detail offline')
    expect(alert).toHaveTextContent('schema offline')
    expect(alert).toHaveTextContent('dataset runs offline')
    expect(within(dialog).getByText('stock_daily')).toBeInTheDocument()
  })
})
