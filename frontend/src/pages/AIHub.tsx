import type { LucideIcon } from 'lucide-react'
import {
  ArrowUpRight,
  BookOpenCheck,
  Bot,
  Cloud,
  FileText,
  History,
  Repeat,
  ScanSearch,
  Settings,
  Sparkles,
  TrendingUp,
} from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { PageHeader } from '@/components/PageHeader'
import { AIHistorySection } from '@/components/ai/AIHistorySection'
import { cn } from '@/lib/cn'
import { useSettings } from '@/lib/useSharedQueries'

type FeatureTone = 'blue' | 'purple' | 'amber' | 'emerald'

interface AIFeature {
  title: string
  category: string
  description: string
  requirement: string
  to: string
  icon: LucideIcon
  tone: FeatureTone
  badge?: string
}

const AI_FEATURES: AIFeature[] = [
  {
    title: 'Hermes Agent 对话',
    category: '个人助理',
    description: '进入当前账户独立的 Hermes Profile，延续会话并沉淀隔离的长期记忆。',
    requirement: '每个账户独立 Profile、Session 与长期记忆',
    to: '/ai/hermes',
    icon: Bot,
    tone: 'purple',
    badge: 'Sandbox',
  },
  {
    title: 'AI 个股分析',
    category: '综合研判',
    description: '结合日 K、关键价位、基本面、财务与消息面，生成四维个股分析报告。',
    requirement: '需要标的日 K 数据',
    to: '/stock-analysis',
    icon: TrendingUp,
    tone: 'blue',
    badge: 'Beta',
  },
  {
    title: 'AI 财务分析',
    category: '财务报告',
    description: '读取利润表、资产负债表、现金流和核心指标，生成专业财务分析报告。',
    requirement: '需要标的财务数据',
    to: '/financials',
    icon: FileText,
    tone: 'purple',
  },
  {
    title: 'AI 大盘复盘',
    category: '盘后复盘',
    description: '汇总市场、指数与板块表现，生成盘面定调、风险观察和次日交易计划。',
    requirement: '需要日 K 与指数数据',
    to: '/review',
    icon: BookOpenCheck,
    tone: 'emerald',
    badge: 'Beta',
  },
  {
    title: "AI 板块轮动分析",
    category: "题材轮动",
    description: "从概念或行业涨幅排名矩阵提炼主线、新晋、退潮和机构/游资特征。",
    requirement: "需要概念或行业扩展数据",
    to: '/concept-analysis',
    icon: Repeat,
    tone: 'amber',
    badge: 'Beta',
  },
  {
    title: 'AI 策略生成',
    category: '策略创建',
    description: '用自然语言生成或修改策略代码，检查结果后可保存到现有策略池。',
    requirement: '生成与保存由你确认',
    to: '/screener?ai=builder',
    icon: ScanSearch,
    tone: 'amber',
  },
]

const TONE_STYLES: Record<FeatureTone, {
  icon: string
  halo: string
  border: string
  eyebrow: string
}> = {
  blue: {
    icon: 'bg-blue-500/10 text-blue-600 ring-blue-400/20 dark:text-blue-300',
    halo: 'bg-blue-500/10',
    border: 'hover:border-blue-400/35',
    eyebrow: 'text-blue-600 dark:text-blue-300',
  },
  purple: {
    icon: 'bg-purple-500/10 text-purple-600 ring-purple-400/20 dark:text-purple-300',
    halo: 'bg-purple-500/10',
    border: 'hover:border-purple-400/35',
    eyebrow: 'text-purple-600 dark:text-purple-300',
  },
  amber: {
    icon: 'bg-amber-500/10 text-amber-600 ring-amber-400/20 dark:text-amber-300',
    halo: 'bg-amber-500/10',
    border: 'hover:border-amber-400/35',
    eyebrow: 'text-amber-600 dark:text-amber-300',
  },
  emerald: {
    icon: 'bg-emerald-500/10 text-emerald-600 ring-emerald-400/20 dark:text-emerald-300',
    halo: 'bg-emerald-500/10',
    border: 'hover:border-emerald-400/35',
    eyebrow: 'text-emerald-600 dark:text-emerald-300',
  },
}

type HubTab = 'catalog' | 'history' | 'stock' | 'review' | 'page'

export function AIHub() {
  const settings = useSettings()
  const aiAccess = settings.data?.ai_access
  const cloudManaged = aiAccess?.mode === 'cloud_subscription'
  const [searchParams, setSearchParams] = useSearchParams()
  const rawTab = searchParams.get('tab')
  const tab: HubTab = rawTab === 'history' || rawTab === 'stock' || rawTab === 'review' || rawTab === 'page' ? rawTab : 'catalog'
  const contextSymbol = (searchParams.get('symbol') ?? '').trim().toUpperCase()
  const contextName = (searchParams.get('name') ?? '').trim()
  const contextLabel = contextName || contextSymbol

  const setTab = (next: HubTab) => {
    const params = new URLSearchParams(searchParams)
    if (next === 'catalog') params.delete('tab')
    else params.set('tab', next)
    setSearchParams(params, { replace: true })
  }

  const withStockContext = (target: string) => {
    if (!contextSymbol) return target
    const [path, rawQuery = ''] = target.split('?', 2)
    const params = new URLSearchParams(rawQuery)
    params.set('symbol', contextSymbol)
    params.set('name', contextLabel)
    return `${path}?${params.toString()}`
  }

  const contextualRequirement = (feature: AIFeature) => {
    if (!contextSymbol) return feature.requirement
    if (feature.to === '/ai/hermes') return `围绕 ${contextLabel} · ${contextSymbol} 继续对话`
    if (feature.to === '/stock-analysis') return `继续分析 ${contextLabel} · ${contextSymbol}`
    if (feature.to === '/financials') return `查看 ${contextLabel} · ${contextSymbol} 的财务表现`
    if (feature.to === '/review') return `围绕 ${contextLabel} · ${contextSymbol} 做市场复盘`
    if (feature.to === '/concept-analysis') return `围绕 ${contextLabel} · ${contextSymbol} 看板块轮动`
    return `以 ${contextLabel} · ${contextSymbol} 为参考生成策略`
  }

  return (
    <div className="min-h-full bg-base">
      <PageHeader
        title="AI"
        subtitle="用户台 AI 分析与生成能力"
        right={
          cloudManaged ? (
            <span
              className={cn(
                'inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium',
                aiAccess.allowed
                  ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-300'
                  : 'border-amber-400/30 bg-amber-500/10 text-amber-600 dark:text-amber-300',
              )}
            >
              <Cloud className="h-3.5 w-3.5" />
              {aiAccess.message}
            </span>
          ) : (
            <Link
              to="/settings?tab=ai"
              className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-surface px-3 py-1.5 text-xs font-medium text-secondary transition-colors hover:border-purple-400/35 hover:text-foreground"
            >
              <Settings className="h-3.5 w-3.5" />
              AI 配置
            </Link>
          )
        }
      />

      <div className="mx-auto w-full max-w-6xl px-4 py-5 lg:px-6 lg:py-6">
        <div className="mb-4 inline-flex rounded-full border border-border bg-surface p-1" role="tablist" aria-label="AI 页面分区">
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'catalog'}
            onClick={() => setTab('catalog')}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors',
              tab === 'catalog'
                ? 'bg-purple-500/10 text-purple-600 dark:text-purple-300'
                : 'text-muted hover:text-foreground',
            )}
          >
            <Sparkles className="h-3.5 w-3.5" />
            功能目录
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'history'}
            onClick={() => setTab('history')}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors',
              tab === 'history'
                ? 'bg-purple-500/10 text-purple-600 dark:text-purple-300'
                : 'text-muted hover:text-foreground',
            )}
          >
            <History className="h-3.5 w-3.5" />
            历史记录
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'stock'}
            onClick={() => setTab('stock')}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors',
              tab === 'stock'
                ? 'bg-purple-500/10 text-purple-600 dark:text-purple-300'
                : 'text-muted hover:text-foreground',
            )}
          >
            <TrendingUp className="h-3.5 w-3.5" />
            个股分析
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'review'}
            onClick={() => setTab('review')}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors',
              tab === 'review'
                ? 'bg-purple-500/10 text-purple-600 dark:text-purple-300'
                : 'text-muted hover:text-foreground',
            )}
          >
            <BookOpenCheck className="h-3.5 w-3.5" />
            复盘
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'page'}
            onClick={() => setTab('page')}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors',
              tab === 'page'
                ? 'bg-purple-500/10 text-purple-600 dark:text-purple-300'
                : 'text-muted hover:text-foreground',
            )}
          >
            <Bot className="h-3.5 w-3.5" />
            页面
          </button>
        </div>

        {tab === 'catalog' ? (
        <>
        <section className="relative overflow-hidden rounded-card border border-purple-400/20 bg-gradient-to-br from-purple-500/[0.10] via-surface to-surface p-5">
          <div className="absolute -right-10 -top-16 h-40 w-40 rounded-full bg-purple-500/10 blur-3xl" />
          <div className="relative flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-purple-500/10 text-purple-600 ring-1 ring-purple-400/20 dark:text-purple-300">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-foreground">AI 功能目录</h2>
              <p className="mt-1 max-w-3xl text-sm leading-6 text-secondary">
                这里集中展示用户台中真正调用 AI 模型的功能。点击功能卡会进入原有工作位置，原来的业务菜单也会继续保留。
              </p>
              <p className="mt-2 text-xs text-muted">
                {cloudManaged
                  ? `四项分析与生成能力及 Hermes Agent 由 ${aiAccess?.plan || 'AI'} 订阅统一提供；Hermes 的 Profile、Session 与记忆按账户隔离。`
                  : '分析与生成能力共用「设置 → AI」中的模型配置；多用户 Hermes 仅在服务器统一 AI 订阅启用时可用。'}
              </p>
            </div>
          </div>
        </section>

        {contextSymbol && (
          <section
            aria-label="当前分析股票"
            className="mt-3 flex flex-wrap items-center gap-3 rounded-card border border-sky-400/25 bg-sky-500/[0.06] px-4 py-3"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-sky-500/10 text-sky-600 dark:text-sky-300">
              <TrendingUp className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <div className="text-[10px] font-medium uppercase tracking-[0.12em] text-sky-600 dark:text-sky-300">当前分析股票</div>
              <div className="mt-0.5 flex items-baseline gap-2">
                <span className="text-sm font-semibold text-foreground">{contextLabel}</span>
                <span className="font-mono text-xs text-muted">{contextSymbol}</span>
              </div>
            </div>
            <span className="ml-auto text-xs text-muted">选择下面任一能力，都会继续使用这只股票。</span>
          </section>
        )}

        <section aria-label="AI 功能" className="mt-4 grid gap-3 md:grid-cols-2">
          {AI_FEATURES.map(feature => {
            const tone = TONE_STYLES[feature.tone]
            const Icon = feature.icon
            const target = withStockContext(feature.to)
            const requirement = contextualRequirement(feature)
            return (
              <Link
                key={feature.title}
                to={target}
                aria-label={`打开${feature.title}`}
                className={cn(
                  'group relative min-h-52 overflow-hidden rounded-card border border-border bg-surface p-5 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg',
                  tone.border,
                )}
              >
                <div className={cn('absolute -right-8 -top-10 h-28 w-28 rounded-full blur-3xl', tone.halo)} />
                <div className="relative flex h-full flex-col">
                  <div className="flex items-start justify-between gap-3">
                    <div className={cn('flex h-10 w-10 items-center justify-center rounded-xl ring-1', tone.icon)}>
                      <Icon className="h-5 w-5" />
                    </div>
                    <div className="flex items-center gap-2">
                      {feature.badge && (
                        <span className="inline-flex rounded-full border border-amber-400/30 bg-amber-400/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-amber-500">
                          {feature.badge}
                        </span>
                      )}
                      <ArrowUpRight className="h-4 w-4 text-muted transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-foreground" />
                    </div>
                  </div>

                  <div className="mt-4">
                    <div className={cn('text-[11px] font-medium uppercase tracking-[0.12em]', tone.eyebrow)}>
                      {feature.category}
                    </div>
                    <h3 className="mt-1 text-base font-semibold text-foreground">{feature.title}</h3>
                    <p className="mt-2 text-sm leading-6 text-secondary">{feature.description}</p>
                  </div>

                  <div className="mt-auto pt-4 text-xs text-muted">{requirement}</div>
                </div>
              </Link>
            )
          })}
        </section>

        <p className="mt-4 text-xs leading-5 text-muted">
          分类说明：扩展分析与回测当前使用本地数据计算，没有调用 AI 模型，因此不列入本目录。概念/行业页的涨幅矩阵本身仍是本地计算；本目录只收录其中真正调用模型的 AI 轮动分析。
        </p>
        </>
        ) : tab === 'stock' ? (
          <AIHistorySection
            lockedFilter="stock"
            hideFilters
            title="个股分析"
            subtitle="每只股票一张卡，点击查看该股完整历史分析"
          />
        ) : tab === 'review' ? (
          <AIHistorySection
            lockedFilter="review"
            hideFilters
            title="复盘"
            subtitle="已保存的大盘复盘报告会集中显示在这里"
          />
        ) : tab === 'page' ? (
          <AIHistorySection
            lockedFilter="page"
            hideFilters
            title="页面"
            subtitle="各业务页保存的 AI 分析结果会集中显示在这里"
          />
        ) : (
          <AIHistorySection />
        )}
      </div>
    </div>
  )
}
