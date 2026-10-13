import { useEffect, useRef, useState } from 'react'
import { NAMES, type OfficeEvent } from './office/choreography'
import { DEMO_LENGTH_MS, playDemo } from './office/demo'
import { connectLive, forgetKey, viewKey, type LiveStatus } from './office/live'
import { createOffice } from './office/OfficeScene'

type Mode = LiveStatus | 'demo'
const LOG_SIZE = 40

const STATUS_TEXT: Record<Mode, string> = {
  connecting: 'Connecting…',
  live: 'Live',
  locked: 'Wrong key: showing the demo',
  offline: 'Reconnecting…',
  demo: 'Demo (made-up numbers)',
}

function App() {
  const mount = useRef<HTMLDivElement>(null)
  const office = useRef<ReturnType<typeof createOffice> | null>(null)
  const [mode, setMode] = useState<Mode>('connecting')
  const [log, setLog] = useState<OfficeEvent[]>([])

  const show = (e: OfficeEvent) => {
    office.current?.scene()?.play(e)
    setLog((l) => [e, ...l].slice(0, LOG_SIZE))
  }

  // One Phaser game for the page's lifetime.
  useEffect(() => {
    if (!mount.current) return
    office.current = createOffice(mount.current)
    return () => {
      office.current?.game.destroy(true)
      office.current = null
    }
  }, [])

  // Live feed with the owner's key; otherwise loop the demo.
  useEffect(() => {
    const key = viewKey()
    let stopDemo: (() => void) | undefined
    let loop: number | undefined
    const demo = () => {
      setMode('demo')
      const run = () => {
        stopDemo = playDemo(show)
      }
      window.setTimeout(run, 800) // let the scene finish starting
      loop = window.setInterval(run, DEMO_LENGTH_MS + 6000)
    }
    if (!key) {
      demo()
      return () => {
        stopDemo?.()
        window.clearInterval(loop)
      }
    }
    const stop = connectLive(key, {
      onEvent: show,
      onHistory: (events) => setLog([...events].reverse().slice(0, LOG_SIZE)),
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
      window.clearInterval(loop)
    }
  }, [])

  return (
    <main>
      <header>
        <h1>Agent Office</h1>
        <span className={`pill ${mode}`}>{STATUS_TEXT[mode]}</span>
      </header>
      <div className="office" ref={mount} />
      <p className="hint">
        {mode === 'demo'
          ? 'A demo run. The live office plays out every message sent to the Telegram bot.'
          : 'Text the Telegram bot and watch the agents work.'}
      </p>
      <ol className="log">
        {log.map((e) => (
          <li key={`${e.run_id}-${e.id}`} className={e.agent}>
            <b>{NAMES[e.agent]}</b> <i>{e.status}</i>
            {e.target ? <span className="target"> → {e.target}</span> : null}
            {e.text ? <div className="text">{e.text}</div> : null}
          </li>
        ))}
      </ol>
    </main>
  )
}

export default App
