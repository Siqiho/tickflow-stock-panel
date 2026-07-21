/**
 * 全局颜色别名 — 集中管理项目中重复使用的色彩组合。
 *
 * 不修改 Tailwind 配置和 CSS 变量，仅作为语义化引用。
 * 浅色用更深一级，暗色保持高亮点缀。
 */

export const color = {
  /** 选中/激活态 — sky 色系 */
  select: {
    bg: 'bg-sky-500',
    text: 'text-sky-700 dark:text-sky-400',
    border: 'border-sky-500/40 dark:border-sky-400/40',
    bgLight: 'bg-sky-500/10 dark:bg-sky-400/10',
    borderHover: 'hover:border-sky-500/30 dark:hover:border-sky-400/30',
  },
  /** 选股条件区 section 标题色 */
  filterSection: 'text-sky-700 dark:text-sky-400',

  /** 评分权重正常指示 — emerald 色系 */
  ok: 'text-emerald-700 dark:text-emerald-400',

  /** 评分权重异常警告 — amber 色系 */
  scoreWarn: 'text-amber-700 dark:text-amber-400',

  /** 交易参数区 section 标题色 */
  tradeSection: 'text-emerald-700 dark:text-emerald-400',
} as const
