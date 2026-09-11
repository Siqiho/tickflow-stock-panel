/**
 * 用户台运行日志 — 覆盖路由、API、错误, 批量上报到后端 data/logs。
 *
 * 目标: 让「设置 → 运行日志」能看到前端操作轨迹与数据台后端日志对照。
 */
import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR'

export type RuntimeLogEvent = {
  ts: string
  level: LogLevel
  category: string
  message: string
  path?: string
  method?: string
  status?: number
  duration_ms?: number
  session_id?: string
  detail?: Record<string, unknown>
  change?: Record<string, unknown>
}

const SESSION_KEY = 'ot_runtime_session'
const MAX_QUEUE = 300
const FLUSH_MS = 1500
const FLUSH_SIZE = 12
const ENDPOINT = '/api/runtime-logs/client'

let installed = false
let remoteUploadEnabled = false
let queue: RuntimeLogEvent[] = []
let flushTimer: ReturnType<typeof setTimeout> | null = null
let lastPath = ''
let lastHref = typeof window !== 'undefined' ? window.location.href : ''

function nowIso() {
  return new Date().toISOString()
}

function getSessionId(): string {
  try {
    let id = sessionStorage.getItem(SESSION_KEY)
    if (!id) {
      id = `ui_${Math.random().toString(36).slice(2, 10)}_${Date.now().toString(36)}`
      sessionStorage.setItem(SESSION_KEY, id)
    }
    return id
  } catch {
    return `ui_${Date.now().toString(36)}`
  }
}

function enqueue(event: Omit<RuntimeLogEvent, 'ts' | 'session_id'> & { ts?: string }) {
  const full: RuntimeLogEvent = {
    ts: event.ts || nowIso(),
    session_id: getSessionId(),
    level: event.level,
    category: event.category,
    message: event.message,
    path: event.path,
    method: event.method,
    status: event.status,
    duration_ms: event.duration_ms,
    detail: event.detail,
    change: event.change,
  }
  queue.push(full)
  if (queue.length > MAX_QUEUE) {
    queue = queue.slice(queue.length - MAX_QUEUE)
  }
  if (queue.length >= FLUSH_SIZE) {
    void flushRuntimeLogs()
  } else if (!flushTimer) {
    flushTimer = setTimeout(() => {
      flushTimer = null
      void flushRuntimeLogs()
    }, FLUSH_MS)
  }
}

export function logRuntime(
  level: LogLevel,
  category: string,
  message: string,
  extra?: Partial<Omit<RuntimeLogEvent, 'ts' | 'session_id' | 'level' | 'category' | 'message'>>,
) {
  enqueue({
    level,
    category,
    message,
    ...extra,
  })
}

export function logUiInfo(message: string, detail?: Record<string, unknown>, change?: Record<string, unknown>) {
  logRuntime('INFO', 'ui', message, { detail, change, path: lastPath || undefined })
}

export function logUiWarn(message: string, detail?: Record<string, unknown>) {
  logRuntime('WARNING', 'ui', message, { detail, path: lastPath || undefined })
}

export function logUiError(message: string, detail?: Record<string, unknown>) {
  logRuntime('ERROR', 'ui', message, { detail, path: lastPath || undefined })
}

export function logRouteChange(to: string, from?: string) {
  if (!to || to === from) return
  lastPath = to
  logRuntime('INFO', 'navigation', `打开页面 ${to}`, {
    path: to,
    change: {
      type: 'route',
      from: from || null,
      to,
    },
  })
}

function shouldSkipApiPath(path: string, method = 'GET') {
  const clean = path.split('?')[0] || path
  if (
    clean.startsWith('/api/runtime-logs') ||
    clean === '/health' ||
    clean.startsWith('/assets/')
  ) {
    return true
  }
  // 高频状态轮询不进用户台运行日志, 保留真正操作/变更
  if ((method || 'GET').toUpperCase() === 'GET') {
    const noisyExact = new Set([
      '/api/intraday/status',
      '/api/pipeline/jobs',
      '/api/data/status',
      '/api/financials/status',
      '/api/alerts',
      '/api/auth/status',
      '/api/backtest/status',
      '/api/strategies/ai/status',
    ])
    if (noisyExact.has(clean)) return true
    if (clean.startsWith('/api/pipeline/jobs/')) return true
  }
  return false
}

export function logApiCall(opts: {
  method: string
  path: string
  status?: number
  ok?: boolean
  duration_ms: number
  requestBody?: unknown
  error?: string
}) {
  if (shouldSkipApiPath(opts.path, opts.method)) return
  const level: LogLevel = !opts.ok || (opts.status != null && opts.status >= 400)
    ? (opts.status != null && opts.status >= 500 ? 'ERROR' : 'WARNING')
    : 'INFO'
  const change: Record<string, unknown> = {
    type: 'api',
    method: opts.method,
    path: opts.path,
    status: opts.status ?? null,
    ok: opts.ok ?? null,
  }
  if (opts.requestBody !== undefined) change.request = opts.requestBody
  if (opts.error) change.error = opts.error
  logRuntime(level, 'api', `${opts.method} ${opts.path} → ${opts.status ?? 'ERR'}`, {
    method: opts.method,
    path: opts.path,
    status: opts.status,
    duration_ms: opts.duration_ms,
    detail: {
      page: lastPath || undefined,
      error: opts.error,
    },
    change,
  })
}

export async function flushRuntimeLogs() {
  if (flushTimer) {
    clearTimeout(flushTimer)
    flushTimer = null
  }
  if (!remoteUploadEnabled) {
    queue = []
    return
  }
  if (!queue.length) return
  const batch = queue.splice(0, queue.length)
  try {
    const res = await fetch(ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: getSessionId(), events: batch }),
      keepalive: true,
    })
    if (!res.ok) {
      // 未登录/无权限时丢弃, 避免登录前队列空转膨胀
      if (res.status === 401 || res.status === 403) return
      // 其它失败塞回队列头部, 避免日志丢失
      queue = batch.concat(queue).slice(0, MAX_QUEUE)
    }
  } catch {
    queue = batch.concat(queue).slice(0, MAX_QUEUE)
  }
}

export function setRuntimeLogUploadEnabled(enabled: boolean) {
  remoteUploadEnabled = enabled
  if (!enabled) {
    queue = []
    if (flushTimer) {
      clearTimeout(flushTimer)
      flushTimer = null
    }
  }
}

export function installRuntimeLogger() {
  if (installed || typeof window === 'undefined') return
  installed = true
  lastPath = window.location.pathname + window.location.search
  lastHref = window.location.href

  logRuntime('INFO', 'lifecycle', '用户台运行日志已启用', {
    path: lastPath,
    detail: {
      href: window.location.href,
      userAgent: navigator.userAgent,
      language: navigator.language,
      viewport: { w: window.innerWidth, h: window.innerHeight },
    },
  })
  logRouteChange(lastPath)

  // 全局错误
  window.addEventListener('error', (ev) => {
    logUiError(ev.message || 'window.error', {
      filename: (ev as ErrorEvent).filename,
      lineno: (ev as ErrorEvent).lineno,
      colno: (ev as ErrorEvent).colno,
      stack: (ev as ErrorEvent).error?.stack,
    })
  })
  window.addEventListener('unhandledrejection', (ev) => {
    const reason = (ev as PromiseRejectionEvent).reason
    const message = reason?.message || String(reason || 'unhandledrejection')
    logUiError(`未处理 Promise: ${message}`, {
      stack: reason?.stack,
    })
  })

  // 可见性变化
  document.addEventListener('visibilitychange', () => {
    logRuntime('INFO', 'lifecycle', `页面可见性 → ${document.visibilityState}`, {
      path: lastPath,
      change: { type: 'visibility', state: document.visibilityState },
    })
  })

  // history 路由变化 (react-router 之外的兜底)
  const wrapHistory = (type: 'pushState' | 'replaceState') => {
    const orig = history[type]
    return function (this: History, ...args: Parameters<typeof orig>) {
      const ret = orig.apply(this, args as any)
      const href = window.location.pathname + window.location.search
      if (href !== lastHref) {
        const from = lastPath
        lastHref = href
        logRouteChange(href, from)
      }
      return ret
    }
  }
  history.pushState = wrapHistory('pushState') as typeof history.pushState
  history.replaceState = wrapHistory('replaceState') as typeof history.replaceState
  window.addEventListener('popstate', () => {
    const href = window.location.pathname + window.location.search
    const from = lastPath
    lastHref = href
    logRouteChange(href, from)
  })

  // 页面关闭尽量冲刷
  window.addEventListener('pagehide', () => {
    if (!queue.length) return
    const body = JSON.stringify({ session_id: getSessionId(), events: queue.splice(0, queue.length) })
    try {
      if (navigator.sendBeacon) {
        const blob = new Blob([body], { type: 'application/json' })
        navigator.sendBeacon(ENDPOINT, blob)
      }
    } catch {
      /* ignore */
    }
  })
}

/** React Router 精确路径同步 (比 history monkey-patch 更稳)。 */
export function useRuntimeRouteLogger() {
  const location = useLocation()
  useEffect(() => {
    const to = location.pathname + location.search
    if (to !== lastPath) {
      const from = lastPath
      lastPath = to
      lastHref = window.location.href
      logRouteChange(to, from || undefined)
    }
  }, [location.pathname, location.search])
}

export function getRuntimeSessionId() {
  return getSessionId()
}
