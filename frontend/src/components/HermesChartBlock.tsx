import { useEffect, useMemo, useRef } from 'react'
import * as echarts from 'echarts'
import { normalizeHermesChartPoints, type HermesChartSpec } from '@/lib/hermesRichContent'
import { useChartChrome } from '@/lib/theme'

function formatValue(value: number, unit?: string) {
  const abs = Math.abs(value)
  const text = abs >= 1e8
    ? `${(value / 1e8).toFixed(2)}亿`
    : abs >= 1e4
      ? `${(value / 1e4).toFixed(2)}万`
      : value.toLocaleString('zh-CN')
  return unit ? `${text}${unit}` : text
}

export function HermesChartBlock({ spec }: { spec: HermesChartSpec }) {
  const chrome = useChartChrome()
  const elRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)
  const points = useMemo(() => normalizeHermesChartPoints(spec), [spec])
  const title = typeof spec.title === 'string' && spec.title.trim() ? spec.title.trim() : '图表'
  const template = [spec.template, spec.view].filter(Boolean).join(' / ')
  const chartType = spec.chartType === 'line' || spec.view === 'line' ? 'line' : 'bar'

  const option = useMemo(() => {
    if (!points.length) return null
    return {
      animation: false,
      backgroundColor: 'transparent',
      grid: { left: 8, right: 12, top: 12, bottom: 28, containLabel: true },
      tooltip: {
        trigger: 'axis',
        backgroundColor: chrome.tooltipBg,
        borderColor: chrome.tooltipBorder,
        textStyle: { color: chrome.text, fontSize: 11 },
        formatter: (params: Array<{ axisValue?: string; value?: number }>) => {
          const item = Array.isArray(params) ? params[0] : params
          return `${item?.axisValue ?? ''}<br/>${formatValue(Number(item?.value ?? 0), spec.unit)}`
        },
      },
      xAxis: {
        type: 'category',
        data: points.map(point => point.label),
        axisLabel: { color: chrome.muted, fontSize: 10 },
        axisLine: { lineStyle: { color: chrome.border } },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        splitNumber: 3,
        axisLabel: {
          color: chrome.muted,
          fontSize: 10,
          formatter: (value: number) => formatValue(value, spec.unit),
        },
        splitLine: { lineStyle: { color: chrome.grid } },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      series: [{
        type: chartType,
        data: points.map(point => point.value),
        barMaxWidth: 22,
        itemStyle: { color: '#8B5CF6', borderRadius: chartType === 'bar' ? [3, 3, 0, 0] : 0 },
        lineStyle: { width: 2, color: '#8B5CF6' },
        symbol: 'circle',
        symbolSize: 6,
      }],
    }
  }, [chartType, chrome, points, spec.unit])

  useEffect(() => {
    const element = elRef.current
    if (!element || !option) return
    let chart = chartRef.current
    if (!chart) {
      chart = echarts.init(element, undefined, { renderer: 'canvas' })
      chartRef.current = chart
    }
    chart.setOption(option, true)
    if (typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(() => chart?.resize())
    observer.observe(element)
    return () => observer.disconnect()
  }, [option])

  useEffect(() => () => {
    chartRef.current?.dispose()
    chartRef.current = null
  }, [])

  return (
    <aside
      aria-label="Hermes 图表块"
      className="overflow-hidden rounded-btn border border-border bg-base/40"
    >
      <div className="flex flex-wrap items-start justify-between gap-2 border-b border-border/70 px-3 py-2">
        <div>
          <div className="text-xs font-medium text-foreground">{title}</div>
          <div className="mt-0.5 text-[11px] text-muted">
            {template || '受控图表'}
            {spec.as_of ? ` · as_of ${spec.as_of}` : ''}
            {spec.source ? ` · ${spec.source}` : ''}
          </div>
        </div>
      </div>
      {points.length ? (
        <div ref={elRef} className="h-52 w-full" role="img" aria-label={title} />
      ) : (
        <div className="px-3 py-4 text-xs text-muted">
          已识别图表说明，但没有可绘制的数值点，因此不编造图形。
        </div>
      )}
    </aside>
  )
}
