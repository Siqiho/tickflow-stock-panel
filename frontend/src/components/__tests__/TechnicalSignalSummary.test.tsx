import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { TechnicalSignalSummary } from '@/components/TechnicalSignalSummary'
import {
  INDICATOR_SIGNAL_NAMES,
  buildIndicatorSignalSummary,
  evaluateIndicatorSignals,
} from '@/lib/technical-signals'
import type { KlineRow } from '@/lib/api'

function makeRows(count = 180): KlineRow[] {
  const start = new Date('2025-01-01T00:00:00Z')
  return Array.from({ length: count }, (_, index) => {
    const baseline = 80 + index * 0.22 + Math.sin(index / 7) * 4
    const open = baseline + Math.sin(index / 3) * 0.8
    const close = baseline + Math.cos(index / 5) * 1.1
    return {
      date: new Date(start.getTime() + index * 86_400_000).toISOString().slice(0, 10),
      open,
      high: Math.max(open, close) + 2 + (index % 4) * 0.2,
      low: Math.min(open, close) - 2 - (index % 3) * 0.15,
      close,
      volume: 800_000 + (index % 17) * 38_000,
    }
  })
}

describe('technical indicator signal summary', () => {
  it('evaluates the complete 44-indicator contract in a stable display order', () => {
    const signals = evaluateIndicatorSignals(makeRows())

    expect(signals).toHaveLength(44)
    expect(signals.map(signal => signal.name)).toEqual(INDICATOR_SIGNAL_NAMES)
    expect(new Set(signals.map(signal => signal.name)).size).toBe(44)
    expect(signals.every(signal => (
      ['bullish', 'bearish', 'oscillating', 'neutral'] as const
    ).includes(signal.signal))).toBe(true)
  })

  it('uses the selected candle date and keeps the four counts consistent', () => {
    const rows = makeRows()
    const selectedDate = rows[145].date
    const summary = buildIndicatorSignalSummary(rows, selectedDate)

    expect(summary.date).toBe(selectedDate)
    expect(summary.total).toBe(44)
    expect(summary.bullish + summary.bearish + summary.oscillating + summary.neutral).toBe(44)
  })

  it('shows all indicators at the requested K-line position and can collapse them', () => {
    const rows = makeRows()
    render(<TechnicalSignalSummary rows={rows} selectedDate={rows.at(-1)?.date ?? null} />)

    const region = screen.getByRole('region', { name: '指标信号汇总' })
    expect(within(region).getByText('指标信号汇总')).toBeInTheDocument()
    expect(within(region).getByText('共 44 项')).toBeInTheDocument()
    expect(within(region).getAllByTestId('technical-signal-tag')).toHaveLength(44)

    const toggle = within(region).getByRole('button', { name: '收起指标信号' })
    fireEvent.click(toggle)

    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(within(region).queryByTestId('technical-signal-tags')).not.toBeInTheDocument()
  })
})
