import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StockInfoBar } from '@/components/StockInfoBar'
import type { KlineRow } from '@/lib/api'

describe('StockInfoBar', () => {
  it('uses the latest quote change fields instead of deriving them from a stale visible row', () => {
    const rows: KlineRow[] = [
      {
        date: '2026-07-31',
        open: 43,
        high: 45.39,
        low: 43,
        close: 45.39,
        volume: 20_000,
      },
      {
        date: '2026-08-07',
        open: 50.46,
        high: 50.97,
        low: 48.67,
        close: 49.11,
        prev_close: 50.45,
        change_amount: -1.34,
        change_pct: -0.02656095,
        volume: 24_954,
        is_quote_snapshot: true,
      },
    ]

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    render(
      <QueryClientProvider client={client}>
        <StockInfoBar
          symbol="603261.SH"
          name="立航科技"
          rows={rows}
          fields={[]}
          onFieldsChange={() => undefined}
        />
      </QueryClientProvider>,
    )

    expect(screen.getByText('49.11')).toBeInTheDocument()
    expect(screen.getByText('-1.34')).toBeInTheDocument()
    expect(screen.getByText('-2.66%')).toBeInTheDocument()
    expect(screen.queryByText('+3.72')).not.toBeInTheDocument()
  })
})
