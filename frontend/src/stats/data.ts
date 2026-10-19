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

export interface Alert {
  symbol: string
  chain: string
  alerted_at: string
  fdv_usd: number | null
  volume_h24_usd: number | null
  status: 'open' | 'closed' | null
  exit_reason: string | null
  now_x: number | null
  peak_x: number | null
  pnl_usd: number | null
}

export interface Stats {
  health: Day[]
  scout: {
    scans_30d: number
    alerts: Alert[]
    paper: { closed: number; open: number; wins: number; win_rate_pct: number | null; total_pnl_usd: number; return_pct: number | null }
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
  return {
    health,
    scout: {
      scans_30d: 4211,
      alerts: [
        { symbol: 'DEMO3', chain: 'base', alerted_at: ago(1), fdv_usd: 2.1e6, volume_h24_usd: 1.4e6, status: 'open', exit_reason: null, now_x: 0.93, peak_x: 1.12, pnl_usd: null },
        { symbol: 'DEMO2', chain: 'solana', alerted_at: ago(6), fdv_usd: 9.7e6, volume_h24_usd: 6.1e6, status: 'closed', exit_reason: 'stop_loss', now_x: 0.47, peak_x: 1.31, pnl_usd: -5.48 },
        { symbol: 'DEMO1', chain: 'solana', alerted_at: ago(12), fdv_usd: 4.2e6, volume_h24_usd: 3.3e6, status: 'closed', exit_reason: 'take_profit', now_x: 2.1, peak_x: 2.6, pnl_usd: 10.17 },
      ],
      paper: { closed: 2, open: 1, wins: 1, win_rate_pct: 50, total_pnl_usd: 4.69, return_pct: 23.5 },
    },
  }
}
