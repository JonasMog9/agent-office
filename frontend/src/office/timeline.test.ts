import { describe, expect, it } from 'vitest'
import { HURRY, Timeline } from './timeline'

/** A fake clock: schedule() queues callbacks, advance() runs the ones that are due. */
function clock() {
  let now = 0
  const due: { at: number; fn: () => void }[] = []
  return {
    schedule: (ms: number, fn: () => void) => due.push({ at: now + ms, fn }),
    advance(ms: number) {
      const until = now + ms
      for (;;) {
        due.sort((a, b) => a.at - b.at)
        if (!due.length || due[0].at > until) break
        const next = due.shift()!
        now = next.at
        next.fn()
      }
      now = until
    },
    get now() {
      return now
    },
  }
}

describe('the office timeline', () => {
  it("holds the Coach's answer until the Manager has arrived", () => {
    const c = clock()
    const t = new Timeline<string>(c.schedule)
    const started: [string, number][] = []
    const step = (name: string, ms: number) => ({
      item: name,
      play: () => {
        started.push([name, c.now])
        return ms
      },
    })
    // The events arrive almost at once, as they do from the backend…
    t.push(step('manager walks to coach (4 s)', 4000))
    t.push(step('coach thinks', 900))
    t.push(step('coach talks', 3000))
    t.push(step('manager walks to the uplink', 3000))
    c.advance(20_000)
    // …but each starts only when the one before it has finished.
    expect(started).toEqual([
      ['manager walks to coach (4 s)', 0],
      ['coach thinks', 4000],
      ['coach talks', 4900],
      ['manager walks to the uplink', 7900],
    ])
  })

  it('can slot a step in at the front, and reports what is waiting', () => {
    const c = clock()
    const t = new Timeline<string>(c.schedule)
    const log: string[] = []
    const step = (name: string) => ({ item: name, play: () => (log.push(name), 1000) })
    t.push(step('a'))
    t.push(step('c'))
    t.pushFront(step('b'))
    expect(t.items()).toEqual(['a', 'b', 'c'])
    expect(t.waiting()).toEqual(['b', 'c'])
    c.advance(5000)
    expect(log).toEqual(['a', 'b', 'c'])
    expect(t.busy).toBe(false)
  })

  it('hurries under a backlog', () => {
    const c = clock()
    const t = new Timeline<number>(c.schedule)
    const hurries: number[] = []
    for (let i = 0; i < 10; i++) t.push({ item: i, play: (_, h) => (hurries.push(h), 100) })
    c.advance(10_000)
    expect(hurries[0]).toBe(1) // the first started before the rest arrived
    expect(hurries).toContain(HURRY)
    expect(hurries.at(-1)).toBe(1)
  })
})
