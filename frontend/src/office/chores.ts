// What the robots get up to between requests: each has a few chores in its own room. A chore is
// a spot to fly to, an animation there and how long it lasts; then the robot flies home.
// Any real event interrupts a chore at once.

import type { AgentId } from './choreography'
import { ROOMS, type Point } from './world'

export type ChoreAnim = 'drink' | 'run' | 'look' | 'type' | 'stretch'

export interface Chore {
  name: string
  at: Point // where the robot stands (the point under its feet)
  anim: ChoreAnim
  ms: number
  label: string
  prop?: 'cup' | 'mug'
}

/** Chore spots are given relative to the room's top-left floor corner. */
const CHORES: Record<AgentId, (Omit<Chore, 'at'> & { dx: number; dy: number })[]> = {
  health_coach: [
    { name: 'water', dx: 100, dy: 130, anim: 'drink', ms: 3600, label: 'Hydrating', prop: 'cup' },
    { name: 'treadmill', dx: 466, dy: 300, anim: 'run', ms: 7000, label: 'Easy jog' },
    { name: 'mat', dx: 105, dy: 300, anim: 'stretch', ms: 4200, label: 'Stretching' },
  ],
  manager: [
    { name: 'status board', dx: 115, dy: 80, anim: 'look', ms: 3800, label: 'Checking on the team' },
    { name: 'coffee', dx: 455, dy: 120, anim: 'drink', ms: 3400, label: 'Coffee break', prop: 'mug' },
    { name: 'window', dx: 420, dy: 74, anim: 'look', ms: 3600, label: 'Watching the city' },
  ],
  market_scout: [
    { name: 'charts', dx: 185, dy: 72, anim: 'look', ms: 4200, label: 'Watching the charts' },
    { name: 'servers', dx: 112, dy: 150, anim: 'type', ms: 3800, label: 'Scanning new coins' },
    { name: 'signal', dx: 410, dy: 290, anim: 'look', ms: 3400, label: 'On patrol' },
  ],
}

export function choresFor(agent: AgentId): Chore[] {
  const r = ROOMS[agent]
  return CHORES[agent].map(({ dx, dy, ...c }) => ({ ...c, at: { x: r.x + dx, y: r.y + dy } }))
}

/** How long a robot waits at its desk before its next chore (ms). */
export function choreDelay(random: () => number = Math.random): number {
  return 7000 + random() * 9000
}
