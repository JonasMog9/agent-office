import { useEffect, useState } from 'react'
import { viewKey } from '../office/live'
import { LoadLines, RecoveryBars } from './charts'
import { SERIES, chartWidth, demoStats, fetchStats, type Alert, type Stats as Data } from './data'

const usd = (x: number | null) =>
  x === null ? '–' : x >= 1e6 ? `$${(x / 1e6).toFixed(1)}M` : x >= 1e3 ? `$${Math.round(x / 1e3)}k` : `$${x.toFixed(0)}`
const money = (x: number | null) => (x === null ? '–' : `${x >= 0 ? '+' : '−'}$${Math.abs(x).toFixed(2)}`)
const ZONE = { green: 'Green', yellow: 'Yellow', red: 'Red' } as const
const REASON: Record<string, string> = {
  take_profit: 'sold at 2×',
  stop_loss: 'stopped out',
  liquidity_gone: 'liquidity vanished',
  time: '3 days up',
  no_price: 'no price',
}

function outcome(a: Alert): string {
  if (a.status === null) return 'no trade'
  if (a.status === 'open') return `open · ${a.now_x ?? '–'}×`
  return `${REASON[a.exit_reason ?? ''] ?? a.exit_reason} · ${money(a.pnl_usd)}`
}

export default function Stats() {
  // Without the office key the page shows made-up numbers, like the office's demo.
  const [key] = useState(viewKey)
  const [data, setData] = useState<Data | null>(() => (key ? null : demoStats()))
  const [demo, setDemo] = useState(!key)
  const [error, setError] = useState<string | null>(null)
  const [narrow, setNarrow] = useState(() => window.matchMedia('(max-width: 700px)').matches)

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 700px)')
    const on = () => setNarrow(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])

  useEffect(() => {
    if (!key) return
    fetchStats(key)
      .then((r) => {
        if (r === 'locked') {
          setDemo(true)
          setData(demoStats())
        } else setData(r)
      })
      .catch((e: Error) => setError(e.message))
  }, [key])

  if (error) return <main className="stats"><p className="muted">Couldn't load the stats: {error}</p></main>
  if (!data) return <main className="stats"><p className="muted">Loading…</p></main>

  const days = data.health
  const scored = days.filter((d) => d.recovery !== null)
  const latest = scored.at(-1)
  const avg = scored.length ? Math.round(scored.reduce((s, d) => s + d.recovery!, 0) / scored.length) : null
  const counts = { green: 0, yellow: 0, red: 0 }
  for (const d of scored) if (d.label) counts[d.label]++
  const p = data.scout.paper

  return (
    <main className="stats">
      <header className="top">
        <div className="brand">
          <span className="logo" aria-hidden>
            <i className="health_coach" />
            <i className="manager" />
            <i className="market_scout" />
          </span>
          <div>
            <h1>Stats</h1>
            <p className="tagline">The last 30 days, computed in Python, explained by the agents</p>
          </div>
        </div>
        <div className="actions">
          {demo && (
            <span className="pill demo">
              <b />
              Demo · made-up numbers
            </span>
          )}
          <a className="pill link" href="/">
            ← Office
          </a>
        </div>
      </header>

      <section className="tiles">
        <div className="tile">
          <span className="k">Latest recovery</span>
          <span className="v">
            {latest ? `${latest.recovery}%` : '–'}
            {latest?.label && <em className={`zone-chip ${latest.label}`}>{ZONE[latest.label]}</em>}
          </span>
          <span className="s">{latest ? new Date(`${latest.day}T12:00:00`).toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' }) : 'no data yet'}</span>
        </div>
        <div className="tile">
          <span className="k">30-day average</span>
          <span className="v">{avg === null ? '–' : `${avg}%`}</span>
          <span className="s">
            {counts.green} green · {counts.yellow} yellow · {counts.red} red · {30 - scored.length} no data
          </span>
        </div>
        <div className="tile">
          <span className="k">Scout alerts</span>
          <span className="v">{data.scout.alerts.length}</span>
          <span className="s">from {data.scout.scans_30d.toLocaleString()} scans in 30 days</span>
        </div>
        <div className="tile">
          <span className="k">Paper trading</span>
          <span className={`v ${p.total_pnl_usd >= 0 ? 'up' : 'down'}`}>{money(p.total_pnl_usd)}</span>
          <span className="s">
            {p.closed} closed{p.win_rate_pct !== null ? ` · ${p.win_rate_pct}% wins` : ''} · {p.open} open · $10 each
          </span>
        </div>
      </section>

      <section className="card">
        <h2>Recovery</h2>
        <p className="muted">HRV, resting heart rate, breathing rate and sleep, each against my own baseline. Grey ticks are nights without the watch.</p>
        <RecoveryBars days={days} W={chartWidth(narrow)} />
        <details>
          <summary>Show as a table</summary>
          <table>
            <thead>
              <tr><th>Day</th><th>Recovery</th><th>Zone</th><th>Strain</th><th>Sleep</th></tr>
            </thead>
            <tbody>
              {[...days].reverse().map((d) => (
                <tr key={d.day}>
                  <td>{d.day}</td>
                  <td>{d.recovery ?? '–'}</td>
                  <td>{d.label ? ZONE[d.label] : 'no data'}</td>
                  <td>{d.strain ?? '–'}</td>
                  <td>{d.sleep_pct === null ? '–' : `${d.sleep_pct}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </section>

      <section className="card">
        <h2>Training load</h2>
        <p className="muted">
          <span className="key" style={{ background: SERIES.fitness }} /> Fitness (42-day load) and{' '}
          <span className="key" style={{ background: SERIES.fatigue }} /> fatigue (7-day load). Fatigue above fitness means a heavy stretch.
        </p>
        <LoadLines days={days} W={chartWidth(narrow)} />
      </section>

      <section className="card">
        <h2>What the Scout flagged vs. what happened</h2>
        <p className="muted">
          Every potential-runner alert, and its paper trade: $10 at the alert price, sold at 2×, −50%, if liquidity vanished, or after 3 days, with 2% fees each way. Paper money only. Not financial advice.
        </p>
        {data.scout.alerts.length === 0 ? (
          <p className="muted">No alerts yet. Most days nothing qualifies, by design.</p>
        ) : (
          <div className="scroll">
            <table>
              <thead>
                <tr><th>Coin</th><th>Alerted</th><th>24 h volume</th><th>FDV</th><th>Best</th><th>Result</th></tr>
              </thead>
              <tbody>
                {data.scout.alerts.map((a) => (
                  <tr key={`${a.chain}-${a.symbol}-${a.alerted_at}`}>
                    <td><b>{a.symbol}</b> <span className="muted">{a.chain}</span></td>
                    <td>{new Date(a.alerted_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</td>
                    <td>{usd(a.volume_h24_usd)}</td>
                    <td>{usd(a.fdv_usd)}</td>
                    <td>{a.peak_x === null ? '–' : `${a.peak_x}×`}</td>
                    <td className={a.pnl_usd === null ? '' : a.pnl_usd >= 0 ? 'up' : 'down'}>{outcome(a)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  )
}
