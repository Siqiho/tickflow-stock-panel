import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { Maximize2, Minimize2 } from 'lucide-react'

import { SourceTraceButton } from '@/components/SourceTraceButton'
import type { DimensionGroup } from '@/lib/analysis-adapter'
import { SOURCE_TRACE } from '@/lib/sourceTraceSubjects'
import type { MarketSnapshotCoverage, MarketSnapshotRow } from '@/lib/api'
import { fmtBigNum, fmtPct } from '@/lib/format'
import { cn } from '@/lib/cn'

type SizeMode = 'float_market_cap' | 'amount' | 'equal'

interface Props {
  groups: DimensionGroup[]
  quoteMap: Map<string, MarketSnapshotRow>
  selectedKey: string | null
  onSelect: (key: string) => void
  onStockClick: (symbol: string, name?: string) => void
  asOf?: string | null
  source?: string | null
  fetchedAt?: string | null
  coverage?: MarketSnapshotCoverage | null
  qualityStatus?: string[] | null
}

function finite(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function quoteFor(symbol: unknown, quoteMap: Map<string, MarketSnapshotRow>) {
  const raw = String(symbol ?? '').trim()
  if (!raw) return undefined
  return quoteMap.get(raw) ?? quoteMap.get(raw.replace(/\.\w+$/, ''))
}

function escapeHtml(value: unknown) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

function tileColor(pct: number | null) {
  if (pct == null || Math.abs(pct) < 0.00005) return '#4b5563'
  const strength = Math.min(1, Math.abs(pct) / 0.1)
  if (pct > 0) {
    const lightness = 34 + strength * 20
    return `hsl(0, 72%, ${lightness}%)`
  }
  const lightness = 28 + strength * 22
  return `hsl(146, 62%, ${lightness}%)`
}

function sourceLabel(source?: string | null) {
  if (source === 'quote_snapshot+enriched') return '全市场行情快照 + 增强日线'
  if (source === 'quote_snapshot') return '全市场行情快照'
  if (source === 'enriched') return '增强日线'
  return source || '本地行情'
}

export function IndustryTreemap({
  groups,
  quoteMap,
  selectedKey,
  onSelect,
  onStockClick,
  asOf,
  source,
  fetchedAt,
  coverage,
  qualityStatus,
}: Props) {
  const [sizeMode, setSizeMode] = useState<SizeMode>('float_market_cap')
  const [isFullscreen, setIsFullscreen] = useState(false)
  const elRef = useRef<HTMLDivElement>(null)
  const fullscreenButtonRef = useRef<HTMLButtonElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)

  const prepared = useMemo(() => {
    const matchedSymbols = new Set<string>()
    const allSymbols = new Set<string>()

    const data = groups.flatMap(group => {
      const seen = new Set<string>()
      const pctValues: number[] = []
      const children = group.stocks.flatMap(stock => {
        const symbol = String(stock.symbol ?? stock.code ?? '').trim()
        if (!symbol || seen.has(symbol)) return []
        seen.add(symbol)
        allSymbols.add(symbol)

        const quote = quoteFor(symbol, quoteMap)
        const pct = finite(quote?.change_pct)
        const close = finite(quote?.close)
        if (!quote || pct == null || close == null) return []

        matchedSymbols.add(symbol)
        pctValues.push(pct)
        const cap = finite(quote.float_market_cap) ?? finite(quote.market_cap)
        const amount = finite(quote.amount)
        const value = sizeMode === 'equal'
          ? 1
          : sizeMode === 'amount'
            ? Math.max(amount ?? 0, 1)
            : Math.max(cap ?? amount ?? 0, 1)
        const name = quote.name ?? stock.name ?? stock['股票简称'] ?? symbol

        return [{
          name: String(name),
          value,
          kind: 'stock',
          symbol,
          industry: group.key,
          pct,
          cap,
          amount,
          turnover: finite(quote.turnover_rate),
          itemStyle: { color: tileColor(pct) },
        }]
      })

      if (!children.length) return []
      const avgPct = pctValues.reduce((sum, value) => sum + value, 0) / pctValues.length
      return [{
        name: group.key,
        kind: 'industry',
        industry: group.key,
        members: seen.size,
        quoted: children.length,
        avgPct,
        children,
        itemStyle: {
          borderColor: selectedKey === group.key ? '#f59e0b' : '#252b38',
          borderWidth: selectedKey === group.key ? 4 : 2,
        },
      }]
    })

    return { data, matched: matchedSymbols.size, total: allSymbols.size }
  }, [groups, quoteMap, selectedKey, sizeMode])

  const option = useMemo<EChartsOption>(() => ({
    animation: false,
    backgroundColor: '#20242f',
    tooltip: {
      trigger: 'item',
      confine: true,
      backgroundColor: 'rgba(25,29,38,0.96)',
      borderColor: 'rgba(255,255,255,0.2)',
      padding: [10, 12],
      extraCssText: 'box-shadow:0 14px 38px rgba(0,0,0,.38);border-radius:10px;',
      textStyle: { color: '#f4f4f5', fontSize: isFullscreen ? 14 : 13, lineHeight: isFullscreen ? 23 : 21 },
      formatter: (params: any) => {
        const item = params?.data
        if (!item) return ''
        if (item.kind === 'industry') {
          return [
            `<b>${escapeHtml(item.industry)}</b>`,
            `行情覆盖 ${item.quoted}/${item.members}`,
            `平均涨跌 ${escapeHtml(fmtPct(item.avgPct))}`,
          ].join('<br/>')
        }
        return [
          `<b>${escapeHtml(item.name)}</b> <span style="color:#a1a1aa">${escapeHtml(item.symbol)}</span>`,
          `行业 ${escapeHtml(item.industry)}`,
          `涨跌幅 ${escapeHtml(fmtPct(item.pct))}`,
          `流通市值 ${escapeHtml(fmtBigNum(item.cap))}`,
          `成交额 ${escapeHtml(fmtBigNum(item.amount))}`,
          `换手率 ${item.turnover == null ? '—' : `${Number(item.turnover).toFixed(2)}%`}`,
        ].join('<br/>')
      },
    },
    series: [{
      type: 'treemap',
      name: '行业热力图',
      data: prepared.data as any,
      top: 2,
      left: 2,
      right: 2,
      bottom: 2,
      roam: false,
      nodeClick: false,
      breadcrumb: { show: false },
      leafDepth: 2,
      visibleMin: 1,
      squareRatio: 1.05,
      label: {
        show: true,
        color: '#f8fafc',
        fontSize: isFullscreen ? 13 : 12,
        fontWeight: 500,
        lineHeight: isFullscreen ? 18 : 17,
        overflow: 'truncate',
        formatter: (params: any) => {
          const item = params?.data
          if (!item || item.kind !== 'stock') return ''
          return `${item.name}\n${fmtPct(item.pct)}`
        },
      },
      upperLabel: {
        show: true,
        height: isFullscreen ? 32 : 29,
        color: '#f8fafc',
        fontSize: isFullscreen ? 16 : 14,
        fontWeight: 700,
        backgroundColor: '#1d222d',
        padding: [5, 8],
        formatter: (params: any) => {
          const item = params?.data
          if (!item || item.kind !== 'industry') return ''
          return `${item.industry}  ${fmtPct(item.avgPct)}  ${item.quoted}/${item.members}`
        },
      },
      itemStyle: {
        borderColor: '#20242f',
        borderWidth: 1,
        gapWidth: 1,
      },
      levels: [
        {
          itemStyle: { borderColor: '#20242f', borderWidth: 3, gapWidth: 3 },
          upperLabel: { show: false },
        },
        {
          itemStyle: { borderColor: '#252b38', borderWidth: 2, gapWidth: 2 },
          upperLabel: { show: true },
        },
        {
          itemStyle: { borderColor: 'rgba(32,36,47,0.9)', borderWidth: 1, gapWidth: 1 },
        },
      ],
      emphasis: {
        focus: 'ancestor',
        itemStyle: { borderColor: '#f8fafc', borderWidth: 2 },
      },
    }],
  }), [isFullscreen, prepared.data])

  useEffect(() => {
    const element = elRef.current
    if (!element) return
    const chart = echarts.init(element, undefined, {
      renderer: 'canvas',
      devicePixelRatio: Math.min(window.devicePixelRatio || 1, 2),
    })
    chartRef.current = chart
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(element)
    return () => {
      observer.disconnect()
      chart.dispose()
      chartRef.current = null
    }
  }, [isFullscreen])

  useEffect(() => {
    chartRef.current?.setOption(option, { notMerge: true })
  }, [option])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    const handleClick = (params: any) => {
      const item = params?.data
      if (item?.kind === 'industry' && item.industry) onSelect(String(item.industry))
      if (item?.kind === 'stock' && item.symbol) onStockClick(String(item.symbol), item.name ? String(item.name) : undefined)
    }
    chart.on('click', handleClick)
    return () => {
      chart.off('click', handleClick)
    }
  }, [isFullscreen, onSelect, onStockClick])

  useEffect(() => {
    if (!isFullscreen) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsFullscreen(false)
    }
    window.addEventListener('keydown', handleKeyDown)
    fullscreenButtonRef.current?.focus()
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [isFullscreen])

  const modes: Array<{ value: SizeMode; label: string }> = [
    { value: 'float_market_cap', label: '流通市值' },
    { value: 'amount', label: '成交额' },
    { value: 'equal', label: '等权' },
  ]
  const globalCoverage = coverage
    ? `${coverage.priced_rows.toLocaleString()} / ${coverage.instrument_rows.toLocaleString()}`
    : `${prepared.matched.toLocaleString()} / ${prepared.total.toLocaleString()}`
  const qualityLabel = qualityStatus?.includes('intraday_partial')
    ? '盘中快照'
    : qualityStatus?.includes('complete')
      ? '完整快照'
      : null

  const panel = (
    <section
      className={cn(
        'flex overflow-hidden border border-border bg-surface shadow-sm',
        isFullscreen ? 'h-full w-full flex-col rounded-xl' : 'flex-col rounded-2xl',
      )}
      role={isFullscreen ? 'dialog' : undefined}
      aria-modal={isFullscreen || undefined}
      aria-labelledby="industry-treemap-title"
    >
      <div className="flex flex-col gap-3 border-b border-border px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id="industry-treemap-title" className="text-[15px] font-semibold text-foreground">大盘热力图</h2>
            <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-700 dark:text-amber-300">
              行情 {globalCoverage}
            </span>
            <span className="rounded-full bg-sky-500/10 px-2 py-0.5 text-[10px] text-sky-700 dark:text-sky-300">
              行业着色 {prepared.matched.toLocaleString()} / {prepared.total.toLocaleString()}
            </span>
          </div>
          <div className="mt-1 text-[11px] text-muted">
            {asOf || '最新'} · {sourceLabel(source)}
            {qualityLabel ? ` · ${qualityLabel}` : ''}
            {fetchedAt ? ` · ${String(fetchedAt).replace('T', ' ').slice(0, 19)}` : ''}
            <span className="hidden sm:inline"> · 悬浮查看明细，点击查看个股</span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex rounded-lg border border-border bg-elevated/50 p-0.5" aria-label="热力图面积口径">
            {modes.map(mode => (
              <button
                key={mode.value}
                type="button"
                aria-pressed={sizeMode === mode.value}
                onClick={() => setSizeMode(mode.value)}
                className={cn(
                  'rounded-md px-2.5 py-1 text-[11px] transition-colors',
                  sizeMode === mode.value
                    ? 'bg-surface font-medium text-foreground shadow-sm'
                    : 'text-muted hover:text-foreground',
                )}
              >
                {mode.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1 text-[10px] text-muted" aria-label="涨跌幅颜色图例">
            {[-4, -2, 0, 2, 4].map(value => (
              <span
                key={value}
                className="min-w-8 rounded px-1.5 py-1 text-center text-white"
                style={{ backgroundColor: tileColor(value / 100) }}
              >
                {value > 0 ? '+' : ''}{value}%
              </span>
            ))}
          </div>
          <SourceTraceButton subjects={SOURCE_TRACE.industryHeatmap} />
          <button
            ref={fullscreenButtonRef}
            type="button"
            aria-expanded={isFullscreen}
            aria-label={isFullscreen ? '退出全屏热力图' : '最大化热力图'}
            title={isFullscreen ? '退出全屏（Esc）' : '最大化显示'}
            onClick={() => setIsFullscreen(value => !value)}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border bg-surface px-2.5 text-[11px] font-medium text-foreground shadow-sm transition-colors hover:border-accent/40 hover:bg-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
          >
            {isFullscreen ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
            <span>{isFullscreen ? '退出全屏' : '最大化'}</span>
          </button>
        </div>
      </div>

      <div className={cn(
        'relative min-h-0 bg-[#20242f]',
        isFullscreen ? 'flex-1' : 'h-[620px] lg:h-[680px] xl:h-[720px]',
      )}>
        <div ref={elRef} className="h-full w-full" role="img" aria-label="按行业分区、按个股展示的市场涨跌热力图" />
        {!prepared.data.length && (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-zinc-400">暂无可着色行情</div>
        )}
      </div>
    </section>
  )

  if (isFullscreen) {
    return createPortal(
      <div className="fixed inset-0 z-[120] bg-black/75 p-2 backdrop-blur-sm sm:p-4" data-testid="industry-treemap-fullscreen">
        {panel}
      </div>,
      document.body,
    )
  }

  return panel
}
