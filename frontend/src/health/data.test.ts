import { describe, expect, it } from 'vitest'
import { clock, demoHealth, fitnessAgeLine, hm, pace } from './data'
import type { FitnessAge } from './data'

describe('formatting', () => {
  it('shows race times and paces the way runners read them', () => {
    expect(clock(1225)).toBe('20:25')
    expect(clock(5680)).toBe('1:34:40')
    expect(clock(59.6)).toBe('1:00')
    expect(clock(null)).toBe('–')
    expect(pace(318)).toBe('5:18/km')
  })
  it('shows sleep and time in hours and minutes', () => {
    expect(hm(468)).toBe('7 h 48 min')
    expect(hm(12)).toBe('0 h 12 min')
    expect(hm(null)).toBe('–')
  })
})

describe('fitness age', () => {
  const fa = (value: number | null, age: number | null): FitnessAge => ({
    value, age, label: null, vo2max: 52, median_at_age: 48, notes: [], source: '', history: [],
  })
  it('compares with my real age', () => {
    expect(fitnessAgeLine(fa(20, 24.8))).toBe('5 years younger than my 24')
    expect(fitnessAgeLine(fa(26, 24.8))).toBe('1 year older than my 24')
    expect(fitnessAgeLine(fa(25, 24.8))).toBe('Same as my age (25)')
    expect(fitnessAgeLine(fa(20, null))).toBe('From VO2max 52')
    expect(fitnessAgeLine(null)).toBe('Needs a VO2max')
  })
})

describe('the demo', () => {
  const d = demoHealth(new Date('2026-11-05T12:00:00'))
  it('has the real shape: 52 weeks, 12-week calendar, four races', () => {
    expect(d.weekly).toHaveLength(52)
    expect(d.calendar).toHaveLength(84)
    expect(d.predictions.current.map((c) => c.distance)).toEqual(['5K', '10K', 'half marathon', 'marathon'])
    expect(d.calendar.at(-1)!.day).toBe(d.today)
  })
  it('lists recent runs newest first, none in the future', () => {
    const days = d.runs.map((r) => r.day)
    expect([...days].sort().reverse()).toEqual(days)
    expect(days[0] <= d.today).toBe(true)
  })
})
