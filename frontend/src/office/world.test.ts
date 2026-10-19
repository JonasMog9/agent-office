import { describe, expect, it } from 'vitest'
import { AGENTS } from './choreography'
import { EXIT, path, pathLength, placeAt, route, spotPoint, walkable, type Point } from './world'

const walk = (from: Point, to: Point) => [from, ...path(from, to)]

function legal(pts: Point[]): boolean {
  return pts.slice(1).every((p, i) => walkable(pts[i], p))
}

describe('the floor plan', () => {
  it('puts every desk and visiting spot inside its own room', () => {
    for (const a of AGENTS) {
      expect(placeAt(spotPoint({ desk: a }))).toBe(a)
      expect(placeAt(spotPoint({ visit: a }))).toBe(a)
    }
    expect(placeAt(EXIT)).toBe('uplink')
  })

  it('routes the Manager down its long hallway to the Health Lab without crossing walls', () => {
    const pts = walk(spotPoint({ desk: 'manager' }), spotPoint({ visit: 'health_coach' }))
    expect(legal(pts)).toBe(true)
    expect(pts.at(-1)).toEqual(spotPoint({ visit: 'health_coach' }))
    // A real trip: well over a thousand world units.
    expect(pathLength(pts[0], pts.slice(1))).toBeGreaterThan(1000)
  })

  it('goes from any room to any other, and out to the uplink and back', () => {
    for (const a of AGENTS)
      for (const b of AGENTS) {
        expect(legal(walk(spotPoint({ desk: a }), spotPoint({ visit: b })))).toBe(true)
      }
    expect(legal(walk(spotPoint({ visit: 'market_scout' }), EXIT))).toBe(true)
    expect(legal(walk(EXIT, spotPoint({ desk: 'manager' })))).toBe(true)
  })

  it('walks straight within a room', () => {
    expect(path(spotPoint({ desk: 'manager' }), spotPoint({ visit: 'manager' }))).toHaveLength(1)
  })

  it('finds the shortest route through the junction', () => {
    expect(route('health_coach:in', 'market_scout:in')).toEqual([
      'health_coach:in',
      'health_coach:door',
      'health_coach:corner',
      'junction',
      'market_scout:corner',
      'market_scout:door',
      'market_scout:in',
    ])
    expect(route('manager:in', 'exit')).toEqual(['manager:in', 'manager:door', 'junction', 'uplink:gate', 'exit'])
  })

  it('rejects a shortcut through a wall', () => {
    expect(walkable(spotPoint({ desk: 'health_coach' }), spotPoint({ desk: 'market_scout' }))).toBe(false)
  })
})
