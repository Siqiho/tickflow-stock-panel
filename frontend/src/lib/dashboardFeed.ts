/** 市场看板盘中快照钟：同一张总览整页换，历史日静止。 */

const SHANGHAI_TIME_ZONE = 'Asia/Shanghai'
const WEEKDAY_INDEX: Record<string, number> = {
  Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6,
}

export function shanghaiCalendarDate(now = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: SHANGHAI_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(now)
}

/** 与 QuoteService._is_trading_hours 对齐：周一到周五 09:15–11:35、12:55–15:05。 */
export function shanghaiIsTradingHours(now = new Date()): boolean {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: SHANGHAI_TIME_ZONE,
    weekday: 'short',
    hour: 'numeric',
    minute: 'numeric',
    hourCycle: 'h23',
  }).formatToParts(now)
  const weekday = WEEKDAY_INDEX[parts.find((part) => part.type === 'weekday')?.value ?? ''] ?? -1
  if (weekday < 1 || weekday > 5) return false
  const hour = Number(parts.find((part) => part.type === 'hour')?.value)
  const minute = Number(parts.find((part) => part.type === 'minute')?.value)
  if (!Number.isFinite(hour) || !Number.isFinite(minute)) return false
  const t = hour * 60 + minute
  return (t >= 9 * 60 + 15 && t <= 11 * 60 + 35) || (t >= 12 * 60 + 55 && t <= 15 * 60 + 5)
}

export function dashboardFeedStatus(input: {
  viewedDate?: string | null
  today?: string
  dataMode?: string | null
  quoteRunning?: boolean
  isTradingHours?: boolean | null
  now?: Date
}): { live: boolean; label: '实时' | '非实时' | '历史'; showAge: boolean } {
  const now = input.now ?? new Date()
  const today = input.today ?? shanghaiCalendarDate(now)
  const viewed = input.viewedDate || ''
  const viewingToday = viewed !== '' && viewed === today
  if (!viewingToday) {
    return { live: false, label: '历史', showAge: false }
  }
  const inSession = input.now
    ? shanghaiIsTradingHours(input.now)
    : (input.isTradingHours ?? shanghaiIsTradingHours(now))
  const live = input.dataMode === 'intraday_snapshot'
    && !!input.quoteRunning
    && inSession
  return { live, label: live ? '实时' : '非实时', showAge: live }
}

export function formatQuoteAge(ms?: number | null): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${Math.round(ms)}ms`
  const seconds = Math.round(ms / 1000)
  if (seconds < 60) return `${seconds}s`
  return `${Math.floor(seconds / 60)}m${seconds % 60}s`
}

export function formatDashboardFeedClock(input: {
  live: boolean
  showAge: boolean
  intervalS?: number | null
  ageMs?: number | null
}): string {
  if (!input.showAge) return '—'
  const age = formatQuoteAge(input.ageMs)
  const interval = input.intervalS
  if (input.live && interval != null && interval > 0) {
    const label = Number.isInteger(interval) ? String(interval) : interval.toFixed(1)
    return `每 ${label} 秒 · 已过 ${age}`
  }
  return age
}

export function isLiveSnapshotQueryKey(queryKey: readonly unknown[], today = shanghaiCalendarDate()): boolean {
  const asOf = queryKey[1]
  return asOf == null || asOf === 'latest' || asOf === today
}

export function liveOverviewRefetchMs(input: {
  live: boolean
  intervalS?: number | null
}): number | false {
  if (!input.live) return false
  const seconds = input.intervalS != null && input.intervalS > 0 ? input.intervalS : 15
  return Math.round(seconds * 1000)
}

/** 标题栏「刷新」要重读的看板模块。不含官方池、脉搏外连更新、资金流 POST。 */
export const DASHBOARD_MODULE_QUERY_PREFIXES = [
  'overview-market',
  'quote-status',
  'index-quotes',
  'limit-ladder',
  'market-pulse',
  'index-minute',
  'fund-flow-boards',
  'fund-flow-concepts',
  'fund-flow-boards-window',
  'fund-flow-concepts-window',
  'fund-flow-board-history',
  'fund-flow-board-intraday',
  'alerts',
  'data-status',
] as const

export function invalidateDashboardModules(queryClient: {
  invalidateQueries: (filters: { predicate: (query: { queryKey: readonly unknown[] }) => boolean }) => Promise<unknown>
}): Promise<unknown[]> {
  return Promise.all(
    DASHBOARD_MODULE_QUERY_PREFIXES.map((prefix) =>
      queryClient.invalidateQueries({
        predicate: (query) => String(query.queryKey[0] ?? '') === prefix
          || String(query.queryKey[0] ?? '').startsWith(`${prefix}-`),
      }),
    ),
  )
}
