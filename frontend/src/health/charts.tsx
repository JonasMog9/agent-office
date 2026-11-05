// The health page's charts, hand-made SVG like the stats page: time-series lines (with an
// optional range band), weekly bars, an activity calendar and stacked sleep bars. Every one
// has a hover tooltip; text stays in text colours, and colour is never the only label.

import { useState } from 'react'
import { Tip } from '../stats/charts'
import { BLUE, SLEEP_STAGE, ZONE_RAMP, hm, shortDay, type Night, type Week } from './data'

const H = 220

export interface Series {
  key: string
  label: string
  color: string
  values: (number | null)[]
}

function niceStep(span: number, ticks = 4): number {
  const raw = span / ticks
  const mag = 10 ** Math.floor(Math.log10(raw || 1))
  return [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag
}

/** Several lines over the same days, one y axis. Nulls are gaps. */
export function TimeLines({
  days,
  series,
  W,
  format,
  band,
  zero = false,
  height = H,
  endLabels = true,
  connect = false,
}: {
  days: string[]
  series: Series[]
  W: number
  format: (v: number) => string
  band?: { low: (number | null)[]; high: (number | null)[]; color: string }
  zero?: boolean
  height?: number
  endLabels?: boolean
  /** Join the points across gaps (for sparse series, like cadence on run days). */
  connect?: boolean
}) {
  const [hover, setHover] = useState<number | null>(null)
  const P = { l: 52, r: endLabels ? 118 : 14, t: 12, b: 24 }
  const iw = W - P.l - P.r
  const ih = height - P.t - P.b
  const all = [...series.flatMap((s) => s.values), ...(band ? [...band.low, ...band.high] : [])].filter(
    (v): v is number => v !== null,
  )
  if (!all.length) return <p className="muted">No data yet.</p>
  let lo = Math.min(...all, ...(zero ? [0] : []))
  let hi = Math.max(...all, ...(zero ? [0] : []))
  if (hi === lo) [lo, hi] = [lo - 1, hi + 1]
  const step = niceStep(hi - lo)
  lo = Math.floor(lo / step) * step
  hi = Math.ceil(hi / step) * step
  const n = days.length
  const x = (i: number) => P.l + (n === 1 ? iw / 2 : (i / (n - 1)) * iw)
  const y = (v: number) => P.t + ih - ((v - lo) / (hi - lo)) * ih
  const ticks: number[] = []
  const seen = new Set<string>()
  for (let v = lo; v <= hi + step / 2; v += step) {
    const t = Math.round(v * 1000) / 1000
    if (!seen.has(format(t))) ticks.push(t) // integer formats can round two ticks alike
    seen.add(format(t))
  }
  const path = (vals: (number | null)[]) => {
    let pen = false
    return vals
      .map((v, i) => {
        if (v === null) {
          if (!connect) pen = false
          return null
        }
        const cmd = pen ? 'L' : 'M'
        pen = true
        return `${cmd}${x(i)},${y(v)}`
      })
      .filter(Boolean)
      .join(' ')
  }
  const bandPath = band
    ? (() => {
        const idx = band.low.map((v, i) => (v !== null && band.high[i] !== null ? i : -1)).filter((i) => i >= 0)
        if (!idx.length) return ''
        const top = idx.map((i, k) => `${k ? 'L' : 'M'}${x(i)},${y(band.high[i]!)}`).join(' ')
        const bottom = [...idx].reverse().map((i) => `L${x(i)},${y(band.low[i]!)}`).join(' ')
        return `${top} ${bottom} Z`
      })()
    : ''
  const lastIdx = (vals: (number | null)[]) => {
    for (let i = vals.length - 1; i >= 0; i--) if (vals[i] !== null) return i
    return -1
  }
  const labels = series
    .map((s) => ({ s, i: lastIdx(s.values) }))
    .filter((e) => e.i >= 0)
    .map((e) => ({ ...e, y: y(e.s.values[e.i]!) + 4 }))
    .sort((a, b) => a.y - b.y)
  for (let k = 1; k < labels.length; k++) labels[k].y = Math.max(labels[k].y, labels[k - 1].y + 14)
  const every = Math.max(1, Math.ceil(n / (W < 700 ? 4 : 7)))
  const pick = (clientX: number, el: SVGRectElement) => {
    const box = (el.ownerSVGElement as SVGSVGElement).getBoundingClientRect()
    const sx = ((clientX - box.left) / box.width) * W
    setHover(Math.max(0, Math.min(n - 1, Math.round(((sx - P.l) / iw) * (n - 1)))))
  }
  return (
    <svg viewBox={`0 0 ${W} ${height}`} className="chart" role="img" aria-label={series.map((s) => s.label).join(', ')}>
      {ticks.map((v) => (
        <g key={v}>
          <line x1={P.l} x2={W - P.r} y1={y(v)} y2={y(v)} className={v === 0 && zero ? 'axis' : 'grid'} />
          <text x={P.l - 6} y={y(v) + 4} className="tick" textAnchor="end">
            {format(v)}
          </text>
        </g>
      ))}
      {days.map((d, i) =>
        (i % every === 0 && n - 1 - i >= every / 2) || i === n - 1 ? (
          <text key={d} x={x(i)} y={height - 7} className="tick" textAnchor="middle">
            {shortDay(d)}
          </text>
        ) : null,
      )}
      {band && <path d={bandPath} fill={band.color} opacity={0.18} />}
      {series.map((s) => (
        <path key={s.key} d={path(s.values)} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      ))}
      {endLabels &&
        labels.map(({ s, i, y: ly }) => (
          <g key={s.key}>
            <circle cx={x(i)} cy={y(s.values[i]!)} r={4} fill={s.color} className="ringed" />
            <text x={x(n - 1) + 10} y={ly} className="end-label">
              {s.label} {format(s.values[i]!)}
            </text>
          </g>
        ))}
      {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={P.t} y2={P.t + ih} className="crosshair" />}
      {hover !== null &&
        series.map((s) =>
          s.values[hover] === null ? null : (
            <circle key={s.key} cx={x(hover)} cy={y(s.values[hover]!)} r={4.5} fill={s.color} className="ringed" />
          ),
        )}
      <rect
        x={P.l - 4}
        y={P.t}
        width={iw + 8}
        height={ih}
        fill="transparent"
        onMouseMove={(e) => pick(e.clientX, e.currentTarget)}
        onTouchStart={(e) => pick(e.touches[0].clientX, e.currentTarget)}
        onTouchMove={(e) => pick(e.touches[0].clientX, e.currentTarget)}
        onMouseLeave={() => setHover(null)}
      />
      {hover !== null && (
        <Tip
          W={W}
          x={x(hover)}
          y={P.t + 22}
          lines={[
            shortDay(days[hover]),
            ...series.map((s) => `${s.label}: ${s.values[hover] === null ? 'no data' : format(s.values[hover]!)}`),
            ...(band && band.low[hover] !== null ? [`Range ${format(band.low[hover]!)}–${format(band.high[hover]!)}`] : []),
          ]}
        />
      )}
    </svg>
  )
}

/** Km per week, Monday to Sunday. */
export function WeeklyBars({ weeks, W }: { weeks: Week[]; W: number }) {
  const [hover, setHover] = useState<number | null>(null)
  const P = { l: 40, r: 10, t: 12, b: 24 }
  const iw = W - P.l - P.r
  const ih = H - P.t - P.b
  const max = Math.max(10, ...weeks.map((w) => w.km))
  const step = niceStep(max)
  const top = Math.ceil(max / step) * step
  const y = (v: number) => P.t + ih - (v / top) * ih
  const slot = iw / weeks.length
  const bw = Math.max(3, slot - 2)
  const ticks = Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step)
  const every = W < 700 ? 13 : 8
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Running km per week">
      {ticks.map((v) => (
        <g key={v}>
          <line x1={P.l} x2={W - P.r} y1={y(v)} y2={y(v)} className={v === 0 ? 'axis' : 'grid'} />
          <text x={P.l - 6} y={y(v) + 4} className="tick" textAnchor="end">
            {v}
          </text>
        </g>
      ))}
      {weeks.map((w, i) => {
        const bx = P.l + i * slot + (slot - bw) / 2
        const h = y(0) - y(w.km)
        if (h <= 0) return null
        const r = Math.min(3, bw / 2, h)
        const t = y(w.km)
        const d = `M${bx},${y(0)} V${t + r} Q${bx},${t} ${bx + r},${t} H${bx + bw - r} Q${bx + bw},${t} ${bx + bw},${t + r} V${y(0)} Z`
        return <path key={w.week} d={d} fill={BLUE} opacity={hover === null || hover === i ? 1 : 0.45} />
      })}
      {weeks.map((w, i) =>
        i % every === weeks.length % every || i === weeks.length - 1 ? (
          <text key={w.week} x={P.l + i * slot + slot / 2} y={H - 7} className="tick" textAnchor="middle">
            {shortDay(w.week)}
          </text>
        ) : null,
      )}
      {weeks.map((w, i) => (
        <rect
          key={w.week}
          x={P.l + i * slot}
          y={P.t}
          width={slot}
          height={ih}
          fill="transparent"
          onMouseEnter={() => setHover(i)}
          onMouseLeave={() => setHover(null)}
          onTouchStart={() => setHover(i)}
        />
      ))}
      {hover !== null && (
        <Tip
          W={W}
          x={P.l + hover * slot + slot / 2}
          y={y(weeks[hover].km)}
          lines={[
            `Week of ${shortDay(weeks[hover].week)}`,
            `${weeks[hover].km} km · ${weeks[hover].runs} run${weeks[hover].runs === 1 ? '' : 's'}`,
            `${hm(weeks[hover].minutes)} · ${weeks[hover].climb_m} m climb`,
          ]}
        />
      )}
    </svg>
  )
}

const CAL_BUCKETS = [0, 5, 10, 15, 20] // km thresholds for the five shades

function calendarShade(km: number): string | null {
  if (km <= 0) return null
  let i = 0
  while (i < CAL_BUCKETS.length - 1 && km >= CAL_BUCKETS[i + 1]) i++
  return ZONE_RAMP[i]
}

/** The last 12 weeks as a grid: a column per week, a row per weekday (Mon at top). */
export function Calendar({ days }: { days: { day: string; km: number }[] }) {
  const [hover, setHover] = useState<number | null>(null)
  const cell = 15
  const gap = 3
  const first = new Date(`${days[0].day}T12:00:00`)
  const offset = (first.getDay() + 6) % 7 // Monday = 0
  const cols = Math.ceil((days.length + offset) / 7)
  const W = 34 + cols * (cell + gap)
  const Hc = 7 * (cell + gap) + 22
  const names = ['Mon', '', 'Wed', '', 'Fri', '', 'Sun']
  return (
    <svg viewBox={`0 0 ${W} ${Hc}`} className="chart calendar" role="img" aria-label="Running km per day, last 12 weeks">
      {names.map((n, r) =>
        n ? (
          <text key={r} x={0} y={14 + r * (cell + gap) + 11} className="tick">
            {n}
          </text>
        ) : null,
      )}
      {days.map((d, i) => {
        const k = i + offset
        const cx = 34 + Math.floor(k / 7) * (cell + gap)
        const cy = 14 + (k % 7) * (cell + gap)
        const shade = calendarShade(d.km)
        return (
          <g key={d.day} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onTouchStart={() => setHover(i)}>
            <rect x={cx} y={cy} width={cell} height={cell} rx={3} fill={shade ?? 'rgba(150,170,230,.10)'} />
            {(i === 0 || new Date(`${d.day}T12:00:00`).getDate() === 1) && (
              <text x={cx} y={9} className="tick">
                {new Date(`${d.day}T12:00:00`).toLocaleDateString(undefined, { month: 'short' })}
              </text>
            )}
          </g>
        )
      })}
      {hover !== null && (
        <Tip
          W={W}
          x={34 + Math.floor((hover + offset) / 7) * (cell + gap) + cell / 2}
          y={14 + ((hover + offset) % 7) * (cell + gap)}
          lines={[shortDay(days[hover].day), days[hover].km ? `${days[hover].km} km` : 'Rest day']}
        />
      )}
    </svg>
  )
}

const STAGES = [
  { key: 'deep_min', label: 'Deep', color: SLEEP_STAGE.deep },
  { key: 'core_min', label: 'Core', color: SLEEP_STAGE.core },
  { key: 'rem_min', label: 'REM', color: SLEEP_STAGE.rem },
  { key: 'awake_min', label: 'Awake', color: SLEEP_STAGE.awake },
] as const

/** Hours asleep per night, split into stages when the watch recorded them. */
export function SleepBars({ nights, W }: { nights: Night[]; W: number }) {
  const [hover, setHover] = useState<number | null>(null)
  const P = { l: 40, r: 10, t: 12, b: 24 }
  const iw = W - P.l - P.r
  const ih = H - P.t - P.b
  const total = (n: Night) =>
    n.deep_min !== null ? STAGES.reduce((s, st) => s + (n[st.key] ?? 0), 0) : (n.asleep_min ?? 0) + (n.awake_min ?? 0)
  const maxH = Math.max(8, ...nights.map((n) => total(n) / 60))
  const top = Math.ceil(maxH / 2) * 2
  const y = (h: number) => P.t + ih - (h / top) * ih
  const slot = iw / nights.length
  const bw = Math.max(4, slot - 3)
  const ticks = Array.from({ length: top / 2 + 1 }, (_, i) => i * 2)
  const every = W < 700 ? 7 : 5
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Sleep per night">
      {ticks.map((v) => (
        <g key={v}>
          <line x1={P.l} x2={W - P.r} y1={y(v)} y2={y(v)} className={v === 0 ? 'axis' : 'grid'} />
          <text x={P.l - 6} y={y(v) + 4} className="tick" textAnchor="end">
            {v} h
          </text>
        </g>
      ))}
      {nights.map((n, i) => {
        const bx = P.l + i * slot + (slot - bw) / 2
        const op = hover === null || hover === i ? 1 : 0.45
        if (n.deep_min === null) {
          if (!n.asleep_min) return <rect key={n.day} x={bx} y={y(0) - 2} width={bw} height={2} className="nodata" />
          return <rect key={n.day} x={bx} y={y(n.asleep_min / 60)} width={bw} height={y(0) - y(n.asleep_min / 60)} rx={2} fill={SLEEP_STAGE.core} opacity={op} />
        }
        let acc = 0
        return (
          <g key={n.day} opacity={op}>
            {STAGES.map((st) => {
              const h = (n[st.key] ?? 0) / 60
              const yTop = y(acc + h)
              const rect = <rect key={st.key} x={bx} y={yTop} width={bw} height={Math.max(0, y(acc) - yTop - 1)} fill={st.color} />
              acc += h
              return rect
            })}
          </g>
        )
      })}
      {nights.map((n, i) =>
        i % every === (nights.length - 1) % every ? (
          <text key={n.day} x={P.l + i * slot + slot / 2} y={H - 7} className="tick" textAnchor="middle">
            {shortDay(n.day)}
          </text>
        ) : null,
      )}
      {nights.map((n, i) => (
        <rect key={n.day} x={P.l + i * slot} y={P.t} width={slot} height={ih} fill="transparent" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onTouchStart={() => setHover(i)} />
      ))}
      {hover !== null && (
        <Tip
          W={W}
          x={P.l + hover * slot + slot / 2}
          y={y(total(nights[hover]) / 60)}
          lines={[
            `Night before ${shortDay(nights[hover].day)}`,
            `Asleep ${hm(nights[hover].asleep_min)}`,
            ...(nights[hover].deep_min !== null
              ? STAGES.map((st) => `${st.label} ${hm(nights[hover][st.key])}`)
              : []),
            ...(nights[hover].performance_pct !== null ? [`${nights[hover].performance_pct}% of need`] : []),
          ]}
        />
      )}
    </svg>
  )
}
