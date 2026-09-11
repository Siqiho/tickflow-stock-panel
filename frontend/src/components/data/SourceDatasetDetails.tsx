import { GitBranch } from 'lucide-react'
import type { CatalogResponse, DatasetCatalogEntry, SourceProvenanceResponse } from '@/lib/api'
import { type CatalogReadState } from '@/lib/dataSources'
import { catalogDisplayTitle } from './DatasetCatalogCard'
import {
  type UnifiedSource,
  coverageTimeLabel,
  datasetsForSource,
  fieldUnitLabel,
  isLocallyPresent,
  producerNamesFor,
} from '@/lib/dataSourceCatalog'

function httpProviderText(source: UnifiedSource, entry?: DatasetCatalogEntry): string {
  const value = entry?.provider ?? source.httpProvider
  return value || '未登记'
}

export function SourceDatasetDetails({
  source,
  catalog,
  catalogState = 'ready',
  provenance,
  onOpenDataset,
  onTraceSource,
  children,
}: {
  source: UnifiedSource
  catalog?: CatalogResponse
  catalogState?: CatalogReadState
  provenance?: SourceProvenanceResponse
  onOpenDataset?: (entry: DatasetCatalogEntry) => void
  onTraceSource?: (subjectId: string) => void
  children?: React.ReactNode
}) {
  const datasets = datasetsForSource(source, catalog)
  const producerSet = [...new Set(datasets.flatMap((entry) => producerNamesFor(entry.descriptor.dataset_id, provenance)))]
  const producers = producerSet.length > 0 ? producerSet : ['未登记']

  return (
    <section aria-labelledby="source-dataset-details-heading" className="rounded-card border border-border bg-surface p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 id="source-dataset-details-heading" className="text-sm font-medium text-foreground">
            {source.displayName} · 实际数据集
          </h3>
          <p className="mt-1 text-[11px] text-muted">
            HTTP 提供方与真实生产者分开记录；缺字段或日期写未登记/未知，不用 0 代替。
          </p>
        </div>
        {source.kind === 'external' && (
          <span className="rounded bg-warning/15 px-1.5 py-0.5 text-[10px] font-medium text-warning">外部只读</span>
        )}
        {source.kind === 'unregistered' && (
          <span className="rounded bg-elevated px-1.5 py-0.5 text-[10px] font-medium text-secondary">未登记</span>
        )}
      </div>

      <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
        <div>
          <dt className="text-muted">HTTP 提供方</dt>
          <dd className="mt-0.5 font-mono text-foreground">{source.httpProvider ?? '未登记'}</dd>
        </div>
        <div>
          <dt className="text-muted">真实生产者</dt>
          <dd className="mt-0.5 text-foreground">{producers.join('、')}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-muted">支持能力</dt>
          <dd className="mt-0.5 text-foreground">
            {source.capabilityIds.length > 0 ? source.capabilityIds.join('、') : (source.extraLabels.join('、') || '未登记')}
          </dd>
        </div>
      </dl>

      {children}

      {datasets.length === 0 ? (
        <p className="mt-3 text-xs text-muted">
          {catalogState === 'loading'
            ? '目录读取中'
            : catalogState === 'error'
              ? '目录读取失败，暂无法判断'
              : source.kind === 'external'
                ? '原包不计入托管目录；目前仅两融可按标的查询。'
                : '没有可关联的本地数据集。'}
        </p>
      ) : (
        <ul className="mt-3 divide-y divide-border rounded-btn border border-border">
          {datasets.map((entry) => {
            const fields = entry.descriptor.fields
            return (
              <li key={entry.descriptor.dataset_id} className="space-y-2 px-3 py-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-xs font-medium text-foreground">{catalogDisplayTitle(entry)}</p>
                    <p className="font-mono text-[10px] text-muted">{entry.descriptor.dataset_id}</p>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {onOpenDataset && (
                      <button
                        type="button"
                        onClick={() => onOpenDataset(entry)}
                        className="rounded-btn border border-border bg-elevated px-2 py-1 text-[10px] text-secondary hover:text-foreground"
                      >
                        查看字段详情
                      </button>
                    )}
                    {onTraceSource && (
                      <button
                        type="button"
                        onClick={() => onTraceSource(entry.descriptor.dataset_id)}
                        className="inline-flex items-center gap-1 rounded-btn px-2 py-1 text-[10px] font-medium text-accent hover:bg-accent/10"
                      >
                        <GitBranch aria-hidden="true" className="h-3 w-3" />
                        来源追踪
                      </button>
                    )}
                  </div>
                </div>
                <p className="text-[11px] text-secondary">
                  覆盖 {coverageTimeLabel(entry)} · {isLocallyPresent(entry) ? '本地已有' : '尚未落库'}
                  {' · '}HTTP {httpProviderText(source, entry)}
                  {' · '}生产者 {producerNamesFor(entry.descriptor.dataset_id, provenance).join('、')}
                </p>
                {fields.length === 0 ? (
                  <p className="text-[11px] text-muted">字段未登记</p>
                ) : (
                  <p className="text-[11px] text-secondary">
                    字段 {fields.slice(0, 4).map((field) => `${field.name}（${fieldUnitLabel(field.unit)}）`).join('、')}
                    {fields.length > 4 ? ` 等 ${fields.length} 项` : ''}
                  </p>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
