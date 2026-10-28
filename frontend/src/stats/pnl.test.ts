import { describe, expect, it } from 'vitest'
import { spread, totalAt } from './pnl'

describe('totalAt', () => {
  const curve = [
    { at: '2026-10-20T00:00:00Z', pnl_usd: 10.17 },
    { at: '2026-10-22T00:00:00Z', pnl_usd: 4.69 },
  ]
  it('is 0 before the first close, then the last step at or before the time', () => {
    expect(totalAt(curve, Date.parse('2026-10-19T00:00:00Z'))).toBe(0)
    expect(totalAt(curve, Date.parse('2026-10-20T00:00:00Z'))).toBe(10.17)
    expect(totalAt(curve, Date.parse('2026-10-21T12:00:00Z'))).toBe(10.17)
    expect(totalAt(curve, Date.parse('2026-10-28T00:00:00Z'))).toBe(4.69)
    expect(totalAt([], Date.now())).toBe(0)
  })
})

describe('spread', () => {
  it('leaves labels that are far apart alone', () => {
    expect(spread([20, 100, 60], 15, 0, 200)).toEqual([20, 100, 60])
  })
  it('pushes close labels apart, keeping their order', () => {
    expect(spread([50, 52, 51], 15, 0, 200)).toEqual([50, 80, 65])
  })
  it('shifts the stack back up when it would run off the bottom', () => {
    expect(spread([190, 192], 15, 0, 200)).toEqual([185, 200])
  })
})
