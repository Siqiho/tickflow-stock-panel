import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { catalogFixture, makeEntry } from '@/components/data/__tests__/catalogFixtures'
import { api, type CapabilityMatrix, type CapabilityRoute, type CatalogResponse } from '@/lib/api'
import { EXTERNAL_READONLY_SOURCES_QK } from '@/lib/dataSources'
import { QK } from '@/lib/queryKeys'
import { Data } from '../Data'
import { Settings } from '../Settings'

function matrixCap(id: string, label: string, overrides: Partial<CapabilityRoute> = {}): CapabilityRoute {
  return {
    id,
    label,
    desc: '',
    field: `${id}_data_provider` as CapabilityRoute['field'],
    default: 'tickflow',
    tf_tier: 'none',
    tf_available: true,
    usable: true,
    current: 'tickflow',
    current_display: 'TickFlow',
    effective: 'tickflow',
    effective_display: 'TickFlow',
    candidates: [
      { name: 'tickflow', display: 'TickFlow', kind: 'builtin', available: true, status: 'ok' },
      { name: 'public', display: '公开源', kind: 'builtin', available: true, status: 'ok' },
    ],
    pending: [],
    ...overrides,
  }
}

const matrixFixture: CapabilityMatrix = {
  tickflow_tier: 'none',
  capabilities: [
    matrixCap('daily', '日K', {
      current: 'tickflow', current_display: 'TickFlow', effective: 'tickflow', effective_display: 'TickFlow',
    }),
    matrixCap('financial', '财务数据', {
      current: 'public', current_display: '公开源', effective: 'public', effective_display: '公开源',
    }),
  ],
}

const dataSourcesFixture = {
  builtin: [{ name: 'tickflow', display_name: 'TickFlow', datasets: ['daily', 'adj_factor'] }],
  plugins: [{
    name: 'fuyao', display_name: '扶摇', datasets: ['financial'],
    runtime: 'python', available: true, status: 'ok', description: '', install_hint: '',
  }, {
    name: 'hithink', display_name: '同花顺', datasets: ['minute'],
    runtime: 'python', available: true, status: 'ok', description: '', install_hint: '',
  }],
  custom: [],
  errors: [],
  config_dir: '/tmp',
}

const mixedCatalog: CatalogResponse = {
  ...catalogFixture,
  datasets: [
    ...catalogFixture.datasets,
    makeEntry('shop_floor_bars', 'Shop floor bars', { provider: 'shop_floor' }),
    makeEntry('mystery_bars', 'Mystery bars', { provider: null }),
  ],
}

const provenanceFixture = {
  generated_at: '2026-08-01T10:00:00Z',
  catalog_refreshed_at: '2026-07-31T01:10:06Z',
  catalog_stale: true,
  missing_reference_count: 0,
  records: [{
    subject_id: 'stock_daily',
    subject_kind: 'dataset' as const,
    title: 'Stock daily bars',
    summary: '已落库',
    true_producers: [{
      producer_id: 'public_quote', name: '腾讯 / 新浪公开行情端点', kind: 'public_web_endpoint',
      role: 'quote_and_eod_fallback',
    }],
    local_chain: {
      providers: ['public'], adapter_paths: [], physical_paths: [], lineage_sources: ['public_feed'],
      materialized: true, serving_ready: true, latest_time: '2026-07-20',
    },
    github_references: [],
    replacement_candidates: [],
    issues: [],
  }],
}

function createClient(isAdmin = true) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } },
  })
  client.setQueryData(QK.capabilities, { capabilities: {}, features: {} })
  client.setQueryData(QK.settings, { mode: 'api_key', tier_label: 'None', current_endpoint: '', is_admin: isAdmin })
  client.setQueryData(QK.preferences, { daily_data_provider: 'tickflow', financial_provider: 'public' })
  client.setQueryData(QK.quoteStatus, { running: false, is_trading_hours: false, interval_s: 10 })
  client.setQueryData(QK.quoteInterval, { interval: 10, min_interval: 5, max_interval: 60 })
  client.setQueryData(QK.dataStatus, { daily: null, instruments: null, storage: { total_size_mb: 0 } })
  client.setQueryData(QK.capabilityMatrix, matrixFixture)
  client.setQueryData(QK.dataSources, dataSourcesFixture)
  client.setQueryData(QK.dataCatalog, mixedCatalog)
  client.setQueryData(QK.dataSourceProvenance, provenanceFixture)
  client.setQueryData(EXTERNAL_READONLY_SOURCES_QK, {
    status: 'configured',
    supported: [{ id: 'margin_trading', label: '两融' }],
    note: '仅两融',
    root_path: '/mnt/offline',
  })
  client.setQueryData(QK.pipelineJobs, { active_id: null, jobs: [] })
  client.setQueryData(QK.extData, { items: [] })
  return client
}

function renderAt(entry: string, client = createClient()) {
  return {
    client,
    ...render(
      <MemoryRouter initialEntries={[entry]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <QueryClientProvider client={client}>
          <Routes>
            <Route path="/data" element={<Data />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </QueryClientProvider>
      </MemoryRouter>,
    ),
  }
}

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="unified-location">{location.pathname}{location.search}</div>
}

beforeEach(() => {
  localStorage.clear()
  vi.spyOn(api, 'dataCatalog').mockResolvedValue(mixedCatalog)
  vi.spyOn(api, 'dataSources').mockResolvedValue(dataSourcesFixture)
  vi.spyOn(api, 'capabilityMatrix').mockResolvedValue(matrixFixture)
  vi.spyOn(api, 'dataSourceProvenance').mockResolvedValue(provenanceFixture)
  vi.spyOn(api, 'dataControlSummary').mockResolvedValue({
    generated_at: '2026-08-01T08:00:00Z',
    catalog_refreshed_at: null,
    catalog_stale: false,
    source_health: [],
    dataset_policies: [],
    sync_checkpoints: [],
    query_audits: [],
    unregistered_physical: [],
    physical_scan_scope: 'reference',
  } as never)
  vi.spyOn(api, 'externalReadonlySources').mockResolvedValue({
    status: 'configured',
    supported: [{ id: 'margin_trading', label: '两融' }],
    note: '仅两融',
    root_path: '/mnt/offline',
  })
  vi.spyOn(api, 'getMarginTrading').mockResolvedValue({
    data: [{
      symbol: '300502.SZ',
      trade_date: '2026-09-01',
      financing_balance: 10,
      securities_lending_balance: 2,
      securities_lending_balance_volume: 3,
      source: 'offline_quantdb',
    }],
    count: 1,
    source: 'offline_quantdb',
    as_of: '2026-09-01',
    status: 'ok',
  })
  vi.spyOn(api, 'updateDataProviders')
  vi.spyOn(api, 'redetectCapabilities')
  vi.spyOn(api, 'installPlugin')
  vi.spyOn(api, 'saveDataSource')
  vi.spyOn(api, 'pipelineJobs').mockResolvedValue({ active_id: null, jobs: [] })
  vi.spyOn(api, 'dataCatalogRuns').mockResolvedValue({ dataset_id: null, runs: [] })
  vi.spyOn(api, 'dataCatalogDataset').mockImplementation(async (id) => (
    mixedCatalog.datasets.find((entry) => entry.descriptor.dataset_id === id)!
  ))
  vi.spyOn(api, 'dataCatalogSchema').mockImplementation(async (id) => ({
    dataset_id: id,
    schema_version: 'v1',
    unit_version: 'cn_market_v1',
    fields: mixedCatalog.datasets.find((entry) => entry.descriptor.dataset_id === id)?.descriptor.fields ?? [],
  }))
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('unified data entry', () => {
  it('keeps ordinary users on the read-only overview without admin metadata or writes', async () => {
    renderAt('/data', createClient(false))

    const sourceGrid = (await screen.findByRole('heading', { name: '数据来源' })).closest('section')!
    expect(within(sourceGrid).getByText('TickFlow')).toBeInTheDocument()
    expect(within(sourceGrid).getByText('扶摇')).toBeInTheDocument()
    expect(within(sourceGrid).getByText('同花顺')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'TickFlow' })).toBeInTheDocument()
    fireEvent.click(within(sourceGrid).getByRole('button', { name: /公开源/ }))
    const dailyRow = (await screen.findByText('Stock daily bars')).closest('li')!
    expect(dailyRow).toBeTruthy()
    expect(within(dailyRow).getByText(/close（元）/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '新增数据源' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '套用' })).not.toBeInTheDocument()
    const routing = screen.getByRole('heading', { name: '能力路由' }).closest('section')!
    expect(routing).toBeTruthy()
    expect(screen.getAllByRole('heading', { name: '能力路由' })).toHaveLength(1)
    expect(within(routing).queryByRole('button', { name: '公开源' })).not.toBeInTheDocument()
    expect(within(routing).queryByRole('button', { name: 'TickFlow' })).not.toBeInTheDocument()
    expect(screen.queryByTitle('根据 API Key 重新检测订阅档位')).not.toBeInTheDocument()
    expect(screen.queryByText('外部只读原包')).not.toBeInTheDocument()
    expect(api.dataSourceProvenance).not.toHaveBeenCalled()
    expect(api.externalReadonlySources).not.toHaveBeenCalled()
    expect(api.dataControlSummary).not.toHaveBeenCalled()
    expect(api.updateDataProviders).not.toHaveBeenCalled()
    expect(api.redetectCapabilities).not.toHaveBeenCalled()
    expect(api.installPlugin).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('tab', { name: '数据目录' }))
    expect(await screen.findByRole('heading', { name: '数据集目录' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /外部只读原包·两融查询/ })).not.toBeInTheDocument()
    expect(api.externalReadonlySources).not.toHaveBeenCalled()
  })

  it('redirects the old settings data-sources tab to the single data page', async () => {
    const client = createClient()
    render(
      <MemoryRouter initialEntries={['/settings?tab=data-sources']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <QueryClientProvider client={client}>
          <Routes>
            <Route path="/settings" element={<Settings />} />
            <Route path="/data" element={<LocationProbe />} />
          </Routes>
        </QueryClientProvider>
      </MemoryRouter>,
    )

    expect(await screen.findByTestId('unified-location')).toHaveTextContent('/data?section=sources')
    expect(screen.queryByText('数据源')).not.toBeInTheDocument()
  })

  it('lets an admin reuse add-source, routing and paid tiers on the same overview', async () => {
    renderAt('/data?section=sources')

    expect(await screen.findByRole('heading', { name: '能力路由' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '新增数据源' })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: '套用' }).length).toBeGreaterThan(0)
    const tickflowDetail = screen.getByRole('heading', { name: 'TickFlow' }).closest('section')!
    expect(within(tickflowDetail).getAllByText('None').length).toBeGreaterThan(0)
    expect(within(tickflowDetail).getByTitle('根据 API Key 重新检测订阅档位')).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { name: '能力路由' })).toHaveLength(1)
  })

  it('shows matched local datasets on an online source and keeps unknown rows unregistered', async () => {
    renderAt('/data')

    const sourceGrid = (await screen.findByRole('heading', { name: '数据来源' })).closest('section')!
    fireEvent.click(within(sourceGrid).getByRole('button', { name: /公开源/ }))
    const publicSection = (await screen.findByRole('heading', { name: '公开源 · 实际数据集' })).closest('section')!
    const dailyRow = within(publicSection).getByText('Stock daily bars').closest('li')!
    expect(dailyRow).toBeTruthy()
    expect(within(dailyRow).getByText(/2024-01-02 ~ 2026-07-20/)).toBeInTheDocument()
    expect(within(dailyRow).getByText(/close（元）/)).toBeInTheDocument()
    expect(within(dailyRow).getByText(/腾讯 \/ 新浪公开行情端点/)).toBeInTheDocument()
    expect(within(publicSection).getByText('真实生产者').closest('div')).toHaveTextContent(/腾讯 \/ 新浪公开行情端点/)
    expect(within(publicSection).queryByText('Mystery bars')).not.toBeInTheDocument()
    expect(within(publicSection).queryByText('Shop floor bars')).not.toBeInTheDocument()

    fireEvent.click(within(sourceGrid).getByRole('button', { name: /shop_floor/ }))
    const localSection = (await screen.findByRole('heading', { name: 'shop_floor · 实际数据集' })).closest('section')!
    expect(within(localSection).getByText('Shop floor bars')).toBeInTheDocument()
    expect(within(localSection).getByText('HTTP 提供方')).toBeInTheDocument()
    expect(within(localSection).getByText('真实生产者').closest('div')).toHaveTextContent('未登记')

    fireEvent.click(within(sourceGrid).getByRole('button', { name: /未登记来源/ }))
    const unknownSection = (await screen.findByRole('heading', { name: '未登记来源 · 实际数据集' })).closest('section')!
    expect(within(unknownSection).getByText('Mystery bars')).toBeInTheDocument()
    expect(within(unknownSection).queryByText('Stock daily bars')).not.toBeInTheDocument()
  })

  it('reuses the external package query with an explicit source and no write-back', async () => {
    renderAt('/data')

    fireEvent.click(await screen.findByRole('button', { name: /外部只读原包/ }))
    expect(await screen.findByRole('heading', { name: '外部只读数据' })).toBeInTheDocument()
    expect(screen.getByText('已配置')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('两融股票代码'), { target: { value: '300502.SZ' } })
    fireEvent.click(screen.getByRole('button', { name: '查询两融' }))

    await waitFor(() => expect(api.getMarginTrading).toHaveBeenCalledWith({
      symbol: '300502.SZ',
      source: 'offline_quantdb',
      limit: 20,
    }))
    expect(await screen.findByText('offline_quantdb')).toBeInTheDocument()
    expect(screen.getByText(/截止日 2026-09-01/)).toBeInTheDocument()
    expect(api.saveDataSource).not.toHaveBeenCalled()
    expect(api.updateDataProviders).not.toHaveBeenCalled()
  })

  it('does not conclude there are no associated datasets while the catalog is loading or failed', async () => {
    vi.mocked(api.dataCatalog).mockReturnValue(new Promise(() => {}))
    const loadingClient = createClient()
    loadingClient.removeQueries({ queryKey: QK.dataCatalog })
    renderAt('/data', loadingClient)

    expect(await screen.findAllByText('目录读取中')).not.toHaveLength(0)
    expect(screen.queryByText(/没有可关联的本地数据集/)).not.toBeInTheDocument()

    cleanup()

    vi.mocked(api.dataCatalog).mockRejectedValue(new Error('catalog offline'))
    const errorClient = createClient()
    errorClient.removeQueries({ queryKey: QK.dataCatalog })
    renderAt('/data', errorClient)

    expect(await screen.findAllByText('目录读取失败，暂无法判断')).not.toHaveLength(0)
    expect(screen.queryByText(/没有可关联的本地数据集/)).not.toBeInTheDocument()
  })
})
