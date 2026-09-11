import { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { type KlineRow, type FinancialMetricRecord } from '@/lib/api'
import { klineDailyQueryOptions, klineMinuteQueryOptions, klineMinuteRangeQueryOptions, DEFAULT_INTRADAY_DAYS } from '@/lib/kline'
import { StockInfoBar } from '@/components/StockInfoBar'
import { StockDailyKChart, getDefaultRange, toOHLC, type StockDailyKChartResult } from '@/components/StockDailyKChart'
import { StockIntradayChart } from '@/components/StockIntradayChart'
import { ChipDistributionPanel } from '@/components/ChipDistributionPanel'
import { TechnicalSignalSummary } from '@/components/TechnicalSignalSummary'
import { financialMetricsQueryOptions, useFinancialMetrics } from '@/lib/useFinancials'
import { useCapabilities } from '@/lib/useSharedQueries'
import { scheduleNeighborPrefetch } from '@/lib/neighborPrefetch'
import type { ChartMarker, ChartPriceLine, ChartRange } from '@/components/EChartsCandlestick'
import {
  loadInfoFields,
  saveInfoFields,
  buildInfoExtColumnsParam,
  type ColumnConfig,
} from '@/lib/stock-info-fields'

interface Props {
  symbol: string
  height?: number
  showIntraday?: boolean
  /** 显示筹码分布侧栏（本地日K近似筹码峰） */
  showChips?: boolean
  className?: string
  /** 当用户点击蜡烛选中日期时回调（用于外部自动开启分时图）。 */
  onSelectDate?: (date: string) => void
  /** 外部传入的日期范围 */
  dateRange?: { start: string; end: string }
  /** 初始视窗显示的 K 线数量；用于让日期范围快捷项同步控制图表缩放 */
  visibleBars?: number | 'all'
  markers?: ChartMarker[]
  ranges?: ChartRange[]
  priceLines?: ChartPriceLine[]
  showLimitMarkers?: boolean
  showMarkerToggle?: boolean
  /** 加监控回调 (传入后信息条显示 RadioTower 图标) */
  onMonitor?: () => void
  /** 加自选 (传入后信息条显示 Star 图标) */
  inWatchlist?: boolean
  onToggleWatchlist?: () => void
  prefetchSymbols?: string[]
  intradayDays?: number
  dailyKlineFlex?: string
}

export { getDefaultRange }

export function StockPanel({
  symbol,
  height = 520,
  showIntraday = true,
  showChips = false,
  className,
  onSelectDate,
  dateRange: externalDateRange,
  visibleBars,
  markers,
  ranges,
  priceLines,
  showLimitMarkers = true,
  showMarkerToggle = true,
  onMonitor,
  inWatchlist,
  onToggleWatchlist,
  prefetchSymbols,
  intradayDays = DEFAULT_INTRADAY_DAYS,
  dailyKlineFlex = 'flex-1',
}: Props) {
  const [linkedPrice, setLinkedPrice] = useState<number | null>(null)
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [hoveredDate, setHoveredDate] = useState<string | null>(null)
  const [dailyResult, setDailyResult] = useState<StockDailyKChartResult | null>(null)
  // 信息条指标配置提升到此层：同时供 StockInfoBar 渲染与 StockDailyKChart 请求 ext 数据
  const [fields, setFields] = useState<ColumnConfig[]>(loadInfoFields)
  const extColumns = useMemo(() => buildInfoExtColumnsParam(fields), [fields])

  const handleFieldsChange = useCallback((next: ColumnConfig[]) => {
    setFields(next)
    saveInfoFields(next)
  }, [])

  // 财务指标：信息条含财务字段，且 TickFlow Expert 或本地/public 财务可用时才请求
  const { data: caps } = useCapabilities()
  const hasFinancialCap = Boolean(
    caps?.features?.financial?.available
    || caps?.financial?.available
    || caps?.capabilities?.['financial'] != null
  )
  const hasFinanceField = useMemo(
    () => fields.some(f => f.visible && f.source.type === 'builtin'
      && ['eps', 'bps', 'roe', 'pe_ttm', 'pb', 'gross_margin', 'net_margin', 'debt_ratio', 'revenue_yoy', 'net_income_yoy'].includes(f.source.key)),
    [fields],
  )
  const financials = useFinancialMetrics(hasFinanceField && hasFinancialCap ? symbol : undefined)

  const defaultDateRange = getDefaultRange()
  const rangeStart = externalDateRange?.start ?? defaultDateRange.start
  const rangeEnd = externalDateRange?.end ?? defaultDateRange.end
  const dateRange = useMemo(() => ({ start: rangeStart, end: rangeEnd }), [rangeStart, rangeEnd])

  // 日K查询由本组件持有 (与 StockDailyKChart 共享同一 cache key/配置, 只发一次请求)。
  // 信息条直接读 query data: 切股到已预取邻股时首帧即有数据, 配合 StockInfoBar 加载态占位,
  // 弹窗整体高度在切换瞬间不塌陷 (不抖动)。
  const kline = useQuery({ ...klineDailyQueryOptions(symbol, dateRange, extColumns), enabled: !!symbol })
  const rawRows: KlineRow[] = kline.data?.rows ?? dailyResult?.rawRows ?? []
  // OHLC 视图用于日期选中/昨收价推导 (与图表侧同口径)
  const rows = useMemo(() => toOHLC(rawRows), [rawRows])
  const stockInfo = kline.data?.stock_info ?? dailyResult?.stockInfo
  const name = kline.data?.name ?? dailyResult?.name

  const handleDateClick = useCallback((date: string) => {
    setSelectedDate(date)
    onSelectDate?.(date)
  }, [onSelectDate])

  // 当前日K就绪后, 等可见查询空闲再串行预取邻股, 避免首屏争抢公网带宽。
  // 日K/分时预取 staleTime 30s 防来回切换重复请求; 成为当前股后 useQuery(staleTime=0) 立即后台刷新,
  // SSE 也只按焦点股精准失效, 实时性不受影响。财务指标与正式查询同 staleTime, 5min 内不重复拉取。
  // prefetchKey 按内容 join: 自选页 navList 随行情 tick 重建但邻股集合通常不变, 避免 effect 每次 tick 重跑。
  const qc = useQueryClient()
  const prefetchKey = prefetchSymbols?.join(',') ?? ''
  useEffect(() => {
    if (!symbol || !prefetchKey || !kline.isSuccess || kline.isPlaceholderData) return
    const tasks: Array<() => Promise<unknown>> = []
    for (const s of new Set(prefetchKey.split(',').filter(Boolean))) {
      if (s === symbol) continue
      let lastDate: string | undefined
      tasks.push(async () => {
        const res = await qc.fetchQuery({ ...klineDailyQueryOptions(s, dateRange, extColumns), staleTime: 30_000 })
        const date = res?.rows?.at(-1)?.date
        lastDate = date ? String(date).slice(0, 10) : undefined
      })
      // 独立排队, 切股/关闭后的日K响应不会继续级联分钟请求。
      tasks.push(async () => {
        if (lastDate) await qc.prefetchQuery({ ...klineMinuteQueryOptions(s, lastDate, true), staleTime: 30_000 })
      })
      if (hasFinanceField && hasFinancialCap) {
        tasks.push(() => qc.prefetchQuery(financialMetricsQueryOptions(s)))
      }
      tasks.push(() => qc.prefetchQuery({ ...klineMinuteRangeQueryOptions(s, intradayDays), staleTime: 30_000 }))
      tasks.push(() => qc.prefetchQuery({ ...klineMinuteQueryOptions(s, undefined, true), staleTime: 30_000 }))
    }
    return scheduleNeighborPrefetch(qc, symbol, tasks)
  }, [prefetchKey, symbol, dateRange, extColumns, hasFinanceField, hasFinancialCap, intradayDays, qc, kline.isSuccess, kline.isPlaceholderData])

  // symbol 变化时重置分时相关状态，避免切股后残留旧日期。
  // 日K信息直接读 query data (切股到已预取邻股首帧即有), 无需清空或门控。
  const prevSymbol = useRef<string | null>(symbol)
  useEffect(() => {
    if (prevSymbol.current === symbol) return
    prevSymbol.current = symbol
    setSelectedDate(null)
    setHoveredDate(null)
    setLinkedPrice(null)
  }, [symbol])

  // 当分时开启、无选中日期时：优先今天（公开分时只稳供当日），否则最新日K日期
  useEffect(() => {
    if (!showIntraday || selectedDate || rows.length === 0) return
    const today = new Date().toISOString().slice(0, 10)
    const hasToday = rows.some(r => r.date === today)
    setSelectedDate(hasToday ? today : rows[rows.length - 1].date)
  }, [showIntraday, selectedDate, rows])

  const selectedIdx = selectedDate ? rows.findIndex(r => r.date === selectedDate) : -1
  const selectedAnalysisDate = selectedDate ?? rows.at(-1)?.date ?? null
  const prevClose = selectedIdx > 0
    ? rows[selectedIdx - 1].close
    : rows.length >= 2
      ? rows[rows.length - 2].close
      : undefined
  if (!symbol) return null

  // 财务指标最新一期（metrics 按 period_end 排序，取首项）
  const financialMetrics: FinancialMetricRecord | undefined = financials.data?.data?.[0]

  return (
    <div className={className}>
      <StockInfoBar
        symbol={symbol}
        name={name}
        stockInfo={stockInfo}
        rows={rawRows}
        fields={fields}
        onFieldsChange={handleFieldsChange}
        financialMetrics={financialMetrics}
        onMonitor={onMonitor}
        inWatchlist={inWatchlist}
        onToggleWatchlist={onToggleWatchlist}
      />

      <TechnicalSignalSummary
        rows={rawRows}
        selectedDate={hoveredDate ?? selectedDate}
      />

      <div className="flex gap-3 items-start">
        <StockDailyKChart
          symbol={symbol}
          height={height}
          className={`${dailyKlineFlex} min-w-0`}
          dateRange={dateRange}
          markers={markers}
          ranges={ranges}
          priceLines={priceLines}
          showLimitMarkers={showLimitMarkers}
          showMarkerToggle={showMarkerToggle}
          linkedPrice={linkedPrice}
          onDateClick={handleDateClick}
          onDateHover={setHoveredDate}
          onDataChange={setDailyResult}
          visibleBars={visibleBars ?? ((showIntraday || showChips) ? 40 : 60)}
          extColumns={extColumns}
        />

        {showIntraday && selectedDate && (
          <StockIntradayChart
            symbol={symbol}
            date={selectedDate}
            height={height}
            prevClose={prevClose}
            onPriceHover={setLinkedPrice}
            className="flex-1 min-w-0 border-l border-border pl-3"
          />
        )}

        {showChips && selectedAnalysisDate && (
          <ChipDistributionPanel
            symbol={symbol}
            height={height}
            asOf={selectedAnalysisDate}
            linkedPrice={linkedPrice}
            className="w-[17.5rem] shrink-0 border-l border-border pl-3"
          />
        )}
      </div>
    </div>
  )
}
