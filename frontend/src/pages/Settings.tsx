/**
 * 统一设置页面 — Tab 切换外壳。
 *
 * 通过 URL query param ?tab=xxx 同步 Tab 状态。
 */
import { Navigate, useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { BarChart3, Key, Radio, SlidersHorizontal, Sparkles, Settings2, Zap, ScrollText, UserRound, Clock3 } from 'lucide-react'
import { SettingsKeysPanel } from './settings/Keys'
import { SettingsAIPanel } from './settings/AI'
import { SettingsMonitoringPanel } from './settings/Monitoring'
import { SettingsExtPagesPanel } from './settings/ExtPages'
import { SettingsMenuSettingsPanel } from './settings/MenuSettings'
import { SettingsSystemPanel } from './settings/System'
import { SettingsRuntimeLogsPanel } from './settings/RuntimeLogs'
import { SettingsCustomSignalsPanel } from './settings/CustomSignals'
import { SettingsAccountPanel } from './settings/Account'
import { SettingsTimeoutPanel } from './settings/Timeout'
import { PageHeader } from '@/components/PageHeader'
import { cn } from '@/lib/cn'
import { DATA_SOURCES_SETTINGS_HREF } from '@/lib/dataSources'
import { useSettings } from '@/lib/useSharedQueries'

// ===== Tab 定义 =====

const TABS = [
  { key: 'profile',    label: '我的账号',   icon: UserRound, panel: SettingsAccountPanel, adminOnly: false },
  { key: 'account',    label: '数据密钥',   icon: Key,       panel: SettingsKeysPanel, adminOnly: true },
  { key: 'ai',         label: 'AI 设置',    icon: Sparkles,  panel: SettingsAIPanel, adminOnly: true },
  { key: 'monitoring', label: '实时监控',   icon: Radio,     panel: SettingsMonitoringPanel, adminOnly: true },
  { key: 'ext-pages',  label: '扩展页面',   icon: BarChart3, panel: SettingsExtPagesPanel, adminOnly: true },
  { key: 'signals',    label: '信号库',     icon: Zap,       panel: SettingsCustomSignalsPanel, adminOnly: true },
  { key: 'menus',      label: '菜单设置',   icon: SlidersHorizontal, panel: SettingsMenuSettingsPanel, adminOnly: false },
  { key: 'timeout',    label: '超时设置',   icon: Clock3,    panel: SettingsTimeoutPanel, adminOnly: true },
  { key: 'system',     label: '系统设置',   icon: Settings2, panel: SettingsSystemPanel, adminOnly: true },
  { key: 'runtime-logs', label: '运行日志', icon: ScrollText, panel: SettingsRuntimeLogsPanel, adminOnly: true },
] as const

export function Settings() {
  const [searchParams, setSearchParams] = useSearchParams()
  const settings = useSettings()
  const isAdmin = settings.data ? settings.data.is_admin !== false : false
  const visibleTabs = TABS.filter(tab => !tab.adminOnly || isAdmin)
  const tabParam = searchParams.get('tab')
  if (tabParam === 'data-sources') {
    return <Navigate to={DATA_SOURCES_SETTINGS_HREF} replace />
  }
  const activeTab = visibleTabs.find((t) => t.key === tabParam) ?? visibleTabs[0]
  const highlight = searchParams.get('highlight') ?? ''

  return (
    <>
      <PageHeader
        title="设置"
        subtitle="管理账户、数据刷新策略和高级功能配置。"
      />

      <div className="px-4 py-4 sm:px-6 md:px-8 md:py-6">
        <div data-testid="settings-layout" className="flex flex-col items-stretch gap-4 lg:flex-row lg:gap-6">
          {/* ===== 手机为顶部网格；平板和桌面为竖向侧栏 ===== */}
          <nav data-testid="settings-navigation" className="w-full shrink-0 lg:w-36">
            <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4 lg:sticky lg:top-6 lg:flex lg:min-h-[60vh] lg:flex-col lg:justify-center lg:gap-0.5">
              {visibleTabs.map(({ key, label, icon: Icon }) => (
                <button
                  key={key}
                  onClick={() => setSearchParams({ tab: key }, { replace: true })}
                  className={cn(
                    'relative flex min-h-11 items-center gap-2 rounded-btn px-3 py-2 text-left text-sm transition-colors duration-150 ease-smooth lg:min-h-0',
                    activeTab.key === key
                      ? 'bg-accent/10 text-accent font-medium'
                      : 'text-secondary hover:text-foreground hover:bg-elevated/60',
                  )}
                >
                  <Icon className="h-3.5 w-3.5 shrink-0" />
                  <span>{label}</span>
                </button>
              ))}
            </div>
          </nav>

          {/* ===== Tab 内容 ===== */}
          <motion.div
            key={activeTab.key}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.15 }}
            data-testid="settings-content"
            className="min-w-0 flex-1"
          >
            {activeTab.key === 'monitoring'
            ? <SettingsMonitoringPanel highlight={highlight} />
            : <activeTab.panel />}
          </motion.div>
        </div>
      </div>
    </>
  )
}
