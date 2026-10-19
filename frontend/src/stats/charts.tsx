// Two small hand-made SVG charts: 30 days of recovery bars (coloured by zone, always with the
// zone named in words), and fitness vs. fatigue lines. Both have a hover tooltip.

import { useState } from 'react'
import { SERIES, type Day } from './data'

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
