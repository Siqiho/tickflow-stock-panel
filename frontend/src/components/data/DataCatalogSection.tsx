import { AlertTriangle, Database } from 'lucide-react'
import type { CatalogResponse, DatasetCatalogEntry } from '@/lib/api'
import { DatasetCatalogCard } from './DatasetCatalogCard'

type CatalogGroup = {
  key: string
  title: string
  entries: DatasetCatalogEntry[]
}

function groupCatalog(entries: DatasetCatalogEntry[]): CatalogGroup[] {
  const finance = entries.filter((entry) => entry.descriptor.dataset_id.startsWith('financial_'))
  const etf = entries.filter((entry) => entry.descriptor.dataset_id.startsWith('etf_'))
  const core = entries.filter((entry) => {
    const id = entry.descriptor.dataset_id
    return id.startsWith('stock_') || id.startsWith('index_') || ['quote_snapshot', 'sealed_l1', 'depth5'].includes(id)
  })
  const grouped = new Set([...finance, ...etf, ...core])
  const other = entries.filter((entry) => !grouped.has(entry))

  return [
    { key: 'core', title: '核心行情', entries: core },
    { key: 'etf', title: 'ETF 数据', entries: etf },
    { key: 'finance', title: '财务数据', entries: finance },
    { key: 'other', title: '其他数据', entries: other },
  ].filter((group) => group.entries.length > 0)
}

export function DataCatalogSection({
  catalog,
  isStale = false,
  error = null,
  onSelectDataset,
  headingLevel = 2,
}: {
  catalog?: CatalogResponse
  isStale?: boolean
  error?: Error | null
  onSelectDataset?: (entry: DatasetCatalogEntry) => void
  headingLevel?: 2 | 3
}) {
  if (!catalog) {
    if (error) {
      return (
        <div role="alert" aria-label="数据目录错误" className="rounded-card border border-danger/30 bg-danger/5 p-4 text-sm text-danger">
          数据目录暂不可用：{error.message}
        </div>
      )
    }
    return <div className="rounded-card border border-border bg-surface p-4 text-sm text-muted">数据目录加载中</div>
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
            <section key={group.key} aria-label={group.title}>
              <div className="mb-3 flex items-center gap-3">
                <h3 className="shrink-0 text-xs font-medium uppercase tracking-widest text-secondary">{group.title}</h3>
                <div className="h-px flex-1 bg-border" />
                <span className="font-mono text-[10px] text-muted">{group.entries.length}</span>
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                {group.entries.map((entry) => (
                  <DatasetCatalogCard key={entry.descriptor.dataset_id} entry={entry} onOpen={onSelectDataset} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </Container>
  )
}
