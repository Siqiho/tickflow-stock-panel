import { Check, X } from 'lucide-react'
import type { DatasetAvailability } from '@/lib/api'

export type AvailabilityKind = Exclude<keyof DatasetAvailability, 'reason_code'>

const LABELS: Record<AvailabilityKind, string> = {
  provider_supported: '数据源支持',
  entitled: '当前有权限',
  local_materialized: '本地已落库',
  serving_ready: '当前可服务',
}

export function AvailabilityBadge({ kind, value }: { kind: AvailabilityKind; value: boolean }) {
  const label = LABELS[kind]
  const valueLabel = value ? '是' : '否'
  const Icon = value ? Check : X

  return (
    <span
      aria-label={`${label}：${valueLabel}`}
      className={`inline-flex min-w-0 items-center gap-1 rounded-btn border px-2 py-1 text-[10px] font-medium ${
        value
          ? 'border-accent/30 bg-accent/[0.06] text-foreground'
          : 'border-border bg-elevated/50 text-secondary'
      }`}
    >
      <Icon aria-hidden="true" className="h-3 w-3 shrink-0" />
      <span className="truncate">{label}</span>
      <span className="font-mono tabular-nums">{valueLabel}</span>
    </span>
  )
}
