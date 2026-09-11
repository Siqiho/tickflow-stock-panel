import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as echarts from 'echarts'
import {
  ArrowRight,
  BarChart3,
  CloudDownload,
  ExternalLink,
  Loader2,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Sparkles,
  TrendingDown,
  TrendingUp,
  X,
} from 'lucide-react'
import {
  api,
  type MarketPulseEvent,
  type MarketPulsePoint,
} from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { useChartChrome } from '@/lib/theme'
import { cn } from '@/lib/cn'
import { DatePicker } from '@/components/DatePicker'
import { SourceTraceButton } from '@/components/SourceTraceButton'
import { SOURCE_TRACE } from '@/lib/sourceTraceSubjects'

const DEFAULT_BENCHMARK = '000001.SH'
const BENCHMARKS = [
  { symbol: '000001.SH', name: '上证指数', source: 'owned' },
  { symbol: '399001.SZ', name: '深证成指', source: 'live' },
  { symbol: '399006.SZ', name: '创业板指', source: 'live' },
  { symbol: '000680.SH', name: '科创综指', source: 'live' },
] as const

type DirectionFilter = 'all' | 'up' | 'down'

function todayInShanghai(): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date())
}

function timeLabel(value: string): string {
  const match = value.match(/(\d{2}):(\d{2})/)
  return match ? `${match[1]}:${match[2]}` : value
}

function minuteIndex(value: string): number {
  const match = value.match(/(\d{2}):(\d{2})/)
  return match ? Number(match[1]) * 60 + Number(match[2]) : 0
}

function formatAmount(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  if (value >= 1e12) return `${(value / 1e12).toFixed(2)}万亿`
  if (value >= 1e8) return `${(value / 1e8).toFixed(0)}亿`
  if (value >= 1e4) return `${(value / 1e4).toFixed(0)}万`
  return value.toFixed(0)
}

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

function closestPointIndex(event: MarketPulseEvent, points: MarketPulsePoint[]): number {
  const target = minuteIndex(event.event_time)
  let best = 0
  let distance = Number.POSITIVE_INFINITY
  points.forEach((point, index) => {
    const nextDistance = Math.abs(minuteIndex(point.event_time) - target)
    if (nextDistance < distance) {
      best = index
      distance = nextDistance
    }
  })
  return best
}

function eventLabelText(events: MarketPulseEvent[]): string {
  const names = [...new Set(events.map(event => event.sector_name).filter(Boolean))]
  if (names.length <= 2) return names.join(' / ')
  return `${names.slice(0, 2).join(' / ')} +${names.length - 2}`
}

function eventFocus(event: MarketPulseEvent, tradeDate?: string | null): string {
  return `请结合${tradeDate || event.trade_date}的市场脉搏，解释${timeLabel(event.event_time)}发生的“${event.sector_name}”${event.direction === 'up' ? '走强' : '走弱'}异动，并说明指数位置、量能配合、持续性风险和下一交易日观察点。`
}

function indexRowsToPulsePoints(
  rows: Array<{ datetime: string; close: number; volume: number; amount: number | null }>,
  symbol: string,
  name: string,
  tradeDate: string,
): MarketPulsePoint[] {
  return rows.map((row, index) => ({
    event_id: `comparison:${symbol}:${index}`,
    trade_date: tradeDate,
    event_time: row.datetime,
    minute: Number(timeLabel(row.datetime).replace(':', '')),
    benchmark_symbol: symbol,
    benchmark_name: name,
    last_price: row.close,
    change_ratio: 0,
    preclose: 0,
    open: row.close,
    volume: row.volume,
    amount: row.amount ?? 0,
    source: 'index_minute_live',
    unit_version: 'canonical_minute_v1',
  }))
}

export function MarketPulsePanel({ tradeDate }: { tradeDate?: string | null }) {
  const queryClient = useQueryClient()
  const chrome = useChartChrome()
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)
  const [benchmarkSymbol, setBenchmarkSymbol] = useState(DEFAULT_BENCHMARK)
  const [direction, setDirection] = useState<DirectionFilter>('all')
  const [selectedEvent, setSelectedEvent] = useState<MarketPulseEvent | null>(null)
  const [playbackIndex, setPlaybackIndex] = useState<number | null>(null)
  const [playing, setPlaying] = useState(false)
  const [selectedTradeDate, setSelectedTradeDate] = useState(tradeDate ?? '')
  const requestedTradeDate = selectedTradeDate || tradeDate || undefined

  const pulse = useQuery({
    queryKey: QK.marketPulse(requestedTradeDate),
    queryFn: () => api.marketPulse(requestedTradeDate),
    staleTime: 30_000,
  })
  const resolvedDate = pulse.data?.resolved_date ?? requestedTradeDate ?? null
  const selectedBenchmark = BENCHMARKS.find(item => item.symbol === benchmarkSymbol) ?? BENCHMARKS[0]
  const comparison = useQuery({
    queryKey: QK.indexMinute(benchmarkSymbol, resolvedDate ?? ''),
    queryFn: () => api.indexMinute(benchmarkSymbol, resolvedDate ?? undefined),
    enabled: benchmarkSymbol !== DEFAULT_BENCHMARK && !!resolvedDate,
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  })

  const sync = useMutation({
    mutationFn: () => api.syncMarketPulse(requestedTradeDate),
    onSuccess: async (result) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: QK.marketPulse(result.resolved_date) }),
        queryClient.invalidateQueries({ queryKey: QK.marketPulse(requestedTradeDate) }),
        queryClient.invalidateQueries({ queryKey: QK.dataCatalog }),
        queryClient.invalidateQueries({ queryKey: QK.dataCatalogDataset('market_pulse') }),
        queryClient.invalidateQueries({ queryKey: QK.dataCatalogSchema('market_pulse') }),
        queryClient.invalidateQueries({ queryKey: QK.dataCatalogRuns('market_pulse') }),
        queryClient.invalidateQueries({ queryKey: QK.dataCatalogRuns() }),
        queryClient.invalidateQueries({ queryKey: QK.dataControlSummary }),
      ])
      setBenchmarkSymbol(DEFAULT_BENCHMARK)
    },
  })

  useEffect(() => {
    if (tradeDate) setSelectedTradeDate(tradeDate)
  }, [tradeDate])

  const points = useMemo(() => {
    const basePoints = pulse.data?.points ?? []
    if (benchmarkSymbol === DEFAULT_BENCHMARK) return basePoints
    return indexRowsToPulsePoints(
      comparison.data?.rows ?? [],
      benchmarkSymbol,
      selectedBenchmark.name,
      resolvedDate ?? '',
    )
  }, [benchmarkSymbol, comparison.data?.rows, pulse.data?.points, resolvedDate, selectedBenchmark.name])
  const filteredEvents = useMemo(() => {
    const events = pulse.data?.events ?? []
    return direction === 'all' ? events : events.filter(event => event.direction === direction)
  }, [direction, pulse.data?.events])
  const visiblePoints = playbackIndex == null ? points : points.slice(0, playbackIndex + 1)
  const visibleThrough = visiblePoints.length > 0
    ? minuteIndex(visiblePoints[visiblePoints.length - 1].event_time)
    : Number.POSITIVE_INFINITY
  const visibleEvents = filteredEvents.filter(event => minuteIndex(event.event_time) <= visibleThrough)

  useEffect(() => {
    setPlaybackIndex(null)
    setPlaying(false)
    setSelectedEvent(null)
  }, [benchmarkSymbol, resolvedDate])

  useEffect(() => {
    if (!playing || points.length === 0) return
    const timer = window.setInterval(() => {
      setPlaybackIndex((current) => {
        const next = current == null ? 0 : current + 1
        if (next >= points.length - 1) {
          window.clearInterval(timer)
          setPlaying(false)
          return points.length - 1
        }
        return next
      })
    }, 90)
    return () => window.clearInterval(timer)
  }, [playing, points.length])

  useEffect(() => {
    if (!containerRef.current || points.length === 0) return
    const chart = echarts.init(containerRef.current)
    chartRef.current = chart
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(containerRef.current)
    return () => {
      observer.disconnect()
      chart.dispose()
      chartRef.current = null
    }
  }, [points.length])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart || visiblePoints.length === 0) return
    const times = visiblePoints.map(point => timeLabel(point.event_time))
    const eventGroups = new Map<number, MarketPulseEvent[]>()
    visibleEvents.forEach((event) => {
      const index = closestPointIndex(event, visiblePoints)
      const group = eventGroups.get(index) ?? []
      group.push(event)
      eventGroups.set(index, group)
    })
    const scatter = Array.from(eventGroups.entries()).map(([index, events], order) => {
      const hasUp = events.some(event => event.direction === 'up')
      const hasDown = events.some(event => event.direction === 'down')
      const color = hasUp && hasDown ? '#F59E0B' : hasUp ? '#F04438' : '#12B76A'
      const labelText = eventLabelText(events)
      const selected = events.some(event => event.event_id === selectedEvent?.event_id)
      return {
        value: [times[index], visiblePoints[index].last_price],
        symbol: 'circle',
        symbolSize: selected ? 13 : 11,
        itemStyle: { color, borderColor: chrome.labelBg, borderWidth: 1.5 },
        events,
        labelText,
        label: {
          show: Boolean(labelText),
          position: order % 2 === 0 ? 'top' : 'bottom',
          distance: 8,
        },
      }
    })

    chart.setOption({
      animation: false,
      backgroundColor: 'transparent',
      grid: { left: 54, right: 64, top: 36, bottom: 42 },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross', lineStyle: { color: chrome.crosshair } },
        backgroundColor: chrome.tooltipBg,
        borderColor: chrome.tooltipBorder,
        textStyle: { color: chrome.text, fontSize: 11 },
        formatter: (params: any[]) => {
          const price = params.find(item => item.seriesName === selectedBenchmark.name)
          const amount = params.find(item => item.seriesName === '分钟成交额')
          const eventPoint = params.find(item => item.seriesName === '板块异动')
          let html = `<strong>${escapeHtml(String(params[0]?.axisValue ?? ''))}</strong>`
          if (price) html += `<br/>${escapeHtml(selectedBenchmark.name)}：${Number(price.value).toFixed(2)}`
          if (amount) html += `<br/>分钟成交额：${escapeHtml(formatAmount(Number(amount.value)))}`
          const events = eventPoint?.data?.events as MarketPulseEvent[] | undefined
          if (events?.length) {
            html += '<br/><span style="color:#f59e0b">板块事件</span>'
            events.forEach((event) => {
              html += `<br/>${event.direction === 'up' ? '↑' : '↓'} ${escapeHtml(event.sector_name)} ${escapeHtml(timeLabel(event.event_time))}`
            })
          }
          return html
        },
      },
      xAxis: {
        type: 'category',
        data: times,
        boundaryGap: false,
        axisLine: { lineStyle: { color: chrome.border } },
        axisTick: { show: false },
        axisLabel: { color: chrome.text, fontSize: 10, hideOverlap: true },
      },
      yAxis: [
        {
          type: 'value',
          scale: true,
          name: '点位',
          nameTextStyle: { color: chrome.muted, fontSize: 10 },
          axisLabel: { color: chrome.text, fontSize: 10, formatter: (value: number) => value.toFixed(0) },
          splitLine: { lineStyle: { color: chrome.grid } },
        },
        {
          type: 'value',
          name: '成交额',
          nameTextStyle: { color: chrome.muted, fontSize: 10 },
          axisLabel: { color: chrome.text, fontSize: 10, formatter: (value: number) => formatAmount(value) },
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: selectedBenchmark.name,
          type: 'line',
          data: visiblePoints.map(point => point.last_price),
          symbol: 'none',
          lineStyle: { color: '#3B82F6', width: 1.8 },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(59,130,246,0.22)' },
              { offset: 1, color: 'rgba(59,130,246,0.01)' },
            ]),
          },
          z: 3,
        },
        {
          name: '分钟成交额',
          type: 'bar',
          yAxisIndex: 1,
          data: visiblePoints.map(point => point.amount),
          barWidth: '60%',
          itemStyle: { color: 'rgba(148,163,184,0.2)' },
          z: 1,
        },
        {
          name: '板块异动',
          type: 'scatter',
          data: scatter,
          symbol: 'circle',
          symbolSize: 11,
          z: 5,
          label: {
            show: true,
            position: 'top',
            distance: 8,
            hideOverlap: false,
            formatter: (params: any) => params.data?.labelText || '',
            color: chrome.text,
            backgroundColor: chrome.labelBg,
            borderColor: chrome.border,
            borderWidth: 1,
            borderRadius: 3,
            padding: [2, 4],
            fontSize: 10,
          },
        },
      ],
    }, true)
    chart.off('click')
    chart.on('click', (params: any) => {
      const events = params?.data?.events as MarketPulseEvent[] | undefined
      if (params.seriesName === '板块异动' && events?.length) setSelectedEvent(events[0])
    })
  }, [chrome, selectedBenchmark.name, selectedEvent?.event_id, visibleEvents, visiblePoints])

  const togglePlayback = () => {
    if (points.length === 0) return
    if (playbackIndex != null && playbackIndex >= points.length - 1) setPlaybackIndex(0)
    setPlaying(value => !value)
  }
  const resetPlayback = () => {
    setPlaying(false)
    setPlaybackIndex(null)
  }

  const loading = pulse.isLoading || (benchmarkSymbol !== DEFAULT_BENCHMARK && comparison.isLoading)
  const hasPulse = pulse.data?.available && (pulse.data?.points.length ?? 0) > 0
  const hasPoints = points.length > 0

  return (
    <section id="market-pulse" aria-labelledby="market-pulse-heading" className="scroll-mt-20 border-y border-border bg-surface/55 py-3">
      <div className="flex flex-wrap items-start justify-between gap-3 px-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <BarChart3 aria-hidden="true" className="h-4 w-4 text-accent" />
            <h2 id="market-pulse-heading" className="text-sm font-semibold text-foreground">市场脉搏</h2>
            <DatePicker
              value={requestedTradeDate ?? resolvedDate ?? ''}
              onChange={setSelectedTradeDate}
              max={todayInShanghai()}
              placeholder="选择交易日"
              align="left"
              buttonClassName="font-mono"
            />
          </div>
          <p className="mt-1 text-[11px] text-muted">指数走势、分钟成交额与板块异动使用同一交易日时间轴</p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <label className="sr-only" htmlFor="market-pulse-benchmark">比较指数</label>
          <select
            id="market-pulse-benchmark"
            value={benchmarkSymbol}
            onChange={(event) => setBenchmarkSymbol(event.target.value)}
            className="h-7 rounded-btn border border-border bg-base px-2 text-[11px] text-secondary outline-none transition-colors hover:text-foreground focus:border-accent"
          >
            {BENCHMARKS.map(item => (
              <option key={item.symbol} value={item.symbol}>{item.name}{item.source === 'live' ? '（即时）' : ''}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => pulse.refetch()}
            disabled={pulse.isFetching}
            className="inline-flex h-7 items-center gap-1 rounded-btn border border-border bg-base px-2 text-[11px] text-secondary transition-colors hover:text-foreground disabled:opacity-40"
          >
            <RefreshCw aria-hidden="true" className={cn('h-3 w-3', pulse.isFetching && 'animate-spin')} />
            刷新本地
          </button>
          <button
            type="button"
            onClick={() => sync.mutate()}
            disabled={sync.isPending}
            className="inline-flex h-7 items-center gap-1 rounded-btn border border-border bg-base px-2 text-[11px] text-secondary transition-colors hover:text-foreground disabled:opacity-40"
          >
            {sync.isPending ? <Loader2 aria-hidden="true" className="h-3 w-3 animate-spin" /> : <CloudDownload aria-hidden="true" className="h-3 w-3" />}
            {sync.isPending ? '更新中…' : '更新'}
          </button>
          <SourceTraceButton
            subjects={SOURCE_TRACE.marketPulse}
            variant="chip"
            label="来源"
            className="h-7 gap-1 border border-border bg-base px-2 text-[11px] font-normal text-secondary hover:bg-base hover:text-foreground"
          />
        </div>
      </div>

      {sync.isError && (
        <div role="alert" className="mx-3 mt-2 rounded-btn border border-danger/30 bg-danger/5 px-3 py-2 text-[11px] text-danger">
          更新失败：{sync.error instanceof Error ? sync.error.message : '财联社市场脉搏暂时不可用'}
        </div>
      )}

      {loading ? (
        <div className="mx-3 mt-3 h-[320px] animate-pulse rounded-btn bg-elevated/60" aria-label="市场脉搏加载中" />
      ) : !hasPulse ? (
        <div className="mx-3 mt-3 flex min-h-48 flex-col items-center justify-center gap-3 border-y border-border py-8 text-center">
          <BarChart3 aria-hidden="true" className="h-6 w-6 text-muted" />
          <div>
            <div className="text-sm font-medium text-foreground">该日期尚无本地市场脉搏</div>
            <p className="mt-1 text-xs text-muted">点击“更新”后才会访问外部端点并写入本地 Parquet。</p>
          </div>
        </div>
      ) : !hasPoints ? (
        <div role="alert" className="mx-3 mt-3 rounded-btn border border-warning/30 bg-warning/5 px-3 py-8 text-center text-xs text-warning">
          {comparison.isError ? '所选指数的即时分时暂不可用；市场事件缓存仍然保留。' : '所选指数暂无分时数据。'}
        </div>
      ) : (
        <>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 px-3">
            <div className="flex items-center gap-1" aria-label="板块异动方向筛选">
              {([
                ['all', '全部'],
                ['up', '走强'],
                ['down', '走弱'],
              ] as const).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setDirection(value)}
                  aria-pressed={direction === value}
                  className={cn(
                    'rounded-btn px-2 py-1 text-[10px] transition-colors',
                    direction === value ? 'bg-elevated text-foreground' : 'text-muted hover:text-secondary',
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-1.5">
              <span className="font-mono text-[10px] text-muted">
                {playbackIndex == null ? `${points.length} 分钟` : `${playbackIndex + 1} / ${points.length}`}
              </span>
              <button
                type="button"
                onClick={togglePlayback}
                aria-label={playing ? '暂停盘中回放' : '开始盘中回放'}
                className="inline-flex items-center gap-1 rounded-btn border border-border bg-base px-2 py-1 text-[10px] text-secondary hover:text-foreground"
              >
                {playing ? <Pause aria-hidden="true" className="h-3 w-3" /> : <Play aria-hidden="true" className="h-3 w-3" />}
                {playing ? '暂停' : '回放'}
              </button>
              <button
                type="button"
                onClick={resetPlayback}
                disabled={playbackIndex == null}
                aria-label="退出盘中回放"
                className="rounded-btn p-1 text-muted hover:bg-elevated hover:text-foreground disabled:opacity-30"
              >
                <RotateCcw aria-hidden="true" className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          <div className={cn('mt-1 grid min-w-0 gap-3', selectedEvent ? 'xl:grid-cols-[minmax(0,1fr)_18rem]' : 'grid-cols-1')}>
            <div ref={containerRef} className="h-[340px] min-w-0" role="img" aria-label={`${selectedBenchmark.name}分时、成交额与板块异动图`} />
            {selectedEvent && (
              <aside className="mx-3 mb-2 border-t border-border px-1 pt-3 xl:mx-0 xl:mb-0 xl:border-l xl:border-t-0 xl:pl-3 xl:pr-3 xl:pt-2" aria-label="板块异动详情">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-1.5">
                      {selectedEvent.direction === 'up'
                        ? <TrendingUp aria-hidden="true" className="h-4 w-4 text-bull" />
                        : <TrendingDown aria-hidden="true" className="h-4 w-4 text-bear" />}
                      <h3 className="text-sm font-semibold text-foreground">{selectedEvent.sector_name}</h3>
                    </div>
                    <div className="mt-1 font-mono text-[10px] text-muted">{timeLabel(selectedEvent.event_time)} · {selectedEvent.sector_code}</div>
                  </div>
                  <button type="button" onClick={() => setSelectedEvent(null)} aria-label="关闭异动详情" className="rounded-btn p-1 text-muted hover:bg-elevated hover:text-foreground">
                    <X aria-hidden="true" className="h-3.5 w-3.5" />
                  </button>
                </div>
                <p className="mt-3 text-[11px] leading-relaxed text-secondary">
                  财联社记录该板块在 {timeLabel(selectedEvent.event_time)} 出现{selectedEvent.direction === 'up' ? '走强' : '走弱'}异动。该事件是盘面时间点，不等同于持续趋势或交易建议。
                </p>
                <div className="mt-3 space-y-1.5">
                  <Link to={`/concept-analysis?focus=${encodeURIComponent(selectedEvent.sector_name)}`} className="flex items-center justify-between rounded-btn border border-border px-2.5 py-2 text-[11px] text-secondary hover:bg-elevated hover:text-foreground">
                    在概念分析中查找<ArrowRight aria-hidden="true" className="h-3 w-3" />
                  </Link>
                  <Link to={`/industry-analysis?focus=${encodeURIComponent(selectedEvent.sector_name)}`} className="flex items-center justify-between rounded-btn border border-border px-2.5 py-2 text-[11px] text-secondary hover:bg-elevated hover:text-foreground">
                    在行业分析中查找<ArrowRight aria-hidden="true" className="h-3 w-3" />
                  </Link>
                  <Link
                    to={`/review?as_of=${encodeURIComponent(resolvedDate ?? selectedEvent.trade_date)}&focus=${encodeURIComponent(eventFocus(selectedEvent, resolvedDate))}`}
                    className="flex items-center justify-between rounded-btn bg-accent/10 px-2.5 py-2 text-[11px] font-medium text-accent hover:bg-accent/15"
                  >
                    带入 AI 复盘<Sparkles aria-hidden="true" className="h-3 w-3" />
                  </Link>
                </div>
              </aside>
            )}
          </div>

          <div className="border-t border-border px-3 pt-2">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-[10px] font-medium uppercase tracking-widest text-secondary">板块轮动轨迹</span>
              <span className="font-mono text-[10px] text-muted">{visibleEvents.length} 条</span>
            </div>
            <div className="flex gap-1.5 overflow-x-auto pb-1" role="list" aria-label="板块轮动事件">
              {visibleEvents.map(event => (
                <button
                  key={event.event_id}
                  type="button"
                  role="listitem"
                  onClick={() => setSelectedEvent(event)}
                  aria-pressed={selectedEvent?.event_id === event.event_id}
                  className={cn(
                    'flex shrink-0 items-center gap-1 rounded-btn border px-2 py-1.5 text-[10px] transition-colors',
                    selectedEvent?.event_id === event.event_id
                      ? 'border-accent/50 bg-accent/10 text-foreground'
                      : 'border-border bg-base/40 text-secondary hover:bg-elevated',
                  )}
                >
                  <span className={event.direction === 'up' ? 'text-bull' : 'text-bear'}>{event.direction === 'up' ? '↑' : '↓'}</span>
                  <span className="font-mono text-muted">{timeLabel(event.event_time)}</span>
                  <span>{event.sector_name}</span>
                </button>
              ))}
              {visibleEvents.length === 0 && <span className="py-1.5 text-[11px] text-muted">当前筛选没有板块事件</span>}
            </div>
          </div>
        </>
      )}
    </section>
  )
}

export function MarketPulseEvidenceLink({ tradeDate }: { tradeDate?: string | null }) {
  const pulse = useQuery({
    queryKey: QK.marketPulse(tradeDate),
    queryFn: () => api.marketPulse(tradeDate),
    enabled: !!tradeDate,
    staleTime: 30_000,
  })
  const available = pulse.data?.available
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-y border-border bg-surface/50 px-3.5 py-2 text-[11px]">
      <div className="flex min-w-0 items-center gap-2">
        <BarChart3 aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-accent" />
        <span className="font-medium text-foreground">盘面证据</span>
        {pulse.isLoading ? (
          <span className="text-muted">读取本地市场脉搏…</span>
        ) : available ? (
          <span className="truncate text-secondary">{pulse.data?.minute_rows} 个分钟点 · {pulse.data?.event_rows} 条板块事件</span>
        ) : (
          <span className="truncate text-muted">该日期尚无市场脉搏缓存</span>
        )}
      </div>
      <Link
        to={`/?as_of=${encodeURIComponent(tradeDate ?? '')}#market-pulse`}
        className="inline-flex items-center gap-1 rounded-btn px-2 py-1 text-accent hover:bg-accent/10"
      >
        {available ? '查看同日时间轴' : '前往看板获取'}
        <ExternalLink aria-hidden="true" className="h-3 w-3" />
      </Link>
    </div>
  )
}
