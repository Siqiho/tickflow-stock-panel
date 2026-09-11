import { useState } from 'react'
import { Check } from 'lucide-react'
import { storage } from '@/lib/storage'

export type CardKey =
  | 'instruments' | 'daily' | 'adj_factor' | 'enriched'
  | 'index' | 'etf' | 'minute' | 'financials' | 'f10' | 'reference'

interface CardDef {
  key: CardKey
  label: string
  desc: string
}

export const DATA_CARD_DEFS: CardDef[] = [
  { key: 'instruments', label: '个股维表', desc: 'A 股股票元数据' },
  { key: 'daily', label: '日 K', desc: 'A 股日 K 数据' },
  { key: 'adj_factor', label: '除权因子', desc: '复权因子' },
  { key: 'enriched', label: 'Enriched', desc: '技术指标计算结果' },
  { key: 'index', label: '指数', desc: '指数维表、日 K 与指标' },
  { key: 'etf', label: 'ETF', desc: '场内基金维表、日 K 与指标' },
  { key: 'minute', label: '分钟 K', desc: '分钟级 K 线' },
  { key: 'financials', label: '财务数据', desc: '利润、资产负债、现金流、股本与指标' },
  { key: 'f10', label: '股票 F10', desc: '融资融券等事件型与交易型补充数据' },
  { key: 'reference', label: '参考数据', desc: '交易日历、派生估值、涨跌停事件、成分历史与公司行动' },
]

const DEFAULT_KEYS = DATA_CARD_DEFS.map((definition) => definition.key)

export function getCardVisibility(
  _caps: Record<string, unknown> | undefined,
): Record<CardKey, boolean> {
  const overrides = storage.dataCardVisible.get({})
  return Object.fromEntries(DATA_CARD_DEFS.map((definition) => [
    definition.key,
    overrides[definition.key] ?? true,
  ])) as Record<CardKey, boolean>
}

export function PageSettingsModal({
  caps,
}: {
  caps: Record<string, unknown> | undefined
}) {
  const [visible, setVisible] = useState<Record<CardKey, boolean>>(() => getCardVisibility(caps))

  const persist = (next: Record<CardKey, boolean>) => {
    setVisible(next)
    storage.dataCardVisible.set(next)
    window.dispatchEvent(new CustomEvent('data-card-visible-change'))
  }

  const reset = () => {
    const defaults = Object.fromEntries(DEFAULT_KEYS.map((key) => [key, true])) as Record<CardKey, boolean>
    persist(defaults)
  }

  return (
    <div className="space-y-2.5">
      <p className="text-xs text-secondary leading-relaxed">
        这些开关只影响目录渲染，不影响数据或请求。目录查询始终读取同一份本地 catalog。
      </p>
      <div className="space-y-1.5">
        {DATA_CARD_DEFS.map((definition) => {
          const on = visible[definition.key]
          return (
            <div
              key={definition.key}
              className={`flex items-center gap-2 rounded-card border px-3 py-2 transition-colors ${
                on ? 'border-accent/40 bg-accent/[0.05]' : 'border-border bg-base/30'
              }`}
            >
              <button
                type="button"
                onClick={() => persist({ ...visible, [definition.key]: !on })}
                className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors ${
                  on ? 'bg-accent border-accent' : 'bg-base border-border'
                }`}
                role="checkbox"
                aria-checked={on}
                aria-label={`显示 ${definition.label}`}
              >
                {on && <Check aria-hidden="true" className="h-3 w-3 text-white" strokeWidth={3} />}
              </button>
              <div className="min-w-0 flex-1">
                <div className="text-xs font-medium text-foreground">{definition.label}</div>
                <div className="text-[10px] text-muted leading-snug">{definition.desc}</div>
              </div>
            </div>
          )
        })}
      </div>
      <div className="flex items-center justify-end pt-1">
        <button
          type="button"
          onClick={reset}
          className="px-2 py-0.5 rounded-btn text-[10px] text-secondary hover:text-foreground transition-colors"
        >
          恢复默认
        </button>
      </div>
    </div>
  )
}
