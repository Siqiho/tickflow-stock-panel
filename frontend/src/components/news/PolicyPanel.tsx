import { useMemo, useState } from 'react'
import { RefreshCw, Star, X } from 'lucide-react'
import { Modal } from '@/components/Modal'
import { cn } from '@/lib/cn'
import { isSafeHttpUrl, shortDeptName, type DepartmentCatalog, type KeyDepartments, type PolicyItem } from '@/lib/news'

export function PolicyPanel({
  departments,
  keyDepartments,
  items,
  total,
  hasMore,
  currentDept,
  keyword,
  searchMode,
  loading,
  refreshing,
  error,
  headerHint,
  onSelectDept,
  onKeywordChange,
  onSearch,
  onClearSearch,
  onRefresh,
  onLoadMore,
  onToggleKey,
  onRemoveKey,
  onSaveKeys,
  onResetKeys,
}: {
  departments: DepartmentCatalog['departments']
  keyDepartments: KeyDepartments
  items: PolicyItem[]
  total: number
  hasMore: boolean
  currentDept: string
  keyword: string
  searchMode: boolean
  loading: boolean
  refreshing: boolean
  error?: string | null
  headerHint: string
  onSelectDept: (name: string) => void
  onKeywordChange: (value: string) => void
  onSearch: () => void
  onClearSearch: () => void
  onRefresh: () => void
  onLoadMore: () => void
  onToggleKey: () => void
  onRemoveKey: (name: string) => void
  onSaveKeys: (names: string[]) => Promise<void> | void
  onResetKeys: () => Promise<void> | void
}) {
  const [manageOpen, setManageOpen] = useState(false)
  const [draft, setDraft] = useState<string[]>([])
  const [deptQuery, setDeptQuery] = useState('')
  const currentUrl = departments.find(item => item.name === currentDept)?.url || ''
  const isKey = currentDept !== '全部部门' && keyDepartments.departments.includes(currentDept)
  const filteredDepts = useMemo(() => {
    const q = deptQuery.trim()
    if (!q) return departments
    return departments.filter(item => item.name.includes(q))
  }, [departments, deptQuery])

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 grid-rows-[minmax(0,auto)_minmax(20rem,1fr)] gap-3 max-lg:overflow-y-auto lg:grid-cols-[13rem_minmax(0,1fr)] lg:grid-rows-none">
      <aside className="min-h-0 space-y-3 max-lg:max-h-[min(22rem,40vh)] max-lg:overflow-y-auto">
        <section className="rounded-card border border-border bg-surface p-2.5">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-[13px] font-semibold">部门</h2>
            <span className="text-[10px] text-muted">{departments.length} 个</span>
          </div>
          <button
            type="button"
            onClick={() => onSelectDept('全部部门')}
            className={cn(
              'block w-full rounded px-2 py-1 text-left text-[12px]',
              currentDept === '全部部门' ? 'bg-accent/15 text-accent' : 'hover:bg-elevated',
            )}
          >
            全部部门
          </button>
          <div className="my-2 h-px bg-border" />
          <div className="space-y-1">
            {keyDepartments.departments.map(name => (
              <div key={name} className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => onSelectDept(name)}
                  className={cn(
                    'min-w-0 flex-1 rounded px-2 py-1 text-left text-[12px]',
                    currentDept === name ? 'bg-accent/15 text-accent' : 'hover:bg-elevated',
                  )}
                >
                  {shortDeptName(name)}
                </button>
                <button
                  type="button"
                  aria-label={`移除${name}`}
                  onClick={() => onRemoveKey(name)}
                  className="rounded p-1 text-muted hover:text-foreground"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
          <button
            type="button"
            className="mt-2 w-full rounded border border-dashed border-border px-2 py-1 text-[11px] text-secondary hover:bg-elevated"
            onClick={() => {
              setDraft([...keyDepartments.departments])
              setManageOpen(true)
            }}
          >
            自定义重点部门
          </button>
        </section>
        <section className="rounded-card border border-border bg-surface p-2.5">
          <h3 className="mb-2 text-[13px] font-semibold">选择部门</h3>
          <input
            value={deptQuery}
            onChange={event => setDeptQuery(event.target.value)}
            placeholder="搜索全部部门"
            className="mb-2 w-full rounded-btn border border-border bg-base px-2 py-1 text-[12px]"
          />
          <div className="max-h-56 overflow-y-auto">
            {filteredDepts.map(dept => (
              <button
                key={dept.name}
                type="button"
                onClick={() => onSelectDept(dept.name)}
                className={cn(
                  'block w-full rounded px-2 py-1 text-left text-[12px]',
                  currentDept === dept.name ? 'bg-accent/15 text-accent' : 'hover:bg-elevated',
                )}
              >
                {dept.name}
              </button>
            ))}
          </div>
        </section>
      </aside>

      <section className="flex min-h-[20rem] flex-col overflow-hidden rounded-card border border-border bg-surface lg:min-h-0">
        <header className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
          <strong className="text-[13px]">{searchMode ? `搜索：${keyword}` : currentDept}</strong>
          <span className="rounded bg-accent/10 px-1.5 py-px text-[10px] text-accent">{total} 条</span>
          {currentDept !== '全部部门' && currentUrl && isSafeHttpUrl(currentUrl) && (
            <a href={currentUrl} target="_blank" rel="noreferrer" className="text-[11px] text-bull hover:underline">
              官网
            </a>
          )}
          {currentDept !== '全部部门' && (
            <button type="button" onClick={onToggleKey} className="text-[11px] text-warning">
              {isKey ? '★ 已重点' : '☆ 加重点'}
            </button>
          )}
          <span className="text-[11px] text-muted">{headerHint}</span>
          <div className="ml-auto flex flex-wrap items-center gap-1.5">
            <input
              value={keyword}
              onChange={event => onKeywordChange(event.target.value)}
              onKeyDown={event => {
                if (event.key === 'Enter') onSearch()
              }}
              placeholder="关键词搜索历史政策"
              className="w-48 rounded-btn border border-border bg-base px-2 py-1 text-[12px]"
            />
            <button
              type="button"
              onClick={onSearch}
              className="rounded-btn bg-elevated px-2 py-1 text-[12px] hover:bg-border"
            >
              搜索
            </button>
            {searchMode ? (
              <button type="button" onClick={onClearSearch} className="rounded-btn px-2 py-1 text-[12px] text-bear">
                退出搜索
              </button>
            ) : (
              <button
                type="button"
                onClick={onRefresh}
                disabled={refreshing}
                className="inline-flex items-center gap-1 rounded-btn px-2 py-1 text-[12px] text-accent disabled:opacity-50"
              >
                <RefreshCw className={cn('h-3.5 w-3.5', refreshing && 'animate-spin')} />
                刷新
              </button>
            )}
          </div>
        </header>
        {error && <div className="border-b border-border px-3 py-1.5 text-[11px] text-bear">{error}</div>}
        <ul className="min-h-0 flex-1 overflow-y-auto">
          {loading && items.length === 0 && <li className="px-3 py-10 text-center text-xs text-muted">加载中…</li>}
          {!loading && items.length === 0 && (
            <li className="px-3 py-10 text-center text-xs text-muted">
              {searchMode ? '没有匹配的政策新闻，换个关键词试试' : '暂无数据，请点击刷新重试'}
            </li>
          )}
          {items.map(item => (
            <li key={item.url} className="flex flex-wrap items-center gap-2 border-b border-border/60 px-3 py-1.5">
              <span className="rounded bg-warning/15 px-1 py-px font-mono text-[10px] text-warning">{item.date}</span>
              <button
                type="button"
                onClick={() => onSelectDept(item.source)}
                className="rounded bg-accent/10 px-1 py-px text-[10px] text-accent"
              >
                {shortDeptName(item.source)}
              </button>
              {isSafeHttpUrl(item.url) ? (
                <a href={item.url} target="_blank" rel="noreferrer" className="min-w-0 flex-1 text-[12px] hover:underline">
                  {item.title}
                </a>
              ) : (
                <span className="min-w-0 flex-1 text-[12px]">{item.title}</span>
              )}
              {isSafeHttpUrl(item.url) && (
                <a href={item.url} target="_blank" rel="noreferrer" className="text-[11px] text-warning">
                  原文
                </a>
              )}
            </li>
          ))}
        </ul>
        {hasMore && (
          <button
            type="button"
            onClick={onLoadMore}
            className="border-t border-border px-3 py-2 text-[12px] text-accent hover:bg-elevated"
          >
            加载更多本地历史
          </button>
        )}
      </section>

      {manageOpen && (
        <Modal onClose={() => setManageOpen(false)} ariaLabel="自定义重点部门" panelClassName="w-[92vw] max-w-lg rounded-card border border-border bg-surface p-4">
          <h2 className="text-sm font-semibold">自定义重点部门</h2>
          <p className="mt-1 text-[11px] text-muted">清空后保存将恢复默认列表。重点部门按当前账号隔离。</p>
          <div className="mt-3 max-h-64 overflow-y-auto rounded border border-border">
            {departments.map(dept => {
              const checked = draft.includes(dept.name)
              return (
                <label key={dept.name} className="flex items-center gap-2 border-b border-border/50 px-2 py-1.5 text-[12px]">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => {
                      setDraft(current => (
                        checked ? current.filter(name => name !== dept.name) : [...current, dept.name]
                      ))
                    }}
                  />
                  <Star className={cn('h-3 w-3', checked ? 'text-warning' : 'text-muted')} />
                  {dept.name}
                </label>
              )
            })}
          </div>
          <div className="mt-3 flex justify-end gap-2">
            <button type="button" className="rounded-btn px-2 py-1 text-[12px]" onClick={() => void onResetKeys()}>
              恢复默认
            </button>
            <button type="button" className="rounded-btn px-2 py-1 text-[12px]" onClick={() => setManageOpen(false)}>
              取消
            </button>
            <button
              type="button"
              className="rounded-btn bg-accent px-2 py-1 text-[12px] text-white"
              onClick={async () => {
                await onSaveKeys(draft)
                setManageOpen(false)
              }}
            >
              保存
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}
