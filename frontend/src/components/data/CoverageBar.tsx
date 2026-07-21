import type { MarketCoverage } from '@/lib/api'

const CORE_MARKETS: MarketCoverage['market'][] = ['SH', 'SZ', 'BJ']

export function CoverageBar({ coverage }: { coverage: MarketCoverage[] }) {
  const byMarket = new Map(coverage.map((item) => [item.market, item]))
  const ordered = [
    ...CORE_MARKETS.map((market) => ({ market, item: byMarket.get(market) })),
    ...(byMarket.get('OTHER')?.symbol_count ? [{ market: 'OTHER' as const, item: byMarket.get('OTHER') }] : []),
  ]

  return (
    <div className="space-y-1.5" aria-label="市场覆盖">
      {ordered.map(({ market, item }) => {
        const ratioText = item?.ratio == null ? '覆盖率未知' : `${(item.ratio * 100).toFixed(1)}%`
        return (
          <div key={market} className="grid grid-cols-[2rem_minmax(0,1fr)_auto] items-center gap-2 text-[10px]">
            <span data-testid="coverage-market" className="font-mono font-medium text-secondary">{market}</span>
            <div className="h-1.5 overflow-hidden rounded-full bg-elevated" aria-label={`${market} ${ratioText}`}>
              {item?.ratio != null && (
                <div
                  className="h-full rounded-full bg-accent"
                  style={{ width: `${Math.max(0, Math.min(1, item.ratio)) * 100}%` }}
                />
              )}
            </div>
            <span className="flex flex-col items-end font-mono tabular-nums text-secondary">
              <span>{item ? item.symbol_count.toLocaleString() : '未知'} / {item?.expected_symbol_count == null ? '未知' : item.expected_symbol_count.toLocaleString()}</span>
              <span className="text-muted">{ratioText}</span>
            </span>
          </div>
        )
      })}
    </div>
  )
}
