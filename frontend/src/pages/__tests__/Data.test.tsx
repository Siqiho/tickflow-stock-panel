import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { catalogFixture, failedRun } from '@/components/data/__tests__/catalogFixtures'
import { api, type CapabilityMatrix, type CapabilityRoute } from '@/lib/api'
import { EXTERNAL_READONLY_SOURCES_QK } from '@/lib/dataSources'
import { QK } from '@/lib/queryKeys'
import { Data } from '../Data'

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
    candidates: [{ name: 'tickflow', display: 'TickFlow', kind: 'builtin', available: true, status: 'ok' }],
    pending: [],
    ...overrides,
  }
}

const matrixFixture: CapabilityMatrix = {
  tickflow_tier: 'none',
  capabilities: [
    matrixCap('daily', '日K', {
      current: 'public', current_display: '公开源', effective: 'public', effective_display: '公开源', usable: false,
    }),
    matrixCap('adj_factor', '除权因子', { tf_tier: 'starter', tf_available: false, usable: false }),
    matrixCap('realtime', '实时行情', { tf_tier: 'starter', tf_available: false, usable: false }),
    matrixCap('minute', '分钟K', { tf_tier: 'pro', tf_available: false, usable: false }),
    matrixCap('depth5', '五档盘口', { tf_tier: 'pro', tf_available: false, usable: false }),
    matrixCap('financial', '财务数据', {
      current: 'public', current_display: '公开源', effective: 'public', effective_display: '公开源',
      usable: true, tf_available: false,
    }),
    matrixCap('full_minute', '全量分钟', { tf_tier: 'expert', tf_available: false, usable: false }),
  ],
}

const noneTierMatrix: CapabilityMatrix = {
  tickflow_tier: 'none',
  capabilities: [
    matrixCap('daily', '日K'),
    matrixCap('adj_factor', '除权因子', { tf_tier: 'starter', tf_available: false, usable: false }),
    matrixCap('realtime', '实时行情', { tf_tier: 'starter', tf_available: false, usable: false }),
    matrixCap('minute', '分钟K', { tf_tier: 'pro', tf_available: false, usable: false }),
    matrixCap('depth5', '五档盘口', { tf_tier: 'pro', tf_available: false, usable: false }),
    matrixCap('financial', '财务数据', { tf_tier: 'expert', tf_available: false, usable: false }),
    matrixCap('full_minute', '全量分钟', { tf_tier: 'expert', tf_available: false, usable: false }),
  ],
}

const unconfiguredExternal = {
  status: 'unconfigured' as const,
  supported: [{ id: 'margin_trading', label: '两融' }],
  note: '外置只读包目前仅支持按标的查询两融，不是全包已入库，也不计入托管存储。',
  root_path: null,
}

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

const controlSummaryFixture = {
  generated_at: '2026-08-01T08:00:00Z',
  catalog_refreshed_at: '2026-07-31T01:10:06Z',
  catalog_stale: true,
  source_health: [
    { provider: 'data_sync', operation: 'sync:stock_daily', last_success_at: '2026-07-31T08:00:00Z', last_failure_at: null, consecutive_failures: 0, cooldown_until: null, last_error_code: null },
    { provider: 'data_sync', operation: 'sync:trading_calendar', last_success_at: '2026-07-31T08:00:00Z', last_failure_at: null, consecutive_failures: 0, cooldown_until: null, last_error_code: null },
    { provider: 'data_sync', operation: 'sync:m6_batch', last_success_at: null, last_failure_at: '2026-07-31T08:05:00Z', consecutive_failures: 2, cooldown_until: '2026-07-31T08:20:00Z', last_error_code: 'm6_incomplete' },
  ],
  dataset_policies: [{
    dataset_id: 'stock_daily', phase: 'isolated', max_lag_trading_days: 1,
    sync_mode: 'scheduled', schedule_cron: '30 15 * * 1-5',
    supports_backfill: true, supports_repair: true, updated_at: '2026-07-31T08:00:00Z',
  }],
  sync_checkpoints: [{
    dataset_id: 'stock_daily', scope: 'default', watermark: '2026-07-31',
    updated_at: '2026-07-31T08:00:00Z', cursor: { date: '2026-07-31' },
    last_success_run_id: 'run-42',
  }],
  query_audits: [{
    audit_id: 'audit-1', created_at: '2026-07-31T09:00:00Z', dataset_id: 'stock_daily',
    tool_name: 'get_daily_bars', row_count: 300, duration_ms: 12, status: 'succeeded', error_code: null,
  }],
  unregistered_physical: [{
    key: 'corporate_actions', title: 'corporate actions', relative_path: 'reference/corporate_actions',
    files: 3, bytes: 1024, updated_at: '2026-07-31T09:00:00Z',
  }],
  physical_scan_scope: 'reference' as const,
}

const sourceProvenanceFixture = {
  generated_at: '2026-08-01T10:00:00Z',
  catalog_refreshed_at: '2026-07-31T01:10:06Z',
  catalog_stale: true,
  missing_reference_count: 0,
  records: [{
    subject_id: 'stock_daily',
    subject_kind: 'dataset' as const,
    title: 'Stock daily bars',
    // explanation 现由后端 /api/data/source-provenance 下发
    explanation: {
      category: '股票日线行情',
      cadence: '日频时序',
      description: '按股票和交易日保存的日 K 行情，是图表、选股、回测和增强数据计算的基础。',
      provides: '交易日期、开盘价、最高价、最低价、收盘价、成交量与成交额。',
    },
    summary: '质量：降级；已落库；当前可服务；准入阶段：isolated',
    true_producers: [{
      producer_id: 'public_quote', name: '腾讯 / 新浪公开行情端点', kind: 'public_web_endpoint',
      role: 'quote_and_eod_fallback', access: 'http', note: '公开源 fallback',
    }],
    local_chain: {
      providers: ['public'],
      adapter_paths: ['backend/app/services/kline_sync.py'],
      physical_paths: ['kline_daily'],
      lineage_sources: ['public_quote_eod'],
      lifecycle: 'isolated', quality_status: 'degraded', materialized: true, serving_ready: true,
      latest_time: '2026-07-31', checkpoint_watermark: '2026-07-31',
      latest_run: {
        run_id: 'run-42', status: 'failed', operation: 'daily_sync', provider: 'public',
        error_code: 'lineage_missing', error_message: 'lineage missing', finished_at: '2026-07-31T08:00:00Z',
      },
    },
    github_references: [{
      project_id: 'tickflow-stock-panel', name: 'shy3130/tickflow-stock-panel',
      repo_url: 'https://github.com/shy3130/tickflow-stock-panel', pinned_ref: '6e4d6b9',
      commit_url: 'https://github.com/shy3130/tickflow-stock-panel/commit/6e4d6b9', reviewed_at: '2026-07-29',
      roles: ['host', 'engineering_mechanism'], contributions: '提供宿主和 TickFlow 主数据链。',
      runtime_dependency: false, adoption_status: 'host_reference_owned_local_runtime', evidence_level: 'E3',
    }],
    replacement_candidates: [{
      project_id: 'akshare', name: 'akfamily/akshare', repo_url: 'https://github.com/akfamily/akshare',
      pinned_ref: 'fcdbf25', commit_url: null, reviewed_at: '2026-07-20', roles: ['candidate'],
      contributions: '公开端点与字段代码地图。', runtime_dependency: false,
      adoption_status: 'rewrite_per_function_no_vendor', evidence_level: 'E3',
    }],
    issues: [{ code: 'catalog_stale', severity: 'warning' as const, message: 'Catalog 快照可能过期。' }],
  }],
}

function createClient(isAdmin = true) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } },
  })
  client.setQueryData(QK.capabilities, { capabilities: {}, features: {} })
  client.setQueryData(QK.settings, { mode: 'api_key', tier_label: 'Local', current_endpoint: '', is_admin: isAdmin })
  client.setQueryData(QK.preferences, {
    minute_sync_enabled: false,
    daily_data_provider: 'public',
    financial_provider: 'public',
    pipeline_schedule: { hour: 15, minute: 30 },
    instruments_schedule: { hour: 9, minute: 10 },
  })
  client.setQueryData(QK.quoteStatus, { running: false, is_trading_hours: false, interval_s: 10 })
  client.setQueryData(QK.quoteInterval, { interval: 10, min_interval: 5, max_interval: 60 })
  client.setQueryData(QK.dataStatus, statusFixture)
  client.setQueryData(QK.capabilityMatrix, matrixFixture)
  client.setQueryData(QK.dataSources, {
    builtin: [{ name: 'tickflow', display_name: 'TickFlow', datasets: ['daily', 'adj_factor', 'realtime', 'minute'] }],
    plugins: [{
      name: 'fuyao', display_name: '扶摇', datasets: ['financial'],
      runtime: 'python', available: true, status: 'ok', description: '', install_hint: '',
    }],
    custom: [],
    errors: [],
    config_dir: '/tmp',
  })
  client.setQueryData(EXTERNAL_READONLY_SOURCES_QK, unconfiguredExternal)
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
  initialEntry = '/data',
) {
  return {
    client,
    ...render(
      <MemoryRouter initialEntries={[initialEntry]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <QueryClientProvider client={client}>
          <Data />
          {unselectedQueryFns && <UnselectedCatalogProbe queryFns={unselectedQueryFns} />}
        </QueryClientProvider>
      </MemoryRouter>,
    ),
  }
}

type DataCategoryName = '数据总览' | '数据目录' | '采集与同步' | '运行记录' | '来源追踪' | '上游工具'

function selectDataCategory(name: DataCategoryName) {
  fireEvent.click(screen.getByRole('tab', { name }))
  return screen.getByRole('tabpanel', { name })
}

function openCollectionMaintenance(region: HTMLElement) {
  fireEvent.click(within(region).getByRole('button', { name: '维护' }))
}

beforeEach(() => {
  localStorage.clear()
  vi.spyOn(api, 'dataCatalog').mockResolvedValue(catalogFixture)
  vi.spyOn(api, 'dataControlSummary').mockResolvedValue(controlSummaryFixture)
  vi.spyOn(api, 'dataSourceProvenance').mockResolvedValue(sourceProvenanceFixture)
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
  vi.spyOn(api, 'capabilityMatrix').mockResolvedValue(matrixFixture)
  vi.spyOn(api, 'dataSources').mockResolvedValue({
    builtin: [{ name: 'tickflow', display_name: 'TickFlow', datasets: ['daily', 'adj_factor', 'realtime', 'minute'] }],
    plugins: [{
      name: 'fuyao', display_name: '扶摇', datasets: ['financial'],
      runtime: 'python', available: true, status: 'ok', description: '', install_hint: '',
    }],
    custom: [],
    errors: [],
    config_dir: '/tmp',
  })
  vi.spyOn(api, 'updateDataProviders')
  vi.spyOn(api, 'redetectCapabilities')
  vi.spyOn(api, 'externalReadonlySources').mockResolvedValue(unconfiguredExternal)
  vi.spyOn(api, 'getMarginTrading')
  vi.spyOn(api, 'syncMarginTrading')
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Data workbench integration', () => {
  it('gives ordinary users the shared market overview and catalog without administrator controls', async () => {
    const client = createClient(false)
    client.removeQueries({ queryKey: EXTERNAL_READONLY_SOURCES_QK })
    renderData(client)

    expect(screen.getByText(/所有账户读取同一份服务器市场数据/)).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '数据总览' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '数据目录' })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: '采集与同步' })).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: '运行记录' })).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: '来源追踪' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '外部只读数据' })).not.toBeInTheDocument()
    expect(screen.queryByText('外部只读原包')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '新增数据源' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '套用' })).not.toBeInTheDocument()
    expect(api.externalReadonlySources).not.toHaveBeenCalled()
    expect(api.dataSourceProvenance).not.toHaveBeenCalled()
    expect(api.dataControlSummary).not.toHaveBeenCalled()
    expect(api.updateDataProviders).not.toHaveBeenCalled()
    expect(api.redetectCapabilities).not.toHaveBeenCalled()
    expect(screen.queryByTitle('根据 API Key 重新检测订阅档位')).not.toBeInTheDocument()
    const overview = screen.getByRole('tabpanel', { name: '数据总览' })
    const routing = within(overview).getByRole('heading', { name: '能力路由' }).closest('section')!
    expect(within(overview).queryByRole('heading', { name: '有哪些数据' })).not.toBeInTheDocument()
    expect(within(overview).getAllByRole('heading', { name: '能力路由' })).toHaveLength(1)
    for (const label of ['日K', '除权因子', '实时行情', '分钟K', '五档盘口', '财务数据', '全量分钟']) {
      expect(within(routing).getAllByRole('heading', { name: label })).toHaveLength(1)
    }
    expect(within(routing).getByText('配置已就绪')).toBeInTheDocument()
    expect(within(routing).queryByRole('button', { name: '公开源' })).not.toBeInTheDocument()
    expect(within(routing).queryByRole('button', { name: 'TickFlow' })).not.toBeInTheDocument()
    expect(await screen.findByTestId('managed-storage')).toHaveTextContent('共享市场数据')
    expect((await within(routing).findAllByText(/本地已有|尚未落库|目录无记录|目录无独立数据集/)).length).toBeGreaterThan(0)
    expect(screen.queryByTestId('operational-storage')).not.toBeInTheDocument()
    expect(screen.queryByTestId('total-storage')).not.toBeInTheDocument()
    expect(screen.queryByText('User data')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /追踪 .* 来源/ })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: '数据目录' }))
    expect(await screen.findByRole('heading', { name: '数据集目录' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '重新扫描本地目录' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /追踪 .* 来源/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /外部只读原包·两融查询/ })).not.toBeInTheDocument()
    expect(api.externalReadonlySources).not.toHaveBeenCalled()
  })

  it('keeps control-plane facts inside the five categories with progressive disclosure', async () => {
    renderData()

    const overview = screen.getByRole('tabpanel', { name: '数据总览' })
    expect(await within(overview).findByText('控制库采集记录：2 条有成功时间 · 1 条连续失败（不是在线探测）')).toBeInTheDocument()
    expect(within(overview).queryByText(/个正常/)).not.toBeInTheDocument()
    const capabilityCards = within(overview).getByRole('heading', { name: '能力路由' }).closest('section')!
    expect(within(overview).queryByRole('heading', { name: '有哪些数据' })).not.toBeInTheDocument()
    expect(within(overview).getAllByRole('heading', { name: '能力路由' })).toHaveLength(1)
    const financeCard = within(capabilityCards).getByRole('heading', { name: '财务数据' }).closest('article')!
    expect(financeCard).toBeTruthy()
    expect(within(financeCard).getAllByText('公开源').length).toBeGreaterThan(0)
    expect(within(financeCard).getByText('配置已就绪')).toBeInTheDocument()
    expect(await within(financeCard).findByText(/本地已有|尚未落库|目录无记录|目录无独立数据集/)).toBeInTheDocument()
    expect(within(capabilityCards).getByText('配置已就绪')).toBeInTheDocument()
    expect(within(capabilityCards).getAllByText('配置未就绪').length).toBeGreaterThan(0)
    expect(within(overview).getByTitle('根据 API Key 重新检测订阅档位')).toBeInTheDocument()
    expect(within(overview).getByText('外部只读原包')).toBeInTheDocument()
    fireEvent.click(within(overview).getByText('外部只读原包'))
    expect(await within(overview).findByRole('heading', { name: '外部只读数据' })).toBeInTheDocument()
    expect(within(overview).getByText('未配置')).toBeInTheDocument()
    expect(within(overview).getByText('1 个参考目录待登记')).toBeInTheDocument()
    expect(within(overview).queryByText('sync:m6_batch')).not.toBeInTheDocument()
    fireEvent.click(within(overview).getByText('高级信息'))
    expect(within(overview).getByText('sync:m6_batch')).toBeInTheDocument()

    const catalog = selectDataCategory('数据目录')
    expect(within(catalog).getByRole('button', { name: /外部只读原包·两融查询/ })).toHaveAttribute('aria-expanded', 'false')
    expect(within(catalog).queryByLabelText('两融股票代码')).not.toBeInTheDocument()
    const dailyCard = within(catalog).getByRole('heading', { name: 'Stock daily bars' }).closest('article')!
    expect(within(dailyCard).getByText('隔离验证中')).toBeInTheDocument()
    expect(within(dailyCard).getByText('已落库，尚未正式可用')).toBeInTheDocument()
    fireEvent.click(within(dailyCard).getByRole('button', { name: '查看 Stock daily bars 详情' }))
    const dialog = await screen.findByRole('dialog', { name: 'Stock daily bars 详情' })
    expect(within(dialog).getByText('近期被 1 个调用方使用')).toBeInTheDocument()
    expect(within(dialog).queryByText('get_daily_bars')).not.toBeInTheDocument()
    expect(within(dialog).queryByText('run-42')).not.toBeInTheDocument()
    fireEvent.click(within(dialog).getByText('高级信息'))
    expect(within(dialog).getByText('run-42')).toBeInTheDocument()
    expect(within(dialog).getByText('get_daily_bars')).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: '关闭“Stock daily bars”详情' }))

    const collection = selectDataCategory('采集与同步')
    expect(within(collection).queryByRole('heading', { name: '采集状态' })).not.toBeInTheDocument()
    expect(within(collection).queryByText('Stock daily bars 已同步到 2026-07-31')).not.toBeInTheDocument()
    expect(within(collection).queryByText('支持回补和修复')).not.toBeInTheDocument()
    expect(within(collection).queryByText('控制库策略')).not.toBeInTheDocument()
    expect(within(collection).getByRole('button', { name: '立即同步' })).toBeInTheDocument()
    expect(within(collection).getByRole('heading', { name: '市场脉搏' })).toBeInTheDocument()
    expect(within(collection).getByRole('heading', { name: '个股融资融券' })).toBeInTheDocument()
    expect(within(collection).getByRole('heading', { name: '同花顺官方特色数据' })).toBeInTheDocument()

    const history = selectDataCategory('运行记录')
    fireEvent.click(within(history).getByRole('button', { name: '数据源失败' }))
    expect(within(history).getByText('数据源失败 · 数据同步')).toBeInTheDocument()
    expect(within(history).queryByText('sync:m6_batch')).not.toBeInTheDocument()
    fireEvent.click(within(history).getByRole('button', { name: '高级信息' }))
    expect(within(history).getByText('sync:m6_batch')).toBeInTheDocument()
    fireEvent.click(within(history).getByRole('button', { name: '消费者查询' }))
    expect(within(history).getByText('消费者查询 · stock_daily')).toBeInTheDocument()
    expect(within(history).queryByText('get_daily_bars')).not.toBeInTheDocument()
    fireEvent.click(within(history).getByRole('button', { name: '高级信息' }))
    expect(within(history).getByText('get_daily_bars')).toBeInTheDocument()
  })

  it('keeps the offline margin query outside catalog counts and mounts it only when an admin expands it', async () => {
    const client = createClient()
    client.removeQueries({ queryKey: EXTERNAL_READONLY_SOURCES_QK })
    renderData(client)

    const catalog = selectDataCategory('数据目录')
    expect(await within(catalog).findByRole('heading', { name: 'Stock daily bars' })).toBeInTheDocument()
    const f10 = within(catalog).getByRole('region', { name: '股票 F10' })
    expect(within(f10).getByText('1')).toBeInTheDocument()
    expect(within(catalog).queryByText(/80\s*GB|80GB/)).not.toBeInTheDocument()
    expect(api.externalReadonlySources).not.toHaveBeenCalled()
    expect(api.getMarginTrading).not.toHaveBeenCalled()

    const fold = within(catalog).getByRole('button', { name: /外部只读原包·两融查询/ })
    expect(fold).toHaveAttribute('aria-expanded', 'false')
    expect(within(catalog).queryByLabelText('两融股票代码')).not.toBeInTheDocument()

    fireEvent.click(fold)
    expect(fold).toHaveAttribute('aria-expanded', 'true')
    expect(await within(catalog).findByLabelText('两融股票代码')).toBeInTheDocument()
    await waitFor(() => expect(api.externalReadonlySources).toHaveBeenCalledTimes(1))
    expect(api.getMarginTrading).not.toHaveBeenCalled()
    expect(within(f10).getByText('1')).toBeInTheDocument()
    expect(within(catalog).getByText('截止按标的查询获取。')).toBeInTheDocument()
    expect(within(catalog).queryByText(/80\s*GB|80GB/)).not.toBeInTheDocument()
  })

  it('renders only the selected category panel', async () => {
    renderData()

    expect(screen.getByRole('tabpanel', { name: '数据总览' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '数据系统状态' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '数据集目录' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '盘后主链' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '同步历史与质量问题' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: '数据目录' }))
    expect(await screen.findByRole('tabpanel', { name: '数据目录' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '数据集目录' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '数据系统状态' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: '采集与同步' }))
    expect(screen.getByRole('tabpanel', { name: '采集与同步' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '盘后主链' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '数据集目录' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: '运行记录' }))
    expect(screen.getByRole('tabpanel', { name: '运行记录' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '同步历史与质量问题' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '盘后主链' })).not.toBeInTheDocument()
  })

  it('exposes six top-level category tabs with one selected state', async () => {
    renderData()

    const tablist = screen.getByRole('tablist', { name: '数据页分类' })
    const expectedTabs = [
      ['数据总览', 'data-overview'],
      ['数据目录', 'data-catalog'],
      ['采集与同步', 'data-collection'],
      ['运行记录', 'data-history'],
      ['来源追踪', 'data-source-trace'],
      ['上游工具', 'data-upstream-tools'],
    ] as const

    for (const [name, panelId] of expectedTabs) {
      expect(within(tablist).getByRole('tab', { name })).toHaveAttribute('aria-controls', panelId)
    }

    const overview = within(tablist).getByRole('tab', { name: '数据总览' })
    const catalog = within(tablist).getByRole('tab', { name: '数据目录' })
    expect(overview).toHaveAttribute('aria-selected', 'true')

    fireEvent.click(catalog)

    expect(catalog).toHaveAttribute('aria-selected', 'true')
    expect(overview).toHaveAttribute('aria-selected', 'false')
  })

  it('opens an exact source trace from a durable URL and separates GitHub from the real producer', async () => {
    renderData(createClient(), undefined, '/data?section=source-trace&trace=stock_daily&run=run-42')

    const panel = await screen.findByRole('tabpanel', { name: '来源追踪' })
    expect(within(panel).getByRole('heading', { name: '来源追踪' })).toHaveFocus()
    expect(await within(panel).findByText('股票日线行情')).toBeInTheDocument()
    expect(within(panel).getByText('日频时序')).toBeInTheDocument()
    expect(within(panel).getByText('按股票和交易日保存的日 K 行情，是图表、选股、回测和增强数据计算的基础。')).toBeInTheDocument()
    expect(within(panel).getByText('交易日期、开盘价、最高价、最低价、收盘价、成交量与成交额。')).toBeInTheDocument()
    const replacementCandidates = within(panel).getByRole('heading', { name: '同类替换候选' })
    const evidenceIssues = within(panel).getByRole('heading', { name: '证据缺口与本地问题' })
    expect(replacementCandidates.compareDocumentPosition(evidenceIssues) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect((await within(panel).findAllByText('腾讯 / 新浪公开行情端点')).length).toBeGreaterThan(0)
    expect(within(panel).getByText(/GitHub 只说明 Adapter 对照，不当数据集父母/)).toBeInTheDocument()
    expect(within(panel).queryByText('GitHub 代码与接口情报')).not.toBeInTheDocument()
    expect(within(panel).getByRole('heading', { name: 'Adapter 对照（GitHub）' })).toBeInTheDocument()
    expect(await within(panel).findByRole('link', { name: /shy3130\/tickflow-stock-panel/ })).toHaveAttribute(
      'href',
      'https://github.com/shy3130/tickflow-stock-panel',
    )
    expect(within(panel).getByText('非运行时依赖')).toBeInTheDocument()
    expect(within(panel).getAllByText('run-42').length).toBeGreaterThan(0)
  })

  it('jumps from a catalog dataset to its matching source trace', async () => {
    renderData()
    const catalog = selectDataCategory('数据目录')
    const dailyCard = (await within(catalog).findByRole('heading', { name: 'Stock daily bars' })).closest('article')!

    fireEvent.click(within(dailyCard).getByRole('button', { name: '追踪 Stock daily bars 来源' }))

    const panel = await screen.findByRole('tabpanel', { name: '来源追踪' })
    expect((await within(panel).findAllByText('stock_daily')).length).toBeGreaterThan(0)
    expect(await within(panel).findByRole('heading', { name: 'Stock daily bars' })).toBeInTheDocument()
    expect(api.dataSourceProvenance).toHaveBeenCalledTimes(1)
  })

  it('keeps collection controls scoped and leaves catalog settings in the catalog', async () => {
    renderData()
    const region = selectDataCategory('采集与同步')

    for (const name of ['立即同步', '数据范围', '新建扩展数据', '测试端点']) {
      expect(within(region).getByRole('button', { name })).toBeInTheDocument()
    }
    for (const name of ['日 K 历史扩展', '重建 Enriched', '指数手动获取', '分钟 K 设置', '清除数据']) {
      expect(within(region).queryByRole('button', { name })).not.toBeInTheDocument()
    }
    openCollectionMaintenance(region)
    for (const name of ['日 K 历史扩展', '重建 Enriched', '指数手动获取', '分钟 K 设置', '清除数据']) {
      expect(within(region).getByRole('button', { name })).toBeInTheDocument()
    }
    expect(within(region).queryByRole('button', { name: '目录显示设置' })).not.toBeInTheDocument()
    expect(within(region).queryByRole('heading', { name: '采集状态' })).not.toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '采集与同步' })).not.toHaveTextContent('8')
    expect(within(region).getByRole('heading', { name: '实时行情' })).toBeInTheDocument()
    expect(within(region).getByRole('heading', { name: '自动调度' })).toBeInTheDocument()
    expect(within(region).getByRole('heading', { name: '市场脉搏' })).toBeInTheDocument()
    expect(within(region).getByRole('heading', { name: '个股融资融券' })).toBeInTheDocument()
    expect(within(region).getByRole('heading', { name: '同花顺官方特色数据' })).toBeInTheDocument()

    const catalog = selectDataCategory('数据目录')
    expect(within(catalog).getByRole('button', { name: '目录显示设置' })).toBeInTheDocument()
  })

  it('does not badge the collection tab with the extension-config count', async () => {
    const client = createClient()
    client.setQueryData(QK.extData, {
      items: Array.from({ length: 8 }, (_, index) => ({
        id: `ext-${index}`,
        label: `扩展 ${index + 1}`,
        mode: 'snapshot' as const,
        fields: [],
        created_at: '2026-07-31T08:00:00Z',
        updated_at: '2026-07-31T08:00:00Z',
      })),
    })
    renderData(client)

    expect(screen.getByRole('tab', { name: '采集与同步' })).not.toHaveTextContent('8')
    const collection = selectDataCategory('采集与同步')
    expect(within(collection).queryByRole('heading', { name: '采集状态' })).not.toBeInTheDocument()
    expect(within(collection).getByRole('heading', { name: '扩展 1' })).toBeInTheDocument()
  })

  it('filters only copied render data and still executes the same catalog query', async () => {
    localStorage.setItem('data-card-visible', JSON.stringify({ etf: false }))
    renderData()
    selectDataCategory('数据目录')

    await waitFor(() => expect(api.dataCatalog).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('heading', { name: 'ETF daily bars' })).not.toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: '封板 L1' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Five-level order book' })).not.toBeInTheDocument()
  })

  it('rescans only through the local POST API, preserves stale results, and invalidates explicit keys', async () => {
    vi.mocked(api.rescanDataCatalog).mockResolvedValue({ ...catalogFixture, stale: true })
    const { client } = renderData()
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    selectDataCategory('数据目录')

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
    const collection = selectDataCategory('采集与同步')
    openCollectionMaintenance(collection)

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
    const collection = selectDataCategory('采集与同步')
    openCollectionMaintenance(collection)

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
    const collection = selectDataCategory('采集与同步')
    openCollectionMaintenance(collection)

    fireEvent.click(await screen.findByRole('button', { name: '清除数据' }))
    fireEvent.click(screen.getAllByRole('button', { name: '清除数据' }).at(-1)!)

    await waitFor(() => expect(api.dataClear).toHaveBeenCalledTimes(1))
    await waitFor(() => expectUnselectedCatalogQueriesRefetched(unselectedQueryFns))
  })

  it('keeps maintenance and legacy history usable when catalog and run queries fail', async () => {
    vi.mocked(api.dataCatalog).mockRejectedValue(new Error('catalog offline'))
    vi.mocked(api.dataCatalogRuns).mockRejectedValue(new Error('runs offline'))
    renderData()

    selectDataCategory('数据目录')
    expect(await screen.findByRole('alert', { name: '数据目录错误' })).toHaveTextContent('catalog offline')
    selectDataCategory('运行记录')
    expect(await screen.findByRole('alert', { name: '运行历史错误' })).toHaveTextContent('runs offline')
    selectDataCategory('采集与同步')
    expect(screen.getByRole('button', { name: '立即同步' })).toBeInTheDocument()
    selectDataCategory('运行记录')
    expect(screen.getByText('暂无同步记录。前往“采集与同步”开始。')).toBeInTheDocument()
  })

  it('keeps the selected catalog entry visible and degrades detail/schema/run failures inline', async () => {
    vi.mocked(api.dataCatalogDataset).mockRejectedValue(new Error('detail offline'))
    vi.mocked(api.dataCatalogSchema).mockRejectedValue(new Error('schema offline'))
    vi.mocked(api.dataCatalogRuns).mockImplementation(async (id) => {
      if (id) throw new Error('dataset runs offline')
      return { dataset_id: null, runs: [] }
    })
    renderData()
    selectDataCategory('数据目录')

    fireEvent.click(await screen.findByRole('button', { name: '查看 Stock daily bars 详情' }))

    const dialog = await screen.findByRole('dialog', { name: 'Stock daily bars 详情' })
    const alert = await within(dialog).findByRole('alert')
    expect(alert).toHaveTextContent('detail offline')
    expect(alert).toHaveTextContent('schema offline')
    expect(alert).toHaveTextContent('dataset runs offline')
    expect(within(dialog).getByText('stock_daily')).toBeInTheDocument()
  })

  it('does not default to TickFlow ready when the capability matrix fails', async () => {
    const client = createClient()
    client.removeQueries({ queryKey: QK.capabilityMatrix })
    vi.mocked(api.capabilityMatrix).mockRejectedValue(new Error('matrix offline'))
    renderData(client)

    const overview = screen.getByRole('tabpanel', { name: '数据总览' })
    expect(await within(overview).findByText(/能力矩阵加载失败: matrix offline/)).toBeInTheDocument()
    expect(within(overview).queryByText('配置已就绪')).not.toBeInTheDocument()
    expect(within(overview).queryByText('配置未就绪')).not.toBeInTheDocument()
  })

  it('keeps none-tier unreadiness separate from existing local catalog data', async () => {
    const client = createClient()
    client.setQueryData(QK.capabilityMatrix, noneTierMatrix)
    vi.mocked(api.capabilityMatrix).mockResolvedValue(noneTierMatrix)
    renderData(client)

    const overview = screen.getByRole('tabpanel', { name: '数据总览' })
    const capabilityCards = within(overview).getByRole('heading', { name: '能力路由' }).closest('section')!
    expect(await within(capabilityCards).findByRole('heading', { name: '日K' })).toBeInTheDocument()
    expect(within(capabilityCards).getByText('配置已就绪')).toBeInTheDocument()
    expect(await within(capabilityCards).findAllByText('本地已有')).not.toHaveLength(0)
    expect(within(capabilityCards).getAllByText('配置未就绪').length).toBeGreaterThan(0)
    expect(within(capabilityCards).getAllByText('目录无记录').length).toBeGreaterThan(0)
  })

  it('points the generic overview config link at native data-sources, not account', async () => {
    const client = createClient()
    client.setQueryData(QK.settings, { mode: 'none', tier_label: 'None', current_endpoint: '', is_admin: true })
    renderData(client)

    const overview = screen.getByRole('tabpanel', { name: '数据总览' })
    expect(within(overview).getByRole('link', { name: '本页数据源' })).toHaveAttribute('href', '/data?section=sources')
    const keyLinks = within(overview).getAllByRole('link', { name: '设置 → 数据密钥' })
    expect(keyLinks.length).toBeGreaterThan(0)
    for (const link of keyLinks) expect(link).toHaveAttribute('href', '/settings?tab=account')
    expect(within(overview).queryByRole('link', { name: '配置' })).not.toBeInTheDocument()
  })

  it('does not treat a loading or failed catalog as having no associated datasets', async () => {
    vi.mocked(api.dataCatalog).mockReturnValue(new Promise(() => {}))
    const loadingClient = createClient()
    loadingClient.removeQueries({ queryKey: QK.dataCatalog })
    renderData(loadingClient)

    const loadingOverview = screen.getByRole('tabpanel', { name: '数据总览' })
    expect(await within(loadingOverview).findAllByText('目录读取中')).not.toHaveLength(0)
    expect(within(loadingOverview).queryByText(/没有可关联的本地数据集/)).not.toBeInTheDocument()

    cleanup()

    vi.mocked(api.dataCatalog).mockRejectedValue(new Error('catalog offline'))
    const errorClient = createClient()
    errorClient.removeQueries({ queryKey: QK.dataCatalog })
    renderData(errorClient)

    const errorOverview = screen.getByRole('tabpanel', { name: '数据总览' })
    expect(await within(errorOverview).findAllByText('目录读取失败，暂无法判断')).not.toHaveLength(0)
    expect(within(errorOverview).queryByText(/没有可关联的本地数据集/)).not.toBeInTheDocument()
  })
})
