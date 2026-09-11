import { useState, useEffect, useCallback, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Sparkles, Save, Loader2, ChevronLeft, ChevronRight, AlertTriangle, Settings2, FileText, Copy, Check, Terminal } from 'lucide-react'
import { api } from '@/lib/api'
import { storage } from '@/lib/storage'
import { cn } from '@/lib/cn'

// ===== 安全声明式策略工具 =====

function parseDefinition(code: string): Record<string, any> {
  try {
    const parsed = JSON.parse(code)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
  } catch {
    return {}
  }
}

function slugId(): string {
  return 'ai_' + Date.now().toString(36)
}

function parseParams(code: string): any[] {
  const params = parseDefinition(code).params
  return Array.isArray(params) ? params : []
}

function parseStringList(code: string, key: string): string[] {
  const value = parseDefinition(code)[key.toLowerCase()]
  return Array.isArray(value) ? value.filter(item => typeof item === 'string') : []
}

function parseScoring(code: string): Record<string, number> {
  const value = parseDefinition(code).scoring
  return value && typeof value === 'object' ? value : {}
}

function parseRules(code: string): string {
  return String(parseDefinition(code).rules ?? '').trim()
}

function parseMetaField(code: string, field: string): string {
  return String(parseDefinition(code)[field] ?? '')
}

// ===== 常量 =====

const DIRECTIONS = [
  { value: 'long', label: '做多' },
  { value: 'short', label: '做空' },
  { value: 'monitor', label: '监控' },
]

// ===== 组件 =====

const CUSTOM_TEMPLATE = `{
  "id": "custom_my_strategy",
  "name": "我的策略",
  "description": "收盘站上 MA20 且量比放大",
  "source": "custom",
  "direction": "long",
  "rules": "收盘价高于 MA20，且 5 日量比大于 1.5",
  "logic": "all",
  "conditions": [
    { "left": "close", "op": ">", "right": "field:ma20" },
    { "left": "vol_ratio_5d", "op": ">", "right": 1.5 }
  ],
  "basic_filter": { "price_min": 3, "price_max": 200, "exclude_st": true },
  "scoring": { "change_pct": 0.5, "vol_ratio_5d": 0.5 },
  "entry_signals": [],
  "exit_signals": ["signal_ma20_breakdown"],
  "stop_loss": -0.05,
  "max_hold_days": 20,
  "order_by": "score",
  "descending": true,
  "limit": 100
}`

interface Props {
  open: boolean
  onClose: () => void
  onSavedId?: (id: string, researchOnly?: boolean) => void | Promise<void>
  mode?: 'create' | 'modify'
  stockContext?: { symbol: string; name: string }
  existingStrategyIds?: Set<string>
}

export function StrategyBuilderDialog({ open, onClose, onSavedId, mode = 'create', stockContext, existingStrategyIds: _existingStrategyIds }: Props) {
  // 根据 mode 选择存储 key
  const draftStore = mode === 'modify' ? storage.strategyModify : storage.strategyDraft
  const stockLabel = stockContext?.name?.trim() || stockContext?.symbol || ''
  const stockSeed = useMemo(() => stockContext?.symbol
    ? {
        name: `${stockLabel}特征策略`,
        description: `以${stockLabel}（${stockContext.symbol}）为参考标的生成可复用选股策略`,
        rules: `参考${stockLabel}（${stockContext.symbol}）的走势、量价与技术指标特征，提炼可泛化的选股条件；不要把策略限定为只匹配这一只股票。`,
      }
    : null, [stockContext?.symbol, stockLabel])
  const [step, setStep] = useState(1)
  const [tab, setTab] = useState<'ai' | 'custom'>('ai')
  const [customCopied, setCustomCopied] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [direction, setDirection] = useState('long')
  const [rules, setRules] = useState('')
  const [code, setCode] = useState('')
  const [instruction, setInstruction] = useState('')
  const [previewTab, setPreviewTab] = useState<'params' | 'code'>('params')
  const [strategyId, setStrategyId] = useState('')

  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [aiStatus, setAiStatus] = useState<{ configured: boolean; message?: string } | null>(null)
  const [checkedAi, setCheckedAi] = useState(false)
  const [loaded, setLoaded] = useState(false)

  // 打开时恢复草稿
  useEffect(() => {
    if (!open) { setLoaded(false); return }
    const d = draftStore.get(null)
    if (d) {
      setStep(d.step ?? 1); setName(d.name ?? ''); setDescription(d.description ?? '')
      setDirection(d.direction ?? 'long')
      setRules(d.rules ?? ''); setCode(d.code ?? ''); setStrategyId(d.strategyId ?? '')
    } else if (stockSeed) {
      setStep(1); setName(stockSeed.name); setDescription(stockSeed.description)
      setDirection('long'); setRules(stockSeed.rules); setCode(''); setStrategyId('')
    }
    setLoaded(true)
  }, [draftStore, open, stockSeed])

  // 打开时检查 AI 状态
  useEffect(() => {
    if (!open || checkedAi) return
    api.strategyAiStatus().then(s => { setAiStatus(s); setCheckedAi(true) }).catch(() => setAiStatus({ configured: false }))
  }, [open, checkedAi])

  // 持久化
  const persist = useCallback(() => {
    if (!name && !rules && !code) {
      draftStore.set(null)
    } else {
      draftStore.set({ name, description, direction, rules, code, step, strategyId })
    }
  }, [code, description, direction, draftStore, name, rules, step, strategyId])
  useEffect(() => { if (loaded) persist() }, [loaded, persist])

  const clearDraft = () => {
    setName(stockSeed?.name ?? ''); setDescription(stockSeed?.description ?? ''); setDirection('long')
    setRules(stockSeed?.rules ?? ''); setCode(''); setStep(1); setError(''); setInstruction('')
    setStrategyId('')
  }

  const handleClose = () => { if (name || rules || code) persist(); onClose() }

  // Step 1: 生成
  const handleGenerate = async () => {
    if (!name.trim() || !rules.trim()) return
    if (!aiStatus?.configured) { setError(aiStatus?.message || 'AI 未配置，请在设置页面配置 API Key'); return }
    setLoading(true); setError('')
    try {
      const id = strategyId || slugId()
      setStrategyId(id)
      const generationRules = stockSeed && !rules.includes(stockContext!.symbol)
        ? `${rules.trim()}\n\n${stockSeed.rules}`
        : rules.trim()
      const res = await api.strategyBuild(1, { name: name.trim(), description: description.trim(), direction, rules: generationRules, strategy_id: id })
      if (!res.valid) { setError(res.error ?? '生成失败'); return }
      setCode(res.code); setStep(2)
      const genDesc = parseMetaField(res.code, 'description')
      const genRules = parseRules(res.code)
      if (genDesc) setDescription(genDesc)
      if (genRules) setRules(genRules)
      await api.strategySaveCode(id, res.code)
      if (genRules) { const sr = storage.strategyRules.get({}); sr[id] = genRules; storage.strategyRules.set(sr) }
    } catch (e: any) {
      const msg = String(e?.message ?? '')
      setError(msg.includes('API Key') || msg.includes('api_key') ? 'AI API Key 未配置或无效' : (msg || '生成失败'))
    } finally { setLoading(false) }
  }

  // Step 2: AI 修改
  const handleModify = async () => {
    if (!instruction.trim() || !code) return
    setLoading(true); setError('')
    try {
      const res = await api.strategyBuild(2, { current_code: code, instruction: instruction.trim() })
      if (!res.valid) { setError(res.error ?? '修改失败'); return }
      setCode(res.code); setInstruction('')
      const genDesc = parseMetaField(res.code, 'description')
      const updatedRules = parseRules(res.code)
      if (genDesc) setDescription(genDesc)
      if (updatedRules) setRules(updatedRules)
      const idMatch = res.code.match(/"id"\s*:\s*"([^"]+)"/)
      if (idMatch) {
        await api.strategySaveCode(idMatch[1], res.code)
        const sr = storage.strategyRules.get({}); sr[idMatch[1]] = updatedRules; storage.strategyRules.set(sr)
      }
    } catch (e: any) { setError(String(e?.message ?? '修改失败')) }
    finally { setLoading(false) }
  }

  // 手动保存
  const handleSave = async () => {
    if (!code) return
    setSaving(true)
    try {
      const idMatch = code.match(/"id"\s*:\s*"([^"]+)"/)
      const id = idMatch?.[1] || strategyId || slugId()
      await api.strategySaveCode(id, code)
      const genRules = parseRules(code)
      const finalRules = (genRules || rules).trim()
      if (finalRules) { const saved = storage.strategyRules.get({}); saved[id] = finalRules; storage.strategyRules.set(saved) }
      await onSavedId?.(id)
      clearDraft()
      setTimeout(() => onClose(), 1000)
    } catch (e: any) { setError(String(e?.message ?? '保存失败')) }
    setSaving(false)
  }

  if (!open) return null

  const params = parseParams(code)
  const entrySignals = parseStringList(code, 'ENTRY_SIGNALS')
  const exitSignals = parseStringList(code, 'EXIT_SIGNALS')
  const scoring = parseScoring(code)
  const parsedDefinition = parseDefinition(code)
  const codeStopLoss = typeof parsedDefinition.stop_loss === 'number' ? parsedDefinition.stop_loss : null
  const codeHoldDays = typeof parsedDefinition.max_hold_days === 'number' ? parsedDefinition.max_hold_days : null
  const hasParams = params.length > 0 || entrySignals.length > 0 || exitSignals.length > 0 || Object.keys(scoring).length > 0

  return (
    <AnimatePresence>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
        onClick={e => { if (e.target === e.currentTarget) handleClose() }}>
        <motion.div initial={{ opacity: 0, scale: 0.95, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 10 }}
          className="w-[820px] max-h-[88vh] bg-surface/95 backdrop-blur-xl border border-border/50 rounded-2xl shadow-2xl flex flex-col overflow-hidden">

          {/* 标题 */}
          <div className="grid grid-cols-[1fr_auto_1fr] items-center px-5 py-2.5 border-b border-border/50">
            {/* 左侧：Tab 切换 */}
            <div className="flex rounded-lg bg-elevated p-0.5 w-fit">
              <button onClick={() => setTab('ai')} className={cn('px-3 py-1 rounded-md text-xs font-medium transition-all cursor-pointer', tab === 'ai' ? 'bg-amber-400/15 text-amber-700 dark:text-amber-400' : 'text-muted hover:text-foreground')}>
                <Sparkles className="h-3 w-3 inline mr-1" />AI 生成
              </button>
              <button onClick={() => setTab('custom')} className={cn('px-3 py-1 rounded-md text-xs font-medium transition-all cursor-pointer', tab === 'custom' ? 'bg-accent/15 text-accent' : 'text-muted hover:text-foreground')}>
                <FileText className="h-3 w-3 inline mr-1" />安全结构
              </button>
            </div>
            {/* 中间：标题 */}
            <span className="text-sm font-semibold text-foreground">
              {strategyId ? '修改策略' : '创建策略'}
            </span>
            {/* 右侧：步骤 + 关闭 */}
            <div className="flex items-center justify-end gap-2">
              {tab === 'ai' && (
                <div className="flex items-center gap-1">
                  <span className={'w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ' + (step === 1 ? 'bg-amber-400/20 text-amber-700 dark:text-amber-400' : 'bg-emerald-400/20 text-emerald-700 dark:text-emerald-400')}>1</span>
                  <span className="text-muted/20 text-[10px]">—</span>
                  <span className={'w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ' + (step === 2 ? 'bg-amber-400/20 text-amber-700 dark:text-amber-400' : 'bg-border/50 text-muted')}>2</span>
                </div>
              )}
              <button onClick={handleClose} className="p-1.5 rounded-lg hover:bg-elevated"><X className="h-4 w-4 text-muted" /></button>
            </div>
          </div>

          {/* Tab 描述 */}
          <div className="px-5 py-2 border-b border-border/30 bg-elevated/30">
            {tab === 'ai' ? (
              <div className="flex flex-wrap items-center gap-2 text-[11px]">
                <Sparkles className="h-3.5 w-3.5 shrink-0 text-amber-700 dark:text-amber-400" />
                <span className="text-amber-700 dark:text-amber-400">步骤 1 描述策略规则 → 步骤 2 预览安全定义 → 保存到个人空间</span>
                {stockContext?.symbol && (
                  <span aria-label="策略参考股票" className="ml-auto rounded-full bg-sky-500/10 px-2 py-0.5 text-sky-600 dark:text-sky-300">
                    参考 {stockLabel} · {stockContext.symbol}
                  </span>
                )}
              </div>
            ) : (
              <div className="flex items-center gap-2 text-[11px]">
                <Terminal className="h-3.5 w-3.5 text-accent shrink-0" />
                <span className="text-muted">服务器只接受白名单字段、运算符和信号组成的 JSON，不执行用户 Python</span>
              </div>
            )}
          </div>

          {/* 内容 */}
          <div className="flex-1 overflow-y-auto px-5 py-5 space-y-4">
            {tab === 'ai' ? (<>
            {aiStatus && !aiStatus.configured && (
              <div className="rounded-xl border border-amber-400/30 bg-amber-400/5 px-4 py-3 flex items-center gap-3">
                <AlertTriangle className="h-4 w-4 text-amber-700 dark:text-amber-400 shrink-0" />
                <div className="flex-1 text-xs text-amber-700 dark:text-amber-400">AI API Key 未配置，无法生成策略。填写的内容会自动保存。</div>
                <button onClick={() => { persist(); window.location.href = '/settings?tab=ai' }}
                  className="h-7 px-3 rounded-lg bg-amber-400/15 border border-amber-400/30 text-amber-700 dark:text-amber-400 text-xs font-medium flex items-center gap-1.5 hover:bg-amber-400/20 shrink-0">
                  <Settings2 className="h-3 w-3" />去配置
                </button>
              </div>
            )}

            {step === 1 ? (
              <>
                <div className="space-y-2">
                  <input type="text" value={name} onChange={e => setName(e.target.value)} placeholder="策略名称，如：强势反包"
                    className="w-full h-9 px-3 rounded-lg bg-base border-0 ring-1 ring-border/30 text-sm font-medium text-foreground placeholder:text-muted/30 focus:outline-none focus:ring-2 focus:ring-accent/30" />
                  <input type="text" value={description} onChange={e => setDescription(e.target.value)} placeholder="一句话描述，如：筛选前日阴线下跌、今日放量阳线反包的短线强势股"
                    className="w-full h-8 px-3 rounded-lg bg-base border-0 ring-1 ring-border/30 text-sm text-foreground placeholder:text-muted/30 focus:outline-none focus:ring-2 focus:ring-accent/30" />
                </div>
                <div>
                  <span className="text-[10px] text-muted/50 uppercase tracking-wider mb-1.5 block">选股方向</span>
                  <div className="flex gap-1">
                    {DIRECTIONS.map(d => (
                      <button key={d.value} onClick={() => setDirection(d.value)} className={'px-2.5 py-1 rounded text-[11px] font-medium border transition-colors ' + (direction === d.value ? 'border-amber-400/40 bg-amber-400/10 text-amber-700 dark:text-amber-400' : 'border-border bg-base text-muted hover:border-amber-400/30')}>{d.label}</button>
                    ))}
                  </div>
                </div>
                <div>
                  <span className="text-[10px] text-muted/50 uppercase tracking-wider mb-1.5 block">策略规则</span>
                  <textarea value={rules} onChange={e => setRules(e.target.value)}
                    placeholder="描述你的选股逻辑，AI 会自动提取参数。例如：\n前一交易日为明显阴线且跌幅不低于2%，今日阳线收盘反包前一日实体，收盘价接近或高于前一日高点，成交量较前一日放大1.2倍以上，当前 close > ma5 或 close > ma10；使用 filter_history，并优先用 Polars shift/with_columns/filter 实现。"
                    className="w-full h-28 px-3 py-2 rounded-lg bg-base border-0 ring-1 ring-border/30 text-sm text-foreground placeholder:text-muted/30 resize-none focus:outline-none focus:ring-2 focus:ring-accent/30" />
                </div>
                {error && <div className="text-[11px] text-danger bg-danger/10 border border-danger/20 rounded-lg px-3 py-2">{error}</div>}
                <button onClick={handleGenerate} disabled={loading || !name.trim() || !rules.trim()}
                  className="w-full h-10 rounded-xl bg-gradient-to-r from-amber-500/20 to-amber-500/10 border border-amber-400/30 text-amber-700 dark:text-amber-400 text-sm font-medium flex items-center justify-center gap-2 hover:from-amber-500/30 hover:to-amber-500/20 disabled:opacity-40 transition-all">
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                  {loading ? 'AI 生成中...' : code ? '重新生成' : 'AI 生成策略'}
                </button>
              </>
            ) : (
              <>
                {/* Tab 切换 */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-0.5">
                    <button onClick={() => setPreviewTab('params')} className={'px-3 py-1 rounded text-xs font-medium transition-colors ' + (previewTab === 'params' ? 'bg-amber-400/15 text-amber-700 dark:text-amber-400' : 'text-muted hover:text-secondary')}>参数</button>
                    <button onClick={() => setPreviewTab('code')} className={'px-3 py-1 rounded text-xs font-medium transition-colors ' + (previewTab === 'code' ? 'bg-amber-400/15 text-amber-700 dark:text-amber-400' : 'text-muted hover:text-secondary')}>安全定义</button>
                  </div>
                </div>

                {previewTab === 'params' ? (
                  hasParams ? (
                    <div className="rounded-xl border border-border/30 bg-surface/30 overflow-hidden max-h-96 overflow-y-auto">
                      <div className="divide-y divide-border/10">
                        {params.length > 0 && (
                          <div className="px-4 py-3 space-y-2">
                            <div className="text-[10px] text-muted/50 uppercase tracking-wider">策略参数</div>
                            {params.map((p: any) => (
                              <div key={p.id} className="flex items-center gap-2">
                                <span className="text-[11px] text-secondary w-24 shrink-0 text-right">{p.label}</span>
                                {p.type === 'bool' ? (
                                  <span className={'text-[11px] font-mono ' + (p.default ? 'text-accent' : 'text-muted')}>{p.default ? '✓ 是' : '✗ 否'}</span>
                                ) : (
                                  <>
                                    <span className="text-[11px] font-mono text-foreground">{p.default}</span>
                                    <span className="text-[10px] text-muted">{p.min} ~ {p.max}{p.type === 'float' || p.type === 'int' ? ' · 步长 ' + p.step : ''}</span>
                                  </>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                        {(entrySignals.length > 0 || exitSignals.length > 0) && (
                          <div className="px-4 py-3 space-y-2">
                            <div className="text-[10px] text-muted/50 uppercase tracking-wider">交易信号</div>
                            {entrySignals.length > 0 && (
                              <div className="flex items-center gap-2">
                                <span className="text-[10px] text-emerald-700 dark:text-emerald-400 w-10 shrink-0">买入</span>
                                <div className="flex flex-wrap gap-0.5">
                                  {entrySignals.map((s: string) => <span key={s} className="px-1.5 py-0.5 rounded bg-emerald-400/10 text-emerald-700 dark:text-emerald-400 text-[10px] font-mono">{s}</span>)}
                                </div>
                              </div>
                            )}
                            {exitSignals.length > 0 && (
                              <div className="flex items-center gap-2">
                                <span className="text-[10px] text-danger w-10 shrink-0">卖出</span>
                                <div className="flex flex-wrap gap-0.5">
                                  {exitSignals.map((s: string) => <span key={s} className="px-1.5 py-0.5 rounded bg-danger/10 text-danger text-[10px] font-mono">{s}</span>)}
                                </div>
                              </div>
                            )}
                            <div className="flex items-center gap-4 text-[10px] text-muted mt-1">
                              {codeStopLoss !== null && <span>止损: {(codeStopLoss * 100).toFixed(1)}%</span>}
                              {codeHoldDays !== null && <span>持有: {codeHoldDays} 天</span>}
                            </div>
                          </div>
                        )}
                        {Object.keys(scoring).length > 0 && (
                          <div className="px-4 py-3 space-y-2">
                            <div className="text-[10px] text-muted/50 uppercase tracking-wider">评分权重</div>
                            {Object.entries(scoring).map(([k, v]) => (
                              <div key={k} className="flex items-center gap-2">
                                <span className="text-[10px] text-muted w-24 shrink-0 text-right font-mono">{k}</span>
                                <div className="flex-1 h-1.5 bg-elevated rounded-full overflow-hidden">
                                  <div className="h-full bg-amber-400/60 rounded-full" style={{ width: Math.min(v * 100, 100) + '%' }} />
                                </div>
                                <span className="w-8 text-right text-[10px] font-mono text-muted">{Math.round(v * 100)}%</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div className="rounded-xl border border-border/30 bg-surface/30 px-4 py-6 text-[11px] text-muted text-center">未检测到可调参数，切换「安全定义」查看完整内容</div>
                  )
                ) : (
                  <pre className="bg-base border border-border/30 rounded-lg p-3 text-[11px] font-mono text-foreground/80 overflow-auto max-h-96 whitespace-pre-wrap">{code}</pre>
                )}

                {error && <div className="text-[11px] text-danger bg-danger/10 border border-danger/20 rounded-lg px-3 py-2">{error}</div>}

                <div className="flex gap-2">
                  <input type="text" value={instruction} onChange={e => setInstruction(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleModify()}
                    placeholder="调整策略逻辑，如：增加RSI超卖条件、要求今日放量、修改均线为30日..."
                    className="flex-1 h-9 px-3 rounded-lg bg-base border-0 ring-1 ring-border/30 text-sm text-foreground placeholder:text-muted/30 focus:outline-none focus:ring-2 focus:ring-accent/30" />
                  <button onClick={handleModify} disabled={loading || !instruction.trim()}
                    className="h-9 px-4 rounded-lg bg-amber-400/15 border border-amber-400/30 text-amber-700 dark:text-amber-400 text-xs font-medium flex items-center gap-1.5 hover:bg-amber-400/20 disabled:opacity-40 transition-all">
                    {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                    AI 修改
                  </button>
                </div>
                <p className="text-[10px] text-muted/40">修改指令可调整参数、信号、告警、评分等任意内容。确认无误后点击「保存策略」。</p>
              </>
            )}
            </>
            ) : (
              /* 自定义编写 */
              <div className="space-y-4">
                <div className="rounded-xl border border-border/40 bg-elevated/50 p-4 space-y-2.5">
                  <div className="flex items-center gap-2">
                    <Terminal className="h-4 w-4 text-accent" />
                    <span className="text-sm font-medium text-foreground">声明式策略结构</span>
                  </div>
                  <div className="space-y-1.5 text-[11px] text-secondary leading-relaxed">
                    <p>每个账号的策略保存在自己的用户空间中。公开用户不能上传或执行 Python，只能使用下面这种经过服务器校验的 JSON 定义。</p>
                    <div className="space-y-1 pl-1">
                      <div className="flex items-start gap-1.5">
                        <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-accent/60 shrink-0" />
                        <span><strong className="text-foreground/80">条件</strong> — 字段、比较符、数字或另一个白名单字段</span>
                      </div>
                      <div className="flex items-start gap-1.5">
                        <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-amber-400/60 shrink-0" />
                        <span><strong className="text-foreground/80">回测</strong> — 买卖信号和风控参数复用现有安全引擎</span>
                      </div>
                    </div>
                    <p>管理员可以只读查看并运行用户策略，但不能替用户改写或删除。</p>
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-foreground">快速模板</span>
                    <button onClick={() => { navigator.clipboard.writeText(CUSTOM_TEMPLATE); setCustomCopied(true); setTimeout(() => setCustomCopied(false), 2000) }}
                      className={cn('inline-flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-all cursor-pointer', customCopied ? 'bg-emerald-400/10 text-emerald-700 dark:text-emerald-400' : 'bg-elevated text-muted hover:text-foreground hover:bg-accent/10')}>
                      {customCopied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                      {customCopied ? '已复制' : '复制模板'}
                    </button>
                  </div>
                  <pre className="rounded-xl border border-border/40 bg-base p-4 text-[10px] leading-relaxed font-mono text-foreground/70 overflow-auto max-h-[400px]">{CUSTOM_TEMPLATE}</pre>
                </div>
              </div>
            )}
          </div>

          {/* 底部 */}
          {tab === 'ai' && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-border/50 bg-surface/50">
            <button onClick={clearDraft} className="text-[10px] text-muted/40 hover:text-danger transition-colors">重新创建</button>
            <div className="flex items-center gap-2">
              {step === 1 && code && name.trim() && (
                <button onClick={() => setStep(2)} className="h-7 px-3 rounded-lg border border-border text-xs text-secondary hover:text-foreground flex items-center gap-1">
                  前往下一步 <ChevronRight className="h-3 w-3" />
                </button>
              )}
              {step === 2 && (
                <>
                  <button onClick={() => setStep(1)} className="h-7 px-3 rounded-lg border border-border text-xs text-secondary hover:text-foreground flex items-center gap-1">
                    <ChevronLeft className="h-3 w-3" />上一步
                  </button>
                  <button onClick={handleSave} disabled={saving || loading}
                    className="inline-flex items-center gap-1.5 h-7 px-3 rounded-lg bg-accent text-white text-xs font-medium hover:bg-accent/90 disabled:opacity-50 transition-all">
                    <Save className="h-3 w-3" />
                    {saving ? '保存中...' : '保存策略'}
                  </button>
                </>
              )}
            </div>
          </div>
          )}
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
