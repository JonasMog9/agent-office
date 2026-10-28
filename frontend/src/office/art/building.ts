// The building: a night-time office floor seen from above, rooms lit like dioramas on a dark
// blueprint. Static art is painted once into textures; the moving parts (heart-rate trace,
// candlestick screens, server lights, the P/L board, the team status board, doors, hallway
// lights, the uplink) are small objects the scene animates.

import Phaser from 'phaser'
import type { AgentId } from '../choreography'
import { STRATEGY_COLOR, STRATEGY_KEYS } from '../../stats/data'
import {
  CORRIDORS,
  DOOR_W,
  EXIT,
  HALL_Y,
  RIM,
  ROOMS,
  UPLINK,
  WALL_FACE,
  WORLD_H,
  WORLD_W,
  northDoor,
  roomCenterX,
  spotPoint,
} from '../world'
import { FONT, glowing, hexNum, hgrad, image, lightTexture, paint, radial, rgba, rr, shadowed, vgrad, type Ctx } from './paint'

export interface RoomTheme {
  title: string
  floor: [string, string]
  wall: [string, string]
  neon: string
  light: string
}

export const THEMES: Record<AgentId, RoomTheme> = {
  health_coach: { title: 'HEALTH LAB', floor: ['#3b2c55', '#41315d'], wall: ['#62357f', '#3e2156'], neon: '#ff6fb1', light: '#ff9fd8' },
  manager: { title: 'COMMAND ROOM', floor: ['#22305e', '#263566'], wall: ['#25306a', '#151b44'], neon: '#5d8dff', light: '#9fc0ff' },
  market_scout: { title: 'TRADING DESK', floor: ['#2a2c37', '#2f323e'], wall: ['#2a2b36', '#15161d'], neon: '#fcc419', light: '#ffe08a' },
  paper_trader: { title: 'PAPER DESK', floor: ['#183a30', '#1c4236'], wall: ['#1c4a3b', '#0e2a21'], neon: '#3ddc97', light: '#a5f3cf' },
}

// ---- background -----------------------------------------------------------------------------

export function drawBackground(scene: Phaser.Scene): void {
  // One opaque backdrop: the night, a faint dot grid, and the building's footprint (a dark slab
  // under every room and hallway, with a soft shadow). One layer keeps the GPU's work low.
  const S = 0.6
  const M = 400 // margin around the world, so zooming out never shows an edge
  paint(
    scene,
    'backdrop',
    WORLD_W + 2 * M,
    WORLD_H + 2 * M,
    (ctx) => {
      ctx.fillStyle = '#070a14'
      ctx.fillRect(0, 0, WORLD_W + 2 * M, WORLD_H + 2 * M)
      ctx.translate(M, M)
      ctx.fillStyle = radial(ctx, WORLD_W / 2, WORLD_H / 2, WORLD_W * 0.75, [
        [0, 'rgba(36,54,128,.55)'],
        [0.55, 'rgba(20,30,80,.25)'],
        [1, 'rgba(7,10,20,0)'],
      ])
      ctx.fillRect(-M, -M, WORLD_W + 2 * M, WORLD_H + 2 * M)
      ctx.fillStyle = 'rgba(140,170,255,.13)'
      for (let y = -M + 20; y < WORLD_H + M; y += 40)
        for (let x = -M + 20; x < WORLD_W + M; x += 40) ctx.fillRect(x - 1, y - 1, 2, 2)
      const shapes: [number, number, number, number, number][] = []
      for (const a of Object.keys(ROOMS) as AgentId[]) {
        const r = ROOMS[a]
        shapes.push([r.x - RIM - 18, r.y - WALL_FACE - 18, r.w + 2 * RIM + 36, r.h + WALL_FACE + RIM + 36, 26])
      }
      for (const c of CORRIDORS) shapes.push([c.x - 16, c.y - 16, c.w + 32, c.h + 32, 18])
      shapes.push([UPLINK.x - UPLINK.r - 26, UPLINK.y - UPLINK.r - 26, 2 * UPLINK.r + 52, 2 * UPLINK.r + 52, UPLINK.r + 26])
      shadowed(ctx, 60, 24, 'rgba(0,0,0,.75)', () => {
        ctx.fillStyle = '#0d1222'
        for (const [x, y, w, h, r] of shapes) {
          rr(ctx, x, y, w, h, r)
          ctx.fill()
        }
      })
      ctx.strokeStyle = 'rgba(110,140,255,.16)'
      ctx.lineWidth = 2
      for (const [x, y, w, h, r] of shapes) {
        rr(ctx, x, y, w, h, r)
        ctx.stroke()
      }
      blueprint(ctx)
    },
    S,
  )
  scene.add.image(-M, -M, 'backdrop').setOrigin(0).setScale(1 / S).setDepth(-20)
}

/** Faint architect's notes in the empty corners: wing names, dimension lines, a compass. */
function blueprint(ctx: Ctx): void {
  ctx.save()
  ctx.strokeStyle = 'rgba(120,150,255,.22)'
  ctx.fillStyle = 'rgba(150,175,255,.40)'
  ctx.lineWidth = 1.5
  ctx.font = `700 22px ${FONT}`
  const label = (x: number, y: number, text: string, sub: string) => {
    ctx.fillStyle = 'rgba(150,175,255,.42)'
    ctx.font = `700 22px ${FONT}`
    ctx.fillText(text, x, y)
    ctx.fillStyle = 'rgba(150,175,255,.26)'
    ctx.font = `500 16px ${FONT}`
    ctx.fillText(sub, x, y + 24)
  }
  label(150, 790, 'WING A', 'Health · recovery, sleep, training')
  label(1690, 585, 'WING B', 'Markets · runners, rug tests, paper trades')
  label(380, 930, 'CORE', 'Operations · routes every message')
  // dimension lines along the main hallway
  ctx.setLineDash([6, 8])
  ctx.beginPath()
  ctx.moveTo(350, 600)
  ctx.lineTo(1650, 600)
  ctx.stroke()
  ctx.setLineDash([])
  for (const x of [350, 1650]) {
    ctx.beginPath()
    ctx.moveTo(x, 590)
    ctx.lineTo(x, 610)
    ctx.stroke()
  }
  ctx.fillStyle = 'rgba(150,175,255,.30)'
  ctx.font = `600 14px ${FONT}`
  ctx.textAlign = 'center'
  ctx.fillText('MAIN HALL · 130 m', 1000 - 330, 592)
  // compass
  const cx = 200
  const cy = 1080
  ctx.beginPath()
  ctx.arc(cx, cy, 46, 0, Math.PI * 2)
  ctx.stroke()
  ctx.beginPath()
  ctx.arc(cx, cy, 30, 0, Math.PI * 2)
  ctx.stroke()
  ctx.fillStyle = 'rgba(150,175,255,.35)'
  ctx.beginPath()
  ctx.moveTo(cx, cy - 56)
  ctx.lineTo(cx + 9, cy)
  ctx.lineTo(cx, cy + 10)
  ctx.lineTo(cx - 9, cy)
  ctx.closePath()
  ctx.fill()
  ctx.font = `700 16px ${FONT}`
  ctx.fillText('N', cx, cy - 64)
  ctx.textAlign = 'left'
  ctx.restore()
}

// ---- hallways -------------------------------------------------------------------------------

export function drawHallways(scene: Phaser.Scene): void {
  const g = scene.add.graphics().setDepth(-5)
  for (const c of CORRIDORS) {
    g.fillStyle(0x262c42, 1).fillRect(c.x, c.y, c.w, c.h)
  }
  // seams in the floor
  g.lineStyle(1, 0xffffff, 0.04)
  for (const c of CORRIDORS) {
    if (c.w > c.h) for (let x = c.x + 40; x < c.x + c.w; x += 40) g.lineBetween(x, c.y, x, c.y + c.h)
    else for (let y = c.y + 40; y < c.y + c.h; y += 40) g.lineBetween(c.x, y, c.x + c.w, y)
  }
  // a runner down the middle
  for (const c of CORRIDORS) {
    g.fillStyle(0x2f3756, 1)
    if (c.w > c.h) g.fillRect(c.x, c.y + c.h / 2 - 13, c.w, 26)
    else g.fillRect(c.x + c.w / 2 - 13, c.y, 26, c.h)
  }
  // glass walls: a soft line with a bright core, except where hallways meet
  const glass = scene.add.graphics().setDepth(-4)
  const rail = (x1: number, y1: number, x2: number, y2: number) => {
    glass.lineStyle(5, 0x6f96ff, 0.1).lineBetween(x1, y1, x2, y2)
    glass.lineStyle(1.5, 0xa9c2ff, 0.55).lineBetween(x1, y1, x2, y2)
  }
  const spine = CORRIDORS[0]
  const gaps = [roomCenterX('health_coach'), roomCenterX('market_scout'), 1000]
  const top = spine.y
  const bottom = spine.y + spine.h
  // spine, top edge: gaps for the corridors up to the Health Lab, the uplink and the Trading Desk
  let x = spine.x
  for (const gx of [...gaps].sort((a, b) => a - b)) {
    rail(x, top, gx - 40, top)
    x = gx + 40
  }
  rail(x, top, spine.x + spine.w, top)
  const paper = roomCenterX('paper_trader')
  rail(spine.x, bottom, 960, bottom)
  rail(1040, bottom, paper - 40, bottom)
  if (paper + 40 < spine.x + spine.w) rail(paper + 40, bottom, spine.x + spine.w, bottom)
  rail(spine.x, top, spine.x, bottom)
  rail(spine.x + spine.w, top, spine.x + spine.w, bottom)
  for (const c of CORRIDORS.slice(1)) {
    rail(c.x, c.y, c.x, c.y + c.h)
    rail(c.x + c.w, c.y, c.x + c.w, c.y + c.h)
  }

  // ceiling lights along the hallways
  lightTexture(scene, 'light-cool', 'rgba(150,180,255,.9)')
  const pools: [number, number][] = []
  for (let px = 430; px <= 1570; px += 190) pools.push([px, HALL_Y])
  pools.push([roomCenterX('health_coach'), 590], [roomCenterX('market_scout'), 590], [1000, 520], [1000, 770], [roomCenterX('paper_trader'), 770])
  for (const [px, py] of pools)
    scene.add.image(px, py, 'light-cool').setDisplaySize(170, 120).setAlpha(0.16).setBlendMode(Phaser.BlendModes.ADD).setDepth(-3)
}

/** Little lights running along the floor from each room towards the uplink. */
export function hallwayPulses(scene: Phaser.Scene): void {
  const tracks: [number, number][][] = [
    [[roomCenterX('health_coach'), 525], [roomCenterX('health_coach'), HALL_Y], [1000, HALL_Y], [1000, UPLINK.y + UPLINK.r]],
    [[roomCenterX('market_scout'), 525], [roomCenterX('market_scout'), HALL_Y], [1000, HALL_Y], [1000, UPLINK.y + UPLINK.r]],
    [[1000, ROOMS.manager.y - WALL_FACE], [1000, UPLINK.y + UPLINK.r]],
    [[roomCenterX('paper_trader'), ROOMS.paper_trader.y - WALL_FACE], [roomCenterX('paper_trader'), HALL_Y], [1000, HALL_Y], [1000, UPLINK.y + UPLINK.r]],
  ]
  paint(scene, 'pulse', 14, 14, (ctx) => {
    ctx.fillStyle = radial(ctx, 7, 7, 7, [[0, 'rgba(160,220,255,1)'], [0.4, 'rgba(90,170,255,.7)'], [1, 'rgba(0,0,0,0)']])
    ctx.fillRect(0, 0, 14, 14)
  })
  tracks.forEach((track, ti) => {
    for (let k = 0; k < 3; k++) {
      const dot = scene.add.image(track[0][0], track[0][1], 'pulse').setScale(0.6).setDepth(-2).setBlendMode(Phaser.BlendModes.ADD)
      const legs = track.slice(1).map(([tx, ty], i) => {
        const [fx, fy] = track[i]
        return { x: tx, y: ty, duration: Math.hypot(tx - fx, ty - fy) * 5, ease: 'Linear' }
      })
      scene.tweens.chain({ targets: dot, tweens: legs, loop: -1, delay: k * 1400 + ti * 450 })
    }
  })
}

// ---- rooms ----------------------------------------------------------------------------------

/** The room texture covers its floor, its back wall's face above it, and the rims around. */
function roomBox(a: AgentId) {
  const r = ROOMS[a]
  return { x: r.x - RIM, y: r.y - WALL_FACE, w: r.w + 2 * RIM, h: r.h + WALL_FACE + RIM, ox: RIM, oy: WALL_FACE }
}

function floorTiles(ctx: Ctx, w: number, h: number, t: RoomTheme, size: number): void {
  for (let y = 0; y < h; y += size)
    for (let x = 0; x < w; x += size) {
      ctx.fillStyle = (x / size + y / size) % 2 ? t.floor[0] : t.floor[1]
      ctx.fillRect(x, y, size, size)
    }
  ctx.strokeStyle = 'rgba(255,255,255,.035)'
  ctx.lineWidth = 1
  for (let y = 0; y <= h; y += size) {
    ctx.beginPath()
    ctx.moveTo(0, y)
    ctx.lineTo(w, y)
    ctx.stroke()
  }
  for (let x = 0; x <= w; x += size) {
    ctx.beginPath()
    ctx.moveTo(x, 0)
    ctx.lineTo(x, h)
    ctx.stroke()
  }
}

function lightPool(ctx: Ctx, x: number, y: number, r: number, color: string, a: number): void {
  ctx.save()
  ctx.globalCompositeOperation = 'lighter'
  ctx.fillStyle = radial(ctx, x, y, r, [[0, rgba(color, a)], [1, 'rgba(0,0,0,0)']])
  ctx.fillRect(x - r, y - r, 2 * r, 2 * r)
  ctx.restore()
}

function plant(ctx: Ctx, x: number, y: number, s = 1): void {
  shadowed(ctx, 8, 5, 'rgba(0,0,0,.45)', () => {
    rr(ctx, x - 13 * s, y - 6 * s, 26 * s, 22 * s, 6 * s)
    ctx.fillStyle = vgrad(ctx, y - 6 * s, y + 16 * s, [[0, '#e9e4dc'], [1, '#b9b2a6']])
    ctx.fill()
  })
  const leaves: [number, number, number, number][] = [
    [-12, -16, 13, -0.6], [12, -16, 13, 0.6], [0, -26, 14, 0], [-7, -6, 10, -1.1], [7, -6, 10, 1.1], [-3, -18, 11, -0.2], [5, -20, 11, 0.3],
  ]
  for (const [lx, ly, lr, rot] of leaves) {
    ctx.save()
    ctx.translate(x + lx * s, y + ly * s)
    ctx.rotate(rot)
    ctx.beginPath()
    ctx.ellipse(0, 0, lr * 0.55 * s, lr * s, 0, 0, Math.PI * 2)
    ctx.fillStyle = vgrad(ctx, -lr * s, lr * s, [[0, '#67d38b'], [1, '#2e8f55']])
    ctx.fill()
    ctx.restore()
  }
}

function wallScreen(ctx: Ctx, x: number, y: number, w: number, h: number, glow: string): void {
  shadowed(ctx, 10, 4, 'rgba(0,0,0,.6)', () => {
    rr(ctx, x - 3, y - 3, w + 6, h + 6, 5)
    ctx.fillStyle = '#0b0d14'
    ctx.fill()
  })
  rr(ctx, x, y, w, h, 3)
  ctx.fillStyle = vgrad(ctx, y, y + h, [[0, '#0a1020'], [1, '#111a32']])
  ctx.fill()
  glowing(ctx, 14, rgba(glow, 0.5), () => {
    rr(ctx, x, y, w, h, 3)
    ctx.strokeStyle = rgba(glow, 0.55)
    ctx.lineWidth = 1.2
    ctx.stroke()
  })
}

function heartIcon(ctx: Ctx, x: number, y: number, s: number, color: string): void {
  ctx.beginPath()
  ctx.moveTo(x, y + s * 0.9)
  ctx.bezierCurveTo(x - s * 1.3, y, x - s * 0.7, y - s * 0.9, x, y - s * 0.25)
  ctx.bezierCurveTo(x + s * 0.7, y - s * 0.9, x + s * 1.3, y, x, y + s * 0.9)
  ctx.fillStyle = color
  ctx.fill()
}

/** A name tab on top of each room's back wall. */
function sign(ctx: Ctx, x: number, y: number, title: string, sub: string, t: RoomTheme): void {
  ctx.font = `800 17px ${FONT}`
  const w = Math.max(ctx.measureText(title).width + 64, 150)
  shadowed(ctx, 10, 2, 'rgba(0,0,0,.5)', () => {
    rr(ctx, x, y, w, 46, 12)
    ctx.fillStyle = 'rgba(10,13,28,.94)'
    ctx.fill()
  })
  rr(ctx, x, y, w, 46, 12)
  ctx.strokeStyle = rgba(t.neon, 0.45)
  ctx.lineWidth = 1
  ctx.stroke()
  glowing(ctx, 8, t.neon, () => {
    ctx.beginPath()
    ctx.arc(x + 20, y + 23, 6, 0, Math.PI * 2)
    ctx.fillStyle = t.neon
    ctx.fill()
  })
  ctx.fillStyle = '#ffffff'
  ctx.textBaseline = 'alphabetic'
  ctx.fillText(title, x + 36, y + 23)
  ctx.font = `600 10.5px ${FONT}`
  ctx.fillStyle = rgba(t.light, 0.95)
  ctx.fillText(sub.toUpperCase(), x + 36, y + 37)
}

function paintRoom(ctx: Ctx, a: AgentId): void {
  const t = THEMES[a]
  const box = roomBox(a)
  const r = ROOMS[a]
  const { ox, oy } = box
  // floor
  ctx.save()
  ctx.translate(ox, oy)
  floorTiles(ctx, r.w, r.h, t, a === 'manager' ? 30 : a === 'paper_trader' ? 36 : 45)
  if (a === 'manager') {
    // a round rug under the command desk
    ctx.beginPath()
    ctx.ellipse(r.w / 2, 150, 190, 92, 0, 0, Math.PI * 2)
    ctx.fillStyle = '#2c3d7a'
    ctx.fill()
    ctx.lineWidth = 3
    ctx.strokeStyle = 'rgba(160,190,255,.25)'
    ctx.stroke()
    ctx.beginPath()
    ctx.ellipse(r.w / 2, 150, 170, 80, 0, 0, Math.PI * 2)
    ctx.strokeStyle = 'rgba(160,190,255,.12)'
    ctx.stroke()
  }
  if (a === 'paper_trader') {
    // a green banker's rug with a gold border under the desk
    rr(ctx, r.w / 2 - 170, 70, 340, 170, 18)
    ctx.fillStyle = '#21574a'
    ctx.fill()
    ctx.lineWidth = 3
    ctx.strokeStyle = 'rgba(255,212,59,.35)'
    ctx.stroke()
    rr(ctx, r.w / 2 - 154, 84, 308, 142, 12)
    ctx.strokeStyle = 'rgba(255,212,59,.15)'
    ctx.lineWidth = 1.5
    ctx.stroke()
  }
  if (a === 'health_coach') {
    ctx.beginPath()
    ctx.ellipse(r.w / 2, 205, 150, 70, 0, 0, Math.PI * 2)
    ctx.fillStyle = 'rgba(255,111,177,.14)'
    ctx.fill()
    ctx.strokeStyle = 'rgba(255,160,210,.25)'
    ctx.lineWidth = 2
    ctx.stroke()
  }
  if (a === 'market_scout') {
    // polished concrete: a faint reflection band
    ctx.fillStyle = hgrad(ctx, 0, r.w, [[0, 'rgba(255,255,255,0)'], [0.5, 'rgba(255,255,255,.035)'], [1, 'rgba(255,255,255,0)']])
    ctx.fillRect(0, 0, r.w, r.h)
  }
  // shadow cast by the back wall onto the floor
  ctx.fillStyle = vgrad(ctx, 0, 40, [[0, 'rgba(0,0,0,.45)'], [1, 'rgba(0,0,0,0)']])
  ctx.fillRect(0, 0, r.w, 40)
  ctx.restore()

  // the back wall's face
  ctx.fillStyle = vgrad(ctx, 0, oy, [[0, t.wall[0]], [1, t.wall[1]]])
  ctx.fillRect(ox, 0, r.w, oy)
  ctx.fillStyle = 'rgba(255,255,255,.18)'
  ctx.fillRect(ox, 0, r.w, 2)
  // neon strip along the foot of the wall
  glowing(ctx, 10, t.neon, () => {
    ctx.fillStyle = t.neon
    ctx.fillRect(ox, oy - 3, r.w, 2)
  })
  // side and front rims
  ctx.fillStyle = '#0a0d18'
  ctx.fillRect(0, 0, RIM, box.h)
  ctx.fillRect(box.w - RIM, 0, RIM, box.h)
  const doorX = ox + r.w / 2
  if (northDoor(a)) {
    ctx.fillRect(0, box.h - RIM, box.w, RIM)
    // the doorway through the back wall: hallway floor seen through it, with a frame
    ctx.fillStyle = '#262c42'
    ctx.fillRect(doorX - DOOR_W / 2, 0, DOOR_W, oy)
    ctx.fillStyle = '#2f3756'
    ctx.fillRect(doorX - 13, 0, 26, oy)
    ctx.fillStyle = '#0a0d18'
    ctx.fillRect(doorX - DOOR_W / 2 - 6, 0, 6, oy)
    ctx.fillRect(doorX + DOOR_W / 2, 0, 6, oy)
  } else {
    ctx.fillRect(0, box.h - RIM, doorX - DOOR_W / 2, RIM)
    ctx.fillRect(doorX + DOOR_W / 2, box.h - RIM, box.w - doorX - DOOR_W / 2, RIM)
    ctx.fillStyle = '#262c42'
    ctx.fillRect(doorX - DOOR_W / 2, box.h - RIM, DOOR_W, RIM)
  }
  ctx.fillStyle = 'rgba(160,180,255,.18)'
  ctx.fillRect(RIM - 1, 0, 1, box.h)
  ctx.fillRect(box.w - RIM, 0, 1, box.h)

  // furniture and decor
  ctx.save()
  ctx.translate(ox, oy)
  if (a === 'health_coach') healthLab(ctx, r.w, r.h, t)
  if (a === 'manager') commandRoom(ctx, r.w, r.h, t)
  if (a === 'market_scout') tradingDesk(ctx, r.w, r.h, t)
  if (a === 'paper_trader') paperDesk(ctx, r.w, r.h, t)
  ctx.restore()
}

function healthLab(ctx: Ctx, w: number, h: number, t: RoomTheme): void {
  wallScreen(ctx, 150, -56, 250, 44, t.neon) // the ECG trace is drawn live on top
  ctx.font = `700 9px ${FONT}`
  ctx.fillStyle = rgba(t.light, 0.9)
  ctx.fillText('HEART RATE', 158, -45)
  glowing(ctx, 6, t.neon, () => heartIcon(ctx, 470, -32, 9, t.neon))
  // water cooler (left)
  shadowed(ctx, 10, 6, 'rgba(0,0,0,.5)', () => {
    rr(ctx, 30, 40, 38, 62, 7)
    ctx.fillStyle = vgrad(ctx, 40, 102, [[0, '#f4f2f8'], [1, '#c9c3d6']])
    ctx.fill()
  })
  rr(ctx, 33, 6, 32, 38, 12)
  ctx.fillStyle = vgrad(ctx, 6, 44, [[0, 'rgba(150,215,255,.95)'], [1, 'rgba(70,150,230,.9)']])
  ctx.fill()
  ctx.fillStyle = 'rgba(255,255,255,.55)'
  ctx.fillRect(38, 10, 4, 26)
  rr(ctx, 41, 66, 16, 6, 2)
  ctx.fillStyle = '#5b6273'
  ctx.fill()
  // yoga mat and dumbbells (bottom left)
  shadowed(ctx, 6, 3, 'rgba(0,0,0,.35)', () => {
    rr(ctx, 30, 250, 150, 62, 8)
    ctx.fillStyle = hgrad(ctx, 30, 180, [[0, '#ff7cbc'], [1, '#c45ad8']])
    ctx.fill()
  })
  ctx.strokeStyle = 'rgba(255,255,255,.25)'
  ctx.lineWidth = 1
  for (let k = 1; k < 5; k++) {
    ctx.beginPath()
    ctx.moveTo(30 + k * 30, 252)
    ctx.lineTo(30 + k * 30, 310)
    ctx.stroke()
  }
  for (const [dx, dy] of [
    [40, 330],
    [80, 336],
  ]) {
    shadowed(ctx, 4, 2, 'rgba(0,0,0,.5)', () => {
      ctx.fillStyle = '#2b2f3b'
      rr(ctx, dx, dy - 6, 9, 14, 3)
      ctx.fill()
      rr(ctx, dx + 21, dy - 6, 9, 14, 3)
      ctx.fill()
      ctx.fillStyle = '#aab2c4'
      ctx.fillRect(dx + 8, dy - 1, 14, 4)
    })
  }
  // treadmill (right), running towards the viewer
  shadowed(ctx, 12, 8, 'rgba(0,0,0,.55)', () => {
    rr(ctx, 420, 190, 92, 150, 12)
    ctx.fillStyle = vgrad(ctx, 190, 340, [[0, '#4a4f60'], [1, '#2a2e3a']])
    ctx.fill()
  })
  rr(ctx, 434, 222, 64, 110, 6)
  ctx.fillStyle = '#16181f'
  ctx.fill()
  // its console
  rr(ctx, 418, 176, 96, 22, 8)
  ctx.fillStyle = vgrad(ctx, 176, 198, [[0, '#5d6377'], [1, '#3a3f4f']])
  ctx.fill()
  glowing(ctx, 6, t.neon, () => {
    rr(ctx, 450, 181, 32, 10, 3)
    ctx.fillStyle = rgba(t.neon, 0.9)
    ctx.fill()
  })
  plant(ctx, 515, 30, 1.1)
  plant(ctx, 515, 330, 0.9)
  lightPool(ctx, w / 2, 150, 260, t.light, 0.16)
  lightPool(ctx, 110, 260, 160, t.light, 0.1)
  lightPool(ctx, 465, 250, 160, t.light, 0.1)
  void h
}

function commandRoom(ctx: Ctx, w: number, h: number, t: RoomTheme): void {
  // the team board (the status lights are drawn live) and a window onto the city
  wallScreen(ctx, 24, -56, 240, 46, t.neon)
  ctx.font = `700 9px ${FONT}`
  ctx.fillStyle = rgba(t.light, 0.9)
  ctx.fillText('TEAM STATUS', 32, -44)
  // window with a skyline
  const wx = 336
  const wy = -58
  const ww = 180
  const wh = 50
  shadowed(ctx, 8, 3, 'rgba(0,0,0,.6)', () => {
    rr(ctx, wx - 4, wy - 4, ww + 8, wh + 8, 5)
    ctx.fillStyle = '#0b0d16'
    ctx.fill()
  })
  ctx.save()
  rr(ctx, wx, wy, ww, wh, 3)
  ctx.clip()
  ctx.fillStyle = vgrad(ctx, wy, wy + wh, [[0, '#0b1230'], [1, '#2c2a66']])
  ctx.fillRect(wx, wy, ww, wh)
  ctx.fillStyle = 'rgba(255,255,255,.8)'
  for (let k = 0; k < 18; k++) ctx.fillRect(wx + ((k * 47) % ww), wy + ((k * 13) % 22), 1, 1)
  ctx.beginPath()
  ctx.arc(wx + 150, wy + 12, 6, 0, Math.PI * 2)
  ctx.fillStyle = '#fff4c9'
  ctx.fill()
  let bx = wx
  let k = 0
  while (bx < wx + ww) {
    const bw = 12 + ((k * 7) % 14)
    const bh = 14 + ((k * 11) % 26)
    ctx.fillStyle = '#121633'
    ctx.fillRect(bx, wy + wh - bh, bw, bh)
    ctx.fillStyle = 'rgba(255,214,120,.75)'
    for (let yy = wy + wh - bh + 4; yy < wy + wh - 3; yy += 6)
      for (let xx = bx + 2; xx < bx + bw - 2; xx += 4) if ((xx + yy + k) % 3 === 0) ctx.fillRect(xx, yy, 1.5, 2)
    bx += bw + 2
    k++
  }
  ctx.restore()
  // sofa (bottom left), coffee machine (right)
  shadowed(ctx, 10, 6, 'rgba(0,0,0,.5)', () => {
    rr(ctx, 40, 220, 150, 52, 14)
    ctx.fillStyle = vgrad(ctx, 220, 272, [[0, '#4f5d99'], [1, '#34407a']])
    ctx.fill()
  })
  rr(ctx, 48, 228, 64, 34, 10)
  ctx.fillStyle = 'rgba(255,255,255,.07)'
  ctx.fill()
  rr(ctx, 118, 228, 64, 34, 10)
  ctx.fill()
  shadowed(ctx, 8, 5, 'rgba(0,0,0,.5)', () => {
    rr(ctx, 482, 30, 40, 54, 7)
    ctx.fillStyle = vgrad(ctx, 30, 84, [[0, '#3d4256'], [1, '#22252f']])
    ctx.fill()
  })
  glowing(ctx, 5, '#ffb35c', () => {
    ctx.fillStyle = '#ffb35c'
    ctx.fillRect(492, 40, 20, 4)
  })
  rr(ctx, 494, 60, 16, 14, 3)
  ctx.fillStyle = '#f3efe8'
  ctx.fill()
  plant(ctx, 26, 30, 0.9)
  plant(ctx, 520, 262, 1)
  lightPool(ctx, w / 2, 130, 260, t.light, 0.16)
  lightPool(ctx, 110, 230, 140, t.light, 0.08)
  void h
}

function tradingDesk(ctx: Ctx, w: number, h: number, t: RoomTheme): void {
  // three chart screens (the candles are drawn live) and the sign
  for (let s = 0; s < 3; s++) wallScreen(ctx, 100 + s * 150, -58, 132, 46, s === 1 ? '#51cf66' : '#ff6b6b')
  // server racks along the left wall
  for (let k = 0; k < 2; k++) {
    const ry = 18 + k * 92
    shadowed(ctx, 10, 6, 'rgba(0,0,0,.6)', () => {
      rr(ctx, 16, ry, 54, 84, 6)
      ctx.fillStyle = vgrad(ctx, ry, ry + 84, [[0, '#2c2f3a'], [1, '#17181e']])
      ctx.fill()
    })
    ctx.fillStyle = '#0d0e13'
    for (let s = 0; s < 6; s++) ctx.fillRect(22, ry + 8 + s * 12, 42, 8)
  }
  // the bat-signal, projected on the floor
  ctx.save()
  ctx.globalCompositeOperation = 'lighter'
  ctx.fillStyle = radial(ctx, 410, 270, 95, [[0, 'rgba(255,214,90,.30)'], [0.7, 'rgba(255,200,60,.12)'], [1, 'rgba(0,0,0,0)']])
  ctx.beginPath()
  ctx.ellipse(410, 270, 100, 52, 0, 0, Math.PI * 2)
  ctx.fill()
  ctx.restore()
  ctx.save()
  ctx.translate(410, 270)
  ctx.scale(5, 2.6)
  ctx.beginPath()
  const bat: [number, number][] = [
    [-7, 0], [-5, -2.6], [-3.2, -1.2], [-1.3, -3.2], [-0.6, -1.7], [0, -2.5], [0.6, -1.7], [1.3, -3.2],
    [3.2, -1.2], [5, -2.6], [7, 0], [4.6, 0.4], [3, 2.3], [1.6, 1], [0, 3], [-1.6, 1], [-3, 2.3], [-4.6, 0.4],
  ]
  bat.forEach(([bx, by], i) => (i ? ctx.lineTo(bx, by) : ctx.moveTo(bx, by)))
  ctx.closePath()
  ctx.fillStyle = 'rgba(16,17,22,.55)'
  ctx.fill()
  ctx.restore()
  // a giant gold coin on a pedestal, trophy-style
  shadowed(ctx, 10, 6, 'rgba(0,0,0,.6)', () => {
    rr(ctx, 470, 300, 50, 26, 5)
    ctx.fillStyle = vgrad(ctx, 300, 326, [[0, '#3a3c46'], [1, '#1d1e24']])
    ctx.fill()
  })
  glowing(ctx, 12, 'rgba(252,196,25,.6)', () => {
    ctx.beginPath()
    ctx.ellipse(495, 276, 22, 26, 0, 0, Math.PI * 2)
    ctx.fillStyle = vgrad(ctx, 250, 302, [[0, '#ffe58a'], [1, '#d99a00']])
    ctx.fill()
  })
  ctx.beginPath()
  ctx.ellipse(495, 276, 16, 20, 0, 0, Math.PI * 2)
  ctx.strokeStyle = 'rgba(140,90,0,.6)'
  ctx.lineWidth = 2
  ctx.stroke()
  ctx.font = `800 20px ${FONT}`
  ctx.fillStyle = 'rgba(120,75,0,.75)'
  ctx.textAlign = 'center'
  ctx.fillText('$', 495, 283)
  ctx.textAlign = 'left'
  lightPool(ctx, w / 2, 130, 260, t.light, 0.16)
  lightPool(ctx, 300, 40, 220, '#7cf3a0', 0.06)
  void h
}

function paperDesk(ctx: Ctx, w: number, h: number, t: RoomTheme): void {
  // the P/L board (one line per strategy, drawn live) and a neon sign
  wallScreen(ctx, 24, -56, 230, 46, t.neon)
  ctx.font = `700 9px ${FONT}`
  ctx.fillStyle = rgba(t.light, 0.9)
  ctx.fillText('P/L · 3 STRATEGIES', 32, -44)
  glowing(ctx, 12, t.neon, () => {
    ctx.font = `800 15px ${FONT}`
    ctx.fillStyle = '#c9ffe6'
    ctx.textAlign = 'center'
    ctx.fillText('PAPER MONEY ONLY', 420, -26)
    ctx.textAlign = 'left'
  })
  rr(ctx, 330, -46, 180, 30, 8)
  ctx.strokeStyle = rgba(t.neon, 0.6)
  ctx.lineWidth = 1.5
  ctx.stroke()
  // filing cabinet for the receipts (left)
  shadowed(ctx, 10, 6, 'rgba(0,0,0,.55)', () => {
    rr(ctx, 22, 26, 58, 96, 6)
    ctx.fillStyle = vgrad(ctx, 26, 122, [[0, '#7c8a86'], [1, '#4c5855']])
    ctx.fill()
  })
  for (let k = 0; k < 3; k++) {
    rr(ctx, 27, 32 + k * 30, 48, 26, 3)
    ctx.fillStyle = vgrad(ctx, 32 + k * 30, 58 + k * 30, [[0, '#8f9e9a'], [1, '#66746f']])
    ctx.fill()
    ctx.fillStyle = '#2b3331'
    ctx.fillRect(43, 42 + k * 30, 16, 3)
    ctx.fillStyle = '#f4f1e6'
    ctx.fillRect(46, 35 + k * 30, 10, 5)
  }
  // a stock-ticker machine under a glass dome, its paper tape spilling onto the floor (right)
  shadowed(ctx, 10, 6, 'rgba(0,0,0,.55)', () => {
    rr(ctx, 452, 74, 56, 16, 4)
    ctx.fillStyle = vgrad(ctx, 74, 90, [[0, '#6a4a2c'], [1, '#3e2a18']])
    ctx.fill()
  })
  rr(ctx, 462, 56, 36, 20, 4)
  ctx.fillStyle = vgrad(ctx, 56, 76, [[0, '#f0c75e'], [1, '#b7862a']])
  ctx.fill()
  ctx.beginPath()
  ctx.ellipse(480, 50, 24, 30, 0, Math.PI, 0)
  ctx.lineTo(504, 74)
  ctx.lineTo(456, 74)
  ctx.closePath()
  ctx.fillStyle = 'rgba(190,240,255,.16)'
  ctx.fill()
  ctx.strokeStyle = 'rgba(220,250,255,.45)'
  ctx.lineWidth = 1.2
  ctx.stroke()
  ctx.fillStyle = 'rgba(255,255,255,.5)'
  ctx.fillRect(464, 30, 3, 26)
  ctx.beginPath()
  ctx.moveTo(498, 84)
  ctx.bezierCurveTo(530, 98, 500, 118, 516, 134)
  ctx.bezierCurveTo(532, 150, 490, 160, 506, 176)
  ctx.lineWidth = 7
  ctx.strokeStyle = '#efe9d6'
  ctx.stroke()
  ctx.lineWidth = 1
  ctx.strokeStyle = 'rgba(60,60,60,.35)'
  ctx.setLineDash([2, 3])
  ctx.stroke()
  ctx.setLineDash([])
  // the safe (bottom left), for paper money
  shadowed(ctx, 10, 6, 'rgba(0,0,0,.6)', () => {
    rr(ctx, 26, 196, 78, 78, 8)
    ctx.fillStyle = vgrad(ctx, 196, 274, [[0, '#4b5654'], [1, '#262d2c']])
    ctx.fill()
  })
  rr(ctx, 33, 203, 64, 64, 5)
  ctx.strokeStyle = 'rgba(255,255,255,.14)'
  ctx.lineWidth = 1.5
  ctx.stroke()
  ctx.beginPath()
  ctx.arc(65, 235, 14, 0, Math.PI * 2)
  ctx.fillStyle = vgrad(ctx, 221, 249, [[0, '#e9d58f'], [1, '#a98a32']])
  ctx.fill()
  ctx.beginPath()
  ctx.arc(65, 235, 5, 0, Math.PI * 2)
  ctx.fillStyle = '#3b3220'
  ctx.fill()
  for (let k = 0; k < 8; k++) {
    const a = (k / 8) * Math.PI * 2
    ctx.fillStyle = '#5c4a1e'
    ctx.fillRect(65 + Math.cos(a) * 10 - 0.75, 235 + Math.sin(a) * 10 - 0.75, 1.5, 1.5)
  }
  // a stack of paper on the floor beside it
  for (let k = 0; k < 4; k++) {
    rr(ctx, 116 + (k % 2) * 2, 250 - k * 5, 34, 22, 2)
    ctx.fillStyle = k % 2 ? '#e8e3d3' : '#f6f2e6'
    ctx.fill()
  }
  plant(ctx, 515, 262, 1)
  lightPool(ctx, w / 2, 140, 260, t.light, 0.14)
  lightPool(ctx, 480, 70, 120, '#ffd43b', 0.08)
  void h
}

// ---- desks: separate images, so a robot standing behind one is partly hidden by it --------------

function paintDesk(ctx: Ctx, a: AgentId): void {
  const t = THEMES[a]
  const dark = a === 'market_scout'
  const wood = a === 'paper_trader' // a banker's desk
  const top: [number, string][] = dark ? [[0, '#5a5e6e'], [1, '#3d404d']] : wood ? [[0, '#a8774a'], [1, '#7d532f']] : [[0, '#f2f4fa'], [1, '#cfd5e3']]
  const face: [number, string][] = dark ? [[0, '#33363f'], [1, '#202229']] : wood ? [[0, '#6a4427'], [1, '#4d2f1a']] : [[0, '#b9c0d2'], [1, '#8d95ab']]
  // top
  shadowed(ctx, 14, 8, 'rgba(0,0,0,.55)', () => {
    rr(ctx, 6, 6, 168, 30, 10)
    ctx.fillStyle = vgrad(ctx, 6, 36, top)
    ctx.fill()
  })
  // front face
  rr(ctx, 10, 30, 160, 28, 8)
  ctx.fillStyle = vgrad(ctx, 30, 58, face)
  ctx.fill()
  glowing(ctx, 8, t.neon, () => {
    ctx.fillStyle = t.neon
    ctx.fillRect(22, 44, 136, 2)
  })
  // a keyboard on top
  rr(ctx, 64, 14, 52, 12, 3)
  ctx.fillStyle = dark ? '#16171c' : wood ? '#2f6b4f' : '#9aa3b8'
  ctx.fill()
  if (wood) {
    // a green banker's lamp
    rr(ctx, 136, 10, 26, 9, 4)
    ctx.fillStyle = '#1f8a5c'
    ctx.fill()
    ctx.fillStyle = '#d9b44a'
    ctx.fillRect(147, 18, 3, 8)
  }
}

function paintHolo(ctx: Ctx, a: AgentId): void {
  const t = THEMES[a]
  rr(ctx, 2, 2, 86, 40, 6)
  ctx.fillStyle = vgrad(ctx, 2, 42, [[0, rgba(t.light, 0.32)], [1, rgba(t.neon, 0.12)]])
  ctx.fill()
  rr(ctx, 2, 2, 86, 40, 6)
  ctx.strokeStyle = rgba(t.light, 0.8)
  ctx.lineWidth = 1.2
  ctx.stroke()
  ctx.fillStyle = rgba(t.light, 0.7)
  for (let k = 0; k < 4; k++) ctx.fillRect(10, 10 + k * 7, 30 + ((k * 23) % 40), 2)
}

export interface Desk {
  holo: Phaser.GameObjects.Image
  lines: Phaser.GameObjects.Graphics
  frame?: number
}

const SUBTITLE: Record<AgentId, string> = {
  health_coach: 'Health Coach',
  manager: 'Manager',
  market_scout: 'Market Scout',
  paper_trader: 'Paper Trader',
}

export function drawRooms(scene: Phaser.Scene): Record<AgentId, Desk> {
  const desks = {} as Record<AgentId, Desk>
  for (const a of Object.keys(ROOMS) as AgentId[]) {
    const box = roomBox(a)
    // the name tab, sitting on the wall's top edge
    paint(scene, `tab-${a}`, 240, 52, (ctx) => sign(ctx, 2, 2, THEMES[a].title, SUBTITLE[a], THEMES[a]))
    image(scene, box.x + 14, box.y - 44, `tab-${a}`).setOrigin(0).setDepth(-0.5)
    paint(scene, `room-${a}`, box.w, box.h, (ctx) => paintRoom(ctx, a))
    image(scene, box.x, box.y, `room-${a}`).setOrigin(0).setDepth(-1)
    const at = spotPoint({ desk: a })
    paint(scene, `desk-${a}`, 180, 64, (ctx) => paintDesk(ctx, a))
    image(scene, at.x, at.y + 4, `desk-${a}`).setOrigin(0.5, 0.25).setDepth(at.y + 40)
    paint(scene, `holo-${a}`, 90, 44, (ctx) => paintHolo(ctx, a))
    const holo = image(scene, at.x, at.y - 34, `holo-${a}`).setDepth(at.y + 41).setAlpha(0.35)
    const lines = scene.add.graphics().setDepth(at.y + 42)
    desks[a] = { holo, lines }
  }
  return desks
}

// ---- doors ----------------------------------------------------------------------------------

export interface Door {
  x: number
  y: number
  left: Phaser.GameObjects.Rectangle
  right: Phaser.GameObjects.Rectangle
  open: number
}

export function drawDoors(scene: Phaser.Scene): Door[] {
  return (Object.keys(ROOMS) as AgentId[]).map((a) => {
    const r = ROOMS[a]
    const x = roomCenterX(a)
    const north = northDoor(a)
    const y = north ? r.y - 6 : r.y + r.h + RIM / 2
    const h = north ? 10 : RIM - 2
    const color = hexNum(THEMES[a].neon)
    const panel = (px: number, ox: number) =>
      scene.add
        .rectangle(px, y, DOOR_W / 2, h, 0x9fc0ff, 0.38)
        .setOrigin(ox, 0.5)
        .setStrokeStyle(1.5, color, 0.9)
        .setDepth(north ? r.y - 1 : r.y + r.h + RIM)
    return { x, y, left: panel(x - DOOR_W / 2, 0), right: panel(x + DOOR_W / 2, 1), open: 0 }
  })
}

// ---- the uplink: where answers leave for the owner's Telegram ----------------------------------

export interface Uplink {
  burst: () => void
}

export function drawUplink(scene: Phaser.Scene): Uplink {
  const R = UPLINK.r
  paint(scene, 'uplink', 2 * R + 20, 2 * R + 20, (ctx) => {
    const c = R + 10
    shadowed(ctx, 18, 8, 'rgba(0,0,0,.6)', () => {
      ctx.beginPath()
      ctx.arc(c, c, R, 0, Math.PI * 2)
      ctx.fillStyle = radial(ctx, c, c, R, [[0, '#1d2a55'], [1, '#0f1531']])
      ctx.fill()
    })
    for (const [rad, a] of [
      [R - 6, 0.35],
      [R - 30, 0.22],
      [64, 0.5],
    ] as [number, number][]) {
      glowing(ctx, 10, 'rgba(77,212,255,.6)', () => {
        ctx.beginPath()
        ctx.arc(c, c, rad, 0, Math.PI * 2)
        ctx.strokeStyle = `rgba(110,220,255,${a})`
        ctx.lineWidth = 2
        ctx.stroke()
      })
    }
    ctx.fillStyle = radial(ctx, c, c, 62, [[0, 'rgba(34,158,217,.65)'], [1, 'rgba(34,158,217,.05)']])
    ctx.beginPath()
    ctx.arc(c, c, 62, 0, Math.PI * 2)
    ctx.fill()
  })
  image(scene, UPLINK.x, UPLINK.y, 'uplink').setDepth(-1)
  // a dashed ring that turns
  paint(scene, 'uplink-ring', 2 * R, 2 * R, (ctx) => {
    ctx.setLineDash([14, 10])
    ctx.beginPath()
    ctx.arc(R, R, R - 18, 0, Math.PI * 2)
    ctx.strokeStyle = 'rgba(140,230,255,.55)'
    ctx.lineWidth = 2.5
    ctx.stroke()
  })
  const ring = image(scene, UPLINK.x, UPLINK.y, 'uplink-ring').setDepth(0).setBlendMode(Phaser.BlendModes.ADD)
  scene.tweens.add({ targets: ring, angle: 360, duration: 24000, repeat: -1 })
  // a hologram paper plane, the owner's Telegram
  paint(scene, 'plane', 60, 50, (ctx) => {
    glowing(ctx, 10, 'rgba(90,200,255,.9)', () => {
      ctx.beginPath()
      ctx.moveTo(4, 24)
      ctx.lineTo(56, 4)
      ctx.lineTo(44, 46)
      ctx.lineTo(28, 33)
      ctx.lineTo(22, 44)
      ctx.lineTo(21, 30)
      ctx.closePath()
      ctx.fillStyle = 'rgba(160,225,255,.92)'
      ctx.fill()
    })
    ctx.beginPath()
    ctx.moveTo(21, 30)
    ctx.lineTo(56, 4)
    ctx.lineTo(28, 33)
    ctx.strokeStyle = 'rgba(30,120,200,.8)'
    ctx.lineWidth = 1.5
    ctx.stroke()
  })
  const plane = image(scene, UPLINK.x, UPLINK.y - 92, 'plane').setDepth(EXIT.y - 1).setAlpha(0.9)
  scene.tweens.add({ targets: plane, y: UPLINK.y - 102, duration: 1800, yoyo: true, repeat: -1, ease: 'Sine.easeInOut' })
  lightTexture(scene, 'light-tg', 'rgba(34,158,217,1)')
  const glow = scene.add.image(UPLINK.x, UPLINK.y, 'light-tg').setDisplaySize(340, 340).setAlpha(0.22).setBlendMode(Phaser.BlendModes.ADD).setDepth(0)
  scene.tweens.add({ targets: glow, alpha: 0.34, duration: 1600, yoyo: true, repeat: -1 })
  paint(scene, 'uplink-sign', 220, 40, (ctx) => {
    shadowed(ctx, 8, 3, 'rgba(0,0,0,.5)', () => {
      rr(ctx, 2, 2, 216, 36, 18)
      ctx.fillStyle = 'rgba(8,12,28,.85)'
      ctx.fill()
    })
    rr(ctx, 2, 2, 216, 36, 18)
    ctx.strokeStyle = 'rgba(110,220,255,.5)'
    ctx.stroke()
    ctx.font = `800 15px ${FONT}`
    ctx.fillStyle = '#ffffff'
    ctx.textAlign = 'center'
    ctx.fillText('UPLINK  ·  TO YOU', 110, 25)
  })
  image(scene, UPLINK.x, UPLINK.y - R - 30, 'uplink-sign').setDepth(UPLINK.y + 300)
  // the beam when an answer goes out
  paint(scene, 'beam', 80, 400, (ctx) => {
    ctx.fillStyle = hgrad(ctx, 0, 80, [[0, 'rgba(90,200,255,0)'], [0.5, 'rgba(160,230,255,.9)'], [1, 'rgba(90,200,255,0)']])
    ctx.fillRect(0, 0, 80, 400)
    ctx.globalCompositeOperation = 'destination-in'
    ctx.fillStyle = vgrad(ctx, 0, 400, [[0, 'rgba(0,0,0,0)'], [0.6, 'rgba(0,0,0,1)'], [1, 'rgba(0,0,0,1)']])
    ctx.fillRect(0, 0, 80, 400)
  })
  const beam = image(scene, EXIT.x, EXIT.y - 30, 'beam').setOrigin(0.5, 1).setAlpha(0).setBlendMode(Phaser.BlendModes.ADD).setDepth(EXIT.y + 400)
  return {
    burst: () => {
      beam.setAlpha(0).setScale(0.3 / 2, 0.5)
      scene.tweens.add({ targets: beam, alpha: 0.9, scaleX: 1 / 2, scaleY: 1 / 2, duration: 260, yoyo: true, hold: 500 })
      scene.tweens.add({ targets: plane, y: UPLINK.y - 220, alpha: 0, duration: 700, ease: 'Cubic.easeIn', onComplete: () => plane.setY(UPLINK.y - 92).setAlpha(0.9) })
      const wave = scene.add.image(UPLINK.x, UPLINK.y, 'uplink-ring').setDepth(1).setBlendMode(Phaser.BlendModes.ADD).setScale(0.3)
      scene.tweens.add({ targets: wave, scale: 0.75, alpha: 0, duration: 900, onComplete: () => wave.destroy() })
    },
  }
}

// ---- live screens ---------------------------------------------------------------------------

/** The Health Lab's heart-rate trace, scrolling across its wall screen. */
export function ecg(scene: Phaser.Scene): (time: number) => void {
  const r = ROOMS.health_coach
  const x0 = r.x + 150 + 8
  const y0 = r.y - 56 + 26
  const w = 234
  const g = scene.add.graphics().setDepth(1)
  const beat = (u: number) => {
    const p = u % 1
    if (p < 0.38) return 0
    if (p < 0.42) return -3
    if (p < 0.45) return 13
    if (p < 0.48) return -20
    if (p < 0.51) return 6
    if (p < 0.62) return 0
    if (p < 0.7) return -4 * Math.sin(((p - 0.62) / 0.08) * Math.PI)
    return 0
  }
  let last = -1
  return (time) => {
    if (time - last < 33) return
    last = time
    g.clear()
    const pts: [number, number][] = []
    for (let i = 0; i <= 70; i++) {
      const x = (i / 70) * w
      pts.push([x0 + x, y0 + beat(x / 70 - time / 900)])
    }
    for (const [width, alpha] of [
      [5, 0.18],
      [1.6, 1],
    ]) {
      g.lineStyle(width, 0xff7cc2, alpha)
      g.beginPath()
      g.moveTo(pts[0][0], pts[0][1])
      for (const [px, py] of pts.slice(1)) g.lineTo(px, py)
      g.strokePath()
    }
  }
}

/** The Trading Desk's candlestick screens, a new candle every second. */
export function candles(scene: Phaser.Scene): void {
  const r = ROOMS.market_scout
  const g = scene.add.graphics().setDepth(1)
  const series = [0, 1, 2].map((s) => Array.from({ length: 15 }, (_, i) => Math.sin(i * 0.9 + s) * 8))
  const draw = () => {
    g.clear()
    series.forEach((vals, s) => {
      const sx = r.x + 100 + s * 150 + 6
      const mid = r.y - 58 + 24
      vals.forEach((v, i) => {
        const prev = i ? vals[i - 1] : v
        const up = v <= prev
        const top = Math.min(v, prev)
        const h = Math.max(3, Math.abs(v - prev))
        g.fillStyle(up ? 0x51cf66 : 0xff6b6b, 0.95)
        g.fillRect(sx + i * 8.2, mid + top - 2, 5, h + 2)
        g.fillRect(sx + i * 8.2 + 2, mid + top - 6, 1.2, h + 10)
      })
    })
  }
  draw()
  scene.time.addEvent({
    delay: 1000,
    loop: true,
    callback: () => {
      for (const vals of series) {
        vals.shift()
        const last = vals[vals.length - 1]
        vals.push(Math.max(-14, Math.min(14, last + (Math.random() - 0.48) * 9)))
      }
      draw()
    },
  })
}

/** Blinking lights on the Trading Desk's server racks. */
export function serverLights(scene: Phaser.Scene): void {
  const r = ROOMS.market_scout
  for (let k = 0; k < 2; k++)
    for (let s = 0; s < 6; s++) {
      const y = r.y + 18 + k * 92 + 12 + s * 12
      for (let i = 0; i < 3; i++) {
        const led = scene.add
          .rectangle(r.x + 30 + i * 9, y, 4, 2.5, [0x51cf66, 0xfcc419, 0x4dabf7][(s + i + k) % 3])
          .setDepth(2)
        scene.tweens.add({ targets: led, alpha: 0.15, duration: 300 + ((s * 7 + i * 13 + k * 5) % 9) * 140, yoyo: true, repeat: -1, delay: (s * 97 + i * 53) % 700 })
      }
    }
}

/** The ticker LED strip along the Trading Desk's wall. */
export function ticker(scene: Phaser.Scene): void {
  const r = ROOMS.market_scout
  const y = r.y - 6
  scene.add.rectangle(r.x + r.w / 2, y, r.w - 24, 9, 0x07080c).setDepth(1)
  const text = scene.add
    .text(r.x + r.w, y, '▲ SOL 3.2%    ▲ BTC 1.1%    ▼ ETH 0.4%    ▲ RUNNERS 0    ▲ RUG TESTS 7/7', {
      fontFamily: FONT,
      fontSize: '7.5px',
      color: '#fcc419',
      fontStyle: '700',
      resolution: 3,
    })
    .setOrigin(0, 0.5)
    .setDepth(2)
  const mask = scene.make.graphics({}, false).fillRect(r.x + 12, y - 5, r.w - 24, 10)
  text.setMask(mask.createGeometryMask())
  scene.tweens.add({ targets: text, x: r.x - text.width, duration: 16000, repeat: -1 })
}

export type BoardState = 'idle' | 'busy' | 'talk' | 'away'

/** The team status board in the Command Room: a light per agent. */
export function statusBoard(scene: Phaser.Scene): (states: Record<AgentId, BoardState>) => void {
  const r = ROOMS.manager
  const order: AgentId[] = ['health_coach', 'manager', 'market_scout', 'paper_trader']
  const short: Record<AgentId, string> = { health_coach: 'COACH', manager: 'MGR', market_scout: 'SCOUT', paper_trader: 'PAPER' }
  const colors: Record<BoardState, number> = { idle: 0x51cf66, busy: 0x4de1ff, talk: 0xffffff, away: 0xffc94d }
  const lights = order.map((a, i) => {
    const x = r.x + 44 + i * 52
    const y = r.y - 56 + 30
    const dot = scene.add.circle(x, y, 5, colors.idle).setDepth(2)
    const halo = scene.add.circle(x, y, 10, colors.idle, 0.25).setDepth(2).setBlendMode(Phaser.BlendModes.ADD)
    scene.add
      .text(x + 9, y, short[a], {
        fontFamily: FONT,
        fontSize: '7px',
        color: '#c9d6ff',
        fontStyle: '700',
        resolution: 3,
      })
      .setOrigin(0, 0.5)
      .setDepth(2)
    scene.tweens.add({ targets: halo, scale: 1.4, alpha: 0.05, duration: 1100, repeat: -1 })
    return { a, dot, halo }
  })
  return (states) => {
    for (const { a, dot, halo } of lights) {
      dot.setFillStyle(colors[states[a]])
      halo.setFillStyle(colors[states[a]], 0.25)
    }
  }
}

/** The Paper Desk's P/L board: one wandering line per strategy, in the stats page's colours. */
export function pnlBoard(scene: Phaser.Scene): void {
  const r = ROOMS.paper_trader
  const g = scene.add.graphics().setDepth(1)
  const x0 = r.x + 24 + 8
  const y0 = r.y - 56 + 30
  const N = 26
  const series = STRATEGY_KEYS.map((_, s) => Array.from({ length: N }, (_, i) => Math.sin(i * 0.35 + s * 2) * 5 - s * 2))
  const draw = () => {
    g.clear()
    g.lineStyle(1, 0xffffff, 0.12).lineBetween(x0, y0, x0 + 214, y0)
    series.forEach((vals, s) => {
      g.lineStyle(1.6, hexNum(STRATEGY_COLOR[STRATEGY_KEYS[s]]), 1)
      g.beginPath()
      vals.forEach((v, i) => {
        const x = x0 + (i / (N - 1)) * 214
        // steps, like the stats page's running totals
        if (i === 0) g.moveTo(x, y0 + v)
        else {
          g.lineTo(x, y0 + vals[i - 1])
          g.lineTo(x, y0 + v)
        }
      })
      g.strokePath()
    })
  }
  draw()
  scene.time.addEvent({
    delay: 1400,
    loop: true,
    callback: () => {
      series.forEach((vals, s) => {
        vals.shift()
        const last = vals[vals.length - 1]
        const jump = Math.random() < 0.35 ? (Math.random() - 0.5 - s * 0.05) * 9 : 0
        vals.push(Math.max(-11, Math.min(11, last + jump)))
      })
      draw()
    },
  })
}

/** The treadmill belt, which only rolls while someone's on it. */
export function treadmillBelt(scene: Phaser.Scene): (running: boolean, delta: number) => void {
  const r = ROOMS.health_coach
  const x = r.x + 434
  const y = r.y + 222
  const g = scene.add.graphics().setDepth(r.y + 223)
  let offset = 0
  const draw = () => {
    g.clear()
    g.fillStyle(0xffffff, 0.08)
    for (let k = 0; k < 8; k++) {
      const yy = y + ((k * 16 + offset) % 110)
      g.fillRect(x + 4, yy, 56, 2)
    }
  }
  draw()
  return (running, delta) => {
    if (!running) return
    offset = (offset + delta * 0.12) % 110
    draw()
  }
}

/** Status: the desk's hologram lights up while its robot works. */
export function holoLines(d: Desk, active: boolean, time: number): void {
  const frame = active ? Math.floor(time / 120) : -1
  if (d.frame === frame) return
  d.frame = frame
  d.holo.setAlpha(active ? 0.95 : 0.35)
  d.lines.clear()
  if (!active) return
  const x0 = d.holo.x - 38
  const y0 = d.holo.y - 14
  d.lines.fillStyle(0xffffff, 0.75)
  for (let k = 0; k < 4; k++) {
    const w = 18 + ((Math.floor(time / 120) * 13 + k * 29) % 52)
    d.lines.fillRect(x0, y0 + k * 7, w, 1.6)
  }
}
