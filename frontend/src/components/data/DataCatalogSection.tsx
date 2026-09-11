import { useEffect, useState } from 'react'
import { AlertTriangle, ChevronDown, ChevronRight, Database } from 'lucide-react'
import type { CatalogResponse, DataControlSummary, DatasetCatalogEntry } from '@/lib/api'
import { DatasetCatalogCard } from './DatasetCatalogCard'
import { datasetControlFacts } from './ControlPlaneSummary'
import { ExternalReadOnlyData } from './ExternalReadOnlyData'

type CatalogGroup = {
  key: string
  title: string
  entries: DatasetCatalogEntry[]
}

// 参考/派生数据集显式清单; 必须优先于 stock_/index_ 前缀规则,
// 否则 index_membership_history 会被误分进核心行情。
const REFERENCE_DATASET_IDS = new Set([
  'trading_calendar',
  'valuation_daily',
  'limit_up_events',
  'index_membership_history',
  'corporate_actions',
  'hithink_limit_pool',
  'hithink_dragon_tiger',
  'hithink_auction_snapshot',
  'hithink_valuation_snapshot',
])

function isExtCatalogDataset(datasetId: string): boolean {
  return datasetId === 'ext_data' || datasetId.startsWith('ext_')
}

function groupCatalog(entries: DatasetCatalogEntry[]): CatalogGroup[] {
  const finance = entries.filter((entry) => entry.descriptor.dataset_id.startsWith('financial_'))
  const f10 = entries.filter((entry) => {
    const id = entry.descriptor.dataset_id
    return id === 'stock_margin_trading' || id.startsWith('stock_f10_')
  })
  const etf = entries.filter((entry) => entry.descriptor.dataset_id.startsWith('etf_'))
  const reference = entries.filter((entry) => REFERENCE_DATASET_IDS.has(entry.descriptor.dataset_id))
  const ext = entries.filter((entry) => isExtCatalogDataset(entry.descriptor.dataset_id))
  const core = entries.filter((entry) => {
    const id = entry.descriptor.dataset_id
    return !f10.includes(entry)
      && !REFERENCE_DATASET_IDS.has(id)
      && (id.startsWith('stock_') || id.startsWith('index_') || ['quote_snapshot', 'sealed_l1', 'depth5'].includes(id))
  })
  const grouped = new Set([...finance, ...f10, ...etf, ...core, ...reference, ...ext])
  const other = entries.filter((entry) => !grouped.has(entry))

  return [
    { key: 'core', title: '核心行情', entries: core },
    { key: 'etf', title: 'ETF 数据', entries: etf },
    { key: 'finance', title: '财务数据', entries: finance },
    { key: 'f10', title: '股票 F10', entries: f10 },
    { key: 'reference', title: '参考数据', entries: reference },
    { key: 'ext', title: '扩展数据', entries: ext },
    { key: 'other', title: '其他数据', entries: other },
  ].filter((group) => group.entries.length > 0)
}

function OfflineMarginCatalogEntry() {
  const [open, setOpen] = useState(false)
  return (
    <div className="mt-4 border-t border-border pt-3">
      <button
        type="button"
        aria-expanded={open}
        aria-controls="catalog-offline-margin-panel"
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-center gap-2 rounded-btn px-1 py-1.5 text-left text-xs text-secondary outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-accent"
      >
        {open
          ? <ChevronDown aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
          : <ChevronRight aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />}
        <span className="font-medium text-foreground">外部只读原包·两融查询</span>
        <span className="ml-auto text-[10px] text-muted">不计入托管目录</span>
      </button>
      {open ? (
        <div id="catalog-offline-margin-panel" className="pt-1">
          <ExternalReadOnlyData isAdmin compact idPrefix="catalog-offline-margin" />
        </div>
      ) : null}
    </div>
  )
}

export function DataCatalogSection({
  catalog,
  isStale = false,
  error = null,
  onSelectDataset,
  headingLevel = 2,
  controlSummary,
  onTraceSource,
  focusGroup = null,
  isAdmin = false,
}: {
  catalog?: CatalogResponse
  isStale?: boolean
  error?: Error | null
  onSelectDataset?: (entry: DatasetCatalogEntry) => void
  headingLevel?: 2 | 3
  controlSummary?: DataControlSummary
  onTraceSource?: (subjectId: string) => void
  focusGroup?: string | null
  isAdmin?: boolean
}) {
  useEffect(() => {
    if (!focusGroup || !catalog) return
    const node = document.getElementById(`catalog-group-${focusGroup}`)
    node?.scrollIntoView({ block: 'start' })
  }, [focusGroup, catalog])

  if (!catalog) {
    if (error) {
      return (
        <div>
          <div role="alert" aria-label="数据目录错误" className="rounded-card border border-danger/30 bg-danger/5 p-4 text-sm text-danger">
            数据目录暂不可用：{error.message}
          </div>
          {isAdmin ? <OfflineMarginCatalogEntry /> : null}
        </div>
      )
    }
    return (
      <div>
        <div className="rounded-card border border-border bg-surface p-4 text-sm text-muted">数据目录加载中</div>
        {isAdmin ? <OfflineMarginCatalogEntry /> : null}
      </div>
    )
  }

  const entries = catalog.datasets.filter((entry) => (
    entry.descriptor.dataset_id !== 'depth5' || entry.depth5_available === true
  ))
  const stale = isStale || catalog.stale || Boolean(error)
  const Heading = headingLevel === 3 ? 'h3' : 'h2'
  const Container = headingLevel === 3 ? 'div' : 'section'

  return (
    <Container aria-labelledby="data-catalog-heading">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-3">
        <div>
          <Heading id="data-catalog-heading" className="flex items-center gap-2 text-sm font-medium text-foreground">
            <Database aria-hidden="true" className="h-4 w-4 text-secondary" />
            数据目录
          </Heading>
          <p className="mt-1 text-[11px] text-muted">本地数据、可用性、覆盖与质量事实</p>
        </div>
        {stale && (
          <span className="inline-flex items-center gap-1.5 rounded-btn bg-warning/10 px-2 py-1 text-xs font-medium text-warning">
            <AlertTriangle aria-hidden="true" className="h-3.5 w-3.5" />
            状态可能过期
          </span>
        )}
      </div>

      {entries.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted">暂无数据目录</p>
      ) : (
        <div className="space-y-8 pt-5">
          {groupCatalog(entries).map((group) => (
            <section id={`catalog-group-${group.key}`} key={group.key} aria-label={group.title}>
              <div className="mb-3 flex items-center gap-3">
                <h3 className="shrink-0 text-xs font-medium uppercase tracking-widest text-secondary">{group.title}</h3>
                <div className="h-px flex-1 bg-border" />
                <span className="font-mono text-[10px] text-muted">{group.entries.length}</span>
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                {group.entries.map((entry) => (
                  <DatasetCatalogCard
                    key={entry.descriptor.dataset_id}
                    entry={entry}
                    onOpen={onSelectDataset}
                    control={datasetControlFacts(controlSummary, entry.descriptor.dataset_id)}
                    controlStale={controlSummary?.catalog_stale}
                    onTraceSource={onTraceSource}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
      {isAdmin ? <OfflineMarginCatalogEntry /> : null}
    </Container>
  )
}
