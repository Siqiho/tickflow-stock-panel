import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { useQuoteStream } from '@/lib/useQuoteStream'
import { ToastContainer } from '@/components/Toast'
import { AlertToastContainer } from '@/components/AlertToast'
import { AiAnalysisHost } from '@/components/financials/AiAnalysisHost'
import { AiReportBubble } from '@/components/financials/AiReportBubble'
import { StockAnalysisHost } from '@/components/stock-analysis/StockAnalysisHost'
import { StockAnalysisBubble } from '@/components/stock-analysis/StockAnalysisBubble'
import {
  useCapabilities,
  useSettings,
  usePreferences,
  useQuoteStatus,
  useVersion,
} from '@/lib/useSharedQueries'
import {
  useToggleRealtimeQuotes,
} from '@/lib/useSharedMutations'
import { QK } from '@/lib/queryKeys'
import { tierRank } from '@/lib/capability-labels'
import {
  Star,
  ScanSearch,
  History,
  FileText,
  Settings,
  Key,
  Database,
  Loader2,
  LayoutDashboard,
  Tags,
  TrendingUp,
  Flame,
  BarChart3,
  Sparkles,
  Layers3,
  Landmark,
  Cable,
  RadioTower,
  CheckCircle2,
  BookOpenCheck,
  Menu,
  Moon,
  Sun,
  X,
} from 'lucide-react'
import { Logo } from './Logo'
import { api, type IndexQuote } from '@/lib/api'
import { cn } from '@/lib/cn'
import { setCurrentTotal as setAlertTotal, useUnreadAlerts } from '@/lib/monitorBadge'
import { useRuntimeRouteLogger } from '@/lib/runtimeLogger'
import { useTheme, useThemeSync } from '@/lib/theme'

// 品牌色 — 只用于 logo / brand 区域,不影响功能语义色
const BRAND = '#8B5CF6'

const CORE_INDEXES = [
  { symbol: '000001.SH', name: '上证指数' },
  { symbol: '399001.SZ', name: '深证成指' },
  { symbol: '399006.SZ', name: '创业板指' },
  { symbol: '000680.SH', name: '科创综指' },
] as const

type CoreIndex = (typeof CORE_INDEXES)[number]

const nav = [
  { to: '/',                label: '看板',     icon: LayoutDashboard },
  { to: '/watchlist',  label: '自选',   icon: Star },
  { to: '/screener',   label: '策略',   icon: ScanSearch },
  { to: '/backtest',   label: '回测',   icon: History },
  { to: '/stock-analysis',    label: '个股分析', icon: TrendingUp },
  { to: '/limit-ladder', label: '连板梯队', icon: Flame },
  { to: '/concept-analysis', label: '概念分析', icon: Layers3 },
  { to: '/industry-analysis', label: '行业分析', icon: Landmark },
  { to: '/financials', label: '财务分析', icon: FileText },
  { to: '/monitor', label: '监控中心', icon: RadioTower },
  { to: '/review',      label: '复盘',   icon: BookOpenCheck },
  { to: '/indices', label: '指数', icon: BarChart3 },
  { to: '/trading', label: '交易', icon: Cable },
  { to: '/data',       label: '数据',   icon: Database },
] as const

function fmtIndexValue(v: number | null | undefined) {
  if (v == null || Number.isNaN(Number(v))) return '--'
  return Number(v).toFixed(2)
}

function fmtIndexPct(v: number | null | undefined) {
  if (v == null || Number.isNaN(Number(v))) return '--'
  return `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(2)}%`
}

function indexPctClass(v: number | null | undefined) {
  if (v == null || Number.isNaN(Number(v))) return 'text-muted'
  const n = Number(v)
  if (n === 0) return 'text-foreground'
  return n > 0 ? 'text-bull' : 'text-bear'
}

/** 监控中心未读徽标 — 仅在非监控页且有未读时显示。 */
function MonitorBadge({ active }: { active: boolean }) {
  const unread = useUnreadAlerts()
  // 尊重用户设置: 可在菜单设置里关闭数字提示
  const badgeEnabled = (() => {
    try { return localStorage.getItem('monitor_badge_enabled') !== '0' } catch { return true }
  })()
  if (active || unread <= 0 || !badgeEnabled) return null
  return (
    <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[9px] font-bold text-white animate-pulse">
      {unread > 99 ? '99+' : unread}
    </span>
  )
}

function SidebarIndexQuotes({
  rows,
  items,
  onNavigate,
}: {
  rows: IndexQuote[] | undefined
  items: CoreIndex[]
  onNavigate?: () => void
}) {
  if (items.length === 0) return null
  const quoteBySymbol = new Map((rows ?? []).map(q => [q.symbol, q]))
  return (
    <div className="mt-2 grid grid-cols-2 gap-1.5">
      {items.map(item => {
        const q = quoteBySymbol.get(item.symbol)
        const value = q?.last_price ?? q?.close
        const pct = q?.change_pct
        return (
          <NavLink
            key={item.symbol}
            to={`/indices?symbol=${encodeURIComponent(item.symbol)}`}
            onClick={onNavigate}
            className="block rounded bg-elevated/60 px-2 py-1.5 transition-colors hover:bg-elevated"
            title={`${item.name} ${item.symbol}`}
          >
            <div className="flex items-center justify-between gap-1">
              <span className="text-[10px] text-secondary">{item.name}</span>
              <span className={`text-[10px] font-mono ${indexPctClass(pct)}`}>{fmtIndexPct(pct)}</span>
            </div>
            <div className="mt-0.5 truncate font-mono text-[10px] text-foreground/80">
              {fmtIndexValue(value)}
            </div>
          </NavLink>
        )
      })}
    </div>
  )
}

// ===== 档位卡片 =====
function TierBadge({
  label,
  hasKey,
  onNavigate,
}: {
  label: string
  hasKey?: boolean
  onNavigate?: () => void
}) {
  const base = label.split(' ')[0].split('+')[0].toLowerCase()
  const isNone = base === 'none'

  const tierConfig: Record<string, {
    desc: string
    tagBg: React.CSSProperties
    dotStyle: React.CSSProperties
    labelTextStyle: React.CSSProperties
  }> = {
    none: {
      desc: '未配置 Key · 仅历史日K',
      tagBg: { background: 'rgba(113,113,122,0.15)' },
      dotStyle: { background: '#52525b' },
      labelTextStyle: { color: '#71717a' },
    },
    free: {
      desc: '基础日K · 自选实时',
      tagBg: { background: 'rgba(113,113,122,0.3)' },
      dotStyle: { background: '#71717a' },
      labelTextStyle: { color: '#a1a1aa' },
    },
    starter: {
      desc: '批量同步 · 行情池',
      tagBg: { background: 'rgba(59,130,246,0.2)' },
      dotStyle: { background: '#3b82f6' },
      labelTextStyle: { color: '#60a5fa' },
    },
    pro: {
      desc: '分钟K · 实时行情 · 盘口',
      tagBg: { background: 'linear-gradient(135deg, rgba(168,85,247,0.2), rgba(124,58,237,0.15))' },
      dotStyle: { background: 'linear-gradient(135deg, #a855f7, #7c3aed)' },
      labelTextStyle: { background: 'linear-gradient(135deg, #c084fc, #a855f7)', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' },
    },
    expert: {
      desc: 'WebSocket · 财务数据',
      tagBg: { background: 'linear-gradient(135deg, rgba(59,130,246,0.2), rgba(168,85,247,0.2), rgba(245,158,11,0.2))' },
      dotStyle: { background: 'linear-gradient(135deg, #3b82f6, #a855f7, #f59e0b)' },
      labelTextStyle: { background: 'linear-gradient(135deg, #60a5fa, #c084fc, #fbbf24)', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' },
    },
  }

  const t = tierConfig[base] || tierConfig.none
  // none 档显示英文「None」,无 label 时也显示「None」
  const displayLabel = isNone ? 'None' : (label || 'None')

  return (
    <NavLink
      to="/settings?tab=account"
      onClick={onNavigate}
      className="mt-2.5 group block -mx-2.5"
      title="API 设置"
    >
      <div className="relative overflow-hidden rounded-lg border border-blue-400/20 bg-gradient-to-br from-blue-500/[0.12] via-surface to-surface px-3 py-2 transition-all hover:border-blue-400/35 hover:from-blue-500/[0.16]">
        <div className="absolute -right-5 -top-6 h-14 w-14 rounded-full bg-blue-500/10 blur-2xl" />
        <div className="relative flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-blue-400/10 text-blue-500 dark:text-blue-300 ring-1 ring-blue-400/20">
            <Key className="h-3.5 w-3.5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-medium text-foreground">TickFlow</span>
              <span
                className="h-1.5 w-1.5 rounded-full"
                style={{ ...t.dotStyle, ...(base === 'expert' ? { animation: 'pulse 2s infinite' } : {}) }}
              />
            </div>
            <div className="mt-0.5 truncate text-[10px] leading-tight text-muted">
              {isNone && !hasKey ? '配置 Key 解锁更多能力' : t.desc}
            </div>
          </div>
          <span
            className="inline-flex h-[18px] max-w-[68px] shrink-0 items-center overflow-hidden rounded px-1.5 text-[10px] font-bold font-mono leading-none"
            style={t.tagBg}
          >
            <span className="truncate" style={t.labelTextStyle}>{displayLabel}</span>
          </span>
          <Settings className="h-3 w-3 shrink-0 text-muted group-hover:text-blue-500 dark:group-hover:text-blue-300 transition-colors" />
        </div>

      </div>
    </NavLink>
  )
}

function AIConfigBadge({
  configured,
  model,
  onNavigate,
}: {
  configured?: boolean
  model?: string
  onNavigate?: () => void
}) {
  return (
    <NavLink
      to="/settings?tab=ai"
      onClick={onNavigate}
      className="mt-2 group block -mx-2.5"
      title="AI 配置"
    >
      <div className="relative overflow-hidden rounded-lg border border-purple-400/20 bg-gradient-to-br from-purple-500/[0.12] via-surface to-surface px-3 py-2 transition-all hover:border-purple-400/35 hover:from-purple-500/[0.16]">
        <div className="absolute -right-5 -top-6 h-14 w-14 rounded-full bg-purple-500/10 blur-2xl" />
        <div className="relative flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-purple-400/10 text-purple-500 dark:text-purple-300 ring-1 ring-purple-400/20">
            <Sparkles className="h-3.5 w-3.5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-medium text-foreground">AI 配置</span>
              <span className={`h-1.5 w-1.5 rounded-full ${configured ? 'bg-bear' : 'bg-warning'}`} />
            </div>
            <div className="mt-0.5 truncate text-[10px] leading-tight text-muted">
              {configured ? (model || '已接入模型') : '接入策略生成模型'}
            </div>
          </div>
          <Settings className="h-3 w-3 text-muted group-hover:text-purple-500 dark:group-hover:text-purple-300 transition-colors" />
        </div>
      </div>
    </NavLink>
  )
}

function RealtimeSidebarControls({
  realtimeEnabled,
  isRunning,
  isTrading,
  isWatchlistMode,
  realtimeModeLabel,
  realtimeAllowed,
  isPending,
  onToggle,
  onSettings,
  showIndexQuotes,
  indexRows,
  indexItems,
  onNavigate,
  className,
}: {
  realtimeEnabled: boolean
  isRunning: boolean
  isTrading: boolean
  isWatchlistMode: boolean
  realtimeModeLabel: string
  realtimeAllowed: boolean
  isPending: boolean
  onToggle: (enabled: boolean) => void
  onSettings: () => void
  showIndexQuotes: boolean
  indexRows: IndexQuote[] | undefined
  indexItems: CoreIndex[]
  onNavigate?: () => void
  className?: string
}) {
  return (
    <div className={cn('shrink-0 border-t border-border px-3 py-2.5', className)}>
      <div className="flex items-center justify-between">
        <div className="flex min-w-0 items-center gap-2">
          <span className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${
            realtimeEnabled && isRunning && isTrading
              ? 'bg-accent animate-pulse'
              : realtimeEnabled
                ? 'bg-warning/60'
                : 'bg-muted'
          }`} />
          <span className="truncate text-xs text-secondary">
            实时行情 · {realtimeModeLabel}
          </span>
          <button
            type="button"
            onClick={onSettings}
            className="shrink-0 text-secondary transition-colors hover:text-foreground"
            title="实时监控设置"
            aria-label="实时监控设置"
          >
            <Settings className="h-3 w-3" />
          </button>
        </div>
        <button
          type="button"
          role="switch"
          aria-label="实时行情开关"
          aria-checked={realtimeEnabled}
          onClick={() => onToggle(!realtimeEnabled)}
          disabled={isPending || !realtimeAllowed}
          className={`relative inline-flex h-4 w-7 shrink-0 items-center rounded-full transition-colors duration-200 ${
            realtimeEnabled
              ? 'bg-accent shadow-[0_0_6px_rgba(59,130,246,0.3)]'
              : 'bg-elevated'
          } ${isPending || !realtimeAllowed ? 'opacity-50' : 'cursor-pointer'}`}
        >
          <span className={`inline-block h-3 w-3 rounded-full bg-white shadow-sm transition-transform duration-200 ${
            realtimeEnabled ? 'translate-x-[14px]' : 'translate-x-0.5'
          }`} />
        </button>
      </div>

      {realtimeEnabled && (
        <div className="mt-1.5 text-[10px] leading-snug">
          {isRunning && isTrading ? (
            <span className="text-accent">行情运行中{isWatchlistMode ? '（自选/公开源）' : ''}</span>
          ) : !isTrading ? (
            <span className="text-warning/70">非交易时段，将在交易时间自动开启</span>
          ) : null}
        </div>
      )}
      {isWatchlistMode && !realtimeEnabled && (
        <div className="mt-1.5 text-[10px] leading-snug text-muted">
          无 TickFlow Key 时使用公开源自选实时
        </div>
      )}
      {showIndexQuotes && !isWatchlistMode && (
        <SidebarIndexQuotes rows={indexRows} items={indexItems} onNavigate={onNavigate} />
      )}
    </div>
  )
}

export function Layout() {
  useRuntimeRouteLogger()
  useThemeSync()
  const { theme, isDark, toggleTheme } = useTheme()

  // ===== 共享 hooks (替代内联 useQuery) =====
  const { data: caps } = useCapabilities()
  const { data: settingsState } = useSettings()
  const { data: versionData } = useVersion()
  const { data: prefs } = usePreferences()
  // poll=true: 全局唯一开启条件轮询 (非交易时段 60s 兜底, 交易时段靠 SSE)
  const { data: quoteStatus } = useQuoteStatus({ poll: true })
  const { data: analysisMenus } = useQuery({
    queryKey: QK.analysisMenus,
    queryFn: api.analysisMenus,
  })

  // 数据同步状态轮询: 有活跃 job 时「数据」菜单项显示转圈
  const { data: pipelineJobs } = useQuery({
    queryKey: QK.pipelineJobs,
    queryFn: () => api.pipelineJobs(1),
    refetchInterval: (query) => (query.state.data?.active_id ? 2000 : 15000),
    refetchIntervalInBackground: true,
  })
  const isDataSyncing = !!pipelineJobs?.active_id

  // 数据同步完成的"瞬时反馈": isDataSyncing 从 true→false 时显示绿色对勾,
  // 闪烁约 3 秒后自动消失。
  const [dataSyncJustDone, setDataSyncJustDone] = useState(false)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const prevSyncingRef = useRef(false)
  const appShellRef = useRef<HTMLDivElement>(null)
  const mobileNavButtonRef = useRef<HTMLButtonElement>(null)
  const mobileNavCloseRef = useRef<HTMLButtonElement>(null)
  const mobileNavOverlayRef = useRef<HTMLDivElement>(null)
  const mobileNavDialogRef = useRef<HTMLElement>(null)
  useEffect(() => {
    // 仅在"刚结束"(true→false)且非首次挂载时触发
    if (prevSyncingRef.current && !isDataSyncing) {
      setDataSyncJustDone(true)
      const t = setTimeout(() => setDataSyncJustDone(false), 3000)
      prevSyncingRef.current = isDataSyncing
      return () => clearTimeout(t)
    }
    prevSyncingRef.current = isDataSyncing
  }, [isDataSyncing])

  useEffect(() => {
    if (!mobileNavOpen) return
    const triggerButton = mobileNavButtonRef.current
    let restoreTriggerFocus = true
    const dialog = mobileNavDialogRef.current
    const overlay = mobileNavOverlayRef.current
    const shell = appShellRef.current
    if (!dialog || !overlay || !shell) return

    const backgroundState = Array.from(shell.children)
      .filter(element => element !== overlay)
      .map(element => {
        const node = element as HTMLElement
        const state = {
          node,
          hadInert: node.hasAttribute('inert'),
          ariaHidden: node.getAttribute('aria-hidden'),
        }
        node.setAttribute('inert', '')
        node.setAttribute('aria-hidden', 'true')
        return state
      })

    const focusableSelector = [
      'a[href]',
      'button:not([disabled])',
      'input:not([disabled])',
      'select:not([disabled])',
      'textarea:not([disabled])',
      '[tabindex]:not([tabindex="-1"])',
    ].join(',')
    const getFocusable = () => Array.from(
      dialog.querySelectorAll<HTMLElement>(focusableSelector),
    ).filter(element => element.getAttribute('aria-hidden') !== 'true')

    mobileNavCloseRef.current?.focus()
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        setMobileNavOpen(false)
        return
      }
      if (event.key !== 'Tab') return

      const focusable = getFocusable()
      if (focusable.length === 0) {
        event.preventDefault()
        dialog.focus()
        return
      }
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const active = document.activeElement
      if (event.shiftKey && (active === first || !dialog.contains(active))) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && (active === last || !dialog.contains(active))) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', handleKeyDown)

    const desktopMedia = window.matchMedia?.('(min-width: 768px)')
    const handleBreakpointChange = (event: MediaQueryListEvent) => {
      if (event.matches) {
        restoreTriggerFocus = false
        setMobileNavOpen(false)
      }
    }
    desktopMedia?.addEventListener('change', handleBreakpointChange)
    if (desktopMedia?.matches) {
      restoreTriggerFocus = false
      setMobileNavOpen(false)
    }

    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      desktopMedia?.removeEventListener('change', handleBreakpointChange)
      for (const { node, hadInert, ariaHidden } of backgroundState) {
        if (!hadInert) node.removeAttribute('inert')
        if (ariaHidden == null) node.removeAttribute('aria-hidden')
        else node.setAttribute('aria-hidden', ariaHidden)
      }
      if (restoreTriggerFocus && triggerButton?.isConnected) triggerButton.focus()
    }
  }, [mobileNavOpen])

  const qc = useQueryClient()
  const navigate = useNavigate()
  const version = versionData?.version
  const realtimeEnabled = prefs?.realtime_quotes_enabled ?? false
  const indicesPinned = prefs?.indices_nav_pinned ?? true
  const sidebarIndexSymbols = prefs?.sidebar_index_symbols ?? CORE_INDEXES.map(p => p.symbol)
  const sidebarIndexes = CORE_INDEXES.filter(item => sidebarIndexSymbols.includes(item.symbol))
  // 卡片数据：固定显示时也拉取（即使实时行情关闭）
  const showSidebarQuotes = indicesPinned || realtimeEnabled
  const { data: sidebarIndexQuotes } = useQuery({
    queryKey: [...QK.indexQuotes, 'sidebar', sidebarIndexSymbols.join(',')] as const,
    queryFn: () => api.indexQuotes(sidebarIndexes.map(p => p.symbol)),
    enabled: showSidebarQuotes && sidebarIndexes.length > 0,
    placeholderData: (prev) => prev,
  })

  // SSE: 行情更新时自动刷新相关 queries + 告警通知
  useQuoteStream(realtimeEnabled, prefs?.sse_refresh_pages)

  const toggleQuote = useToggleRealtimeQuotes()
  const isRunning = quoteStatus?.running ?? false
  const isTrading = quoteStatus?.is_trading_hours ?? false
  const tier = tierRank(caps?.label ?? '')
  // none/free: 自选实时（公开源可兜底）；starter+: 全市场
  const isWatchlistMode = tier <= 0
  const realtimeModeLabel = isWatchlistMode ? '自选股' : '全市场'
  const quoteFeat = caps?.features?.quote ?? caps?.quote
  const realtimeAllowed = quoteFeat?.available ?? (caps ? caps.capabilities?.['quote.by_symbol'] != null : true)

  // 轮询触发记录总数 → 更新监控中心徽标 (每 15 秒)
  const alertsTotalQuery = useQuery({
    queryKey: ['alerts-total'],
    queryFn: () => api.alertsList({ days: 7, limit: 1 }),
    refetchInterval: 15000,
    refetchIntervalInBackground: true,
    select: (data) => data.total,
  })
  // 只在拿到真实总数时同步徽标 (避免 data=undefined 时传 0 重置 lastSeen)
  const alertsTotal = alertsTotalQuery.data
  useEffect(() => {
    if (alertsTotal != null) setAlertTotal(alertsTotal)
  }, [alertsTotal])

  // 合并内置页面 + 可见的扩展分析菜单
  const analysisNav = (analysisMenus?.items ?? [])
    .filter(m => m.visible)
    .map(m => ({ to: `/analysis/${m.id}`, label: m.label, icon: m.icon === 'tags' ? Tags : BarChart3 }))

  const allNav = [...nav, ...analysisNav]
  const savedOrder = prefs?.nav_order ?? []

  const navItems = savedOrder.length > 0
    ? (() => {
        const byTo = new Map(allNav.map(n => [n.to, n]))
        const ordered = savedOrder
          .map(id => byTo.get(id) ?? byTo.get(`/analysis/${id}`))
          .filter(Boolean)
        const seen = new Set(ordered.map(n => n!.to))
        return [...ordered as typeof allNav, ...allNav.filter(n => !seen.has(n.to))]
      })()
    : allNav

  const hiddenIds = new Set(prefs?.nav_hidden ?? [])
  const visibleNavItems = navItems.filter(n => !hiddenIds.has(n.to) && !hiddenIds.has(n.to.replace(/^\/analysis\//, '')))

  const handleToggle = async (enabled: boolean) => {
    // 开启时重新校验档位
    if (enabled) {
      const fresh = await qc.fetchQuery({
        queryKey: QK.capabilities,
        queryFn: api.capabilities,
      })
      const freshTier = tierRank(fresh.label ?? '')
      if (freshTier < 0) return
      if (freshTier === 0 && (prefs?.realtime_watchlist_symbols?.length ?? 0) === 0) {
        navigate('/watchlist')
        return
      }
    }
    await toggleQuote.mutateAsync(enabled)
    // 仅在交易时段立即获取一次行情
    if (enabled && isTrading) {
      api.intradayRefresh().catch(() => {})
    }
  }

  return (
    <div
      ref={appShellRef}
      data-testid="app-shell"
      className="h-screen grid grid-cols-1 grid-rows-[auto_1fr] md:grid-cols-[14rem_1fr] md:grid-rows-1 bg-base text-foreground overflow-hidden"
    >
      <header
        data-testid="mobile-header"
        className="flex h-14 items-center justify-between border-b border-border bg-surface px-4 md:hidden"
      >
        <div className="flex items-center gap-2.5">
          <Logo size={24} className="text-violet-500" />
          <div className="font-mono text-xs font-bold leading-tight tracking-[0.06em]">
            <div>one</div>
            <div>trading</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] text-muted">{version ?? ''}</span>
          <button
            ref={mobileNavButtonRef}
            type="button"
            onClick={() => setMobileNavOpen(true)}
            className="inline-flex h-10 w-10 items-center justify-center rounded-btn text-foreground/80 transition-colors hover:bg-elevated hover:text-foreground"
            aria-label="打开导航"
            aria-expanded={mobileNavOpen}
            aria-controls="mobile-navigation-dialog"
          >
            <Menu className="h-5 w-5" />
          </button>
        </div>
      </header>

      {mobileNavOpen && (
        <div
          ref={mobileNavOverlayRef}
          data-testid="mobile-navigation-backdrop"
          className="fixed inset-0 z-50 bg-black/45 backdrop-blur-[1px] md:hidden"
          onClick={event => {
            if (event.target === event.currentTarget) setMobileNavOpen(false)
          }}
        >
          <aside
            ref={mobileNavDialogRef}
            id="mobile-navigation-dialog"
            role="dialog"
            aria-modal="true"
            aria-label="移动导航"
            tabIndex={-1}
            className="relative flex h-full w-[min(20rem,calc(100vw-3rem))] flex-col border-r border-border bg-surface shadow-2xl"
          >
            <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
              <div className="flex items-center gap-2.5">
                <Logo size={24} className="text-violet-500" />
                <span className="font-mono text-xs font-bold tracking-[0.06em]">one-trading</span>
              </div>
              <button
                ref={mobileNavCloseRef}
                type="button"
                onClick={() => setMobileNavOpen(false)}
                className="inline-flex h-10 w-10 items-center justify-center rounded-btn text-foreground/80 transition-colors hover:bg-elevated hover:text-foreground"
                aria-label="关闭导航"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto">
              <div className="border-b border-border px-5 pb-3">
                <TierBadge
                  label={caps?.label ?? ''}
                  hasKey={settingsState?.mode !== 'none'}
                  onNavigate={() => setMobileNavOpen(false)}
                />
                <AIConfigBadge
                  configured={settingsState?.ai_configured ?? settingsState?.has_ai_key}
                  model={settingsState?.ai_model}
                  onNavigate={() => setMobileNavOpen(false)}
                />
              </div>

              <nav aria-label="移动端主导航" className="space-y-0.5 px-3 py-3">
                {visibleNavItems.map(({ to, label, icon: Icon }) => (
                  <NavLink
                    key={to}
                    to={to}
                    onClick={() => setMobileNavOpen(false)}
                    className={({ isActive }) =>
                      cn(
                        'flex items-center gap-3 rounded-btn px-3 py-2.5 text-sm transition-colors duration-150 ease-smooth',
                        isActive
                          ? 'bg-elevated font-medium text-foreground'
                          : 'text-foreground/80 hover:bg-elevated hover:text-foreground',
                      )
                    }
                  >
                    {({ isActive }) => (
                      <>
                        <Icon className="h-4 w-4 shrink-0" />
                        <span className="flex-1">{label}</span>
                        {(to === '/stock-analysis' || to === '/review') && (
                          <span className="inline-flex items-center rounded-full border border-amber-400/30 bg-amber-400/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-amber-400">
                            Beta
                          </span>
                        )}
                        {to === '/data' && isDataSyncing && (
                          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-accent" />
                        )}
                        {to === '/data' && !isDataSyncing && dataSyncJustDone && (
                          <CheckCircle2 className="h-3.5 w-3.5 shrink-0 animate-pulse text-bull" />
                        )}
                        {to === '/monitor' && <MonitorBadge active={isActive} />}
                      </>
                    )}
                  </NavLink>
                ))}
              </nav>

              <RealtimeSidebarControls
                realtimeEnabled={realtimeEnabled}
                isRunning={isRunning}
                isTrading={isTrading}
                isWatchlistMode={isWatchlistMode}
                realtimeModeLabel={realtimeModeLabel}
                realtimeAllowed={realtimeAllowed}
                isPending={toggleQuote.isPending}
                onToggle={handleToggle}
                onSettings={() => {
                  setMobileNavOpen(false)
                  navigate('/settings?tab=monitoring')
                }}
                showIndexQuotes={showSidebarQuotes}
                indexRows={sidebarIndexQuotes?.rows}
                indexItems={sidebarIndexes}
                onNavigate={() => setMobileNavOpen(false)}
                className="border-b"
              />
            </div>

            <div className="flex shrink-0 items-center gap-2 border-t border-border p-3">
              <NavLink
                to="/settings"
                onClick={() => setMobileNavOpen(false)}
                className="flex min-w-0 flex-1 items-center gap-3 rounded-btn px-3 py-2.5 text-sm text-foreground/80 transition-colors hover:bg-elevated hover:text-foreground"
              >
                <Settings className="h-4 w-4" />
                <span className="flex-1">设置</span>
                <span className="font-mono text-[10px] text-muted">{version ?? ''}</span>
              </NavLink>
              <button
                type="button"
                onClick={toggleTheme}
                className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-btn text-foreground/80 transition-colors hover:bg-elevated hover:text-foreground"
                aria-label={isDark ? '切换到浅色模式' : '切换到暗色模式'}
                aria-pressed={isDark}
              >
                {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              </button>
            </div>
          </aside>
        </div>
      )}

      <aside
        data-testid="desktop-sidebar"
        className="hidden border-r border-border bg-surface md:flex flex-col h-full min-h-0 overflow-hidden"
      >
        <div className="px-5 py-5 border-b border-border shrink-0">
          {/* Brand block — 原创 logo + 等宽 wordmark */}
          <div className="flex items-center gap-2.5">
            <Logo
              size={28}
              className="shrink-0 drop-shadow-[0_0_8px_rgba(139,92,246,0.5)]"
              style={{ color: BRAND }}
            />
            <div
              className="font-mono font-bold text-[13px] tracking-[0.06em] text-foreground leading-tight"
              style={{ textShadow: `0 0 10px ${BRAND}44` }}
            >
              <div>one</div>
              <div>trading</div>
            </div>
          </div>

          <div className="mt-2.5 text-[10px] uppercase tracking-[0.22em] text-secondary">
            Quant · Terminal
          </div>

          <div
            className="mt-3 h-px"
            style={{ background: `linear-gradient(90deg, ${BRAND}88, transparent 80%)` }}
          />

          <TierBadge
            label={caps?.label ?? ''}
            hasKey={settingsState?.mode !== 'none'}
          />
          <AIConfigBadge
            configured={settingsState?.ai_configured ?? settingsState?.has_ai_key}
            model={settingsState?.ai_model}
          />
        </div>

        <nav className="flex-1 min-h-0 overflow-y-auto px-2 py-3 space-y-0.5">
          {visibleNavItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 px-3 py-2 rounded-btn text-sm transition-colors duration-150 ease-smooth',
                  isActive
                    ? 'bg-elevated text-foreground font-medium'
                    : 'text-foreground/80 hover:bg-elevated hover:text-foreground',
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className="h-4 w-4 shrink-0" />
                  <span className="flex-1">{label}</span>
                  {/* 个股分析 Beta 标识 */}
                  {(to === '/stock-analysis' || to === '/review') && (
                    <span className="inline-flex items-center rounded-full border border-amber-400/30 bg-amber-400/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-amber-400 shrink-0">
                      Beta
                    </span>
                  )}
                  {/* 数据同步状态: 同步中转圈, 刚完成显示绿色对勾闪烁 3 秒 */}
                  {to === '/data' && isDataSyncing && (
                    <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-accent" />
                  )}
                  {to === '/data' && !isDataSyncing && dataSyncJustDone && (
                    <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-bull animate-pulse" />
                  )}
                  {/* 监控中心徽标: 仅非监控页且有未读时显示 */}
                  {to === '/monitor' && <MonitorBadge active={isActive} />}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <RealtimeSidebarControls
          realtimeEnabled={realtimeEnabled}
          isRunning={isRunning}
          isTrading={isTrading}
          isWatchlistMode={isWatchlistMode}
          realtimeModeLabel={realtimeModeLabel}
          realtimeAllowed={realtimeAllowed}
          isPending={toggleQuote.isPending}
          onToggle={handleToggle}
          onSettings={() => navigate('/settings?tab=monitoring')}
          showIndexQuotes={showSidebarQuotes}
          indexRows={sidebarIndexQuotes?.rows}
          indexItems={sidebarIndexes}
        />

        <div className="border-t border-border px-2 py-3 space-y-0.5 shrink-0">
          <div className="flex items-center gap-1">
            <NavLink
              to="/settings"
              className={({ isActive }) =>
                cn(
                  'flex min-w-0 flex-1 items-center justify-between gap-3 px-3 py-2 rounded-btn text-sm transition-colors duration-150 ease-smooth',
                  isActive
                    ? 'bg-elevated text-foreground font-medium'
                    : 'text-foreground/80 hover:bg-elevated hover:text-foreground',
                )
              }
            >
              <span className="flex items-center gap-3">
                <Settings className="h-4 w-4 shrink-0" />
                <span>设置</span>
              </span>
              <span className="font-mono text-[10px] text-muted/50 select-none">
                {version ?? ''}
              </span>
            </NavLink>
            <button
              type="button"
              onClick={toggleTheme}
              className={cn(
                'inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-btn transition-colors duration-150 ease-smooth',
                'text-foreground/80 hover:bg-elevated hover:text-foreground',
              )}
              title={isDark ? '切换到浅色模式' : '切换到暗色模式'}
              aria-label={isDark ? '切换到浅色模式' : '切换到暗色模式'}
              aria-pressed={isDark}
              data-theme={theme}
            >
              {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
          </div>
        </div>
      </aside>

      <motion.main
        data-testid="app-main"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
        className="h-full min-h-0 min-w-0 overflow-auto scrollbar-gutter-stable"
      >
        <Outlet />
      </motion.main>
      <ToastContainer />
      <AlertToastContainer />
      <AiAnalysisHost />
      <AiReportBubble />
      <StockAnalysisHost />
      <StockAnalysisBubble />
    </div>
  )
}
