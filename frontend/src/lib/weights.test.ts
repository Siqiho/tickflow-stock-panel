import { describe, expect, it } from 'vitest'
import { normalizeWeights, toPercentages } from './weights'

describe('weights', () => {
  it('converts stored decimals to slider percentages that sum to 100', () => {
    expect(toPercentages([0.6, 0.4])).toEqual([60, 40])
  })

  it('keeps zero-weight members and equalizes when all zero', () => {
    expect(normalizeWeights([0, 0])).toEqual([0.5, 0.5])
    expect(normalizeWeights([80, 20, 0])).toEqual([0.8, 0.2, 0])
  })
})
