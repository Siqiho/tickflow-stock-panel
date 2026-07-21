import { useCallback, useEffect, useRef, useState } from 'react'
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
import { Link } from 'react-router-dom'
import { EndpointTestDialog } from '@/components/EndpointTestDialog'
import { PageHeader } from '@/components/PageHeader'
import { ActiveJobCard } from '@/components/data/ActiveJobCard'
import { DataCatalogSection } from '@/components/data/DataCatalogSection'
import { DatasetDetailDrawer } from '@/components/data/DatasetDetailDrawer'
import { DatasetRunHistory } from '@/components/data/DatasetRunHistory'
import { EnrichedRebuildPanel } from '@/components/data/EnrichedRebuildPanel'
import { ExtendHistoryPanel } from '@/components/data/ExtendHistoryPanel'
import { MinuteSyncConfig } from '@/components/data/MinuteSyncConfig'
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
import { QK } from '@/lib/queryKeys'
import { useToggleRealtimeQuotes, useUpdateQuoteInterval } from '@/lib/useSharedMutations'
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

function catalogVisibilityGroup(datasetId: string): CardKey | null {
  if (CATALOG_GROUP_BY_DATASET[datasetId]) return CATALOG_GROUP_BY_DATASET[datasetId]
  if (datasetId.startsWith('index_')) return 'index'
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

export function Data() {
  const queryClient = useQueryClient()
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
  const prefs = usePreferences()
  const status = useDataStatus({ refetchInterval: activeJobId ? 2_000 : 30_000 })
  const catalog = useDataCatalog({ refetchInterval: activeJobId ? 2_000 : 30_000 })
  const history = useQuery({
    queryKey: QK.pipelineJobs,
    queryFn: () => api.pipelineJobs(15),
    refetchInterval: activeJobId ? false : 60_000,
  })
  const allRuns = useQuery({
    queryKey: QK.dataCatalogRuns(),
    queryFn: () => api.dataCatalogRuns(),
  })
  const job = useQuery({
    queryKey: QK.pipelineJob(activeJobId ?? ''),
    queryFn: () => api.pipelineJob(activeJobId!),
    enabled: Boolean(activeJobId),
    refetchInterval: (query) => {
      const current = query.state.data
      return current && ['succeeded', 'degraded', 'failed'].includes(current.status) ? false : 1_000
    },
  })
  const extConfigs = useQuery({ queryKey: QK.extData, queryFn: api.extDataList })

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
    enabled: Boolean(selectedDatasetId),
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
      const affectedCatalogKeys = ['index_instruments', 'etf_instruments', 'index_daily', 'index_enriched'].flatMap(
        (datasetId) => [
          QK.dataCatalogDataset(datasetId),
          QK.dataCatalogSchema(datasetId),
          QK.dataCatalogRuns(datasetId),
        ],
      )
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: QK.dataStatus, exact: true }),
        queryClient.invalidateQueries({ queryKey: QK.dataCatalog, exact: true }),
        queryClient.invalidateQueries({ queryKey: QK.dataCatalogRuns(), exact: true }),
        ...affectedCatalogKeys.map((queryKey) => queryClient.invalidateQueries({ queryKey, exact: true })),
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
    void queryClient.invalidateQueries({ queryKey: QK.pipelineJobs, exact: true })
    const timer = window.setTimeout(() => setActiveJobId(null), 5_000)
    return () => window.clearTimeout(timer)
  }, [queryClient, terminalJobStatus])

  useEffect(() => {
    if (job.isError && /404/.test(String((job.error as Error)?.message ?? ''))) setActiveJobId(null)
  }, [job.error, job.isError])
  useEffect(() => {
    if (!activeJobId && history.data?.active_id) setActiveJobId(history.data.active_id)
  }, [activeJobId, history.data?.active_id])

  const handleJobClick = useCallback((id: string) => {
    setActiveJobId(id)
    requestAnimationFrame(() => topRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }, [])

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

  const detailWarnings = [
    warningMessage('详情暂不可用，保留目录快照', selectedDetail.error),
    warningMessage('Schema 暂不可用，使用目录字段', selectedSchema.error),
    warningMessage('数据集运行记录暂不可用', selectedRuns.error),
  ].filter((message): message is string => Boolean(message))

  return (
    <>
      <div ref={topRef} />
      <PageHeader title="数据" subtitle="本地数据画像 · 同步状态 · 历史记录" />

      <div className="max-w-6xl space-y-8 px-8 py-6">
        <section aria-labelledby="data-system-status-heading" className="space-y-4">
          <div>
            <h2 id="data-system-status-heading" className="flex items-center gap-2 text-base font-semibold text-foreground">
              <Database aria-hidden="true" className="h-4 w-4 text-secondary" />
              数据系统状态
            </h2>
            <p className="mt-1 text-xs text-muted">本地 catalog 报告的存储事实与当前运行状态</p>
          </div>
          {isNoKey && (
            <div className="flex items-center gap-2 rounded-card border border-border bg-elevated/40 px-3 py-2 text-xs">
              <Info aria-hidden="true" className="h-4 w-4 shrink-0 text-muted" />
              <span className="text-secondary">当前使用免费历史数据模式；实时行情等扩展能力可在 <Link to="/settings?tab=account" className="font-medium text-accent hover:underline">配置</Link> 中启用。</span>
            </div>
          )}
          {job.data && <ActiveJobCard job={job.data} />}
          {catalog.data ? (
            <StorageBreakdownCard
              storage={catalog.data.storage}
              refreshedAt={catalog.data.refreshed_at}
              isStale={catalog.isCatalogStale}
              headingLevel={3}
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
        </section>

        <section aria-labelledby="data-catalog-region-heading" className="space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 id="data-catalog-region-heading" className="text-base font-semibold text-foreground">数据集目录</h2>
              <p className="mt-1 text-xs text-muted">只读查看本地数据、覆盖、质量、Schema 与血缘</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => rescanCatalog.mutate()}
                disabled={rescanCatalog.isPending}
                className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-elevated px-3 py-1.5 text-xs text-secondary hover:text-foreground disabled:opacity-40"
              >
                {rescanCatalog.isPending ? <Loader2 aria-hidden="true" className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw aria-hidden="true" className="h-3.5 w-3.5" />}
                {rescanCatalog.isPending ? '扫描中…' : '重新扫描本地目录'}
              </button>
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
          />
        </section>

        <section aria-labelledby="data-maintenance-heading" className="space-y-4">
          <div>
            <h2 id="data-maintenance-heading" className="flex items-center gap-2 text-base font-semibold text-foreground">
              <Wrench aria-hidden="true" className="h-4 w-4 text-secondary" />
              同步和维护操作
            </h2>
            <p className="mt-1 text-xs text-muted">同步、配置和清理操作会明确触发写入；目录浏览不会访问外部数据源</p>
          </div>
          <div className="flex flex-wrap gap-2 rounded-card border border-border bg-surface p-4">
            <button type="button" onClick={() => startSync.mutate()} disabled={startSync.isPending || isRunning} className="inline-flex items-center gap-1.5 rounded-btn bg-accent px-3 py-1.5 text-xs font-medium text-base disabled:opacity-40">
              {startSync.isPending || isRunning ? <Loader2 aria-hidden="true" className="h-3.5 w-3.5 animate-spin" /> : <Play aria-hidden="true" className="h-3.5 w-3.5" />}
              {startSync.isPending ? '启动中…' : isRunning ? '同步中…' : '立即同步'}
            </button>
            <button type="button" onClick={() => setOpenSettings('pipeline-scope')} className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-elevated px-3 py-1.5 text-xs text-secondary hover:text-foreground"><CheckSquare aria-hidden="true" className="h-3.5 w-3.5" />数据范围</button>
            <button type="button" onClick={() => setShowCreateExt(true)} className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-elevated px-3 py-1.5 text-xs text-secondary hover:text-foreground"><Plus aria-hidden="true" className="h-3.5 w-3.5" />新建扩展数据</button>
            <button type="button" onClick={() => setShowEndpointTest(true)} className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-elevated px-3 py-1.5 text-xs text-secondary hover:text-foreground"><Wifi aria-hidden="true" className="h-3.5 w-3.5" />测试端点</button>
            <button type="button" onClick={() => setOpenSettings('page-settings')} className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-elevated px-3 py-1.5 text-xs text-secondary hover:text-foreground"><SlidersHorizontal aria-hidden="true" className="h-3.5 w-3.5" />目录显示设置</button>
            <button type="button" onClick={() => setOpenSettings('daily')} disabled={!hasData} className="rounded-btn border border-border bg-elevated px-3 py-1.5 text-xs text-secondary hover:text-foreground disabled:opacity-40">日 K 历史扩展</button>
            <button type="button" onClick={() => setOpenSettings('enriched')} disabled={!hasData} className="rounded-btn border border-border bg-elevated px-3 py-1.5 text-xs text-secondary hover:text-foreground disabled:opacity-40">重建 Enriched</button>
            <button type="button" onClick={() => setOpenSettings('index')} disabled={!hasData} className="rounded-btn border border-border bg-elevated px-3 py-1.5 text-xs text-secondary hover:text-foreground disabled:opacity-40">指数手动获取</button>
            <button type="button" onClick={() => setOpenSettings('minute')} disabled={!hasData} className="rounded-btn border border-border bg-elevated px-3 py-1.5 text-xs text-secondary hover:text-foreground disabled:opacity-40">分钟 K 设置</button>
            <button type="button" onClick={() => setShowClearConfirm(true)} disabled={isRunning} className="inline-flex items-center gap-1.5 rounded-btn border border-danger/30 px-3 py-1.5 text-xs text-danger hover:bg-danger/5 disabled:opacity-40"><Trash2 aria-hidden="true" className="h-3.5 w-3.5" />清除数据</button>
          </div>
          {startSync.isError && <div role="alert" className="rounded-btn border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">启动失败：{(startSync.error as Error).message}</div>}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <QuoteConfigCard
              enabled={prefs.data?.realtime_quotes_enabled ?? false}
              running={quoteStatus.data?.running ?? false}
              isTrading={quoteStatus.data?.is_trading_hours ?? false}
              lastFetchMs={quoteStatus.data?.last_fetch_ms ?? null}
              intervalS={quoteInterval.data?.interval ?? quoteStatus.data?.interval_s ?? 10}
              intervalMin={quoteInterval.data?.min_interval ?? 5}
              intervalMax={quoteInterval.data?.max_interval ?? 60}
              loading={quoteStatus.isLoading}
              onToggle={(value) => toggleQuote.mutate(value)}
              toggling={toggleQuote.isPending}
              showIntervalEdit={showIntervalEdit}
              onShowIntervalEdit={handleToggleIntervalEdit}
              onIntervalChange={(value) => updateInterval.mutate(value)}
            />
            <div className="rounded-card border border-border bg-surface p-4">
              <div className="mb-3 flex items-center gap-2"><Calendar aria-hidden="true" className="h-4 w-4 text-secondary" /><h3 className="text-sm font-medium text-foreground">自动调度</h3></div>
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
          </div>
          {(extConfigs.data?.items ?? []).length > 0 && (
            <div>
              <h3 className="mb-3 text-xs font-medium uppercase tracking-widest text-secondary">扩展数据配置</h3>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {(extConfigs.data?.items ?? []).map((config) => (
                  <ExtDataStatCard key={config.id} config={config} onDelete={() => deleteExt.mutate(config.id)} deleting={deleteExt.isPending} onEdit={() => setEditingExt(config)} />
                ))}
              </div>
            </div>
          )}
        </section>

        <section aria-labelledby="data-history-heading" className="space-y-4">
          <div>
            <h2 id="data-history-heading" className="flex items-center gap-2 text-base font-semibold text-foreground"><History aria-hidden="true" className="h-4 w-4 text-secondary" />同步历史与质量问题</h2>
            <p className="mt-1 text-xs text-muted">本地控制库运行记录与兼容的管道任务历史</p>
          </div>
          {allRuns.isError && <div role="alert" aria-label="运行历史错误" className="rounded-btn border border-warning/30 bg-warning/5 px-3 py-2 text-xs text-warning">本地运行历史暂不可用：{(allRuns.error as Error).message}</div>}
          <div className="rounded-card border border-border bg-surface p-4"><DatasetRunHistory runs={allRuns.data?.runs ?? []} /></div>
          <div>
            <h3 className="flex items-center gap-2 text-xs font-medium uppercase tracking-widest text-secondary"><Clock aria-hidden="true" className="h-4 w-4" />管道任务历史</h3>
            <div className="mt-3 overflow-hidden rounded-card border border-border">
              {history.isLoading ? <div className="px-5 py-6"><Skeleton w="w-28" /></div> : history.data && history.data.jobs.length > 0 ? (
                <div className="divide-y divide-border">{history.data.jobs.map((item) => <HistoryRow key={item.id} job={item} onClick={() => handleJobClick(item.id)} />)}</div>
              ) : <div className="px-5 py-8 text-center text-sm text-muted">暂无同步记录 — 使用上方“立即同步”开始。</div>}
            </div>
          </div>
        </section>
      </div>

      <DatasetDetailDrawer
        entry={selectedDetail.data ?? selectedDataset}
        schema={selectedSchema.data}
        runs={selectedRuns.data?.runs ?? []}
        warnings={detailWarnings}
        onClose={() => setSelectedDataset(null)}
      />
      {showEndpointTest && <EndpointTestDialog hasKey={settings.data?.mode === 'api_key'} tierLabel={settings.data?.tier_label ?? ''} currentEndpoint={settings.data?.current_endpoint ?? ''} onClose={() => setShowEndpointTest(false)} />}
      <AnimatePresence>
        {showCreateExt && <CreateExtDialog onClose={() => setShowCreateExt(false)} />}
        {editingExt && <EditExtDialog config={editingExt} onClose={() => setEditingExt(null)} />}
      </AnimatePresence>
      <AnimatePresence>
        {openSettings === 'daily' && <SettingsModal title="日 K · 向前扩展历史" onClose={() => setOpenSettings(null)}><ExtendHistoryPanel caps={caps.data} isRunning={Boolean(activeJobId)} earliestDate={dataStatus?.daily?.earliest_date ?? null} onStart={() => setOpenSettings(null)} /></SettingsModal>}
        {openSettings === 'enriched' && <SettingsModal title="Enriched · 计算设置" onClose={() => setOpenSettings(null)}><EnrichedRebuildPanel isRunning={Boolean(activeJobId)} onStart={() => setOpenSettings(null)} /></SettingsModal>}
        {openSettings === 'pipeline-scope' && <SettingsModal title="盘后管道 · 拉取内容" onClose={() => setOpenSettings(null)}><PipelineScopeConfig /></SettingsModal>}
        {openSettings === 'page-settings' && <SettingsModal title="页面设置 · 目录显隐" onClose={() => setOpenSettings(null)}><PageSettingsModal caps={caps.data?.capabilities} /></SettingsModal>}
        {openSettings === 'index' && <SettingsModal title="指数 · 手动获取" onClose={() => setOpenSettings(null)}><IndexSettings indexExtendValue={indexExtendValue} setIndexExtendValue={setIndexExtendValue} indexExtendUnit={indexExtendUnit} setIndexExtendUnit={setIndexExtendUnit} indexTargetDateText={indexTargetDateText} indexEarliestDate={indexEarliestDate} indexBatchInput={indexBatchInput} setIndexBatchInput={setIndexBatchInput} indexDailyBatchSize={indexDailyBatchSize} hasDailyBatchCap={hasDailyBatchCap} blocked={Boolean(activeJobId)} sync={syncIndexDaily} updateBatchSize={updateIndexBatchSize} /></SettingsModal>}
        {openSettings === 'minute' && <SettingsModal title="分钟 K · 同步设置" onClose={() => setOpenSettings(null)}><MinuteSyncConfig caps={caps.data} isRunning={Boolean(activeJobId)} onStart={() => setOpenSettings(null)} /></SettingsModal>}
      </AnimatePresence>

      <AnimatePresence>
        {showClearConfirm && (
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
