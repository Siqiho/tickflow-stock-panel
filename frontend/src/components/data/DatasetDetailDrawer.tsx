import { useEffect, useId, useRef } from 'react'
import { GitBranch, X } from 'lucide-react'
import type { CatalogSchemaResponse, DatasetCatalogEntry, FieldContract, SyncRun } from '@/lib/api'
import { AdvancedDisclosure } from './AdvancedDisclosure'
import {
  consumerText,
  lifecycleText,
  materializationText,
  type DatasetControlFacts,
} from './ControlPlaneSummary'
import { DatasetRunHistory } from './DatasetRunHistory'
import { catalogDisplayTitle } from './DatasetCatalogCard'
import { QualityLineagePanel } from './QualityLineagePanel'

function metadataValue(value: string | null): string {
  return value ?? '未声明'
}

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'area[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  'iframe',
  'object',
  'embed',
  '[contenteditable="true"]',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

function drawerFocusables(dialog: HTMLElement): HTMLElement[] {
  return Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter((element) => (
    element.tabIndex >= 0 && !element.closest('[hidden], [aria-hidden="true"]')
  ))
}

function FieldTable({ fields }: { fields: FieldContract[] }) {
  return (
    <div className="overflow-x-auto rounded-btn border border-border">
      <table className="min-w-[760px] w-full text-left text-[11px]">
        <thead className="bg-elevated/70 text-muted">
          <tr>
            {['字段', '类型', '语义', '单位', '缩放', '币种', '时区'].map((label) => (
              <th key={label} scope="col" className="px-3 py-2 font-medium">{label}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {fields.map((field) => (
            <tr key={field.name}>
              <th scope="row" className="px-3 py-2 font-mono font-medium text-foreground">{field.name}</th>
              <td className="px-3 py-2 font-mono text-secondary">{field.dtype}</td>
              <td className="px-3 py-2 text-secondary">{field.semantic}</td>
              <td className="px-3 py-2 font-mono text-secondary">{metadataValue(field.unit)}</td>
              <td className="px-3 py-2 font-mono text-secondary">{metadataValue(field.scale)}</td>
              <td className="px-3 py-2 font-mono text-secondary">{metadataValue(field.currency)}</td>
              <td className="px-3 py-2 font-mono text-secondary">{metadataValue(field.timezone)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function DatasetDetailDrawer({
  entry,
  schema,
  runs = [],
  warnings = [],
  control,
  controlStale = false,
  onClose,
  onTraceSource,
}: {
  entry: DatasetCatalogEntry | null
  schema?: CatalogSchemaResponse | null
  runs?: SyncRun[]
  warnings?: string[]
  control?: DatasetControlFacts
  controlStale?: boolean
  onClose: () => void
  onTraceSource?: (subjectId: string) => void
}) {
  const dialogRef = useRef<HTMLElement>(null)
  const drawerId = useId()
  const isOpen = entry !== null

  useEffect(() => {
    if (!isOpen) return undefined

    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const dialog = dialogRef.current
    const initialFocus = dialog ? drawerFocusables(dialog)[0] ?? dialog : null
    initialFocus?.focus()

    return () => {
      if (previouslyFocused?.isConnected) previouslyFocused.focus()
    }
  }, [isOpen])

  useEffect(() => {
    if (!isOpen) return undefined

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key !== 'Tab') return

      const dialog = dialogRef.current
      if (!dialog) return
      const focusables = drawerFocusables(dialog)
      if (focusables.length === 0) {
        event.preventDefault()
        dialog.focus()
        return
      }

      const first = focusables[0]
      const last = focusables[focusables.length - 1]
      const active = document.activeElement
      if (focusables.length === 1) {
        event.preventDefault()
        first.focus()
      } else if (event.shiftKey && (active === first || !dialog.contains(active))) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && (active === last || !dialog.contains(active))) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  if (!entry) return null

  const title = catalogDisplayTitle(entry)
  const headingId = `${drawerId}-dataset-heading`
  const fields = schema?.fields ?? entry.descriptor.fields

  return (
    <div className="fixed inset-0 z-50 bg-foreground/20" aria-hidden={false}>
      <section
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={headingId}
        tabIndex={-1}
        className="ml-auto flex h-full w-full max-w-3xl flex-col border-l border-border bg-surface shadow-xl"
      >
        <header className="flex items-start justify-between gap-4 border-b border-border px-4 py-4 sm:px-6">
          <div className="min-w-0">
            <h2 id={headingId} className="truncate text-base font-semibold text-foreground">{title} 详情</h2>
            <p className="mt-1 break-all font-mono text-[11px] text-muted">{entry.descriptor.dataset_id}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={`关闭“${title}”详情`}
            className="rounded-btn p-2 text-secondary outline-none transition-colors hover:bg-elevated hover:text-foreground focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
          >
            <X aria-hidden="true" className="h-4 w-4" />
          </button>
        </header>

        <div className="scrollbar-gutter-stable flex-1 space-y-7 overflow-y-auto px-4 py-5 sm:px-6">
          {warnings.length > 0 && (
            <div role="alert" className="space-y-1 rounded-card border border-warning/30 bg-warning/5 p-3 text-xs text-warning">
              {warnings.map((warning) => <p key={warning}>{warning}</p>)}
            </div>
          )}
          <section aria-labelledby={`${headingId}-current`}>
            <h3 id={`${headingId}-current`} className="text-xs font-medium uppercase tracking-widest text-secondary">当前状态</h3>
            <dl className="mt-3 divide-y divide-border rounded-btn border border-border px-3 text-xs">
              <div className="grid gap-1 py-2.5 sm:grid-cols-[8rem_minmax(0,1fr)]"><dt className="text-muted">准入阶段</dt><dd className="font-medium text-foreground">{lifecycleText(control?.policy, controlStale)}</dd></div>
              <div className="grid gap-1 py-2.5 sm:grid-cols-[8rem_minmax(0,1fr)]"><dt className="text-muted">正式数据状态</dt><dd className="font-medium text-foreground">{materializationText(entry, controlStale)}</dd></div>
              <div className="grid gap-1 py-2.5 sm:grid-cols-[8rem_minmax(0,1fr)]"><dt className="text-muted">同步进度</dt><dd className="font-medium text-foreground">{control?.checkpoint?.watermark ? `已同步到 ${control.checkpoint.watermark}` : '尚未记录'}</dd></div>
              <div className="grid gap-1 py-2.5 sm:grid-cols-[8rem_minmax(0,1fr)]"><dt className="text-muted">实际消费者</dt><dd className="font-medium text-foreground">{consumerText(control?.audits ?? [])}</dd></div>
            </dl>
            {onTraceSource && <button
              type="button"
              onClick={() => onTraceSource?.(entry.descriptor.dataset_id)}
              className="mt-3 inline-flex items-center gap-1.5 rounded-btn border border-accent/20 bg-accent/5 px-2.5 py-1.5 text-xs font-medium text-accent hover:bg-accent/10 focus-visible:ring-2 focus-visible:ring-accent"
            >
              <GitBranch aria-hidden="true" className="h-3.5 w-3.5" />追踪此数据集来源
            </button>}
          </section>

          <AdvancedDisclosure>
            <div className="space-y-7">
              {(control?.policy || control?.checkpoint) && (
                <section aria-labelledby={`${headingId}-control`}>
                  <h3 id={`${headingId}-control`} className="text-xs font-medium uppercase tracking-widest text-secondary">控制记录</h3>
                  <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-3 text-xs sm:grid-cols-2">
                    <div><dt className="text-muted">内部阶段</dt><dd className="mt-0.5 font-mono">{control.policy?.phase ?? '未登记'}</dd></div>
                    <div><dt className="text-muted">同步策略</dt><dd className="mt-0.5 font-mono">{control.policy?.sync_mode ?? '未登记'}</dd></div>
                    <div><dt className="text-muted">续传位置</dt><dd className="mt-0.5 break-all font-mono">{JSON.stringify(control.checkpoint?.cursor ?? {})}</dd></div>
                    <div><dt className="text-muted">run_id</dt><dd className="mt-0.5 break-all font-mono">{control.checkpoint?.last_success_run_id ?? '未记录'}</dd></div>
                  </dl>
                </section>
              )}
              {control && control.audits.length > 0 && (
                <section aria-labelledby={`${headingId}-consumers`}>
                  <h3 id={`${headingId}-consumers`} className="text-xs font-medium uppercase tracking-widest text-secondary">消费者审计</h3>
                  <div className="mt-3 divide-y divide-border rounded-btn border border-border text-xs">
                    {control.audits.map((audit) => (
                      <div key={audit.audit_id} className="grid gap-1 px-3 py-2 sm:grid-cols-[minmax(0,1fr)_auto]">
                        <span className="break-all font-mono text-foreground">{audit.tool_name ?? '调用方未登记'}</span>
                        <span className="text-muted">{audit.status === 'succeeded' ? '成功' : '失败'} · {audit.row_count.toLocaleString()} 行</span>
                      </div>
                    ))}
                  </div>
                </section>
              )}
              <section aria-labelledby={`${headingId}-contract`}>
                <h3 id={`${headingId}-contract`} className="text-xs font-medium uppercase tracking-widest text-secondary">数据契约</h3>
                <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-3 text-xs sm:grid-cols-2">
                  <div><dt className="text-muted">主键</dt><dd className="mt-0.5 font-mono">{entry.descriptor.primary_key.join(', ') || '未声明'}</dd></div>
                  <div><dt className="text-muted">点时态</dt><dd className="mt-0.5">{entry.descriptor.point_in_time ? '是' : '否'}</dd></div>
                  <div><dt className="text-muted">复权</dt><dd className="mt-0.5 font-mono">{metadataValue(entry.descriptor.adjustment)}</dd></div>
                  <div><dt className="text-muted">Provider</dt><dd className="mt-0.5 break-all font-mono">{metadataValue(entry.provider)}</dd></div>
                  <div><dt className="text-muted">Schema 版本</dt><dd className="mt-0.5 font-mono">{schema?.schema_version ?? entry.descriptor.schema_version}</dd></div>
                  <div><dt className="text-muted">单位版本</dt><dd className="mt-0.5 font-mono">{schema?.unit_version ?? entry.descriptor.unit_version}</dd></div>
                  <div className="sm:col-span-2"><dt className="text-muted">可用性原因代码</dt><dd className="mt-0.5 break-all font-mono">{metadataValue(entry.descriptor.availability.reason_code)}</dd></div>
                </dl>
              </section>

              <section aria-labelledby={`${headingId}-fields`}>
                <h3 id={`${headingId}-fields`} className="mb-3 text-xs font-medium uppercase tracking-widest text-secondary">字段</h3>
                <FieldTable fields={fields} />
              </section>

              <QualityLineagePanel entry={entry} />
              <DatasetRunHistory runs={runs} />
            </div>
          </AdvancedDisclosure>
        </div>
      </section>
    </div>
  )
}
