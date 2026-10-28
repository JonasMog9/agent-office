// The stats page's data: the backend's /stats (with the office key), or a made-up demo.

import { API_URL } from '../office/live'

/** The two training-load lines (validated as a pair on the dark card surface). */
export const SERIES = { fitness: '#3987e5', fatigue: '#d95926' } as const

/** Chart width in SVG units: narrower on phones so the text stays readable once scaled. */
export const chartWidth = (narrow: boolean) => (narrow ? 560 : 1040)

export interface Day {
  day: string
  recovery: number | null
  label: 'green' | 'yellow' | 'red' | null
  strain: number | null
  sleep_pct: number | null
  fitness: number | null
  fatigue: number | null
}

/** The three paper-trading strategies (validated as a set on the dark card surface). */
export const STRATEGY_COLOR = { quick: '#199e70', runner: '#c98500', moon: '#9085e9' } as const
export type StrategyKey = keyof typeof STRATEGY_COLOR
export const STRATEGY_KEYS: StrategyKey[] = ['quick', 'runner', 'moon']

export interface PaperResult {
  status: 'open' | 'closed'
  exit_reason: string | null
  now_x: number | null
  sold_pct: number
  pnl_usd: number | null // closed
  pnl_now_usd: number | null // open: if sold now
}

export interface Alert {
  symbol: string
  chain: string
  alerted_at: string
  fdv_usd: number | null
  volume_h24_usd: number | null
  peak_x: number | null
  trades: Partial<Record<StrategyKey, PaperResult>>
}

export interface Summary {
  closed: number
  open: number
  wins: number
  win_rate_pct: number | null
  total_pnl_usd: number
  return_pct: number | null
  open_pnl_usd: number
}

export interface Strategy {
  key: StrategyKey
  name: string
  blurb: string
  summary: Summary
  curve: { at: string; pnl_usd: number }[] // running total of closed trades
}

export interface Stats {
  generated_at: string
  health: Day[]
  scout: {
    scans_30d: number
    alerts: Alert[]
    strategies: Strategy[]
  }
}

export async function fetchStats(key: string, api = API_URL): Promise<Stats | 'locked'> {
  const r = await fetch(new URL('/stats', api), { headers: { 'X-Office-Key': key } })
  if (r.status === 401) return 'locked'
  if (!r.ok) throw new Error(`stats: HTTP ${r.status}`)
  return r.json()
}

export function label(recovery: number): 'green' | 'yellow' | 'red' {
  return recovery >= 67 ? 'green' : recovery >= 34 ? 'yellow' : 'red'
}

/** Made-up numbers with the real shape, for the public page. Deterministic, so it doesn't jump. */
export function demoStats(end = new Date()): Stats {
  const health: Day[] = []
  let fitness = 28
  let fatigue = 30
  for (let i = 29; i >= 0; i--) {
    const d = new Date(end)
    d.setDate(d.getDate() - i)
    const k = 29 - i
    const missing = k === 11 || k === 12
    const rec = Math.round(58 + 22 * Math.sin(k * 0.7) + 9 * Math.cos(k * 1.9) - (k > 20 && k < 24 ? 30 : 0))
    const r = Math.max(8, Math.min(97, rec))
    const strain = Math.round((8 + 6 * Math.abs(Math.sin(k * 1.3))) * 10) / 10
    fitness += (strain * 4 - fitness) / 42
    fatigue += (strain * 4 - fatigue) / 7
    health.push({
      day: d.toISOString().slice(0, 10),
      recovery: missing ? null : r,
      label: missing ? null : label(r),
      strain: missing ? null : strain,
      sleep_pct: missing ? null : Math.round(70 + 20 * Math.sin(k * 0.5)),
      fitness: Math.round(fitness * 10) / 10,
      fatigue: Math.round(fatigue * 10) / 10,
    })
  }
  const ago = (days: number) => new Date(end.getTime() - days * 86_400_000).toISOString()
  const closed = (pnl: number, x: number, why: string): PaperResult => ({
    status: 'closed', exit_reason: why, now_x: x, sold_pct: 100, pnl_usd: pnl, pnl_now_usd: null,
  })
  const open = (x: number, sold: number, now: number): PaperResult => ({
    status: 'open', exit_reason: null, now_x: x, sold_pct: sold, pnl_usd: null, pnl_now_usd: now,
  })
  const sum = (s: Partial<Summary>): Summary => ({
    closed: 0, open: 0, wins: 0, win_rate_pct: null, total_pnl_usd: 0, return_pct: null, open_pnl_usd: 0, ...s,
  })
  return {
    generated_at: end.toISOString(),
    health,
    scout: {
      scans_30d: 4211,
      alerts: [
        {
          symbol: 'DEMO4', chain: 'base', alerted_at: ago(1), fdv_usd: 2.1e6, volume_h24_usd: 1.4e6, peak_x: 1.12,
          trades: { quick: open(0.93, 0, -0.95), runner: open(0.93, 0, -0.95), moon: open(0.93, 0, -0.95) },
        },
        {
          symbol: 'DEMO3', chain: 'solana', alerted_at: ago(5), fdv_usd: 3.8e6, volume_h24_usd: 4.4e6, peak_x: 7.9,
          trades: {
            quick: closed(10.17, 2.1, 'take_profit'),
            runner: closed(42.2, 5.4, 'trailing_stop'),
            moon: open(4.6, 75, 31.06),
          },
        },
        {
          symbol: 'DEMO2', chain: 'solana', alerted_at: ago(9), fdv_usd: 9.7e6, volume_h24_usd: 6.1e6, peak_x: 1.31,
          trades: {
            quick: closed(-5.48, 0.47, 'stop_loss'),
            runner: closed(-5.48, 0.47, 'stop_loss'),
            moon: closed(-5.48, 0.47, 'stop_loss'),
          },
        },
        {
          symbol: 'DEMO1', chain: 'solana', alerted_at: ago(14), fdv_usd: 4.2e6, volume_h24_usd: 3.3e6, peak_x: 2.6,
          trades: {
            quick: closed(10.17, 2.1, 'take_profit'),
            runner: closed(7.27, 1.82, 'trailing_stop'),
            moon: closed(5.27, 1.3, 'trailing_stop'),
          },
        },
      ],
      strategies: [
        {
          key: 'quick', name: 'Quick 2×', blurb: 'Sell everything at 2×. Stop at −50%, sell after 3 days.',
          summary: sum({ closed: 3, open: 1, wins: 2, win_rate_pct: 67, total_pnl_usd: 14.86, return_pct: 49.5, open_pnl_usd: -0.95 }),
          curve: [{ at: ago(13), pnl_usd: 10.17 }, { at: ago(8.6), pnl_usd: 4.69 }, { at: ago(4.8), pnl_usd: 14.86 }],
        },
        {
          key: 'runner', name: 'Runner',
          blurb: 'No fixed target: once it hits 2×, sell when it drops 30% from its peak. Stop at −50%, sell after 7 days.',
          summary: sum({ closed: 3, open: 1, wins: 2, win_rate_pct: 67, total_pnl_usd: 43.99, return_pct: 146.6, open_pnl_usd: -0.95 }),
          curve: [{ at: ago(12.5), pnl_usd: 7.27 }, { at: ago(8.6), pnl_usd: 1.79 }, { at: ago(3.9), pnl_usd: 43.99 }],
        },
        {
          key: 'moon', name: 'Moon bag',
          blurb: 'Sell half at 2× (stake back) and a quarter at 5×; the last quarter rides for 10× or more with a 50% trailing stop, up to 14 days.',
          summary: sum({ closed: 2, open: 2, wins: 1, win_rate_pct: 50, total_pnl_usd: -0.21, return_pct: -1.1, open_pnl_usd: 30.11 }),
          curve: [{ at: ago(11.8), pnl_usd: 5.27 }, { at: ago(8.6), pnl_usd: -0.21 }],
        },
      ],
    },
  }
}
