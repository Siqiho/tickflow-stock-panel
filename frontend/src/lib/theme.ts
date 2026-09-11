/**
 * 全局外观主题 — light / dark
 *
 * - 持久化到 localStorage
 * - 通过 html.dark class 驱动 Tailwind + CSS variables
 * - 图表等非 CSS 场景可通过 getChartChrome() / useTheme() 读取
 */
import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'

export type ThemeMode = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'ot-theme'
export const DEFAULT_THEME: ThemeMode = 'light'

const listeners = new Set<() => void>()

function emit() {
  listeners.forEach(l => l())
}

export function getStoredTheme(): ThemeMode {
  try {
    const v = localStorage.getItem(THEME_STORAGE_KEY)
    if (v === 'light' || v === 'dark') return v
  } catch { /* ignore */ }
  return DEFAULT_THEME
}

export function isDarkTheme(mode: ThemeMode = getStoredTheme()): boolean {
  return mode === 'dark'
}

/** 同步应用到 <html>，并更新 theme-color meta。 */
export function applyTheme(mode: ThemeMode) {
  const root = document.documentElement
  root.classList.toggle('dark', mode === 'dark')
  root.dataset.theme = mode
  root.style.colorScheme = mode
  try {
    const meta = document.querySelector('meta[name="theme-color"]')
    if (meta) meta.setAttribute('content', mode === 'dark' ? '#0A0A0B' : '#FAFAFA')
  } catch { /* ignore */ }
}

export function setTheme(mode: ThemeMode) {
  try { localStorage.setItem(THEME_STORAGE_KEY, mode) } catch { /* ignore */ }
  applyTheme(mode)
  emit()
}

export function toggleTheme() {
  setTheme(getStoredTheme() === 'dark' ? 'light' : 'dark')
}

function subscribe(cb: () => void) {
  listeners.add(cb)
  return () => { listeners.delete(cb) }
}

function getSnapshot(): ThemeMode {
  return getStoredTheme()
}

/** 在组件中订阅当前主题；切换时重渲染。 */
export function useTheme() {
  const theme = useSyncExternalStore(subscribe, getSnapshot, () => DEFAULT_THEME)
  const set = useCallback((mode: ThemeMode) => setTheme(mode), [])
  const toggle = useCallback(() => toggleTheme(), [])
  return { theme, isDark: theme === 'dark', setTheme: set, toggleTheme: toggle } as const
}

/**
 * 跨标签页同步 + 确保挂载时 html class 与 storage 一致。
 * 在 Layout 或根组件调用一次即可。
 */
export function useThemeSync() {
  const { theme } = useTheme()
  useEffect(() => {
    applyTheme(theme)
    const onStorage = (e: StorageEvent) => {
      if (e.key === THEME_STORAGE_KEY) {
        applyTheme(getStoredTheme())
        emit()
      }
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [theme])
}

/** 读取当前 CSS 变量为可用颜色字符串（供 ECharts 等）。 */
function cssVar(name: string, fallback: string): string {
  try {
    const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
    if (!raw) return fallback
    // 变量存的是 "H S% L%" 形式
    if (raw.includes(' ')) return `hsl(${raw})`
    return raw
  } catch {
    return fallback
  }
}

export interface ChartChrome {
  text: string
  muted: string
  grid: string
  border: string
  tooltipBg: string
  tooltipBorder: string
  tooltipText: string
  crosshair: string
  refLine: string
  infoBarBg: string
  handle: string
  labelBg: string
  fillSubtle: string
  textStrong: string
  zoomFill: string
}

/** 图表 UI 色（随主题变化）。涨跌语义色保持固定。 */
export function getChartChrome(isDark = isDarkTheme()): ChartChrome {
  if (typeof document !== 'undefined') {
    // 优先跟真实 DOM class，避免 storage 与 class 短暂不一致
    isDark = document.documentElement.classList.contains('dark')
  }
  if (isDark) {
    return {
      text: '#A1A1AA',
      muted: '#8E8E96',
      grid: 'rgba(255,255,255,0.04)',
      border: '#27272A',
      tooltipBg: 'rgba(39,39,42,0.92)',
      tooltipBorder: 'rgba(255,255,255,0.1)',
      tooltipText: '#E4E4E7',
      crosshair: 'rgba(255,255,255,0.2)',
      refLine: 'rgba(255,255,255,0.25)',
      infoBarBg: 'rgba(39,39,42,0.6)',
      handle: '#52525B',
      labelBg: 'rgba(15,23,42,0.85)',
      fillSubtle: 'rgba(255,255,255,0.06)',
      textStrong: '#FAFAFA',
      zoomFill: 'rgba(255,255,255,0.08)',
    }
  }
  return {
    text: cssVar('--fg-muted', '#71717A') || '#71717A',
    muted: '#A1A1AA',
    grid: 'rgba(24,24,27,0.06)',
    border: '#E4E4E7',
    tooltipBg: 'rgba(255,255,255,0.96)',
    tooltipBorder: 'rgba(24,24,27,0.08)',
    tooltipText: '#18181B',
    crosshair: 'rgba(24,24,27,0.18)',
    refLine: 'rgba(24,24,27,0.22)',
    infoBarBg: 'rgba(244,244,245,0.92)',
    handle: '#A1A1AA',
    labelBg: 'rgba(255,255,255,0.92)',
    fillSubtle: 'rgba(24,24,27,0.04)',
    textStrong: '#18181B',
    zoomFill: 'rgba(24,24,27,0.06)',
  }
}

/** React 辅助：主题变化时返回最新 chrome，驱动图表重建。 */
export function useChartTheme(): ChartChrome {
  return useChartChrome()
}

export function useChartChrome(): ChartChrome {
  const { isDark } = useTheme()
  // 用 state 确保 DOM class 应用后再读
  const [chrome, setChrome] = useState(() => getChartChrome(isDark))
  useEffect(() => {
    setChrome(getChartChrome(isDark))
  }, [isDark])
  return chrome
}
