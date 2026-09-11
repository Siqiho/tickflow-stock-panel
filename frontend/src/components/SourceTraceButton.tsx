import { GitBranch } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useSettings } from '@/lib/useSharedQueries'
import { sourceTracePath, type SourceTraceSubject } from '@/lib/sourceTraceSubjects'
import { cn } from '@/lib/cn'

type Variant = 'icon' | 'chip'

function SourceTraceLink({
  subjects,
  label,
  variant,
  className,
}: {
  subjects: readonly SourceTraceSubject[]
  label: string
  variant: Variant
  className?: string
}) {
  const settings = useSettings()
  const primary = subjects[0]
  if (settings.data?.is_admin !== true || !primary) return null

  const extra = subjects.slice(1)
  const title = extra.length
    ? `${label}：${subjects.map(item => item.label).join('、')}`
    : `${label}：${primary.label}`

  return (
    <Link
      to={sourceTracePath(primary.id)}
      aria-label={title}
      title={title}
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-btn text-muted transition-colors hover:bg-elevated hover:text-accent',
        variant === 'icon' ? 'h-7 w-7' : 'h-7 gap-1 px-2 text-[11px] font-medium',
        className,
      )}
    >
      <GitBranch aria-hidden="true" className="h-3.5 w-3.5" />
      {variant === 'chip' ? <span>{label}</span> : null}
    </Link>
  )
}

export function SourceTraceButton({
  subjects,
  label = '来源追踪',
  variant = 'icon',
  className,
}: {
  subjects: readonly SourceTraceSubject[]
  label?: string
  variant?: Variant
  className?: string
}) {
  try {
    useQueryClient()
  } catch {
    return null
  }
  return (
    <SourceTraceLink
      subjects={subjects}
      label={label}
      variant={variant}
      className={className}
    />
  )
}
