// The robots: glossy hover-bots built from painted parts (shell, face screen, glowing eyes,
// arms, jet, accessories), animated by moving those parts. Each agent has its own look:
//
//   Health Coach   pink and purple, a sweatband, a heart on its chest
//   Manager        blue, a headset with a mic and a gold tie
//   Market Scout   a dark cowl with pointed ears, a cape, a yellow belt and bat emblem

import Phaser from 'phaser'
import type { AgentId } from '../choreography'
import type { Point } from '../world'
import { glowing, hgrad, paint, radial, rgba, rr, shadowed, vgrad, type Ctx } from './paint'

const R = 3 // robot textures are painted at 3× for close-ups

export interface Look {
  body: string
  dark: string
  accent: string // antenna light, emblem glow
  eye: string
  shell: [string, string]
}

export const LOOKS: Record<AgentId, Look> = {
  health_coach: { body: '#ff6fb1', dark: '#8f3ad6', accent: '#ffd1ec', eye: '#ff9fdc', shell: ['#fbf8ff', '#d3c8e6'] },
  manager: { body: '#5d8dff', dark: '#2a3fc0', accent: '#ffd43b', eye: '#7df4ff', shell: ['#f7f9ff', '#c4ccde'] },
  market_scout: { body: '#3b3e4a', dark: '#15161b', accent: '#fcc419', eye: '#ffffff', shell: ['#33363f', '#121318'] },
}

// ---- painting the parts -------------------------------------------------------------------

function heart(ctx: Ctx, x: number, y: number, s: number, color: string): void {
  ctx.beginPath()
  ctx.moveTo(x, y + s * 0.9)
  ctx.bezierCurveTo(x - s * 1.3, y, x - s * 0.7, y - s * 0.9, x, y - s * 0.25)
  ctx.bezierCurveTo(x + s * 0.7, y - s * 0.9, x + s * 1.3, y, x, y + s * 0.9)
  ctx.fillStyle = color
  ctx.fill()
}

const BAT: [number, number][] = [
  [-7, 0], [-5, -2.6], [-3.2, -1.2], [-1.3, -3.2], [-0.6, -1.7], [0, -2.5], [0.6, -1.7], [1.3, -3.2],
  [3.2, -1.2], [5, -2.6], [7, 0], [4.6, 0.4], [3, 2.3], [1.6, 1], [0, 3], [-1.6, 1], [-3, 2.3], [-4.6, 0.4],
]

function bat(ctx: Ctx, x: number, y: number, s: number, color: string): void {
  ctx.beginPath()
  BAT.forEach(([bx, by], i) => (i ? ctx.lineTo(x + bx * s, y + by * s) : ctx.moveTo(x + bx * s, y + by * s)))
  ctx.closePath()
  ctx.fillStyle = color
  ctx.fill()
}

function paintBody(ctx: Ctx, id: AgentId, l: Look): void {
  shadowed(ctx, 6, 3, 'rgba(0,0,0,.45)', () => {
    rr(ctx, 5, 3, 46, 34, 15)
    ctx.fillStyle = vgrad(ctx, 3, 37, [[0, l.body], [1, l.dark]])
    ctx.fill()
  })
  rr(ctx, 5.5, 3.5, 45, 33, 14.5)
  ctx.strokeStyle = 'rgba(255,255,255,.22)'
  ctx.lineWidth = 1
  ctx.stroke()
  ctx.save()
  ctx.translate(17, 10)
  ctx.rotate(-0.35)
  ctx.fillStyle = 'rgba(255,255,255,.30)'
  ctx.beginPath()
  ctx.ellipse(0, 0, 9, 4, 0, 0, Math.PI * 2)
  ctx.fill()
  ctx.restore()
  // chest panel and emblem
  rr(ctx, 17, 13, 22, 15, 6)
  ctx.fillStyle = 'rgba(8,10,20,.35)'
  ctx.fill()
  if (id === 'health_coach') glowing(ctx, 5, l.body, () => heart(ctx, 28, 20.5, 5, '#fff0f8'))
  if (id === 'manager') {
    glowing(ctx, 4, l.accent, () => {
      ctx.fillStyle = l.accent
      ctx.beginPath()
      ctx.moveTo(25.5, 14.5)
      ctx.lineTo(30.5, 14.5)
      ctx.lineTo(29, 17.5)
      ctx.lineTo(27, 17.5)
      ctx.closePath()
      ctx.fill()
      ctx.beginPath()
      ctx.moveTo(27, 17.5)
      ctx.lineTo(29, 17.5)
      ctx.lineTo(30.5, 24.5)
      ctx.lineTo(28, 27)
      ctx.lineTo(25.5, 24.5)
      ctx.closePath()
      ctx.fill()
    })
  }
  if (id === 'market_scout') {
    glowing(ctx, 6, l.accent, () => {
      ctx.fillStyle = l.accent
      ctx.beginPath()
      ctx.ellipse(28, 20.5, 9, 5.5, 0, 0, Math.PI * 2)
      ctx.fill()
    })
    bat(ctx, 28, 20.5, 1.05, '#15161b')
    // utility belt
    rr(ctx, 6, 29, 44, 5, 2.5)
    ctx.fillStyle = vgrad(ctx, 29, 34, [[0, '#ffe066'], [1, '#e0a800']])
    ctx.fill()
    for (const bx of [13, 20, 36, 43]) {
      rr(ctx, bx - 2, 28.5, 4, 6, 1.2)
      ctx.fillStyle = '#c99700'
      ctx.fill()
    }
  }
  // thruster ring
  rr(ctx, 14, 35, 28, 6, 3)
  ctx.fillStyle = vgrad(ctx, 35, 41, [[0, '#a7aec0'], [1, '#575e70']])
  ctx.fill()
}

function paintHead(ctx: Ctx, id: AgentId, l: Look): void {
  const scout = id === 'market_scout'
  shadowed(ctx, 7, 3, 'rgba(0,0,0,.4)', () => {
    ctx.fillStyle = vgrad(ctx, 4, 56, [[0, l.shell[0]], [1, l.shell[1]]])
    if (scout) {
      // the cowl's pointed ears
      for (const [a, b, c] of [
        [10, 21, 14.5],
        [54, 43, 49.5],
      ]) {
        ctx.beginPath()
        ctx.moveTo(a, 18)
        ctx.lineTo(c, 1)
        ctx.lineTo(b, 14)
        ctx.closePath()
        ctx.fill()
      }
    }
    rr(ctx, 4, 12, 56, 42, 16)
    ctx.fill()
  })
  rr(ctx, 4.5, 12.5, 55, 41, 15.5)
  ctx.strokeStyle = scout ? 'rgba(255,255,255,.10)' : 'rgba(255,255,255,.7)'
  ctx.lineWidth = 1
  ctx.stroke()
  // glossy highlight
  ctx.save()
  ctx.translate(20, 19)
  ctx.rotate(-0.25)
  ctx.fillStyle = scout ? 'rgba(255,255,255,.10)' : 'rgba(255,255,255,.65)'
  ctx.beginPath()
  ctx.ellipse(0, 0, 11, 3.6, 0, 0, Math.PI * 2)
  ctx.fill()
  ctx.restore()
  if (id === 'health_coach') {
    // sweatband across the forehead
    rr(ctx, 4.5, 16, 55, 6, 3)
    ctx.fillStyle = hgrad(ctx, 4, 60, [[0, l.dark], [0.5, l.body], [1, l.dark]])
    ctx.fill()
    ctx.fillStyle = 'rgba(255,255,255,.55)'
    ctx.fillRect(8, 18.4, 48, 1.1)
  }
  if (id !== 'market_scout') {
    // ear pods (the Manager's are headset cups)
    for (const ex of [3.5, 60.5]) {
      ctx.beginPath()
      ctx.arc(ex, 34, id === 'manager' ? 7 : 5.5, 0, Math.PI * 2)
      ctx.fillStyle = id === 'manager' ? '#262c3d' : vgrad(ctx, 28, 40, [[0, l.body], [1, l.dark]])
      ctx.fill()
      if (id === 'manager') {
        ctx.beginPath()
        ctx.arc(ex, 34, 3.4, 0, Math.PI * 2)
        ctx.fillStyle = l.body
        ctx.fill()
      }
    }
  }
  if (id === 'manager') {
    // headband over the top, and a mic boom
    ctx.beginPath()
    ctx.arc(32, 36, 30, Math.PI * 1.08, Math.PI * 1.92)
    ctx.strokeStyle = '#262c3d'
    ctx.lineWidth = 3.4
    ctx.stroke()
    ctx.beginPath()
    ctx.moveTo(5, 39)
    ctx.quadraticCurveTo(6, 51, 19, 51)
    ctx.strokeStyle = '#262c3d'
    ctx.lineWidth = 2
    ctx.stroke()
    glowing(ctx, 4, l.eye, () => {
      ctx.beginPath()
      ctx.arc(20, 51, 2.4, 0, Math.PI * 2)
      ctx.fillStyle = l.eye
      ctx.fill()
    })
  }
  // the face screen
  const fy = scout ? 22 : 24
  const fh = scout ? 20 : 24
  rr(ctx, 10, fy, 44, fh, 10)
  ctx.fillStyle = vgrad(ctx, fy, fy + fh, [[0, '#070b18'], [1, '#1a2444']])
  ctx.fill()
  rr(ctx, 10, fy, 44, fh, 10)
  ctx.strokeStyle = 'rgba(120,160,255,.18)'
  ctx.stroke()
  ctx.fillStyle = 'rgba(255,255,255,.07)'
  ctx.beginPath()
  ctx.moveTo(14, fy + 2)
  ctx.lineTo(30, fy + 2)
  ctx.lineTo(22, fy + fh - 3)
  ctx.lineTo(13, fy + fh - 3)
  ctx.closePath()
  ctx.fill()
}

function paintEye(ctx: Ctx, id: AgentId, l: Look): void {
  glowing(ctx, 5, l.eye, () => {
    ctx.fillStyle = l.eye
    if (id === 'market_scout') {
      // narrow, slanted, menacing
      ctx.beginPath()
      ctx.moveTo(2, 6)
      ctx.lineTo(10, 3.5)
      ctx.lineTo(10, 8)
      ctx.lineTo(3, 9)
      ctx.closePath()
      ctx.fill()
    } else {
      rr(ctx, 2.5, 1.5, 7, 11, 3.5)
      ctx.fill()
    }
  })
}

function paintMouth(ctx: Ctx, l: Look): void {
  glowing(ctx, 3, l.eye, () => {
    rr(ctx, 2, 1.5, 14, 2.6, 1.3)
    ctx.fillStyle = l.eye
    ctx.fill()
  })
}

function paintArm(ctx: Ctx, l: Look): void {
  shadowed(ctx, 3, 1.5, 'rgba(0,0,0,.35)', () => {
    rr(ctx, 2, 1, 8, 20, 4)
    ctx.fillStyle = vgrad(ctx, 1, 21, [[0, l.body], [1, l.dark]])
    ctx.fill()
  })
  ctx.beginPath()
  ctx.arc(6, 21, 3.6, 0, Math.PI * 2)
  ctx.fillStyle = vgrad(ctx, 17, 25, [[0, '#e3e7f0'], [1, '#9aa2b5']])
  ctx.fill()
}

function paintAntenna(ctx: Ctx, l: Look): void {
  ctx.fillStyle = vgrad(ctx, 8, 22, [[0, '#c9cfdc'], [1, '#7c8497']])
  ctx.fillRect(5, 8, 2, 14)
  glowing(ctx, 7, l.accent, () => {
    ctx.beginPath()
    ctx.arc(6, 6, 4.2, 0, Math.PI * 2)
    ctx.fillStyle = l.accent
    ctx.fill()
  })
  ctx.beginPath()
  ctx.arc(4.8, 4.8, 1.3, 0, Math.PI * 2)
  ctx.fillStyle = 'rgba(255,255,255,.9)'
  ctx.fill()
}

function paintCape(ctx: Ctx): void {
  ctx.beginPath()
  ctx.moveTo(16, 2)
  ctx.lineTo(44, 2)
  ctx.quadraticCurveTo(54, 24, 58, 48)
  // scalloped hem
  ctx.quadraticCurveTo(51, 43, 44, 49)
  ctx.quadraticCurveTo(37, 43, 30, 50)
  ctx.quadraticCurveTo(23, 43, 16, 49)
  ctx.quadraticCurveTo(9, 43, 2, 48)
  ctx.quadraticCurveTo(6, 24, 16, 2)
  ctx.closePath()
  ctx.fillStyle = vgrad(ctx, 2, 50, [[0, '#2a2c35'], [1, '#0b0c10']])
  ctx.fill()
  ctx.strokeStyle = 'rgba(255,255,255,.08)'
  ctx.lineWidth = 1
  ctx.stroke()
}

function paintJet(ctx: Ctx, l: Look): void {
  ctx.fillStyle = radial(ctx, 20, 8, 20, [
    [0, 'rgba(255,255,255,.95)'],
    [0.25, rgba(l.eye, 0.85)],
    [1, 'rgba(0,0,0,0)'],
  ])
  ctx.beginPath()
  ctx.ellipse(20, 12, 14, 18, 0, 0, Math.PI * 2)
  ctx.fill()
}

function paintShadow(ctx: Ctx): void {
  ctx.save()
  ctx.scale(1, 0.3)
  ctx.fillStyle = radial(ctx, 34, 34, 32, [
    [0, 'rgba(0,0,0,.55)'],
    [0.6, 'rgba(0,0,0,.25)'],
    [1, 'rgba(0,0,0,0)'],
  ])
  ctx.fillRect(0, 0, 68, 68)
  ctx.restore()
}

function paintRing(ctx: Ctx): void {
  ctx.save()
  ctx.scale(1, 0.34)
  glowing(ctx, 6, '#ffffff', () => {
    ctx.beginPath()
    ctx.ellipse(44, 44, 34, 34, 0, 0, Math.PI * 2)
    ctx.strokeStyle = 'rgba(255,255,255,.95)'
    ctx.lineWidth = 3.2
    ctx.stroke()
  })
  ctx.restore()
}

export function makeRobotTextures(scene: Phaser.Scene, id: AgentId): void {
  const l = LOOKS[id]
  paint(scene, `${id}-body`, 56, 44, (c) => paintBody(c, id, l), R)
  paint(scene, `${id}-head`, 64, 56, (c) => paintHead(c, id, l), R)
  paint(scene, `${id}-eye`, 12, 14, (c) => paintEye(c, id, l), R)
  paint(scene, `${id}-mouth`, 18, 6, (c) => paintMouth(c, l), R)
  paint(scene, `${id}-arm`, 12, 26, (c) => paintArm(c, l), R)
  paint(scene, `${id}-antenna`, 12, 22, (c) => paintAntenna(c, l), R)
  paint(scene, `${id}-jet`, 40, 36, (c) => paintJet(c, l), R)
  if (id === 'market_scout') paint(scene, `${id}-cape`, 60, 52, paintCape, R)
  if (!scene.textures.exists('bot-shadow')) paint(scene, 'bot-shadow', 68, 22, paintShadow, R)
  if (!scene.textures.exists('bot-ring')) paint(scene, 'bot-ring', 88, 32, paintRing, R)
}

// ---- the animated robot -------------------------------------------------------------------

export type BotState = 'idle' | 'fly' | 'think' | 'work' | 'talk' | 'drink' | 'run' | 'look' | 'type' | 'stretch'

const HOVER = 12
const SCALE = 1.2 // robots read better a little larger than life at office zoom
const RING_TINT: Partial<Record<BotState, number>> = { think: 0xffc94d, work: 0x4de1ff, talk: 0xffffff, type: 0x4de1ff }

export class Bot {
  readonly root: Phaser.GameObjects.Container
  private rig: Phaser.GameObjects.Container
  private head: Phaser.GameObjects.Container
  private eyes: Phaser.GameObjects.Image[]
  private mouth: Phaser.GameObjects.Image
  private arms: Phaser.GameObjects.Image[]
  private jet: Phaser.GameObjects.Image
  private shadow: Phaser.GameObjects.Image
  private ring: Phaser.GameObjects.Image
  private cape?: Phaser.GameObjects.Image
  private antenna?: Phaser.GameObjects.Image
  private fx: (Phaser.Tweens.Tween | Phaser.Time.TimerEvent)[] = []
  private flight?: Phaser.Tweens.TweenChain
  private bob = 0
  state: BotState = 'idle'
  flying = false
  private scene: Phaser.Scene
  readonly id: AgentId

  constructor(scene: Phaser.Scene, id: AgentId, x: number, y: number) {
    this.scene = scene
    this.id = id
    makeRobotTextures(scene, id)
    const img = (k: string, px: number, py: number, ox = 0.5, oy = 0.5) =>
      scene.add.image(px, py, k).setScale(1 / R).setOrigin(ox, oy)
    this.shadow = img('bot-shadow', 0, 0).setAlpha(0.9)
    // a soft glow in the robot's colour on the floor beneath it, so even the dark Scout pops
    if (!scene.textures.exists(`${id}-under`))
      paint(scene, `${id}-under`, 120, 60, (c) => {
        c.save()
        c.scale(1, 0.5)
        c.fillStyle = radial(c, 60, 60, 60, [[0, rgba(id === 'market_scout' ? LOOKS[id].accent : LOOKS[id].body, 0.55)], [1, 'rgba(0,0,0,0)']])
        c.fillRect(0, 0, 120, 120)
        c.restore()
      }, 1)
    const under = scene.add.image(0, 2, `${id}-under`).setBlendMode(Phaser.BlendModes.ADD).setAlpha(0.8)
    this.ring = img('bot-ring', 0, 0).setAlpha(0).setBlendMode(Phaser.BlendModes.ADD)
    this.jet = img(`${id}-jet`, 0, -8, 0.5, 0.2).setBlendMode(Phaser.BlendModes.ADD).setAlpha(0.55)
    const parts: Phaser.GameObjects.GameObject[] = [this.jet]
    if (id === 'market_scout') {
      this.cape = img(`${id}-cape`, 0, -50, 0.5, 0)
      parts.push(this.cape)
    }
    this.arms = [img(`${id}-arm`, -24, -44, 0.5, 0.12), img(`${id}-arm`, 24, -44, 0.5, 0.12).setFlipX(true)]
    const body = img(`${id}-body`, 0, -31)
    this.eyes = [img(`${id}-eye`, -10, 1), img(`${id}-eye`, 10, 1).setFlipX(true)]
    this.mouth = img(`${id}-mouth`, 0, 11).setVisible(false)
    const headImg = img(`${id}-head`, 0, 0)
    const headParts: Phaser.GameObjects.GameObject[] = [headImg, ...this.eyes, this.mouth]
    if (id !== 'market_scout') {
      this.antenna = img(`${id}-antenna`, 0, -26, 0.5, 1)
      headParts.unshift(this.antenna)
    }
    this.head = scene.add.container(0, -74, headParts)
    parts.push(...this.arms, body, this.head)
    this.rig = scene.add.container(0, -HOVER, parts)
    this.root = scene.add.container(x, y, [under, this.shadow, this.ring, this.rig]).setScale(SCALE)
    this.setState('idle')
  }

  get x(): number {
    return this.root.x
  }

  get y(): number {
    return this.root.y
  }

  /** Top of the robot's head, for placing bubbles. */
  get top(): number {
    return this.root.y - 108 * SCALE
  }

  update(time: number): void {
    // a gentle hover, the shadow breathing with it
    const speed = this.flying ? 0.012 : 0.0035
    this.bob = Math.sin(time * speed) * (this.flying ? 2 : 3.2)
    this.rig.y = -HOVER + this.bob
    const s = 1 - this.bob * 0.02
    this.shadow.setScale(s / R, s / R)
    this.root.setDepth(this.root.y)
  }

  /** Eyes look along the direction of travel (or straight ahead for dx = 0). */
  look(dx: number, dy = 0): void {
    const ox = Math.sign(dx) * 3
    const oy = Math.sign(dy) * 1.5
    this.eyes[0].setPosition(-10 + ox, 1 + oy)
    this.eyes[1].setPosition(10 + ox, 1 + oy)
  }

  blink(): void {
    if (this.state === 'work' || this.state === 'type') return
    for (const e of this.eyes)
      this.scene.tweens.add({ targets: e, scaleY: 0.08 / R, duration: 70, yoyo: true, ease: 'Sine.easeInOut' })
  }

  private clearFx(): void {
    for (const f of this.fx) f.remove()
    this.fx = []
    this.arms[0].setRotation(0)
    this.arms[1].setRotation(0)
    this.head.setRotation(0).setY(-74)
    this.rig.setRotation(0)
    for (const e of this.eyes) e.setScale(1 / R)
    this.mouth.setVisible(false)
    this.jet.setScale(1 / R).setAlpha(0.55)
    this.antenna?.setTint(0xffffff)
    this.ring.setAlpha(0)
    this.look(0)
  }

  private loop(cfg: Phaser.Types.Tweens.TweenBuilderConfig): void {
    this.fx.push(this.scene.tweens.add({ yoyo: true, repeat: -1, ease: 'Sine.easeInOut', ...cfg }))
  }

  private every(ms: number, fn: (n: number) => void): void {
    let n = 0
    this.fx.push(this.scene.time.addEvent({ delay: ms, loop: true, callback: () => fn(n++) }))
  }

  setState(s: BotState): void {
    this.clearFx()
    this.state = s
    const [left, right] = this.arms
    const tint = RING_TINT[s]
    if (tint !== undefined) {
      this.ring.setTint(tint)
      this.loop({ targets: this.ring, alpha: { from: 0.35, to: 0.85 }, duration: 700 })
    }
    if (this.cape) this.loop({ targets: this.cape, scaleX: { from: 1 / R, to: 0.93 / R }, duration: 1300 })
    switch (s) {
      case 'idle':
        this.loop({ targets: left, rotation: 0.12, duration: 1600 })
        this.loop({ targets: right, rotation: -0.12, duration: 1600 })
        break
      case 'fly':
        this.jet.setAlpha(0.85).setScale(1.1 / R, 1.35 / R)
        left.setRotation(0.6)
        right.setRotation(-0.6)
        this.loop({ targets: this.jet, alpha: 0.6, duration: 90 })
        break
      case 'think':
        this.look(0, -1)
        this.antenna?.setTint(0xffd36b)
        this.loop({ targets: this.head, rotation: 0.09, duration: 900 })
        left.setRotation(-0.9) // hand to chin
        break
      case 'work':
      case 'type':
        for (const e of this.eyes) e.setScale(1 / R, 0.55 / R)
        this.look(0, 1)
        this.every(110, (n) => {
          left.setRotation(n % 2 ? -0.55 : -0.2)
          right.setRotation(n % 2 ? 0.2 : 0.55)
        })
        break
      case 'talk':
        this.mouth.setVisible(true)
        this.every(95, () => this.mouth.setScale((0.35 + Math.random() * 0.75) / R, 1 / R))
        this.loop({ targets: this.head, y: -76, duration: 260 })
        this.loop({ targets: right, rotation: -0.5, duration: 420 })
        break
      case 'drink':
        right.setRotation(-2.3)
        this.look(0, -1)
        this.loop({ targets: this.head, rotation: -0.18, duration: 600 })
        break
      case 'run':
        this.jet.setAlpha(0.9)
        this.every(160, (n) => {
          left.setRotation(n % 2 ? 0.7 : -0.7)
          right.setRotation(n % 2 ? -0.7 : 0.7)
          this.head.setY(n % 2 ? -75.5 : -73)
        })
        break
      case 'look':
        this.look(0, -1)
        this.every(1400, (n) => this.look(n % 2 ? 1 : -1, -1))
        break
      case 'stretch':
        left.setRotation(2.6)
        right.setRotation(-2.6)
        this.loop({ targets: [left, right], scaleY: 1.15 / R, duration: 700 })
        break
    }
  }

  /** Fly along waypoints at `speed` world units per second; returns the flight time (ms). */
  flyAlong(points: Point[], speed: number, onDone?: () => void): number {
    this.stopFlight()
    if (!points.length) {
      onDone?.()
      return 0
    }
    this.flying = true
    this.setState('fly')
    let prev = { x: this.x, y: this.y }
    let total = 0
    const tweens = points.map((p) => {
      const ms = Math.max(60, (Math.hypot(p.x - prev.x, p.y - prev.y) / speed) * 1000)
      const dx = p.x - prev.x
      const dy = p.y - prev.y
      prev = p
      total += ms
      return {
        x: p.x,
        y: p.y,
        duration: ms,
        ease: 'Sine.easeInOut',
        onStart: () => {
          this.look(dx, dy)
          this.rig.setRotation(Math.abs(dx) > Math.abs(dy) ? Math.sign(dx) * 0.13 : 0)
        },
      }
    })
    this.flight = this.scene.tweens.chain({
      targets: this.root,
      tweens,
      onComplete: () => {
        this.flight = undefined
        this.flying = false
        this.setState('idle')
        onDone?.()
      },
    })
    return total
  }

  stopFlight(): void {
    this.flight?.stop()
    this.flight = undefined
    this.flying = false
  }
}
