export type HermesChartPoint = {
  label: string
  value: number
}

export type HermesChartSpec = {
  type?: string
  kind?: string
  chartType?: 'bar' | 'line'
  template?: string
  view?: string
  as_of?: string
  source?: string
  title?: string
  unit?: string
  points?: HermesChartPoint[]
  [key: string]: unknown
}

export type HermesRichBlock =
  | { type: 'markdown'; text: string }
  | { type: 'chart'; spec: HermesChartSpec; raw: string }

const CHART_FENCE = /```(?:json)?\s*\n(\s*\{[\s\S]*?\}\s*)\n```/g

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function finiteNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

function pointLabel(value: Record<string, unknown>, index: number): string {
  const label = value.label ?? value.name ?? value.date ?? value.x ?? value.category
  if (typeof label === 'string' && label.trim()) return label.trim()
  if (typeof label === 'number' && Number.isFinite(label)) return String(label)
  return `项 ${index + 1}`
}

export function normalizeHermesChartPoints(spec: HermesChartSpec): HermesChartPoint[] {
  const rawPoints = Array.isArray(spec.points)
    ? spec.points
    : Array.isArray(spec.data)
      ? spec.data
      : Array.isArray(spec.series)
        ? spec.series
        : []
  return rawPoints.flatMap((item, index) => {
    if (!isRecord(item)) return []
    const value = finiteNumber(item.value ?? item.y ?? item.main_net ?? item.amount)
    if (value == null) return []
    return [{ label: pointLabel(item, index), value }]
  }).slice(0, 24)
}

function isChartSpec(value: unknown): value is HermesChartSpec {
  if (!isRecord(value)) return false
  const kind = String(value.type ?? value.kind ?? '').toLowerCase()
  return kind === 'chart' || kind === 'lieflat' || kind === 'lieflat-chart'
}

export function parseHermesRichContent(content: string): HermesRichBlock[] {
  const text = content.replace(/\r\n/g, '\n')
  const blocks: HermesRichBlock[] = []
  let last = 0
  for (const match of text.matchAll(CHART_FENCE)) {
    const start = match.index ?? 0
    const raw = match[1]?.trim() ?? ''
    if (start > last) {
      const before = text.slice(last, start).trim()
      if (before) blocks.push({ type: 'markdown', text: before })
    }
    try {
      const parsed = JSON.parse(raw) as unknown
      if (isChartSpec(parsed)) {
        blocks.push({ type: 'chart', spec: parsed, raw })
      } else if (raw) {
        blocks.push({ type: 'markdown', text: match[0] })
      }
    } catch {
      if (raw) blocks.push({ type: 'markdown', text: match[0] })
    }
    last = start + match[0].length
  }
  const rest = text.slice(last).trim()
  if (rest) blocks.push({ type: 'markdown', text: rest })
  return blocks.length ? blocks : [{ type: 'markdown', text }]
}
