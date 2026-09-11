import type {
  CapabilityMatrix,
  CatalogResponse,
  DataSourcesResponse,
  DatasetCatalogEntry,
  SourceProvenanceProducer,
  SourceProvenanceRecord,
  SourceProvenanceResponse,
} from './api'
import { CAPABILITY_LOCAL_DATASETS, displaySourceName } from './dataSources'

export const EXTERNAL_SOURCE_ID = 'offline_quantdb'
export const UNREGISTERED_SOURCE_ID = 'unregistered'
export const EXTRA_MARGIN_LABEL = '两融'

export type UnifiedSourceKind = 'online' | 'local' | 'external' | 'unregistered'

export type UnifiedSource = {
  id: string
  kind: UnifiedSourceKind
  name: string
  displayName: string
  paid: boolean
  tier: string | null
  capabilityIds: string[]
  datasetIds: string[]
  extraLabels: string[]
  httpProvider: string | null
}

export type SourceCatalogInput = {
  sources?: DataSourcesResponse
  matrix?: CapabilityMatrix
  catalog?: CatalogResponse
  provenance?: SourceProvenanceResponse
  includeExternal?: boolean
}

const PROVIDER_ALIASES: Record<string, string> = {
  local_public: 'public',
  public: 'public',
}

function unique(values: Array<string | null | undefined>): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const value of values) {
    if (!value || seen.has(value)) continue
    seen.add(value)
    out.push(value)
  }
  return out
}

export function canonicalProviderName(raw: string | null | undefined): string | null {
  if (raw == null) return null
  const name = raw.trim()
  if (!name || name === 'same_as_daily') return null
  return PROVIDER_ALIASES[name] ?? name
}

export function coverageTimeLabel(entry: DatasetCatalogEntry): string {
  const start = entry.state.earliest_time
  const end = entry.state.latest_time
  if (!start && !end) return '未知'
  const left = start ? start.slice(0, 10) : '未知'
  const right = end ? end.slice(0, 10) : '未知'
  return `${left} ~ ${right}`
}

export function fieldUnitLabel(unit: string | null | undefined): string {
  return unit == null || unit === '' ? '未登记' : unit
}

export function isLocallyPresent(entry: DatasetCatalogEntry): boolean {
  if (entry.descriptor.availability.local_materialized) return true
  return (entry.state.row_count ?? 0) > 0
}

export function extraDatasetLabel(datasetId: string): string | null {
  if (datasetId === 'stock_margin_trading' || datasetId.startsWith('stock_f10_')) return EXTRA_MARGIN_LABEL
  return null
}

function declaredCapabilities(name: string, datasets: string[], matrix?: CapabilityMatrix): string[] {
  const fromItem = datasets
  const fromMatrix = (matrix?.capabilities ?? [])
    .filter((cap) => (
      cap.candidates.some((item) => item.name === name)
      || cap.pending.some((item) => item.name === name)
      || (name === 'tickflow' && cap.tf_available)
    ))
    .map((cap) => cap.id)
  return unique([...fromItem, ...fromMatrix])
}

function displayForName(
  name: string,
  sources?: DataSourcesResponse,
  matrix?: CapabilityMatrix,
): string {
  const listed = sources?.builtin.find((item) => item.name === name)
    ?? sources?.plugins.find((item) => item.name === name)
    ?? sources?.custom.find((item) => item.name === name)
  if (listed?.display_name) return listed.display_name
  for (const cap of matrix?.capabilities ?? []) {
    const hit = cap.candidates.find((item) => item.name === name)
      ?? cap.pending.find((item) => item.name === name)
    if (hit) return hit.display
  }
  return displaySourceName(name)
}

export function collectOnlineSourceNames(
  sources?: DataSourcesResponse,
  matrix?: CapabilityMatrix,
): Map<string, { displayName: string; datasets: string[] }> {
  const map = new Map<string, { displayName: string; datasets: string[] }>()
  const add = (name: string, displayName: string, datasets: string[] = []) => {
    const existing = map.get(name)
    if (existing) {
      existing.datasets = unique([...existing.datasets, ...datasets])
      return
    }
    map.set(name, { displayName, datasets: [...datasets] })
  }

  for (const item of sources?.builtin ?? []) add(item.name, item.display_name, item.datasets)
  for (const item of sources?.plugins ?? []) add(item.name, item.display_name, item.datasets)
  for (const item of sources?.custom ?? []) add(item.name, item.display_name, item.datasets)

  for (const cap of matrix?.capabilities ?? []) {
    for (const candidate of [...cap.candidates, ...cap.pending]) {
      if (candidate.name === 'same_as_daily') continue
      add(candidate.name, candidate.display)
    }
  }
  return map
}

export function provenanceRecordFor(
  datasetId: string,
  provenance?: SourceProvenanceResponse,
): SourceProvenanceRecord | undefined {
  return provenance?.records.find((record) => record.subject_id === datasetId)
}

export function trueProducersFor(
  datasetId: string,
  provenance?: SourceProvenanceResponse,
): SourceProvenanceProducer[] {
  return provenanceRecordFor(datasetId, provenance)?.true_producers ?? []
}

export function producerNamesFor(
  datasetId: string,
  provenance?: SourceProvenanceResponse,
): string[] {
  const producers = trueProducersFor(datasetId, provenance)
  if (producers.length === 0) return ['未登记']
  return unique(producers.map((item) => item.name || item.producer_id || null))
}

function httpProviderEvidence(entry: DatasetCatalogEntry): string | null {
  return canonicalProviderName(entry.provider)
}

function assignDataset(
  entry: DatasetCatalogEntry,
  onlineNames: Set<string>,
): { target: string; kind: 'online' | 'local' | 'unregistered' } {
  const provider = httpProviderEvidence(entry)
  if (!provider) return { target: UNREGISTERED_SOURCE_ID, kind: 'unregistered' }
  if (onlineNames.has(provider)) return { target: provider, kind: 'online' }
  return { target: provider, kind: 'local' }
}

export function buildUnifiedSources({
  sources,
  matrix,
  catalog,
  includeExternal = false,
}: SourceCatalogInput): UnifiedSource[] {
  const online = collectOnlineSourceNames(sources, matrix)
  const onlineNames = new Set(online.keys())
  const grouped = new Map<string, string[]>()

  for (const entry of catalog?.datasets ?? []) {
    const assignment = assignDataset(entry, onlineNames)
    const current = grouped.get(assignment.target) ?? []
    current.push(entry.descriptor.dataset_id)
    grouped.set(assignment.target, current)
  }

  const result: UnifiedSource[] = []

  for (const [name, meta] of online) {
    const datasetIds = grouped.get(name) ?? []
    result.push({
      id: name,
      kind: 'online',
      name,
      displayName: meta.displayName,
      paid: name === 'tickflow',
      tier: name === 'tickflow' ? matrix?.tickflow_tier ?? null : null,
      capabilityIds: declaredCapabilities(name, meta.datasets, matrix),
      datasetIds,
      extraLabels: unique(datasetIds.map(extraDatasetLabel)),
      httpProvider: name,
    })
  }

  for (const [name, datasetIds] of grouped) {
    if (name === UNREGISTERED_SOURCE_ID || onlineNames.has(name)) continue
    result.push({
      id: `local:${name}`,
      kind: 'local',
      name,
      displayName: displayForName(name, sources, matrix),
      paid: false,
      tier: null,
      capabilityIds: unique(
        datasetIds.flatMap((datasetId) => (
          Object.entries(CAPABILITY_LOCAL_DATASETS)
            .filter(([, ids]) => ids.includes(datasetId))
            .map(([cap]) => cap)
        )),
      ),
      datasetIds,
      extraLabels: unique(datasetIds.map(extraDatasetLabel)),
      httpProvider: name,
    })
  }

  const unregisteredIds = grouped.get(UNREGISTERED_SOURCE_ID) ?? []
  if (unregisteredIds.length > 0) {
    result.push({
      id: UNREGISTERED_SOURCE_ID,
      kind: 'unregistered',
      name: UNREGISTERED_SOURCE_ID,
      displayName: '未登记来源',
      paid: false,
      tier: null,
      capabilityIds: [],
      datasetIds: unregisteredIds,
      extraLabels: unique(unregisteredIds.map(extraDatasetLabel)),
      httpProvider: null,
    })
  }

  if (includeExternal) {
    result.push({
      id: EXTERNAL_SOURCE_ID,
      kind: 'external',
      name: EXTERNAL_SOURCE_ID,
      displayName: '外部只读原包',
      paid: false,
      tier: null,
      capabilityIds: [],
      datasetIds: [],
      extraLabels: [EXTRA_MARGIN_LABEL],
      httpProvider: EXTERNAL_SOURCE_ID,
    })
  }

  return result
}

export function datasetsForSource(
  source: UnifiedSource | undefined,
  catalog?: CatalogResponse,
): DatasetCatalogEntry[] {
  if (!source || !catalog) return []
  const wanted = new Set(source.datasetIds)
  return catalog.datasets.filter((entry) => wanted.has(entry.descriptor.dataset_id))
}

export function sourceById(
  sources: UnifiedSource[],
  id: string | undefined,
): UnifiedSource | undefined {
  if (!id) return undefined
  return sources.find((item) => item.id === id || item.name === id)
}
