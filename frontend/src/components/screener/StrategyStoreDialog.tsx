import { motion, AnimatePresence } from 'framer-motion'
import { X, Store, Hammer, Download, Zap } from 'lucide-react'

interface Props {
  open: boolean
  onClose: () => void
}

/**
 * 获取策略（占位）
 * 目标：不定时更新更多策略。功能正在建设中，当前仅占位。
 */
export function StrategyStoreDialog({ open, onClose }: Props) {
  return (
    <AnimatePresence>
      {open && (
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
            className="flex max-h-[calc(100dvh-1.5rem)] w-full max-w-[560px] flex-col rounded-card border border-border bg-surface shadow-xl sm:max-h-[78vh]"
          >
            {/* 标题 */}
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-border shrink-0">
              <span className="flex items-center gap-1.5 text-sm font-medium text-foreground">
                <Store className="h-4 w-4 text-accent" />
                获取策略
              </span>
              <button aria-label="关闭获取策略" onClick={onClose} className="inline-flex h-11 w-11 items-center justify-center rounded transition-colors hover:bg-elevated sm:h-8 sm:w-8 cursor-pointer">
                <X className="h-4 w-4 text-muted" />
              </button>
            </div>

            {/* 建设中占位内容 */}
            <div className="flex flex-1 flex-col items-center justify-center overflow-y-auto px-5 py-10 text-center sm:px-6 sm:py-14">
              <div className="relative mb-5">
                <div className="absolute inset-0 blur-2xl bg-amber-400/20 rounded-full" />
                <div className="relative h-16 w-16 rounded-2xl bg-amber-400/10 border border-amber-400/30 flex items-center justify-center">
                  <Hammer className="h-8 w-8 text-amber-400" />
                </div>
              </div>

              <h3 className="text-base font-semibold text-foreground mb-1.5">
                不定时更新更多策略
              </h3>
              <p className="text-sm text-muted leading-relaxed max-w-[380px]">
                敬请期待。
              </p>

              <div className="mt-6 flex flex-wrap items-center justify-center gap-3 text-[11px] text-muted sm:gap-4">
                <span className="flex items-center gap-1">
                  <Download className="h-3.5 w-3.5" />
                  一键下载
                </span>
                <span className="w-px h-3 bg-border" />
                <span className="flex items-center gap-1">
                  <Zap className="h-3.5 w-3.5" />
                  无需配置 即可使用
                </span>
              </div>
            </div>

            {/* 底部关闭 */}
            <div className="flex justify-end px-4 py-2.5 border-t border-border shrink-0">
              <button
                onClick={onClose}
                className="inline-flex min-h-11 items-center gap-1.5 px-4 rounded-btn sm:min-h-7
                  border border-border bg-surface text-xs font-medium text-secondary
                  hover:text-accent hover:border-accent/50 transition-colors cursor-pointer"
              >
                知道了
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
