// The office. Three rooms far apart on a night-time floor, joined by long hallways, with a robot
// per agent. Every event the backend sends becomes one step on a single timeline (timeline.ts),
// so the story plays in order: the Manager flies all the way to the Health Lab before the Coach
// answers, and carries the answer back out to the uplink ("to you", i.e. Telegram).
//
// Two cameras: the office camera (zoomed out to show the whole floor, or following whoever is
// acting) and an overlay camera at screen scale for the bubbles and name tags.

import Phaser from 'phaser'
import { AGENTS, NAMES, bubbleText, duration, toAction, type Action, type AgentId, type OfficeEvent } from './choreography'
import { choreDelay, choresFor, type Chore } from './chores'
import { Overlay } from './overlay'
import { Timeline } from './timeline'
import { EXIT, WORLD_H, WORLD_W, path, placeAt, spotPoint } from './world'
import {
  candles,
  drawBackground,
  drawDoors,
  drawHallways,
  drawRooms,
  drawUplink,
  ecg,
  hallwayPulses,
  holoLines,
  serverLights,
  statusBoard,
  ticker,
  treadmillBelt,
  type BoardState,
  type Desk,
  type Door,
  type Uplink,
} from './art/building'
import { hexNum, paint, rr, vgrad } from './art/paint'
import { Bot, type BotState } from './art/robot'

const SPEED = 300 // flying speed, world units per second
const TAG_COLOR: Record<AgentId, string> = { health_coach: '#ff6fb1', manager: '#5d8dff', market_scout: '#fcc419' }
export type View = 'overview' | 'follow'

interface ChoreRun {
  chore: Chore
  timers: Phaser.Time.TimerEvent[]
  prop?: Phaser.GameObjects.Image
}

export class OfficeScene extends Phaser.Scene {
  private bots = new Map<AgentId, Bot>()
  private desks!: Record<AgentId, Desk>
  private doors: Door[] = []
  private uplink!: Uplink
  private overlay!: Overlay
  private uiLayer!: Phaser.GameObjects.Layer
  private uiCam!: Phaser.Cameras.Scene2D.Camera
  private creatingUi = false
  private timeline = new Timeline<Action>((ms, fn) => this.time.delayedCall(ms, fn))
  private chores = new Map<AgentId, ChoreRun>()
  private nextChore = new Map<AgentId, number>()
  private tick: ((t: number) => void)[] = []
  private board!: (s: Record<AgentId, BoardState>) => void
  private belt!: (running: boolean, delta: number) => void
  private view: View = 'overview'
  private focus: AgentId = 'manager'
  private camTarget = new Phaser.Math.Vector2(WORLD_W / 2, WORLD_H / 2)
  readonly dpr: number

  constructor(dpr: number) {
    super('office')
    this.dpr = dpr
  }

  create(): void {
    const cam = this.cameras.main
    cam.setBackgroundColor('#070a14')
    this.uiCam = this.cameras.add(0, 0, this.scale.width, this.scale.height).setOrigin(0, 0).setZoom(this.dpr)
    this.uiLayer = this.add.layer()
    cam.ignore(this.uiLayer)
    // Everything that isn't overlay is office: keep it off the overlay camera.
    this.events.on(Phaser.Scenes.Events.ADDED_TO_SCENE, (obj: Phaser.GameObjects.GameObject) => {
      if (!this.creatingUi && (obj as unknown) !== this.uiLayer) this.uiCam.ignore(obj)
    })

    drawBackground(this)
    drawHallways(this)
    hallwayPulses(this)
    this.desks = drawRooms(this)
    this.doors = drawDoors(this)
    this.uplink = drawUplink(this)
    this.tick.push(ecg(this))
    candles(this)
    serverLights(this)
    ticker(this)
    this.board = statusBoard(this)
    this.belt = treadmillBelt(this)
    this.props()

    this.overlay = new Overlay(this, this.uiLayer, this.dpr)
    for (const id of AGENTS) {
      const at = spotPoint({ desk: id })
      this.bots.set(id, new Bot(this, id, at.x, at.y))
      this.ui(() => this.overlay.add(id, NAMES[id], hexNum(TAG_COLOR[id])))
      this.nextChore.set(id, this.time.now + 4000 + Math.random() * 6000)
    }

    // blinking, and pottering about between requests
    this.time.addEvent({
      delay: 900,
      loop: true,
      callback: () => {
        for (const b of this.bots.values()) if (Math.random() < 0.3) b.blink()
      },
    })
    this.time.addEvent({
      delay: 500,
      loop: true,
      callback: () => {
        for (const id of AGENTS) if (this.isFree(id)) this.startChore(id)
      },
    })

    this.scale.on(Phaser.Scale.Events.RESIZE, () => this.layout(false))
    this.view = this.cssWidth() < 720 ? 'follow' : 'overview'
    this.layout(false)
  }

  /** Create overlay objects: they go on the overlay layer and camera only. */
  private ui(fn: () => void): void {
    this.creatingUi = true
    try {
      fn()
    } finally {
      this.creatingUi = false
    }
  }

  private cssWidth(): number {
    return this.scale.width / this.dpr
  }

  // ---- cameras ------------------------------------------------------------------------------

  setView(view: View): void {
    this.view = view
    this.layout(true)
  }

  getView(): View {
    return this.view
  }

  private fitZoom(): number {
    const { width, height } = this.scale
    return Math.min(width / (WORLD_W + 40), height / (WORLD_H + 40))
  }

  private layout(animate: boolean): void {
    const { width, height } = this.scale
    const cam = this.cameras.main
    cam.setSize(width, height)
    this.uiCam.setSize(width, height)
    if (this.view === 'overview') {
      cam.stopFollow()
      const z = this.fitZoom()
      if (animate) {
        cam.zoomTo(z, 700, 'Sine.easeInOut')
        cam.pan(WORLD_W / 2, WORLD_H / 2, 700, 'Sine.easeInOut')
      } else {
        cam.setZoom(z)
        cam.centerOn(WORLD_W / 2, WORLD_H / 2)
      }
    } else {
      // about one room across on a phone, a room and its hallway on a laptop
      const across = Phaser.Math.Clamp(this.cssWidth() * 1.6, 640, 1150)
      const z = Math.max(this.fitZoom() * 1.5, width / across)
      const bot = this.bots.get(this.focus)
      if (animate) cam.zoomTo(z, 700, 'Sine.easeInOut')
      else cam.setZoom(z)
      if (bot) {
        this.camTarget.set(...this.framing())
        if (!animate) cam.centerOn(this.camTarget.x, this.camTarget.y)
        cam.startFollow(this.camTarget, false, 0.09, 0.09)
      }
    }
  }

  private follow(id: AgentId): void {
    this.focus = id
  }

  /** Where the follow camera looks: the robot acting, or both robots when one visits another. */
  private framing(): [number, number] {
    const f = this.bots.get(this.focus)!
    const room = placeAt(f)
    let other: { x: number; y: number } | undefined
    if (room && room !== 'uplink' && room !== f.id) other = this.bots.get(room)
    else if (room === f.id)
      other = [...this.bots.values()].find((b) => b !== f && placeAt(b) === room && !b.flying)
    if (other) return [(f.x + other.x) / 2, (f.y + other.y) / 2 - 50]
    return [f.x, f.y - 50]
  }

  // ---- events → the timeline ----------------------------------------------------------------

  /** Queue one event; it plays when everything before it has. */
  play(event: OfficeEvent): void {
    const bot = this.bots.get(event.agent)
    if (!bot) return
    const action = toAction(event)
    // Interrupted mid-chore: head back to the desk first, unless this flies off anyway.
    if (this.stopChore(event.agent) && action.kind !== 'walk' && !this.atHome(event.agent))
      this.enqueue({ kind: 'walk', agent: event.agent, to: { desk: event.agent } })
    this.enqueue(action)
  }

  private enqueue(action: Action, front = false): void {
    const step = { item: action, play: (a: Action, hurry: number) => this.act(a, hurry) }
    if (front) this.timeline.pushFront(step)
    else this.timeline.push(step)
  }

  private atHome(id: AgentId): boolean {
    const bot = this.bots.get(id)!
    const p = spotPoint({ desk: id })
    return Math.hypot(bot.x - p.x, bot.y - p.y) < 2
  }

  /** Nothing playing or waiting: the office is between requests. */
  quiet(): boolean {
    return !this.timeline.busy && this.timeline.waiting().length === 0
  }

  /** What each robot is up to, for the page around the office. */
  statuses(): Record<AgentId, string> {
    const out = {} as Record<AgentId, string>
    for (const [id, b] of this.bots) {
      const chore = this.chores.get(id)
      const words: Partial<Record<BotState, string>> = { think: 'thinking…', work: 'working', talk: 'talking' }
      out[id] = chore ? chore.chore.label : b.flying ? 'on the move' : (words[b.state] ?? 'idle')
    }
    return out
  }

  /** Starts an action; returns how long it holds the stage (ms). */
  private act(a: Action, hurry: number): number {
    const bot = this.bots.get(a.agent)!
    this.follow(a.agent)
    this.nextChore.set(a.agent, this.time.now + choreDelay()) // a rest before any chore
    if (a.kind !== 'talk') this.overlay.quiet(a.agent)
    this.overlay.chip(a.agent, null)
    switch (a.kind) {
      case 'think':
        bot.setState('think')
        this.overlay.think(a.agent)
        return duration(a) * hurry
      case 'walk': {
        const to = spotPoint(a.to)
        const target = 'visit' in a.to ? this.bots.get(a.to.visit) : undefined
        const ms = bot.flyAlong(path({ x: bot.x, y: bot.y }, to), SPEED / hurry, () => {
          if (target) {
            bot.look(target.x - bot.x)
            target.look(bot.x - target.x)
          }
        })
        return ms + 150
      }
      case 'work':
        bot.setState('work')
        this.overlay.chip(a.agent, a.label)
        return duration(a) * hurry
      case 'talk': {
        bot.setState('talk')
        this.overlay.say(a.agent, bubbleText(a.text), this.cssWidth())
        if (a.to === 'owner' && Math.hypot(bot.x - EXIT.x, bot.y - EXIT.y) < 40) this.uplink.burst()
        return duration(a) * Math.max(hurry, 0.75)
      }
      case 'idle': {
        bot.setState('idle')
        // Away from the desk with nothing else to do there: fly home next.
        const next = this.timeline.waiting().find((x) => x.agent === a.agent)
        if (!this.atHome(a.agent) && next?.kind !== 'walk')
          this.enqueue({ kind: 'walk', agent: a.agent, to: { desk: a.agent } }, true)
        return 250
      }
    }
  }

  // ---- chores -------------------------------------------------------------------------------

  private props(): void {
    paint(this, 'cup', 12, 16, (ctx) => {
      ctx.beginPath()
      ctx.moveTo(1, 1)
      ctx.lineTo(11, 1)
      ctx.lineTo(9, 15)
      ctx.lineTo(3, 15)
      ctx.closePath()
      ctx.fillStyle = vgrad(ctx, 1, 15, [[0, '#ffffff'], [1, '#c9d3e6']])
      ctx.fill()
      ctx.fillStyle = 'rgba(90,170,255,.8)'
      ctx.fillRect(2.4, 3, 7.2, 3)
    })
    paint(this, 'mug', 16, 14, (ctx) => {
      rr(ctx, 1, 1, 11, 12, 3)
      ctx.fillStyle = vgrad(ctx, 1, 13, [[0, '#ffd43b'], [1, '#e0a400']])
      ctx.fill()
      ctx.beginPath()
      ctx.arc(12.5, 7, 3, -Math.PI / 2, Math.PI / 2)
      ctx.strokeStyle = '#e0a400'
      ctx.lineWidth = 1.6
      ctx.stroke()
    })
  }

  private isFree(id: AgentId): boolean {
    const bot = this.bots.get(id)!
    if (bot.flying || this.chores.has(id) || this.overlay.speaking(id)) return false
    if (this.time.now < (this.nextChore.get(id) ?? 0) || !this.atHome(id)) return false
    // Nothing queued for it, and nobody on their way to see it.
    return !this.timeline
      .items()
      .some((a) => a.agent === id || (a.kind === 'walk' && 'visit' in a.to && a.to.visit === id))
  }

  private startChore(id: AgentId): void {
    const options = choresFor(id)
    const chore = options[Math.floor(Math.random() * options.length)]
    const bot = this.bots.get(id)!
    const run: ChoreRun = { chore, timers: [] }
    this.chores.set(id, run)
    const later = (ms: number, fn: () => void) => run.timers.push(this.time.delayedCall(ms, fn))
    const there = bot.flyAlong([chore.at], SPEED * 0.55)
    later(there + 50, () => {
      bot.setState(chore.anim as BotState)
      this.overlay.chip(id, chore.label, true)
      if (chore.prop) {
        run.prop = this.add.image(bot.x + 16, bot.y - 70, chore.prop).setScale(1 / 2).setDepth(bot.y + 1)
        this.tweens.add({ targets: run.prop, angle: -35, y: bot.y - 80, duration: 600, yoyo: true, hold: 500, repeat: 1 })
      }
      later(chore.ms, () => {
        run.prop?.destroy()
        this.overlay.chip(id, null)
        const home = bot.flyAlong([spotPoint({ desk: id })], SPEED * 0.55)
        later(home + 50, () => {
          this.chores.delete(id)
          this.nextChore.set(id, this.time.now + choreDelay())
        })
      })
    })
  }

  /** A real event arrived: drop any chore right where the robot is. True if one was going. */
  private stopChore(id: AgentId): boolean {
    const run = this.chores.get(id)
    if (!run) return false
    for (const t of run.timers) t.remove()
    run.prop?.destroy()
    this.chores.delete(id)
    const bot = this.bots.get(id)!
    bot.stopFlight()
    bot.setState('idle')
    this.overlay.chip(id, null)
    this.nextChore.set(id, this.time.now + choreDelay())
    return true
  }

  // ---- every frame --------------------------------------------------------------------------

  update(time: number, delta: number): void {
    const cam = this.cameras.main
    const view = cam.worldView
    const z = cam.zoom / this.dpr // world units → CSS px
    const states = {} as Record<AgentId, BoardState>
    for (const [id, bot] of this.bots) {
      bot.update(time)
      const sx = (bot.x - view.x) * z
      const sy = (bot.y - view.y) * z
      this.overlay.place(id, { headX: sx, headY: (bot.top - view.y) * z, feetX: sx, feetY: sy }, this.cssWidth())
      const s = bot.state
      states[id] = s === 'talk' ? 'talk' : s === 'think' || s === 'work' ? 'busy' : placeAt(bot) !== id ? 'away' : 'idle'
      holoLines(this.desks[id], s === 'work' && this.atHome(id), time)
    }
    this.board(states)
    if (this.view === 'follow') this.camTarget.set(...this.framing())
    this.belt(this.bots.get('health_coach')!.state === 'run', delta)
    for (const f of this.tick) f(time)
    // doors slide open while a robot passes
    for (const d of this.doors) {
      const near = [...this.bots.values()].some((b) => Math.abs(b.x - d.x) < 60 && Math.abs(b.y - d.y) < 90)
      d.open += ((near ? 1 : 0) - d.open) * 0.15
      d.left.scaleX = d.right.scaleX = Math.max(0.05, 1 - d.open)
    }
  }
}

/** One Phaser game in `parent`, sized to it and sharp on high-density screens. */
export function createOffice(parent: HTMLElement): {
  game: Phaser.Game
  scene: () => OfficeScene | null
  destroy: () => void
} {
  const dpr = Math.min(window.devicePixelRatio || 1, 2.5)
  const size = () => ({ w: Math.max(1, parent.clientWidth), h: Math.max(1, parent.clientHeight) })
  const { w, h } = size()
  const scene = new OfficeScene(dpr)
  const game = new Phaser.Game({
    type: Phaser.AUTO,
    parent,
    width: Math.round(w * dpr),
    height: Math.round(h * dpr),
    backgroundColor: '#070a14',
    antialias: true,
    scale: { mode: Phaser.Scale.NONE, zoom: 1 / dpr },
    scene: [scene],
  })
  const observer = new ResizeObserver(() => {
    const s = size()
    game.scale.resize(Math.round(s.w * dpr), Math.round(s.h * dpr))
    game.scale.setZoom(1 / dpr)
  })
  observer.observe(parent)
  if (new URLSearchParams(window.location.search).has('debug')) Object.assign(window, { office: game })
  return {
    game,
    scene: () => (game.scene.isActive('office') ? scene : null),
    destroy: () => {
      observer.disconnect()
      game.destroy(true)
    },
  }
}
