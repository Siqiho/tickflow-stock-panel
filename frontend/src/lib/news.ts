export type MarketSourceId = 'cls' | 'sina' | 'foreign'

export type NewsItem = {
  id: string
  source: string
  title: string
  content: string
  time: string
  data_time: string
  url: string
  subjects: string[]
  stocks: string[]
  is_red: boolean
  sentiment: string
}

export type MarketSourceState = {
  source: MarketSourceId
  label: string
  ok: boolean
  error?: string | null
  fetched_at?: string | null
  producer?: string
  endpoint?: string
  items: NewsItem[]
  from_cache?: boolean
  preserved?: boolean
}

export type MarketNewsResponse = {
  timezone: string
  sources: Record<MarketSourceId, MarketSourceState>
}

export type PolicyItem = {
  title: string
  url: string
  date: string
  source: string
}

export type PolicyNewsResponse = {
  items: PolicyItem[]
  total: number
  page: number
  page_size: number
  has_more: boolean
  search_mode: boolean
  department: string
  keyword: string
  from_cache?: boolean
  updated_at?: string | null
  last_refresh?: {
    ok?: boolean
    error?: string | null
    fetched?: number
    added?: number
    failures?: Array<{ department: string; error: string }>
  }
  note?: string
}

export type GovDepartment = {
  name: string
  url: string
}

export type DepartmentCatalog = {
  departments: GovDepartment[]
  count: number
  ok: boolean
  error?: string | null
  fetched_at?: string | null
}

export type KeyDepartments = {
  departments: string[]
  is_default: boolean
  defaults: string[]
}

export const MARKET_SOURCE_ORDER: MarketSourceId[] = ['cls', 'sina', 'foreign']

export const MARKET_SOURCE_LABEL: Record<MarketSourceId, string> = {
  cls: '财联社电报',
  sina: '新浪财经',
  foreign: '外媒',
}

export function shortDeptName(name: string) {
  return name
    .replace('中华人民共和国', '')
    .replace('国家发展和改革委员会', '发改委')
    .replace('中国证券监督管理委员会', '证监会')
    .replace('中国人民银行', '央行')
    .replace('国家金融监督管理总局', '金监总局')
    .replace('国家外汇管理局', '外汇局')
    .replace('国家统计局', '统计局')
    .replace('国家卫生健康委员会', '卫健委')
    .replace('人力资源和社会保障部', '人社部')
    .replace('住房和城乡建设部', '住建部')
    .replace('国有资产监督管理委员会', '国资委')
    .replace('市场监督管理总局', '市场监管总局')
    .replace('国家数据局', '数据局')
    .replace('国家能源局', '能源局')
    .replace('国家国际发展合作署', '国合署')
    .replace('国家国防科技工业局', '国防科工局')
}

export function sentimentClass(label: string) {
  if (label === '看涨') return 'text-bull'
  if (label === '看跌') return 'text-bear'
  return 'text-muted'
}

export function isSafeHttpUrl(value: string) {
  try {
    const url = new URL(value)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}
