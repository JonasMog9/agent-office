// One timeline for the whole office: actions play one after another, across all robots, in
// the order the events happened. So the Health Coach can't answer before the Manager has
// actually arrived at its desk, and the Manager doesn't leave while the Coach is still talking.

export type Schedule = (ms: number, fn: () => void) => void

export interface Step<T> {
  item: T
  /** Starts the step; returns how long it holds the stage, in ms. */
  play: (item: T, hurry: number) => number
}

/** Under a backlog the office speeds up rather than falling minutes behind the real run. */
export const BACKLOG = 6
export const HURRY = 0.45

export class Timeline<T> {
  private queue: Step<T>[] = []
  private current: Step<T> | null = null
  private schedule: Schedule

  constructor(schedule: Schedule) {
    this.schedule = schedule
  }

  push(step: Step<T>): void {
    this.queue.push(step)
    this.pump()
  }

  /** Put a step at the front (e.g. walking home before the next thing). */
  pushFront(step: Step<T>): void {
    this.queue.unshift(step)
    this.pump()
  }

  /** Steps waiting, plus the one playing. */
  items(): T[] {
    return [...(this.current ? [this.current.item] : []), ...this.queue.map((s) => s.item)]
  }

  waiting(): T[] {
    return this.queue.map((s) => s.item)
  }

  get busy(): boolean {
    return this.current !== null
  }

  private pump(): void {
    if (this.current || !this.queue.length) return
    const step = this.queue.shift()!
    this.current = step
    const hurry = this.queue.length >= BACKLOG ? HURRY : 1
    const ms = Math.max(0, step.play(step.item, hurry))
    this.schedule(ms, () => {
      this.current = null
      this.pump()
    })
  }
}
