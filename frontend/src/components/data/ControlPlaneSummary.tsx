import { DatabaseZap, GitBranch } from 'lucide-react'
import type {
  CapabilityRoute,
  CatalogResponse,
  DataControlSummary,
  DataQueryAudit,
  DataSyncCheckpoint,
  DatasetCatalogEntry,
  DatasetControlPolicy,
} from '@/lib/api'
import {
  CAPABILITY_LOCAL_DATASETS,
  catalogLocalDataLabel,
  collectionHealthLabel,
  type CatalogReadState,
} from '@/lib/dataSources'
import { AdvancedDisclosure } from './AdvancedDisclosure'
import { formatCatalogBytes } from './StorageBreakdownCard'

export type ProviderSelection = {
  label: string
  provider?: string | null
  displayName?: string
  subjectId?: string
}

export type DatasetControlFacts = {
  policy?: DatasetControlPolicy
  checkpoint?: DataSyncCheckpoint
  audits: DataQueryAudit[]
}

const PHASE_LABELS: Record<string, string> = {
  planned: '规划中',
  'source-verified': '来源已核验',
  source_verified: '来源已核验',
  isolated: '隔离验证中',
  canary: '小范围试用中',
  accepted: '已验收',
  production: '正式使用',
}

function shortDate(value: string | null | undefined): string {
  return value ? value.slice(0, 10) : '尚未记录'
}

export function datasetControlFacts(
  summary: DataControlSummary | undefined,
  datasetId: string,
): DatasetControlFacts {
  return {
    policy: summary?.dataset_policies.find((item) => item.dataset_id === datasetId),
    checkpoint: summary?.sync_checkpoints.find((item) => item.dataset_id === datasetId),
    audits: summary?.query_audits.filter((item) => item.dataset_id === datasetId) ?? [],
  }
}

export function lifecycleText(policy: DatasetControlPolicy | undefined, stale = false): string {
  if (!policy) return '未使用控制库准入'
  const label = PHASE_LABELS[policy.phase] ?? '状态待核验'
  return stale && policy.phase === 'production' ? `${label}（待核验）` : label
}

export function materializationText(entry: DatasetCatalogEntry, stale = false): string {
  const availability = entry.descriptor.availability
  if (availability.serving_ready) return stale ? '可服务状态待刷新' : '已落库并可服务'
  if (availability.local_materialized) return '已落库，尚未正式可用'
  return '目录已登记，尚未落库'
}

export function consumerText(audits: DataQueryAudit[]): string {
  const tools = [...new Set(audits.map((item) => item.tool_name).filter((value): value is string => Boolean(value)))]
  if (tools.length === 0) return '近期无消费者审计'
  return `近期被 ${tools.length} 个调用方使用`
}

export function capabilityLocalFacts(
  cap: Pick<CapabilityRoute, 'id' | 'usable'>,
  catalog: CatalogResponse | undefined,
  catalogState: CatalogReadState,
): { readyLabel: string; localDataLabel: string } {
  return {
    readyLabel: cap.usable ? '配置已就绪' : '配置未就绪',
    localDataLabel: catalogLocalDataLabel(catalog, CAPABILITY_LOCAL_DATASETS[cap.id], catalogState),
  }
}

function SummaryRow({ label, value, warning = false }: { label: string; value: string; warning?: boolean }) {
  return (
    <div className="grid gap-1 py-2.5 sm:grid-cols-[9rem_minmax(0,1fr)] sm:items-center">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className={`text-xs font-medium ${warning ? 'text-warning' : 'text-foreground'}`}>{value}</dd>
    </div>
  )
}

export function DataOverviewControlPanel({
  summary,
  error,
  onTraceSource,
}: {
  summary?: DataControlSummary
  error?: Error | null
  onTraceSource?: (subjectId: string) => void
}) {
  const health = collectionHealthLabel(summary)
  const physicalCount = summary?.unregistered_physical.length ?? 0

  return (
    <section aria-labelledby="data-control-overview-heading" className="rounded-card border border-border bg-surface p-4">
      <div className="flex items-start gap-2">
        <DatabaseZap aria-hidden="true" className="mt-0.5 h-4 w-4 text-secondary" />
        <div>
          <h3 id="data-control-overview-heading" className="text-sm font-medium text-foreground">数据台要点</h3>
          <p className="mt-1 text-[11px] text-muted">先看能否使用；内部位置与审计按需展开</p>
        </div>
      </div>

      {error && <p role="alert" className="mt-3 rounded-btn bg-warning/5 px-3 py-2 text-xs text-warning">控制信息暂不可用：{error.message}</p>}
      <dl className="mt-3 divide-y divide-border border-y border-border">
        <SummaryRow
          label="采集健康"
          value={summary ? health.text : '正在读取'}
          warning={health.warning || health.unverified}
        />
        <SummaryRow
          label="目录新鲜度"
          value={summary?.catalog_stale ? `状态可能过期 · 上次更新 ${shortDate(summary.catalog_refreshed_at)}` : `已更新到 ${shortDate(summary?.catalog_refreshed_at)}`}
          warning={summary?.catalog_stale}
        />
        <SummaryRow
          label="未登记物理数据"
          value={physicalCount > 0 ? `${physicalCount} 个参考目录待登记` : '未发现待登记参考目录'}
          warning={physicalCount > 0}
        />
      </dl>

      {summary && (
        <AdvancedDisclosure className="mt-3">
          <div className="space-y-4 text-[11px]">
            <div>
              <p className="font-medium text-secondary">控制库采集记录明细</p>
              <div className="mt-2 divide-y divide-border rounded-btn border border-border">
                {summary.source_health.map((item) => (
                  <div key={`${item.provider}:${item.operation}`} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                    <span className="font-mono text-foreground">{item.operation}</span>
                    <span className="flex items-center gap-2">
                      <span className={item.consecutive_failures > 0 ? 'text-warning' : 'text-secondary'}>
                        {item.consecutive_failures > 0 ? `连续失败 ${item.consecutive_failures} 次` : `最近成功 ${shortDate(item.last_success_at)}`}
                      </span>
                      {item.operation.startsWith('sync:') && (
                        <button
                          type="button"
                          onClick={() => onTraceSource?.(item.operation.slice('sync:'.length))}
                          className="inline-flex items-center gap-1 rounded-btn px-1.5 py-1 text-[10px] font-medium text-accent hover:bg-accent/10"
                          aria-label={`追踪 ${item.operation.slice('sync:'.length)} 来源`}
                        >
                          <GitBranch aria-hidden="true" className="h-3 w-3" />来源
                        </button>
                      )}
                    </span>
                  </div>
                ))}
                {summary.source_health.length === 0 && <p className="px-3 py-2 text-muted">控制库尚未记录数据源健康</p>}
              </div>
            </div>
            {summary.unregistered_physical.length > 0 && (
              <div>
                <p className="font-medium text-secondary">待登记参考目录</p>
                <div className="mt-2 divide-y divide-border rounded-btn border border-border">
                  {summary.unregistered_physical.map((item) => (
                    <div key={item.key} className="grid gap-1 px-3 py-2 sm:grid-cols-[minmax(0,1fr)_auto]">
                      <span className="break-all font-mono text-foreground">{item.relative_path}</span>
                      <span className="text-muted">{item.files} 文件 · {formatCatalogBytes(item.bytes)}</span>
                    </div>
                  ))}
                </div>
                <p className="mt-1 text-[10px] text-muted">只检查 reference 范围；这里是物理旁路提醒，不代表已准入。</p>
              </div>
            )}
          </div>
        </AdvancedDisclosure>
      )}
    </section>
  )
}
