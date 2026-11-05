import { useEffect, useState } from 'react'
import { viewKey } from '../office/live'
import { chartWidth } from '../stats/data'
import { Calendar, SleepBars, TimeLines, WeeklyBars } from './charts'
import {
  BLUE,
  LOAD,
  RACE_KM,
  SLEEP_STAGE,
  STRAVA_CURRENCY,
  STRAVA_PER_YEAR,
  ZONE_RAMP,
  clock,
  demoHealth,
  fetchHealth,
  fitnessAgeLine,
  hm,
  pace,
  shortDay,
  type Health as Data,
  type Totals,
} from './data'

const ZONE = { green: 'Green', yellow: 'Yellow', red: 'Red' } as const
const RACE_NAME: Record<string, string> = { '5K': '5K', '10K': '10K', 'half marathon': 'Half', marathon: 'Marathon' }
const EFFORT_NAME: Record<string, string> = { '5k': '5K', '10k': '10K', 'Half-Marathon': 'half marathon' }
const sign = (x: number) => `${x > 0 ? '+' : x < 0 ? '−' : ''}${Math.abs(x)}`

function TotalsRow({ label, t }: { label: string; t: Totals }) {
  return (
    <tr>
      <td>{label}</td>
      <td>{t.runs}</td>
      <td>{t.km} km</td>
      <td>{t.hours} h</td>
      <td>{t.climb_m} m</td>
      <td>{t.longest_km === null ? '–' : `${t.longest_km} km`}</td>
    </tr>
  )
}

function Key({ color, label }: { color: string; label: string }) {
  return (
    <span className="legend-item">
      <span className="swatch" style={{ background: color }} />
      {label}
    </span>
  )
}

export default function Health() {
  const [key] = useState(viewKey)
  const [data, setData] = useState<Data | null>(() => (key ? null : demoHealth()))
  const [demo, setDemo] = useState(!key)
  const [error, setError] = useState<string | null>(null)
  const [narrow, setNarrow] = useState(() => window.matchMedia('(max-width: 700px)').matches)
  const [race, setRace] = useState('10K')

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 700px)')
    const on = () => setNarrow(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])

  useEffect(() => {
    if (!key) return
    fetchHealth(key)
      .then((r) => {
        if (r === 'locked') {
          setDemo(true)
          setData(demoHealth())
        } else setData(r)
      })
      .catch((e: Error) => setError(e.message))
  }, [key])

  if (error) return <main className="stats health"><p className="muted">Couldn't load the health data: {error}</p></main>
  if (!data) return <main className="stats health"><p className="muted">Loading…</p></main>

  const W = chartWidth(narrow)
  const half = narrow ? W : 520
  const s = data.summary
  const fa = data.fitness_age
  const best = data.best_vdot
  const current = Object.fromEntries(data.predictions.current.map((c) => [c.distance, c]))
  const picked = current[race]
  const hist = data.predictions.history[race] ?? []
  const zoneTotal = data.zones.hr.reduce((a, z) => a + z.minutes, 0)
  const formSeries = [
    { key: 'cadence_spm', label: 'Cadence', unit: 'spm', fmt: (v: number) => `${Math.round(v)}` },
    { key: 'ground_contact_ms', label: 'Ground contact', unit: 'ms', fmt: (v: number) => `${Math.round(v)}` },
    { key: 'vertical_oscillation_cm', label: 'Vertical oscillation', unit: 'cm', fmt: (v: number) => v.toFixed(1) },
    { key: 'stride_length_m', label: 'Stride length', unit: 'm', fmt: (v: number) => v.toFixed(2) },
  ] as const
  const formWithData = formSeries.filter((f) => data.form.some((d) => d[f.key] !== null))
  const weekKm = data.weekly.slice(-4)

  return (
    <main className="stats health">
      <header className="top">
        <div className="brand">
          <span className="logo" aria-hidden>
            <i className="health_coach" />
            <i className="manager" />
            <i className="market_scout" />
          </span>
          <div>
            <h1>Health &amp; Training</h1>
            <p className="tagline">Everything a Strava or Garmin subscription shows, computed in Python from my own data</p>
          </div>
        </div>
        <div className="actions">
          {demo && (
            <span className="pill demo">
              <b />
              Demo · made-up numbers
            </span>
          )}
          <a className="pill link" href="/stats">
            Stats
          </a>
          <a className="pill link" href="/">
            ← Office
          </a>
        </div>
      </header>

      <section className="savings">
        <div>
          <span className="k">Strava subscription cancelled</span>
          <span className="v">
            Saves {STRAVA_CURRENCY}
            {STRAVA_PER_YEAR.toFixed(2)} a year
          </span>
        </div>
        <p>
          This page replaced it: race predictions, fitness and freshness, VO2max, best efforts, heart-rate and pace zones,
          weekly mileage and a training calendar. Runs still sync from the free Strava app through its free API; health data
          comes from the Apple Watch. The whole app costs under $1 a month in AI.
        </p>
      </section>

      <section className="tiles tiles-8">
        <div className="tile">
          <span className="k">VO2max</span>
          <span className="v">{s.vo2max ?? '–'}</span>
          <span className="s">{s.vo2max_change_90d === null ? 'Apple Watch estimate' : `${sign(s.vo2max_change_90d)} in 90 days`}</span>
        </div>
        <div className="tile">
          <span className="k">Fitness age</span>
          <span className="v">{fa?.value ?? '–'}</span>
          <span className="s">{fitnessAgeLine(fa)}</span>
        </div>
        <div className="tile">
          <span className="k">This week</span>
          <span className="v">{s.this_week_km} km</span>
          <span className="s">{s.avg_week_km_4w === null ? '–' : `4-week average ${s.avg_week_km_4w} km`}</span>
        </div>
        <div className="tile">
          <span className="k">Predicted 5K · half</span>
          <span className="v">{clock(current['5K']?.seconds)}</span>
          <span className="s">Half {clock(current['half marathon']?.seconds)}</span>
        </div>
        <div className="tile">
          <span className="k">Recovery today</span>
          <span className="v">
            {s.recovery === null ? '–' : `${s.recovery}%`}
            {s.label && <em className={`zone-chip ${s.label}`}>{ZONE[s.label]}</em>}
          </span>
          <span className="s">vs. my own baselines</span>
        </div>
        <div className="tile">
          <span className="k">Resting HR · HRV</span>
          <span className="v">
            {s.resting_hr ?? '–'} · {s.hrv ?? '–'}
          </span>
          <span className="s">
            bpm · ms; 30-day {s.resting_hr_30d ?? '–'} · {s.hrv_30d ?? '–'}
          </span>
        </div>
        <div className="tile">
          <span className="k">Fitness · fatigue</span>
          <span className="v">
            {s.fitness ?? '–'} · {s.fatigue ?? '–'}
          </span>
          <span className="s">Form {s.form === null ? '–' : sign(s.form)}</span>
        </div>
        <div className="tile">
          <span className="k">Running score (VDOT)</span>
          <span className="v">{data.zones.vdot ?? '–'}</span>
          <span className="s">{best ? `Best ever ${best.vdot}, higher = faster` : 'Higher = faster'}</span>
        </div>
      </section>

      <section className="card">
        <h2>Race-time predictor</h2>
        <p className="muted">
          Each distance is the middle of several methods (VDOT and Riegel from my best recent effort, Apple's VO2max, a
          personal pace-at-heart-rate model, and for the marathon Tanda's mileage formula and a trained ML model). Pick a
          distance to see how it's moved.
        </p>
        <div className="races">
          {data.predictions.current.map((c) => (
            <button key={c.distance} className={`race ${race === c.distance ? 'on' : ''}`} onClick={() => setRace(c.distance)}>
              <span className="k">{RACE_NAME[c.distance]}</span>
              <span className="v">{clock(c.seconds)}</span>
              <span className="s">
                {c.seconds ? pace(c.seconds / RACE_KM[c.distance]) : 'not enough data'}
                {c.confidence ? ` · ${c.confidence}` : ''}
              </span>
            </button>
          ))}
        </div>
        {hist.length > 1 && (
          <TimeLines
            days={hist.map((h) => h.day)}
            series={[{ key: 'p', label: RACE_NAME[race], color: BLUE, values: hist.map((h) => h.seconds) }]}
            band={{ low: hist.map((h) => h.low), high: hist.map((h) => h.high), color: BLUE }}
            W={W}
            format={clock}
          />
        )}
        {picked?.methods?.length ? (
          <div className="scroll">
            <table>
              <thead>
                <tr><th>Method</th><th>{RACE_NAME[race]}</th><th>From</th></tr>
              </thead>
              <tbody>
                {picked.methods.map((m) => (
                  <tr key={m.method}>
                    <td><b>{m.method}</b></td>
                    <td>{clock(m.seconds)}</td>
                    <td className="muted wrap">{m.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        {picked?.low ? (
          <p className="muted">
            Range {clock(picked.low)}–{clock(picked.high)} ({picked.confidence} confidence), as of {shortDay(picked.as_of!)}.
          </p>
        ) : null}
      </section>

      <section className="card">
        <h2>VO2max</h2>
        <p className="muted">Apple Watch's estimate from outdoor runs, over the last year.</p>
        <TimeLines
          days={data.vo2max.map((v) => v.day)}
          series={[{ key: 'vo2', label: 'VO2max', color: BLUE, values: data.vo2max.map((v) => v.value) }]}
          W={W}
          format={(v) => v.toFixed(1)}
        />
      </section>

      {fa && (
        <section className="card">
          <h2>Fitness age</h2>
          <p className="muted">
            The age at which a typical person has my VO2max ({fa.vo2max}). VO2max drops with age, so it can be read as an
            age: the idea behind Garmin's Fitness Age and WHOOP Age. The yardstick is the median VO2max for each decade of
            age in the FRIEND fitness registry (Kaminsky et al. 2015).
            {fa.age !== null && fa.median_at_age !== null
              ? ` I'm ${Math.floor(fa.age)}; the median VO2max at my age is ${fa.median_at_age}.`
              : ''}
          </p>
          {fa.notes.slice(1).map((n) => (
            <p key={n} className="muted">{n}</p>
          ))}
          {fa.history.length > 1 && (
            <TimeLines
              days={fa.history.map((h) => h.day)}
              series={[{ key: 'fa', label: 'Fitness age', color: BLUE, values: fa.history.map((h) => h.value) }]}
              W={W}
              format={(v) => `${Math.round(v)}`}
            />
          )}
        </section>
      )}

      <section className="card">
        <h2>Running score (VDOT)</h2>
        <p className="muted">
          VDOT is Jack Daniels' running-fitness number: the VO2max that a race time implies, so higher means faster. Now:{' '}
          <b>{data.zones.vdot ?? '–'}</b>, {data.zones.vdot_source}, using efforts in the last 8 weeks only, so it follows
          current form.
          {best
            ? ` Best ever: ${best.vdot}, from a ${EFFORT_NAME[best.effort] ?? best.effort} in ${clock(best.seconds)} on ${shortDay(best.day)}.`
            : ''}
        </p>
      </section>

      <section className="card">
        <h2>Weekly mileage</h2>
        <p className="muted">
          Running km per week (Monday to Sunday), last 52 weeks. Last 4 weeks: {weekKm.map((w) => w.km).join(', ')} km.
        </p>
        <WeeklyBars weeks={data.weekly} W={W} />
        <div className="scroll">
          <table>
            <thead>
              <tr><th></th><th>Runs</th><th>Distance</th><th>Time</th><th>Climb</th><th>Longest</th></tr>
            </thead>
            <tbody>
              <TotalsRow label="Last 4 weeks" t={data.totals.last_4_weeks} />
              <TotalsRow label="Year to date" t={data.totals.year_to_date} />
              <TotalsRow label="All time" t={data.totals.all_time} />
            </tbody>
          </table>
        </div>
      </section>

      <section className="grid2">
        <section className="card">
          <h2>Training calendar</h2>
          <p className="muted">The last 12 weeks, one square a day; darker means further.</p>
          <Calendar days={data.calendar} />
          <div className="legend">
            <span className="legend-item"><span className="swatch rest" />Rest</span>
            <Key color={ZONE_RAMP[0]} label="under 5 km" />
            <Key color={ZONE_RAMP[1]} label="5–10" />
            <Key color={ZONE_RAMP[2]} label="10–15" />
            <Key color={ZONE_RAMP[3]} label="15–20" />
            <Key color={ZONE_RAMP[4]} label="20+" />
          </div>
        </section>

        <section className="card">
          <h2>Heart-rate zones</h2>
          <p className="muted">
            Time in each zone over the last {data.zones.window_days} days of runs. Zones from heart-rate reserve (resting{' '}
            {data.zones.hr_rest ?? '–'}, max {data.zones.hr_max ?? '–'}).
          </p>
          {data.zones.hr.length ? (
            <div className="zones">
              {data.zones.hr.map((z) => {
                const pct = zoneTotal ? (100 * z.minutes) / zoneTotal : 0
                return (
                  <div key={z.zone} className="zone-row">
                    <span className="zname">
                      <b>Z{z.zone}</b> {z.name}
                      <span className="muted"> {Math.round(z.low)}–{Math.round(z.high)} bpm</span>
                    </span>
                    <span className="zbar">
                      <span style={{ width: `${Math.max(pct, 0.5)}%`, background: ZONE_RAMP[z.zone - 1] }} />
                    </span>
                    <span className="zval">
                      {hm(z.minutes)} · {Math.round(pct)}%
                    </span>
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="muted">Needs a resting and max heart rate first.</p>
          )}
        </section>
      </section>

      <section className="card">
        <h2>Fitness &amp; freshness</h2>
        <p className="muted">
          Fitness is the 42-day training load, fatigue the 7-day load, and form is fitness minus fatigue: below zero means
          tired from training, above zero fresh. From heart rate on every run (Banister TRIMP).
        </p>
        <TimeLines
          days={data.load.map((d) => d.day)}
          series={[
            { key: 'fit', label: 'Fitness', color: LOAD.fitness, values: data.load.map((d) => d.fitness) },
            { key: 'fat', label: 'Fatigue', color: LOAD.fatigue, values: data.load.map((d) => d.fatigue) },
            { key: 'form', label: 'Form', color: LOAD.form, values: data.load.map((d) => d.form) },
          ]}
          W={W}
          zero
          format={(v) => `${Math.round(v)}`}
        />
      </section>

      <section className="grid2">
        <section className="card">
          <h2>Personal records</h2>
          <p className="muted">Fastest Strava best effort at each distance, from every run.</p>
          {data.records.length ? (
            <div className="scroll">
              <table>
                <thead>
                  <tr><th>Distance</th><th>Time</th><th>Pace</th><th>When</th></tr>
                </thead>
                <tbody>
                  {data.records.map((r) => (
                    <tr key={r.name}>
                      <td><b>{r.name}</b></td>
                      <td>{clock(r.seconds)}</td>
                      <td>{pace(r.seconds / (r.distance_m / 1000))}</td>
                      <td className="muted">{shortDay(r.day)} · {r.run}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="muted">No best efforts synced yet.</p>
          )}
        </section>

        <section className="card">
          <h2>Pace zones</h2>
          <p className="muted">
            Daniels training paces for VDOT {data.zones.vdot ?? '–'}, {data.zones.vdot_source}.
          </p>
          <div className="scroll">
          <table>
            <thead>
              <tr><th>Zone</th><th>Pace</th><th>Use</th></tr>
            </thead>
            <tbody>
              {data.zones.pace.map((p) => (
                <tr key={p.name}>
                  <td><b>{p.name[0].toUpperCase() + p.name.slice(1)}</b></td>
                  <td>{p.fast_s_per_km === p.slow_s_per_km ? pace(p.fast_s_per_km) : `${clock(p.fast_s_per_km)}–${pace(p.slow_s_per_km)}`}</td>
                  <td className="muted">
                    {{ easy: 'most runs', marathon: 'long-run finishes', threshold: 'tempo', interval: '3–5 min reps', repetition: 'short fast reps' }[p.name] ?? ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </section>
      </section>

      <section className="card">
        <h2>Recent runs</h2>
        <div className="scroll">
          <table>
            <thead>
              <tr><th>Day</th><th>Run</th><th>Distance</th><th>Time</th><th>Pace</th><th>Avg HR</th><th>Climb</th><th>Cadence</th></tr>
            </thead>
            <tbody>
              {data.runs.map((r) => (
                <tr key={`${r.day}-${r.name}-${r.km}`}>
                  <td>{shortDay(r.day)}</td>
                  <td>{r.name}</td>
                  <td>{r.km} km</td>
                  <td>{clock(r.moving_s)}</td>
                  <td>{pace(r.pace_s_per_km)}</td>
                  <td>{r.avg_hr ?? '–'}</td>
                  <td>{r.climb_m === null ? '–' : `${r.climb_m} m`}</td>
                  <td>{r.cadence_spm ?? '–'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="grid2">
        <section className="card">
          <h2>Resting heart rate</h2>
          <p className="muted">bpm each morning, last 90 days. Lower is generally fitter and better recovered.</p>
          <TimeLines
            days={data.vitals.map((v) => v.day)}
            series={[{ key: 'rhr', label: 'Resting HR', color: LOAD.fatigue, values: data.vitals.map((v) => v.resting_hr) }]}
            W={half}
            format={(v) => `${Math.round(v)}`}
          />
        </section>
        <section className="card">
          <h2>Heart-rate variability</h2>
          <p className="muted">SDNN in ms, last 90 days, compared only with my own normal.</p>
          <TimeLines
            days={data.vitals.map((v) => v.day)}
            series={[{ key: 'hrv', label: 'HRV', color: LOAD.form, values: data.vitals.map((v) => v.hrv) }]}
            W={half}
            format={(v) => `${Math.round(v)}`}
          />
        </section>
      </section>

      <section className="card">
        <h2>Sleep</h2>
        <p className="muted">The last 30 nights, by stage where the watch recorded them.</p>
        <SleepBars nights={data.sleep} W={W} />
        <div className="legend">
          {data.sleep.some((n) => n.deep_min !== null) ? (
            <>
              <Key color={SLEEP_STAGE.deep} label="Deep" />
              <Key color={SLEEP_STAGE.core} label="Core" />
              <Key color={SLEEP_STAGE.rem} label="REM" />
              <Key color={SLEEP_STAGE.awake} label="Awake" />
            </>
          ) : (
            <Key color={SLEEP_STAGE.core} label="Asleep (no stage data from the watch)" />
          )}
        </div>
      </section>

      {formWithData.length > 0 && (
        <section className="card">
          <h2>Running form</h2>
          <p className="muted">Running dynamics from the watch and cadence from Strava, last 90 days.</p>
          <div className="grid2 inner">
            {formWithData.map((f) => (
              <div key={f.key}>
                <h3 className="sub">
                  {f.label} ({f.unit})
                </h3>
                <TimeLines
                  days={data.form.map((d) => d.day)}
                  series={[{ key: f.key, label: f.label, color: BLUE, values: data.form.map((d) => d[f.key]) }]}
                  W={half}
                  height={170}
                  endLabels={false}
                  connect={f.key === 'cadence_spm'}
                  format={f.fmt}
                />
              </div>
            ))}
          </div>
        </section>
      )}

      {data.plan && (
        <section className="card">
          <h2>This week's plan</h2>
          <p className="muted">
            {data.plan.this_week.phase[0].toUpperCase() + data.plan.this_week.phase.slice(1)} phase, {data.plan.this_week.km} km
            {data.plan.goal.race ? ` · building to a ${data.plan.goal.race} on ${shortDay(data.plan.goal.date!)}` : ''}.
          </p>
          <div className="scroll">
          <table>
            <tbody>
              {data.plan.this_week.workouts.map((w) => (
                <tr key={w.day} className={w.day === data.today ? 'today' : ''}>
                  <td>{new Date(`${w.day}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric' })}</td>
                  <td><b>{w.kind}</b></td>
                  <td className="wrap">{w.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </section>
      )}

      <p className="muted footnote">
        Every number here is computed in Python from Apple Health and Strava data; none is estimated by an AI.{' '}
        <a href="https://github.com/JonasMog9/agent-office">How it works</a>.
      </p>
    </main>
  )
}
