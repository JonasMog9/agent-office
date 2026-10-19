// The overlay: speech bubbles, name tags and tool chips, drawn by a second camera at a fixed
// on-screen size. However far the office camera zooms out, the words stay readable.

import Phaser from 'phaser'
import type { AgentId } from './choreography'
import { FONT } from './art/paint'

export interface Anchor {
  headX: number
  headY: number
  feetX: number
  feetY: number
}

const DARK = '#151a2b'

class Bubble {
  readonly box: Phaser.GameObjects.Container
  private g: Phaser.GameObjects.Graphics
  private text: Phaser.GameObjects.Text
  private dots?: Phaser.Time.TimerEvent
  kind: 'speech' | 'thought' = 'speech'
  private scene: Phaser.Scene

  constructor(scene: Phaser.Scene, layer: Phaser.GameObjects.Layer, dpr: number) {
    this.scene = scene
    this.g = scene.add.graphics()
    this.text = scene.add.text(0, 0, '', {
      fontFamily: FONT,
      fontSize: '13px',
      color: DARK,
      lineSpacing: 3,
      resolution: dpr,
      wordWrap: { width: 240, useAdvancedWrap: true },
    })
    this.box = scene.add.container(0, 0, [this.g, this.text]).setVisible(false)
    layer.add(this.box)
  }

  show(text: string, kind: 'speech' | 'thought', maxWidth: number): void {
    this.dots?.remove()
    this.kind = kind
    this.text.setWordWrapWidth(maxWidth, true)
    if (kind === 'thought') {
      let n = 0
      this.text.setText('•  ').setColor('#5b6480').setFontSize(16)
      this.dots = this.scene.time.addEvent({
        delay: 330,
        loop: true,
        callback: () => this.text.setText(['•  ', '•• ', '•••'][++n % 3]),
      })
    } else this.text.setText(text).setColor(DARK).setFontSize(13)
    this.box.setVisible(true).setAlpha(0).setScale(0.92)
    this.scene.tweens.add({ targets: this.box, alpha: 1, scale: 1, duration: 160, ease: 'Back.easeOut' })
  }

  hide(): void {
    this.dots?.remove()
    this.box.setVisible(false)
  }

  get visible(): boolean {
    return this.box.visible
  }

  /** Above the head, kept on screen; the tail points at the robot. */
  place(a: Anchor, viewW: number): void {
    const padX = this.kind === 'thought' ? 12 : 12
    const padY = this.kind === 'thought' ? 4 : 9
    const w = Math.ceil(this.text.width) + padX * 2
    const h = Math.ceil(this.text.height) + padY * 2
    const x = Phaser.Math.Clamp(a.headX - w / 2, 8, viewW - w - 8)
    // above the name tag, or below the robot when there's no room above
    const below = a.headY - h - 38 < 6
    const y = below ? a.feetY + 16 : a.headY - h - 38
    this.box.setPosition(x, y)
    this.text.setPosition(padX, padY)
    const tail = Phaser.Math.Clamp(a.headX - x, 14, w - 14)
    const g = this.g
    g.clear()
    g.fillStyle(0x000000, 0.28).fillRoundedRect(1, 4, w, h, 13)
    const fill = this.kind === 'thought' ? 0xe9edf7 : 0xffffff
    g.fillStyle(fill, 1).fillRoundedRect(0, 0, w, h, 13)
    if (this.kind === 'thought') {
      if (below) g.fillCircle(tail - 4, -6, 4).fillCircle(tail - 8, -13, 2.4)
      else g.fillCircle(tail - 4, h + 6, 4).fillCircle(tail - 8, h + 13, 2.4)
    } else if (below) g.fillTriangle(tail - 7, 1, tail + 7, 1, tail, -9)
    else g.fillTriangle(tail - 7, h - 1, tail + 7, h - 1, tail, h + 9)
  }
}

class Tag {
  readonly box: Phaser.GameObjects.Container
  private chip: Phaser.GameObjects.Container
  private chipText: Phaser.GameObjects.Text
  private chipBg: Phaser.GameObjects.Graphics

  constructor(scene: Phaser.Scene, layer: Phaser.GameObjects.Layer, dpr: number, name: string, color: number) {
    const label = scene.add.text(0, 0, name, {
      fontFamily: FONT,
      fontSize: '11px',
      fontStyle: '600',
      color: '#eef2ff',
      resolution: dpr,
    })
    const w = Math.ceil(label.width) + 26
    const bg = scene.add.graphics()
    bg.fillStyle(0x0b1022, 0.78).fillRoundedRect(-w / 2, 0, w, 20, 10)
    bg.lineStyle(1, color, 0.6).strokeRoundedRect(-w / 2, 0, w, 20, 10)
    bg.fillStyle(color, 1).fillCircle(-w / 2 + 11, 10, 3.5)
    label.setPosition(-w / 2 + 19, 3)
    this.box = scene.add.container(0, 0, [bg, label])
    this.chipBg = scene.add.graphics()
    this.chipText = scene.add.text(0, 0, '', {
      fontFamily: FONT,
      fontSize: '11px',
      fontStyle: '600',
      color: '#7ee8ff',
      resolution: dpr,
    })
    this.chip = scene.add.container(0, 0, [this.chipBg, this.chipText]).setVisible(false)
    layer.add([this.box, this.chip])
  }

  setChip(text: string | null, muted = false): void {
    if (!text) {
      this.chip.setVisible(false)
      return
    }
    this.chipText.setText(muted ? text : `⚙ ${text}`).setColor(muted ? '#c9d0e6' : '#7ee8ff')
    const w = Math.ceil(this.chipText.width) + 18
    this.chipBg.clear()
    this.chipBg.fillStyle(muted ? 0x1a2036 : 0x07222e, 0.88).fillRoundedRect(-w / 2, 0, w, 20, 10)
    this.chipBg.lineStyle(1, muted ? 0x5b6480 : 0x4de1ff, 0.7).strokeRoundedRect(-w / 2, 0, w, 20, 10)
    this.chipText.setPosition(-w / 2 + 9, 3)
    this.chip.setVisible(true)
  }

  get chipVisible(): boolean {
    return this.chip.visible
  }

  /** The name floats just above the head; a tool chip above that. */
  place(a: Anchor): void {
    this.box.setPosition(a.headX, a.headY - 26)
    this.chip.setPosition(a.headX, a.headY - 50)
  }
}

export class Overlay {
  private bubbles = new Map<AgentId, Bubble>()
  private tags = new Map<AgentId, Tag>()
  private scene: Phaser.Scene
  private layer: Phaser.GameObjects.Layer
  private dpr: number

  constructor(scene: Phaser.Scene, layer: Phaser.GameObjects.Layer, dpr: number) {
    this.scene = scene
    this.layer = layer
    this.dpr = dpr
  }

  add(id: AgentId, name: string, color: number): void {
    this.tags.set(id, new Tag(this.scene, this.layer, this.dpr, name, color))
    this.bubbles.set(id, new Bubble(this.scene, this.layer, this.dpr))
  }

  say(id: AgentId, text: string, viewW: number): void {
    this.bubbles.get(id)?.show(text, 'speech', Math.min(250, viewW * 0.62))
  }

  think(id: AgentId): void {
    this.bubbles.get(id)?.show('', 'thought', 200)
  }

  quiet(id: AgentId): void {
    this.bubbles.get(id)?.hide()
  }

  chip(id: AgentId, text: string | null, muted = false): void {
    this.tags.get(id)?.setChip(text, muted)
  }

  place(id: AgentId, a: Anchor, viewW: number): void {
    const b = this.bubbles.get(id)
    if (b?.visible) b.place(a, viewW)
    this.tags.get(id)?.place(a)
  }

  speaking(id: AgentId): boolean {
    return !!this.bubbles.get(id)?.visible
  }
}
