import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { useEffect, useRef } from 'react'
import { Loader2 } from 'lucide-react'
import { api, type ChipDistribution } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { useChartChrome } from '@/lib/theme'

interface Props {
  symbol: string
  height?: number
  days?: number
  bins?: number
  className?: string
  /** 分时/日K联动价，用于在筹码轴上画参考线 */
  linkedPrice?: number | null
}

function pct(v: number | null | undefined, digits = 1): string {
  if (v == null || Number.isNaN(Number(v))) return '--'
  return `${(Number(v) * 100).toFixed(digits)}%`
}

function num(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(Number(v))) return '--'
  return Number(v).toFixed(digits)
}

function buildOption(data: ChipDistribution, chrome: { text: string; muted: string; grid: string; border: string; tooltipBg: string; tooltipBorder: string; crosshair: string; labelBg: string }, linkedPrice?: number | null): EChartsOption {
  const items = data.items ?? []
  // horizontal bars: y = price (low→high), x = ratio
  const prices = items.map(i => i.price)
  const ratios = items.map(i => Number(i.ratio || 0) * 100)
  const cur = data.current
  const avg = data.avg_cost
  const c70 = data.cost70
  const maxR = Math.max(...ratios, 0.01)

  const barColors = items.map(i => {
    const p = i.price
    if (p <= cur) return 'rgba(199,64,64,0.72)' // 获利
    return 'rgba(45,155,101,0.72)' // 套牢
  })

  const markLineData: any[] = []
  const nearestCat = (price: number) => {
    if (!prices.length) return String(price)
    let best = prices[0]
    let bestD = Math.abs(best - price)
    for (const p of prices) {
      const d = Math.abs(p - price)
      if (d < bestD) { best = p; bestD = d }
    }
    return String(best)
  }

  if (cur != null) {
    markLineData.push({
      yAxis: nearestCat(cur),
      label: {
        formatter: `现价 ${num(cur)}`,
        position: 'end',
        color: chrome.text,
        fontSize: 10,
        backgroundColor: chrome.labelBg,
        padding: [2, 4],
        borderRadius: 2,
      },
      lineStyle: { color: '#3B82F6', width: 1.2, type: 'solid' },
      symbol: 'none',
    })
  }
  if (avg != null) {
    markLineData.push({
      yAxis: nearestCat(avg),
      label: {
        formatter: `均成本 ${num(avg)}`,
        position: 'insideEndTop',
        color: chrome.muted,
        fontSize: 9,
      },
      lineStyle: { color: '#F59E0B', width: 1, type: 'dashed' },
      symbol: 'none',
    })
  }
  if (linkedPrice != null && Number.isFinite(linkedPrice) && linkedPrice > 0) {
    markLineData.push({
      yAxis: nearestCat(linkedPrice),
      label: {
        formatter: `联动 ${num(linkedPrice)}`,
        position: 'insideStartTop',
        color: chrome.muted,
        fontSize: 9,
      },
      lineStyle: { color: 'rgba(168,85,247,0.85)', width: 1, type: 'dotted' },
      symbol: 'none',
    })
  }

  // 70% 成本区用 markArea（category 轴用最接近的分箱价）
  const markArea =
    c70 && c70.low_price != null && c70.high_price != null
      ? {
          silent: true,
          itemStyle: { color: 'rgba(59,130,246,0.08)' },
          data: [
            [
              { yAxis: nearestCat(c70.low_price) },
              { yAxis: nearestCat(c70.high_price) },
            ],
          ],
        }
      : undefined

  const series: any[] = [
      {
        type: 'bar',
        data: ratios.map((v, i) => ({
          value: v,
          itemStyle: { color: barColors[i], borderRadius: [0, 2, 2, 0] },
        })),
        barWidth: '78%',
        markLine: {
          symbol: 'none',
          animation: false,
          data: markLineData,
          emphasis: { disabled: true },
        },
        markArea,
      },
    ]

  return {
    animation: false,
    backgroundColor: 'transparent',
    grid: { left: 48, right: 18, top: 12, bottom: 28 },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: chrome.crosshair } },
      backgroundColor: chrome.tooltipBg,
      borderColor: chrome.tooltipBorder,
      textStyle: { color: chrome.text, fontSize: 11 },
      formatter: (params: any) => {
        const p = Array.isArray(params) ? params[0] : params
        if (!p) return ''
        const price = Number(p.name)
        const ratio = Number(p.value)
        const item = items.find(i => Math.abs(i.price - price) < 1e-6)
        const side = price <= cur ? '获利区' : '套牢区'
        return [
          `<div style="font-family:ui-monospace,monospace">`,
          `<div>价格 <b>${num(price)}</b> · ${side}</div>`,
          `<div>占比 ${ratio.toFixed(2)}%</div>`,
          item ? `<div>筹码量 ${num(item.vol, 0)}</div>` : '',
          `</div>`,
        ].join('')
      },
    },
    xAxis: {
      type: 'value',
      max: maxR * 1.15,
      axisLabel: {
        color: chrome.muted,
        fontSize: 10,
        formatter: (v: number) => `${v.toFixed(v >= 10 ? 0 : 1)}%`,
      },
      splitLine: { lineStyle: { color: chrome.grid } },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'category',
      data: prices.map(p => String(p)),
      axisLabel: {
        color: chrome.muted,
        fontSize: 10,
        formatter: (v: string) => Number(v).toFixed(2),
        interval: Math.max(0, Math.floor(prices.length / 8) - 1),
      },
      axisLine: { lineStyle: { color: chrome.border } },
      axisTick: { show: false },
      splitLine: { show: false },
    },
    series,
  }
}

export function ChipDistributionPanel({
  symbol,
  height = 520,
  days = 120,
  bins = 80,
  className,
  linkedPrice = null,
}: Props) {
  const chrome = useChartChrome()
  const elRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)

  const q = useQuery({
    queryKey: QK.stockChips(symbol, days, bins),
    queryFn: () => api.stockChips(symbol, days, bins),
    enabled: !!symbol,
    staleTime: 60_000,
  })

  const data = q.data?.data
  const option = useMemo(
    () => (data ? buildOption(data, chrome, linkedPrice) : null),
    [data, chrome, linkedPrice],
  )

  useEffect(() => {
    const el = elRef.current
    if (!el) return
    let chart = chartRef.current
    if (!chart) {
      chart = echarts.init(el, undefined, { renderer: 'canvas' })
      chartRef.current = chart
    }
    if (option) chart.setOption(option, true)
    else chart.clear()
    const ro = new ResizeObserver(() => chart?.resize())
    ro.observe(el)
    return () => {
      ro.disconnect()
    }
  }, [option])

  useEffect(() => {
    return () => {
      chartRef.current?.dispose()
      chartRef.current = null
    }
  }, [])

  const profit = data?.profit_ratio ?? null
  const trapped = profit != null ? 1 - profit : null

  return (
    <div className={className} style={{ height, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
      <div className="mb-1.5 flex items-start justify-between gap-2 px-0.5">
        <div className="min-w-0">
          <div className="text-[11px] font-medium text-foreground">筹码分布</div>
          <div className="mt-0.5 text-[10px] text-muted">
            本地日K近似 · {days}日
            {data?.source ? ` · ${data.source === 'local_daily_derived' ? '推算' : data.source}` : ''}
          </div>
        </div>
        {data && (
          <div className="shrink-0 text-right font-mono text-[10px] leading-4 text-secondary">
            <div>均成本 <span className="text-foreground">{num(data.avg_cost)}</span></div>
            <div>中位 <span className="text-foreground">{num(data.median_cost)}</span></div>
          </div>
        )}
      </div>

      {data && (
        <div className="mb-1.5 grid grid-cols-2 gap-1.5">
          <div className="rounded-btn border border-border/70 bg-elevated/50 px-2 py-1">
            <div className="text-[9px] text-muted">获利盘</div>
            <div className="font-mono text-[12px] font-medium text-[#C74040]">{pct(profit)}</div>
          </div>
          <div className="rounded-btn border border-border/70 bg-elevated/50 px-2 py-1">
            <div className="text-[9px] text-muted">套牢盘</div>
            <div className="font-mono text-[12px] font-medium text-[#2D9B65]">{pct(trapped)}</div>
          </div>
          <div className="rounded-btn border border-border/70 bg-elevated/50 px-2 py-1 col-span-2">
            <div className="flex items-center justify-between gap-2 text-[9px] text-muted">
              <span>90%筹码</span>
              <span className="font-mono text-[10px] text-secondary">
                {num(data.cost90?.low_price)} ~ {num(data.cost90?.high_price)}
              </span>
            </div>
            <div className="mt-0.5 flex items-center justify-between gap-2 text-[9px] text-muted">
              <span>70%筹码</span>
              <span className="font-mono text-[10px] text-secondary">
                {num(data.cost70?.low_price)} ~ {num(data.cost70?.high_price)}
              </span>
            </div>
          </div>
        </div>
      )}

      <div className="relative min-h-0 flex-1">
        {q.isLoading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center gap-2 text-xs text-muted">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            计算筹码…
          </div>
        )}
        {q.isError && (
          <div className="absolute inset-0 z-10 flex items-center justify-center px-3 text-center text-xs text-danger">
            筹码计算失败（需本地日K）
          </div>
        )}
        {!q.isLoading && !q.isError && !data && (
          <div className="absolute inset-0 z-10 flex items-center justify-center text-xs text-muted">
            暂无筹码数据
          </div>
        )}
        <div ref={elRef} className="h-full w-full" />
      </div>

      <div className="mt-1 px-0.5 text-[9px] leading-snug text-muted/80">
        红=现价下获利筹码，绿=现价上套牢筹码。非交易所官方筹码峰。
      </div>
    </div>
  )
}
