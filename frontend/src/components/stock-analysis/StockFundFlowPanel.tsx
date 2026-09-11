import { useEffect, useMemo, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { Loader2, RefreshCw, WalletCards } from 'lucide-react'
import { SourceTraceButton } from '@/components/SourceTraceButton'
import { api } from '@/lib/api'
import { SOURCE_TRACE } from '@/lib/sourceTraceSubjects'
import { fmtBigNum } from '@/lib/format'
import { useChartChrome, type ChartChrome } from '@/lib/theme'

interface StockFundFlowPoint {
  symbol?: string
  date: string
  main_net: number | null
  small_net?: number | null
  med_net?: number | null
  large_net?: number | null
  super_net?: number | null
  main_net_pct?: number | null
  source?: string | null
  unit_amount?: string | null
}

interface Props {
  symbol: string
  height?: number
  limit?: number
  className?: string
}

const INFLOW = '#C74040'
const OUTFLOW = '#2D9B65'
const CUMULATIVE = '#3B82F6'

function finite(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function sumFlow(rows: StockFundFlowPoint[]) {
  return rows.reduce((sum, row) => sum + (finite(row.main_net) ? row.main_net : 0), 0)
}

function flowText(value: number | null | undefined) {
  if (!finite(value)) return '—'
  const text = fmtBigNum(value)
  return value > 0 ? `+${text}` : text
}

function flowTone(value: number | null | undefined) {
  if (!finite(value) || value === 0) return 'text-muted'
  return value > 0 ? 'text-bull' : 'text-bear'
}

function pctText(value: number | null | undefined) {
  if (!finite(value)) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
}

function latestStreak(rows: StockFundFlowPoint[]) {
  const latest = rows[rows.length - 1]?.main_net
  if (!finite(latest) || latest === 0) return null
  const direction = latest > 0 ? 1 : -1
  let days = 0
  for (let i = rows.length - 1; i >= 0; i -= 1) {
    const value = rows[i].main_net
    if (!finite(value) || value === 0 || Math.sign(value) !== direction) break
    days += 1
  }
  if (days < 2) return null
  return `${days}日连续${direction > 0 ? '净流入' : '净流出'}`
}

function buildOption(rows: StockFundFlowPoint[], chrome: ChartChrome): EChartsOption {
  let cumulative = 0
  const plotted = rows.slice(-24).map(row => {
    const daily = finite(row.main_net) ? row.main_net : 0
    cumulative += daily
    return { ...row, daily, cumulative }
  })

  const dates = plotted.map(row => row.date)
  const daily = plotted.map(row => row.daily)
  const cumulativeSeries = plotted.map(row => row.cumulative)

  return {
    animation: false,
    backgroundColor: 'transparent',
    grid: { left: 8, right: 8, top: 30, bottom: 24, containLabel: true },
    legend: {
      top: 0,
      right: 0,
      itemWidth: 10,
      itemHeight: 6,
      textStyle: { color: chrome.muted, fontSize: 9 },
      data: ['当日主力', '累计主力'],
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: chrome.tooltipBg,
      borderColor: chrome.tooltipBorder,
      textStyle: { color: chrome.text, fontSize: 10 },
      formatter: (params: any) => {
        const list = Array.isArray(params) ? params : [params]
        const dailyValue = Number(list[0]?.value ?? 0)
        const cumulativeValue = Number(list[1]?.value ?? 0)
        return [
          `<div style="font-family:ui-monospace,monospace">`,
          `<div>${list[0]?.axisValue ?? ''}</div>`,
          `<div>当日主力 <b>${flowText(dailyValue)}</b></div>`,
          `<div>可见区间累计 <b>${flowText(cumulativeValue)}</b></div>`,
          `</div>`,
        ].join('')
      },
    },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: true,
      axisLine: { lineStyle: { color: chrome.border } },
      axisTick: { show: false },
      axisLabel: {
        color: chrome.muted,
        fontSize: 9,
        formatter: (value: string) => value.slice(5),
        interval: Math.max(0, Math.ceil(dates.length / 4) - 1),
      },
    },
    yAxis: [
      {
        type: 'value',
        splitNumber: 3,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: chrome.muted, fontSize: 9, formatter: (value: number) => fmtBigNum(value) },
        splitLine: { lineStyle: { color: chrome.grid } },
      },
      {
        type: 'value',
        splitLine: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { show: false },
      },
    ],
    series: [
      {
        name: '当日主力',
        type: 'bar',
        data: daily.map(value => ({
          value,
          itemStyle: { color: value >= 0 ? INFLOW : OUTFLOW, borderRadius: [2, 2, 0, 0] },
        })),
        barMaxWidth: 9,
        markLine: {
          symbol: 'none',
          silent: true,
          label: { show: false },
          lineStyle: { color: chrome.refLine, width: 1 },
          data: [{ yAxis: 0 }],
        },
      },
      {
        name: '累计主力',
        type: 'line',
        yAxisIndex: 1,
        data: cumulativeSeries,
        showSymbol: false,
        smooth: 0.18,
        lineStyle: { color: CUMULATIVE, width: 1.5 },
        itemStyle: { color: CUMULATIVE },
      },
    ],
  }
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-btn border border-border/70 bg-elevated/50 px-2 py-1.5">
      <div className="text-[9px] text-muted">{label}</div>
      <div className={`mt-0.5 truncate font-mono text-[11px] font-medium ${tone ?? 'text-foreground'}`}>{value}</div>
    </div>
  )
}

export function StockFundFlowPanel({ symbol, height = 360, limit = 60, className }: Props) {
  const chrome = useChartChrome()
  const queryClient = useQueryClient()
  const chartElRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)
  const queryKey = ['fund-flow-stock', symbol, limit] as const

  const query = useQuery({
    queryKey,
    queryFn: () => api.fundFlowStock(symbol, limit),
    enabled: !!symbol,
    staleTime: 60_000,
  })

  const refresh = useMutation({
    mutationFn: () => api.fundFlowStockRefresh(symbol),
    onSuccess: () => queryClient.invalidateQueries({ queryKey }),
  })

  const rows = useMemo(() => {
    const raw = (query.data?.rows ?? []) as StockFundFlowPoint[]
    return [...raw]
      .filter(row => typeof row.date === 'string' && row.date.length > 0)
      .sort((a, b) => a.date.localeCompare(b.date))
  }, [query.data?.rows])

  const validRows = useMemo(() => rows.filter(row => finite(row.main_net)), [rows])
  const latest = validRows[validRows.length - 1]
  const flow5 = sumFlow(validRows.slice(-5))
  const flow20 = sumFlow(validRows.slice(-20))
  const direction = flow5 > 0 ? '近5日流入占优' : flow5 < 0 ? '近5日流出占优' : '近5日多空均衡'
  const streak = latestStreak(validRows)
  const option = useMemo(
    () => (validRows.length ? buildOption(validRows, chrome) : null),
    [chrome, validRows],
  )

  useEffect(() => {
    if (!option) {
      chartRef.current?.clear()
      return
    }
    const element = chartElRef.current
    if (!element) return
    let chart = chartRef.current
    if (!chart) {
      chart = echarts.init(element, undefined, { renderer: 'canvas' })
      chartRef.current = chart
    }
    chart.setOption(option, true)
    const observer = new ResizeObserver(() => chart?.resize())
    observer.observe(element)
    return () => observer.disconnect()
  }, [option])

  useEffect(() => () => {
    chartRef.current?.dispose()
    chartRef.current = null
  }, [])

  const sourceLabel = latest?.source === 'eastmoney_fflow'
    ? '东财公开资金流'
    : latest?.source || '本地缓存'

  return (
    <section
      className={className}
      style={{ height, display: 'flex', flexDirection: 'column', minWidth: 0 }}
      data-testid="stock-fund-flow-panel"
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-foreground">
            <WalletCards className="h-3.5 w-3.5 text-sky-400" />
            资金分析
            <SourceTraceButton subjects={SOURCE_TRACE.stockFundFlow} className="h-6 w-6" />
          </div>
          <div className="mt-0.5 text-[10px] text-muted">主力净流入 · 近{limit}日 · 按需缓存</div>
        </div>
        <button
          type="button"
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending || query.isFetching}
          className="inline-flex shrink-0 items-center gap-1 rounded-btn border border-border bg-elevated px-2 py-1 text-[10px] text-secondary transition-colors hover:text-foreground disabled:opacity-50"
          title="从东方财富更新该股资金流"
        >
          {refresh.isPending || query.isFetching
            ? <Loader2 className="h-3 w-3 animate-spin" />
            : <RefreshCw className="h-3 w-3" />}
          更新
        </button>
      </div>

      {query.isLoading ? (
        <div className="flex min-h-0 flex-1 items-center justify-center gap-2 text-xs text-muted">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          加载资金流…
        </div>
      ) : validRows.length === 0 ? (
        <div className="flex min-h-0 flex-1 flex-col items-center justify-center rounded-lg border border-dashed border-border bg-elevated/20 px-4 text-center">
          <WalletCards className="h-6 w-6 text-muted/60" />
          <div className="mt-2 text-[11px] text-secondary">尚未缓存该股资金流</div>
          <div className="mt-1 text-[10px] leading-relaxed text-muted">点击后按需获取东财公开历史资金流，并保存到本地。</div>
          <button
            type="button"
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending}
            className="mt-3 inline-flex items-center gap-1.5 rounded-btn border border-sky-400/30 bg-sky-500/10 px-3 py-1.5 text-[11px] text-sky-700 hover:bg-sky-500/15 disabled:opacity-50 dark:text-sky-300"
          >
            {refresh.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            获取资金流
          </button>
          {(query.isError || refresh.isError) && (
            <div className="mt-2 text-[10px] text-danger">
              {(refresh.error as Error)?.message || (query.error as Error)?.message || '资金流获取失败'}
            </div>
          )}
        </div>
      ) : (
        <>
          {refresh.isError && (
            <div className="mb-2 rounded-md border border-danger/20 bg-danger/5 px-2 py-1 text-[10px] text-danger">
              更新失败：{(refresh.error as Error)?.message || '请稍后重试'}
            </div>
          )}
          <div className="mb-2 grid grid-cols-2 gap-1.5">
            <Metric label={`最新 · ${latest.date.slice(5)}`} value={flowText(latest.main_net)} tone={flowTone(latest.main_net)} />
            <Metric label="主力净占比" value={pctText(latest.main_net_pct)} tone={flowTone(latest.main_net_pct)} />
            <Metric label="近5日累计" value={flowText(flow5)} tone={flowTone(flow5)} />
            <Metric label="近20日累计" value={flowText(flow20)} tone={flowTone(flow20)} />
          </div>

          <div className="mb-1 flex items-center justify-between gap-2 text-[9px]">
            <span className={flowTone(flow5)}>{direction}</span>
            {streak && <span className="text-muted">{streak}</span>}
          </div>

          <div className="relative min-h-0 flex-1">
            <div ref={chartElRef} className="h-full w-full" aria-label="个股主力资金流趋势图" />
          </div>

          <div className="mt-1 flex items-center justify-between gap-2 text-[9px] text-muted/80">
            <span>{sourceLabel} · 单位元</span>
            <span>红流入 · 绿流出</span>
          </div>
        </>
      )}
    </section>
  )
}
