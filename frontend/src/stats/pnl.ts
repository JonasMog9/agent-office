// Helpers for the paper-trading P/L chart (pure, so they're unit tested).

import type { Strategy } from './data'

/** A strategy's running total at time t: the last step at or before it (0 before any close). */
export function totalAt(curve: Strategy['curve'], t: number): number {
  let v = 0
  for (const p of curve) if (Date.parse(p.at) <= t) v = p.pnl_usd
  return v
}

/** Spread end labels so none sit closer than `gap` (keeps the order, nudges as needed). */
export function spread(ys: number[], gap: number, lo: number, hi: number): number[] {
  const order = ys.map((y, i) => [y, i] as const).sort((a, b) => a[0] - b[0])
  const out = new Array<number>(ys.length)
  let prev = -Infinity
  for (const [y, i] of order) prev = out[i] = Math.max(y, prev + gap)
  const over = Math.max(...out) - hi
  if (over > 0) for (let i = 0; i < out.length; i++) out[i] -= over
  return out.map((y) => Math.max(lo, y))
}
