import { Link, Navigate, Outlet, useLocation } from 'react-router-dom'
import { usePreferences, useSettings } from '@/lib/useSharedQueries'
import {
  firstVisibleMemberPath,
  QUANT_GROUP,
  TRADE_GROUP,
  permissionFromSettings,
  visibleMembers,
  type NavGroupDef,
} from '@/lib/navGroups'
import { cn } from '@/lib/cn'

function groupById(groupId: 'quant' | 'trade'): NavGroupDef {
  return groupId === 'quant' ? QUANT_GROUP : TRADE_GROUP
}

export function GroupEntryRedirect({ groupId }: { groupId: 'quant' | 'trade' }) {
  const settings = useSettings()
  const { data: prefs } = usePreferences()
  if (settings.isLoading && !settings.data) {
    return (
      <div className="grid h-full min-h-0 place-items-center">
        <div className="text-xs text-muted">加载中…</div>
      </div>
    )
  }
  const perm = permissionFromSettings(settings.data)
  const hidden = new Set(prefs?.nav_hidden ?? [])
  return <Navigate to={firstVisibleMemberPath(groupById(groupId), hidden, perm)} replace />
}

export function GroupPageLayout({ groupId }: { groupId: 'quant' | 'trade' }) {
  const group = groupById(groupId)
  const location = useLocation()
  const { data: settings } = useSettings()
  const { data: prefs } = usePreferences()
  const perm = permissionFromSettings(settings)
  const hidden = new Set(prefs?.nav_hidden ?? [])
  const tabs = visibleMembers(group, hidden, perm, { includePath: location.pathname })

  return (
    <div
      data-testid="group-page-layout"
      className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden"
    >
      <div className="shrink-0 border-b border-border bg-surface">
        <nav
          data-testid="group-page-tabs"
          aria-label={`${group.label}功能`}
          className="min-w-0 overflow-x-auto"
        >
          <div className="flex min-w-max items-center gap-0.5 px-3 py-2">
            {tabs.map(tab => {
              const active = location.pathname === tab.path
              return (
                <Link
                  key={tab.path}
                  to={active
                    ? { pathname: location.pathname, search: location.search, hash: location.hash }
                    : tab.path}
                  state={active ? location.state : undefined}
                  replace={active}
                  aria-current={active ? 'page' : undefined}
                  className={cn(
                    'inline-flex h-8 shrink-0 items-center whitespace-nowrap rounded-btn px-3 text-xs font-medium transition-colors',
                    active
                      ? 'bg-accent text-white shadow-sm'
                      : 'text-secondary hover:bg-elevated hover:text-foreground',
                  )}
                >
                  {tab.label}
                </Link>
              )
            })}
          </div>
        </nav>
      </div>
      <div
        data-testid="group-page-panel"
        className="min-h-0 min-w-0 flex-1 overflow-auto"
      >
        <Outlet />
      </div>
    </div>
  )
}
