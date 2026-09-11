import { useState, useMemo, useEffect, useCallback } from 'react'
import { motion, AnimatePresence, Reorder } from 'framer-motion'
import { X, Plus, GripVertical, ListPlus, Loader2, Trash2 } from 'lucide-react'
import { api, type StrategyDetail } from '@/lib/api'

interface Props {
  pool: string[]
  onConfirm: (newPool: string[]) => void
  onClose: () => void
}

const SOURCE_CLS: Record<string, string> = {
  builtin: 'bg-accent/10 text-accent border-accent/20',
  custom: 'bg-amber-400/10 text-amber-700 dark:text-amber-400 border-amber-400/30',
  ai: 'bg-purple-500/10 text-purple-700 dark:text-purple-400 border-purple-500/20',
  // 叠加策略归入「自定义」分组展示, 徽标与 StrategyCard 一致用 teal 区分
  composite: 'bg-teal-500/10 text-teal-400 border-teal-500/30',
  invalid: 'bg-danger/10 text-danger border-danger/20',
}

const SOURCE_LABEL: Record<string, string> = {
  builtin: '内置',
  custom: '自定义',
  ai: 'AI',
  composite: '叠加',
  invalid: '失效',
}

type SourceTab = 'all' | 'builtin' | 'custom' | 'ai'

const TABS: { id: SourceTab; label: string }[] = [
  { id: 'all', label: '全部' },
  { id: 'builtin', label: '内置' },
  { id: 'custom', label: '自定义' },
  { id: 'ai', label: 'AI' },
]

export function StrategyPoolDialog({ pool, onConfirm, onClose }: Props) {
  // 草稿状态: 打开时从 pool 复制, 操作只改草稿, 点确定才提交
  const [draftPool, setDraftPool] = useState<string[]>(() => [...pool])
  const [allStrategies, setAllStrategies] = useState<StrategyDetail[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<SourceTab>('all')
  const [publishingId, setPublishingId] = useState<string | null>(null)

  useEffect(() => {
    api.strategyList()
      .then(d => setAllStrategies(d.strategies))
      .catch(() => setAllStrategies([]))
      .finally(() => setLoading(false))
  }, [])

  const stratMap = useMemo(() => {
    const m = new Map<string, StrategyDetail>()
    allStrategies.forEach(s => m.set(s.id, s))
    return m
  }, [allStrategies])

  const validDraft = useMemo(
    () => draftPool.filter(id => stratMap.has(id)),
    [draftPool, stratMap]
  )
  const invalidPoolCount = draftPool.length - validDraft.length

  const available = useMemo(
    () => allStrategies.filter(s => !s.research_only && !draftPool.includes(s.id)),
    [allStrategies, draftPool]
  )

  // research_only 草稿(AI 来源)单独列出, 供「发布」操作; 不进待选列表
  const drafts = useMemo(
    () => allStrategies.filter(s => s.research_only),
    [allStrategies]
  )

  // 按 Tab 分组过滤待选; 叠加策略(composite)并入「自定义」分组
  const filteredAvailable = useMemo(() => {
    if (activeTab === 'all') return available
    if (activeTab === 'custom') {
      return available.filter(s => s.source === 'custom' || s.source === 'composite')
    }
    return available.filter(s => s.source === activeTab)
  }, [available, activeTab])

  const handleAdd = useCallback((id: string) => {
    setDraftPool(prev => prev.includes(id) ? prev : [...prev, id])
  }, [])

  const handleRemove = useCallback((id: string) => {
    setDraftPool(prev => prev.filter(x => x !== id))
  }, [])

  const handleReorder = useCallback((newOrder: string[]) => {
    setDraftPool(newOrder)
  }, [])

  const handleClearAll = useCallback(() => {
    setDraftPool([])
  }, [])

  const handleAddGroup = useCallback(() => {
    setDraftPool(prev => {
      const next = [...prev]
      for (const s of filteredAvailable) {
        if (!next.includes(s.id)) next.push(s.id)
      }
      return next
    })
  }, [filteredAvailable])

  const handlePublish = useCallback(async (id: string) => {
    setPublishingId(id)
    try {
      await api.strategyPublish(id)
    } finally {
      setPublishingId(null)
    }
  }, [])

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-3 sm:items-center"
        onClick={e => { if (e.target === e.currentTarget) onClose() }}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 10 }}
          transition={{ duration: 0.15, ease: [0.16, 1, 0.3, 1] }}
          className="flex max-h-[calc(100dvh-1.5rem)] w-full max-w-[680px] flex-col rounded-card border border-border bg-surface shadow-xl sm:max-h-[78vh]"
        >
          {/* 标题 */}
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-border shrink-0">
            <span className="text-sm font-medium text-foreground">
              策略池 <span className="text-muted font-normal text-xs">{validDraft.length} / {allStrategies.length}</span>
              {invalidPoolCount > 0 && <span className="ml-2 text-[10px] text-danger">{invalidPoolCount} 个失效</span>}
            </span>
            <button aria-label="关闭策略池" onClick={onClose} className="inline-flex h-11 w-11 items-center justify-center rounded transition-colors hover:bg-elevated sm:h-8 sm:w-8 cursor-pointer">
              <X className="h-4 w-4 text-muted" />
            </button>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="w-5 h-5 border-2 border-accent/30 border-t-accent rounded-full animate-spin" />
            </div>
          ) : (
            <div className="flex min-h-0 flex-1 flex-col overflow-y-auto md:grid md:grid-cols-2 md:overflow-hidden">
              {/* 左侧: 待选 (Tab 分组) */}
              <div className="flex min-h-[16rem] flex-col border-b border-border md:min-h-0 md:border-b-0 md:border-r">
                <div className="flex shrink-0 items-center gap-0.5 overflow-x-auto border-b border-border/60 px-3 py-2">
                  {TABS.map(tab => {
                    const count = tab.id === 'all'
                      ? available.length
                      : tab.id === 'custom'
                        ? available.filter(s => s.source === 'custom' || s.source === 'composite').length
                        : available.filter(s => s.source === tab.id).length
                    return (
                      <button
                        key={tab.id}
                        onClick={() => setActiveTab(tab.id)}
                        className={`min-h-9 shrink-0 px-2.5 py-1 text-[11px] font-medium rounded-btn transition-colors cursor-pointer ${
                          activeTab === tab.id
                            ? 'bg-accent/10 text-accent'
                            : 'text-muted hover:text-secondary hover:bg-elevated'
                        }`}
                      >
                        {tab.label}
                        <span className="ml-1 text-[9px] opacity-60">{count}</span>
                      </button>
                    )
                  })}
                  <button
                    onClick={handleAddGroup}
                    disabled={filteredAvailable.length === 0}
                    title="把当前分组剩余的策略全部加入策略池"
                    className="ml-auto inline-flex items-center gap-1 px-2 py-1 rounded-btn text-[10px] text-accent border border-accent/25 bg-accent/8 hover:bg-accent/15 disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer shrink-0"
                  >
                    <ListPlus className="h-3 w-3" />
                    本组全加
                  </button>
                </div>
                <div className="flex-1 overflow-y-auto px-2 py-2">
                  {activeTab === 'ai' && drafts.length > 0 && (
                    <div className="mb-3">
                      <div className="flex items-center justify-between px-1 mb-1">
                        <span className="text-[10px] font-medium text-muted">草稿</span>
                        <span className="text-[9px] text-muted">{drafts.length} 个待发布</span>
                      </div>
                      <div className="space-y-0.5">
                        {drafts.map(s => (
                          <div
                            key={s.id}
                            className="flex items-center gap-2 px-2.5 py-1.5 rounded-btn border border-purple-500/15 bg-purple-500/5"
                          >
                            <span className="flex-1 min-w-0">
                              <span className="text-[12px] text-foreground block truncate">
                                {s.name} <span className="text-[10px] text-muted font-mono">{s.id}</span>
                              </span>
                              <span className="text-[10px] text-muted truncate block">{s.description}</span>
                            </span>
                            <button
                              onClick={() => handlePublish(s.id)}
                              disabled={publishingId === s.id}
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-btn text-[10px] text-purple-400 border border-purple-500/25 bg-purple-500/10 hover:bg-purple-500/20 disabled:opacity-50 transition-colors cursor-pointer shrink-0"
                            >
                              {publishingId === s.id && <Loader2 className="h-3 w-3 animate-spin" />}
                              发布
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {filteredAvailable.length === 0 ? (
                    <div className="flex items-center justify-center h-full text-[11px] text-muted">
                      {available.length === 0 ? '全部已加入策略池' : '此分组无待选策略'}
                    </div>
                  ) : filteredAvailable.map(s => (
                    <button
                      key={s.id}
                      onClick={() => handleAdd(s.id)}
                      className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-btn
                        hover:bg-accent/8 transition-colors cursor-pointer group text-left"
                    >
                      <span className="flex-1 min-w-0">
                        <span className="text-[12px] text-foreground group-hover:text-accent transition-colors block truncate">{s.name}</span>
                        <span className="text-[10px] text-muted truncate block">{s.description}</span>
                      </span>
                      <span className={`text-[8px] px-1 py-px rounded border leading-tight shrink-0 ${SOURCE_CLS[s.source] ?? SOURCE_CLS.builtin}`}>
                        {SOURCE_LABEL[s.source] ?? '内置'}
                      </span>
                      <Plus className="h-3.5 w-3.5 text-muted/40 group-hover:text-accent shrink-0" />
                    </button>
                  ))}
                </div>
              </div>

              {/* 右侧: 已选 (Reorder.Group 纵向拖拽) */}
              <div className="flex min-h-[16rem] flex-col md:min-h-0">
                <div className="flex items-center gap-1.5 px-3 py-2 border-b border-border/60 shrink-0">
                  <GripVertical className="h-3 w-3 text-muted/50" />
                  <span className="text-[10px] text-muted">已选 · 上下拖拽排序</span>
                  <button
                    onClick={handleClearAll}
                    disabled={draftPool.length === 0}
                    title="清空已选策略池 (未点确定前可用「取消」恢复)"
                    className="ml-auto inline-flex items-center gap-1 px-2 py-1 rounded-btn text-[10px] text-muted border border-border/60 hover:text-danger hover:border-danger/30 disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer shrink-0"
                  >
                    <Trash2 className="h-3 w-3" />
                    清空
                  </button>
                </div>
                <div className="flex-1 overflow-y-auto px-2 py-2">
                  {draftPool.length === 0 ? (
                    <div className="flex items-center justify-center h-full text-[11px] text-muted">
                      从左侧点击策略添加
                    </div>
                  ) : (
                    <Reorder.Group
                      axis="y"
                      values={draftPool}
                      onReorder={handleReorder}
                      className="space-y-1"
                    >
                      {draftPool.map(id => {
                        const s = stratMap.get(id)
                        const src = s?.source ?? 'invalid'
                        return (
                          <Reorder.Item
                            key={id}
                            value={id}
                            className="flex items-center gap-2 px-2.5 py-1.5 rounded-btn
                              bg-accent/8 border border-accent/20
                              cursor-grab active:cursor-grabbing
                              hover:bg-accent/15 transition-colors group"
                            whileDrag={{ scale: 1.02, zIndex: 50, boxShadow: '0 4px 12px rgba(0,0,0,0.2)' }}
                          >
                            <GripVertical className="h-3.5 w-3.5 text-accent/40 group-hover:text-accent/70 shrink-0" />
                            <span className="flex-1 min-w-0 text-[12px] text-foreground truncate">{s?.name ?? id}</span>
                            <span className={`text-[8px] px-1 py-px rounded border leading-tight shrink-0 ${SOURCE_CLS[src] ?? SOURCE_CLS.builtin}`}>
                              {SOURCE_LABEL[src] ?? '内置'}
                            </span>
                            <button
                              onClick={(e) => { e.stopPropagation(); handleRemove(id) }}
                              className="text-muted/40 hover:text-danger transition-colors cursor-pointer leading-none shrink-0"
                              title="移除"
                            >
                              <X className="h-3.5 w-3.5" />
                            </button>
                          </Reorder.Item>
                        )
                      })}
                    </Reorder.Group>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* 底部 */}
          <div className="flex shrink-0 flex-col gap-2 border-t border-border px-4 py-2 sm:flex-row sm:items-center sm:justify-between">
            <span className="text-[10px] leading-relaxed text-muted">仅策略池中的策略会在扫描时运行</span>
            <div className="flex items-center gap-2">
              <button
                onClick={onClose}
                className="min-h-11 px-4 py-1 text-xs rounded-btn border border-border text-muted hover:text-foreground hover:border-border/80 transition-colors cursor-pointer sm:min-h-8"
              >
                取消
              </button>
              <button
                onClick={() => { onConfirm(draftPool); onClose() }}
                className="min-h-11 px-4 py-1 text-xs rounded-btn bg-accent text-white hover:bg-accent/90 transition-colors cursor-pointer sm:min-h-8"
              >
                确定
              </button>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
