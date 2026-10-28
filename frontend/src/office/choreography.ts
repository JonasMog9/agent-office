// Turns agent events (the backend's {agent, status, target, text}) into what a character does.
// Pure functions, so the rules are testable without a canvas.

export type AgentId = 'manager' | 'health_coach' | 'market_scout' | 'paper_trader'
export type Status = 'idle' | 'thinking' | 'walking' | 'working' | 'talking'

export interface OfficeEvent {
  id: number
  agent: AgentId
  status: Status
  target: string | null
  text: string
  at?: string
  run_id?: string | null
}

export const AGENTS: AgentId[] = ['health_coach', 'manager', 'market_scout', 'paper_trader']
export const NAMES: Record<AgentId, string> = {
  manager: 'Manager',
  health_coach: 'Health Coach',
  market_scout: 'Market Scout',
  paper_trader: 'Paper Trader',
}

// Where a character goes: its own desk, another agent's desk, or the door (out to the owner).
export type Spot = { desk: AgentId } | { visit: AgentId } | { door: true }

export type Action =
  | { kind: 'think'; agent: AgentId }
  | { kind: 'walk'; agent: AgentId; to: Spot }
  | { kind: 'work'; agent: AgentId; label: string }
  | { kind: 'talk'; agent: AgentId; text: string; to: string | null }
  | { kind: 'idle'; agent: AgentId }

const isAgent = (x: string | null): x is AgentId => AGENTS.includes(x as AgentId)

export function toAction(e: OfficeEvent): Action {
  switch (e.status) {
    case 'thinking':
      return { kind: 'think', agent: e.agent }
    case 'walking':
      // To another agent: visit their desk. To the owner: the door, where answers go out to
      // Telegram. Anything else: back to your own desk.
      if (isAgent(e.target) && e.target !== e.agent)
        return { kind: 'walk', agent: e.agent, to: { visit: e.target } }
      return { kind: 'walk', agent: e.agent, to: e.target === 'owner' ? { door: true } : { desk: e.agent } }
    case 'working':
      return { kind: 'work', agent: e.agent, label: e.text || e.target || 'working' }
    case 'talking':
      return { kind: 'talk', agent: e.agent, text: e.text, to: e.target }
    default:
      return { kind: 'idle', agent: e.agent }
  }
}

// How long each action holds the stage, so a fast burst of events still reads as a story.
export function duration(a: Action): number {
  switch (a.kind) {
    case 'think':
      return 900
    case 'walk':
      return 1400
    case 'work':
      return 1500
    case 'talk':
      // ~ reading speed: 2.5 s minimum, 8 s maximum
      return Math.min(8000, Math.max(2500, a.text.length * 45))
    default:
      return 300
  }
}

// Speech bubbles stay small; the full text is in the log beside the office.
export function bubbleText(text: string, max = 140): string {
  const clean = text.replace(/\*\*/g, '').replace(/\s+/g, ' ').trim()
  return clean.length <= max ? clean : clean.slice(0, max - 1).trimEnd() + '…'
}
