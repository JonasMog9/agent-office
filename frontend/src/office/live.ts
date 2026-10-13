// The live feed: a WebSocket to the backend's /ws/events, reconnecting with backoff.

import type { OfficeEvent } from './choreography'

export type LiveStatus = 'connecting' | 'live' | 'locked' | 'offline'

export const API_URL: string =
  import.meta.env.VITE_API_URL ?? 'https://agent-office-production-d0e3.up.railway.app'

export function wsUrl(api: string, key: string): string {
  const u = new URL('/ws/events', api)
  u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:'
  u.searchParams.set('key', key)
  return u.toString()
}

interface Handlers {
  onEvent: (e: OfficeEvent) => void
  onHistory: (events: OfficeEvent[]) => void
  onStatus: (s: LiveStatus) => void
}

/** Connects and keeps reconnecting until the returned function is called. */
export function connectLive(key: string, h: Handlers, api = API_URL): () => void {
  let ws: WebSocket | null = null
  let stopped = false
  let delay = 1000
  let retry: number | undefined

  const open = () => {
    h.onStatus('connecting')
    ws = new WebSocket(wsUrl(api, key))
    ws.onopen = () => {
      delay = 1000
      h.onStatus('live')
    }
    ws.onmessage = (m) => {
      const msg = JSON.parse(m.data)
      if (msg.type === 'hello') h.onHistory(msg.recent)
      else if (msg.type === 'event') h.onEvent(msg.event)
    }
    ws.onclose = (e) => {
      if (stopped) return
      if (e.code === 4401) {
        h.onStatus('locked') // wrong key: don't hammer the server
        return
      }
      h.onStatus('offline')
      retry = window.setTimeout(open, delay)
      delay = Math.min(delay * 2, 30_000)
    }
  }
  open()
  return () => {
    stopped = true
    window.clearTimeout(retry)
    ws?.close()
  }
}

/** The view key: from ?key= once (then removed from the address bar), else remembered. */
export function viewKey(): string | null {
  const url = new URL(window.location.href)
  const fromUrl = url.searchParams.get('key')
  try {
    if (fromUrl) {
      localStorage.setItem('officeKey', fromUrl)
      url.searchParams.delete('key')
      window.history.replaceState(null, '', url.toString())
      return fromUrl
    }
    return localStorage.getItem('officeKey')
  } catch {
    return fromUrl
  }
}

export function forgetKey(): void {
  try {
    localStorage.removeItem('officeKey')
  } catch {
    /* private mode: nothing stored */
  }
}
