// The office floor plan: three rooms side by side, each with a doorway onto a shared hallway,
// and the exit ("to you") at the hallway's right end. Pure geometry, so paths are testable.

import type { AgentId, Spot } from './choreography'

export const WIDTH = 640
export const HEIGHT = 400
export const ROOM_W = WIDTH / 3
export const ROOM_BOTTOM = 276 // inner bottom wall of the rooms; the hallway is below it
export const HALL_Y = 335 // the line robots travel along in the hallway
export const EXIT = { x: 604, y: 312 }

export const ROOM_ORDER: AgentId[] = ['health_coach', 'manager', 'market_scout']

export interface Point {
  x: number
  y: number
}

export function roomOf(agent: AgentId): number {
  return ROOM_ORDER.indexOf(agent)
}

/** Centre x of a room (also the x of its doorway). */
export function roomX(agent: AgentId): number {
  return ROOM_W * roomOf(agent) + ROOM_W / 2
}

/** The room a point is in, or null when it's in the hallway. */
export function roomAt(p: Point): AgentId | null {
  if (p.y >= ROOM_BOTTOM) return null
  return ROOM_ORDER[Math.min(2, Math.max(0, Math.floor(p.x / ROOM_W)))]
}

export function spotPoint(s: Spot): Point {
  if ('door' in s) return EXIT
  if ('desk' in s) return { x: roomX(s.desk), y: 148 }
  return { x: roomX(s.visit) + 62, y: 262 } // in front of the visited agent's desk
}

/**
 * Waypoints from `from` to `to`: out through the current room's doorway, along the hallway,
 * and in through the target room's doorway. Never through a wall.
 */
export function path(from: Point, to: Point): Point[] {
  const a = roomAt(from)
  const b = roomAt(to)
  if (a !== null && a === b) return [to] // same room: walk straight there
  const pts: Point[] = []
  if (a !== null) {
    const dx = roomX(a)
    pts.push({ x: dx, y: Math.max(from.y, 240) }, { x: dx, y: HALL_Y })
  }
  if (b !== null) {
    const dx = roomX(b)
    pts.push({ x: dx, y: HALL_Y }, { x: dx, y: Math.max(to.y, 240) }, to)
  } else {
    pts.push({ x: to.x, y: HALL_Y }, to)
  }
  // Drop consecutive duplicates (e.g. leaving from right at the doorway).
  return pts.filter((p, i) => i === 0 || p.x !== pts[i - 1].x || p.y !== pts[i - 1].y)
}

export function pathLength(from: Point, pts: Point[]): number {
  let len = 0
  let cur = from
  for (const p of pts) {
    len += Math.hypot(p.x - cur.x, p.y - cur.y)
    cur = p
  }
  return len
}
