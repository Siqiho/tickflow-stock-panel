import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { HermesPageAgentHost } from '@/components/HermesPageAgentHost'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { useQuoteStream } from '@/lib/useQuoteStream'
import { ToastContainer } from '@/components/Toast'
import { AlertToastContainer } from '@/components/AlertToast'
import { AiAnalysisHost } from '@/components/financials/AiAnalysisHost'
import { AiReportBubble } from '@/components/financials/AiReportBubble'
import { StockAnalysisHost } from '@/components/stock-analysis/StockAnalysisHost'
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
  FileText,
  Settings,
  Database,
  Loader2,
  LayoutDashboard,
  Tags,
  TrendingUp,
  Flame,
  Gauge,
  BarChart3,
  Sparkles,
  Layers3,
  Landmark,
  Cable,
  CheckCircle2,
  BookOpenCheck,
  Menu,
  Moon,
  Sun,
  X,
  UsersRound,
  Newspaper,
} from 'lucide-react'
import { Logo } from './Logo'
import { api, type IndexQuote } from '@/lib/api'
import { cn } from '@/lib/cn'
import { findDataSource } from '@/lib/dataSources'
import { setCurrentTotal as setAlertTotal, useUnreadAlerts } from '@/lib/monitorBadge'
import { setRuntimeLogUploadEnabled, useRuntimeRouteLogger } from '@/lib/runtimeLogger'
import { useTheme, useThemeSync } from '@/lib/theme'
import {
  applySavedNavOrder,
  builtinSidebarItems,
  isCatalogEntryVisible,
  isGroupNavPath,
  isPathInNavGroup,
  permissionFromSettings,
  pinAdminBeforeData,
  TRADE_PATH,
} from '@/lib/navGroups'

// 品牌色 — 只用于 logo / brand 区域,不影响功能语义色
const BRAND = '#8B5CF6'

const CORE_INDEXES = [
  { symbol: '000001.SH', name: '上证指数' },
  { symbol: '399001.SZ', name: '深证成指' },
  { symbol: '399006.SZ', name: '创业板指' },
  { symbol: '000680.SH', name: '科创综指' },
] as const

type CoreIndex = (typeof CORE_INDEXES)[number]

const NAV_ICONS = {
  '/': LayoutDashboard,
  '/ai': Sparkles,
  '/watchlist': Star,
  '/quant': ScanSearch,
  '/stock-analysis': TrendingUp,
  '/limit-ladder': Flame,
  '/concept-analysis': Layers3,
  '/industry-analysis': Landmark,
  '/financials': FileText,
  '/trade': Cable,
  '/regime': Gauge,
  '/review': BookOpenCheck,
  '/indices': BarChart3,
  '/admin/users': UsersRound,
  '/data': Database,
  '/news': Newspaper,
} as const

function fmtIndexValue(v: number | null | undefined) {
  if (v == null || Number.isNaN(Number(v))) return '--'
  return Number(v).toFixed(2)
}

function fmtIndexPct(v: number | null | undefined) {
  if (v == null || Number.isNaN(Number(v))) return '--'
  return `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(2)}%`
}

/**
 * 组入口不能用 NavLink：RR 6.30.3 用内部 isActive 决定 aria-current，
 * `/quant` 对不上 `/screener`，传入 aria-current="page" 仍会被写成 undefined。
 * 普通叶子继续走 NavLink，保留 `/` 精确匹配和 `/ai` → `/ai/hermes` 前缀匹配。
 */
function AppNavLink({
  to,
  onClick,
  className,
  children,
}: {
  to: string
  onClick?: () => void
  className: (active: boolean) => string
  children: ReactNode
}) {
  const { pathname } = useLocation()
  if (isGroupNavPath(to)) {
    const active = isPathInNavGroup(pathname, to)
    return (
      <Link
        to={to}
        onClick={onClick}
        aria-current={active ? 'page' : undefined}
        className={className(active)}
      >
        {children}
      </Link>
    )
  }
  return (
    <NavLink to={to} onClick={onClick} className={({ isActive }) => className(isActive)}>
      {children}
    </NavLink>
  )
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

function RealtimeSidebarControls({
  realtimeEnabled,
  isRunning,
  isTrading,
  isWatchlistMode,
  realtimeModeLabel,
  realtimeProviderName,
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
  realtimeProviderName?: string | null
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
            实时行情 · {realtimeProviderName || realtimeModeLabel}
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
  const location = useLocation()
  const navPerm = permissionFromSettings(settingsState)
  const isAdmin = navPerm.isAdmin
  const { data: versionData } = useVersion()
  const { data: prefs } = usePreferences()
  const { data: dataSources } = useQuery({
    queryKey: QK.dataSources,
    queryFn: api.dataSources,
  })
  // poll=true: 全局唯一开启条件轮询 (非交易时段 60s 兜底, 交易时段靠 SSE)
  const { data: quoteStatus } = useQuoteStatus({ poll: true })
  const { data: analysisMenus } = useQuery({
    queryKey: QK.analysisMenus,
    queryFn: api.analysisMenus,
  })

  useEffect(() => {
    if (settingsState) setRuntimeLogUploadEnabled(isAdmin)
  }, [isAdmin, settingsState])

  // 数据同步状态轮询: 有活跃 job 时「数据」菜单项显示转圈
  const { data: pipelineJobs } = useQuery({
    queryKey: QK.pipelineJobs,
    queryFn: () => api.pipelineJobs(1),
    enabled: isAdmin,
    refetchInterval: (query) => (query.state.data?.active_id ? 2000 : 15000),
    refetchIntervalInBackground: true,
  })
  const isDataSyncing = !!pipelineJobs?.active_id

  // 数据同步完成的"瞬时反馈": isDataSyncing 从 true→false 时显示绿色对勾,
  // 闪烁约 3 秒后自动消失。
  const [dataSyncJustDone, setDataSyncJustDone] = useState(false)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [pageAgentOpen, setPageAgentOpen] = useState(false)
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
  // 插件/自定义源显示源名, tickflow 不显示
  const realtimeProvider = prefs?.realtime_data_provider
  const realtimeProviderName = realtimeProvider && realtimeProvider !== 'tickflow'
    ? (findDataSource(dataSources, realtimeProvider)?.display_name || realtimeProvider)
    : null
  const quoteFeat = caps?.features?.quote ?? caps?.quote
  const realtimeAllowed = quoteFeat?.available ?? (caps ? caps.capabilities?.['quote.by_symbol'] != null : true)

  // 轮询触发记录总数 → 更新监控中心徽标 (每 15 秒)
  const alertsTotalQuery = useQuery({
    queryKey: ['alerts-total'],
    queryFn: () => api.alertsList({ days: 7, limit: 1 }),
    enabled: isAdmin,
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

  const baseNav = builtinSidebarItems()
    .filter(item => !item.adminOnly || (navPerm.settingsReady && navPerm.isAdmin))
    .map(item => ({
      to: item.to,
      label: item.label,
      icon: NAV_ICONS[item.to as keyof typeof NAV_ICONS] ?? BarChart3,
      beta: item.beta,
    }))
  const allNav = [...baseNav, ...analysisNav]
  const hiddenIds = new Set(prefs?.nav_hidden ?? [])
  const orderedNav = applySavedNavOrder(
    allNav.map(item => ({ ...item, id: item.to })),
    prefs?.nav_order ?? [],
  )
  const visibleNavItems = orderedNav.filter(item => (
    isCatalogEntryVisible(item.to, hiddenIds, navPerm, item.to === '/admin/users')
  ))
  const menuNavItems = pinAdminBeforeData(visibleNavItems, isAdmin)
  const onMonitorPage = location.pathname === '/monitor'

  const handleToggle = async (enabled: boolean) => {
    // 开启时重新校验档位
    if (enabled) {
      const fresh = await qc.fetchQuery({
        queryKey: QK.capabilities,
        queryFn: api.capabilities,
      })
      const freshTier = tierRank(fresh.label ?? '')
      if (freshTier < 0) return 'blocked' as const
      if (freshTier === 0 && (prefs?.realtime_watchlist_symbols?.length ?? 0) === 0) {
        navigate('/watchlist')
        return 'navigated' as const
      }
    }
    await toggleQuote.mutateAsync(enabled)
    // 仅在交易时段立即获取一次行情
    if (enabled && isTrading) {
      api.intradayRefresh().catch(() => {})
    }
    return 'toggled' as const
  }

  return (
    <div
      ref={appShellRef}
      data-testid="app-shell"
      className="h-screen grid grid-cols-1 grid-rows-[auto_1fr] md:grid-cols-[14rem_1fr] md:grid-rows-1 bg-base text-foreground overflow-hidden"
    >
      <header
        data-testid="mobile-header"
        className="grid h-14 grid-cols-[2.75rem_1fr_auto] items-center gap-3 border-b border-border bg-surface px-3 md:hidden"
      >
        <button
          ref={mobileNavButtonRef}
          type="button"
          onClick={() => setMobileNavOpen(true)}
          className="inline-flex h-11 w-11 items-center justify-center rounded-btn text-foreground/80 transition-colors hover:bg-elevated hover:text-foreground"
          aria-label="打开导航"
          aria-expanded={mobileNavOpen}
          aria-controls="mobile-navigation-dialog"
        >
          <Menu className="h-5 w-5" />
        </button>

        <span data-testid="mobile-version" className="justify-self-center font-mono text-[10px] text-muted">
          {version ?? ''}
        </span>

        <div data-testid="mobile-brand" className="flex items-center gap-2.5 justify-self-end">
          <Logo size={24} className="text-violet-500" />
          <div className="font-mono text-xs font-bold leading-tight tracking-[0.06em]">
            <div>one</div>
            <div>trading</div>
          </div>
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
              <nav aria-label="移动端主导航" className="space-y-0.5 px-3 py-3">
                {menuNavItems.map(({ to, label, icon: Icon }) => (
                  <AppNavLink
                    key={to}
                    to={to}
                    onClick={() => setMobileNavOpen(false)}
                    className={active =>
                      cn(
                        'flex items-center gap-3 rounded-btn px-3 py-2.5 text-sm transition-colors duration-150 ease-smooth',
                        active
                          ? 'bg-elevated font-medium text-foreground'
                          : 'text-foreground/80 hover:bg-elevated hover:text-foreground',
                      )
                    }
                  >
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
                    {to === TRADE_PATH && <MonitorBadge active={onMonitorPage} />}
                  </AppNavLink>
                ))}
              </nav>

              {isAdmin && <RealtimeSidebarControls
                realtimeEnabled={realtimeEnabled}
                isRunning={isRunning}
                isTrading={isTrading}
                isWatchlistMode={isWatchlistMode}
                realtimeModeLabel={realtimeModeLabel}
                realtimeProviderName={realtimeProviderName}
                realtimeAllowed={realtimeAllowed}
                isPending={toggleQuote.isPending}
                onToggle={async enabled => {
                  const outcome = await handleToggle(enabled)
                  if (outcome === 'navigated') setMobileNavOpen(false)
                }}
                onSettings={() => {
                  setMobileNavOpen(false)
                  navigate('/settings?tab=monitoring')
                }}
                showIndexQuotes={showSidebarQuotes}
                indexRows={sidebarIndexQuotes?.rows}
                indexItems={sidebarIndexes}
                onNavigate={() => setMobileNavOpen(false)}
                className="border-b"
              />}
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

        </div>

        <nav className="flex-1 min-h-0 overflow-y-auto px-2 py-3 space-y-0.5">
          {menuNavItems.map(({ to, label, icon: Icon }) => (
            <AppNavLink
              key={to}
              to={to}
              className={active =>
                cn(
                  'flex items-center gap-3 px-3 py-2 rounded-btn text-sm transition-colors duration-150 ease-smooth',
                  active
                    ? 'bg-elevated text-foreground font-medium'
                    : 'text-foreground/80 hover:bg-elevated hover:text-foreground',
                )
              }
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="flex-1">{label}</span>
              {(to === '/stock-analysis' || to === '/review') && (
                <span className="inline-flex items-center rounded-full border border-amber-400/30 bg-amber-400/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-amber-400 shrink-0">
                  Beta
                </span>
              )}
              {to === '/data' && isDataSyncing && (
                <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-accent" />
              )}
              {to === '/data' && !isDataSyncing && dataSyncJustDone && (
                <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-bull animate-pulse" />
              )}
              {to === TRADE_PATH && <MonitorBadge active={onMonitorPage} />}
            </AppNavLink>
          ))}
        </nav>

        {isAdmin && <RealtimeSidebarControls
          realtimeEnabled={realtimeEnabled}
          isRunning={isRunning}
          isTrading={isTrading}
          isWatchlistMode={isWatchlistMode}
          realtimeModeLabel={realtimeModeLabel}
          realtimeProviderName={realtimeProviderName}
          realtimeAllowed={realtimeAllowed}
          isPending={toggleQuote.isPending}
          onToggle={handleToggle}
          onSettings={() => navigate('/settings?tab=monitoring')}
          showIndexQuotes={showSidebarQuotes}
          indexRows={sidebarIndexQuotes?.rows}
          indexItems={sidebarIndexes}
        />}

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
      <HermesPageAgentHost open={pageAgentOpen} onOpenChange={setPageAgentOpen} />
    </div>
  )
}
