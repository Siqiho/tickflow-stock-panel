// @ts-nocheck
import type { KlineRow } from '@/lib/api'
import {
  adValues,
  adxValues,
  alligatorValues,
  aoValues,
  aroonValues,
  atrValues,
  bollingerBands,
  chaikinOscValues,
  chopValues,
  cciValues,
  cmfValues,
  cmoValues,
  coppockValues,
  demaValues,
  donchianChannelValues,
  elderRayValues,
  emaFinite,
  emaLeadingNull,
  forceIndexValues,
  hullMaValues,
  ichimokuValues,
  kamaValues,
  kdjBundle,
  keltnerChannelValues,
  macdBundle,
  massIndexValues,
  mfiValues,
  obvValues,
  pivotPointsValues,
  rocValues,
  rsiBundle,
  sarValues,
  satsValues,
  smaValues,
  smiValues,
  stochRsiValues,
  supertrendValues,
  temaSlopeValues,
  temaValues,
  trixValues,
  ulcerIndexValues,
  vwapBandsValues,
  vwapValues,
  williamsRValues,
  zigzagValues,
} from '@/lib/technical-signal-calc'

export type IndicatorSignalState = 'bullish' | 'bearish' | 'oscillating' | 'neutral'

export interface IndicatorSignal {
  name: IndicatorSignalName
  signal: IndicatorSignalState
  available?: boolean
}

export const INDICATOR_SIGNAL_NAMES = [
  'MA', 'EMA', 'BOLL', 'VWAP', 'DEMA', 'TEMA', 'TEMA斜率', 'KAMA',
  'HullMA', 'Keltner', 'SuperTrend', 'Ichimoku', 'SAR', 'Donchian',
  'Alligator', 'ZigZag', 'SATS', 'Pivot', 'VWAPBands', 'MACD', 'RSI',
  'KDJ', 'CCI', 'W%R', 'StochRSI', 'ADX', 'Aroon', 'CMO', 'TRIX',
  'ROC', 'Coppock', 'SMI', 'AO', 'OBV', 'MFI', 'CMF', 'A/D', 'FI',
  'ChaikinOsc', 'ATR', 'CHOP', 'MassIndex', 'UlcerIndex', 'ElderRay',
] as const

export type IndicatorSignalName = typeof INDICATOR_SIGNAL_NAMES[number]

export interface IndicatorSignalSummary {
  date: string | null
  total: number
  bullish: number
  bearish: number
  oscillating: number
  neutral: number
  bullishPct: number
  bearishPct: number
  oscillatingPct: number
  neutralPct: number
  signals: IndicatorSignal[]
}

export function evaluateIndicatorSignals(
  rows: KlineRow[],
  selectedDate?: string | null,
): IndicatorSignal[] {
  const normalizedRows = rows
    .filter(row => row?.date && [row.open, row.high, row.low, row.close].every(Number.isFinite))
    .map(row => ({ ...row, date: String(row.date).slice(0, 10) }))

  const endIdx = selectedDate
    ? normalizedRows.findIndex(row => row.date === selectedDate.slice(0, 10))
    : -1
  const sliced = endIdx >= 0 && endIdx < normalizedRows.length - 1
    ? normalizedRows.slice(0, endIdx + 1)
    : normalizedRows
  const closes = sliced.map(row => Number(row.close))
  const highs = sliced.map(row => Number(row.high))
  const lows = sliced.map(row => Number(row.low))
  const vols = sliced.map(row => Number(row.volume ?? 0))
  const n = closes.length
  if (n < 2) {
    return INDICATOR_SIGNAL_NAMES.map(name => ({ name, signal: 'neutral', available: false }))
  }

  const last = (arr) => {
    for (let i = arr.length - 1; i >= 0; i--) {
      if (arr[i] != null && Number.isFinite(arr[i])) return arr[i]
    }
    return null
  }
  const prev = (arr) => {
    let cnt = 0
    for (let i = arr.length - 1; i >= 0; i--) {
      if (arr[i] != null && Number.isFinite(arr[i])) {
        cnt++
        if (cnt === 2) return arr[i]
      }
    }
    return null
  }
  const signals = []

  // ── Trend indicators ──

  // MA
  {
    const m5 = smaValues(closes, 5)
    const m10 = smaValues(closes, 10)
    const m20 = smaValues(closes, 20)
    const m60 = smaValues(closes, 60)
    const v5 = last(m5), v10 = last(m10), v20 = last(m20), v60 = last(m60)
    if (v5 != null && v10 != null && v20 != null && v60 != null) {
      if (v5 > v10 && v10 > v20 && v20 > v60) signals.push({ name: 'MA', signal: 'bullish' })
      else if (v5 < v10 && v10 < v20 && v20 < v60) signals.push({ name: 'MA', signal: 'bearish' })
      else if ((v5 > v20 && v10 < v60) || (v5 < v20 && v10 > v60)) signals.push({ name: 'MA', signal: 'oscillating' })
      else signals.push({ name: 'MA', signal: 'neutral' })
    }
  }

  // EMA
  {
    const e12 = emaFinite(closes, 12)
    const e21 = emaFinite(closes, 21)
    const v12 = last(e12), v21 = last(e21)
    if (v12 != null && v21 != null) {
      if (v12 > v21) signals.push({ name: 'EMA', signal: 'bullish' })
      else if (v12 < v21) signals.push({ name: 'EMA', signal: 'bearish' })
      else signals.push({ name: 'EMA', signal: 'neutral' })
    }
  }

  // BOLL
  {
    const { upper, mid, lower } = bollingerBands(closes, 20, 2)
    const vU = last(upper), vM = last(mid), vL = last(lower), c = closes[n - 1]
    if (vU != null && vM != null && vL != null) {
      if (c > vU) signals.push({ name: 'BOLL', signal: 'bullish' })
      else if (c < vL) signals.push({ name: 'BOLL', signal: 'bearish' })
      else if (c > vM) signals.push({ name: 'BOLL', signal: 'oscillating' })
      else signals.push({ name: 'BOLL', signal: 'neutral' })
    }
  }

  // VWAP
  {
    const vw = vwapValues(highs, lows, closes, vols, 20)
    const v = last(vw), c = closes[n - 1]
    if (v != null) {
      if (c > v) signals.push({ name: 'VWAP', signal: 'bullish' })
      else if (c < v) signals.push({ name: 'VWAP', signal: 'bearish' })
      else signals.push({ name: 'VWAP', signal: 'neutral' })
    }
  }

  // DEMA
  {
    const d = demaValues(closes, 21)
    const v = last(d), c = closes[n - 1]
    if (v != null) {
      if (c > v) signals.push({ name: 'DEMA', signal: 'bullish' })
      else if (c < v) signals.push({ name: 'DEMA', signal: 'bearish' })
      else signals.push({ name: 'DEMA', signal: 'neutral' })
    }
  }

  // TEMA
  {
    const t = temaValues(closes, 21)
    const v = last(t), c = closes[n - 1]
    if (v != null) {
      if (c > v) signals.push({ name: 'TEMA', signal: 'bullish' })
      else if (c < v) signals.push({ name: 'TEMA', signal: 'bearish' })
      else signals.push({ name: 'TEMA', signal: 'neutral' })
    }
  }

  // TEMA 斜率（趋势反转点）
  {
    const slope = temaSlopeValues(closes, 21)
    const v = last(slope)
    if (v != null) {
      if (v > 0) signals.push({ name: 'TEMA斜率', signal: 'bullish' })
      else if (v < 0) signals.push({ name: 'TEMA斜率', signal: 'bearish' })
      else signals.push({ name: 'TEMA斜率', signal: 'neutral' })
    }
  }

  // KAMA
  {
    const k = kamaValues(closes, 10, 2, 30)
    const v = last(k), c = closes[n - 1], pv = prev(k)
    if (v != null && pv != null) {
      if (c > v && v > pv) signals.push({ name: 'KAMA', signal: 'bullish' })
      else if (c < v && v < pv) signals.push({ name: 'KAMA', signal: 'bearish' })
      else signals.push({ name: 'KAMA', signal: 'neutral' })
    }
  }

  // HullMA
  {
    const h = hullMaValues(closes, 9)
    const v = last(h), pv = prev(h)
    if (v != null && pv != null) {
      if (v > pv) signals.push({ name: 'HullMA', signal: 'bullish' })
      else if (v < pv) signals.push({ name: 'HullMA', signal: 'bearish' })
      else signals.push({ name: 'HullMA', signal: 'neutral' })
    }
  }

  // Keltner
  {
    const { upper: kU, lower: kL } = keltnerChannelValues(highs, lows, closes, 20, 10, 1.5)
    const vU = last(kU), vL = last(kL), c = closes[n - 1]
    if (vU != null && vL != null) {
      if (c > vU) signals.push({ name: 'Keltner', signal: 'bullish' })
      else if (c < vL) signals.push({ name: 'Keltner', signal: 'bearish' })
      else signals.push({ name: 'Keltner', signal: 'oscillating' })
    }
  }

  // SuperTrend
  {
    const { direction } = supertrendValues(highs, lows, closes, 10, 3)
    const d = last(direction)
    if (d != null) {
      if (d === 1) signals.push({ name: 'SuperTrend', signal: 'bullish' })
      else if (d === -1) signals.push({ name: 'SuperTrend', signal: 'bearish' })
      else signals.push({ name: 'SuperTrend', signal: 'neutral' })
    }
  }

  // Ichimoku
  {
    const { tenkan, kijun, spanA, senkouB } = ichimokuValues(highs, lows, closes)
    const vT = last(tenkan), vK = last(kijun), vSA = last(spanA), vSB = last(senkouB), c = closes[n - 1]
    if (vT != null && vK != null && vSA != null && vSB != null) {
      const cloudTop = Math.max(vSA, vSB)
      const cloudBot = Math.min(vSA, vSB)
      if (c > cloudTop && vT > vK) signals.push({ name: 'Ichimoku', signal: 'bullish' })
      else if (c < cloudBot && vT < vK) signals.push({ name: 'Ichimoku', signal: 'bearish' })
      else if (c >= cloudBot && c <= cloudTop) signals.push({ name: 'Ichimoku', signal: 'oscillating' })
      else signals.push({ name: 'Ichimoku', signal: 'neutral' })
    }
  }

  // SAR
  {
    const { direction } = sarValues(highs, lows, closes, 0.02, 0.2)
    const d = last(direction)
    if (d != null) {
      if (d === 1) signals.push({ name: 'SAR', signal: 'bullish' })
      else if (d === -1) signals.push({ name: 'SAR', signal: 'bearish' })
      else signals.push({ name: 'SAR', signal: 'neutral' })
    }
  }

  // Donchian
  {
    const { upper, lower } = donchianChannelValues(highs, lows, 20)
    const vU = last(upper), vL = last(lower), c = closes[n - 1]
    if (vU != null && vL != null) {
      if (c >= vU) signals.push({ name: 'Donchian', signal: 'bullish' })
      else if (c <= vL) signals.push({ name: 'Donchian', signal: 'bearish' })
      else signals.push({ name: 'Donchian', signal: 'oscillating' })
    }
  }

  // Alligator
  {
    const { jaw, teeth, lips } = alligatorValues(highs, lows, closes)
    const vJ = last(jaw), vT = last(teeth), vL = last(lips)
    if (vJ != null && vT != null && vL != null) {
      if (vL > vT && vT > vJ) signals.push({ name: 'Alligator', signal: 'bullish' })
      else if (vL < vT && vT < vJ) signals.push({ name: 'Alligator', signal: 'bearish' })
      else signals.push({ name: 'Alligator', signal: 'oscillating' })
    }
  }

  // ZigZag
  {
    const { directions } = zigzagValues(highs, lows, closes, 5)
    let zzDir = 0
    for (let i = directions.length - 1; i >= 0; i--) {
      if (directions[i] === 1 || directions[i] === -1) { zzDir = directions[i]; break }
    }
    if (zzDir === -1) signals.push({ name: 'ZigZag', signal: 'bullish' })
    else if (zzDir === 1) signals.push({ name: 'ZigZag', signal: 'bearish' })
    else signals.push({ name: 'ZigZag', signal: 'neutral' })
  }

  // SATS
  {
    const { direction } = satsValues(highs, lows, closes, vols)
    const d = last(direction)
    if (d != null) {
      if (d === 1) signals.push({ name: 'SATS', signal: 'bullish' })
      else if (d === -1) signals.push({ name: 'SATS', signal: 'bearish' })
      else signals.push({ name: 'SATS', signal: 'neutral' })
    }
  }

  // Pivot
  {
    const { pp, s1, r1 } = pivotPointsValues(highs, lows, closes)
    const vPP = last(pp), vS1 = last(s1), vR1 = last(r1), c = closes[n - 1]
    if (vPP != null && vR1 != null && vS1 != null) {
      if (c > vR1) signals.push({ name: 'Pivot', signal: 'bullish' })
      else if (c < vS1) signals.push({ name: 'Pivot', signal: 'bearish' })
      else if (c > vPP) signals.push({ name: 'Pivot', signal: 'oscillating' })
      else signals.push({ name: 'Pivot', signal: 'neutral' })
    }
  }

  // VWAPBands
  {
    const { upper: vbU, lower: vbL } = vwapBandsValues(highs, lows, closes, vols)
    const vU = last(vbU), vL = last(vbL), c = closes[n - 1]
    if (vU != null && vL != null) {
      if (c > vU) signals.push({ name: 'VWAPBands', signal: 'bullish' })
      else if (c < vL) signals.push({ name: 'VWAPBands', signal: 'bearish' })
      else signals.push({ name: 'VWAPBands', signal: 'oscillating' })
    }
  }

  // ── Momentum / oscillator indicators ──

  // MACD
  {
    const { dif, dea, hist } = macdBundle(closes)
    const vDif = last(dif), vDea = last(dea), vHist = last(hist)
    if (vDif != null && vDea != null && vHist != null) {
      if (vDif > vDea && vHist > 0) signals.push({ name: 'MACD', signal: 'bullish' })
      else if (vDif < vDea && vHist < 0) signals.push({ name: 'MACD', signal: 'bearish' })
      else if (vDif > 0 && vHist < 0) signals.push({ name: 'MACD', signal: 'oscillating' })
      else if (vDif < 0 && vHist > 0) signals.push({ name: 'MACD', signal: 'oscillating' })
      else signals.push({ name: 'MACD', signal: 'neutral' })
    }
  }

  // RSI
  {
    const rsi = rsiBundle(closes, 14)
    const v = last(rsi)
    if (v != null) {
      if (v > 70) signals.push({ name: 'RSI', signal: 'oscillating' })
      else if (v < 30) signals.push({ name: 'RSI', signal: 'oscillating' })
      else if (v > 50) signals.push({ name: 'RSI', signal: 'bullish' })
      else signals.push({ name: 'RSI', signal: 'bearish' })
    }
  }

  // KDJ
  {
    const { K, D, J } = kdjBundle(highs, lows, closes, 9)
    const vK = last(K), vD = last(D), vJ = last(J)
    if (vK != null && vD != null && vJ != null) {
      if (vJ > vK && vK > vD && vK < 80) signals.push({ name: 'KDJ', signal: 'bullish' })
      else if (vJ < vK && vK < vD && vK > 20) signals.push({ name: 'KDJ', signal: 'bearish' })
      else if (vK > 80) signals.push({ name: 'KDJ', signal: 'bearish' })
      else if (vK < 20) signals.push({ name: 'KDJ', signal: 'bullish' })
      else signals.push({ name: 'KDJ', signal: 'oscillating' })
    }
  }

  // CCI
  {
    const cci = cciValues(highs, lows, closes, 20)
    const v = last(cci)
    if (v != null) {
      if (v > 100) signals.push({ name: 'CCI', signal: 'bullish' })
      else if (v < -100) signals.push({ name: 'CCI', signal: 'bearish' })
      else signals.push({ name: 'CCI', signal: 'oscillating' })
    }
  }

  // Williams %R
  {
    const wr = williamsRValues(highs, lows, closes, 14)
    const v = last(wr)
    if (v != null) {
      if (v < -80) signals.push({ name: 'W%R', signal: 'bullish' })
      else if (v > -20) signals.push({ name: 'W%R', signal: 'bearish' })
      else signals.push({ name: 'W%R', signal: 'oscillating' })
    }
  }

  // StochRSI
  {
    const { k, d } = stochRsiValues(closes, 14, 14, 3, 3)
    const vK = last(k), vD = last(d)
    if (vK != null && vD != null) {
      if (vK < 20 && vD < 20 && vK > vD) signals.push({ name: 'StochRSI', signal: 'bullish' })
      else if (vK > 80 && vD > 80 && vK < vD) signals.push({ name: 'StochRSI', signal: 'bearish' })
      else signals.push({ name: 'StochRSI', signal: 'oscillating' })
    }
  }

  // ADX
  {
    const { adx, diP, diM } = adxValues(highs, lows, closes, 14)
    const vAdx = last(adx), vP = last(diP), vM = last(diM)
    if (vAdx != null && vP != null && vM != null) {
      if (vAdx > 25 && vP > vM) signals.push({ name: 'ADX', signal: 'bullish' })
      else if (vAdx > 25 && vP < vM) signals.push({ name: 'ADX', signal: 'bearish' })
      else signals.push({ name: 'ADX', signal: 'oscillating' })
    }
  }

  // Aroon
  {
    const { up, down } = aroonValues(highs, lows, 25)
    const vU = last(up), vD = last(down)
    if (vU != null && vD != null) {
      if (vU > 70 && vD < 30) signals.push({ name: 'Aroon', signal: 'bullish' })
      else if (vD > 70 && vU < 30) signals.push({ name: 'Aroon', signal: 'bearish' })
      else signals.push({ name: 'Aroon', signal: 'oscillating' })
    }
  }

  // CMO
  {
    const cmo = cmoValues(closes, 14)
    const v = last(cmo)
    if (v != null) {
      if (v > 50) signals.push({ name: 'CMO', signal: 'bullish' })
      else if (v < -50) signals.push({ name: 'CMO', signal: 'bearish' })
      else signals.push({ name: 'CMO', signal: 'oscillating' })
    }
  }

  // TRIX
  {
    const trix = trixValues(closes, 15)
    const signal = emaLeadingNull(trix, 9)
    const vT = last(trix), vS = last(signal)
    if (vT != null && vS != null) {
      if (vT > vS) signals.push({ name: 'TRIX', signal: 'bullish' })
      else if (vT < vS) signals.push({ name: 'TRIX', signal: 'bearish' })
      else signals.push({ name: 'TRIX', signal: 'neutral' })
    }
  }

  // ROC
  {
    const roc = rocValues(closes, 12)
    const v = last(roc)
    if (v != null) {
      if (v > 0) signals.push({ name: 'ROC', signal: 'bullish' })
      else if (v < 0) signals.push({ name: 'ROC', signal: 'bearish' })
      else signals.push({ name: 'ROC', signal: 'neutral' })
    }
  }

  // Coppock
  {
    const cp = coppockValues(closes)
    const v = last(cp), pv = prev(cp)
    if (v != null && pv != null) {
      if (v > 0 && pv <= 0) signals.push({ name: 'Coppock', signal: 'bullish' })
      else if (v < 0) signals.push({ name: 'Coppock', signal: 'bearish' })
      else signals.push({ name: 'Coppock', signal: 'neutral' })
    }
  }

  // SMI
  {
    const { smi: smiData, signal: smiSig } = smiValues(highs, lows, closes)
    const vSmi = last(smiData), vSig = last(smiSig)
    if (vSmi != null && vSig != null) {
      if (vSmi > vSig && vSmi > 0) signals.push({ name: 'SMI', signal: 'bullish' })
      else if (vSmi < vSig && vSmi < 0) signals.push({ name: 'SMI', signal: 'bearish' })
      else signals.push({ name: 'SMI', signal: 'oscillating' })
    }
  }

  // AO
  {
    const ao = aoValues(highs, lows)
    const v = last(ao), pv = prev(ao)
    if (v != null && pv != null) {
      if (v > 0 && v > pv) signals.push({ name: 'AO', signal: 'bullish' })
      else if (v < 0 && v < pv) signals.push({ name: 'AO', signal: 'bearish' })
      else if (v > 0 && v < pv) signals.push({ name: 'AO', signal: 'oscillating' })
      else signals.push({ name: 'AO', signal: 'neutral' })
    }
  }

  // ── Volume indicators ──

  // OBV
  {
    const obv = obvValues(closes, vols)
    const v = last(obv), pv = prev(obv)
    if (v != null && pv != null) {
      if (v > pv) signals.push({ name: 'OBV', signal: 'bullish' })
      else if (v < pv) signals.push({ name: 'OBV', signal: 'bearish' })
      else signals.push({ name: 'OBV', signal: 'neutral' })
    }
  }

  // MFI
  {
    const mfi = mfiValues(highs, lows, closes, vols, 14)
    const v = last(mfi)
    if (v != null) {
      if (v > 80) signals.push({ name: 'MFI', signal: 'oscillating' })
      else if (v < 20) signals.push({ name: 'MFI', signal: 'oscillating' })
      else if (v > 50) signals.push({ name: 'MFI', signal: 'bullish' })
      else signals.push({ name: 'MFI', signal: 'bearish' })
    }
  }

  // CMF
  {
    const cmf = cmfValues(highs, lows, closes, vols, 20)
    const v = last(cmf)
    if (v != null) {
      if (v > 0.05) signals.push({ name: 'CMF', signal: 'bullish' })
      else if (v < -0.05) signals.push({ name: 'CMF', signal: 'bearish' })
      else signals.push({ name: 'CMF', signal: 'oscillating' })
    }
  }

  // A/D
  {
    const ad = adValues(highs, lows, closes, vols)
    const v = last(ad), pv = prev(ad)
    if (v != null && pv != null) {
      if (v > pv) signals.push({ name: 'A/D', signal: 'bullish' })
      else if (v < pv) signals.push({ name: 'A/D', signal: 'bearish' })
      else signals.push({ name: 'A/D', signal: 'neutral' })
    }
  }

  // ForceIndex
  {
    const fi = forceIndexValues(closes, vols, 13)
    const v = last(fi)
    if (v != null) {
      if (v > 0) signals.push({ name: 'FI', signal: 'bullish' })
      else if (v < 0) signals.push({ name: 'FI', signal: 'bearish' })
      else signals.push({ name: 'FI', signal: 'neutral' })
    }
  }

  // ChaikinOsc
  {
    const co = chaikinOscValues(highs, lows, closes, vols, 3, 10)
    const v = last(co), pv = prev(co)
    if (v != null && pv != null) {
      if (v > 0 && v > pv) signals.push({ name: 'ChaikinOsc', signal: 'bullish' })
      else if (v < 0 && v < pv) signals.push({ name: 'ChaikinOsc', signal: 'bearish' })
      else signals.push({ name: 'ChaikinOsc', signal: 'oscillating' })
    }
  }

  // ── Volatility indicators ──

  // ATR
  {
    const atr = atrValues(highs, lows, closes, 14)
    const v = last(atr), pv = prev(atr)
    if (v != null && pv != null) {
      if (v > pv) signals.push({ name: 'ATR', signal: 'oscillating' })
      else signals.push({ name: 'ATR', signal: 'neutral' })
    }
  }

  // CHOP
  {
    const chop = chopValues(highs, lows, closes, 14)
    const v = last(chop)
    if (v != null) {
      if (v > 61.8) signals.push({ name: 'CHOP', signal: 'oscillating' })
      else signals.push({ name: 'CHOP', signal: 'neutral' })
    }
  }

  // MassIndex
  {
    const mi = massIndexValues(highs, lows)
    const v = last(mi), pv = prev(mi)
    if (v != null && pv != null) {
      if (pv > 27 && v < 27) signals.push({ name: 'MassIndex', signal: 'bullish' })
      else signals.push({ name: 'MassIndex', signal: 'neutral' })
    }
  }

  // UlcerIndex
  {
    const ui = ulcerIndexValues(closes)
    const v = last(ui)
    if (v != null) {
      if (v < 5) signals.push({ name: 'UlcerIndex', signal: 'bullish' })
      else if (v > 15) signals.push({ name: 'UlcerIndex', signal: 'bearish' })
      else signals.push({ name: 'UlcerIndex', signal: 'neutral' })
    }
  }

  // ElderRay
  {
    const { bullPower, bearPower } = elderRayValues(highs, lows, closes, 13)
    const bP = last(bullPower), brP = last(bearPower)
    if (bP != null && brP != null) {
      if (bP > 0 && bP > brP) signals.push({ name: 'ElderRay', signal: 'bullish' })
      else if (brP < 0 && brP < bP) signals.push({ name: 'ElderRay', signal: 'bearish' })
      else signals.push({ name: 'ElderRay', signal: 'oscillating' })
    }
  }

  const evaluated = new Map(signals.map(signal => [signal.name, signal]))
  return INDICATOR_SIGNAL_NAMES.map(name => (
    evaluated.get(name) ?? { name, signal: 'neutral', available: false }
  ))
}


export function buildIndicatorSignalSummary(
  rows: KlineRow[],
  selectedDate?: string | null,
): IndicatorSignalSummary {
  const signals = evaluateIndicatorSignals(rows, selectedDate)
  const counts: Record<IndicatorSignalState, number> = {
    bullish: 0,
    bearish: 0,
    oscillating: 0,
    neutral: 0,
  }
  for (const signal of signals) counts[signal.signal] += 1

  const total = signals.length
  const percent = (count: number) => total > 0 ? Math.round(count / total * 100) : 0
  const requestedDate = selectedDate?.slice(0, 10) ?? null
  const normalizedDate = requestedDate && rows.some(row => row.date?.slice(0, 10) === requestedDate)
    ? requestedDate
    : rows.at(-1)?.date?.slice(0, 10) ?? null

  return {
    date: normalizedDate,
    total,
    bullish: counts.bullish,
    bearish: counts.bearish,
    oscillating: counts.oscillating,
    neutral: counts.neutral,
    bullishPct: percent(counts.bullish),
    bearishPct: percent(counts.bearish),
    oscillatingPct: percent(counts.oscillating),
    neutralPct: percent(counts.neutral),
    signals,
  }
}
