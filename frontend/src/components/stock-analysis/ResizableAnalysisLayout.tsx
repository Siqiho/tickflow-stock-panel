import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
} from 'react'

const DEFAULT_RAIL_WIDTH = 296
const MIN_RAIL_WIDTH = 280
const MAX_RAIL_WIDTH = 520
const MIN_MAIN_WIDTH = 640
const GRID_GAP = 16
const KEYBOARD_STEP = 24
const KEYBOARD_LARGE_STEP = 48

interface Props {
  main: ReactNode
  rail: ReactNode
}

interface DragState {
  divider: HTMLDivElement
  pointerId: number
  startX: number
  startWidth: number
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max)
}

export function ResizableAnalysisLayout({ main, rail }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<DragState | null>(null)
  const maxRailWidthRef = useRef(MAX_RAIL_WIDTH)
  const [railWidth, setRailWidth] = useState(DEFAULT_RAIL_WIDTH)
  const [maxRailWidth, setMaxRailWidth] = useState(MAX_RAIL_WIDTH)
  const [isDragging, setIsDragging] = useState(false)

  const updateRailWidth = useCallback((nextWidth: number) => {
    setRailWidth(clamp(nextWidth, MIN_RAIL_WIDTH, maxRailWidthRef.current))
  }, [])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const updateBounds = () => {
      const containerWidth = container.getBoundingClientRect().width
      if (containerWidth <= 0) return
      const nextMax = Math.max(
        MIN_RAIL_WIDTH,
        Math.min(MAX_RAIL_WIDTH, Math.floor(containerWidth - MIN_MAIN_WIDTH - GRID_GAP)),
      )
      maxRailWidthRef.current = nextMax
      setMaxRailWidth(nextMax)
      setRailWidth(current => clamp(current, MIN_RAIL_WIDTH, nextMax))
    }

    updateBounds()
    const observer = typeof ResizeObserver === 'undefined'
      ? null
      : new ResizeObserver(updateBounds)
    observer?.observe(container)
    window.addEventListener('resize', updateBounds)
    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', updateBounds)
    }
  }, [])

  useEffect(() => {
    const finishDrag = (event?: globalThis.PointerEvent) => {
      const drag = dragRef.current
      if (!drag) return
      if (event && event.pointerId !== drag.pointerId) return
      if (drag.divider.hasPointerCapture?.(drag.pointerId)) {
        drag.divider.releasePointerCapture(drag.pointerId)
      }
      dragRef.current = null
      setIsDragging(false)
    }

    const moveDivider = (event: globalThis.PointerEvent) => {
      const drag = dragRef.current
      if (!drag || event.pointerId !== drag.pointerId) return
      event.preventDefault()
      updateRailWidth(drag.startWidth + drag.startX - event.clientX)
    }
    const cancelDrag = () => finishDrag()

    window.addEventListener('pointermove', moveDivider, { passive: false })
    window.addEventListener('pointerup', finishDrag)
    window.addEventListener('pointercancel', finishDrag)
    window.addEventListener('blur', cancelDrag)
    return () => {
      window.removeEventListener('pointermove', moveDivider)
      window.removeEventListener('pointerup', finishDrag)
      window.removeEventListener('pointercancel', finishDrag)
      window.removeEventListener('blur', cancelDrag)
    }
  }, [updateRailWidth])

  useEffect(() => {
    if (!isDragging) return
    const previousCursor = document.body.style.cursor
    const previousUserSelect = document.body.style.userSelect
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    return () => {
      document.body.style.cursor = previousCursor
      document.body.style.userSelect = previousUserSelect
    }
  }, [isDragging])

  const startDrag = (event: PointerEvent<HTMLDivElement>) => {
    if (event.pointerType === 'mouse' && event.button !== 0) return
    event.preventDefault()
    event.currentTarget.focus({ preventScroll: true })
    event.currentTarget.setPointerCapture?.(event.pointerId)
    dragRef.current = {
      divider: event.currentTarget,
      pointerId: event.pointerId,
      startX: event.clientX,
      startWidth: railWidth,
    }
    setIsDragging(true)
  }

  const resizeWithKeyboard = (event: KeyboardEvent<HTMLDivElement>) => {
    let nextWidth: number | null = null
    const step = event.shiftKey ? KEYBOARD_LARGE_STEP : KEYBOARD_STEP
    if (event.key === 'ArrowLeft') nextWidth = railWidth + step
    if (event.key === 'ArrowRight') nextWidth = railWidth - step
    if (event.key === 'Home') nextWidth = MIN_RAIL_WIDTH
    if (event.key === 'End') nextWidth = maxRailWidth
    if (nextWidth == null) return
    event.preventDefault()
    updateRailWidth(nextWidth)
  }

  const layoutStyle = {
    '--stock-analysis-rail-width': `${railWidth}px`,
  } as CSSProperties

  return (
    <div
      ref={containerRef}
      className="relative grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_var(--stock-analysis-rail-width)]"
      style={layoutStyle}
      data-testid="stock-analysis-layout"
    >
      {main}

      <div
        role="separator"
        aria-label="调整辅助分析栏宽度"
        aria-orientation="vertical"
        aria-valuemin={MIN_RAIL_WIDTH}
        aria-valuemax={maxRailWidth}
        aria-valuenow={Math.round(railWidth)}
        aria-valuetext={`${Math.round(railWidth)} 像素`}
        tabIndex={0}
        title="左右拖动调整辅助分析栏宽度，双击恢复默认宽度"
        onPointerDown={startDrag}
        onKeyDown={resizeWithKeyboard}
        onDoubleClick={() => updateRailWidth(DEFAULT_RAIL_WIDTH)}
        className="group absolute inset-y-0 z-10 hidden w-4 cursor-col-resize touch-none select-none items-stretch justify-center xl:flex focus-visible:outline-none"
        style={{ left: 'calc(100% - var(--stock-analysis-rail-width) - 1rem)' }}
      >
        <span
          aria-hidden="true"
          className={`my-2 w-px rounded-full transition-all group-hover:w-0.5 group-hover:bg-sky-400/70 group-focus-visible:w-0.5 group-focus-visible:bg-sky-400 ${isDragging ? 'w-0.5 bg-sky-400' : 'bg-border/70'}`}
        />
      </div>

      {rail}
    </div>
  )
}
