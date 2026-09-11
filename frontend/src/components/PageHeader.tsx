import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

interface Props {
  title: string
  subtitle?: ReactNode
  /** 标题右侧、subtitle 之前的额外节点(如状态徽标) */
  titleExtra?: ReactNode
  right?: ReactNode
  className?: string
}

export function PageHeader({ title, subtitle, titleExtra, right, className }: Props) {
  return (
    <header
      className={cn(
        'flex flex-col items-stretch gap-3 border-b border-border px-4 pb-3 pt-3 md:flex-row md:items-center md:justify-between md:gap-4 md:px-5 md:pb-2',
        className,
      )}
    >
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <h1 className="shrink-0 text-lg font-semibold tracking-tight">{title}</h1>
        {titleExtra}
        {subtitle && <span className="min-w-0 text-xs leading-relaxed text-muted">{subtitle}</span>}
      </div>
      {right && <div className="min-w-0 w-full md:w-auto">{right}</div>}
    </header>
  )
}
