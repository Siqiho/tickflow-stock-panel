const ACCOUNT_KEYS = new Set([
  'strategy-pool',
  'watchlist_columns',
  'stock_info_bar_fields',
  'screener_result_columns',
  'watchlist_view',
  'watchlist_showCandle',
  'watchlist_boardFilter',
  'screener_showCandle',
  'screener-card-size',
  'limit-ladder-board-filter',
  'limit-ladder-ext-fields',
  'limit-ladder-show-ext',
  'limit-ladder-direction',
  'limit-ladder-seal-mode',
  'strategy-draft',
  'strategy-modify',
  'strategy-builder-draft',
  'strategy-rules',
  'strategy-backtest-last',
  'backtest_reconnect',
  'concept-analysis-config',
  'industry-analysis-config',
  'monitor_last_seen_total',
])

const ACCOUNT_PREFIXES = ['last_stock:', 'recent_stocks:', 'one-trading.hermes.']

/** Remove browser-only state that could otherwise cross an account boundary. */
export function clearAccountLocalState() {
  try {
    const remove: string[] = []
    for (let index = 0; index < localStorage.length; index += 1) {
      const key = localStorage.key(index)
      if (key && (ACCOUNT_KEYS.has(key) || ACCOUNT_PREFIXES.some(prefix => key.startsWith(prefix)))) {
        remove.push(key)
      }
    }
    remove.forEach(key => localStorage.removeItem(key))
    sessionStorage.removeItem('tf_welcome_shown')
  } catch { /* storage can be unavailable in hardened WebViews */ }
}
