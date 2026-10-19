// Drawing helpers. Art is painted once with the Canvas 2D API (gradients, soft shadows, glows)
// into textures at RES× their world size, so it stays sharp when the camera zooms in.

import Phaser from 'phaser'

export const RES = 2

export type Ctx = CanvasRenderingContext2D

/** Paint a w×h (world units) texture under `key`; returns the key. */
export function paint(scene: Phaser.Scene, key: string, w: number, h: number, draw: (ctx: Ctx) => void, res = RES): string {
  if (scene.textures.exists(key)) scene.textures.remove(key)
  const tex = scene.textures.createCanvas(key, Math.ceil(w * res), Math.ceil(h * res))
  if (!tex) throw new Error(`could not create texture ${key}`)
  const ctx = tex.getContext()
  ctx.scale(res, res)
  draw(ctx)
  tex.refresh()
  return key
}

/** An image of a painted texture, at world scale. */
export function image(scene: Phaser.Scene, x: number, y: number, key: string, res = RES): Phaser.GameObjects.Image {
  return scene.add.image(x, y, key).setScale(1 / res)
}

export function rr(ctx: Ctx, x: number, y: number, w: number, h: number, r: number): void {
  const rad = Math.min(r, w / 2, h / 2)
  ctx.beginPath()
  ctx.moveTo(x + rad, y)
  ctx.arcTo(x + w, y, x + w, y + h, rad)
  ctx.arcTo(x + w, y + h, x, y + h, rad)
  ctx.arcTo(x, y + h, x, y, rad)
  ctx.arcTo(x, y, x + w, y, rad)
  ctx.closePath()
}

export function vgrad(ctx: Ctx, y0: number, y1: number, stops: [number, string][]): CanvasGradient {
  const g = ctx.createLinearGradient(0, y0, 0, y1)
  for (const [at, c] of stops) g.addColorStop(at, c)
  return g
}

export function hgrad(ctx: Ctx, x0: number, x1: number, stops: [number, string][]): CanvasGradient {
  const g = ctx.createLinearGradient(x0, 0, x1, 0)
  for (const [at, c] of stops) g.addColorStop(at, c)
  return g
}

export function radial(ctx: Ctx, x: number, y: number, r: number, stops: [number, string][]): CanvasGradient {
  const g = ctx.createRadialGradient(x, y, 0, x, y, r)
  for (const [at, c] of stops) g.addColorStop(at, c)
  return g
}

/** Run `draw` with a soft drop shadow. */
export function shadowed(ctx: Ctx, blur: number, dy: number, color: string, draw: () => void): void {
  ctx.save()
  ctx.shadowColor = color
  ctx.shadowBlur = blur
  ctx.shadowOffsetY = dy
  draw()
  ctx.restore()
}

/** Run `draw` with a coloured glow around it. */
export function glowing(ctx: Ctx, blur: number, color: string, draw: () => void): void {
  shadowed(ctx, blur, 0, color, draw)
}

/** A soft round light: a radial gradient texture, for additive light pools and glows. */
export function lightTexture(scene: Phaser.Scene, key: string, color: string, size = 256): string {
  return paint(
    scene,
    key,
    size,
    size,
    (ctx) => {
      ctx.fillStyle = radial(ctx, size / 2, size / 2, size / 2, [
        [0, color],
        [1, 'rgba(0,0,0,0)'],
      ])
      ctx.fillRect(0, 0, size, size)
    },
    1,
  )
}

/** `#rrggbb` + alpha → rgba() */
export function rgba(hex: string, a: number): string {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`
}

export function hexNum(hex: string): number {
  return parseInt(hex.slice(1), 16)
}

export const FONT = '-apple-system, "SF Pro Display", "Segoe UI", Roboto, Inter, "Helvetica Neue", Arial, sans-serif'
