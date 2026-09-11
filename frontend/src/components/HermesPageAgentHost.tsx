import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { GripHorizontal, X } from 'lucide-react'
import { AiMark } from '@/components/AiMark'
import { HermesAgentChat } from '@/pages/HermesAgentChat'
import { setPageContextPickerOpen, usePageContext } from '@/lib/pageContext'
import { cn } from '@/lib/cn'

const HIDDEN_ROUTES = new Set(['/login', '/onboarding', '/ai/hermes'])
const PANEL_POS_KEY = 'one-trading.page-ai-panel.pos.v1'
const PANEL_EDGE = 12
const PANEL_MIN_VISIBLE = 80
const PANEL_MIN_WIDTH = 320
const PANEL_MIN_HEIGHT = 360

type PanelBox = { x: number; y: number; width: number; height: number }
type ResizeEdge = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw'

function measurePanel() {
  const mobile = typeof window === 'undefined' ? false : window.innerWidth < 768
  const width = mobile
    ? Math.max(PANEL_MIN_WIDTH, window.innerWidth - 24)
    : Math.min(28 * 16, Math.max(PANEL_MIN_WIDTH, window.innerWidth - 32))
  const height = mobile
    ? Math.max(PANEL_MIN_HEIGHT, window.innerHeight - 64 - 12)
    : Math.max(PANEL_MIN_HEIGHT, Math.min(window.innerHeight - 32, 720))
  return { width, height, mobile }
}

function defaultPanelPos() {
  const { width, height, mobile } = measurePanel()
  return {
    x: mobile ? 12 : Math.max(PANEL_EDGE, window.innerWidth - width - 16),
    y: mobile ? 64 : 16,
    width,
    height,
  }
}

function clampPanelPos(x: number, y: number, width: number, height: number) {
  const maxWidth = Math.max(PANEL_MIN_WIDTH, window.innerWidth - PANEL_EDGE * 2)
  const maxHeight = Math.max(PANEL_MIN_HEIGHT, window.innerHeight - PANEL_EDGE)
  const nextWidth = Math.min(maxWidth, Math.max(PANEL_MIN_WIDTH, width))
  const nextHeight = Math.min(maxHeight, Math.max(PANEL_MIN_HEIGHT, height))
  const maxX = Math.max(PANEL_EDGE, window.innerWidth - PANEL_MIN_VISIBLE)
  const maxY = Math.max(PANEL_EDGE, window.innerHeight - PANEL_MIN_VISIBLE)
  return {
    x: Math.min(maxX, Math.max(PANEL_MIN_VISIBLE - nextWidth, x)),
    y: Math.min(maxY, Math.max(PANEL_EDGE, y)),
    width: nextWidth,
    height: nextHeight,
  }
}

function loadPanelPos() {
  const fallback = defaultPanelPos()
  try {
    const raw = localStorage.getItem(PANEL_POS_KEY)
    if (!raw) return fallback
    const parsed = JSON.parse(raw) as { x?: number; y?: number; width?: number; height?: number }
    return clampPanelPos(
      typeof parsed.x === 'number' ? parsed.x : fallback.x,
      typeof parsed.y === 'number' ? parsed.y : fallback.y,
      typeof parsed.width === 'number' ? parsed.width : fallback.width,
      typeof parsed.height === 'number' ? parsed.height : fallback.height,
    )
  } catch {
    return fallback
  }
}

function savePanelPos(pos: PanelBox) {
  try {
    localStorage.setItem(PANEL_POS_KEY, JSON.stringify(pos))
  } catch {
    /* ignore quota / private mode */
  }
}

const RESIZE_HANDLES: Array<{ edge: ResizeEdge; className: string }> = [
  { edge: 'n', className: 'left-3 right-12 top-0 h-2 cursor-n-resize' },
  { edge: 's', className: 'left-3 right-3 bottom-0 h-2 cursor-s-resize' },
  { edge: 'e', className: 'top-12 bottom-3 right-0 w-2 cursor-e-resize' },
  { edge: 'w', className: 'top-3 bottom-3 left-0 w-2 cursor-w-resize' },
  { edge: 'ne', className: 'right-0 top-10 h-3 w-3 cursor-nesw-resize' },
  { edge: 'nw', className: 'left-0 top-0 h-3 w-3 cursor-nwse-resize' },
  { edge: 'se', className: 'right-0 bottom-0 h-3 w-3 cursor-nwse-resize' },
  { edge: 'sw', className: 'left-0 bottom-0 h-3 w-3 cursor-nesw-resize' },
]

export function HermesPageAgentHost({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const pageAiId = (searchParams.get('pageAi') ?? '').trim()
  const pageContext = usePageContext()
  const hidden = HIDDEN_ROUTES.has(location.pathname)
  const [conversationKey, setConversationKey] = useState(0)
  const panelRef = useRef<HTMLElement>(null)
  const [pos, setPos] = useState(defaultPanelPos)
  const draggingRef = useRef(false)
  const movedRef = useRef(false)
  const dragData = useRef({ mx: 0, my: 0, ox: 0, oy: 0, ow: 0, oh: 0 })
  const posRef = useRef(pos)
  posRef.current = pos
  const resizingRef = useRef<ResizeEdge | null>(null)

  const applyBox = useCallback((next: { x: number; y: number; width: number; height: number }) => {
    const el = panelRef.current
    if (!el) return
    el.style.transform = `translate3d(${next.x}px, ${next.y}px, 0)`
    el.style.width = `${next.width}px`
    el.style.height = `${next.height}px`
  }, [])

  const syncPos = useCallback((next: { x: number; y: number; width: number; height: number }) => {
    setPos(next)
    applyBox(next)
  }, [applyBox])

  useEffect(() => {
    if (hidden && open) onOpenChange(false)
  }, [hidden, open, onOpenChange])

  useEffect(() => {
    if (pageAiId && !hidden && !open) onOpenChange(true)
  }, [hidden, open, onOpenChange, pageAiId])

  useEffect(() => {
    setPageContextPickerOpen(!hidden && open)
    return () => setPageContextPickerOpen(false)
  }, [hidden, open])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onOpenChange(false)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open, onOpenChange])

  useEffect(() => {
    if (!open) return
    const next = loadPanelPos()
    syncPos(next)
  }, [open, syncPos])

  useEffect(() => {
    if (!open) return
    const onResize = () => {
      setPos(prev => {
        const next = clampPanelPos(prev.x, prev.y, prev.width, prev.height)
        applyBox(next)
        return next
      })
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [applyBox, open])

  const moveRef = useRef<(event: { clientX: number; clientY: number }) => void>(() => undefined)
  const upRef = useRef<() => void>(() => undefined)

  const finishDrag = useCallback(() => {
    if (!draggingRef.current && !resizingRef.current) return
    draggingRef.current = false
    resizingRef.current = null
    panelRef.current?.classList.remove('dragging')
    if (!movedRef.current) return
    const el = panelRef.current
    if (!el) return
    const transform = el.style.transform ?? ''
    const match = transform.match(/translate3d\(([\-\d.]+)px,\s*([\-\d.]+)px/)
    const next = clampPanelPos(
      match ? parseFloat(match[1]) : posRef.current.x,
      match ? parseFloat(match[2]) : posRef.current.y,
      parseFloat(el.style.width) || posRef.current.width,
      parseFloat(el.style.height) || posRef.current.height,
    )
    savePanelPos(next)
    syncPos(next)
  }, [syncPos])

  const onWindowPointerMove = useCallback((event: { clientX: number; clientY: number }) => {
    if (!draggingRef.current && !resizingRef.current) return
    const dx = event.clientX - dragData.current.mx
    const dy = event.clientY - dragData.current.my
    if (Math.abs(dx) > 2 || Math.abs(dy) > 2) movedRef.current = true
    if (draggingRef.current) {
      applyBox(clampPanelPos(dragData.current.ox + dx, dragData.current.oy + dy, dragData.current.ow, dragData.current.oh))
      return
    }
    const edge = resizingRef.current
    if (!edge) return
    let x = dragData.current.ox
    let y = dragData.current.oy
    let width = dragData.current.ow
    let height = dragData.current.oh
    if (edge.includes('e')) width = dragData.current.ow + dx
    if (edge.includes('s')) height = dragData.current.oh + dy
    if (edge.includes('w')) {
      width = dragData.current.ow - dx
      x = dragData.current.ox + dx
    }
    if (edge.includes('n')) {
      height = dragData.current.oh - dy
      y = dragData.current.oy + dy
    }
    applyBox(clampPanelPos(x, y, width, height))
  }, [applyBox])

  moveRef.current = onWindowPointerMove
  upRef.current = finishDrag

  useEffect(() => {
    if (!open) return
    const onMove = (event: MouseEvent) => moveRef.current(event)
    const onUp = () => upRef.current()
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    window.addEventListener('pointercancel', onUp)
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      window.removeEventListener('pointercancel', onUp)
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [open])

  const beginInteract = useCallback((event: ReactPointerEvent<HTMLElement>, mode: 'move' | ResizeEdge) => {
    if (event.button != null && event.button !== 0 && event.button !== -1) return
    movedRef.current = false
    dragData.current = { mx: event.clientX, my: event.clientY, ox: posRef.current.x, oy: posRef.current.y, ow: posRef.current.width, oh: posRef.current.height }
    if (mode === 'move') {
      draggingRef.current = true
      resizingRef.current = null
    } else {
      draggingRef.current = false
      resizingRef.current = mode
    }
    panelRef.current?.classList.add('dragging')
    event.currentTarget.setPointerCapture?.(event.pointerId)
    event.preventDefault()
  }, [])

  const onHandlePointerDown = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement | null
    if (target?.closest('a, button, input, textarea, [data-no-drag]')) return
    beginInteract(event, 'move')
  }, [beginInteract])

  if (hidden) return null
  if (!pageContext && !open) return null

  return (
    <>
      {!open && (
        <button
          type="button"
          onClick={() => { setConversationKey(Date.now()); onOpenChange(true) }}
          aria-label={pageContext ? `打开 ${pageContext.title} 的 AI 助理` : '打开嵌入 AI 助理'}
          title={pageContext ? `询问当前${pageContext.title}` : '打开 AI 助理'}
          className={cn(
            'fixed bottom-4 right-4 z-[70] inline-flex h-16 w-16 items-center justify-center',
            'rounded-full bg-transparent p-0',
            'transition-transform hover:scale-105',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300/70',
          )}
        >
          <AiMark size={64} />
        </button>
      )}

      {open && (
        <aside
          ref={panelRef}
          role="dialog"
          aria-modal="true"
          aria-label="嵌入 AI 助理"
          className={cn(
            'page-ai-panel fixed left-0 top-0 z-[80] flex min-h-0 flex-col overflow-hidden rounded-2xl',
            'border border-violet-400/25 bg-base shadow-2xl',
          )}
          style={{
            width: pos.width,
            height: pos.height,
            transform: `translate3d(${pos.x}px, ${pos.y}px, 0)`,
            transition: 'transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), width 0.2s cubic-bezier(0.16, 1, 0.3, 1), height 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
          }}
        >
          <div
            onPointerDown={onHandlePointerDown}
            onMouseDown={onHandlePointerDown}
            className="relative z-20 flex shrink-0 select-none cursor-grab items-center justify-between gap-3 border-b border-border px-4 py-3 active:cursor-grabbing"
            style={{ touchAction: 'none' }}
            title="拖动标题栏可移动窗口"
          >
            <div className="flex min-w-0 items-center gap-2">
              <GripHorizontal className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
              <div className="min-w-0">
                <p className="text-sm font-semibold text-foreground">当前页 AI</p>
                <p className="truncate text-[11px] text-muted">
                  {pageContext ? pageContext.title : '当前页面还没有结构化快照'}
                </p>
              </div>
            </div>
            <Link
              to="/ai"
              data-no-drag
              className="relative z-20 inline-flex h-8 items-center rounded-btn px-2 text-[11px] text-muted transition-colors hover:bg-elevated hover:text-foreground"
            >
              历史
            </Link>
            <button
              type="button"
              data-no-drag
              onPointerDown={event => event.stopPropagation()}
              onMouseDown={event => event.stopPropagation()}
              onClick={event => {
                event.preventDefault()
                event.stopPropagation()
                onOpenChange(false)
              }}
              aria-label="关闭嵌入 AI 助理"
              className="relative z-20 inline-flex h-8 w-8 items-center justify-center rounded-btn text-muted transition-colors hover:bg-elevated hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/40"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          {RESIZE_HANDLES.map(handle => (
            <div
              key={handle.edge}
              data-resize-edge={handle.edge}
              title="拖动边缘可改变窗口大小"
              className={cn('absolute z-10', handle.className)}
              onPointerDown={event => beginInteract(event, handle.edge)}
              onMouseDown={event => beginInteract(event as unknown as ReactPointerEvent<HTMLElement>, handle.edge)}
            />
          ))}
          <div className="min-h-0 flex-1">
            <HermesAgentChat key={conversationKey} embedded />
          </div>
          <style>{`.page-ai-panel.dragging { transition: none !important; }`}</style>
        </aside>
      )}
    </>
  )
}
