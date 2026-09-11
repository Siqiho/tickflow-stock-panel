import { Database, FolderSearch, GitBranch, History, RefreshCw, SlidersHorizontal, type LucideIcon } from 'lucide-react'
import { cn } from '@/lib/cn'

export type DataPageSectionId = 'data-overview' | 'data-catalog' | 'data-collection' | 'data-history' | 'data-source-trace' | 'data-upstream-tools'

type Category = {
  id: DataPageSectionId
  label: string
  icon: LucideIcon
  count?: number
}

export function DataPageCategoryNav({
  activeId,
  catalogCount,
  isAdmin,
  onSelect,
}: {
  activeId: DataPageSectionId
  catalogCount?: number
  isAdmin: boolean
  onSelect: (id: DataPageSectionId) => void
}) {
  const sharedCategories: Category[] = [
    { id: 'data-overview', label: '数据总览', icon: Database },
    { id: 'data-catalog', label: '数据目录', icon: FolderSearch, count: catalogCount },
  ]
  const categories: Category[] = isAdmin
    ? [
        ...sharedCategories,
        { id: 'data-collection', label: '采集与同步', icon: RefreshCw },
        { id: 'data-history', label: '运行记录', icon: History },
        { id: 'data-source-trace', label: '来源追踪', icon: GitBranch },
        { id: 'data-upstream-tools', label: '上游工具', icon: SlidersHorizontal },
      ]
    : sharedCategories

  const handleKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    let nextIndex: number | null = null
    if (event.key === 'ArrowRight') nextIndex = (index + 1) % categories.length
    if (event.key === 'ArrowLeft') nextIndex = (index - 1 + categories.length) % categories.length
    if (event.key === 'Home') nextIndex = 0
    if (event.key === 'End') nextIndex = categories.length - 1
    if (nextIndex === null) return

    event.preventDefault()
    const next = categories[nextIndex]
    onSelect(next.id)
    const tabs = event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')
    tabs?.[nextIndex]?.focus()
  }

  return (
    <nav
      aria-label="数据页分类"
      className="order-3 w-full overflow-x-auto border-t border-border pt-2 xl:order-none xl:w-auto xl:border-t-0 xl:pt-0"
    >
      <div role="tablist" aria-label="数据页分类" className="flex min-w-max items-center gap-1 rounded-btn bg-elevated/60 p-1">
        {categories.map(({ id, label, icon: Icon, count }, index) => {
          const selected = activeId === id
          return (
            <button
              key={id}
              id={`${id}-tab`}
              type="button"
              role="tab"
              aria-label={label}
              aria-controls={id}
              aria-selected={selected}
              tabIndex={selected ? 0 : -1}
              onClick={() => onSelect(id)}
              onKeyDown={(event) => handleKeyDown(event, index)}
              className={cn(
                'inline-flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-btn px-2.5 text-[11px] font-medium outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-base sm:text-xs',
                selected
                  ? 'bg-surface text-foreground shadow-sm ring-1 ring-border'
                  : 'text-muted hover:bg-surface/70 hover:text-foreground',
              )}
            >
              <Icon aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
              <span>{label}</span>
              {count !== undefined && (
                <span
                  aria-hidden="true"
                  className={cn(
                    'hidden min-w-5 rounded px-1 text-center font-mono text-[10px] tabular-nums sm:inline-block',
                    selected ? 'bg-accent/10 text-accent' : 'bg-base/70 text-secondary',
                  )}
                >
                  {count}
                </span>
              )}
            </button>
          )
        })}
      </div>
    </nav>
  )
}
