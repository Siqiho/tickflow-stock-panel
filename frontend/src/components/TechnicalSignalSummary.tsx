import { useMemo, useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import type { KlineRow } from '@/lib/api'
import {
  buildIndicatorSignalSummary,
  type IndicatorSignalState,
} from '@/lib/technical-signals'

interface Props {
  rows: KlineRow[]
  selectedDate?: string | null
}

const SIGNAL_META: Record<IndicatorSignalState, {
  label: string
  dotClass: string
  segmentClass: string
  tagClass: string
}> = {
  bullish: {
    label: '看多',
    dotClass: 'bg-bull',
    segmentClass: 'bg-bull',
    tagClass: 'border-bull/20 bg-bull/10 text-bull',
  },
  bearish: {
    label: '看空',
    dotClass: 'bg-bear',
    segmentClass: 'bg-bear',
    tagClass: 'border-bear/20 bg-bear/10 text-bear',
  },
  oscillating: {
    label: '震荡',
    dotClass: 'bg-warning',
    segmentClass: 'bg-warning',
    tagClass: 'border-warning/20 bg-warning/10 text-warning',
  },
  neutral: {
    label: '中性',
    dotClass: 'bg-muted',
    segmentClass: 'bg-muted/70',
    tagClass: 'border-border bg-elevated text-muted',
  },
}

const SIGNAL_ORDER: IndicatorSignalState[] = ['bullish', 'bearish', 'oscillating', 'neutral']

export function TechnicalSignalSummary({ rows, selectedDate }: Props) {
  const [expanded, setExpanded] = useState(true)
  const summary = useMemo(
    () => buildIndicatorSignalSummary(rows, selectedDate),
    [rows, selectedDate],
  )

  if (rows.length === 0) return null

  const countBySignal = {
    bullish: summary.bullish,
    bearish: summary.bearish,
    oscillating: summary.oscillating,
    neutral: summary.neutral,
  }
  const pctBySignal = {
    bullish: summary.bullishPct,
    bearish: summary.bearishPct,
    oscillating: summary.oscillatingPct,
    neutral: summary.neutralPct,
  }

  return (
    <section
      aria-label="指标信号汇总"
      className="mx-1 mb-2 overflow-hidden rounded-card border border-border/60 bg-elevated/25"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-border/40 px-2.5 py-1.5">
        <div className="flex min-w-0 items-baseline gap-2">
          <h3 className="text-[11px] font-semibold text-foreground">指标信号汇总</h3>
          <span className="text-[10px] text-muted">共 {summary.total} 项</span>
          {summary.date && (
            <span className="hidden text-[10px] font-mono text-muted/80 sm:inline">
              截至 {summary.date}
            </span>
          )}
        </div>

        <div className="ml-auto flex flex-wrap items-center justify-end gap-x-2.5 gap-y-1 text-[10px]">
          {SIGNAL_ORDER.map(signal => {
            const meta = SIGNAL_META[signal]
            return (
              <span key={signal} className="inline-flex items-center gap-1 whitespace-nowrap text-secondary">
                <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${meta.dotClass}`} />
                <span>{meta.label}</span>
                <span className="font-mono tabular-nums text-foreground/80">
                  {countBySignal[signal]} ({pctBySignal[signal]}%)
                </span>
              </span>
            )
          })}
          <button
            type="button"
            aria-expanded={expanded}
            aria-controls="technical-signal-tags"
            aria-label={expanded ? '收起指标信号' : '展开指标信号'}
            title={expanded ? '收起指标信号' : '展开指标信号'}
            onClick={() => setExpanded(value => !value)}
            className="inline-flex h-6 w-6 items-center justify-center rounded-btn text-muted transition-colors hover:bg-surface hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
          >
            {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      <div
        className="flex h-1.5 w-full overflow-hidden bg-border/25"
        role="img"
        aria-label={`看多 ${summary.bullishPct}%，看空 ${summary.bearishPct}%，震荡 ${summary.oscillatingPct}%，中性 ${summary.neutralPct}%`}
      >
        {SIGNAL_ORDER.map(signal => (
          <span
            key={signal}
            aria-hidden="true"
            className={SIGNAL_META[signal].segmentClass}
            style={{ width: `${pctBySignal[signal]}%` }}
          />
        ))}
      </div>

      {expanded && (
        <div
          id="technical-signal-tags"
          data-testid="technical-signal-tags"
          className="flex flex-wrap gap-1 px-2.5 py-2"
        >
          {summary.signals.map(signal => {
            const meta = SIGNAL_META[signal.signal]
            const unavailable = signal.available === false
            return (
              <span
                key={signal.name}
                data-testid="technical-signal-tag"
                title={unavailable
                  ? `${signal.name}：当前历史数据不足，暂记为中性`
                  : `${signal.name}：${meta.label}`}
                className={`inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[10px] leading-none ${meta.tagClass} ${unavailable ? 'border-dashed opacity-70' : ''}`}
              >
                {signal.name}
              </span>
            )
          })}
        </div>
      )}
    </section>
  )
}
