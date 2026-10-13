import { describe, expect, it } from 'vitest'
import { bubbleText, duration, toAction, type OfficeEvent } from './choreography'

const ev = (over: Partial<OfficeEvent>): OfficeEvent => ({
  id: 1, agent: 'manager', status: 'idle', target: null, text: '', ...over,
})

describe('toAction', () => {
  it('walks to the agent being asked, and to the door with the answer', () => {
    expect(toAction(ev({ status: 'walking', target: 'health_coach' }))).toEqual({
      kind: 'walk', agent: 'manager', to: { visit: 'health_coach' },
    })
    expect(toAction(ev({ status: 'walking', target: 'owner' }))).toEqual({
      kind: 'walk', agent: 'manager', to: { door: true },
    })
    expect(toAction(ev({ status: 'walking', target: null }))).toEqual({
      kind: 'walk', agent: 'manager', to: { desk: 'manager' },
    })
  })

  it('works on a tool, talks with the text, and goes idle', () => {
    expect(toAction(ev({ agent: 'health_coach', status: 'working', target: 'get_recovery', text: 'Checking recovery' })))
      .toEqual({ kind: 'work', agent: 'health_coach', label: 'Checking recovery' })
    expect(toAction(ev({ status: 'talking', target: 'owner', text: 'Hi' })))
      .toEqual({ kind: 'talk', agent: 'manager', text: 'Hi', to: 'owner' })
    expect(toAction(ev({ status: 'thinking' })).kind).toBe('think')
    expect(toAction(ev({})).kind).toBe('idle')
  })
})

describe('timing and bubbles', () => {
  it('holds long answers longer, within limits', () => {
    expect(duration({ kind: 'talk', agent: 'manager', text: 'ok', to: null })).toBe(2500)
    expect(duration({ kind: 'talk', agent: 'manager', text: 'x'.repeat(1000), to: null })).toBe(8000)
  })

  it('cleans markdown and shortens bubble text', () => {
    expect(bubbleText('**Recovery:**  77\n green')).toBe('Recovery: 77 green')
    const long = bubbleText('word '.repeat(60))
    expect(long.length).toBeLessThanOrEqual(140)
    expect(long.endsWith('…')).toBe(true)
  })
})
