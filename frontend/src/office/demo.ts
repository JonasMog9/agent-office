// A scripted run for the public page: the same event shapes the backend sends, with made-up
// numbers, so anyone can watch the office without seeing the owner's real health data.

import type { OfficeEvent } from './choreography'

type Step = Omit<OfficeEvent, 'id'> & { wait: number }

const STEPS: Step[] = [
  { wait: 0, agent: 'manager', status: 'thinking', target: 'owner', text: 'How recovered am I today?' },
  { wait: 900, agent: 'manager', status: 'working', target: 'ask_health_coach', text: 'Asking the Health Coach' },
  { wait: 600, agent: 'manager', status: 'walking', target: 'health_coach', text: 'Asking the Health Coach' },
  { wait: 1500, agent: 'health_coach', status: 'thinking', target: 'manager', text: 'Thinking…' },
  { wait: 900, agent: 'health_coach', status: 'working', target: 'get_recovery', text: 'Checking recovery' },
  { wait: 1500, agent: 'health_coach', status: 'working', target: 'get_sleep', text: 'Checking sleep' },
  { wait: 1500, agent: 'health_coach', status: 'talking', target: 'manager',
    text: 'Demo: recovery 74 (green). HRV 61 vs your usual 55, resting HR 50 vs 52. Slept 7 h 48 min. Good day for the planned tempo run.' },
  { wait: 4500, agent: 'health_coach', status: 'idle', target: null, text: '' },
  { wait: 200, agent: 'manager', status: 'walking', target: 'owner', text: 'Back with the answer' },
  { wait: 1500, agent: 'manager', status: 'talking', target: 'owner',
    text: 'Demo: you\'re at 74, green. Go ahead with the tempo run.' },
  { wait: 3500, agent: 'manager', status: 'idle', target: null, text: '' },
]

let runs = 0

/** Plays the demo through `emit`; returns a function that cancels it. Each run gets its own
 *  ids, since the log is keyed by them. */
export function playDemo(emit: (e: OfficeEvent) => void): () => void {
  const run = ++runs
  const timers: number[] = []
  let t = 0
  STEPS.forEach(({ wait, ...e }, i) => {
    t += wait
    timers.push(window.setTimeout(() => emit({ ...e, id: run * 1000 + i, run_id: `demo-${run}` }), t))
  })
  return () => timers.forEach(clearTimeout)
}

export const DEMO_LENGTH_MS = STEPS.reduce((sum, s) => sum + s.wait, 0)
