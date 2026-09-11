import {
  Bot,
  BarChart3,
  Brain,
  Check,
  CircleUserRound,
  Eye,
  EyeOff,
  History,
  Loader2,
  MessageSquare,
  MessageSquarePlus,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Play,
  Quote,
  RefreshCw,
  Send,
  Settings,
  ShieldCheck,
  Trash2,
  Wifi,
  WifiOff,
  X,
} from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import type { FormEvent, KeyboardEvent, PointerEvent as ReactPointerEvent } from 'react'
import { PageHeader } from '@/components/PageHeader'
import { HermesChartBlock } from '@/components/HermesChartBlock'
import { MarkdownRenderer } from '@/components/financials/MarkdownRenderer'
import { StockPreviewDialog } from '@/components/StockPreviewDialog'
import { api, type HermesAgentStatus, type HermesMessage, type HermesSession, type SettingsState } from '@/lib/api'
import { parseHermesRichContent } from '@/lib/hermesRichContent'
import { cn } from '@/lib/cn'
import { QK } from '@/lib/queryKeys'
import { useSettings } from '@/lib/useSharedQueries'
import { composePageContextMessage, formatFocusOption, removePageContextFocus, usePageContext } from '@/lib/pageContext'

const SESSION_STORAGE_KEY = 'one-trading.hermes.session-id'
const HISTORY_COLLAPSED_KEY = 'one-trading.hermes.history-collapsed'

function stockContextDraft(symbol: string, name: string) {
  const code = symbol.trim().toUpperCase()
  const label = name.trim()
  if (!code) return ''
  return label && label !== code
    ? `请分析 ${label} ${code}`
    : `请分析 ${code}`
}

function collectTextNodes(root: HTMLElement) {
  const nodes: Text[] = []
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  let current = walker.nextNode()
  while (current) {
    if (current instanceof Text && current.nodeValue) nodes.push(current)
    current = walker.nextNode()
  }
  return nodes
}

function findExcerptDomRange(root: HTMLElement, excerpt: string, occurrence = 0) {
  const compactTarget = excerpt.replace(/\s+/g, '')
  if (!compactTarget) return null
  type Unit = { node: Text; offset: number; ch: string }
  const units: Unit[] = []
  for (const node of collectTextNodes(root)) {
    const value = node.nodeValue ?? ''
    for (let offset = 0; offset < value.length; offset += 1) {
      const ch = value[offset]
      if (/\s/.test(ch)) continue
      units.push({ node, offset, ch })
    }
  }
  if (units.length < compactTarget.length) return null
  let seen = 0
  for (let i = 0; i <= units.length - compactTarget.length; i += 1) {
    let matched = true
    for (let j = 0; j < compactTarget.length; j += 1) {
      if (units[i + j].ch !== compactTarget[j]) {
        matched = false
        break
      }
    }
    if (!matched) continue
    if (seen === occurrence) {
      const startUnit = units[i]
      const endUnit = units[i + compactTarget.length - 1]
      const range = document.createRange()
      range.setStart(startUnit.node, startUnit.offset)
      range.setEnd(endUnit.node, endUnit.offset + 1)
      return range
    }
    seen += 1
  }
  return null
}

function wrapRangeWithMark(range: Range, quote: MessageQuote, index: number, active: boolean) {
  const mark = document.createElement('mark')
  mark.dataset.quoteId = quote.id
  mark.className = [
    'hermes-quote-mark relative mx-0.5 rounded-[4px] px-0.5 py-px',
    active ? 'bg-sky-500/25 ring-1 ring-sky-400/50' : 'bg-sky-500/15',
  ].join(' ')
  try {
    range.surroundContents(mark)
  } catch {
    mark.appendChild(range.extractContents())
    range.insertNode(mark)
  }
  const badge = document.createElement('button')
  badge.type = 'button'
  badge.dataset.quoteReveal = quote.id
  badge.setAttribute('aria-label', `查看第 ${index} 条引用`)
  badge.className = [
    'ml-1 inline-flex h-4 min-w-4 -translate-y-px items-center justify-center rounded-full px-1 align-super text-[10px] font-semibold leading-none',
    active ? 'bg-sky-600 text-white' : 'bg-sky-500 text-white hover:bg-sky-600',
  ].join(' ')
  badge.textContent = String(index)
  mark.appendChild(badge)
}

function applyQuoteMarks(
  root: HTMLElement,
  quotes: Array<{ quote: MessageQuote; index: number }>,
  highlightedQuoteId?: string,
) {
  root.querySelectorAll('button[data-quote-reveal]').forEach(button => button.remove())
  root.querySelectorAll('mark.hermes-quote-mark').forEach(mark => {
    const parent = mark.parentNode
    if (!parent) return
    while (mark.firstChild) parent.insertBefore(mark.firstChild, mark)
    parent.removeChild(mark)
    parent.normalize()
  })
  for (const item of quotes) {
    const range = findExcerptDomRange(root, item.quote.excerpt, item.quote.occurrence ?? 0)
    if (!range) continue
    wrapRangeWithMark(range, item.quote, item.index, highlightedQuoteId === item.quote.id)
  }
}

function HermesAssistantBody({
  content,
  onSymbolClick,
}: {
  content: string
  onSymbolClick?: (symbol: string) => void
}) {
  const blocks = parseHermesRichContent(content)
  return (
    <div className="space-y-3">
      {blocks.map((block, index) => {
        if (block.type === 'chart') {
          return <HermesChartBlock key={`chart-${index}`} spec={block.spec} />
        }
        return (
          <MarkdownRenderer
            key={`md-${index}`}
            content={block.text}
            onSymbolClick={onSymbolClick}
          />
        )
      })}
    </div>
  )
}

function composerBoundsElement(from: HTMLElement | null) {
  return (
    from?.closest('[aria-label="嵌入 AI 助理"]') as HTMLElement | null
    ?? from?.closest('[data-hermes-bounds]') as HTMLElement | null
    ?? null
  )
}

function placeQuoteComposer(
  markBox: DOMRect,
  boundsBox: DOMRect,
  preferSide: 'right' | 'left',
  composerSize: { width: number; height: number },
) {
  const pad = 8
  const gap = 12
  const width = Math.min(composerSize.width, Math.max(240, boundsBox.width - pad * 2))
  const height = Math.min(composerSize.height, Math.max(96, boundsBox.height - pad * 2))
  const spaceRight = boundsBox.right - markBox.right - gap - pad
  const spaceLeft = markBox.left - boundsBox.left - gap - pad
  let side: 'right' | 'left' = preferSide
  if (preferSide === 'right' && spaceRight < width && spaceLeft > spaceRight) side = 'left'
  if (preferSide === 'left' && spaceLeft < width && spaceRight > spaceLeft) side = 'right'

  let left = side === 'right' ? markBox.right + gap : markBox.left - width - gap
  let top = markBox.top
  left = Math.min(boundsBox.right - pad - width, Math.max(boundsBox.left + pad, left))
  top = Math.min(boundsBox.bottom - pad - height, Math.max(boundsBox.top + pad, top))
  return {
    side,
    width,
    top: top - boundsBox.top,
    left: left - boundsBox.left,
  }
}

function clampComposerPos(left: number, top: number, width: number, height: number, bounds: DOMRect) {
  const pad = 8
  const maxLeft = Math.max(pad, bounds.width - width - pad)
  const maxTop = Math.max(pad, bounds.height - height - pad)
  return {
    left: Math.min(maxLeft, Math.max(pad, left)),
    top: Math.min(maxTop, Math.max(pad, top)),
  }
}

function QuoteInlineComposer({
  quote,
  index,
  top,
  left,
  width,
  value,
  disabled,
  onChange,
  onSend,
  onRemove,
  onMove,
}: {
  quote: MessageQuote
  index: number
  top: number
  left: number
  width: number
  value: string
  disabled?: boolean
  onChange: (quoteId: string, value: string) => void
  onSend: (quote: MessageQuote) => void
  onRemove: (quote: MessageQuote) => void
  onMove: (quoteId: string, next: { left: number; top: number }) => void
}) {
  const shellRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<{
    pointerId: number
    startX: number
    startY: number
    originLeft: number
    originTop: number
  } | null>(null)
  const [dragging, setDragging] = useState(false)

  const onHandlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return
    const target = event.target as HTMLElement | null
    if (target?.closest('textarea, button, input, a')) return
    const host = composerBoundsElement(event.currentTarget)
    if (!host) return
    event.preventDefault()
    event.stopPropagation()
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originLeft: left,
      originTop: top,
    }
    setDragging(true)
    event.currentTarget.setPointerCapture?.(event.pointerId)
  }

  const onHandlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== event.pointerId) return
    const host = composerBoundsElement(event.currentTarget)
    const shell = shellRef.current
    if (!host || !shell) return
    const next = clampComposerPos(
      drag.originLeft + (event.clientX - drag.startX),
      drag.originTop + (event.clientY - drag.startY),
      width,
      shell.getBoundingClientRect().height,
      host.getBoundingClientRect(),
    )
    onMove(quote.id, next)
  }

  const endDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== event.pointerId) return
    dragRef.current = null
    setDragging(false)
    event.currentTarget.releasePointerCapture?.(event.pointerId)
  }

  return (
    <div
      ref={shellRef}
      role="dialog"
      aria-label={'第 ' + index + ' 条引用的追问框'}
      className="absolute z-40"
      style={{ top, left, width }}
    >
      <div
        onPointerDown={onHandlePointerDown}
        onPointerMove={onHandlePointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        className="rounded-2xl border border-border bg-surface p-2 shadow-lg"
        style={{ touchAction: 'none', cursor: dragging ? 'grabbing' : 'grab' }}
      >
        <div
          aria-label={'拖动第 ' + index + ' 条引用的追问框'}
          className="mb-1 h-4 cursor-grab rounded-full bg-elevated/80 active:cursor-grabbing"
        />
        <textarea
          id={'hermes-quote-input-' + quote.id}
          value={value}
          onChange={event => onChange(quote.id, event.target.value)}
          onClick={event => event.stopPropagation()}
          onPointerDown={event => event.stopPropagation()}
          onMouseDown={event => event.stopPropagation()}
          onKeyDown={event => {
            event.stopPropagation()
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              onSend(quote)
            }
          }}
          placeholder="针对这段继续问"
          aria-label={'第 ' + index + ' 条引用的追问'}
          rows={3}
          maxLength={12_000}
          disabled={disabled}
          autoFocus
          className="min-h-[4.5rem] w-full cursor-text resize-none bg-transparent px-2 py-1.5 text-sm leading-6 text-foreground outline-none placeholder:text-muted disabled:cursor-not-allowed"
        />
        <div className="flex items-center justify-between pt-1">
          <button
            type="button"
            onClick={event => {
              event.preventDefault()
              event.stopPropagation()
              onRemove(quote)
            }}
            aria-label={'删除第 ' + index + ' 条引用'}
            className="inline-flex h-8 w-8 items-center justify-center rounded-full text-muted hover:bg-rose-500/10 hover:text-rose-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400/40"
          >
            <X className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={event => {
              event.preventDefault()
              event.stopPropagation()
              onSend(quote)
            }}
            disabled={disabled}
            aria-label={'发送第 ' + index + ' 条引用'}
            className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-sky-600 text-white hover:bg-sky-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Send className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  )
}

function QuoteAnnotatedContent({
  quotes,
  highlightedQuoteId,
  preferSide,
  composerDrafts,
  composerDisabled,
  onRevealQuote,
  onComposerChange,
  onComposerSend,
  onComposerRemove,
  children,
}: {
  quotes: Array<{ quote: MessageQuote; index: number }>
  highlightedQuoteId?: string
  preferSide: 'right' | 'left'
  composerDrafts: Record<string, string>
  composerDisabled?: boolean
  onRevealQuote: (quote: MessageQuote) => void
  onComposerChange: (quoteId: string, value: string) => void
  onComposerSend: (quote: MessageQuote) => void
  onComposerRemove: (quote: MessageQuote) => void
  children: ReactNode
}) {
  const rootRef = useRef<HTMLDivElement>(null)
  const [anchor, setAnchor] = useState<{
    id: string
    index: number
    quote: MessageQuote
    top: number
    left: number
    width: number
    host: HTMLElement
  } | null>(null)
  const dragOffsetRef = useRef<Record<string, { left: number; top: number }>>({})

  useEffect(() => {
    const root = rootRef.current
    if (!root) return
    applyQuoteMarks(root, quotes, highlightedQuoteId)
    const quoteIds = new Set(quotes.map(item => item.quote.id))
    Object.keys(dragOffsetRef.current).forEach(id => {
      if (!quoteIds.has(id)) delete dragOffsetRef.current[id]
    })
    const active = quotes.find(item => item.quote.id === highlightedQuoteId) ?? quotes[quotes.length - 1]
    const host = composerBoundsElement(root)
    if (!active || !host) {
      setAnchor(null)
      return
    }
    const mark = root.querySelector('[data-quote-id="' + active.quote.id + '"]') as HTMLElement | null
    if (!mark) {
      setAnchor(null)
      return
    }
    const update = () => {
      const placed = placeQuoteComposer(
        mark.getBoundingClientRect(),
        host.getBoundingClientRect(),
        preferSide,
        { width: 352, height: 148 },
      )
      const dragged = dragOffsetRef.current[active.quote.id]
      const clamped = clampComposerPos(
        dragged?.left ?? placed.left,
        dragged?.top ?? placed.top,
        placed.width,
        148,
        host.getBoundingClientRect(),
      )
      setAnchor({
        id: active.quote.id,
        index: active.index,
        quote: active.quote,
        top: clamped.top,
        left: clamped.left,
        width: placed.width,
        host,
      })
    }
    update()
    const onWindowChange = () => update()
    const scrollTargets: EventTarget[] = [window]
    let node: HTMLElement | null = mark
    while (node) {
      scrollTargets.push(node)
      node = node.parentElement
    }
    scrollTargets.forEach(target => target.addEventListener('scroll', onWindowChange, true))
    window.addEventListener('resize', onWindowChange)
    return () => {
      scrollTargets.forEach(target => target.removeEventListener('scroll', onWindowChange, true))
      window.removeEventListener('resize', onWindowChange)
    }
  }, [quotes, highlightedQuoteId, preferSide, children])

  return (
    <div
      ref={rootRef}
      className="relative overflow-visible"
      onClick={event => {
        const button = (event.target as HTMLElement | null)?.closest('button[data-quote-reveal]') as HTMLButtonElement | null
        if (!button) return
        const id = button.dataset.quoteReveal
        const item = quotes.find(entry => entry.quote.id === id)
        if (!item) return
        event.preventDefault()
        event.stopPropagation()
        onRevealQuote(item.quote)
      }}
    >
      {children}
      {anchor ? createPortal(
        <QuoteInlineComposer
          quote={anchor.quote}
          index={anchor.index}
          top={anchor.top}
          left={anchor.left}
          width={anchor.width}
          value={composerDrafts[anchor.id] ?? ''}
          disabled={composerDisabled}
          onChange={onComposerChange}
          onSend={onComposerSend}
          onRemove={onComposerRemove}
          onMove={(quoteId, next) => {
            dragOffsetRef.current[quoteId] = next
            setAnchor(current => current && current.id === quoteId ? { ...current, ...next } : current)
          }}
        />,
        anchor.host,
      ) : null}
    </div>
  )
}

function visibleMessages(messages: HermesMessage[]) {
  return messages.filter(message =>
    (message.role === 'user' || message.role === 'assistant')
    && typeof message.content === 'string'
    && message.content.trim().length > 0,
  )
}

function sessionTitle(session: HermesSession) {
  return session.title?.trim() || session.preview?.trim() || '未命名对话'
}

function formatSessionTime(value: number | null | undefined) {
  if (!value || !Number.isFinite(value)) return ''
  const milliseconds = value < 1_000_000_000_000 ? value * 1000 : value
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(milliseconds))
}

const MODEL_SELECT_CLS =
  'h-7 w-[11.5rem] max-w-[58%] rounded-btn border border-border bg-base px-1.5 font-mono text-[11px] text-foreground focus:outline-none focus:ring-2 focus:ring-purple-400/40 disabled:cursor-not-allowed disabled:opacity-50'

interface MessageQuote {
  id: string
  messageKey: string
  excerpt: string
  comment?: string
  occurrence?: number
}

function normalizeQuoteText(value: string) {
  return value.replace(/\s+/g, ' ').trim()
}

function messageKey(message: HermesMessage, index: number) {
  return message.id || `${message.role}-${index}`
}

function excerptPreview(value: string, limit = 72) {
  const normalized = value.replace(/\s+/g, ' ').trim()
  if (normalized.length <= limit) return normalized
  return `${normalized.slice(0, limit).trimEnd()}…`
}

function annotationLabel(count: number) {
  return count === 1 ? '1 条引用' : `${count} 条引用`
}

function composeQuotedMessage(quotes: MessageQuote[], message: string) {
  if (quotes.length === 0) return message
  const body = quotes.map((item, index) => {
    const comment = item.comment?.trim()
    const line = `${index + 1}. ${item.excerpt}`
    return comment ? `${line}\n批注：${comment}` : line
  }).join('\n\n')
  const quoted = `引用：\n${body}`
  return message ? `${quoted}\n\n${message}` : quoted
}

function selectionInside(root: HTMLElement, selection: Selection) {
  const { anchorNode, focusNode } = selection
  if (!anchorNode || !focusNode) return false
  const contains = (node: Node) => node === root || root.contains(node)
  return contains(anchorNode) && contains(focusNode)
}

function isRetryableAssistantFailure(content: string) {
  const value = content.trim()
  if (!value || value.length > 400) return false
  return /API call failed/i.test(value)
    || /currently overloaded/i.test(value)
    || /rate limit/i.test(value)
    || /all connection attempts failed/i.test(value)
}

function subscriptionSourceLabel(status: HermesAgentStatus | null) {
  if (status?.model_source === 'server_subscription') {
    return `服务器统一 ${status.model_plan || 'AI'} 订阅`
  }
  if (status?.model_source === 'server_grok_subscription') {
    return `服务器统一 Grok 订阅${status.model_plan ? ` · ${status.model_plan}` : ''}`
  }
  return '等待服务器订阅'
}

export function HermesAgentChat({ embedded = false }: { embedded?: boolean } = {}) {
  const queryClient = useQueryClient()
  const settings = useSettings()
  const [searchParams] = useSearchParams()
  const contextSymbol = (searchParams.get('symbol') ?? '').trim().toUpperCase()
  const contextName = (searchParams.get('name') ?? '').trim()
  const contextDraft = stockContextDraft(contextSymbol, contextName)
  const pageAiId = (searchParams.get('pageAi') ?? '').trim()
  const pageContext = usePageContext()
  const [status, setStatus] = useState<HermesAgentStatus | null>(null)
  const [sessionId, setSessionId] = useState(() => (
    embedded || contextDraft ? '' : (localStorage.getItem(SESSION_STORAGE_KEY) ?? '')
  ))
  const [historyCollapsed, setHistoryCollapsed] = useState(
    () => localStorage.getItem(HISTORY_COLLAPSED_KEY) === '1',
  )
  const [statusPanelOpen, setStatusPanelOpen] = useState(false)
  const [previewSymbol, setPreviewSymbol] = useState<string | null>(null)
  const [sessions, setSessions] = useState<HermesSession[]>([])
  const [messages, setMessages] = useState<HermesMessage[]>([])
  const [input, setInput] = useState(contextDraft)
  const [isLoadingHistory, setIsLoadingHistory] = useState(() => Boolean(sessionId) && !contextDraft)
  const [isLoadingSessions, setIsLoadingSessions] = useState(true)
  const [sessionsError, setSessionsError] = useState('')
  const [openSessionMenuId, setOpenSessionMenuId] = useState('')
  const [editingSessionId, setEditingSessionId] = useState('')
  const [editingTitle, setEditingTitle] = useState('')
  const [deleteConfirmSessionId, setDeleteConfirmSessionId] = useState('')
  const [mutatingSessionId, setMutatingSessionId] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [, setSavedReportId] = useState('')
  const [error, setError] = useState('')
  const [quotes, setQuotes] = useState<MessageQuote[]>([])
  const [quoteDrafts, setQuoteDrafts] = useState<Record<string, string>>({})
  const [quoteHover, setQuoteHover] = useState(false)
  const [highlightedQuote, setHighlightedQuote] = useState<MessageQuote | null>(null)
  const [toolActivity, setToolActivity] = useState('')
  const [draftProvider, setDraftProvider] = useState('')
  const [draftModel, setDraftModel] = useState('')
  const [draftBaseUrl, setDraftBaseUrl] = useState('')
  const [draftApiKey, setDraftApiKey] = useState('')
  const [showApiKey, setShowApiKey] = useState(false)
  const [modelDraftTouched, setModelDraftTouched] = useState(false)
  const [sourceDraftTouched, setSourceDraftTouched] = useState(false)
  const [modelSaving, setModelSaving] = useState(false)
  const [sourceSaving, setSourceSaving] = useState(false)
  const [modelSaveError, setModelSaveError] = useState('')
  const [modelTesting, setModelTesting] = useState(false)
  const [modelTestResult, setModelTestResult] = useState<{ ok: boolean; msg: string } | null>(null)
  const [gatewayStarting, setGatewayStarting] = useState(false)
  const [gatewayStartError, setGatewayStartError] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const messageRefs = useRef<Record<string, HTMLElement | null>>({})
  const skipNextHistoryLoad = useRef(false)
  const initializationStarted = useRef(false)
  const settingsPanelRef = useRef<HTMLDivElement>(null)
  const stockContextHandled = useRef(false)
  useEffect(() => {
    if (!pageAiId) return
    let cancelled = false
    api.pageAiReportGet(pageAiId).then(result => {
      if (cancelled) return
      setSessionId('')
      setMessages([{ role: 'assistant', content: result.report.content }])
      setSavedReportId(result.report.id)
      setIsLoadingHistory(false)
    }).catch(() => {
      if (!cancelled) setError('打开历史分析失败')
    })
    return () => { cancelled = true }
  }, [pageAiId])


  useEffect(() => {
    if (!embedded) return
    if (pageAiId) return
    setSessionId('')
    setMessages([])
    setQuotes([])
    setQuoteDrafts({})
    setQuoteHover(false)
    setHighlightedQuote(null)
    setError('')
    setToolActivity('')
    setIsLoadingHistory(false)
    setInput('')
    setSavedReportId('')
  }, [embedded, pageAiId, pageContext?.route, pageContext?.title, pageContext?.asOf])

  useEffect(() => {
    if (!contextDraft || stockContextHandled.current) return
    stockContextHandled.current = true
    localStorage.removeItem(SESSION_STORAGE_KEY)
    setSessionId('')
    setMessages([])
    setOpenSessionMenuId('')
    setEditingSessionId('')
    setDeleteConfirmSessionId('')
    setError('')
    setToolActivity('')
    setInput(contextDraft)
    setIsLoadingHistory(false)
  }, [contextDraft])

  const loadSessions = useCallback(async () => {
    setIsLoadingSessions(true)
    setSessionsError('')
    try {
      const result = await api.hermesSessions()
      setSessions(result.sessions)
    } catch (cause) {
      setSessionsError(cause instanceof Error ? cause.message : '无法读取历史对话')
    } finally {
      setIsLoadingSessions(false)
    }
  }, [])

  const refreshStatus = useCallback(async () => {
    let nextStatus: HermesAgentStatus
    try {
      nextStatus = await api.hermesAgentStatus()
    } catch (cause) {
      nextStatus = {
        connected: false,
        profile: null,
        message: cause instanceof Error ? cause.message : '无法读取 Hermes 状态',
      }
    }
    setStatus(nextStatus)
    return nextStatus
  }, [])

  const checkConnection = useCallback(async () => {
    const nextStatus = await refreshStatus()
    if (nextStatus.connected) {
      await loadSessions()
      return nextStatus
    }
    setSessions([])
    setSessionsError('')
    setIsLoadingSessions(false)
    setIsLoadingHistory(false)
    return nextStatus
  }, [loadSessions, refreshStatus])

  const startInternalGateway = useCallback(async () => {
    setGatewayStarting(true)
    setGatewayStartError('')
    try {
      const result = await api.hermesStartGateway()
      const nextStatus = await checkConnection()
      if (!nextStatus.connected) {
        setGatewayStartError(result.message || '内部网关已尝试启动，请再检查连接')
      }
    } catch (cause) {
      setGatewayStartError(cause instanceof Error ? cause.message : '无法启动内部网关')
    } finally {
      setGatewayStarting(false)
    }
  }, [checkConnection])

  useEffect(() => {
    // React StrictMode replays mount effects in development.  A ref keeps the
    // bootstrap request idempotent while a real remount still gets fresh state.
    if (initializationStarted.current) return
    initializationStarted.current = true
    void checkConnection()
  }, [checkConnection])

  useEffect(() => {
    if (status?.connected !== true) {
      setIsLoadingHistory(false)
      return
    }
    if (!sessionId) {
      setIsLoadingHistory(false)
      return
    }
    if (skipNextHistoryLoad.current) {
      skipNextHistoryLoad.current = false
      setIsLoadingHistory(false)
      return
    }
    let cancelled = false
    setIsLoadingHistory(true)
    api.hermesSessionMessages(sessionId)
      .then(result => {
        if (!cancelled) setMessages(visibleMessages(result.messages))
      })
      .catch(() => {
        if (cancelled) return
        localStorage.removeItem(SESSION_STORAGE_KEY)
        setSessionId('')
        setMessages([])
      })
      .finally(() => {
        if (!cancelled) setIsLoadingHistory(false)
      })
    return () => { cancelled = true }
  }, [sessionId, status?.connected])

  useEffect(() => {
    if (typeof bottomRef.current?.scrollIntoView === 'function') {
      bottomRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [messages, toolActivity])

  const createSession = async () => {
    // Do not seed Hermes with the first message as a unique title. Hermes
    // rejects duplicate titles Profile-wide, which blocked repeated openers.
    const result = await api.hermesCreateSession('')
    if (!embedded) localStorage.setItem(SESSION_STORAGE_KEY, result.session.id)
    skipNextHistoryLoad.current = true
    setSessionId(result.session.id)
    setSessions(current => [
      result.session,
      ...current.filter(session => session.id !== result.session.id),
    ])
    return result.session.id
  }

  const suggestSessionTitle = (message: string, sessionKey: string) => {
    const base = message.replace(/\s+/g, ' ').trim().slice(0, 40)
    const suffix = sessionKey.slice(-6)
    if (!base) return `对话 · ${suffix}`
    return `${base} · ${suffix}`
  }

  const sendMessage = async (
    rawMessage?: string,
    options?: { retry?: boolean; skipQuotes?: boolean },
  ) => {
    const typed = (rawMessage ?? input).trim()
    const outgoingQuotes = options?.retry || options?.skipQuotes ? [] : quotes
    const message = composeQuotedMessage(outgoingQuotes, typed)

    const shouldAttachPage = embedded && Boolean(pageContext)
    const outgoing = shouldAttachPage && pageContext
      ? composePageContextMessage(pageContext, message)
      : message
    if (!outgoing || isSending || status?.connected === false) return
    const visibleMessage = message || (shouldAttachPage ? `请阅读当前${pageContext?.title ?? '页面'}` : '')
    if (!visibleMessage) return

    const lastUser = [...messages].reverse().find(item => item.role === 'user')
    const reuseUserMessage = Boolean(options?.retry) && lastUser?.content.trim() === message

    if (rawMessage == null) setInput('')
    if (!options?.retry && !options?.skipQuotes) {
      setQuotes([])
      setQuoteDrafts({})
      setQuoteHover(false)
    }
    setHighlightedQuote(null)
    setError('')
    setToolActivity('')
    setIsSending(true)

    let activeSession = sessionId
    const createdFresh = !activeSession
    const assistantId = `pending-${Date.now()}`
    let streamedContent = ''
    try {
      if (!activeSession) activeSession = await createSession()
      setMessages(current => {
        const next = [...current]
        if (reuseUserMessage) {
          while (
            next.length > 0
            && next[next.length - 1].role === 'assistant'
            && isRetryableAssistantFailure(next[next.length - 1].content)
          ) {
            next.pop()
          }
        } else {
          next.push({ role: 'user', content: visibleMessage })
        }
        next.push({ id: assistantId, role: 'assistant', content: '' })
        return next
      })

      for await (const event of api.hermesChatStream(activeSession, outgoing)) {
        if (event.type === 'delta' && event.content) {
          streamedContent += event.content
          setMessages(current => current.map(item => (
            item.id === assistantId
              ? { ...item, content: item.content + event.content }
              : item
          )))
        } else if (event.type === 'tool') {
          setToolActivity(event.name ? `正在使用 ${event.name}` : '正在整理长期记忆')
        } else if (event.type === 'error') {
          throw new Error(event.message || 'Hermes 对话失败')
        } else if (event.type === 'done') {
          setToolActivity('')
        }
      }
      if (isRetryableAssistantFailure(streamedContent)) {
        throw new Error(streamedContent.trim())
      }
      if (embedded && pageContext && streamedContent.trim()) {
        try {
          const prior = messages
            .filter(item => item.role === 'user' || item.role === 'assistant')
            .map(item => `${item.role === 'user' ? '用户' : 'AI'}：${item.content}`)
            .join('\n\n')
          const transcript = [prior, `AI：${streamedContent}`].filter(Boolean).join('\n\n')
          const saved = await api.pageAiReportSave({
            title: pageContext.title,
            route: pageContext.route,
            as_of: pageContext.asOf ?? undefined,
            focus: pageContext.focus ?? '',
            summary: pageContext.focus || pageContext.summary,
            content: transcript || streamedContent,
            session_id: activeSession,
          })
          setSavedReportId(saved.report.id)
            } catch {
        }
      }
      if (createdFresh && activeSession) {
        const nextTitle = suggestSessionTitle(typed || pageContext?.title || visibleMessage, activeSession)
        try {
          const renamed = await api.hermesRenameSession(activeSession, nextTitle)
          setSessions(current => current.map(session => (
            session.id === activeSession
              ? { ...session, ...renamed.session, title: renamed.session.title ?? nextTitle }
              : session
          )))
        } catch {
          // Preview text still identifies the conversation if rename conflicts.
        }
      }
    } catch (cause) {
      const messageText = cause instanceof Error ? cause.message : 'Hermes 对话失败'
      setMessages(current => current.map(item => (
        item.id === assistantId
          ? { ...item, content: item.content.trim() || messageText }
          : item
      )).filter(item => item.role !== 'assistant' || item.content.trim()))
      await refreshStatus()
    } finally {
      setIsSending(false)
      setToolActivity('')
      void loadSessions()
    }
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    void sendMessage()
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void sendMessage()
    }
  }

  const handleMessageMouseUp = (key: string, event: { currentTarget: HTMLElement }) => {
    const selection = window.getSelection()
    if (!selection || selection.isCollapsed) return
    const root = event.currentTarget.closest('article') ?? event.currentTarget
    if (!selectionInside(root, selection)) return
    const excerpt = normalizeQuoteText(selection.toString()).slice(0, 800)
    if (!excerpt) return
    const created: MessageQuote = {
      id: `q-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      messageKey: key,
      excerpt,
      occurrence: 0,
    }
    setQuotes(current => {
      if (current.some(item => item.messageKey === key && item.excerpt === excerpt)) {
        const existing = current.find(item => item.messageKey === key && item.excerpt === excerpt)
        if (existing) setHighlightedQuote(existing)
        return current
      }
      created.occurrence = current.filter(item => item.messageKey === key && item.excerpt === excerpt).length
      return [...current, created]
    })
    setQuoteDrafts(current => ({ ...current, [created.id]: current[created.id] ?? '' }))
    setHighlightedQuote(created)
    window.getSelection()?.removeAllRanges()
  }

  const clearQuotes = () => {
    setQuotes([])
    setQuoteDrafts({})
    setQuoteHover(false)
    setHighlightedQuote(null)
  }

  const removeQuote = (quote: MessageQuote) => {
    setQuotes(current => current.filter(item => item.id !== quote.id))
    setQuoteDrafts(current => {
      const next = { ...current }
      delete next[quote.id]
      return next
    })
    setHighlightedQuote(current => current?.id === quote.id ? null : current)
  }

  const updateQuoteDraft = (quoteId: string, value: string) => {
    setQuoteDrafts(current => ({ ...current, [quoteId]: value }))
  }

  const sendQuotedFollowUp = (quote: MessageQuote) => {
    const typed = (quoteDrafts[quote.id] ?? '').trim()
    const message = composeQuotedMessage([quote], typed)
    if (!message) return
    setQuoteDrafts(current => {
      const next = { ...current }
      delete next[quote.id]
      return next
    })
    setQuotes(current => current.filter(item => item.id !== quote.id))
    if (highlightedQuote?.id === quote.id) setHighlightedQuote(null)
    void sendMessage(message, { skipQuotes: true })
  }

  const revealQuote = (target: MessageQuote) => {
    setHighlightedQuote(target)
    const article = messageRefs.current[target.messageKey]
    const mark = article?.querySelector(`[data-quote-id="${target.id}"]`)
    const node = (mark as HTMLElement | null) ?? article
    if (node && typeof node.scrollIntoView === 'function') {
      node.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }

  const startNewConversation = () => {
    localStorage.removeItem(SESSION_STORAGE_KEY)
    setOpenSessionMenuId('')
    setEditingSessionId('')
    setDeleteConfirmSessionId('')
    setSessionId('')
    setMessages([])
    setError('')
    setQuotes([])
    setQuoteDrafts({})
    setQuoteHover(false)
    setHighlightedQuote(null)
    setToolActivity('')
  }

  const switchSession = (nextSessionId: string) => {
    if (isSending || nextSessionId === sessionId) return
    if (!embedded) localStorage.setItem(SESSION_STORAGE_KEY, nextSessionId)
    setOpenSessionMenuId('')
    setEditingSessionId('')
    setDeleteConfirmSessionId('')
    setMessages([])
    setError('')
    setQuotes([])
    setQuoteDrafts({})
    setQuoteHover(false)
    setHighlightedQuote(null)
    setToolActivity('')
    setSessionId(nextSessionId)
  }

  const startRenamingSession = (session: HermesSession) => {
    setOpenSessionMenuId('')
    setDeleteConfirmSessionId('')
    setEditingSessionId(session.id)
    setEditingTitle(sessionTitle(session))
    setError('')
  }

  const cancelSessionAction = () => {
    setOpenSessionMenuId('')
    setEditingSessionId('')
    setEditingTitle('')
    setDeleteConfirmSessionId('')
  }

  const renameSession = async (targetSessionId: string) => {
    const nextTitle = editingTitle.trim()
    if (!nextTitle) {
      setError('对话标题不能为空')
      return
    }
    setMutatingSessionId(targetSessionId)
    setError('')
    try {
      const result = await api.hermesRenameSession(targetSessionId, nextTitle)
      setSessions(current => current.map(session => (
        session.id === targetSessionId
          ? { ...session, ...result.session, title: result.session.title ?? nextTitle }
          : session
      )))
      cancelSessionAction()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '无法重命名对话')
    } finally {
      setMutatingSessionId('')
    }
  }

  const handleRenameKeyDown = (event: KeyboardEvent<HTMLInputElement>, targetSessionId: string) => {
    if (event.key === 'Enter') {
      event.preventDefault()
      void renameSession(targetSessionId)
    } else if (event.key === 'Escape') {
      event.preventDefault()
      cancelSessionAction()
    }
  }

  const deleteSession = async (targetSessionId: string) => {
    setMutatingSessionId(targetSessionId)
    setError('')
    try {
      await api.hermesDeleteSession(targetSessionId)
      setSessions(current => current.filter(session => session.id !== targetSessionId))
      if (targetSessionId === sessionId) {
        localStorage.removeItem(SESSION_STORAGE_KEY)
        setSessionId('')
        setMessages([])
        setError('')
            setToolActivity('')
      }
      cancelSessionAction()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '无法删除对话')
    } finally {
      setMutatingSessionId('')
    }
  }

  const toggleHistoryCollapsed = () => {
    setHistoryCollapsed(current => {
      const next = !current
      localStorage.setItem(HISTORY_COLLAPSED_KEY, next ? '1' : '0')
      return next
    })
  }

  const isAdmin = settings.data?.is_admin === true
  const canStartGateway = isAdmin && status?.can_start_gateway === true && status?.connected !== true
  const cloudManaged = settings.data?.ai_access?.mode === 'cloud_subscription'
  const subscriptionSources = settings.data?.ai_subscriptions ?? []
  const canManageModel = isAdmin && cloudManaged && subscriptionSources.length > 0
  const activeProvider = settings.data?.ai_access?.provider || ''
  const activeModel = settings.data?.ai_access?.model || status?.model || ''
  const selectedSource = subscriptionSources.find(item => item.provider === draftProvider) ?? subscriptionSources[0]
  const sourceModels = selectedSource?.models ?? []
  const customModel = !!draftModel && !sourceModels.includes(draftModel)
  const modelDirty = canManageModel && (
    draftProvider !== activeProvider || draftModel !== activeModel
  )
  const sourceDirty = canManageModel && sourceDraftTouched && (
    draftBaseUrl.trim() !== (selectedSource?.base_url || '').trim()
    || draftApiKey.trim().length > 0
  )

  useEffect(() => {
    if (!cloudManaged || modelDraftTouched) return
    const nextProvider = settings.data?.ai_access?.provider
      || settings.data?.ai_subscriptions?.find(item => item.active)?.provider
      || ''
    const nextModel = settings.data?.ai_access?.model || status?.model || ''
    if (nextProvider) setDraftProvider(nextProvider)
    if (nextModel) setDraftModel(nextModel)
  }, [
    cloudManaged,
    modelDraftTouched,
    settings.data?.ai_access?.provider,
    settings.data?.ai_access?.model,
    settings.data?.ai_subscriptions,
    status?.model,
  ])

  useEffect(() => {
    if (!canManageModel || sourceDraftTouched || !selectedSource) return
    setDraftBaseUrl(selectedSource.base_url || selectedSource.default_base_url || '')
    setDraftApiKey('')
    setShowApiKey(false)
  }, [canManageModel, selectedSource, sourceDraftTouched, settings.data?.ai_subscriptions])

  useEffect(() => {
    if (!statusPanelOpen) return
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target
      if (!(target instanceof Node)) return
      if (settingsPanelRef.current?.contains(target)) return
      setStatusPanelOpen(false)
    }
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') setStatusPanelOpen(false)
    }
    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [statusPanelOpen])

  const applyServerModel = async () => {
    if (!canManageModel || !draftProvider || !draftModel.trim()) return
    setModelSaving(true)
    setModelSaveError('')
    setModelTestResult(null)
    try {
      await api.selectAiSubscription({ provider: draftProvider, model: draftModel.trim() })
      setModelDraftTouched(false)
      await queryClient.invalidateQueries({ queryKey: QK.settings })
      await checkConnection()
    } catch (cause) {
      setModelSaveError(cause instanceof Error ? cause.message : '无法更新模型')
    } finally {
      setModelSaving(false)
    }
  }

  const saveProviderSource = async () => {
    if (!canManageModel || !draftProvider) return
    setSourceSaving(true)
    setModelSaveError('')
    setModelTestResult(null)
    try {
      const result = await api.saveAiSubscriptionSource({
        provider: draftProvider,
        base_url: draftBaseUrl.trim() || undefined,
        api_key: draftApiKey.trim() || undefined,
      })
      setDraftApiKey('')
      setSourceDraftTouched(false)
      if (result.base_url) setDraftBaseUrl(result.base_url)
      queryClient.setQueryData(QK.settings, (prev: SettingsState | undefined) => prev ? {
        ...prev,
        ai_access: result.ai_access ?? prev.ai_access,
        ai_subscriptions: result.ai_subscriptions ?? prev.ai_subscriptions,
      } : prev)
      await queryClient.invalidateQueries({ queryKey: QK.settings })
      setModelTestResult({
        ok: true,
        msg: `已保存 ${selectedSource?.label || draftProvider} 的 URL/Key`,
      })
    } catch (cause) {
      setModelSaveError(cause instanceof Error ? cause.message : '无法保存提供商配置')
    } finally {
      setSourceSaving(false)
    }
  }

  const testServerModel = async () => {
    if (!canManageModel || !draftProvider || !draftModel.trim()) return
    setModelTesting(true)
    setModelTestResult(null)
    setModelSaveError('')
    try {
      const result = await api.testAiSubscription({
        provider: draftProvider,
        model: draftModel.trim(),
        base_url: draftBaseUrl.trim() || undefined,
        api_key: draftApiKey.trim() || undefined,
      })
      if (result.ok) {
        setModelTestResult({
          ok: true,
          msg: `连通成功 · ${result.label || draftProvider} · ${result.model || draftModel}`,
        })
      } else {
        setModelTestResult({
          ok: false,
          msg: result.error || '连通失败',
        })
      }
    } catch (cause) {
      setModelTestResult({
        ok: false,
        msg: cause instanceof Error ? cause.message : '连通失败',
      })
    } finally {
      setModelTesting(false)
    }
  }

  const connected = status?.connected === true
  const subscriptionName = status?.model_source === 'server_subscription'
    ? (status.model_plan || 'AI')
    : 'Grok'

  return (
    <div data-hermes-bounds data-testid="hermes-bounds" className="relative flex h-full min-h-0 flex-col overflow-hidden bg-base">
      {embedded ? null : (
      <PageHeader
        title="Hermes Agent"
        subtitle="当前账户专属个人 AI 助理"
        className="shrink-0"
        right={
          <button
            type="button"
            onClick={startNewConversation}
            disabled={isSending}
            className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-surface px-3 py-1.5 text-xs font-medium text-secondary transition-colors hover:border-purple-400/35 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/40 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <MessageSquarePlus className="h-3.5 w-3.5" />
            新对话
          </button>
        }
      />
      )}

      <div className={cn(
        'grid min-h-0 flex-1',
        embedded
          ? 'grid-cols-1 grid-rows-[minmax(0,1fr)]'
          : cn(
            'grid-cols-1 grid-rows-[auto_minmax(0,1fr)] lg:grid-rows-1',
            historyCollapsed
              ? 'lg:grid-cols-[4rem_minmax(0,1fr)]'
              : 'lg:grid-cols-[15.5rem_minmax(0,1fr)]',
          ),
      )}>
        <aside
          aria-label="历史对话"
          className={cn(
            'flex min-h-0 flex-col overflow-visible border-b border-border bg-surface/45 lg:border-b-0 lg:border-r',
            embedded && 'hidden',
          )}
        >
          <div className={cn(
            'flex shrink-0 items-center gap-2 border-b border-border px-4 py-3',
            historyCollapsed && 'lg:flex-col lg:px-2',
          )}>
            <History className="h-4 w-4 text-muted" />
            <h2 className={cn('text-sm font-semibold text-foreground', historyCollapsed && 'lg:sr-only')}>历史对话</h2>
            <span className={cn('font-mono text-[10px] text-muted', historyCollapsed && 'lg:hidden')}>{sessions.length}</span>
            <button
              type="button"
              onClick={() => void loadSessions()}
              disabled={isLoadingSessions}
              aria-label="刷新历史对话"
              className={cn(
                'ml-1 inline-flex h-8 w-8 items-center justify-center rounded-btn text-muted transition-colors hover:bg-elevated hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/40 disabled:cursor-not-allowed disabled:opacity-50',
                historyCollapsed && 'lg:ml-0',
              )}
            >
              <RefreshCw className={cn('h-3.5 w-3.5', isLoadingSessions && 'animate-spin')} />
            </button>
            <button
              type="button"
              onClick={toggleHistoryCollapsed}
              aria-controls="hermes-history-list"
              aria-expanded={!historyCollapsed}
              aria-label={historyCollapsed ? '展开历史对话栏' : '折叠历史对话栏'}
              className={cn(
                'ml-auto hidden h-8 w-8 items-center justify-center rounded-btn text-muted transition-colors hover:bg-elevated hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/40 lg:inline-flex',
                historyCollapsed && 'lg:ml-0',
              )}
            >
              {historyCollapsed
                ? <PanelLeftOpen className="h-3.5 w-3.5" />
                : <PanelLeftClose className="h-3.5 w-3.5" />}
            </button>
          </div>

          <nav
            id="hermes-history-list"
            aria-label="Hermes 历史 Session"
            className={cn(
              'flex min-h-0 gap-2 overflow-x-auto px-4 py-3 lg:flex-1 lg:flex-col lg:overflow-x-hidden lg:overflow-y-auto',
              historyCollapsed && 'lg:px-2',
            )}
          >
            {isLoadingSessions ? (
              <>
                <div className="h-[4.5rem] min-w-52 animate-pulse rounded-btn bg-elevated lg:min-w-0" />
                <div className="h-[4.5rem] min-w-52 animate-pulse rounded-btn bg-elevated lg:min-w-0" />
              </>
            ) : sessionsError ? (
              <div className="min-w-52 py-3 text-xs leading-5 text-muted lg:min-w-0">
                <p>历史对话暂时不可用</p>
                <button
                  type="button"
                  onClick={() => void loadSessions()}
                  className="mt-1 font-medium text-purple-600 hover:text-purple-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/40 dark:text-purple-300"
                >
                  重新加载
                </button>
              </div>
            ) : sessions.length === 0 ? (
              <div className="min-w-52 py-3 text-xs leading-5 text-muted lg:min-w-0">
                发送第一条消息后，对话会保存在这里。
              </div>
            ) : (
              sessions.map(session => {
                const active = session.id === sessionId
                const title = sessionTitle(session)
                const isEditing = editingSessionId === session.id
                const isConfirmingDelete = deleteConfirmSessionId === session.id
                const isMutating = mutatingSessionId === session.id
                return (
                  <div
                    key={session.id}
                    title={historyCollapsed ? title : undefined}
                    className={cn(
                      'relative min-w-52 rounded-btn border transition-colors lg:min-w-0',
                      active
                        ? 'border-purple-400/35 bg-purple-500/[0.08] text-foreground'
                        : 'border-transparent text-secondary hover:border-border hover:bg-elevated hover:text-foreground',
                    )}
                  >
                    {isEditing ? (
                      <div className="p-2.5">
                        <label className="sr-only" htmlFor={`hermes-session-title-${session.id}`}>
                          重命名对话标题
                        </label>
                        <input
                          id={`hermes-session-title-${session.id}`}
                          autoFocus
                          value={editingTitle}
                          maxLength={120}
                          onChange={event => setEditingTitle(event.target.value)}
                          onKeyDown={event => handleRenameKeyDown(event, session.id)}
                          disabled={isMutating}
                          className="h-8 w-full rounded-btn border border-purple-400/40 bg-base px-2.5 text-xs text-foreground outline-none focus:ring-2 focus:ring-purple-400/30 disabled:opacity-60"
                        />
                        <div className="mt-2 flex justify-end gap-1.5">
                          <button
                            type="button"
                            onClick={cancelSessionAction}
                            disabled={isMutating}
                            aria-label="取消重命名"
                            className="inline-flex h-7 items-center gap-1 rounded-btn px-2 text-[11px] text-muted transition-colors hover:bg-elevated hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/40 disabled:opacity-50"
                          >
                            <X className="h-3 w-3" />
                            取消
                          </button>
                          <button
                            type="button"
                            onClick={() => void renameSession(session.id)}
                            disabled={isMutating || !editingTitle.trim()}
                            aria-label="保存对话标题"
                            className="inline-flex h-7 items-center gap-1 rounded-btn bg-purple-500 px-2 text-[11px] font-medium text-white transition-colors hover:bg-purple-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/40 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            <Check className="h-3 w-3" />
                            保存
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => switchSession(session.id)}
                          disabled={isSending || isMutating}
                          aria-current={active ? 'page' : undefined}
                          aria-label={`切换到历史对话：${title}`}
                          className={cn(
                            'block w-full px-3 py-2.5 pr-10 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-purple-400/40 disabled:cursor-not-allowed disabled:opacity-50',
                            historyCollapsed && 'lg:px-2 lg:pr-2',
                          )}
                        >
                          <span className={cn('flex items-center gap-2', historyCollapsed && 'lg:justify-center')}>
                            <MessageSquare className={cn('h-3.5 w-3.5 shrink-0', active ? 'text-purple-500 dark:text-purple-300' : 'text-muted')} />
                            <span className={cn('truncate text-xs font-medium', historyCollapsed && 'lg:sr-only')}>{title}</span>
                          </span>
                          <span className={cn(
                            'mt-1.5 flex items-center justify-between gap-2 pl-5 font-mono text-[10px] text-muted',
                            historyCollapsed && 'lg:hidden',
                          )}>
                            <span>{session.message_count ?? 0} 条消息</span>
                            <span>{formatSessionTime(session.last_active ?? session.started_at)}</span>
                          </span>
                        </button>

                        <button
                          type="button"
                          onClick={() => {
                            setDeleteConfirmSessionId('')
                            setOpenSessionMenuId(current => current === session.id ? '' : session.id)
                          }}
                          disabled={isSending || isMutating}
                          aria-expanded={openSessionMenuId === session.id || isConfirmingDelete}
                          aria-label={`打开“${title}”对话菜单`}
                          className={cn(
                            'absolute right-1.5 top-1.5 inline-flex h-7 w-7 items-center justify-center rounded-btn text-muted transition-colors hover:bg-surface hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/40 disabled:opacity-50',
                            historyCollapsed && 'lg:hidden',
                          )}
                        >
                          <MoreHorizontal className="h-4 w-4" />
                        </button>

                        {openSessionMenuId === session.id && (
                          <div
                            role="menu"
                            aria-label={`“${title}”对话操作`}
                            className="absolute right-1.5 top-9 z-40 w-36 rounded-btn border border-border bg-surface p-1 shadow-lg"
                          >
                            <button
                              type="button"
                              role="menuitem"
                              onClick={() => startRenamingSession(session)}
                              className="flex w-full items-center gap-2 rounded-btn px-2.5 py-2 text-left text-xs text-secondary transition-colors hover:bg-elevated hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/40"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                              重命名
                            </button>
                            <button
                              type="button"
                              role="menuitem"
                              onClick={() => {
                                setOpenSessionMenuId('')
                                setDeleteConfirmSessionId(session.id)
                              }}
                              className="flex w-full items-center gap-2 rounded-btn px-2.5 py-2 text-left text-xs text-rose-600 transition-colors hover:bg-rose-500/[0.08] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400/40 dark:text-rose-300"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                              删除对话
                            </button>
                          </div>
                        )}

                        {isConfirmingDelete && (
                          <div
                            role="dialog"
                            aria-label={`确认删除“${title}”对话`}
                            className="absolute right-1.5 top-9 z-40 w-48 rounded-btn border border-rose-400/25 bg-surface p-3 shadow-lg"
                          >
                            <p className="text-xs font-medium text-foreground">删除这条对话？</p>
                            <p className="mt-1 text-[11px] leading-4 text-muted">消息记录会从 Hermes 中永久删除。</p>
                            <div className="mt-2.5 flex justify-end gap-1.5">
                              <button
                                type="button"
                                onClick={cancelSessionAction}
                                disabled={isMutating}
                                className="rounded-btn px-2 py-1.5 text-[11px] text-muted hover:bg-elevated hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/40 disabled:opacity-50"
                              >
                                取消
                              </button>
                              <button
                                type="button"
                                onClick={() => void deleteSession(session.id)}
                                disabled={isMutating}
                                aria-label={`确认删除“${title}”对话`}
                                className="rounded-btn bg-rose-600 px-2 py-1.5 text-[11px] font-medium text-white hover:bg-rose-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400/40 disabled:cursor-not-allowed disabled:opacity-50"
                              >
                                {isMutating ? '删除中…' : '确认删除'}
                              </button>
                            </div>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )
              })
            )}
          </nav>

          <div
            ref={settingsPanelRef}
            className={cn(
              'relative z-20 shrink-0 overflow-visible border-t border-border p-3',
              historyCollapsed && 'lg:p-2',
            )}
          >
            {statusPanelOpen && (
              <section
                id="hermes-agent-settings"
                aria-label="Agent 设置详情"
                className={cn(
                  'absolute bottom-[calc(100%+0.5rem)] left-3 z-30 w-[min(22rem,calc(100vw-1.5rem))] rounded-card border border-border bg-surface p-4 shadow-xl',
                  historyCollapsed && 'lg:left-2',
                )}
              >
                <div className="flex items-center gap-2 border-b border-border pb-3">
                  <Settings className="h-4 w-4 text-muted" />
                  <h3 className="text-sm font-semibold text-foreground">Agent 设置</h3>
                </div>

                <div className="mt-3 flex items-center justify-between gap-3 text-xs">
                  <span className="text-muted">连接状态</span>
                  <span className={cn(
                    'inline-flex items-center gap-1.5 font-medium',
                    connected ? 'text-emerald-600 dark:text-emerald-300' : 'text-rose-600 dark:text-rose-300',
                  )}>
                    {connected ? <Wifi className="h-3.5 w-3.5" /> : <WifiOff className="h-3.5 w-3.5" />}
                    {status === null ? '正在检查' : connected ? 'Profile 已连接' : (status?.gateway_startable ? '内部网关未运行' : 'Profile 未连接')}
                  </span>
                </div>
                {status?.message && !connected ? (
                  <p className="mt-2 text-[11px] leading-relaxed text-muted">{status.message}</p>
                ) : null}
                {gatewayStartError ? (
                  <p className="mt-2 text-[11px] break-all text-rose-600 dark:text-rose-300">{gatewayStartError}</p>
                ) : null}

                <dl className="mt-3 space-y-2.5 text-xs">
                  <div className="flex items-center justify-between gap-4">
                    <dt className="text-muted">Profile</dt>
                    <dd className="font-mono text-secondary">{status?.profile || '尚未分配'}</dd>
                  </div>
                  {canManageModel ? (
                    <>
                      <div className="flex items-center justify-between gap-3">
                        <dt className="shrink-0 text-muted">模型提供商</dt>
                        <dd>
                          <select
                            aria-label="选择模型提供商"
                            value={draftProvider || selectedSource?.provider || ''}
                            onChange={event => {
                              const nextProvider = event.target.value
                              const nextSource = subscriptionSources.find(item => item.provider === nextProvider)
                              setModelDraftTouched(true)
                              setSourceDraftTouched(false)
                              setDraftProvider(nextProvider)
                              setDraftModel(
                                nextProvider === activeProvider && activeModel
                                  ? activeModel
                                  : (nextSource?.default_model || nextSource?.models[0] || ''),
                              )
                              setDraftBaseUrl(nextSource?.base_url || nextSource?.default_base_url || '')
                              setDraftApiKey('')
                              setShowApiKey(false)
                              setModelSaveError('')
                              setModelTestResult(null)
                            }}
                            className={MODEL_SELECT_CLS}
                          >
                            {subscriptionSources.map(source => (
                              <option key={source.provider} value={source.provider}>
                                {source.label}{source.ready ? '' : '（未就绪）'}
                              </option>
                            ))}
                          </select>
                        </dd>
                      </div>
                      <div className="space-y-1.5">
                        <label className="block text-[11px] text-muted" htmlFor="hermes-provider-base-url">
                          提供商 URL
                        </label>
                        <input
                          id="hermes-provider-base-url"
                          type="text"
                          aria-label="模型提供商 URL"
                          value={draftBaseUrl}
                          onChange={event => {
                            setSourceDraftTouched(true)
                            setDraftBaseUrl(event.target.value)
                            setModelSaveError('')
                            setModelTestResult(null)
                          }}
                          placeholder={selectedSource?.default_base_url || 'https://…/v1'}
                          className="h-7 w-full rounded-btn border border-border bg-base px-2 font-mono text-[11px] text-foreground placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-purple-400/40"
                        />
                      </div>
                      <div className="space-y-1.5">
                        <label className="block text-[11px] text-muted" htmlFor="hermes-provider-api-key">
                          模型 Key
                        </label>
                        <div className="relative">
                          <input
                            id="hermes-provider-api-key"
                            type={showApiKey ? 'text' : 'password'}
                            aria-label="模型 API Key"
                            value={draftApiKey}
                            onChange={event => {
                              setSourceDraftTouched(true)
                              setDraftApiKey(event.target.value)
                              setModelSaveError('')
                              setModelTestResult(null)
                            }}
                            placeholder={
                              selectedSource?.api_key_masked
                                ? `已保存 ${selectedSource.api_key_masked}，留空不改`
                                : selectedSource?.has_api_key
                                  ? '已保存 Key，留空不改'
                                  : '粘贴 API Key'
                            }
                            className="h-7 w-full rounded-btn border border-border bg-base px-2 pr-8 font-mono text-[11px] text-foreground placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-purple-400/40"
                            autoComplete="off"
                          />
                          <button
                            type="button"
                            aria-label={showApiKey ? '隐藏 API Key' : '显示 API Key'}
                            onClick={() => setShowApiKey(current => !current)}
                            className="absolute inset-y-0 right-0 flex w-8 items-center justify-center text-muted hover:text-foreground"
                          >
                            {showApiKey ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                          </button>
                        </div>
                      </div>
                      <div className="flex flex-col gap-2">
                        <div className="flex items-center justify-between gap-3">
                          <dt className="shrink-0 text-muted">模型</dt>
                          <dd>
                            <select
                              aria-label="选择模型"
                              value={customModel ? '__custom__' : (draftModel || selectedSource?.default_model || '')}
                              onChange={event => {
                                const value = event.target.value
                                setModelDraftTouched(true)
                                setModelSaveError('')
                                setModelTestResult(null)
                                if (value === '__custom__') {
                                  if (sourceModels.includes(draftModel)) setDraftModel('')
                                  return
                                }
                                setDraftModel(value)
                              }}
                              className={MODEL_SELECT_CLS}
                            >
                              {sourceModels.map(modelId => (
                                <option key={modelId} value={modelId}>{modelId}</option>
                              ))}
                              <option value="__custom__">自定义…</option>
                            </select>
                          </dd>
                        </div>
                        {customModel && (
                          <input
                            type="text"
                            aria-label="自定义模型 ID"
                            value={draftModel}
                            onChange={event => {
                              setModelDraftTouched(true)
                              setDraftModel(event.target.value)
                              setModelSaveError('')
                              setModelTestResult(null)
                            }}
                            placeholder={selectedSource?.default_model || '模型 ID'}
                            className="h-7 w-full rounded-btn border border-border bg-base px-2 font-mono text-[11px] text-foreground placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-purple-400/40"
                          />
                        )}
                      </div>
                      <p className="text-[11px] leading-relaxed text-muted">
                        先保存 URL/Key，再测试连通，最后应用到全部账户。Key 只保存在服务器，普通用户看不到也不能改。
                      </p>
                      {modelTestResult ? (
                        <p className={cn(
                          'text-[11px] break-all',
                          modelTestResult.ok
                            ? 'text-emerald-600 dark:text-emerald-300'
                            : 'text-rose-600 dark:text-rose-300',
                        )}>
                          {modelTestResult.msg}
                        </p>
                      ) : null}
                      {modelSaveError ? (
                        <p className="text-[11px] break-all text-rose-600 dark:text-rose-300">{modelSaveError}</p>
                      ) : null}
                      <button
                        type="button"
                        onClick={() => void saveProviderSource()}
                        disabled={
                          !sourceDirty
                          || sourceSaving
                          || modelTesting
                          || modelSaving
                          || !draftProvider
                          || (!draftBaseUrl.trim() && !draftApiKey.trim())
                        }
                        className="inline-flex h-8 w-full items-center justify-center gap-1.5 rounded-btn border border-border bg-base px-3 text-xs font-medium text-secondary transition-colors hover:bg-elevated hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/40 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        {sourceSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                        {sourceSaving ? '正在保存' : sourceDirty ? '保存提供商配置' : '提供商配置已保存'}
                      </button>
                      <button
                        type="button"
                        onClick={() => void testServerModel()}
                        disabled={modelTesting || modelSaving || sourceSaving || !draftProvider || !draftModel.trim()}
                        className="inline-flex h-8 w-full items-center justify-center gap-1.5 rounded-btn border border-border bg-base px-3 text-xs font-medium text-secondary transition-colors hover:bg-elevated hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/40 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        {modelTesting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wifi className="h-3.5 w-3.5" />}
                        {modelTesting ? '正在测试' : '测试连通'}
                      </button>
                      <button
                        type="button"
                        onClick={() => void applyServerModel()}
                        disabled={!modelDirty || modelSaving || modelTesting || sourceSaving || !draftModel.trim()}
                        className="inline-flex h-8 w-full items-center justify-center gap-1.5 rounded-btn border border-border bg-base px-3 text-xs font-medium text-secondary transition-colors hover:bg-elevated hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/40 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        {modelSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                        {modelSaving ? '正在应用' : modelDirty ? '应用到全部账户' : '已是当前配置'}
                      </button>
                    </>
                  ) : (
                    <>
                      <div className="flex items-center justify-between gap-4">
                        <dt className="text-muted">模型</dt>
                        <dd className="font-mono text-secondary">{status?.model || '等待连接'}</dd>
                      </div>
                      <div className="flex items-center justify-between gap-4">
                        <dt className="text-muted">模型来源</dt>
                        <dd className="text-right text-secondary">{subscriptionSourceLabel(status)}</dd>
                      </div>
                      {cloudManaged ? (
                        <p className="text-[11px] leading-relaxed text-muted">由管理员统一配置，当前账户不能修改。</p>
                      ) : null}
                    </>
                  )}
                  <div className="flex items-center justify-between gap-4">
                    <dt className="inline-flex items-center gap-1.5 text-muted">
                      <Brain className="h-3.5 w-3.5" />
                      长期记忆
                    </dt>
                    <dd className="text-secondary">
                      {status?.memory_provider
                        ? (status.memory_provider === 'holographic' ? 'Holographic' : status.memory_provider)
                        : '独立记忆'}
                    </dd>
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <dt className="inline-flex items-center gap-1.5 text-muted">
                      <ShieldCheck className="h-3.5 w-3.5" />
                      用户台数据
                    </dt>
                    <dd className="text-secondary">
                      {status?.data_tool_enabled
                        ? `${status.data_view_count ?? 0} 个只读视图`
                        : '仅记忆与会话检索'}
                    </dd>
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <dt className="inline-flex items-center gap-1.5 text-muted">
                      <BarChart3 className="h-3.5 w-3.5" />
                      图表 Skill
                    </dt>
                    <dd className="text-secondary">
                      {status?.lieflat_charts_enabled ? 'Lieflat Charts' : '未启用'}
                    </dd>
                  </div>
                </dl>

                {canStartGateway ? (
                  <button
                    type="button"
                    onClick={() => void startInternalGateway()}
                    disabled={gatewayStarting}
                    className="mt-4 inline-flex w-full items-center justify-center gap-1.5 rounded-btn border border-purple-400/40 bg-purple-500/10 px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-purple-500/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/40 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {gatewayStarting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                    {gatewayStarting ? '正在启动内部网关' : '启动内部网关'}
                  </button>
                ) : null}
                <button
                  type="button"
              onClick={() => void checkConnection()}
                  className={cn(
                    'inline-flex w-full items-center justify-center gap-1.5 rounded-btn border border-border bg-base px-3 py-2 text-xs font-medium text-secondary transition-colors hover:bg-elevated hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/40',
                    canStartGateway ? 'mt-2' : 'mt-4',
                  )}
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  重新检查连接
                </button>
              </section>
            )}

            <button
              type="button"
              onClick={() => setStatusPanelOpen(current => !current)}
              aria-controls="hermes-agent-settings"
              aria-expanded={statusPanelOpen}
              aria-label={statusPanelOpen ? '关闭 Agent 设置' : '打开 Agent 设置'}
              className={cn(
                'flex h-9 w-full items-center gap-2 rounded-btn px-2.5 text-xs font-medium text-secondary transition-colors hover:bg-elevated hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/40',
                historyCollapsed && 'lg:justify-center lg:px-0',
              )}
            >
              <Settings className="h-4 w-4 shrink-0" />
              <span className={cn(historyCollapsed && 'lg:sr-only')}>Agent 设置</span>
              <span className={cn(
                'ml-auto h-1.5 w-1.5 rounded-full',
                connected ? 'bg-emerald-500' : status === null ? 'bg-muted' : 'bg-rose-500',
                historyCollapsed && 'lg:hidden',
              )} />
            </button>
          </div>
        </aside>

        <main className={cn('flex min-h-0 min-w-0 flex-col', embedded ? 'px-3' : 'px-4 lg:px-6')}>
          {!connected && status !== null && (
            <div role="alert" className="mt-4 shrink-0 rounded-btn border border-rose-400/25 bg-rose-500/[0.06] px-4 py-3 text-sm text-rose-700 dark:text-rose-200">
              <p>{status.message || '当前账户的 Hermes Profile 暂不可用'}</p>
              {status.detail && status.detail !== status.message ? (
                <p className="mt-1 text-xs opacity-80">{status.detail}</p>
              ) : null}
              {canStartGateway ? (
                <button
                  type="button"
                  onClick={() => {
                    setStatusPanelOpen(true)
                    void startInternalGateway()
                  }}
                  disabled={gatewayStarting}
                  className="mt-3 inline-flex items-center gap-1.5 rounded-btn border border-rose-400/30 bg-base px-3 py-1.5 text-xs font-medium text-rose-700 transition-colors hover:bg-rose-500/10 dark:text-rose-200"
                >
                  {gatewayStarting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                  {gatewayStarting ? '正在启动内部网关' : '启动内部网关'}
                </button>
              ) : null}
            </div>
          )}

          <section aria-label="Hermes 对话" className="flex min-h-0 flex-1 flex-col pt-4">
            <div className="min-h-0 flex-1 space-y-5 overflow-y-auto pr-1">
              {isLoadingHistory ? (
                <div className="space-y-3" aria-label="正在读取对话历史">
                  <div className="h-16 animate-pulse rounded-btn bg-elevated" />
                  <div className="ml-auto h-12 w-3/4 animate-pulse rounded-btn bg-elevated" />
                </div>
              ) : messages.length === 0 ? (
                <div className={cn('mx-auto flex max-w-xl flex-col items-center text-center', embedded ? 'py-8' : 'py-16')}>
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-purple-500/10 text-purple-600 ring-1 ring-purple-400/20 dark:text-purple-300">
                    <Bot className="h-5 w-5" />
                  </div>
                  <h2 className="mt-4 text-base font-semibold text-foreground">
                    {embedded && pageContext ? `询问当前${pageContext.title}` : '开始和你的专属 Agent 对话'}
                  </h2>
                  <p className="mt-2 max-w-[65ch] text-sm leading-6 text-secondary">
                    {embedded && pageContext
                      ? '发送后会带上当前页正在看的筛选、摘要和可见条目。Agent 先读这份快照，不够再查数据台。'
                      : `这是当前账户独立的 Hermes Profile。所有 Profile 统一使用服务器的 ${subscriptionName} 订阅，但 Session、长期记忆、内部凭据和可见数据仍按账户隔离。它可以读取该账户有权访问的行情、自选、K 线、财务、指数、策略、监控、数据目录和已保存报告；账户交易和当前尚未进入运行面的公告数据不在本次范围。`}
                  </p>
                  {embedded ? null : (
                    <p className="mt-2 max-w-[65ch] text-xs leading-6 text-muted">
                      稳定关注面会记入当前账户 Profile，新对话会先读；分析框架和出图规则不会被自动改。
                    </p>
                  )}
                </div>
              ) : (
                messages.map((message, index) => {
                  const isUser = message.role === 'user'
                  const key = messageKey(message, index)
                  const failedReply = !isUser && isRetryableAssistantFailure(message.content)
                  const retryPrompt = failedReply
                    ? [...messages.slice(0, index)].reverse().find(item => item.role === 'user')?.content.trim() || ''
                    : ''
                  const messageQuotes = quotes
                    .map((quote, quoteIndex) => ({ quote, index: quoteIndex + 1 }))
                    .filter(item => item.quote.messageKey === key)
                  const isQuotedSource = highlightedQuote?.messageKey === key || messageQuotes.length > 0
                  return (
                    <article
                      key={key}
                      ref={node => { messageRefs.current[key] = node }}
                      aria-label={isUser ? '你的消息' : failedReply ? 'Hermes 发送失败' : 'Hermes 的回复'}
                      data-quoted={isQuotedSource ? 'true' : undefined}
                      className={cn('flex gap-3', isUser && 'flex-row-reverse')}
                    >
                      <div className={cn(
                        'mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg',
                        isUser
                          ? 'bg-sky-500/10 text-sky-600 dark:text-sky-300'
                          : 'bg-purple-500/10 text-purple-600 dark:text-purple-300',
                      )}>
                        {isUser ? <CircleUserRound className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                      </div>
                      <div className="relative max-w-[88%] overflow-visible lg:max-w-[75ch]">
                        <div
                          onMouseUp={event => handleMessageMouseUp(key, event)}
                          className={cn(
                          'rounded-btn px-4 py-3 text-sm leading-6',
                          isUser
                            ? 'whitespace-pre-wrap bg-sky-500/[0.09] text-foreground'
                            : failedReply
                              ? 'whitespace-pre-wrap border border-rose-400/25 bg-rose-500/[0.06] text-rose-700 dark:text-rose-200'
                              : 'border border-border bg-surface text-secondary',
                        )}>
                          {message.content ? (
                            <QuoteAnnotatedContent
                              quotes={messageQuotes}
                              highlightedQuoteId={highlightedQuote?.id}
                              preferSide={isUser ? 'left' : 'right'}
                              composerDrafts={quoteDrafts}
                              composerDisabled={isSending || !connected}
                              onRevealQuote={revealQuote}
                              onComposerChange={updateQuoteDraft}
                              onComposerSend={sendQuotedFollowUp}
                              onComposerRemove={removeQuote}
                            >
                              {isUser || failedReply
                                ? message.content
                                : <HermesAssistantBody content={message.content} onSymbolClick={setPreviewSymbol} />}
                            </QuoteAnnotatedContent>
                          ) : (
                            <span className="inline-flex items-center gap-1.5 text-muted">
                              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
                              正在思考
                            </span>
                          )}
                        </div>
                        {failedReply && retryPrompt ? (
                          <button
                            type="button"
                            onClick={() => void sendMessage(retryPrompt, { retry: true })}
                            disabled={isSending || !connected}
                            aria-label="重新发送这条指令"
                            className="mt-2 inline-flex items-center gap-1.5 rounded-btn border border-rose-400/25 bg-surface px-2.5 py-1.5 text-xs font-medium text-rose-700 transition-colors hover:bg-rose-500/[0.08] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400/40 disabled:cursor-not-allowed disabled:opacity-50 dark:text-rose-200"
                          >
                            <RefreshCw className="h-3.5 w-3.5" />
                            重新发送
                          </button>
                        ) : null}
                      </div>
                    </article>
                  )
                })
              )}
              {toolActivity && <p className="pl-11 text-xs text-muted">{toolActivity}</p>}
              <div ref={bottomRef} />
            </div>

            {error && <p role="alert" className="mt-3 shrink-0 text-sm text-rose-600 dark:text-rose-300">{error}</p>}

            {quotes.length > 0 && (
              <div
                aria-label="引用原文"
                className="relative mt-3 shrink-0"
                onMouseEnter={() => setQuoteHover(true)}
                onMouseLeave={() => setQuoteHover(false)}
              >
                <div className="inline-flex max-w-full items-center gap-1 rounded-full border border-purple-400/25 bg-purple-500/[0.08] px-2.5 py-1 text-xs text-purple-700 dark:text-purple-200">
                  <Quote className="h-3.5 w-3.5 shrink-0" />
                  <span className="font-medium">{annotationLabel(quotes.length)}</span>
                  <button
                    type="button"
                    aria-label="取消引用"
                    onClick={clearQuotes}
                    className="inline-flex h-5 w-5 items-center justify-center rounded-full text-purple-500 hover:bg-purple-500/10 hover:text-purple-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/40"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
                {quoteHover && (
                  <div
                    role="list"
                    aria-label="引用预览"
                    className="absolute bottom-full left-0 z-20 mb-2 w-[min(28rem,calc(100vw-3rem))] rounded-card border border-border bg-surface p-2 shadow-lg"
                  >
                    {quotes.map((item, index) => (
                      <button
                        key={item.id}
                        type="button"
                        role="listitem"
                        onClick={() => revealQuote(item)}
                        className="flex w-full items-start gap-2 rounded-btn px-2 py-1.5 text-left hover:bg-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/40"
                      >
                        <span className="mt-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-purple-500/15 px-1 text-[11px] font-medium text-purple-700 dark:text-purple-200">
                          {index + 1}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block text-xs leading-5 text-foreground">{excerptPreview(item.excerpt, 88)}</span>
                          {item.comment ? (
                            <span className="mt-0.5 block text-[11px] leading-4 text-muted">批注：{excerptPreview(item.comment, 72)}</span>
                          ) : null}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {embedded && pageContext && (
              <div
                aria-label="当前页面快照"
                className="mt-3 shrink-0 rounded-card border border-violet-400/25 bg-violet-500/[0.06] px-3 py-2"
              >
                <div className="flex min-w-0 items-baseline gap-2 text-sm text-foreground">
                  <span className="font-medium">{pageContext.title}</span>
                  {pageContext.asOf ? <span className="font-mono text-xs text-muted">{pageContext.asOf}</span> : null}
                </div>
                {(pageContext.selectedFocuses?.length ?? 0) > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {pageContext.selectedFocuses?.map(option => (
                      <button
                        key={option.id}
                        type="button"
                        onClick={() => removePageContextFocus(option.id)}
                        className="inline-flex max-w-full items-center gap-1 rounded-full border border-violet-400/35 bg-violet-500/15 px-2.5 py-1 text-[11px] font-medium text-violet-800 dark:text-violet-100"
                        title="移出这个分析模块"
                      >
                        <span className="min-w-0 truncate">{formatFocusOption(option)}</span>
                        <X className="h-3 w-3 shrink-0 opacity-70" />
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            )}
            {contextSymbol && (
              <div
                aria-label="当前分析股票"
                className="mt-3 shrink-0 rounded-card border border-sky-400/25 bg-sky-500/[0.06] px-3 py-2 text-xs text-secondary"
              >
                已预填 <span className="font-medium text-foreground">{contextName || contextSymbol}</span>
                <span className="ml-1 font-mono text-muted">{contextSymbol}</span>
                <span className="ml-1 text-muted">，已放入新对话，确认后发送，不会自动发出。</span>
                <span className="mt-1 block text-muted">稳定关注面会记入当前账户 Profile，新对话会先读；分析框架和出图规则不会被自动改。</span>
              </div>
            )}
            <form
              data-testid="hermes-composer"
              onSubmit={handleSubmit}
              className="mt-3 shrink-0 border-t border-border bg-base pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3"
            >
              <div className="flex items-end gap-2 rounded-card border border-border bg-surface p-2 focus-within:border-purple-400/40 focus-within:ring-2 focus-within:ring-purple-400/10">
                <textarea
                  value={input}
                  onChange={event => setInput(event.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={embedded && pageContext ? `询问当前${pageContext.title}，可不输入直接发送` : '输入消息，Shift + Enter 换行'}
                  aria-label="发送给 Hermes Agent 的消息"
                  rows={2}
                  maxLength={12_000}
                  disabled={!connected || isSending}
                  className="min-h-12 flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-6 text-foreground outline-none placeholder:text-muted disabled:cursor-not-allowed"
                />
                <button
                  type="submit"
                  disabled={(!input.trim() && quotes.length === 0 && !(embedded && pageContext)) || !connected || isSending}
                  aria-label="发送消息"
                  className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-btn bg-purple-600 text-white transition-colors hover:bg-purple-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <Send className="h-4 w-4" />
                </button>
              </div>
            </form>
          </section>
        </main>
      </div>

      <StockPreviewDialog
        symbol={previewSymbol}
        onClose={() => setPreviewSymbol(null)}
        showAnalysisAction
      />
    </div>
  )
}
