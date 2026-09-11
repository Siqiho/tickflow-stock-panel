import { useCallback, useState } from 'react'

/**
 * 记忆"上次查看 / 最近查看的个股"(按页面维度,localStorage 持久化)。
 *
 * 两个分析页(财务 / 个股)各自独立记忆,key 区分:
 *   - financials: 最后查看的财务分析个股
 *   - stock-analysis: 最后查看的个股分析个股
 *
 * 用法:
 *   const { last, recent, remember } = useLastStock('stock-analysis')
 *   remember('000001.SZ', '平安银行')   // 选中股票时调用
 *   <LastStockChip stock={last} ... />  // 渲染在 PageHeader 右侧
 */

export interface StockRef { symbol: string; name: string }

const PREFIX = 'last_stock:'
const RECENT_PREFIX = 'recent_stocks:'
const RECENT_LIMIT = 10

export function useLastStock(scope: string) {
  const [last, setLast] = useState<StockRef | null>(() => load(scope))
  const [recent, setRecent] = useState<StockRef[]>(() => loadRecent(scope, load(scope)))

  const remember = useCallback((symbol: string, name: string) => {
    const ref = normalize({ symbol, name })
    if (!ref) return
    setLast(ref)
    save(scope, ref)
    setRecent(current => {
      const next = uniqueStocks([ref, ...current]).slice(0, RECENT_LIMIT)
      saveRecent(scope, next)
      return next
    })
  }, [scope])

  const clear = useCallback(() => {
    setLast(null)
    save(scope, null)
  }, [scope])

  return { last, recent, remember, clear }
}

function load(scope: string): StockRef | null {
  try {
    const v = localStorage.getItem(PREFIX + scope)
    if (!v) return null
    const p = JSON.parse(v)
    if (p && typeof p.symbol === 'string' && typeof p.name === 'string') return p
  } catch { /* ignore */ }
  return null
}

function save(scope: string, ref: StockRef | null) {
  try {
    if (ref) localStorage.setItem(PREFIX + scope, JSON.stringify(ref))
    else localStorage.removeItem(PREFIX + scope)
  } catch { /* ignore */ }
}

function loadRecent(scope: string, fallback: StockRef | null): StockRef[] {
  try {
    const raw = localStorage.getItem(RECENT_PREFIX + scope)
    const parsed = raw ? JSON.parse(raw) : []
    const stored = Array.isArray(parsed)
      ? parsed.map(normalize).filter((item): item is StockRef => item !== null)
      : []
    return uniqueStocks(fallback ? [fallback, ...stored] : stored).slice(0, RECENT_LIMIT)
  } catch {
    return fallback ? [fallback] : []
  }
}

function saveRecent(scope: string, refs: StockRef[]) {
  try {
    localStorage.setItem(RECENT_PREFIX + scope, JSON.stringify(refs))
  } catch { /* ignore */ }
}

function normalize(value: unknown): StockRef | null {
  if (!value || typeof value !== 'object') return null
  const symbol = 'symbol' in value && typeof value.symbol === 'string'
    ? value.symbol.trim().toUpperCase()
    : ''
  const name = 'name' in value && typeof value.name === 'string'
    ? value.name.trim()
    : ''
  if (!symbol) return null
  return { symbol, name: name || symbol }
}

function uniqueStocks(refs: StockRef[]): StockRef[] {
  const seen = new Set<string>()
  return refs.filter(ref => {
    if (seen.has(ref.symbol)) return false
    seen.add(ref.symbol)
    return true
  })
}
