import { ChevronDown } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'

export function AdvancedDisclosure({
  children,
  className = '',
  label = '高级信息',
}: {
  children: ReactNode
  className?: string
  label?: string
}) {
  const [open, setOpen] = useState(false)
  const contentId = useId()

  return (
    <div className={className}>
      <button
        type="button"
        aria-controls={contentId}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="inline-flex items-center gap-1.5 rounded-btn px-1 py-1 text-xs font-medium text-secondary outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-accent"
      >
        {label}
        <ChevronDown aria-hidden="true" className={`h-3.5 w-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && <div id={contentId} className="mt-3">{children}</div>}
    </div>
  )
}
