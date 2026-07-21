import type { QueryClient } from '@tanstack/react-query'
import { QK } from './queryKeys'

export const INDEX_INSTRUMENT_CATALOG_DATASETS = [
  'index_instruments',
  'etf_instruments',
] as const

export const INDEX_DAILY_CATALOG_DATASETS = [
  ...INDEX_INSTRUMENT_CATALOG_DATASETS,
  'index_daily',
  'index_enriched',
] as const

export function invalidateIndexCatalogQueries(
  queryClient: QueryClient,
  datasetIds: readonly string[],
) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: QK.dataStatus, exact: true }),
    queryClient.invalidateQueries({ queryKey: QK.dataCatalog, exact: true }),
    queryClient.invalidateQueries({ queryKey: QK.dataCatalogRuns(), exact: true }),
    ...datasetIds.flatMap((datasetId) => [
      queryClient.invalidateQueries({ queryKey: QK.dataCatalogDataset(datasetId), exact: true }),
      queryClient.invalidateQueries({ queryKey: QK.dataCatalogSchema(datasetId), exact: true }),
      queryClient.invalidateQueries({ queryKey: QK.dataCatalogRuns(datasetId), exact: true }),
    ]),
  ])
}
