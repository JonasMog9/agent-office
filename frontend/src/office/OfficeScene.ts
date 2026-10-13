// The office: a Phaser scene drawn entirely in code (no image assets, so nothing to license).
// Each agent has a desk; events arrive through `play(event)` and are acted out one at a time
// per agent: walk to a desk, think, type at the monitor, talk in a speech bubble, go idle.

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

export const WIDTH = 640
export const HEIGHT = 400
const PX = 3 // size of one art pixel on screen
const TILE = 32

const STYLE: Record<AgentId, { shirt: number; hair: number }> = {
  manager: { shirt: 0x3b5bdb, hair: 0x2b2b2b },
  health_coach: { shirt: 0x2f9e44, hair: 0x8d5524 },
  market_scout: { shirt: 0xf08c00, hair: 0xc92a2a },
}
const DESK_X: Record<AgentId, number> = { health_coach: 150, manager: 320, market_scout: 490 }
const DESK_Y = 190

// 12×15 character, one letter per art pixel. Two frames: standing and mid-stride.
const BODY = [
  '....HHHH....',
  '...HHHHHH...',
  '...HSSSSH...',
  '...SESSES...',
  '...SSSSSS...',
  '....SSSS....',
  '...CCCCCC...',
  '..CCCCCCCC..',
  '.SCCCCCCCCS.',
  '.SCCCCCCCCS.',
  '..CCCCCCCC..',
  '...PPPPPP...',
]
const LEGS = [
  ['...PP..PP...', '...PP..PP...', '...KK..KK...'],
  ['...PP...PP..', '..PP....PP..', '..KK....KK..'],
]

interface Agent {
  id: AgentId
  sprite: Phaser.GameObjects.Sprite
  label: Phaser.GameObjects.Text
  bubble?: Phaser.GameObjects.Container
  screen: Phaser.GameObjects.Rectangle
  queue: Action[]
  busy: boolean
  typing?: Phaser.Time.TimerEvent
}

export class OfficeScene extends Phaser.Scene {
  private agents = new Map<AgentId, Agent>()

  constructor() {
    super('office')
  }

  create(): void {
    this.drawRoom()
    for (const id of AGENTS) this.makeTextures(id)
    for (const id of AGENTS) this.agents.set(id, this.makeAgent(id))
  }

  /** Queue one event; each agent acts out its events in order. */
  play(event: OfficeEvent): void {
    const agent = this.agents.get(event.agent)
    if (!agent) return
    agent.queue.push(toAction(event))
    this.next(agent)
  }

  // ---- drawing -----------------------------------------------------------------------

  private drawRoom(): void {
    const g = this.add.graphics()
    for (let x = 0; x < WIDTH; x += TILE)
      for (let y = 96; y < HEIGHT; y += TILE) {
        g.fillStyle((x / TILE + y / TILE) % 2 ? 0x3a3a4a : 0x34344a)
        g.fillRect(x, y, TILE, TILE)
      }
    g.fillStyle(0x4c5c7a).fillRect(0, 0, WIDTH, 96) // wall
    g.fillStyle(0x2c3a52).fillRect(0, 90, WIDTH, 6) // skirting
    // window
    g.fillStyle(0x99c1f1).fillRect(40, 18, 120, 52)
    g.lineStyle(4, 0x2c3a52).strokeRect(40, 18, 120, 52).lineBetween(100, 18, 100, 70)
    // chart wall behind the scout
    g.fillStyle(0x1f2633).fillRect(430, 14, 150, 64)
    g.lineStyle(2, 0x51cf66)
    g.beginPath()
    const pts = [0, 18, 10, 30, 22, 26, 40, 48, 36, 54]
    pts.forEach((v, i) => (i ? g.lineTo(438 + i * 14, 70 - v) : g.moveTo(438, 70 - v)))
    g.strokePath()
    this.add.text(436, 16, 'MARKETS', { fontFamily: 'monospace', fontSize: '9px', color: '#9aa4b2' })
    // the door, where answers go out to the owner on Telegram
    g.fillStyle(0x6b4f3a).fillRect(WIDTH - 46, 24, 34, 72)
    g.fillStyle(0xd9b44a).fillCircle(WIDTH - 18, 62, 3)
    this.add.text(WIDTH - 54, 6, 'to you', { fontFamily: 'monospace', fontSize: '9px', color: '#c8d0dc' })
    // plant
    g.fillStyle(0x8d5524).fillRect(200, 62, 18, 24)
    g.fillStyle(0x40c057).fillCircle(209, 54, 14)

    for (const id of AGENTS) {
      const x = DESK_X[id]
      g.fillStyle(0x7a5230).fillRect(x - 46, DESK_Y + 20, 92, 34) // desk top
      g.fillStyle(0x5c3d24).fillRect(x - 46, DESK_Y + 50, 92, 6)
      g.fillStyle(0x222831).fillRect(x - 18, DESK_Y - 6, 36, 26) // monitor
      g.fillStyle(0x222831).fillRect(x - 4, DESK_Y + 20, 8, 4)
      this.add
        .text(x, DESK_Y + 70, NAMES[id], { fontFamily: 'monospace', fontSize: '11px', color: '#e8e8e8' })
        .setOrigin(0.5, 0)
    }
  }

  private makeTextures(id: AgentId): void {
    const colors: Record<string, number> = {
      H: STYLE[id].hair, S: 0xf1c27d, E: 0x222222, C: STYLE[id].shirt, P: 0x343a52, K: 0x111111,
    }
    LEGS.forEach((legs, frame) => {
      const g = this.make.graphics({}, false)
      ;[...BODY, ...legs].forEach((row, y) =>
        [...row].forEach((c, x) => {
          if (c === '.') return
          g.fillStyle(colors[c]).fillRect(x * PX, y * PX, PX, PX)
        }),
      )
      g.generateTexture(`${id}-${frame}`, 12 * PX, 15 * PX)
      g.destroy()
    })
    this.anims.create({
      key: `${id}-walk`,
      frames: [{ key: `${id}-0` }, { key: `${id}-1` }],
      frameRate: 6,
      repeat: -1,
    })
  }

  private makeAgent(id: AgentId): Agent {
    const { x, y } = this.spot({ desk: id })
    const screen = this.add.rectangle(DESK_X[id], DESK_Y + 7, 30, 20, 0x2b3a55)
    const sprite = this.add.sprite(x, y, `${id}-0`).setOrigin(0.5, 1).setDepth(y)
    const label = this.add
      .text(x, y + 2, '', { fontFamily: 'monospace', fontSize: '9px', color: '#ffd43b' })
      .setOrigin(0.5, 0)
    return { id, sprite, label, screen, queue: [], busy: false }
  }

  // Where a character stands: behind its own desk, or in front of someone else's.
  private spot(s: Spot): { x: number; y: number } {
    if ('desk' in s) return { x: DESK_X[s.desk], y: DESK_Y + 20 }
    if ('door' in s) return { x: WIDTH - 60, y: 150 }
    return { x: DESK_X[s.visit] + 52, y: DESK_Y + 130 }
  }

  // ---- acting ------------------------------------------------------------------------

  private next(agent: Agent): void {
    if (agent.busy) return
    const action = agent.queue.shift()
    if (!action) return
    agent.busy = true
    this.act(agent, action)
    // Under a backlog, hurry: long queues would otherwise lag far behind the real run.
    const speed = agent.queue.length > 6 ? 0.4 : 1
    this.time.delayedCall(duration(action) * speed, () => {
      agent.busy = false
      this.next(agent)
    })
  }

  private act(agent: Agent, a: Action): void {
    this.stopTyping(agent)
    agent.label.setText('')
    switch (a.kind) {
      case 'think':
        this.say(agent, '…', true)
        break
      case 'walk':
        this.walk(agent, a.to, duration(a) - 100)
        break
      case 'work':
        this.clearBubble(agent)
        agent.label.setText(a.label)
        agent.typing = this.time.addEvent({
          delay: 140,
          loop: true,
          callback: () => {
            agent.screen.setFillStyle(Math.random() > 0.5 ? 0x74c0fc : 0x4dabf7)
            agent.sprite.setTexture(`${agent.id}-${Math.random() > 0.5 ? 1 : 0}`)
          },
        })
        break
      case 'talk':
        this.say(agent, bubbleText(a.text), false)
        break
      case 'idle':
        agent.screen.setFillStyle(0x2b3a55)
        this.time.delayedCall(1200, () => {
          if (agent.busy || agent.queue.length) return
          this.clearBubble(agent)
          // Away from the desk (visiting, or at the door): walk home.
          const home = this.spot({ desk: agent.id })
          if (agent.sprite.x !== home.x || agent.sprite.y !== home.y) this.walk(agent, { desk: agent.id }, 1300)
        })
        break
    }
  }

  private walk(agent: Agent, spot: Spot, ms: number): void {
    this.clearBubble(agent)
    const to = this.spot(spot)
    agent.sprite.setFlipX(to.x < agent.sprite.x)
    agent.sprite.play(`${agent.id}-walk`)
    this.tweens.add({ targets: agent.label, x: to.x, y: to.y + 2, duration: ms, ease: 'Sine.easeInOut' })
    this.tweens.add({
      targets: agent.sprite,
      x: to.x,
      y: to.y,
      duration: ms,
      ease: 'Sine.easeInOut',
      onUpdate: () => agent.sprite.setDepth(agent.sprite.y),
      onComplete: () => {
        agent.sprite.stop().setTexture(`${agent.id}-0`)
      },
    })
  }

  private stopTyping(agent: Agent): void {
    agent.typing?.remove()
    agent.typing = undefined
    agent.screen.setFillStyle(0x2b3a55)
    agent.sprite.setTexture(`${agent.id}-0`)
  }

  private clearBubble(agent: Agent): void {
    agent.bubble?.destroy()
    agent.bubble = undefined
  }

  private say(agent: Agent, text: string, thought: boolean): void {
    this.clearBubble(agent)
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
    // Keep the bubble on screen even for agents near the edges.
    const x = Phaser.Math.Clamp(agent.sprite.x, w / 2 + 4, WIDTH - w / 2 - 4)
    const y = Math.max(h + 4, agent.sprite.y - 52)
    agent.bubble = this.add.container(x, y, [g, body]).setDepth(1000)
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
