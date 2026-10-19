// Scripted runs for the public page: the same event shapes the backend sends, with made-up
// numbers, so anyone can watch the office without seeing the owner's real data. Three
// scenarios take turns: a health question, a Market Scout alert, and a paper-trading check.

import type { OfficeEvent } from './choreography'

type Step = Omit<OfficeEvent, 'id'> & { wait: number }

const HEALTH: Step[] = [
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
  { wait: 1500, agent: 'manager', status: 'talking', target: 'owner', text: "Demo: you're at 74, green. Go ahead with the tempo run." },
  { wait: 3500, agent: 'manager', status: 'idle', target: null, text: '' },
]

const ALERT: Step[] = [
  { wait: 0, agent: 'market_scout', status: 'working', target: 'get_alert', text: 'Spotted a potential runner: DEMO' },
  { wait: 300, agent: 'manager', status: 'walking', target: 'market_scout', text: "Picking up the Scout's alert" },
  { wait: 300, agent: 'market_scout', status: 'thinking', target: 'manager', text: 'Thinking…' },
  { wait: 900, agent: 'market_scout', status: 'working', target: 'get_alert', text: 'Writing the alert' },
  { wait: 1500, agent: 'market_scout', status: 'talking', target: 'manager',
    text: 'Demo: 🚀 Potential runner: DEMO on Solana. 14 h old, $4.2M volume, 9,800 buyers. Passed all 7 rug tests. Not financial advice.' },
  { wait: 300, agent: 'market_scout', status: 'idle', target: null, text: '' },
  { wait: 200, agent: 'manager', status: 'walking', target: 'owner', text: 'Bringing you the alert' },
  { wait: 300, agent: 'manager', status: 'talking', target: 'owner', text: 'Demo: 🚀 Potential runner: DEMO on Solana' },
  { wait: 300, agent: 'manager', status: 'idle', target: null, text: '' },
]

const PAPER: Step[] = [
  { wait: 0, agent: 'manager', status: 'thinking', target: 'owner', text: 'How are my paper trades?' },
  { wait: 900, agent: 'manager', status: 'working', target: 'ask_market_scout', text: 'Asking the Market Scout' },
  { wait: 400, agent: 'manager', status: 'walking', target: 'market_scout', text: 'Asking the Market Scout' },
  { wait: 900, agent: 'market_scout', status: 'thinking', target: 'manager', text: 'Thinking…' },
  { wait: 900, agent: 'market_scout', status: 'working', target: 'paper_trades', text: 'Checking paper trades' },
  { wait: 1500, agent: 'market_scout', status: 'talking', target: 'manager',
    text: 'Demo: 4 paper trades. 1 closed at 2.1× (+$10.17), 3 still open. Paper money only. Not financial advice.' },
  { wait: 300, agent: 'market_scout', status: 'idle', target: null, text: '' },
  { wait: 200, agent: 'manager', status: 'walking', target: 'owner', text: 'Back with the answer' },
  { wait: 300, agent: 'manager', status: 'talking', target: 'owner', text: 'Demo: one win so far, +$10.17 on paper. Not financial advice.' },
  { wait: 300, agent: 'manager', status: 'idle', target: null, text: '' },
]

export const SCENARIOS: Step[][] = [HEALTH, ALERT, PAPER]

let runs = 0

/** Plays scenario `n` through `emit`; returns a function that cancels it. Each run gets its own
 *  ids, since the log is keyed by them. */
export function playDemo(emit: (e: OfficeEvent) => void, n = 0): () => void {
  const run = ++runs
  const timers: number[] = []
  let t = 0
  SCENARIOS[n % SCENARIOS.length].forEach(({ wait, ...e }, i) => {
    t += wait
    timers.push(window.setTimeout(() => emit({ ...e, id: run * 1000 + i, run_id: `demo-${run}` }), t))
  })
  return () => timers.forEach(clearTimeout)
}

/** How long scenario `n` takes to send all its events. */
export function demoLength(n: number): number {
  return SCENARIOS[n % SCENARIOS.length].reduce((sum, s) => sum + s.wait, 0)
}
