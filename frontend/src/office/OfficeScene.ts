// The office: three themed rooms on a hallway, with a robot per agent, drawn entirely in code
// (no image assets, so nothing to license). Events arrive through `play(event)` and each robot
// acts its own out in order: fly between rooms along the hallway, think, work at its console,
// talk in a speech bubble, carry answers to the exit, fly home when idle.

import Phaser from 'phaser'
import {
  AGENTS,
  NAMES,
  bubbleText,
  duration,
  toAction,
  type Action,
  type AgentId,
  type OfficeEvent,
  type Spot,
} from './choreography'
import {
  EXIT,
  HALL_Y,
  HEIGHT,
  ROOM_BOTTOM,
  ROOM_W,
  WIDTH,
  path,
  pathLength,
  roomOf,
  roomX,
  spotPoint,
  type Point,
} from './layout'

export { HEIGHT, WIDTH }

const PX = 3 // one art pixel on screen
const SPEED = 170 // robot flying speed, px/s
const DOOR_W = 54

interface Theme {
  title: string
  floor: [number, number]
  wall: number
  body: number
  dark: number
  light: number // antenna and chest light
}

const THEME: Record<AgentId, Theme> = {
  health_coach: {
    title: 'HEALTH LAB',
    floor: [0x2b3d36, 0x30443b],
    wall: 0x3f6b5c,
    body: 0x37b24d,
    dark: 0x2b8a3e,
    light: 0xff6b6b,
  },
  manager: {
    title: 'COMMAND ROOM',
    floor: [0x2c3350, 0x313958],
    wall: 0x44507a,
    body: 0x4c6ef5,
    dark: 0x364fc7,
    light: 0xffd43b,
  },
  market_scout: {
    title: 'TRADING DESK',
    floor: [0x3d3128, 0x43362c],
    wall: 0x6b4f3a,
    body: 0xf76707,
    dark: 0xd9480f,
    light: 0x66d9e8,
  },
}

// A 16×16 robot, one letter per art pixel. Frames: eyes open, eyes shut (blink, typing), and
// hovering with its jet lit (flying).
const ROBOT = [
  '.......LL.......',
  '.......AA.......',
  '....HHHHHHHH....',
  '...HHHHHHHHHH...',
  '...HVVVVVVVVH...',
  '...HVEEVVEEVH...',
  '...HVVVVVVVVH...',
  '...HHHHHHHHHH...',
  '.....NNNNNN.....',
  '..RBBBBBBBBBBR..',
  '.RRBBBBCCBBBBRR.',
  '.R.BBBBCCBBBB.R.',
  '.R.BBBBBBBBBB.R.',
  '...DDDDDDDDDD...',
  '....TTTTTTTT....',
]
const FEET = { stand: '...TTTTTTTTTT...', fly: '.....FFFFFF.....' }

interface Robot {
  id: AgentId
  sprite: Phaser.GameObjects.Sprite
  label: Phaser.GameObjects.Text
  bubble?: Phaser.GameObjects.Container
  screen: Phaser.GameObjects.Rectangle
  queue: Action[]
  busy: boolean
  flying: boolean
  typing?: Phaser.Time.TimerEvent
}

export class OfficeScene extends Phaser.Scene {
  private robots = new Map<AgentId, Robot>()

  constructor() {
    super('office')
  }

  create(): void {
    this.drawHallway()
    for (const id of AGENTS) this.drawRoom(id)
    for (const id of AGENTS) this.makeTextures(id)
    for (const id of AGENTS) this.robots.set(id, this.makeRobot(id))
    // Robots blink now and then while standing still.
    this.time.addEvent({
      delay: 2600,
      loop: true,
      callback: () => {
        for (const r of this.robots.values()) {
          if (r.flying || r.typing || Math.random() > 0.5) continue
          r.sprite.setTexture(`${r.id}-blink`)
          this.time.delayedCall(160, () => !r.flying && !r.typing && r.sprite.setTexture(`${r.id}-open`))
        }
      },
    })
  }

  /** Queue one event; each robot acts out its own events in order. */
  play(event: OfficeEvent): void {
    const robot = this.robots.get(event.agent)
    if (!robot) return
    robot.queue.push(toAction(event))
    this.next(robot)
  }

  // ---- the building ------------------------------------------------------------------

  private drawHallway(): void {
    const g = this.add.graphics()
    for (let x = 0; x < WIDTH; x += 20)
      for (let y = ROOM_BOTTOM; y < HEIGHT; y += 20) {
        g.fillStyle((x / 20 + y / 20) % 2 ? 0x30303c : 0x2b2b36).fillRect(x, y, 20, 20)
      }
    g.fillStyle(0x3a3a48).fillRect(0, HALL_Y + 34, WIDTH, 4) // a runner line along the hall
    // The exit: answers leave here for the owner's Telegram.
    g.fillStyle(0x495057).fillRect(EXIT.x - 22, ROOM_BOTTOM + 4, 44, 6)
    g.fillStyle(0x6b4f3a).fillRect(EXIT.x - 18, ROOM_BOTTOM + 10, 36, 52)
    g.fillStyle(0xd9b44a).fillCircle(EXIT.x + 10, ROOM_BOTTOM + 38, 2.5)
    g.fillStyle(0x74c0fc).fillTriangle(EXIT.x - 8, 300, EXIT.x + 9, 293, EXIT.x - 1, 306) // paper plane
    this.text(EXIT.x, ROOM_BOTTOM + 66, 'TO YOU', '#c8d0dc', 9).setOrigin(0.5, 0)
  }

  private drawRoom(id: AgentId): void {
    const t = THEME[id]
    const x0 = ROOM_W * roomOf(id)
    const cx = roomX(id)
    const g = this.add.graphics()
    // floor and back wall
    for (let x = x0; x < x0 + ROOM_W; x += 16)
      for (let y = 64; y < ROOM_BOTTOM; y += 16)
        g.fillStyle(((x - x0) / 16 + y / 16) % 2 ? t.floor[0] : t.floor[1]).fillRect(x, y, 16, 16)
    g.fillStyle(t.wall).fillRect(x0, 0, ROOM_W, 64)
    g.fillStyle(0x1b1b24).fillRect(x0, 58, ROOM_W, 6)
    // side walls between rooms, and the bottom wall with a doorway
    g.fillStyle(0x15151c)
    if (roomOf(id) > 0) g.fillRect(x0 - 3, 0, 6, ROOM_BOTTOM)
    g.fillRect(x0, ROOM_BOTTOM - 4, ROOM_W / 2 - DOOR_W / 2, 8)
    g.fillRect(cx + DOOR_W / 2, ROOM_BOTTOM - 4, ROOM_W / 2 - DOOR_W / 2, 8)
    // room sign
    g.fillStyle(0x1b1b24).fillRoundedRect(cx - 52, 6, 104, 16, 3)
    this.text(cx, 9, t.title, '#e8e8e8', 10).setOrigin(0.5, 0)

    if (id === 'health_coach') this.healthLab(g, x0)
    if (id === 'manager') this.commandRoom(g, x0)
    if (id === 'market_scout') this.tradingDesk(g, x0)

    // the robot's console: a desk with a screen that lights up while it works
    g.fillStyle(0x495057).fillRect(cx - 40, 166, 80, 22)
    g.fillStyle(0x343a40).fillRect(cx - 40, 186, 80, 6)
    g.fillStyle(0x212529).fillRect(cx - 16, 150, 32, 18)
    this.text(cx, 196, NAMES[id], '#e8e8e8', 10).setOrigin(0.5, 0)
  }

  private healthLab(g: Phaser.GameObjects.Graphics, x0: number): void {
    // heart-rate monitor with an ECG trace
    g.fillStyle(0x101418).fillRect(x0 + 18, 26, 74, 28)
    g.lineStyle(2, 0x51cf66)
    const ecg = [0, 0, 0, 0, -10, 12, -4, 0, 0, 0, 0, -8, 9, -2, 0, 0]
    g.beginPath()
    ecg.forEach((v, i) => {
      const x = x0 + 22 + i * 4.3
      const y = 40 + v
      if (i) g.lineTo(x, y)
      else g.moveTo(x, y)
    })
    g.strokePath()
    g.fillStyle(0xff6b6b).fillCircle(x0 + 86, 31, 2)
    // treadmill
    g.fillStyle(0x212529).fillRect(x0 + 14, 214, 70, 14)
    g.fillStyle(0x495057).fillRect(x0 + 14, 228, 70, 4)
    g.fillStyle(0x868e96).fillRect(x0 + 74, 190, 4, 26).fillRect(x0 + 66, 188, 18, 4)
    // dumbbell rack
    g.fillStyle(0x495057).fillRect(x0 + 150, 230, 48, 4)
    for (const dx of [156, 176]) {
      g.fillStyle(0x212529).fillRect(x0 + dx, 222, 4, 8).fillRect(x0 + dx + 12, 222, 4, 8)
      g.fillStyle(0xadb5bd).fillRect(x0 + dx + 4, 225, 8, 2)
    }
    // water bottle
    g.fillStyle(0x74c0fc).fillRect(x0 + 186, 78, 10, 18)
    g.fillStyle(0x1c7ed6).fillRect(x0 + 188, 74, 6, 4)
  }

  private commandRoom(g: Phaser.GameObjects.Graphics, x0: number): void {
    // big status screen: three agent status lights
    g.fillStyle(0x0b1020).fillRect(x0 + 46, 22, 120, 34)
    g.lineStyle(1, 0x364fc7).strokeRect(x0 + 46, 22, 120, 34)
    for (const [i, c] of [0x37b24d, 0x4c6ef5, 0xf76707].entries()) {
      g.fillStyle(c).fillCircle(x0 + 70 + i * 36, 34, 4)
      g.fillStyle(0x364fc7).fillRect(x0 + 60 + i * 36, 44, 20, 3)
    }
    // console lights on the desk sides and a rug
    g.fillStyle(0x1f2a4d).fillRoundedRect(x0 + 46, 205, 120, 52, 6)
    g.lineStyle(2, 0x364fc7).strokeRoundedRect(x0 + 46, 205, 120, 52, 6)
    for (const [i, c] of [0xffd43b, 0x51cf66, 0xff6b6b, 0x74c0fc].entries())
      g.fillStyle(c).fillRect(x0 + 72 + i * 20, 180, 5, 3)
    // antenna mast in the corner
    g.fillStyle(0x868e96).fillRect(x0 + 192, 80, 3, 40)
    g.fillStyle(0xffd43b).fillCircle(x0 + 193, 78, 3)
  }

  private tradingDesk(g: Phaser.GameObjects.Graphics, x0: number): void {
    // three chart screens with candlesticks
    for (let s = 0; s < 3; s++) {
      const sx = x0 + 14 + s * 64
      g.fillStyle(0x101418).fillRect(sx, 26, 56, 30)
      for (let c = 0; c < 6; c++) {
        const up = (c + s) % 3 !== 0
        const h = 6 + ((c * 7 + s * 3) % 9)
        const y = 30 + ((c * 5 + s * 4) % 12)
        g.fillStyle(up ? 0x51cf66 : 0xff6b6b).fillRect(sx + 5 + c * 8, y, 4, h)
        g.fillRect(sx + 6 + c * 8, y - 2, 2, h + 4)
      }
    }
    // ticker strip (decoration only: the Scout's real briefs come in Phase 6)
    g.fillStyle(0x101418).fillRect(x0 + 6, 66, ROOM_W - 12, 10)
    this.text(x0 + 10, 66, '▲ BTC  ▼ ETH  ▲ SOL  ▲ DOGE', '#ffd43b', 8)
    // a second desk with a laptop
    g.fillStyle(0x6b4f3a).fillRect(x0 + 150, 222, 52, 14)
    g.fillStyle(0xadb5bd).fillRect(x0 + 164, 214, 22, 8)
  }

  private text(x: number, y: number, s: string, color: string, size: number): Phaser.GameObjects.Text {
    return this.add.text(x, y, s, { fontFamily: 'monospace', fontSize: `${size}px`, color })
  }

  // ---- robots ------------------------------------------------------------------------

  private makeTextures(id: AgentId): void {
    const t = THEME[id]
    const colors: Record<string, number> = {
      L: t.light, A: 0x868e96, H: 0xced4da, V: 0x1b1b24, E: 0x66d9e8, N: 0x868e96,
      B: t.body, C: t.light, R: 0xadb5bd, D: t.dark, T: 0x495057, F: 0xffa94d,
    }
    const frames: Record<string, string[]> = {
      open: [...ROBOT, FEET.stand],
      blink: [...ROBOT.map((r) => r.replace(/E/g, 'V')), FEET.stand],
      fly: [...ROBOT, FEET.fly],
    }
    for (const [name, rows] of Object.entries(frames)) {
      const g = this.make.graphics({}, false)
      rows.forEach((row, y) =>
        [...row].forEach((c, x) => {
          if (c !== '.') g.fillStyle(colors[c]).fillRect(x * PX, y * PX, PX, PX)
        }),
      )
      g.generateTexture(`${id}-${name}`, 16 * PX, 16 * PX)
      g.destroy()
    }
  }

  private makeRobot(id: AgentId): Robot {
    const { x, y } = spotPoint({ desk: id })
    const screen = this.add.rectangle(roomX(id), 159, 28, 14, 0x2b3a55)
    const sprite = this.add.sprite(x, y, `${id}-open`).setOrigin(0.5, 1).setDepth(y)
    const label = this.text(x, y + 26, '', '#ffd43b', 9).setOrigin(0.5, 0).setDepth(900)
    return { id, sprite, label, screen, queue: [], busy: false, flying: false }
  }

  // ---- acting ------------------------------------------------------------------------

  private next(robot: Robot): void {
    if (robot.busy) return
    const action = robot.queue.shift()
    if (!action) return
    robot.busy = true
    const ms = this.act(robot, action)
    // Under a backlog, hurry: a long queue would otherwise lag far behind the real run.
    const speed = robot.queue.length > 6 ? 0.4 : 1
    this.time.delayedCall(ms * speed, () => {
      robot.busy = false
      this.next(robot)
    })
  }

  /** Starts an action; returns how long it holds the stage. */
  private act(robot: Robot, a: Action): number {
    this.stopTyping(robot)
    robot.label.setText('')
    switch (a.kind) {
      case 'think':
        this.say(robot, '…', true)
        return duration(a)
      case 'walk':
        return this.fly(robot, a.to)
      case 'work':
        this.clearBubble(robot)
        robot.label.setText(a.label)
        robot.typing = this.time.addEvent({
          delay: 140,
          loop: true,
          callback: () => {
            robot.screen.setFillStyle(Math.random() > 0.5 ? 0x74c0fc : 0x4dabf7)
            robot.sprite.setTexture(`${robot.id}-${Math.random() > 0.5 ? 'blink' : 'open'}`)
          },
        })
        return duration(a)
      case 'talk':
        this.say(robot, bubbleText(a.text), false)
        return duration(a)
      case 'idle':
        this.time.delayedCall(1200, () => {
          if (robot.busy || robot.queue.length) return
          this.clearBubble(robot)
          if (!this.isAt(robot, { desk: robot.id })) this.fly(robot, { desk: robot.id })
        })
        return duration(a)
    }
  }

  private isAt(robot: Robot, s: Spot): boolean {
    const p = spotPoint(s)
    return Math.abs(robot.sprite.x - p.x) < 1 && Math.abs(robot.sprite.y - p.y) < 1
  }

  /** Fly along the hallway route to a spot; returns the flight time. */
  private fly(robot: Robot, s: Spot): number {
    this.clearBubble(robot)
    const from: Point = { x: robot.sprite.x, y: robot.sprite.y }
    const pts = path(from, spotPoint(s))
    const total = Math.max(400, (pathLength(from, pts) / SPEED) * 1000)
    robot.flying = true
    robot.sprite.setTexture(`${robot.id}-fly`)
    let prev = from
    const steps = pts.map((p) => {
      const ms = Math.max(60, (Math.hypot(p.x - prev.x, p.y - prev.y) / SPEED) * 1000)
      const flip = p.x < prev.x
      prev = p
      return { p, ms, flip }
    })
    this.tweens.chain({
      targets: robot.sprite,
      tweens: steps.map(({ p, ms, flip }) => ({
        x: p.x,
        y: p.y,
        duration: ms,
        ease: 'Linear',
        onStart: () => robot.sprite.setFlipX(flip),
        onUpdate: () => {
          robot.sprite.setDepth(robot.sprite.y)
          robot.label.setPosition(robot.sprite.x, robot.sprite.y + 26)
        },
      })),
      onComplete: () => {
        robot.flying = false
        robot.sprite.setTexture(`${robot.id}-open`).setFlipX(false)
        robot.label.setPosition(robot.sprite.x, robot.sprite.y + 26)
      },
    })
    return total + 150
  }

  private stopTyping(robot: Robot): void {
    robot.typing?.remove()
    robot.typing = undefined
    robot.screen.setFillStyle(0x2b3a55)
    if (!robot.flying) robot.sprite.setTexture(`${robot.id}-open`)
  }

  private clearBubble(robot: Robot): void {
    robot.bubble?.destroy()
    robot.bubble = undefined
  }

  private say(robot: Robot, text: string, thought: boolean): void {
    this.clearBubble(robot)
    const maxWidth = 170
    const body = this.add.text(0, 0, text, {
      fontFamily: 'monospace',
      fontSize: '10px',
      color: '#1b1b24',
      wordWrap: { width: maxWidth },
    })
    const w = Math.min(maxWidth, body.width) + 12
    const h = body.height + 10
    const g = this.add.graphics()
    g.fillStyle(thought ? 0xe9ecef : 0xffffff).fillRoundedRect(-w / 2, -h, w, h, 6)
    g.fillTriangle(-5, 0, 5, 0, 0, 7)
    body.setPosition(-w / 2 + 6, -h + 5)
    // Keep the bubble on screen even for robots near the edges.
    const x = Phaser.Math.Clamp(robot.sprite.x, w / 2 + 4, WIDTH - w / 2 - 4)
    const y = Math.max(h + 4, robot.sprite.y - 52)
    robot.bubble = this.add.container(x, y, [g, body]).setDepth(1000)
  }
}

export function createOffice(parent: HTMLElement): { game: Phaser.Game; scene: () => OfficeScene | null } {
  const game = new Phaser.Game({
    type: Phaser.AUTO,
    parent,
    width: WIDTH,
    height: HEIGHT,
    pixelArt: true,
    backgroundColor: '#1b1b24',
    scale: { mode: Phaser.Scale.FIT, autoCenter: Phaser.Scale.CENTER_HORIZONTALLY },
    scene: [OfficeScene],
  })
  return {
    game,
    scene: () => (game.scene.isActive('office') ? (game.scene.getScene('office') as OfficeScene) : null),
  }
}
