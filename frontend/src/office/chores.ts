// What the robots get up to between requests: each has a few chores in its own room. A chore is
// a spot to fly to, a little animation there and how long it lasts; then the robot flies home.
// Any real event interrupts a chore at once.

import type { AgentId } from './choreography'
import { ROOM_W, roomOf, type Point } from './layout'

export type ChoreAnim = 'drink' | 'run' | 'look' | 'type'

export interface Chore {
  name: string
  at: Point // where the robot stands (bottom-centre of the sprite)
  anim: ChoreAnim
  ms: number
  label: string
}

/** Chore spots are given relative to the room's left wall and placed by `choresFor`. */
const CHORES: Record<AgentId, (Omit<Chore, 'at'> & { dx: number; y: number })[]> = {
  health_coach: [
    { name: 'water', dx: 180, y: 128, anim: 'drink', ms: 3200, label: 'Hydrating' },
    { name: 'treadmill', dx: 46, y: 248, anim: 'run', ms: 6000, label: 'Easy jog' },
  ],
  manager: [
    { name: 'status board', dx: 56, y: 118, anim: 'look', ms: 3500, label: 'Checking on the team' },
    { name: 'antenna', dx: 176, y: 140, anim: 'look', ms: 3000, label: 'Listening for messages' },
  ],
  market_scout: [
    { name: 'charts', dx: 60, y: 124, anim: 'look', ms: 4000, label: 'Watching the charts' },
    { name: 'laptop', dx: 100, y: 256, anim: 'type', ms: 3500, label: 'Scanning tokens' },
  ],
}

export function choresFor(agent: AgentId): Chore[] {
  const x0 = ROOM_W * roomOf(agent)
  return CHORES[agent].map(({ dx, y, ...c }) => ({ ...c, at: { x: x0 + dx, y } }))
}

/** How long a robot waits at its desk before its next chore (ms). */
export function choreDelay(random: () => number = Math.random): number {
  return 7000 + random() * 9000
}
