import { describe, expect, it } from 'vitest'
import { AGENTS } from './choreography'
import { choreDelay, choresFor } from './chores'
import { ROOM_BOTTOM, ROOM_W, roomAt, roomOf } from './layout'

const HALF = 24 // half a robot sprite's width
const TALL = 48

describe('chores', () => {
  it('keep every robot inside its own room, clear of the walls', () => {
    for (const id of AGENTS) {
      const x0 = ROOM_W * roomOf(id)
      for (const c of choresFor(id)) {
        expect(roomAt(c.at)).toBe(id)
        expect(c.at.x - HALF).toBeGreaterThan(x0)
        expect(c.at.x + HALF).toBeLessThan(x0 + ROOM_W)
        expect(c.at.y - TALL).toBeGreaterThan(64) // below the back wall
        expect(c.at.y).toBeLessThan(ROOM_BOTTOM - 4)
      }
    }
  })

  it('gives the Health Coach its water and treadmill', () => {
    expect(choresFor('health_coach').map((c) => c.anim)).toEqual(['drink', 'run'])
  })

  it('waits between 7 and 16 seconds', () => {
    expect(choreDelay(() => 0)).toBe(7000)
    expect(choreDelay(() => 1)).toBe(16000)
  })
})
