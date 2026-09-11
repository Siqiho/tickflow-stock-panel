import type { ReactNode } from 'react'
import { selectPageContextFocus, usePageContext, usePageContextPickerOpen } from '@/lib/pageContext'
import { cn } from '@/lib/cn'

export function PageContextModule({
  id,
  children,
  className,
}: {
  id: string
  children: ReactNode
  className?: string
}) {
  const pageContext = usePageContext()
  const picking = usePageContextPickerOpen()
  const active = picking && (pageContext?.selectedFocusIds ?? []).includes(id)

  const activate = () => {
    if (!picking) return
    selectPageContextFocus(id)
  }

  return (
    <div
      data-page-module={id}
      onClickCapture={event => {
        const target = event.target as HTMLElement | null
        if (target?.closest('a[href*="source-trace"], button[aria-label*="来源追踪"]')) return
        activate()
      }}
      className={cn(
        'min-w-0',
        picking && '[&>*]:transition-[box-shadow]',
        picking && 'hover:[&>*]:shadow-[0_0_0_1px_rgba(139,92,246,0.28)]',
        active && '[&>*]:shadow-[0_0_0_2px_rgba(139,92,246,0.45)]',
        className,
      )}
    >
      {children}
    </div>
  )
}
