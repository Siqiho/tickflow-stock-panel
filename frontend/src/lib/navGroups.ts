/**
 * 量化 / 交易分组导航的唯一来源。
 * Layout 侧栏、移动抽屉与设置/菜单设置共用，避免两份菜单漂移。
 * 只在读取时兼容旧 nav_order / nav_hidden，不自动写回迁移。
 */

export const QUANT_PATH = '/quant'
export const TRADE_PATH = '/trade'

export type NavPermission = {
  settingsReady: boolean
  isAdmin: boolean
}

export type NavMemberDef = {
  path: string
  label: string
  adminOnly?: boolean
}

export type NavGroupDef = {
  id: 'quant' | 'trade'
  path: string
  label: string
  members: readonly NavMemberDef[]
}

export type NavLeafDef = {
  path: string
  label: string
  adminOnly?: boolean
  beta?: boolean
}

export type NavSequenceItem =
  | { kind: 'leaf'; def: NavLeafDef }
  | { kind: 'group'; def: NavGroupDef }

export const QUANT_GROUP: NavGroupDef = {
  id: 'quant',
  path: QUANT_PATH,
  label: '量化',
  members: [
    { path: '/screener', label: '策略' },
    { path: '/backtest', label: '回测' },
    { path: '/factors', label: '因子' },
    { path: '/mining', label: '挖掘' },
  ],
}

export const TRADE_GROUP: NavGroupDef = {
  id: 'trade',
  path: TRADE_PATH,
  label: '交易',
  members: [
    { path: '/monitor', label: '监控中心', adminOnly: true },
    { path: '/lots', label: '持仓提醒' },
    { path: '/signals', label: '信号库' },
    { path: '/abnormal', label: '风控 · 异动监控' },
    { path: '/trading', label: '交易' },
  ],
}

export const NAV_GROUPS: readonly NavGroupDef[] = [QUANT_GROUP, TRADE_GROUP]

/** 折叠后的默认侧栏/菜单顺序：原 Layout 顺序，组成员归到首次出现的位置。 */
export const DEFAULT_NAV_SEQUENCE: readonly NavSequenceItem[] = [
  { kind: 'leaf', def: { path: '/', label: '看板' } },
  { kind: 'leaf', def: { path: '/ai', label: 'AI' } },
  { kind: 'leaf', def: { path: '/watchlist', label: '自选' } },
  { kind: 'group', def: QUANT_GROUP },
  { kind: 'leaf', def: { path: '/stock-analysis', label: '个股分析', beta: true } },
  { kind: 'leaf', def: { path: '/limit-ladder', label: '连板梯队' } },
  { kind: 'leaf', def: { path: '/concept-analysis', label: '概念分析' } },
  { kind: 'leaf', def: { path: '/industry-analysis', label: '行业分析' } },
  { kind: 'leaf', def: { path: '/financials', label: '财务分析' } },
  { kind: 'group', def: TRADE_GROUP },
  { kind: 'leaf', def: { path: '/regime', label: '市场环境' } },
  { kind: 'leaf', def: { path: '/review', label: '复盘', beta: true } },
  { kind: 'leaf', def: { path: '/indices', label: '指数' } },
  { kind: 'leaf', def: { path: '/admin/users', label: '用户管理', adminOnly: true } },
  { kind: 'leaf', def: { path: '/data', label: '数据' } },
  { kind: 'leaf', def: { path: '/news', label: '资讯' } },
]

const MEMBER_TO_GROUP = new Map<string, string>()
for (const group of NAV_GROUPS) {
  MEMBER_TO_GROUP.set(group.path, group.path)
  for (const member of group.members) {
    MEMBER_TO_GROUP.set(member.path, group.path)
  }
}

export function findNavGroup(path: string): NavGroupDef | undefined {
  return NAV_GROUPS.find(group => group.path === path)
}

export function canonicalizeNavId(id: string): string {
  return MEMBER_TO_GROUP.get(id) ?? id
}

export function isGroupNavPath(id: string): boolean {
  return NAV_GROUPS.some(group => group.path === id)
}

export function collapseNavOrder(ids: readonly string[]): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  for (const id of ids) {
    const canon = canonicalizeNavId(id)
    if (seen.has(canon)) continue
    seen.add(canon)
    out.push(canon)
  }
  return out
}

export function memberAllowed(member: NavMemberDef, perm: NavPermission): boolean {
  if (!member.adminOnly) return true
  return perm.settingsReady && perm.isAdmin
}

export function allowedMembers(group: NavGroupDef, perm: NavPermission): NavMemberDef[] {
  return group.members.filter(member => memberAllowed(member, perm))
}

export function isGroupHidden(
  group: NavGroupDef,
  hidden: ReadonlySet<string>,
  perm: NavPermission,
): boolean {
  if (hidden.has(group.path)) return true
  const allowed = allowedMembers(group, perm)
  if (allowed.length === 0) return true
  return allowed.every(member => hidden.has(member.path))
}

export function hiddenGroupMembers(
  group: NavGroupDef,
  hidden: ReadonlySet<string>,
  perm: NavPermission,
): NavMemberDef[] {
  return allowedMembers(group, perm).filter(member => hidden.has(member.path))
}

export function visibleMembers(
  group: NavGroupDef,
  hidden: ReadonlySet<string>,
  perm: NavPermission,
  opts?: { includePath?: string },
): NavMemberDef[] {
  return allowedMembers(group, perm).filter(member => (
    !hidden.has(member.path) || member.path === opts?.includePath
  ))
}

export function firstVisibleMemberPath(
  group: NavGroupDef,
  hidden: ReadonlySet<string>,
  perm: NavPermission,
): string {
  const allowed = allowedMembers(group, perm)
  const visible = allowed.filter(member => !hidden.has(member.path))
  return (visible[0] ?? allowed[0] ?? group.members[0]).path
}

export function isPathInNavGroup(pathname: string, groupPath: string): boolean {
  const group = findNavGroup(groupPath)
  if (!group) return pathname === groupPath
  if (pathname === group.path) return true
  return group.members.some(member => (
    pathname === member.path || pathname.startsWith(`${member.path}/`)
  ))
}

export function permissionFromSettings(settings: { is_admin?: boolean } | null | undefined): NavPermission {
  return {
    settingsReady: settings != null,
    isAdmin: settings ? settings.is_admin !== false : false,
  }
}

export function isCatalogEntryVisible(
  id: string,
  hidden: ReadonlySet<string>,
  perm: NavPermission,
  adminOnly?: boolean,
): boolean {
  if (adminOnly && (!perm.settingsReady || !perm.isAdmin)) return false
  const group = findNavGroup(id)
  if (group) return !isGroupHidden(group, hidden, perm)
  return !hidden.has(id) && !hidden.has(id.replace(/^\/analysis\//, ''))
}

export type OrderableNav = { id: string }

export function applySavedNavOrder<T extends OrderableNav>(
  items: readonly T[],
  savedOrder: readonly string[],
): T[] {
  if (savedOrder.length === 0) return [...items]
  const collapsed = collapseNavOrder(savedOrder)
  const byId = new Map(items.map(item => [item.id, item]))
  const ordered: T[] = []
  const seen = new Set<string>()
  for (const id of collapsed) {
    const item = byId.get(id) ?? byId.get(`/analysis/${id}`)
    if (item && !seen.has(item.id)) {
      ordered.push(item)
      seen.add(item.id)
    }
  }
  for (const item of items) {
    if (!seen.has(item.id)) ordered.push(item)
  }
  return ordered
}

export function pinAdminBeforeData<T extends { to: string }>(items: readonly T[], isAdmin: boolean): T[] {
  if (!isAdmin) return [...items]
  const pinned = ['/admin/users', '/data', '/news'] as const
  const rest = items.filter(item => !pinned.includes(item.to as typeof pinned[number]))
  const tail = items
    .filter(item => pinned.includes(item.to as typeof pinned[number]))
    .sort((left, right) => pinned.indexOf(left.to as typeof pinned[number]) - pinned.indexOf(right.to as typeof pinned[number]))
  return [...rest, ...tail]
}

export function toggleHiddenIds(
  hidden: readonly string[],
  id: string,
  perm: NavPermission,
): string[] {
  const next = new Set(hidden)
  const group = findNavGroup(id)
  if (group) {
    if (isGroupHidden(group, next, perm)) {
      next.delete(group.path)
      for (const member of allowedMembers(group, perm)) next.delete(member.path)
    } else {
      next.add(group.path)
    }
    return [...next]
  }
  if (next.has(id)) next.delete(id)
  else next.add(id)
  return [...next]
}

export type MenuCatalogEntry = {
  id: string
  label: string
  type: 'builtin' | 'analysis'
  kind: 'leaf' | 'group'
  adminOnly?: boolean
}

export function builtinMenuCatalog(): MenuCatalogEntry[] {
  return DEFAULT_NAV_SEQUENCE.map(item => (
    item.kind === 'group'
      ? {
          id: item.def.path,
          label: item.def.label,
          type: 'builtin' as const,
          kind: 'group' as const,
        }
      : {
          id: item.def.path,
          label: item.def.label,
          type: 'builtin' as const,
          kind: 'leaf' as const,
          adminOnly: item.def.adminOnly,
        }
  ))
}

export function builtinSidebarItems(): Array<{ to: string; label: string; adminOnly?: boolean; beta?: boolean; kind: 'leaf' | 'group' }> {
  return DEFAULT_NAV_SEQUENCE.map(item => (
    item.kind === 'group'
      ? { to: item.def.path, label: item.def.label, kind: 'group' as const }
      : {
          to: item.def.path,
          label: item.def.label,
          adminOnly: item.def.adminOnly,
          beta: item.def.beta,
          kind: 'leaf' as const,
        }
  ))
}
