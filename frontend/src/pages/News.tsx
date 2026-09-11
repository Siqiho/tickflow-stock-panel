import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { NewsColumn } from '@/components/news/NewsColumn'
import { PolicyPanel } from '@/components/news/PolicyPanel'
import { api } from '@/lib/api'
import { MARKET_SOURCE_ORDER, type MarketSourceId, type PolicyItem } from '@/lib/news'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'

type NewsTab = 'market' | 'policy'

export function News() {
  const [params, setParams] = useSearchParams()
  const tab: NewsTab = params.get('tab') === 'policy' ? 'policy' : 'market'
  const qc = useQueryClient()
  const [previousIds, setPreviousIds] = useState<Record<MarketSourceId, Set<string>>>({
    cls: new Set(),
    sina: new Set(),
    foreign: new Set(),
  })
  const [currentDept, setCurrentDept] = useState('全部部门')
  const [keyword, setKeyword] = useState('')
  const [searchMode, setSearchMode] = useState(false)
  const [page, setPage] = useState(1)
  const [extraItems, setExtraItems] = useState<PolicyItem[]>([])
  const [extraHasMore, setExtraHasMore] = useState(false)
  const [refreshingSource, setRefreshingSource] = useState<string | null>(null)

  const marketQuery = useQuery({
    queryKey: QK.newsMarket,
    queryFn: api.newsMarket,
    enabled: tab === 'market',
  })
  const policyQuery = useQuery({
    queryKey: QK.newsPolicy(currentDept, searchMode ? keyword : '', 1),
    queryFn: () => api.newsPolicy({
      department: currentDept === '全部部门' ? '' : currentDept,
      keyword: searchMode ? keyword : '',
      page: 1,
      pageSize: searchMode ? 200 : 100,
    }),
    enabled: tab === 'policy',
  })
  const deptQuery = useQuery({
    queryKey: QK.newsDepartments,
    queryFn: api.newsDepartments,
    enabled: tab === 'policy',
  })
  const keyQuery = useQuery({
    queryKey: QK.newsKeyDepartments,
    queryFn: api.newsKeyDepartments,
    enabled: tab === 'policy',
  })

  const refreshMarket = useMutation({
    mutationFn: (source: MarketSourceId | 'all') => api.newsRefreshMarket(source),
    onSuccess: (data, source) => {
      if (source !== 'all') {
        const prev = new Set((marketQuery.data?.sources[source]?.items ?? []).map(item => item.id))
        setPreviousIds(current => ({ ...current, [source]: prev }))
      }
      qc.setQueryData(QK.newsMarket, data)
    },
  })
  const refreshPolicy = useMutation({
    mutationFn: async () => {
      if ((deptQuery.data?.departments.length ?? 0) === 0) {
        await api.newsRefreshDepartments()
        await qc.invalidateQueries({ queryKey: QK.newsDepartments })
      }
      return api.newsRefreshPolicy(currentDept === '全部部门' ? '' : currentDept)
    },
    onSuccess: async () => {
      setPage(1)
      setExtraItems([])
      setExtraHasMore(false)
      await qc.invalidateQueries({ queryKey: QK.newsPolicy(currentDept, searchMode ? keyword : '', 1) })
    },
  })
  const saveKeys = useMutation({
    mutationFn: (departments: string[]) => api.newsSaveKeyDepartments(departments),
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.newsKeyDepartments }),
  })

  const visibleItems = [...(policyQuery.data?.items ?? []), ...extraItems]
  const lastRefresh = refreshPolicy.data?.last_refresh || policyQuery.data?.last_refresh
  const policyError = [
    lastRefresh?.error,
    lastRefresh?.failures?.length
      ? `${lastRefresh.failures.length} 个部门失败，已保留其他部门与上次数据`
      : '',
    deptQuery.data?.error,
  ].filter(Boolean).join('；') || null
  const headerHint = searchMode
    ? '搜索已入库的历史政策'
    : currentDept === '全部部门'
      ? '全部部门按日期倒序'
      : '只展示该部门官网发布的内容'

  function setTab(next: NewsTab) {
    const copy = new URLSearchParams(params)
    if (next === 'market') copy.delete('tab')
    else copy.set('tab', next)
    setParams(copy, { replace: true })
  }

  function selectDept(name: string) {
    setCurrentDept(name)
    setPage(1)
    setExtraItems([])
    setExtraHasMore(false)
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-base px-3 py-3 md:px-4">
      <div className="mb-3 flex items-center gap-3">
        <h1 className="text-lg font-semibold tracking-tight">资讯</h1>
        <div className="flex rounded-btn border border-border bg-surface p-0.5">
          <button
            type="button"
            onClick={() => setTab('market')}
            className={cn('rounded px-3 py-1 text-[12px]', tab === 'market' ? 'bg-elevated font-medium' : 'text-secondary')}
          >
            市场快讯
          </button>
          <button
            type="button"
            onClick={() => setTab('policy')}
            className={cn('rounded px-3 py-1 text-[12px]', tab === 'policy' ? 'bg-elevated font-medium' : 'text-secondary')}
          >
            政策信息
          </button>
        </div>
      </div>

      {tab === 'market' && (
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 xl:grid-cols-3">
          {MARKET_SOURCE_ORDER.map(source => (
            <NewsColumn
              key={source}
              state={marketQuery.data?.sources[source]}
              previousIds={previousIds[source]}
              refreshing={refreshingSource === source && refreshMarket.isPending}
              onRefresh={() => {
                setRefreshingSource(source)
                refreshMarket.mutate(source, { onSettled: () => setRefreshingSource(null) })
              }}
            />
          ))}
        </div>
      )}

      {tab === 'policy' && (
        <PolicyPanel
          departments={deptQuery.data?.departments ?? []}
          keyDepartments={keyQuery.data ?? { departments: [], is_default: true, defaults: [] }}
          items={visibleItems}
          total={policyQuery.data?.total ?? visibleItems.length}
          hasMore={page <= 1 ? Boolean(policyQuery.data?.has_more) : extraHasMore}
          currentDept={currentDept}
          keyword={keyword}
          searchMode={searchMode}
          loading={policyQuery.isLoading}
          refreshing={refreshPolicy.isPending}
          error={policyError}
          headerHint={headerHint}
          onSelectDept={selectDept}
          onKeywordChange={setKeyword}
          onSearch={() => {
            setExtraItems([])
            setExtraHasMore(false)
            setPage(1)
            setSearchMode(Boolean(keyword.trim()))
          }}
          onClearSearch={() => {
            setKeyword('')
            setSearchMode(false)
            setPage(1)
            setExtraItems([])
            setExtraHasMore(false)
          }}
          onRefresh={() => refreshPolicy.mutate()}
          onLoadMore={async () => {
            const next = page + 1
            const more = await api.newsPolicy({
              department: currentDept === '全部部门' ? '' : currentDept,
              keyword: searchMode ? keyword : '',
              page: next,
              pageSize: searchMode ? 200 : 100,
            })
            setExtraItems(current => [...current, ...more.items])
            setExtraHasMore(Boolean(more.has_more))
            setPage(next)
          }}
          onToggleKey={() => {
            if (currentDept === '全部部门') return
            const current = keyQuery.data?.departments ?? []
            const next = current.includes(currentDept)
              ? current.filter(name => name !== currentDept)
              : [...current, currentDept]
            saveKeys.mutate(next)
          }}
          onRemoveKey={name => saveKeys.mutate((keyQuery.data?.departments ?? []).filter(item => item !== name))}
          onSaveKeys={async names => {
            await saveKeys.mutateAsync(names)
          }}
          onResetKeys={async () => {
            await saveKeys.mutateAsync([])
          }}
        />
      )}
    </div>
  )
}
