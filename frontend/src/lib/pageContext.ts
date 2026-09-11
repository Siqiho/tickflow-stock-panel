import { useSyncExternalStore } from 'react'

export interface PageContextItem {
  label: string
  detail?: string
}

export interface PageContextFocusOption {
  id: string
  label: string
  value?: string | null
}

export interface PageContextSnapshot {
  route: string
  title: string
  asOf?: string | null
  summary: string
  focus?: string | null
  focusOptions?: PageContextFocusOption[]
  selectedFocusId?: string | null
  selectedFocusIds?: string[]
  selectedFocuses?: PageContextFocusOption[]
  filters?: string[]
  items: PageContextItem[]
  notes?: string[]
  queryHint?: string
}

const MAX_PROMPT_CHARS = 3600

let current: PageContextSnapshot | null = null
let selectedFocusIds: string[] = []
let pickerOpen = false
const listeners = new Set<() => void>()

export function formatFocusOption(option: PageContextFocusOption) {
  return option.value ? `${option.label} · ${option.value}` : option.label
}

function uniqueValidIds(ids: string[], options: PageContextFocusOption[]) {
  const allowed = new Set(options.map(option => option.id))
  const next: string[] = []
  for (const id of ids) {
    if (!allowed.has(id) || next.includes(id)) continue
    next.push(id)
  }
  return next
}

function applyFocus(snapshot: PageContextSnapshot): PageContextSnapshot {
  const options = snapshot.focusOptions ?? []
  selectedFocusIds = uniqueValidIds(selectedFocusIds, options)
  const selected = selectedFocusIds
    .map(id => options.find(option => option.id === id))
    .filter((option): option is PageContextFocusOption => Boolean(option))
  return {
    ...snapshot,
    selectedFocusId: selectedFocusIds[selectedFocusIds.length - 1] ?? null,
    selectedFocusIds,
    selectedFocuses: selected,
    focus: selected.length ? selected.map(formatFocusOption).join('；') : null,
  }
}

function emit() {
  listeners.forEach(fn => fn())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

export function setPageContext(next: PageContextSnapshot) {
  current = applyFocus(next)
  emit()
}

export function clearPageContext(route?: string) {
  if (!current) return
  if (route && current.route !== route) return
  current = null
  selectedFocusIds = []
  emit()
}

export function setPageContextPickerOpen(open: boolean) {
  if (pickerOpen === open) return
  pickerOpen = open
  emit()
}

export function isPageContextPickerOpen() {
  return pickerOpen
}

export function selectPageContextFocus(id: string) {
  if (!current?.focusOptions?.some(option => option.id === id)) return
  if (!selectedFocusIds.includes(id)) selectedFocusIds = [...selectedFocusIds, id]
  current = applyFocus(current)
  emit()
}

export function removePageContextFocus(id: string) {
  if (!selectedFocusIds.includes(id)) return
  selectedFocusIds = selectedFocusIds.filter(item => item !== id)
  if (current) current = applyFocus(current)
  emit()
}

export function getPageContext() {
  return current
}

export function usePageContext() {
  return useSyncExternalStore(subscribe, getPageContext, () => null)
}

export function usePageContextPickerOpen() {
  return useSyncExternalStore(subscribe, isPageContextPickerOpen, () => false)
}

function snapshotToLines(snapshot: PageContextSnapshot) {
  const lines = [
    `当前页面：${snapshot.title}`,
    `路由：${snapshot.route}`,
  ]
  if (snapshot.asOf) lines.push(`日期：${snapshot.asOf}`)
  if (snapshot.selectedFocuses?.length) {
    lines.push(`当前分析模块：${snapshot.selectedFocuses.map(formatFocusOption).join('；')}`)
  } else if (snapshot.focus) {
    lines.push(`当前分析模块：${snapshot.focus}`)
  }
  if (snapshot.filters?.length) lines.push(`筛选：${snapshot.filters.join(' · ')}`)
  lines.push(`摘要：${snapshot.summary}`)

  if (snapshot.items.length > 0) {
    lines.push('', '当前可见内容：')
    for (const item of snapshot.items) {
      lines.push(item.detail ? `- ${item.label}：${item.detail}` : `- ${item.label}`)
    }
  }

  if (snapshot.notes?.length) {
    lines.push('', '说明：')
    for (const note of snapshot.notes) lines.push(`- ${note}`)
  }
  if (snapshot.queryHint) {
    lines.push(`- 需要更多原始数据时，使用 one_trading_data_query 查询 ${snapshot.queryHint}`)
  }
  return lines.join('\n')
}

export function formatPageContextPrompt(snapshot: PageContextSnapshot) {
  let working: PageContextSnapshot = snapshot
  let text = snapshotToLines(working)
  if (text.length <= MAX_PROMPT_CHARS) return text

  const items = [...snapshot.items]
  while (items.length > 4 && text.length > MAX_PROMPT_CHARS) {
    items.pop()
    working = {
      ...snapshot,
      items,
      notes: [
        ...(snapshot.notes ?? []),
        `快照已截断，仅保留前 ${items.length} 条可见项`,
      ],
    }
    text = snapshotToLines(working)
  }
  return text.length <= MAX_PROMPT_CHARS ? text : text.slice(0, MAX_PROMPT_CHARS)
}

export function composePageContextMessage(snapshot: PageContextSnapshot, message: string) {
  const snapshotText = formatPageContextPrompt(snapshot)
  const user = message.trim()
  return user
    ? `以下是用户当前界面的结构化快照，请先基于它回答；不够再查数据台。

${snapshotText}

用户问题：${user}`
    : `以下是用户当前界面的结构化快照。请先概括我正在看的内容，再指出最值得关注的点；不够再查数据台。

${snapshotText}`
}
