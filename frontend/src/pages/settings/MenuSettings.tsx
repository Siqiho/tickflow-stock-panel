import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Eye, EyeOff, ExternalLink, GripVertical, Settings, Bell } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { usePreferences, useSettings } from '@/lib/useSharedQueries'
import {
  applySavedNavOrder,
  builtinMenuCatalog,
  findNavGroup,
  hiddenGroupMembers,
  isCatalogEntryVisible,
  permissionFromSettings,
  toggleHiddenIds,
  TRADE_PATH,
  type MenuCatalogEntry,
} from '@/lib/navGroups'

// ── Sortable row ──

function SortableItem({ entry, hidden, onToggleHidden, badgeEnabled, onToggleBadge, hiddenMembers, onRestoreMember }: {
  entry: MenuCatalogEntry
  hidden: boolean
  onToggleHidden: (id: string) => void
  badgeEnabled?: boolean
  onToggleBadge?: (id: string) => void
  hiddenMembers?: Array<{ path: string; label: string }>
  onRestoreMember?: (id: string) => void
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: entry.id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.6 : 1,
    zIndex: isDragging ? 10 : undefined,
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`border-b border-border/70 last:border-b-0 ${
        isDragging ? 'bg-elevated rounded-lg shadow-lg' : ''
      } ${hidden ? 'opacity-50' : ''}`}
    >
    <div className="grid grid-cols-[2.5rem_1fr_4.5rem_3rem_3rem_3rem] items-center px-4 py-3">
      <div
        {...attributes}
        {...listeners}
        className="cursor-grab active:cursor-grabbing text-muted hover:text-foreground transition-colors"
      >
        <GripVertical className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex items-center gap-2">
        <span className={`truncate text-sm font-medium ${!hidden ? 'text-foreground' : 'text-muted line-through'}`}>
          {entry.label}
        </span>
        {entry.kind === 'group' && (
          <span className="rounded bg-elevated px-1.5 py-0.5 text-[10px] text-muted shrink-0">分组</span>
        )}
        {hidden && (
          <span className="rounded bg-elevated px-1.5 py-0.5 text-[10px] text-muted shrink-0">已隐藏</span>
        )}
        <span className="truncate text-[11px] text-muted font-mono">{entry.id}</span>
      </div>
      <div>
        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] ${
          entry.type === 'analysis' ? 'bg-accent/10 text-accent' : 'bg-elevated text-muted'
        }`}>
          {entry.type === 'builtin' ? '内置' : '扩展'}
        </span>
      </div>
      <div className="flex justify-center">
        <button
          onClick={() => onToggleHidden(entry.id)}
          className={`rounded p-1 transition-colors ${
            hidden
              ? 'text-muted hover:text-accent hover:bg-accent/10'
              : 'text-accent hover:bg-accent/10'
          }`}
          title={hidden ? '显示' : '隐藏'}
        >
          {hidden ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
      <div className="flex justify-center">
        {entry.type === 'builtin' ? (
          <Link
            to={entry.id}
            className="rounded p-1 text-muted hover:text-accent hover:bg-accent/10 transition-colors"
            title="打开页面"
          >
            <ExternalLink className="h-3.5 w-3.5" />
          </Link>
        ) : (
          <Link
            to={`/settings?tab=ext-pages`}
            className="rounded p-1 text-muted hover:text-accent hover:bg-accent/10 transition-colors"
            title="编辑扩展页面"
          >
            <Settings className="h-3.5 w-3.5" />
          </Link>
        )}
      </div>
      {/* 第 6 列: 徽标开关 (交易组 / 监控未读) */}
      <div className="flex justify-center">
        {onToggleBadge && (
          <button
            onClick={() => onToggleBadge(entry.id)}
            className={`rounded p-1 transition-colors ${
              badgeEnabled
                ? 'text-accent hover:bg-accent/10'
                : 'text-muted hover:text-accent hover:bg-accent/10'
            }`}
            title={badgeEnabled ? '关闭数字提示' : '开启数字提示'}
          >
            <Bell className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </div>
    {!hidden && hiddenMembers && hiddenMembers.length > 0 && (
      <div className="flex flex-wrap items-center gap-2 px-4 pb-3 text-[11px] text-muted">
        <span>部分标签已隐藏，可恢复：</span>
        {hiddenMembers.map(member => (
          <button
            key={member.path}
            type="button"
            onClick={() => onRestoreMember?.(member.path)}
            className="rounded-btn border border-border bg-elevated px-2 py-0.5 text-[11px] text-secondary hover:text-accent"
          >
            恢复 {member.label}
          </button>
        ))}
      </div>
    )}
    </div>
  )
}

// ── Main panel ──

export function SettingsMenuSettingsPanel() {
  const qc = useQueryClient()
  const { data: prefs } = usePreferences()
  const { data: settings } = useSettings()
  const perm = permissionFromSettings(settings)
  const menus = useQuery({ queryKey: QK.analysisMenus, queryFn: api.analysisMenus })

  const analysisEntries: MenuCatalogEntry[] = (menus.data?.items ?? []).map(m => ({
    id: m.id,
    label: m.label,
    type: 'analysis' as const,
    kind: 'leaf' as const,
  }))

  const catalog = useMemo(
    () => [
      ...builtinMenuCatalog().filter(entry => !entry.adminOnly || (perm.settingsReady && perm.isAdmin)),
      ...analysisEntries,
    ],
    [analysisEntries, perm.isAdmin, perm.settingsReady],
  )

  const allEntries = useMemo(
    () => applySavedNavOrder(catalog, prefs?.nav_order ?? []),
    [catalog, prefs?.nav_order],
  )

  const hiddenSet = useMemo(() => new Set(prefs?.nav_hidden ?? []), [prefs?.nav_hidden])

  // Local order state for optimistic drag updates
  const [localOrder, setLocalOrder] = useState<string[] | null>(null)
  const orderedEntries = useMemo(
    () => applySavedNavOrder(allEntries, localOrder ?? prefs?.nav_order ?? []),
    [localOrder, prefs?.nav_order, allEntries],
  )

  const saveNavOrder = useMutation({
    mutationFn: (order: string[]) => api.saveNavOrder(order),
    onSuccess: () => {
      setLocalOrder(null)
      qc.invalidateQueries({ queryKey: QK.preferences })
    },
  })

  const saveNavHidden = useMutation({
    mutationFn: (hidden: string[]) => api.saveNavHidden(hidden),
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.preferences }),
  })

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id) return

    const ids = orderedEntries.map(e => e.id)
    const oldIdx = ids.indexOf(active.id as string)
    const newIdx = ids.indexOf(over.id as string)
    const reordered = arrayMove(ids, oldIdx, newIdx)
    setLocalOrder(reordered)
    saveNavOrder.mutate(reordered)
  }

  const toggleHidden = (id: string) => {
    saveNavHidden.mutate(toggleHiddenIds([...hiddenSet], id, perm))
  }

  // 监控未读徽标开关 (localStorage) — 设置入口指向交易组
  const [badgeEnabled, setBadgeEnabled] = useState(() => {
    try { return localStorage.getItem('monitor_badge_enabled') !== '0' } catch { return true }
  })
  const toggleBadge = (id: string) => {
    if (id !== TRADE_PATH) return
    const next = !badgeEnabled
    setBadgeEnabled(next)
    try { localStorage.setItem('monitor_badge_enabled', next ? '1' : '0') } catch { /* ignore */ }
  }

  return (
    <div className="max-w-5xl space-y-6">
      <section className="rounded-2xl border border-border bg-surface p-6 bg-[radial-gradient(circle_at_top_right,rgba(59,130,246,0.12),transparent_38%)]">
        <div className="text-[11px] uppercase tracking-[0.2em] text-accent/80">菜单设置</div>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">调整左侧菜单顺序</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-secondary">
          拖动左侧手柄调整菜单排列顺序，点击眼睛图标控制菜单在侧边栏中的显示或隐藏。
        </p>
      </section>

      <section className="rounded-card border border-border bg-surface overflow-hidden">
        <div className="grid grid-cols-[2.5rem_1fr_4.5rem_3rem_3rem_3rem] items-center border-b border-border px-4 py-2 text-[11px] text-muted">
          <div />
          <div>菜单</div>
          <div>类型</div>
          <div className="text-center">显示</div>
          <div className="text-center">设置</div>
          <div className="text-center">数字</div>
        </div>

        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={orderedEntries.map(e => e.id)}
            strategy={verticalListSortingStrategy}
          >
            {orderedEntries.map((entry) => {
              const group = findNavGroup(entry.id)
              const membersHidden = group
                ? hiddenGroupMembers(group, hiddenSet, perm)
                : []
              return (
              <SortableItem
                key={entry.id}
                entry={entry}
                hidden={!isCatalogEntryVisible(entry.id, hiddenSet, perm, entry.adminOnly)}
                onToggleHidden={toggleHidden}
                badgeEnabled={entry.id === TRADE_PATH ? badgeEnabled : undefined}
                onToggleBadge={entry.id === TRADE_PATH ? toggleBadge : undefined}
                hiddenMembers={membersHidden}
                onRestoreMember={toggleHidden}
              />
              )
            })}
          </SortableContext>
        </DndContext>

        {menus.isLoading && (
          <div className="px-5 py-10 text-center text-sm text-muted">正在加载菜单...</div>
        )}
      </section>
    </div>
  )
}
