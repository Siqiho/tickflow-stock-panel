import { createBrowserRouter, Navigate, useLocation } from 'react-router-dom'
import { Layout } from './components/Layout'
import { GroupEntryRedirect, GroupPageLayout } from './components/GroupPageLayout'
import { Watchlist } from './pages/Watchlist'
import { Screener } from './pages/Screener'
import { Backtest } from './pages/Backtest'
import { Financials } from './pages/Financials'
import { Onboarding } from './pages/Onboarding'
import { Auth } from './pages/Auth'
import { Data } from './pages/Data'
import { News } from './pages/News'
import { Monitor } from './pages/Monitor'
import { Trading } from './pages/Trading'
import { Dashboard } from './pages/Dashboard'
import { AIHub } from './pages/AIHub'
import { HermesAgentChat } from './pages/HermesAgentChat'
import { AnalysisDetail } from './pages/AnalysisDetail'
import { ConceptAnalysis } from './pages/ConceptAnalysis'
import { IndustryAnalysis } from './pages/IndustryAnalysis'
import { StockAnalysis } from './pages/StockAnalysis'
import { Review } from './pages/Review'
import { LimitUpLadder } from './pages/LimitUpLadder'
import { Branding } from './pages/Branding'
import { Settings } from './pages/Settings'
import { Indices } from './pages/Indices'
import { Regime } from './pages/Regime'
import { Mining } from './pages/Mining'
import { Factors } from './pages/Factors'
import { Lots } from './pages/Lots'
import { Signals } from './pages/Signals'
import { AbnormalMoves } from './pages/AbnormalMoves'
import { Dev } from './pages/Dev'
import { AdminUsers } from './pages/AdminUsers'
import { useSettings } from './lib/useSharedQueries'
import { Logo } from './components/Logo'

// 首次使用守卫 —— 未完成向导则重定向到 /onboarding
// 只挂在根路由上;/onboarding 本身不被守卫,避免循环重定向。
// settings 由 Layout 预取,守卫判定不产生额外请求。
function OnboardingGuard({ children }: { children: React.ReactNode }) {
  const settings = useSettings()
  const location = useLocation()

  // 仅首次加载(本地无缓存)时显示占位。
  // 后台重取 (isFetching) 时本地已有上一份缓存可用, 直接放行, 避免切页时整屏 logo 闪烁。
  // 防误重定向已由 Onboarding/AI 等处 invalidate 前的 setQueryData 同步缓存兜底。
  if (settings.isLoading) {
    return (
      <div className="min-h-screen bg-base grid place-items-center">
        <div className="flex flex-col items-center gap-3 text-muted">
          <Logo size={28} className="text-foreground" />
          <div className="text-xs">加载中…</div>
        </div>
      </div>
    )
  }

  // 查询出错或字段缺失时不拦截 —— 宁可放行,也不把用户卡在空白页
  if (
    settings.data
    && settings.data.onboarding_completed === false
    && !location.pathname.startsWith('/admin/')
  ) {
    return <Navigate to="/onboarding" replace />
  }

  return <>{children}</>
}

function AdminGuard({ children }: { children: React.ReactNode }) {
  const settings = useSettings()
  if (settings.isLoading) {
    return (
      <div className="min-h-screen bg-base grid place-items-center">
        <div className="text-xs text-muted">正在验证管理员身份…</div>
      </div>
    )
  }
  if (settings.data?.is_admin !== true) return <Navigate to="/" replace />
  return <>{children}</>
}

export const router = createBrowserRouter([
  { path: '/onboarding', element: <Onboarding /> },
  { path: '/login', element: <Auth /> },
  {
    path: '/',
    element: (
      <OnboardingGuard>
        <Layout />
      </OnboardingGuard>
    ),
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'overview', element: <Navigate to="/" replace /> },
      { path: 'ai', element: <AIHub /> },
      { path: 'ai/hermes', element: <HermesAgentChat /> },
      { path: 'analysis', element: <Navigate to="/settings?tab=ext-pages" replace /> },
      { path: 'analysis/:menuId', element: <AnalysisDetail /> },
      { path: 'concept-analysis', element: <ConceptAnalysis /> },
      { path: 'industry-analysis', element: <IndustryAnalysis /> },
      { path: 'stock-analysis', element: <StockAnalysis /> },
      { path: 'review', element: <Review /> },
      { path: 'watchlist', element: <Watchlist /> },
      { path: 'quant', element: <GroupEntryRedirect groupId="quant" /> },
      {
        element: <GroupPageLayout groupId="quant" />,
        children: [
          { path: 'screener', element: <Screener /> },
          { path: 'backtest', element: <Backtest /> },
          { path: 'factors', element: <Factors /> },
          { path: 'mining', element: <Mining /> },
        ],
      },
      { path: 'financials', element: <Financials /> },
      { path: 'data', element: <Data /> },
      { path: 'news', element: <News /> },
      { path: 'trade', element: <GroupEntryRedirect groupId="trade" /> },
      {
        element: <GroupPageLayout groupId="trade" />,
        children: [
          { path: 'monitor', element: <Monitor /> },
          { path: 'lots', element: <Lots /> },
          { path: 'signals', element: <Signals /> },
          { path: 'abnormal', element: <AbnormalMoves /> },
          { path: 'trading', element: <Trading /> },
        ],
      },
      { path: 'limit-ladder', element: <LimitUpLadder /> },
      { path: 'indices', element: <Indices /> },
      { path: 'regime', element: <Regime /> },
      { path: 'branding', element: <Branding /> },
      { path: 'settings', element: <Settings /> },
      {
        path: 'admin/users',
        element: <AdminGuard><AdminUsers /></AdminGuard>,
      },
      // 隐藏路由：开发者工具（不暴露在菜单，仅供调试）
      { path: 'dev', element: <Dev /> },
      // 旧路由兼容重定向
      { path: 'settings/keys', element: <Navigate to="/settings?tab=account" replace /> },
      { path: 'settings/ai', element: <Navigate to="/settings?tab=ai" replace /> },
      { path: 'settings/queries', element: <Navigate to="/settings?tab=queries" replace /> },
    ],
  },
])
