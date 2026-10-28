import { useEffect, useState } from 'react'
import { viewKey } from '../office/live'
import { LoadLines, PnlLines, RecoveryBars } from './charts'
import {
  SERIES,
  STRATEGY_COLOR,
  chartWidth,
  demoStats,
  fetchStats,
  type PaperResult,
  type Stats as Data,
} from './data'

const usd = (x: number | null) =>
  x === null ? '–' : x >= 1e6 ? `$${(x / 1e6).toFixed(1)}M` : x >= 1e3 ? `$${Math.round(x / 1e3)}k` : `$${x.toFixed(0)}`
const money = (x: number | null) => (x === null ? '–' : `${x >= 0 ? '+' : '−'}$${Math.abs(x).toFixed(2)}`)
const ZONE = { green: 'Green', yellow: 'Yellow', red: 'Red' } as const
const REASON: Record<string, string> = {
  take_profit: 'hit its target',
  trailing_stop: 'trailing stop',
  stop_loss: 'stopped out',
  liquidity_gone: 'liquidity vanished',
  time: 'time up',
  no_price: 'no price',
}

const pct = (x: number) => `${x > 0 ? '+' : x < 0 ? '−' : ''}${Math.abs(x)}%`

/** One strategy's result on one alert: P/L and why it sold, or where an open trade stands. */
function Result({ r, as: Tag = 'td' }: { r: PaperResult | undefined; as?: 'td' | 'div' }) {
  if (!r) return <Tag className="muted">–</Tag>
  if (r.status === 'open') {
    const now = r.pnl_now_usd ?? 0
    return (
      <Tag>
        <span className="muted">open · {r.now_x ?? '–'}×</span>
        <small className={now >= 0 ? 'up' : 'down'}>
          {money(now)} if sold now{r.sold_pct ? ` · ${r.sold_pct}% sold` : ''}
        </small>
      </Tag>
    )
  }
  return (
    <Tag className={(r.pnl_usd ?? 0) >= 0 ? 'up' : 'down'}>
      {money(r.pnl_usd)}
      <small className="muted">
        {REASON[r.exit_reason ?? ''] ?? r.exit_reason} · {r.now_x ?? '–'}×
      </small>
    </Tag>
  )
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
  const strategies = data.scout.strategies ?? [] // empty while the backend is an older version
  const best = [...strategies].sort((a, b) => b.summary.total_pnl_usd - a.summary.total_pnl_usd)[0]
  const anyClosed = strategies.some((x) => x.summary.closed > 0)
  const end = Date.parse(data.generated_at)
  const firstAlert = Math.min(end, ...data.scout.alerts.map((a) => Date.parse(a.alerted_at)))

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
          <span className="k">Best paper strategy</span>
          <span className={`v ${anyClosed ? (best.summary.total_pnl_usd >= 0 ? 'up' : 'down') : ''}`}>
            {anyClosed ? money(best.summary.total_pnl_usd) : '–'}
          </span>
          <span className="s">{anyClosed ? `${best.name} · of 3 strategies, $10 a trade` : 'no closed trades yet'}</span>
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
        <h2>Paper trading: three ways to sell</h2>
        <p className="muted">
          Every alert buys a pretend $10 with each strategy at the alert price; only the selling rules differ. 2% fees and slippage each way.
          Paper money only. Not financial advice.
        </p>
        <div className="strategies">
          {strategies.map((x, i) => (
            <article key={x.key} className="strategy">
              <header>
                <span className="swatch" style={{ background: STRATEGY_COLOR[x.key] }} />
                <span className="num">Strategy {i + 1}</span>
                <h3>{x.name}</h3>
              </header>
              <p className="blurb">{x.blurb}</p>
              <div className={`pnl ${x.summary.closed ? (x.summary.total_pnl_usd >= 0 ? 'up' : 'down') : ''}`}>
                {x.summary.closed ? money(x.summary.total_pnl_usd) : '$0.00'}
                {x.summary.return_pct !== null && <em>{pct(x.summary.return_pct)}</em>}
              </div>
              <p className="facts">
                {x.summary.closed} closed{x.summary.win_rate_pct !== null ? ` · ${x.summary.win_rate_pct}% wins` : ''}
                {x.summary.open ? (
                  <>
                    {' · '}
                    {x.summary.open} open, <span className={x.summary.open_pnl_usd >= 0 ? 'up' : 'down'}>{money(x.summary.open_pnl_usd)}</span> if sold now
                  </>
                ) : null}
              </p>
            </article>
          ))}
        </div>
        {anyClosed ? (
          <>
            <h3 className="sub">Running total of closed trades</h3>
            <PnlLines strategies={strategies} start={firstAlert} end={end} W={chartWidth(narrow)} />
          </>
        ) : (
          <p className="muted">No closed trades yet: the running totals appear here once one sells out.</p>
        )}
      </section>

      <section className="card">
        <h2>What the Scout flagged vs. what happened</h2>
        <p className="muted">
          Every potential-runner alert, and how each strategy's paper trade on it played out. Best is the highest price seen after the alert.
        </p>
        {data.scout.alerts.length === 0 ? (
          <p className="muted">No alerts yet. Most days nothing qualifies, by design.</p>
        ) : narrow ? (
          <ol className="alert-list">
            {data.scout.alerts.map((a) => (
              <li key={`${a.chain}-${a.symbol}-${a.alerted_at}`}>
                <div className="head">
                  <b>{a.symbol}</b> <span className="muted">{a.chain}</span>
                  <span className="muted when">
                    {new Date(a.alerted_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} · best{' '}
                    {a.peak_x === null ? '–' : `${a.peak_x}×`}
                  </span>
                </div>
                <div className="trio">
                  {strategies.map((x) => (
                    <div key={x.key}>
                      <span className="name">
                        <span className="swatch" style={{ background: STRATEGY_COLOR[x.key] }} />
                        {x.name}
                      </span>
                      <Result as="div" r={a.trades[x.key]} />
                    </div>
                  ))}
                </div>
                <p className="muted small">
                  {usd(a.volume_h24_usd)} 24 h volume · {usd(a.fdv_usd)} FDV
                </p>
              </li>
            ))}
          </ol>
        ) : (
          <div className="scroll">
            <table className="results">
              <thead>
                <tr>
                  <th>Coin</th>
                  <th>Alerted</th>
                  <th>24 h volume</th>
                  <th>FDV</th>
                  <th>Best</th>
                  {strategies.map((x) => (
                    <th key={x.key}>
                      <span className="swatch" style={{ background: STRATEGY_COLOR[x.key] }} />
                      {x.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.scout.alerts.map((a) => (
                  <tr key={`${a.chain}-${a.symbol}-${a.alerted_at}`}>
                    <td><b>{a.symbol}</b> <span className="muted">{a.chain}</span></td>
                    <td>{new Date(a.alerted_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</td>
                    <td>{usd(a.volume_h24_usd)}</td>
                    <td>{usd(a.fdv_usd)}</td>
                    <td>{a.peak_x === null ? '–' : `${a.peak_x}×`}</td>
                    {strategies.map((x) => (
                      <Result key={x.key} r={a.trades[x.key]} />
                    ))}
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
