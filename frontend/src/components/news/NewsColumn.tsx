import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { cn } from '@/lib/cn'
import { isSafeHttpUrl, sentimentClass, type MarketSourceState, type NewsItem } from '@/lib/news'

function dayKey(item: NewsItem) {
  return (item.data_time || '').slice(0, 10)
}

function NewsRow({ item, isNew }: { item: NewsItem; isNew: boolean }) {
  const [open, setOpen] = useState(false)
  const hasTitle = Boolean(item.title)
  return (
    <div className="border-b border-border/60 px-2.5 py-1.5">
      {isNew && (
        <span className="mb-1 inline-flex rounded bg-bull/15 px-1 py-px text-[9px] font-semibold text-bull">新</span>
      )}
      <div className="flex items-start gap-1.5">
        <span
          className={cn(
            'shrink-0 rounded px-1 py-px font-mono text-[10px]',
            item.is_red ? 'bg-bull/15 text-bull' : 'bg-warning/15 text-warning',
          )}
        >
          {item.time || '--:--:--'}
        </span>
        {hasTitle ? (
          <button
            type="button"
            className={cn(
              'min-w-0 flex-1 text-left text-[12px] leading-5',
              item.is_red ? 'text-bull' : 'text-foreground',
            )}
            onClick={() => setOpen(value => !value)}
          >
            {item.title}
          </button>
        ) : (
          <p className={cn('min-w-0 flex-1 text-[12px] leading-5', item.is_red ? 'text-bull' : 'text-foreground')}>
            {item.content}
          </p>
        )}
      </div>
      {open && item.content && (
        <p className="mt-1 pl-[3.4rem] text-[12px] leading-5 text-secondary">{item.content}</p>
      )}
      {(item.subjects.length > 0 || item.stocks.length > 0 || item.url || item.sentiment) && (
        <div className="mt-1 flex flex-wrap items-center gap-1 pl-[3.4rem]">
          {item.subjects.map(subject => (
            <span key={subject} className="rounded bg-accent/10 px-1 py-px text-[10px] text-accent">
              {subject}
            </span>
          ))}
          {item.stocks.map(stock => (
            <span key={stock} className="rounded bg-warning/10 px-1 py-px text-[10px] text-warning">
              {stock}
            </span>
          ))}
          {item.url && isSafeHttpUrl(item.url) && (
            <a
              href={item.url}
              target="_blank"
              rel="noreferrer"
              className="text-[10px] text-warning hover:underline"
            >
              原文
            </a>
          )}
          {item.sentiment && (
            <span className={cn('text-[10px]', sentimentClass(item.sentiment))}>{item.sentiment}</span>
          )}
        </div>
      )}
    </div>
  )
}

export function NewsColumn({
  state,
  previousIds,
  refreshing,
  onRefresh,
}: {
  state?: MarketSourceState
  previousIds: Set<string>
  refreshing: boolean
  onRefresh: () => void
}) {
  const items = state?.items ?? []
  return (
    <section className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-card border border-border bg-surface">
      <header className="flex items-center justify-between gap-2 border-b border-border px-2.5 py-2">
        <div className="min-w-0">
          <h2 className="truncate text-[13px] font-semibold">{state?.label ?? '快讯'}</h2>
          {state?.error && (
            <p className="truncate text-[10px] text-bear">
              {state.preserved ? '本源失败，仍显示上次数据' : state.error}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={refreshing}
          className="inline-flex h-7 w-7 items-center justify-center rounded-btn text-accent hover:bg-elevated disabled:opacity-50"
          aria-label={`刷新${state?.label ?? ''}`}
        >
          <RefreshCw className={cn('h-4 w-4', refreshing && 'animate-spin')} />
        </button>
      </header>
      <ul className="min-h-0 flex-1 overflow-y-auto">
        {items.length === 0 && (
          <li className="px-3 py-8 text-center text-xs text-muted">
            {state?.error ? state.error : '暂无缓存，请点击刷新'}
          </li>
        )}
        {items.map((item, index) => {
          const prevDay = index > 0 ? dayKey(items[index - 1]) : ''
          const currentDay = dayKey(item)
          return (
            <li key={item.id || `${item.data_time}-${item.title}`} className="list-none">
              {index > 0 && currentDay && currentDay !== prevDay && (
                <div className="px-2 py-1 text-center text-[10px] text-muted">{currentDay}</div>
              )}
              <NewsRow item={item} isNew={previousIds.size > 0 && !previousIds.has(item.id)} />
            </li>
          )
        })}
      </ul>
    </section>
  )
}
