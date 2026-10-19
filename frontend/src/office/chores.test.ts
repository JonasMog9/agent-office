import { describe, expect, it } from 'vitest'
import { AGENTS } from './choreography'
import { choreDelay, choresFor } from './chores'
import { ROOMS, placeAt, spotPoint } from './world'

const HALF = 30 // half a robot's width
const TALL = 100

describe('chores', () => {
  it('keep every robot inside its own room, clear of the walls', () => {
    for (const id of AGENTS) {
      const r = ROOMS[id]
      for (const c of choresFor(id)) {
        expect(placeAt(c.at)).toBe(id)
        expect(c.at.x - HALF).toBeGreaterThan(r.x)
        expect(c.at.x + HALF).toBeLessThan(r.x + r.w)
        expect(c.at.y - TALL).toBeGreaterThan(r.y - 70) // its head may overlap the back wall
        expect(c.at.y).toBeLessThan(r.y + r.h - 4)
      }
    }
  })

  it("don't stand on the desk or the visitor's spot", () => {
    for (const id of AGENTS)
      for (const c of choresFor(id)) {
        for (const s of [spotPoint({ desk: id }), spotPoint({ visit: id })])
          expect(Math.hypot(c.at.x - s.x, c.at.y - s.y)).toBeGreaterThan(60)
      }
  })

  it('give the Health Coach its water, treadmill and mat', () => {
    expect(choresFor('health_coach').map((c) => c.anim)).toEqual(['drink', 'run', 'stretch'])
  })

  it('waits between 7 and 16 seconds', () => {
    expect(choreDelay(() => 0)).toBe(7000)
    expect(choreDelay(() => 1)).toBe(16000)
  })
})
