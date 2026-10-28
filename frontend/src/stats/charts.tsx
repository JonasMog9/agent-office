// Small hand-made SVG charts: 30 days of recovery bars (coloured by zone, always with the
// zone named in words), fitness vs. fatigue lines, and the paper strategies' running P/L.
// All have a hover tooltip.

import { useState } from 'react'
import { SERIES, STRATEGY_COLOR, type Day, type Strategy } from './data'
import { spread, totalAt } from './pnl'

const H = 250
const PAD = { l: 34, r: 96, t: 14, b: 26 }
const STATUS = { green: '#0ca30c', yellow: '#fab219', red: '#d03b3b' } as const
const ZONE = { green: 'Green', yellow: 'Yellow', red: 'Red' } as const

const short = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

function Tip({ x, y, lines, W }: { x: number; y: number; lines: string[]; W: number }) {
  const w = Math.max(...lines.map((l) => l.length)) * 6.6 + 16
  const h = lines.length * 16 + 10
  const tx = Math.min(Math.max(x - w / 2, 2), W - w - 2)
  const ty = Math.max(y - h - 10, 2)
  return (
    <g className="tip" pointerEvents="none">
      <rect x={tx} y={ty} width={w} height={h} rx={8} />
      {lines.map((l, i) => (
        <text key={i} x={tx + 8} y={ty + 18 + i * 16} className={i === 0 ? 'tip-title' : ''}>
          {l}
        </text>
      ))}
    </g>
  )
}

export function RecoveryBars({ days, W }: { days: Day[]; W: number }) {
  const [hover, setHover] = useState<number | null>(null)
  const iw = W - PAD.l - PAD.r
  const ih = H - PAD.t - PAD.b
  const step = iw / days.length
  const bw = Math.max(4, step - 2) // a 2px gap between bars
  const y = (v: number) => PAD.t + ih - (v / 100) * ih
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Recovery, last 30 days">
      {[0, 34, 67, 100].map((v) => (
        <g key={v}>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} className={v === 0 ? 'axis' : 'grid'} />
          <text x={PAD.l - 6} y={y(v) + 4} className="tick" textAnchor="end">
            {v}
          </text>
        </g>
      ))}
      <text x={W - PAD.r + 6} y={y(83) + 4} className="zone">green</text>
      <text x={W - PAD.r + 6} y={y(50) + 4} className="zone">yellow</text>
      <text x={W - PAD.r + 6} y={y(17) + 4} className="zone">red</text>
      {days.map((d, i) => {
        const x = PAD.l + i * step + (step - bw) / 2
        if (d.recovery === null)
          return <rect key={d.day} x={x} y={y(0) - 2} width={bw} height={2} className="nodata" />
        const top = y(d.recovery)
        const h = y(0) - top
        const r = Math.min(4, bw / 2, h)
        // rounded at the data end, square on the baseline
        const path = `M${x},${y(0)} V${top + r} Q${x},${top} ${x + r},${top} H${x + bw - r} Q${x + bw},${top} ${x + bw},${top + r} V${y(0)} Z`
        return <path key={d.day} d={path} fill={STATUS[d.label ?? 'yellow']} opacity={hover === null || hover === i ? 1 : 0.45} />
      })}
      {days.map((d, i) =>
        i % (W < 800 ? 7 : 5) === (W < 800 ? 1 : 4) || i === days.length - 1 ? (
          <text key={d.day} x={PAD.l + i * step + step / 2} y={H - 8} className="tick" textAnchor="middle">
            {short(d.day)}
          </text>
        ) : null,
      )}
      {days.map((d, i) => (
        <rect
          key={d.day}
          x={PAD.l + i * step}
          y={PAD.t}
          width={step}
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
          x={PAD.l + hover * step + step / 2}
          y={days[hover].recovery === null ? y(0) : y(days[hover].recovery!)}
          lines={
            days[hover].recovery === null
              ? [short(days[hover].day), 'No data (watch off)']
              : [
                  short(days[hover].day),
                  `Recovery ${days[hover].recovery}% · ${ZONE[days[hover].label ?? 'yellow']}`,
                  ...(days[hover].strain !== null ? [`Strain ${days[hover].strain}`] : []),
                ]
          }
        />
      )}
    </svg>
  )
}

export function LoadLines({ days, W }: { days: Day[]; W: number }) {
  const [hover, setHover] = useState<number | null>(null)
  const iw = W - PAD.l - PAD.r
  const ih = H - PAD.t - PAD.b
  const vals = days.flatMap((d) => [d.fitness, d.fatigue]).filter((v): v is number => v !== null)
  const max = Math.max(10, Math.ceil((Math.max(...vals, 0) * 1.15) / 10) * 10)
  const step = iw / Math.max(1, days.length - 1)
  const x = (i: number) => PAD.l + i * step
  const y = (v: number) => PAD.t + ih - (v / max) * ih
  const line = (k: 'fitness' | 'fatigue') =>
    days
      .map((d, i) => (d[k] === null ? null : `${x(i)},${y(d[k]!)}`))
      .reduce<string[]>((segs, p, i, all) => {
        if (p === null) return segs
        segs.push(`${i === 0 || all[i - 1] === null ? 'M' : 'L'}${p}`)
        return segs
      }, [])
      .join(' ')
  const last = (k: 'fitness' | 'fatigue') => {
    for (let i = days.length - 1; i >= 0; i--) if (days[i][k] !== null) return i
    return -1
  }
  const ticks = [0, max / 2, max]
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Fitness and fatigue, last 30 days">
      {ticks.map((v) => (
        <g key={v}>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} className={v === 0 ? 'axis' : 'grid'} />
          <text x={PAD.l - 6} y={y(v) + 4} className="tick" textAnchor="end">
            {Math.round(v)}
          </text>
        </g>
      ))}
      {(['fatigue', 'fitness'] as const).map((k) => {
        const i = last(k)
        return (
          <g key={k}>
            <path d={line(k)} fill="none" stroke={SERIES[k]} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
            {i >= 0 && (
              <>
                <circle cx={x(i)} cy={y(days[i][k]!)} r={4} fill={SERIES[k]} className="ringed" />
                <text x={x(i) + 9} y={y(days[i][k]!) + 4} className="end-label">
                  {k === 'fitness' ? 'Fitness' : 'Fatigue'} {days[i][k]}
                </text>
              </>
            )}
          </g>
        )
      })}
      {days.map((d, i) =>
        i % (W < 800 ? 7 : 5) === (W < 800 ? 1 : 4) || i === days.length - 1 ? (
          <text key={d.day} x={x(i)} y={H - 8} className="tick" textAnchor="middle">
            {short(d.day)}
          </text>
        ) : null,
      )}
      {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={PAD.t} y2={PAD.t + ih} className="crosshair" />}
      {hover !== null &&
        (['fitness', 'fatigue'] as const).map((k) =>
          days[hover][k] === null ? null : (
            <circle key={k} cx={x(hover)} cy={y(days[hover][k]!)} r={4.5} fill={SERIES[k]} className="ringed" />
          ),
        )}
      <rect
        x={PAD.l - step / 2}
        y={PAD.t}
        width={iw + step}
        height={ih}
        fill="transparent"
        onMouseMove={(e) => {
          const box = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect()
          const sx = ((e.clientX - box.left) / box.width) * W
          setHover(Math.max(0, Math.min(days.length - 1, Math.round((sx - PAD.l) / step))))
        }}
        onTouchMove={(e) => {
          const box = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect()
          const sx = ((e.touches[0].clientX - box.left) / box.width) * W
          setHover(Math.max(0, Math.min(days.length - 1, Math.round((sx - PAD.l) / step))))
        }}
        onMouseLeave={() => setHover(null)}
      />
      {hover !== null && (
        <Tip
          W={W}
          x={x(hover)}
          y={PAD.t + 20}
          lines={[
            short(days[hover].day),
            `Fitness ${days[hover].fitness ?? '–'}`,
            `Fatigue ${days[hover].fatigue ?? '–'}`,
          ]}
        />
      )}
    </svg>
  )
}

const signed = (x: number) => `${x >= 0 ? '+' : '−'}$${Math.abs(x).toFixed(2)}`

const PNL_PAD = { l: 44, r: 132, t: 16, b: 26 }

export function PnlLines({ strategies, start, end, W }: { strategies: Strategy[]; start: number; end: number; W: number }) {
  const [hover, setHover] = useState<number | null>(null) // a time
  const P = PNL_PAD
  const iw = W - P.l - P.r
  const ih = H - P.t - P.b
  const vals = strategies.flatMap((s) => s.curve.map((p) => p.pnl_usd))
  const top = Math.max(5, ...vals)
  const bottom = Math.min(0, ...vals)
  const span = top - bottom
  const step = span > 60 ? 20 : span > 24 ? 10 : 5
  const hi = Math.ceil((top + span * 0.08) / step) * step
  const lo = Math.floor((bottom - (bottom < 0 ? span * 0.08 : 0)) / step) * step
  const t0 = Math.min(start, end - 86_400_000)
  const x = (t: number) => P.l + ((t - t0) / (end - t0)) * iw
  const y = (v: number) => P.t + ih - ((v - lo) / (hi - lo)) * ih
  const ticks: number[] = []
  for (let v = lo; v <= hi + 1e-9; v += step) ticks.push(v)
  const path = (s: Strategy) => {
    let d = `M${x(t0)},${y(0)}`
    let v = 0
    for (const p of s.curve) {
      const px = x(Math.max(t0, Date.parse(p.at)))
      d += ` H${px} V${y(p.pnl_usd)}`
      v = p.pnl_usd
    }
    return d + ` H${x(end)} V${y(v)}`
  }
  const finals = strategies.map((s) => s.curve.at(-1)?.pnl_usd ?? 0)
  const labelY = spread(finals.map((v) => y(v) + 4), 15, P.t + 8, P.t + ih)
  const days = Math.max(1, Math.round((end - t0) / 86_400_000))
  const every = days > 20 ? 7 : days > 8 ? 3 : 1
  const dayTicks: number[] = []
  for (let d = 0; d <= days; d += every) dayTicks.push(t0 + d * 86_400_000)
  const fromEvent = (clientX: number, el: SVGRectElement) => {
    const box = (el.ownerSVGElement as SVGSVGElement).getBoundingClientRect()
    const sx = ((clientX - box.left) / box.width) * W
    setHover(Math.max(t0, Math.min(end, t0 + ((sx - P.l) / iw) * (end - t0))))
  }
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Paper trading profit and loss by strategy">
      {ticks.map((v) => (
        <g key={v}>
          <line x1={P.l} x2={W - P.r} y1={y(v)} y2={y(v)} className={v === 0 ? 'axis' : 'grid'} />
          <text x={P.l - 6} y={y(v) + 4} className="tick" textAnchor="end">
            {v === 0 ? '$0' : `${v > 0 ? '+' : '−'}$${Math.abs(v)}`}
          </text>
        </g>
      ))}
      {dayTicks.map((t) => (
        <text key={t} x={x(t)} y={H - 8} className="tick" textAnchor="middle">
          {short(new Date(t).toISOString().slice(0, 10))}
        </text>
      ))}
      {strategies.map((s) => (
        <path key={s.key} d={path(s)} fill="none" stroke={STRATEGY_COLOR[s.key]} strokeWidth={2} strokeLinejoin="round" />
      ))}
      {strategies.map((s, i) => (
        <g key={s.key}>
          <circle cx={x(end)} cy={y(finals[i])} r={4} fill={STRATEGY_COLOR[s.key]} className="ringed" />
          <text x={x(end) + 10} y={labelY[i]} className="end-label">
            {s.name} {signed(finals[i])}
          </text>
        </g>
      ))}
      {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={P.t} y2={P.t + ih} className="crosshair" />}
      {hover !== null &&
        strategies.map((s) => (
          <circle key={s.key} cx={x(hover)} cy={y(totalAt(s.curve, hover))} r={4.5} fill={STRATEGY_COLOR[s.key]} className="ringed" />
        ))}
      <rect
        x={P.l}
        y={P.t}
        width={iw}
        height={ih}
        fill="transparent"
        onMouseMove={(e) => fromEvent(e.clientX, e.currentTarget)}
        onTouchMove={(e) => fromEvent(e.touches[0].clientX, e.currentTarget)}
        onTouchStart={(e) => fromEvent(e.touches[0].clientX, e.currentTarget)}
        onMouseLeave={() => setHover(null)}
      />
      {hover !== null && (
        <Tip
          W={W}
          x={x(hover)}
          y={P.t + 20}
          lines={[
            new Date(hover).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: 'numeric' }),
            ...strategies.map((s) => `${s.name} ${signed(totalAt(s.curve, hover))}`),
          ]}
        />
      )}
    </svg>
  )
}
