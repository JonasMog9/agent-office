// The office floor plan, in world units. Three rooms far apart, joined by long hallways:
//
//        ┌─ Health Lab ─┐          (uplink)          ┌─ Trading Desk ─┐
//        └──────┬───────┘              │             └───────┬────────┘
//               │                      │                     │
//               └──────────────────────┼─────────────────────┘   ← the main hallway
//                                      │
//                              ┌─ Command Room ─┐
//
// Robots move along a small graph of waypoints (doors, corners, junctions), so a route never
// cuts through a wall. Pure geometry, so routes are testable without a canvas.

import type { AgentId, Spot } from './choreography'

export const WORLD_W = 2000
export const WORLD_H = 1250

export interface Point {
  x: number
  y: number
}

export interface Rect {
  x: number
  y: number
  w: number
  h: number
}

/** Each room's floor. Its back wall rises WALL_FACE above the floor's top edge. */
export const ROOMS: Record<AgentId, Rect> = {
  health_coach: { x: 120, y: 150, w: 540, h: 360 },
  market_scout: { x: 1340, y: 150, w: 540, h: 360 },
  manager: { x: 730, y: 880, w: 540, h: 300 },
}
export const WALL_FACE = 64
export const RIM = 14 // the thickness of the side and front walls, seen from above
export const DOOR_W = 84

export const HALL_Y = 680 // the main hallway's centre line
export const HALL_HALF = 40
export const UPLINK = { x: 1000, y: 300, r: 130 }
export const EXIT: Point = { x: 1000, y: 385 } // where answers leave for the owner's Telegram

export const roomCenterX = (a: AgentId): number => ROOMS[a].x + ROOMS[a].w / 2

/** The hallway floor, as rectangles: the spine plus a corridor up or down to each room. */
export const CORRIDORS: Rect[] = [
  { x: 350, y: HALL_Y - HALL_HALF, w: 1300, h: 2 * HALL_HALF },
  { x: roomCenterX('health_coach') - HALL_HALF, y: 510, w: 2 * HALL_HALF, h: HALL_Y - 510 },
  { x: roomCenterX('market_scout') - HALL_HALF, y: 510, w: 2 * HALL_HALF, h: HALL_Y - 510 },
  {
    x: 1000 - HALL_HALF,
    y: HALL_Y,
    w: 2 * HALL_HALF,
    h: ROOMS.manager.y - WALL_FACE - HALL_Y,
  },
  { x: 1000 - HALL_HALF, y: UPLINK.y + UPLINK.r - 10, w: 2 * HALL_HALF, h: HALL_Y - UPLINK.y - UPLINK.r + 10 },
]

// ---- the waypoint graph -------------------------------------------------------------------

const H = roomCenterX('health_coach')
const S = roomCenterX('market_scout')
const M = roomCenterX('manager')

export const NODES: Record<string, Point> = {
  'health_coach:in': { x: H, y: ROOMS.health_coach.y + ROOMS.health_coach.h - 40 },
  'health_coach:door': { x: H, y: 530 },
  'health_coach:corner': { x: H, y: HALL_Y },
  junction: { x: M, y: HALL_Y },
  'market_scout:corner': { x: S, y: HALL_Y },
  'market_scout:door': { x: S, y: 530 },
  'market_scout:in': { x: S, y: ROOMS.market_scout.y + ROOMS.market_scout.h - 40 },
  'manager:door': { x: M, y: ROOMS.manager.y - WALL_FACE / 2 },
  'manager:in': { x: M, y: ROOMS.manager.y + 50 },
  'uplink:gate': { x: M, y: UPLINK.y + UPLINK.r + 10 },
  exit: EXIT,
}

const EDGES: [string, string][] = [
  ['health_coach:in', 'health_coach:door'],
  ['health_coach:door', 'health_coach:corner'],
  ['health_coach:corner', 'junction'],
  ['junction', 'market_scout:corner'],
  ['market_scout:corner', 'market_scout:door'],
  ['market_scout:door', 'market_scout:in'],
  ['junction', 'manager:door'],
  ['manager:door', 'manager:in'],
  ['junction', 'uplink:gate'],
  ['uplink:gate', 'exit'],
]

const dist = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y)

const NEIGHBOURS: Record<string, string[]> = {}
for (const [a, b] of EDGES) {
  ;(NEIGHBOURS[a] ??= []).push(b)
  ;(NEIGHBOURS[b] ??= []).push(a)
}

/** Shortest route between two graph nodes (Dijkstra over a dozen nodes). */
export function route(from: string, to: string): string[] {
  const best: Record<string, number> = { [from]: 0 }
  const prev: Record<string, string> = {}
  const open = new Set([from])
  while (open.size) {
    let cur = ''
    for (const n of open) if (!cur || best[n] < best[cur]) cur = n
    open.delete(cur)
    if (cur === to) break
    for (const n of NEIGHBOURS[cur] ?? []) {
      const d = best[cur] + dist(NODES[cur], NODES[n])
      if (best[n] === undefined || d < best[n]) {
        best[n] = d
        prev[n] = cur
        open.add(n)
      }
    }
  }
  const out = [to]
  while (out[0] !== from) {
    const p = prev[out[0]]
    if (p === undefined) return [] // unreachable (never, on this plan)
    out.unshift(p)
  }
  return out
}

// ---- places ---------------------------------------------------------------------------------

export function inRect(p: Point, r: Rect, pad = 0): boolean {
  return p.x >= r.x - pad && p.x <= r.x + r.w + pad && p.y >= r.y - pad && p.y <= r.y + r.h + pad
}

/** The room a point is in, 'uplink' on the uplink platform, or null in a hallway. */
export function placeAt(p: Point): AgentId | 'uplink' | null {
  for (const a of Object.keys(ROOMS) as AgentId[]) if (inRect(p, ROOMS[a])) return a
  if (dist(p, UPLINK) <= UPLINK.r) return 'uplink'
  return null
}

/** Where a robot stands (the point under its feet) for each kind of spot. */
export function spotPoint(s: Spot): Point {
  if ('door' in s) return EXIT
  if ('desk' in s) return { x: roomCenterX(s.desk), y: ROOMS[s.desk].y + 120 }
  const r = ROOMS[s.visit]
  return { x: roomCenterX(s.visit) + 110, y: r.y + 215 } // beside the visited agent's desk
}

function nearestNode(p: Point): string {
  let best = ''
  for (const id of Object.keys(NODES)) if (!best || dist(p, NODES[id]) < dist(p, NODES[best])) best = id
  return best
}

/** The node a point joins the graph at: its room's inside node, else the nearest node. */
function entry(p: Point): string {
  const place = placeAt(p)
  if (place === 'uplink') return dist(p, EXIT) < 30 ? 'exit' : 'uplink:gate'
  if (place) return `${place}:in`
  return nearestNode(p)
}

/**
 * Waypoints from `from` to `to`, ending at `to`. Within one room it's a straight line;
 * otherwise out of the room's door, along the hallways and in through the other door.
 */
export function path(from: Point, to: Point): Point[] {
  const a = placeAt(from)
  if (a !== null && a === placeAt(to)) return [to]
  const nodes = route(entry(from), entry(to)).map((id) => NODES[id])
  const pts = [...nodes, to]
  // Drop points we're already at, and consecutive duplicates.
  return pts.filter((p, i) => {
    const prevPt = i === 0 ? from : pts[i - 1]
    return dist(p, prevPt) > 0.5
  })
}

export function pathLength(from: Point, pts: Point[]): number {
  let len = 0
  let cur = from
  for (const p of pts) {
    len += dist(cur, p)
    cur = p
  }
  return len
}

/** True when a straight segment stays on walkable floor (a room, a corridor or the uplink). */
export function walkable(a: Point, b: Point, step = 10): boolean {
  const n = Math.max(1, Math.ceil(dist(a, b) / step))
  for (let i = 0; i <= n; i++) {
    const p = { x: a.x + ((b.x - a.x) * i) / n, y: a.y + ((b.y - a.y) * i) / n }
    const onFloor =
      placeAt(p) !== null ||
      CORRIDORS.some((c) => inRect(p, c, 1)) ||
      // the doorways through each room's wall
      (Object.keys(ROOMS) as AgentId[]).some((r) => doorway(r, p))
    if (!onFloor) return false
  }
  return true
}

function doorway(r: AgentId, p: Point): boolean {
  const room = ROOMS[r]
  const cx = roomCenterX(r)
  if (Math.abs(p.x - cx) > DOOR_W / 2) return false
  return r === 'manager'
    ? p.y >= room.y - WALL_FACE - 1 && p.y <= room.y + 1
    : p.y >= room.y + room.h - 1 && p.y <= room.y + room.h + RIM + 30
}
