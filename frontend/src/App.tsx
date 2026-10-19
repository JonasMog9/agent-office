import { useEffect, useRef, useState } from 'react'
import { AGENTS, NAMES, type AgentId, type OfficeEvent } from './office/choreography'
import { SCENARIOS, demoLength, playDemo } from './office/demo'
import { connectLive, forgetKey, viewKey, type LiveStatus } from './office/live'
import { createOffice, type View } from './office/OfficeScene'

type Mode = LiveStatus | 'demo'
type Entry = OfficeEvent & { received: number }
const LOG_SIZE = 40

const STATUS_TEXT: Record<Mode, string> = {
  connecting: 'Connecting…',
  live: 'Live',
  locked: 'Wrong key: showing the demo',
  offline: 'Reconnecting…',
  demo: 'Demo · made-up numbers',
}

const ROLE: Record<AgentId, string> = {
  manager: 'Routes your Telegram messages',
  health_coach: 'Recovery, sleep, training',
  market_scout: 'New-coin runners, rug tests',
}

const VERB: Record<string, string> = {
  thinking: 'is thinking',
  working: 'is working',
  walking: 'is on the move',
  talking: 'says',
  idle: 'is done',
}

function ago(ms: number): string {
  const s = Math.round(ms / 1000)
  if (s < 5) return 'now'
  if (s < 60) return `${s}s`
  const m = Math.round(s / 60)
  return m < 60 ? `${m}m` : `${Math.round(m / 60)}h`
}

function App() {
  const mount = useRef<HTMLDivElement>(null)
  const office = useRef<ReturnType<typeof createOffice> | null>(null)
  const [mode, setMode] = useState<Mode>('connecting')
  const [log, setLog] = useState<Entry[]>([])
  const [view, setView] = useState<View | null>(null)
  const [status, setStatus] = useState<Record<AgentId, string> | null>(null)
  const [now, setNow] = useState(() => Date.now())

  const show = (e: OfficeEvent) => {
    office.current?.scene()?.play(e)
    setLog((l) => [{ ...e, received: Date.now() }, ...l].slice(0, LOG_SIZE))
  }

  // One office for the page's lifetime; the cards below read what each robot is doing.
  useEffect(() => {
    if (!mount.current) return
    office.current = createOffice(mount.current)
    const poll = window.setInterval(() => {
      const scene = office.current?.scene()
      if (!scene) return
      setStatus(scene.statuses())
      setView(scene.getView())
      setNow(Date.now())
    }, 500)
    return () => {
      window.clearInterval(poll)
      office.current?.destroy()
      office.current = null
    }
  }, [])

  // Live feed with the owner's key; otherwise the demo scenarios take turns, each one starting
  // when the office has finished acting out the last.
  useEffect(() => {
    const key = viewKey()
    let stopDemo: (() => void) | undefined
    let ticker: number | undefined
    const demo = () => {
      setMode('demo')
      let n = 0
      let started = 0
      let quietFor = 0
      ticker = window.setInterval(() => {
        const scene = office.current?.scene()
        if (!scene) return
        const due = started === 0 || Date.now() - started > demoLength(n - 1)
        quietFor = due && scene.quiet() ? quietFor + 1 : 0
        if (started === 0 || quietFor >= 6) {
          stopDemo = playDemo(show, n % SCENARIOS.length)
          n++
          started = Date.now()
          quietFor = 0
        }
      }, 500)
    }
    if (!key) {
      demo()
      return () => {
        stopDemo?.()
        window.clearInterval(ticker)
      }
    }
    const stop = connectLive(key, {
      onEvent: show,
      onHistory: (events) =>
        setLog([...events].reverse().slice(0, LOG_SIZE).map((e) => ({ ...e, received: Date.parse(e.at ?? '') || Date.now() }))),
      onStatus: (s) => {
        if (s === 'locked') {
          forgetKey()
          demo()
        } else setMode(s)
      },
    })
    return () => {
      stop()
      stopDemo?.()
      window.clearInterval(ticker)
    }
  }, [])

  const pick = (v: View) => {
    office.current?.scene()?.setView(v)
    setView(v)
  }

  return (
    <main>
      <header className="top">
        <div className="brand">
          <span className="logo" aria-hidden>
            <i className="health_coach" />
            <i className="manager" />
            <i className="market_scout" />
          </span>
          <div>
            <h1>Agent Office</h1>
            <p className="tagline">Three AI agents at work, live from Telegram</p>
          </div>
        </div>
        <div className="actions">
          <a className="pill link" href="/stats">
            Stats →
          </a>
          <span className={`pill ${mode}`}>
            <b />
            {STATUS_TEXT[mode]}
          </span>
        </div>
      </header>

      <section className="stage">
        <div className="stagebar">
          <span className="where">
            <i className="health_coach" /> Health Lab <i className="manager" /> Command Room <i className="market_scout" /> Trading Desk
          </span>
          <div className="views" role="group" aria-label="Camera">
            {(['overview', 'follow'] as View[]).map((v) => (
              <button key={v} className={view === v ? 'on' : ''} onClick={() => pick(v)}>
                {v === 'overview' ? 'Overview' : 'Follow'}
              </button>
            ))}
          </div>
        </div>
        <div className="office" ref={mount} />
      </section>

      <section className="agents">
        {AGENTS.map((a) => {
          const s = status?.[a] ?? 'idle'
          const busy = s !== 'idle'
          return (
            <article key={a} className={`agent ${a}${busy ? ' busy' : ''}`}>
              <span className="dot" />
              <div>
                <h2>{NAMES[a]}</h2>
                <p>{ROLE[a]}</p>
              </div>
              <span className="now">{s}</span>
            </article>
          )
        })}
      </section>

      <section className="feed">
        <h3>
          Activity
          <span>
            {mode === 'demo'
              ? 'A demo run: the live office plays out every message sent to the Telegram bot.'
              : 'Text the Telegram bot and watch the agents work.'}
          </span>
        </h3>
        <ol>
          {log.map((e) => (
            <li key={`${e.run_id}-${e.id}`} className={e.agent}>
              <span className="dot" />
              <div className="body">
                <div className="line">
                  <b>{NAMES[e.agent]}</b> {VERB[e.status] ?? e.status}
                  {e.target && e.status !== 'idle' ? <span className="target"> · {e.target.replace(/_/g, ' ')}</span> : null}
                  <time>{ago(now - e.received)}</time>
                </div>
                {e.text && e.status !== 'idle' ? <div className="text">{e.text}</div> : null}
              </div>
            </li>
          ))}
        </ol>
      </section>
    </main>
  )
}

export default App
