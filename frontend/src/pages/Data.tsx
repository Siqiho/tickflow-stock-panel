import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import {
  AlertTriangle,
  Calendar,
  CheckSquare,
  Clock,
  Database,
  History,
  Info,
  Loader2,
  Play,
  Plus,
  RefreshCw,
  SlidersHorizontal,
  Trash2,
  Wifi,
  Wrench,
} from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { EndpointTestDialog } from '@/components/EndpointTestDialog'
import { PageHeader } from '@/components/PageHeader'
import { ActiveJobCard } from '@/components/data/ActiveJobCard'
import { AdvancedDisclosure } from '@/components/data/AdvancedDisclosure'
import {
  DataOverviewControlPanel,
  datasetControlFacts,
} from '@/components/data/ControlPlaneSummary'
import { DataCatalogSection } from '@/components/data/DataCatalogSection'
import { DataOperationsHistory } from '@/components/data/DataOperationsHistory'
import { DataPageCategoryNav, type DataPageSectionId } from '@/components/data/DataPageCategoryNav'
import { DataSourceTracePanel } from '@/components/data/DataSourceTracePanel'
import { DatasetDetailDrawer } from '@/components/data/DatasetDetailDrawer'
import { EnrichedRebuildPanel } from '@/components/data/EnrichedRebuildPanel'
import { ExtendHistoryPanel } from '@/components/data/ExtendHistoryPanel'
import { RepairDailyPanel } from '@/components/data/RepairDailyPanel'
import { RegimeConfigCard } from '@/components/data/RegimeConfigCard'
import { MinuteSyncConfig } from '@/components/data/MinuteSyncConfig'
import { MarginTradingSyncCard } from '@/components/data/MarginTradingSyncCard'
import { MarketPulseSyncCard } from '@/components/data/MarketPulseSyncCard'
import { HithinkSpecialDataSyncCard } from '@/components/data/HithinkSpecialDataSyncCard'
import { PageSettingsModal, getCardVisibility, type CardKey } from '@/components/data/PageSettingsModal'
import { PipelineScopeConfig } from '@/components/data/PipelineScopeConfig'
import { QuoteConfigCard } from '@/components/data/QuoteConfigCard'
import { ScheduleEditor } from '@/components/data/ScheduleEditor'
import { HistoryRow } from '@/components/data/SectionTitle'
import { SettingsModal } from '@/components/data/SettingsModal'
import { StorageBreakdownCard } from '@/components/data/StorageBreakdownCard'
import { Skeleton } from '@/components/data/Skeleton'
import { CreateExtDialog } from '@/components/ext-data/CreateExtDialog'
import { EditExtDialog } from '@/components/ext-data/EditExtDialog'
import { ExtDataStatCard } from '@/components/ext-data/ExtDataStatCard'
import { formatScheduleDatePart, formatScheduleTimePart, isToday } from '@/lib/format'
import { api, type CatalogResponse, type DatasetCatalogEntry, type ExtDataConfig } from '@/lib/api'
import {
  INDEX_DAILY_CATALOG_DATASETS,
  invalidateIndexCatalogQueries,
} from '@/lib/indexCatalogInvalidation'
import { QK } from '@/lib/queryKeys'
import { DATA_KEYS_SETTINGS_HREF, DATA_SOURCES_SETTINGS_HREF } from '@/lib/dataSources'
import { useToggleRealtimeQuotes, useUpdateQuoteInterval } from '@/lib/useSharedMutations'
import { SettingsDataSourcesPanel } from '@/pages/settings/DataSources'
import {
  useCapabilities,
  useDataCatalog,
  useDataStatus,
  usePreferences,
  useQuoteInterval,
  useQuoteStatus,
  useSettings,
} from '@/lib/useSharedQueries'

const CATALOG_GROUP_BY_DATASET: Record<string, CardKey> = {
  stock_instruments: 'instruments',
  stock_daily: 'daily',
  stock_adj_factor: 'adj_factor',
  stock_enriched: 'enriched',
  stock_minute: 'minute',
}

const SECTION_QUERY: Record<DataPageSectionId, string> = {
  'data-overview': 'overview',
  'data-catalog': 'catalog',
  'data-collection': 'collection',
  'data-history': 'history',
  'data-source-trace': 'source-trace',
  'data-upstream-tools': 'upstream-tools',
}

function sectionFromQuery(value: string | null): DataPageSectionId {
  if (value === 'sources') return 'data-overview'
  const entry = Object.entries(SECTION_QUERY).find(([, queryValue]) => queryValue === value)
  return (entry?.[0] as DataPageSectionId | undefined) ?? 'data-overview'
}

const REFERENCE_VISIBILITY_DATASET_IDS = new Set([
  'trading_calendar',
  'valuation_daily',
  'limit_up_events',
  'index_membership_history',
  'corporate_actions',
])

function catalogVisibilityGroup(datasetId: string): CardKey | null {
  if (datasetId === 'stock_margin_trading' || datasetId.startsWith('stock_f10_')) return 'f10'
  // 参考/派生数据集必须先于 index_ 前缀判断, 否则 index_membership_history 会被归错组
  if (REFERENCE_VISIBILITY_DATASET_IDS.has(datasetId)) return 'reference'
  if (CATALOG_GROUP_BY_DATASET[datasetId]) return CATALOG_GROUP_BY_DATASET[datasetId]
  if (datasetId.startsWith('index_')) return 'index'
  if (datasetId === 'market_pulse') return 'index'
  if (datasetId.startsWith('etf_')) return 'etf'
  if (datasetId.startsWith('financial_')) return 'financials'
  return null
}

function filterCatalogForRendering(
  catalog: CatalogResponse | undefined,
  visible: Record<CardKey, boolean>,
): CatalogResponse | undefined {
  if (!catalog) return undefined
  return {
    ...catalog,
    datasets: catalog.datasets.filter((entry) => {
      const group = catalogVisibilityGroup(entry.descriptor.dataset_id)
      return group === null || visible[group]
    }),
  }
}

function warningMessage(label: string, error: unknown): string | null {
  if (!error) return null
  const message = error instanceof Error ? error.message : String(error)
  return `${label}：${message}`
}

function DataPagePanel({
  activeId,
  children,
  id,
}: {
  activeId: DataPageSectionId
  children: ReactNode
  id: DataPageSectionId
}) {
  if (activeId !== id) return null

  return (
    <section id={id} role="tabpanel" aria-labelledby={`${id}-tab`} tabIndex={0} className="space-y-4 outline-none">
      {children}
    </section>
  )
}

export function Data() {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedSection = sectionFromQuery(searchParams.get('section'))
  const catalogGroup = searchParams.get('group')
  const traceSubjectId = searchParams.get('trace')
  const traceRunId = searchParams.get('run')
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [selectedDataset, setSelectedDataset] = useState<DatasetCatalogEntry | null>(null)
  const [openSettings, setOpenSettings] = useState<string | null>(null)
  const [showScheduleEdit, setShowScheduleEdit] = useState(false)
  const [showInstScheduleEdit, setShowInstScheduleEdit] = useState(false)
  const [showClearConfirm, setShowClearConfirm] = useState(false)
  const [showEndpointTest, setShowEndpointTest] = useState(false)
  const [showCreateExt, setShowCreateExt] = useState(false)
  const [editingExt, setEditingExt] = useState<ExtDataConfig | null>(null)
  const [showIntervalEdit, setShowIntervalEdit] = useState(false)
  const [indexExtendValue, setIndexExtendValue] = useState(6)
  const [indexExtendUnit, setIndexExtendUnit] = useState<'month' | 'year'>('month')
  const [indexBatchInput, setIndexBatchInput] = useState('100')
  const [visibilityVersion, setVisibilityVersion] = useState(0)
  const topRef = useRef<HTMLDivElement>(null)

  const caps = useCapabilities()
  const settings = useSettings()
  const isAdmin = settings.data?.is_admin === true
  const activeSection = isAdmin || requestedSection === 'data-overview' || requestedSection === 'data-catalog'
    ? requestedSection
    : 'data-overview'
  const prefs = usePreferences()
  const status = useDataStatus({ refetchInterval: activeJobId ? 2_000 : 30_000 })
  const catalog = useDataCatalog({ refetchInterval: activeJobId ? 2_000 : 30_000 })
  const history = useQuery({
    queryKey: QK.pipelineJobs,
    queryFn: () => api.pipelineJobs(15),
    enabled: isAdmin,
    refetchInterval: activeJobId ? false : 60_000,
  })
  const allRuns = useQuery({
    queryKey: QK.dataCatalogRuns(),
    queryFn: () => api.dataCatalogRuns(),
    enabled: isAdmin,
  })
  const controlSummary = useQuery({
    queryKey: QK.dataControlSummary,
    queryFn: api.dataControlSummary,
    enabled: isAdmin,
  })
  const sourceProvenance = useQuery({
    queryKey: QK.dataSourceProvenance,
    queryFn: api.dataSourceProvenance,
    enabled: isAdmin && (activeSection === 'data-source-trace' || activeSection === 'data-overview'),
  })
  const job = useQuery({
    queryKey: QK.pipelineJob(activeJobId ?? ''),
    queryFn: () => api.pipelineJob(activeJobId!),
    enabled: isAdmin && Boolean(activeJobId),
    refetchInterval: (query) => {
      const current = query.state.data
      return current && ['succeeded', 'degraded', 'failed'].includes(current.status) ? false : 1_000
    },
  })
  const extConfigs = useQuery({ queryKey: QK.extData, queryFn: api.extDataList, enabled: isAdmin })

  const selectedDatasetId = selectedDataset?.descriptor.dataset_id ?? ''
  const selectedDetail = useQuery({
    queryKey: QK.dataCatalogDataset(selectedDatasetId),
    queryFn: () => api.dataCatalogDataset(selectedDatasetId),
    enabled: Boolean(selectedDatasetId),
  })
  const selectedSchema = useQuery({
    queryKey: QK.dataCatalogSchema(selectedDatasetId),
    queryFn: () => api.dataCatalogSchema(selectedDatasetId),
    enabled: Boolean(selectedDatasetId),
  })
  const selectedRuns = useQuery({
    queryKey: QK.dataCatalogRuns(selectedDatasetId),
    queryFn: () => api.dataCatalogRuns(selectedDatasetId),
    enabled: isAdmin && Boolean(selectedDatasetId),
  })

  useEffect(() => {
    const handleVisibilityChange = () => setVisibilityVersion((version) => version + 1)
    window.addEventListener('data-card-visible-change', handleVisibilityChange)
    return () => window.removeEventListener('data-card-visible-change', handleVisibilityChange)
  }, [])

  const cardVisibility = getCardVisibility(caps.data?.capabilities)
  void visibilityVersion
  const renderCatalog = filterCatalogForRendering(catalog.data, cardVisibility)

  const startSync = useMutation({
    mutationFn: api.pipelineRun,
    onSuccess: ({ job_id }) => setActiveJobId(job_id),
  })
  const clearData = useMutation({
    mutationFn: api.dataClear,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: QK.dataStatus, exact: true }),
        queryClient.invalidateQueries({ queryKey: QK.dataCatalog }),
        queryClient.invalidateQueries({ queryKey: QK.dataControlSummary, exact: true }),
        queryClient.invalidateQueries({ queryKey: QK.pipelineJobs, exact: true }),
      ])
      setShowClearConfirm(false)
    },
  })
  const rescanCatalog = useMutation({
    mutationFn: () => api.rescanDataCatalog(),
    onSuccess: async (response) => {
      queryClient.setQueryData(QK.dataCatalog, response)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: QK.dataStatus, exact: true }),
        queryClient.invalidateQueries({ queryKey: QK.dataCatalogRuns(), exact: true }),
        queryClient.invalidateQueries({ queryKey: QK.dataControlSummary, exact: true }),
      ])
      if (selectedDatasetId) {
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: QK.dataCatalogDataset(selectedDatasetId), exact: true }),
          queryClient.invalidateQueries({ queryKey: QK.dataCatalogSchema(selectedDatasetId), exact: true }),
          queryClient.invalidateQueries({ queryKey: QK.dataCatalogRuns(selectedDatasetId), exact: true }),
        ])
      }
    },
  })
  const deleteExt = useMutation({
    mutationFn: (id: string) => api.extDataDelete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QK.extData }),
  })

  const pipelineSchedule = prefs.data?.pipeline_schedule ?? { hour: 15, minute: 30 }
  const instrumentsSchedule = prefs.data?.instruments_schedule ?? { hour: 9, minute: 10 }
  const minuteAuto = prefs.data?.minute_sync_enabled ?? false
  const indexAuto = prefs.data?.pipeline_pull_index ?? true
  const etfAuto = prefs.data?.pipeline_pull_etf ?? false
  const indexDailyBatchSize = prefs.data?.index_daily_batch_size ?? 100

  const updateSchedule = useMutation({
    mutationFn: ({ hour, minute }: { hour: number; minute: number }) => api.updatePipelineSchedule(hour, minute),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: QK.preferences }),
        queryClient.invalidateQueries({ queryKey: QK.dataStatus }),
      ])
      setShowScheduleEdit(false)
    },
  })
  const updateInstSchedule = useMutation({
    mutationFn: ({ hour, minute }: { hour: number; minute: number }) => api.updateInstrumentsSchedule(hour, minute),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: QK.preferences }),
        queryClient.invalidateQueries({ queryKey: QK.dataStatus }),
      ])
      setShowInstScheduleEdit(false)
    },
  })

  const hasDailyBatchCap = Boolean(caps.data?.capabilities?.['kline.daily.batch'])
  const indexEarliestDate = status.data?.index_daily?.earliest_date ?? status.data?.index_enriched?.earliest_date ?? null
  const indexOffsetDays = indexExtendUnit === 'month' ? indexExtendValue * 30 : indexExtendValue * 365
  const indexTargetDate = new Date(indexEarliestDate ?? Date.now())
  indexTargetDate.setDate(indexTargetDate.getDate() - indexOffsetDays)
  const indexTargetDateText = indexTargetDate.toISOString().slice(0, 10)
  const indexSyncDays = Math.min(5000, Math.max(30, Math.ceil((Date.now() - indexTargetDate.getTime()) / 86_400_000) + 1))
  const syncIndexDaily = useMutation({
    mutationFn: () => api.syncIndexDaily(indexSyncDays),
    onSuccess: async () => {
      await Promise.all([
        invalidateIndexCatalogQueries(queryClient, INDEX_DAILY_CATALOG_DATASETS),
        queryClient.invalidateQueries({ queryKey: QK.indexList, exact: true }),
        queryClient.invalidateQueries({ queryKey: QK.indexQuotes, exact: true }),
      ])
    },
  })
  const updateIndexBatchSize = useMutation({
    mutationFn: (size: number) => api.updateIndexDailyBatchSize(size),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QK.preferences }),
  })

  useEffect(() => setIndexBatchInput(String(indexDailyBatchSize)), [indexDailyBatchSize])

  const quoteInterval = useQuoteInterval()
  const quoteStatus = useQuoteStatus()
  const updateInterval = useUpdateQuoteInterval()
  const toggleQuote = useToggleRealtimeQuotes()
  const handleToggleIntervalEdit = useCallback((fromEvent?: boolean) => {
    setShowIntervalEdit((current) => {
      const next = !current
      if (!fromEvent) window.dispatchEvent(new CustomEvent('quote-interval-editor-toggle', { detail: { source: 'data' } }))
      return next
    })
  }, [])
  useEffect(() => {
    const handler = (event: Event) => {
      if ((event as CustomEvent).detail?.source !== 'data') setShowIntervalEdit((current) => !current)
    }
    window.addEventListener('quote-interval-editor-toggle', handler)
    return () => window.removeEventListener('quote-interval-editor-toggle', handler)
  }, [])

  const terminalJobStatus = job.data?.status
  useEffect(() => {
    if (!terminalJobStatus || !['succeeded', 'degraded', 'failed'].includes(terminalJobStatus)) return undefined
    void queryClient.invalidateQueries({ queryKey: QK.dataStatus, exact: true })
    void queryClient.invalidateQueries({ queryKey: QK.dataCatalog })
    void queryClient.invalidateQueries({ queryKey: QK.dataControlSummary, exact: true })
    void queryClient.invalidateQueries({ queryKey: QK.pipelineJobs, exact: true })
    const timer = window.setTimeout(() => setActiveJobId(null), 5_000)
    return () => window.clearTimeout(timer)
  }, [queryClient, terminalJobStatus])

  useEffect(() => {
    if (job.isError && /404/.test(String((job.error as Error)?.message ?? ''))) setActiveJobId(null)
  }, [job.error, job.isError])
  useEffect(() => {
    if (isAdmin && !activeJobId && history.data?.active_id) setActiveJobId(history.data.active_id)
  }, [activeJobId, history.data?.active_id, isAdmin])

  const handleJobClick = useCallback((id: string) => {
    setActiveJobId(id)
    requestAnimationFrame(() => topRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }, [])

  const handleSectionSelect = useCallback((id: DataPageSectionId) => {
    const allowedId = isAdmin || id === 'data-overview' || id === 'data-catalog'
      ? id
      : 'data-overview'
    const next = new URLSearchParams(searchParams)
    if (allowedId === 'data-overview') next.delete('section')
    else next.set('section', SECTION_QUERY[allowedId])
    if (allowedId !== 'data-source-trace') {
      next.delete('trace')
      next.delete('run')
    }
    if (allowedId !== 'data-catalog') next.delete('group')
    setSearchParams(next)
    setSelectedDataset(null)
    requestAnimationFrame(() => topRef.current?.scrollIntoView?.({ block: 'start' }))
  }, [isAdmin, searchParams, setSearchParams])

  const handleTraceSource = useCallback((subjectId: string, runId?: string) => {
    if (!isAdmin) return
    const next = new URLSearchParams(searchParams)
    next.set('section', SECTION_QUERY['data-source-trace'])
    next.set('trace', subjectId)
    next.delete('group')
    if (runId) next.set('run', runId)
    else next.delete('run')
    setSelectedDataset(null)
    setSearchParams(next)
  }, [isAdmin, searchParams, setSearchParams])

  const handleOpenCatalogGroup = useCallback((group: string) => {
    const next = new URLSearchParams(searchParams)
    next.set('section', SECTION_QUERY['data-catalog'])
    next.set('group', group)
    next.delete('trace')
    next.delete('run')
    setSelectedDataset(null)
    setSearchParams(next)
  }, [searchParams, setSearchParams])

  useEffect(() => {
    if (searchParams.get('section') !== 'sources') return undefined
    const frame = requestAnimationFrame(() => {
      document.getElementById('data-unified-sources')?.scrollIntoView?.({ block: 'start' })
    })
    return () => cancelAnimationFrame(frame)
  }, [searchParams])

  useEffect(() => {
    if (!isAdmin || activeSection !== 'data-source-trace') return
    const frame = requestAnimationFrame(() => {
      const heading = document.getElementById('source-provenance-heading')
      heading?.scrollIntoView?.({ block: 'start' })
      heading?.focus?.()
    })
    return () => cancelAnimationFrame(frame)
  }, [activeSection, isAdmin, traceSubjectId])

  const dataStatus = status.data
  const hasData = Boolean(dataStatus?.instruments?.rows || dataStatus?.daily?.rows)
  const isRunning = job.data?.status === 'running' || job.data?.status === 'pending'
  const isNoKey = settings.data?.mode === 'none'
  const minuteFeature = caps.data?.features?.minute ?? caps.data?.minute
  const hasMinuteCap = Boolean(
    minuteFeature?.full_market_sync_allowed
    || (caps.data?.capabilities?.['kline.minute.batch'] && !(caps.data.capabilities['kline.minute.batch'] as { view_only?: boolean })?.view_only),
  )
  const hasAdjCap = Boolean(caps.data?.capabilities?.adj_factor)
  const hasFinancialPublic = prefs.data?.financial_provider === 'public' || Boolean(caps.data?.capabilities?.financial)
  const pipelineSteps = [
    '日K',
    ...(hasAdjCap ? ['复权'] : []),
    ...(hasFinancialPublic && prefs.data?.financial_provider === 'public' ? ['财务'] : []),
    '指标',
    ...(indexAuto ? ['指数'] : []),
    ...(etfAuto ? ['ETF'] : []),
    ...(hasMinuteCap && minuteAuto ? ['分钟K'] : []),
  ]
  const catalogState = catalog.isError ? 'error' : catalog.data ? 'ready' : 'loading'

  const detailWarnings = [
    warningMessage('详情暂不可用，保留目录快照', selectedDetail.error),
    warningMessage('Schema 暂不可用，使用目录字段', selectedSchema.error),
    warningMessage('数据集运行记录暂不可用', selectedRuns.error),
  ].filter((message): message is string => Boolean(message))

  return (
    <>
      <div ref={topRef} />
      <PageHeader
        title="数据"
        subtitle={isAdmin ? '本地数据画像 · 同步状态 · 历史记录' : '共享市场数据 · 覆盖范围 · 数据目录'}
        className="sticky top-0 z-30 flex-wrap gap-y-2 bg-base xl:flex-nowrap"
        right={(
          <DataPageCategoryNav
            activeId={activeSection}
            catalogCount={catalog.data?.datasets.length}
            isAdmin={isAdmin}
            onSelect={handleSectionSelect}
          />
        )}
      />

      <div className={`${activeSection === 'data-source-trace' ? 'max-w-[100rem]' : 'max-w-6xl'} space-y-8 px-8 py-6`}>
        {!isAdmin && (
          <div className="rounded-card border border-accent/25 bg-accent/5 px-4 py-3 text-xs leading-relaxed text-secondary">
            <span className="font-medium text-foreground">所有账户读取同一份服务器市场数据。</span>
            自选、页面偏好、策略、报告和 Agent 会话仍按账户隔离；同步、重建和清除操作只由管理员执行。
          </div>
        )}
        <DataPagePanel activeId={activeSection} id="data-overview">
          <div>
            <h2 id="data-system-status-heading" className="flex items-center gap-2 text-base font-semibold text-foreground">
              <Database aria-hidden="true" className="h-4 w-4 text-secondary" />
              数据系统状态
            </h2>
            <p className="mt-1 text-xs text-muted">本地 catalog 报告的存储事实与当前运行状态</p>
          </div>
          {isAdmin && isNoKey && (
            <div className="flex items-center gap-2 rounded-card border border-border bg-elevated/40 px-3 py-2 text-xs">
              <Info aria-hidden="true" className="h-4 w-4 shrink-0 text-muted" />
              <span className="text-secondary">当前使用免费历史数据模式；实时行情等扩展能力可在 <Link to={DATA_SOURCES_SETTINGS_HREF} className="font-medium text-accent hover:underline">本页数据源</Link> 中配置提供方；密钥仍在 <Link to={DATA_KEYS_SETTINGS_HREF} className="font-medium text-accent hover:underline">设置 → 数据密钥</Link>。</span>
            </div>
          )}
          {isAdmin && job.data && <ActiveJobCard job={job.data} />}
          <SettingsDataSourcesPanel
            readOnly={!isAdmin}
            catalog={catalog.data}
            catalogState={catalogState}
            provenance={isAdmin ? sourceProvenance.data : undefined}
            includeExternal={isAdmin}
            onOpenDataset={setSelectedDataset}
            onTraceSource={isAdmin ? handleTraceSource : undefined}
          />
          {isAdmin && (
            <DataOverviewControlPanel
              summary={controlSummary.data}
              error={controlSummary.error as Error | null}
              onTraceSource={handleTraceSource}
            />
          )}
          {catalog.data ? (
            <StorageBreakdownCard
              storage={catalog.data.storage}
              refreshedAt={catalog.data.refreshed_at}
              isStale={catalog.isCatalogStale}
              headingLevel={3}
              managedOnly={!isAdmin}
              onTraceSource={isAdmin ? handleTraceSource : undefined}
              onOpenCatalogGroup={isAdmin ? handleOpenCatalogGroup : undefined}
            />
          ) : catalog.error ? (
            <div role="alert" className="rounded-card border border-danger/30 bg-danger/5 p-4 text-sm text-danger">
              本地存储状态暂不可用：{(catalog.error as Error).message}
            </div>
          ) : (
            <div className="rounded-card border border-border bg-surface p-4 text-sm text-muted">正在读取本地存储状态</div>
          )}
          {status.isError && (
            <div role="status" className="rounded-btn border border-warning/30 bg-warning/5 px-3 py-2 text-xs text-warning">
              运行状态刷新失败，catalog 与维护操作仍可使用。
            </div>
          )}
        </DataPagePanel>

        <DataPagePanel activeId={activeSection} id="data-catalog">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 id="data-catalog-region-heading" className="text-base font-semibold text-foreground">数据集目录</h2>
              <p className="mt-1 text-xs text-muted">只读查看本地数据、覆盖、质量、Schema 与血缘</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {isAdmin && (
                <button
                  type="button"
                  onClick={() => rescanCatalog.mutate()}
                  disabled={rescanCatalog.isPending}
                  className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-elevated px-3 py-1.5 text-xs text-secondary hover:text-foreground disabled:opacity-40"
                >
                  {rescanCatalog.isPending ? <Loader2 aria-hidden="true" className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw aria-hidden="true" className="h-3.5 w-3.5" />}
                  {rescanCatalog.isPending ? '扫描中…' : '重新扫描本地目录'}
                </button>
              )}
              <button
                type="button"
                onClick={() => setOpenSettings('page-settings')}
                className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-elevated px-3 py-1.5 text-xs text-secondary hover:text-foreground"
              >
                <SlidersHorizontal aria-hidden="true" className="h-3.5 w-3.5" />
                目录显示设置
              </button>
            </div>
          </div>
          {rescanCatalog.isError && (
            <div role="alert" className="rounded-btn border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">
              本地目录扫描失败：{(rescanCatalog.error as Error).message}
            </div>
          )}
          <DataCatalogSection
            catalog={renderCatalog}
            isStale={catalog.isCatalogStale}
            error={catalog.error as Error | null}
            onSelectDataset={setSelectedDataset}
            headingLevel={3}
            controlSummary={isAdmin ? controlSummary.data : undefined}
            onTraceSource={isAdmin ? handleTraceSource : undefined}
            focusGroup={catalogGroup}
            isAdmin={isAdmin}
          />
        </DataPagePanel>

        {isAdmin && <DataPagePanel activeId={activeSection} id="data-collection">
          <div>
            <h2 id="data-pipeline-heading" className="flex items-center gap-2 text-base font-semibold text-foreground">
              <Calendar aria-hidden="true" className="h-4 w-4 text-secondary" />
              盘后主链
            </h2>
            <p className="mt-1 text-xs text-muted">立即同步写入盘后管道；补洞、重建和清除在维护里，默认收起</p>
          </div>
          <div className="space-y-4 rounded-card border border-border bg-surface p-4">
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={() => startSync.mutate()} disabled={startSync.isPending || isRunning} className="inline-flex items-center gap-1.5 rounded-btn bg-accent px-3 py-1.5 text-xs font-medium text-base disabled:opacity-40">
                {startSync.isPending || isRunning ? <Loader2 aria-hidden="true" className="h-3.5 w-3.5 animate-spin" /> : <Play aria-hidden="true" className="h-3.5 w-3.5" />}
                {startSync.isPending ? '启动中…' : isRunning ? '同步中…' : '立即同步'}
              </button>
              <button type="button" onClick={() => setOpenSettings('pipeline-scope')} className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-elevated px-3 py-1.5 text-xs text-secondary hover:text-foreground"><CheckSquare aria-hidden="true" className="h-3.5 w-3.5" />数据范围</button>
            </div>
            {startSync.isError && <div role="alert" className="rounded-btn border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">启动失败：{(startSync.error as Error).message}</div>}
            <div>
              <div className="mb-3 flex items-center gap-2"><h3 className="text-sm font-medium text-foreground">自动调度</h3></div>
              {status.isLoading ? <div className="space-y-2"><Skeleton w="w-16" /><Skeleton w="w-28" /></div> : (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center gap-1.5 border-b border-border/50 pb-2 text-[10px] text-muted"><span>盘前 个股维表</span><span>→</span><span>盘后 {pipelineSteps.join(' → ')}</span></div>
                  <div className="flex items-center justify-between text-[11px]"><span className="text-muted">时区</span><span className="font-mono text-secondary">Asia/Shanghai</span></div>
                  <ScheduleLine label="盘前 · 个股维表" schedule={instrumentsSchedule} lastRun={dataStatus?.last_instruments_run} nextRun={dataStatus?.next_instruments_run} open={showInstScheduleEdit} onToggle={() => setShowInstScheduleEdit((value) => !value)} />
                  {showInstScheduleEdit && <ScheduleEditor value={instrumentsSchedule} onSave={(hour, minute) => updateInstSchedule.mutate({ hour, minute })} loading={updateInstSchedule.isPending} hint="不晚于 09:15" />}
                  <ScheduleLine label="盘后 · 全量管道" schedule={pipelineSchedule} lastRun={dataStatus?.last_pipeline_run} nextRun={dataStatus?.next_pipeline_run} open={showScheduleEdit} onToggle={() => setShowScheduleEdit((value) => !value)} />
                  {showScheduleEdit && <ScheduleEditor value={pipelineSchedule} onSave={(hour, minute) => updateSchedule.mutate({ hour, minute })} loading={updateSchedule.isPending} hint="不早于 15:00" />}
                </div>
              )}
            </div>
            <AdvancedDisclosure label="维护">
              <p className="mb-2 text-[11px] text-muted">补洞、重建和清除，不是每天要看的同步</p>
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => setOpenSettings('daily')} disabled={!hasData} className="rounded-btn border border-border bg-elevated px-3 py-1.5 text-xs text-secondary hover:text-foreground disabled:opacity-40">日 K 历史扩展</button>
                <button type="button" onClick={() => setOpenSettings('enriched')} disabled={!hasData} className="rounded-btn border border-border bg-elevated px-3 py-1.5 text-xs text-secondary hover:text-foreground disabled:opacity-40">重建 Enriched</button>
                <button type="button" onClick={() => setOpenSettings('index')} disabled={!hasData} className="rounded-btn border border-border bg-elevated px-3 py-1.5 text-xs text-secondary hover:text-foreground disabled:opacity-40">指数手动获取</button>
                <button type="button" onClick={() => setOpenSettings('minute')} disabled={!hasData} className="rounded-btn border border-border bg-elevated px-3 py-1.5 text-xs text-secondary hover:text-foreground disabled:opacity-40">分钟 K 设置</button>
                <button type="button" onClick={() => setShowClearConfirm(true)} disabled={isRunning} className="inline-flex items-center gap-1.5 rounded-btn border border-danger/30 px-3 py-1.5 text-xs text-danger hover:bg-danger/5 disabled:opacity-40"><Trash2 aria-hidden="true" className="h-3.5 w-3.5" />清除数据</button>
              </div>
            </AdvancedDisclosure>
          </div>
          <MarketPulseSyncCard onTraceSource={handleTraceSource} />
          <MarginTradingSyncCard onTraceSource={handleTraceSource} />
          <HithinkSpecialDataSyncCard onTraceSource={handleTraceSource} />
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <QuoteConfigCard
              enabled={prefs.data?.realtime_quotes_enabled ?? false}
              running={quoteStatus.data?.running ?? false}
              isTrading={quoteStatus.data?.is_trading_hours ?? false}
              lastFetchMs={quoteStatus.data?.last_fetch_ms ?? null}
              intervalS={quoteInterval.data?.interval ?? quoteStatus.data?.interval_s ?? 15}
              intervalMin={quoteInterval.data?.min_interval ?? 5}
              intervalMax={quoteInterval.data?.max_interval ?? 60}
              loading={quoteStatus.isLoading}
              onToggle={(value) => toggleQuote.mutate(value)}
              toggling={toggleQuote.isPending}
              showIntervalEdit={showIntervalEdit}
              onShowIntervalEdit={handleToggleIntervalEdit}
              onIntervalChange={(value) => updateInterval.mutate(value)}
            />
          </div>
          <div>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-xs font-medium uppercase tracking-widest text-secondary">扩展数据配置</h3>
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => setShowCreateExt(true)} className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-elevated px-3 py-1.5 text-xs text-secondary hover:text-foreground"><Plus aria-hidden="true" className="h-3.5 w-3.5" />新建扩展数据</button>
                <button type="button" onClick={() => setShowEndpointTest(true)} className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-elevated px-3 py-1.5 text-xs text-secondary hover:text-foreground"><Wifi aria-hidden="true" className="h-3.5 w-3.5" />测试端点</button>
              </div>
            </div>
            {(extConfigs.data?.items ?? []).length > 0 && (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {(extConfigs.data?.items ?? []).map((config) => (
                  <ExtDataStatCard key={config.id} config={config} onDelete={() => deleteExt.mutate(config.id)} deleting={deleteExt.isPending} onEdit={() => setEditingExt(config)} onTraceSource={() => handleTraceSource(config.id)} />
                ))}
              </div>
            )}
          </div>
        </DataPagePanel>}

        {isAdmin && <DataPagePanel activeId={activeSection} id="data-history">
          <div>
            <h2 id="data-history-heading" className="flex items-center gap-2 text-base font-semibold text-foreground"><History aria-hidden="true" className="h-4 w-4 text-secondary" />同步历史与质量问题</h2>
            <p className="mt-1 text-xs text-muted">本地控制库运行记录与兼容的管道任务历史</p>
          </div>
          {allRuns.isError && <div role="alert" aria-label="运行历史错误" className="rounded-btn border border-warning/30 bg-warning/5 px-3 py-2 text-xs text-warning">本地运行历史暂不可用：{(allRuns.error as Error).message}</div>}
          <DataOperationsHistory runs={allRuns.data?.runs ?? []} control={controlSummary.data} onTraceSource={handleTraceSource} />
          <div>
            <h3 className="flex items-center gap-2 text-xs font-medium uppercase tracking-widest text-secondary"><Clock aria-hidden="true" className="h-4 w-4" />管道任务历史</h3>
            <div className="mt-3 overflow-hidden rounded-card border border-border">
              {history.isLoading ? <div className="px-5 py-6"><Skeleton w="w-28" /></div> : history.data && history.data.jobs.length > 0 ? (
                <div className="divide-y divide-border">{history.data.jobs.map((item) => <HistoryRow key={item.id} job={item} onClick={() => handleJobClick(item.id)} />)}</div>
              ) : <div className="px-5 py-8 text-center text-sm text-muted">暂无同步记录。前往“采集与同步”开始。</div>}
            </div>
          </div>
        </DataPagePanel>}


        {isAdmin && <DataPagePanel activeId={activeSection} id="data-upstream-tools">
          <div>
            <h2 id="data-upstream-tools-heading" className="flex items-center gap-2 text-base font-semibold text-foreground">
              <Wrench aria-hidden="true" className="h-4 w-4 text-secondary" />
              上游原版数据工具
            </h2>
            <p className="mt-1 text-xs text-muted">
              从 tickflow-stock-panel 迁入的原版数据页能力，和本页改版后的目录、采集同步、来源追踪分开存放，避免互相抢布局。
            </p>
          </div>
          <RepairDailyPanel caps={caps.data} isRunning={Boolean(activeJobId)} latestDate={dataStatus?.daily?.latest_date ?? null} onStart={() => undefined} />
          <RegimeConfigCard />
        </DataPagePanel>}
        {isAdmin && <DataPagePanel activeId={activeSection} id="data-source-trace">
          <DataSourceTracePanel
            data={sourceProvenance.data}
            error={sourceProvenance.error as Error | null}
            selectedId={traceSubjectId}
            selectedRunId={traceRunId}
            onSelect={(subjectId) => handleTraceSource(subjectId, traceRunId ?? undefined)}
          />
        </DataPagePanel>}
      </div>

      <DatasetDetailDrawer
        entry={selectedDetail.data ?? selectedDataset}
        schema={selectedSchema.data}
        runs={isAdmin ? selectedRuns.data?.runs ?? [] : []}
        warnings={detailWarnings}
        control={isAdmin ? datasetControlFacts(controlSummary.data, selectedDatasetId) : undefined}
        controlStale={isAdmin ? controlSummary.data?.catalog_stale : false}
        onClose={() => setSelectedDataset(null)}
        onTraceSource={isAdmin ? handleTraceSource : undefined}
      />
      {isAdmin && showEndpointTest && <EndpointTestDialog hasKey={settings.data?.mode === 'api_key'} tierLabel={settings.data?.tier_label ?? ''} currentEndpoint={settings.data?.current_endpoint ?? ''} onClose={() => setShowEndpointTest(false)} />}
      <AnimatePresence>
        {isAdmin && showCreateExt && <CreateExtDialog onClose={() => setShowCreateExt(false)} />}
        {isAdmin && editingExt && <EditExtDialog config={editingExt} onClose={() => setEditingExt(null)} />}
      </AnimatePresence>
      <AnimatePresence>
        {isAdmin && openSettings === 'daily' && <SettingsModal title="日 K · 向前扩展历史" onClose={() => setOpenSettings(null)}><ExtendHistoryPanel caps={caps.data} isRunning={Boolean(activeJobId)} earliestDate={dataStatus?.daily?.earliest_date ?? null} onStart={() => setOpenSettings(null)} /></SettingsModal>}
        {isAdmin && openSettings === 'enriched' && <SettingsModal title="Enriched · 计算设置" onClose={() => setOpenSettings(null)}><EnrichedRebuildPanel isRunning={Boolean(activeJobId)} onStart={() => setOpenSettings(null)} /></SettingsModal>}
        {isAdmin && openSettings === 'pipeline-scope' && <SettingsModal title="盘后管道 · 拉取内容" onClose={() => setOpenSettings(null)}><PipelineScopeConfig /></SettingsModal>}
        {openSettings === 'page-settings' && <SettingsModal title="页面设置 · 目录显隐" onClose={() => setOpenSettings(null)}><PageSettingsModal caps={caps.data?.capabilities} /></SettingsModal>}
        {isAdmin && openSettings === 'index' && <SettingsModal title="指数 · 手动获取" onClose={() => setOpenSettings(null)}><IndexSettings indexExtendValue={indexExtendValue} setIndexExtendValue={setIndexExtendValue} indexExtendUnit={indexExtendUnit} setIndexExtendUnit={setIndexExtendUnit} indexTargetDateText={indexTargetDateText} indexEarliestDate={indexEarliestDate} indexBatchInput={indexBatchInput} setIndexBatchInput={setIndexBatchInput} indexDailyBatchSize={indexDailyBatchSize} hasDailyBatchCap={hasDailyBatchCap} blocked={Boolean(activeJobId)} sync={syncIndexDaily} updateBatchSize={updateIndexBatchSize} /></SettingsModal>}
        {isAdmin && openSettings === 'minute' && <SettingsModal title="分钟 K · 同步设置" onClose={() => setOpenSettings(null)}><MinuteSyncConfig caps={caps.data} isRunning={Boolean(activeJobId)} onStart={() => setOpenSettings(null)} /></SettingsModal>}
      </AnimatePresence>

      <AnimatePresence>
        {isAdmin && showClearConfirm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center">
            <motion.div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => !clearData.isPending && setShowClearConfirm(false)} />
            <motion.div initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.97 }} className="relative w-[90vw] max-w-[420px] rounded-card border border-border bg-base p-6 shadow-2xl">
              <div className="flex items-start gap-3"><AlertTriangle aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-danger" /><div><h3 className="text-sm font-semibold text-foreground">确认清除本地数据？</h3><p className="mt-2 text-xs leading-relaxed text-secondary">此操作将永久删除个股维表、日 K、除权因子、Enriched、分钟 K、财务、指数和 ETF 数据；扩展数据不受影响。</p></div></div>
              <div className="mt-5 flex justify-end gap-2"><button type="button" onClick={() => setShowClearConfirm(false)} disabled={clearData.isPending} className="rounded-btn bg-elevated px-3 py-1.5 text-sm text-secondary">取消</button><button type="button" onClick={() => clearData.mutate()} disabled={clearData.isPending} className="rounded-btn bg-danger px-3 py-1.5 text-sm font-medium text-base disabled:opacity-50">{clearData.isPending ? '清除中…' : '清除数据'}</button></div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  )
}

function ScheduleLine({
  label,
  schedule,
  lastRun,
  nextRun,
  open,
  onToggle,
}: {
  label: string
  schedule: { hour: number; minute: number }
  lastRun?: string | null
  nextRun?: string | null
  open: boolean
  onToggle: () => void
}) {
  return (
    <div className="flex items-center justify-between gap-3 text-[11px]">
      <div className="flex items-center gap-1"><span className="text-muted">{label}</span><span className="font-mono text-secondary">{String(schedule.hour).padStart(2, '0')}:{String(schedule.minute).padStart(2, '0')}</span><button type="button" onClick={onToggle} aria-label={`编辑${label}调度`} className={`rounded p-0.5 hover:bg-elevated ${open ? 'text-accent' : 'text-secondary'}`}><Clock aria-hidden="true" className="h-3 w-3" /></button></div>
      <div className="flex items-center gap-2 font-mono text-secondary">{lastRun && <span className={isToday(lastRun) ? 'text-bear' : 'text-muted'}>✓ {formatScheduleDatePart(lastRun)} {formatScheduleTimePart(lastRun)}</span>}{nextRun && <span>→ {formatScheduleDatePart(nextRun)} {formatScheduleTimePart(nextRun)}</span>}</div>
    </div>
  )
}

function IndexSettings({
  indexExtendValue,
  setIndexExtendValue,
  indexExtendUnit,
  setIndexExtendUnit,
  indexTargetDateText,
  indexEarliestDate,
  indexBatchInput,
  setIndexBatchInput,
  indexDailyBatchSize,
  hasDailyBatchCap,
  blocked,
  sync,
  updateBatchSize,
}: {
  indexExtendValue: number
  setIndexExtendValue: (value: number | ((current: number) => number)) => void
  indexExtendUnit: 'month' | 'year'
  setIndexExtendUnit: (value: 'month' | 'year') => void
  indexTargetDateText: string
  indexEarliestDate: string | null
  indexBatchInput: string
  setIndexBatchInput: (value: string) => void
  indexDailyBatchSize: number
  hasDailyBatchCap: boolean
  blocked: boolean
  sync: { isPending: boolean; mutate: () => void }
  updateBatchSize: { isPending: boolean; mutate: (value: number) => void }
}) {
  const disabled = !hasDailyBatchCap || blocked || sync.isPending
  return (
    <div className="space-y-4 rounded-card border border-border bg-base/30 p-4">
      <div><div className="text-sm font-medium text-foreground">指数日 K</div><div className="mt-1 text-[11px] text-muted">先刷新 CN_Index 维表，再向前扩展指数历史；指数不需要复权。</div></div>
      <div className="flex flex-wrap items-center gap-2"><button type="button" onClick={() => setIndexExtendValue((value) => Math.max(1, value - 1))} disabled={disabled} className="rounded-btn border border-border bg-elevated px-2 py-1 text-xs">−</button><span className="font-mono text-xs">{indexExtendValue}</span><button type="button" onClick={() => setIndexExtendValue((value) => Math.min(indexExtendUnit === 'year' ? 10 : 36, value + 1))} disabled={disabled} className="rounded-btn border border-border bg-elevated px-2 py-1 text-xs">+</button>{(['month', 'year'] as const).map((unit) => <button type="button" key={unit} onClick={() => { setIndexExtendUnit(unit); if (unit === 'year' && indexExtendValue > 10) setIndexExtendValue(1); if (unit === 'month' && indexExtendValue > 36) setIndexExtendValue(6) }} disabled={disabled} className={`rounded-btn border border-border px-2 py-1 text-xs ${indexExtendUnit === unit ? 'bg-accent/15 text-accent' : 'bg-elevated text-secondary'}`}>{unit === 'month' ? '月' : '年'}</button>)}</div>
      <div className="text-[10px] text-muted">预计扩展至 <span className="font-mono text-secondary">{indexTargetDateText}</span>{indexEarliestDate && <>（当前最早：<span className="font-mono text-secondary">{indexEarliestDate}</span>）</>}</div>
      <div className="rounded-btn border border-border p-3"><div className="flex items-center justify-between gap-3"><div><div className="text-xs font-medium">批次大小</div><div className="text-[10px] text-muted">当前生效：{indexDailyBatchSize}</div></div><div className="flex gap-2"><input aria-label="指数批次大小" type="number" min={1} max={10000} value={indexBatchInput} onChange={(event) => setIndexBatchInput(event.target.value)} disabled={updateBatchSize.isPending || blocked} className="w-20 rounded-btn border border-border bg-elevated px-2 py-1 text-xs" /><button type="button" onClick={() => { const size = Math.max(1, Math.min(10000, Number(indexBatchInput) || 100)); setIndexBatchInput(String(size)); updateBatchSize.mutate(size) }} disabled={updateBatchSize.isPending || blocked} className="rounded-btn border border-border bg-elevated px-2 py-1 text-xs">{updateBatchSize.isPending ? '保存中…' : '保存'}</button></div></div></div>
      <button type="button" onClick={() => sync.mutate()} disabled={disabled} className="w-full rounded-btn bg-accent px-3 py-1.5 text-xs font-medium text-base disabled:opacity-40">{sync.isPending ? '获取中…' : '获取数据'}</button>
      {!hasDailyBatchCap && <p className="text-[10px] text-warning">当前 Provider 不支持批量指数日 K。</p>}
    </div>
  )
}
