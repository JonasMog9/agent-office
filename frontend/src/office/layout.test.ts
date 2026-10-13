import { describe, expect, it } from 'vitest'
import { HALL_Y, ROOM_BOTTOM, path, roomAt, roomX, spotPoint, type Point } from './layout'

// A segment is legal if it stays inside one room, or runs along the hallway, or passes through
// a doorway (vertical at a room's centre x).
function legal(a: Point, b: Point): boolean {
  if (roomAt(a) !== null && roomAt(a) === roomAt(b)) return true
  if (a.y >= ROOM_BOTTOM && b.y >= ROOM_BOTTOM) return true
  const doorway = ['health_coach', 'manager', 'market_scout'].some(
    (r) => a.x === roomX(r as never) && b.x === roomX(r as never),
  )
  return doorway
}

function walk(from: Point, to: Point): Point[] {
  return [from, ...path(from, to)]
}

describe('path', () => {
  it('goes from the Manager desk to the Coach through both doorways and the hallway', () => {
    const pts = walk(spotPoint({ desk: 'manager' }), spotPoint({ visit: 'health_coach' }))
    expect(pts.some((p) => p.y === HALL_Y)).toBe(true)
    expect(pts.at(-1)).toEqual(spotPoint({ visit: 'health_coach' }))
    pts.slice(1).forEach((p, i) => expect(legal(pts[i], p)).toBe(true))
  })

  it('walks out to the exit and back home without crossing walls', () => {
    const out = walk(spotPoint({ visit: 'health_coach' }), spotPoint({ door: true }))
    out.slice(1).forEach((p, i) => expect(legal(out[i], p)).toBe(true))
    const home = walk(spotPoint({ door: true }), spotPoint({ desk: 'manager' }))
    home.slice(1).forEach((p, i) => expect(legal(home[i], p)).toBe(true))
    expect(home[1].y).toBe(HALL_Y)
  })

  it('stays inside a room when the target is in the same room', () => {
    expect(path(spotPoint({ desk: 'manager' }), spotPoint({ visit: 'manager' }))).toHaveLength(1)
  })
})
