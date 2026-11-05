// The health page's data: the backend's /stats/health (with the office key), or a made-up demo.

import { API_URL } from '../office/live'

/** What the Strava subscription cost; this page replaced it. Edit if your price differs. */
export const STRAVA_PER_YEAR = 79.99
export const STRAVA_CURRENCY = 'CA$'

/** Load lines, validated as a set on the dark card surface. */
export const LOAD = { fitness: '#3987e5', fatigue: '#d95926', form: '#199e70' } as const
export const BLUE = '#3987e5'
/** One-hue ramps (light → dark), validated as ordinal: sleep stages and HR zones. */
export const SLEEP_STAGE = { awake: '#cde2fb', rem: '#86b6ef', core: '#3987e5', deep: '#1c5cab' } as const
export const ZONE_RAMP = ['#184f95', '#2a78d6', '#5598e7', '#86b6ef', '#b7d3f6'] as const
export const RACES = ['5K', '10K', 'half marathon', 'marathon'] as const
export const RACE_KM: Record<string, number> = { '5K': 5, '10K': 10, 'half marathon': 21.0975, marathon: 42.195 }

export interface Totals {
  runs: number
  km: number
  hours: number
  climb_m: number
  longest_km: number | null
}
export interface Week {
  week: string
  km: number
  runs: number
  minutes: number
  climb_m: number
}
export interface Method {
  method: string
  seconds: number
  note: string
}
export interface Current {
  distance: string
  as_of?: string
  seconds: number | null
  low?: number | null
  high?: number | null
  confidence?: string | null
  methods?: Method[]
}
export interface PredPoint {
  day: string
  seconds: number
  low: number | null
  high: number | null
}
export interface LoadDay {
  day: string
  fitness: number | null
  fatigue: number | null
  form: number | null
  strain: number | null
}
export interface Vital {
  day: string
  resting_hr: number | null
  hrv: number | null
  respiratory_rate: number | null
  recovery: number | null
  label: 'green' | 'yellow' | 'red' | null
}
export interface Night {
  day: string
  asleep_min: number | null
  deep_min: number | null
  core_min: number | null
  rem_min: number | null
  awake_min: number | null
  performance_pct: number | null
  debt_min: number | null
}
export interface HrZone {
  zone: number
  name: string
  low: number
  high: number
  minutes: number
}
export interface PaceZone {
  name: string
  fast_s_per_km: number
  slow_s_per_km: number
}
export interface Record_ {
  name: string
  distance_m: number
  seconds: number
  day: string
  run: string
}
export interface RunRow {
  day: string
  name: string
  km: number
  moving_s: number | null
  pace_s_per_km: number | null
  avg_hr: number | null
  climb_m: number | null
  cadence_spm: number | null
}
export interface FormDay {
  day: string
  cadence_spm: number | null
  ground_contact_ms: number | null
  vertical_oscillation_cm: number | null
  stride_length_m: number | null
}
export interface PlanWorkout {
  day: string
  kind: string
  km: number
  description: string
}

export interface Health {
  today: string
  generated_at?: string
  summary: {
    vo2max: number | null
    vo2max_change_90d: number | null
    this_week_km: number
    avg_week_km_4w: number | null
    resting_hr: number | null
    resting_hr_30d: number | null
    hrv: number | null
    hrv_30d: number | null
    recovery: number | null
    label: 'green' | 'yellow' | 'red' | null
    fitness: number | null
    fatigue: number | null
    form: number | null
  }
  totals: { last_4_weeks: Totals; year_to_date: Totals; all_time: Totals }
  vo2max: { day: string; value: number }[]
  weekly: Week[]
  calendar: { day: string; km: number }[]
  predictions: { current: Current[]; history: Record<string, PredPoint[]> }
  load: LoadDay[]
  vitals: Vital[]
  sleep: Night[]
  zones: {
    hr: HrZone[]
    hr_rest: number | null
    hr_max: number | null
    window_days: number
    pace: PaceZone[]
    vdot: number | null
    vdot_source: string
  }
  records: Record_[]
  runs: RunRow[]
  form: FormDay[]
  plan: { this_week: { start: string; phase: string; km: number; workouts: PlanWorkout[] }; goal: { race: string | null; date: string | null }; today: PlanWorkout | null } | null
}

export async function fetchHealth(key: string, api = API_URL): Promise<Health | 'locked'> {
  const r = await fetch(new URL('/stats/health', api), { headers: { 'X-Office-Key': key } })
  if (r.status === 401) return 'locked'
  if (!r.ok) throw new Error(`health: HTTP ${r.status}`)
  return r.json()
}

// ---- formatting ----------------------------------------------------------------------------

export function clock(s: number | null | undefined): string {
  if (s == null) return '–'
  const t = Math.round(s)
  const h = Math.floor(t / 3600)
  const m = Math.floor((t % 3600) / 60)
  const sec = t % 60
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}` : `${m}:${String(sec).padStart(2, '0')}`
}
export const pace = (s: number | null | undefined) => (s == null ? '–' : `${clock(s)}/km`)
export function hm(min: number | null | undefined): string {
  if (min == null) return '–'
  const m = Math.round(min)
  return `${Math.floor(m / 60)} h ${m % 60} min`
}
export const shortDay = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

// ---- the demo -------------------------------------------------------------------------------

const iso = (d: Date) => d.toISOString().slice(0, 10)
function addDays(d: Date, n: number): Date {
  const x = new Date(d)
  x.setDate(x.getDate() + n)
  return x
}

/** Made-up numbers with the real shape, for the public page. Deterministic, so it doesn't jump. */
export function demoHealth(end = new Date()): Health {
  const day = (n: number) => iso(addDays(end, -n)) // n days ago
  const wobble = (k: number, a = 1) => Math.sin(k * 0.9) * a + Math.cos(k * 0.37) * a * 0.6

  // runs: most days except Mon/Fri, a long run on Sundays, a parkrun on some Saturdays
  const runs: RunRow[] = []
  const calendar: { day: string; km: number }[] = []
  const byDay = new Map<string, number>()
  for (let n = 364; n >= 0; n--) {
    const d = addDays(end, -n)
    const dow = d.getDay()
    if (dow === 1 || dow === 5 || n % 23 === 0) continue
    const k = 364 - n
    const build = 0.75 + 0.25 * Math.min(1, k / 200)
    const km = Math.round((dow === 0 ? 18 + 4 * Math.sin(k / 30) : dow === 3 ? 10 : 7 + (k % 3)) * build * 10) / 10
    const p = dow === 6 && n % 14 === 6 ? 252 : dow === 0 ? 335 : 318 - Math.round(k / 30)
    byDay.set(iso(d), km)
    runs.push({
      day: iso(d),
      name: dow === 0 ? 'Long run' : dow === 6 && n % 14 === 6 ? 'Demo parkrun' : dow === 3 ? 'Tempo' : 'Easy run',
      km,
      moving_s: Math.round(km * p),
      pace_s_per_km: p,
      avg_hr: dow === 3 ? 162 : 146 + (k % 5),
      climb_m: Math.round(km * 6 + (k % 7) * 3),
      cadence_spm: 168 + (k % 6),
    })
  }
  for (let n = 83; n >= 0; n--) calendar.push({ day: day(n), km: byDay.get(day(n)) ?? 0 })
  runs.reverse()

  // weekly totals, Monday weeks
  const monday = (d: Date) => addDays(d, -((d.getDay() + 6) % 7))
  const weeks = new Map<string, Week>()
  const firstWeek = monday(addDays(end, -7 * 51))
  for (let w = 0; w < 52; w++) {
    const s = iso(addDays(firstWeek, w * 7))
    weeks.set(s, { week: s, km: 0, runs: 0, minutes: 0, climb_m: 0 })
  }
  for (const r of runs) {
    const w = weeks.get(iso(monday(new Date(`${r.day}T12:00:00`))))
    if (!w) continue
    w.km = Math.round((w.km + r.km) * 10) / 10
    w.runs++
    w.minutes += Math.round((r.moving_s ?? 0) / 60)
    w.climb_m += r.climb_m ?? 0
  }
  const weekly = [...weeks.values()]
  const tot = (rs: RunRow[]): Totals => ({
    runs: rs.length,
    km: Math.round(rs.reduce((s, r) => s + r.km, 0) * 10) / 10,
    hours: Math.round(rs.reduce((s, r) => s + (r.moving_s ?? 0), 0) / 360) / 10,
    climb_m: rs.reduce((s, r) => s + (r.climb_m ?? 0), 0),
    longest_km: Math.max(...rs.map((r) => r.km)),
  })
  const year = String(end.getFullYear())

  const vo2max = Array.from({ length: 52 }, (_, i) => ({
    day: day((51 - i) * 7),
    value: Math.round((48.6 + i * 0.07 + 0.35 * Math.sin(i / 3)) * 10) / 10,
  }))

  const load: LoadDay[] = []
  let fit = 48
  let fat = 50
  for (let n = 119; n >= 0; n--) {
    const strain = byDay.get(day(n)) ? 8 + (byDay.get(day(n))! / 3) : 2
    fit += (strain * 5.2 - fit) / 42
    fat += (strain * 5.2 - fat) / 7
    load.push({ day: day(n), fitness: Math.round(fit * 10) / 10, fatigue: Math.round(fat * 10) / 10, form: Math.round((fit - fat) * 10) / 10, strain: Math.round(strain * 10) / 10 })
  }

  const vitals: Vital[] = Array.from({ length: 90 }, (_, i) => {
    const missing = i === 40 || i === 41
    const rec = Math.max(9, Math.min(96, Math.round(60 + 22 * Math.sin(i * 0.7) + 8 * wobble(i))))
    return {
      day: day(89 - i),
      resting_hr: missing ? null : Math.round(51 - i * 0.02 + wobble(i, 1.2)),
      hrv: missing ? null : Math.round(55 + i * 0.05 + wobble(i, 5)),
      respiratory_rate: missing ? null : Math.round((15.4 + wobble(i, 0.3)) * 10) / 10,
      recovery: missing ? null : rec,
      label: missing ? null : rec >= 67 ? 'green' : rec >= 34 ? 'yellow' : 'red',
    }
  })

  const sleep: Night[] = Array.from({ length: 30 }, (_, i) => {
    const asleep = Math.round(440 + 35 * Math.sin(i * 0.8) + 15 * wobble(i))
    const deep = Math.round(asleep * 0.15)
    const rem = Math.round(asleep * 0.22)
    return {
      day: day(29 - i),
      asleep_min: asleep,
      deep_min: deep,
      rem_min: rem,
      core_min: asleep - deep - rem,
      awake_min: Math.round(18 + 8 * Math.abs(Math.sin(i))),
      performance_pct: Math.min(100, Math.round((asleep / 490) * 100)),
      debt_min: Math.round(90 + 60 * Math.sin(i / 4)),
    }
  })

  const base = { '5K': 1225, '10K': 2555, 'half marathon': 5680, marathon: 11980 } as Record<string, number>
  const history: Record<string, PredPoint[]> = {}
  for (const r of RACES) {
    history[r] = Array.from({ length: 26 }, (_, i) => {
      const s = Math.round(base[r] * (1.045 - i * 0.0018 + 0.004 * Math.sin(i / 2)))
      return { day: day((25 - i) * 7), seconds: s, low: Math.round(s * 0.95), high: Math.round(s * 1.05) }
    })
  }
  const current: Current[] = RACES.map((r) => {
    const s = history[r].at(-1)!.seconds
    const methods: Method[] = [
      { method: 'VDOT', seconds: Math.round(s * 0.99), note: 'Demo parkrun 5.0 km in 20.9 min' },
      { method: 'Riegel', seconds: Math.round(s * 1.01), note: 'Demo parkrun 5.0 km in 20.9 min' },
      { method: 'VO2max', seconds: Math.round(s * 0.96), note: 'Apple estimate as VDOT' },
      { method: 'HR model', seconds: Math.round(s * 1.02), note: 'VDOT from your pace at heart rate' },
      ...(r === 'marathon' ? [{ method: 'Tanda', seconds: Math.round(s * 1.04), note: '42 km/week at 5:18/km, last 8 weeks' }] : []),
    ]
    return { distance: r, as_of: day(0), seconds: s, low: Math.round(s * 0.95), high: Math.round(s * 1.05), confidence: 'medium', methods }
  })

  const zones = [
    { zone: 1, name: 'recovery', low: 115, high: 128, minutes: 96 },
    { zone: 2, name: 'aerobic / easy', low: 128, high: 141, minutes: 412 },
    { zone: 3, name: 'tempo', low: 141, high: 154, minutes: 238 },
    { zone: 4, name: 'threshold', low: 154, high: 167, minutes: 74 },
    { zone: 5, name: 'max', low: 167, high: 180, minutes: 12 },
  ]
  const s = vitals.at(-1)!
  return {
    today: day(0),
    generated_at: end.toISOString(),
    summary: {
      vo2max: vo2max.at(-1)!.value,
      vo2max_change_90d: Math.round((vo2max.at(-1)!.value - vo2max.at(-13)!.value) * 10) / 10,
      this_week_km: weekly.at(-1)!.km,
      avg_week_km_4w: Math.round((weekly.slice(-5, -1).reduce((a, w) => a + w.km, 0) / 4) * 10) / 10,
      resting_hr: s.resting_hr,
      resting_hr_30d: 51,
      hrv: s.hrv,
      hrv_30d: 58,
      recovery: s.recovery,
      label: s.label,
      fitness: load.at(-1)!.fitness,
      fatigue: load.at(-1)!.fatigue,
      form: load.at(-1)!.form,
    },
    totals: {
      last_4_weeks: tot(runs.filter((r) => r.day > day(28))),
      year_to_date: tot(runs.filter((r) => r.day.startsWith(year))),
      all_time: tot(runs),
    },
    vo2max,
    weekly,
    calendar,
    predictions: { current, history },
    load,
    vitals,
    sleep,
    zones: {
      hr: zones,
      hr_rest: 50,
      hr_max: 180,
      window_days: 28,
      pace: [
        { name: 'easy', fast_s_per_km: 300, slow_s_per_km: 333 },
        { name: 'marathon', fast_s_per_km: 284, slow_s_per_km: 284 },
        { name: 'threshold', fast_s_per_km: 266, slow_s_per_km: 266 },
        { name: 'interval', fast_s_per_km: 245, slow_s_per_km: 245 },
        { name: 'repetition', fast_s_per_km: 228, slow_s_per_km: 228 },
      ],
      vdot: 48.5,
      vdot_source: 'from the demo 5K prediction (medium confidence)',
    },
    records: [
      { name: '400m', distance_m: 400, seconds: 78, day: day(40), run: 'Demo intervals' },
      { name: '1k', distance_m: 1000, seconds: 222, day: day(40), run: 'Demo intervals' },
      { name: '1 mile', distance_m: 1609, seconds: 371, day: day(76), run: 'Demo mile' },
      { name: '5k', distance_m: 5000, seconds: 1218, day: day(34), run: 'Demo parkrun' },
      { name: '10k', distance_m: 10000, seconds: 2561, day: day(55), run: 'Demo 10K' },
      { name: 'Half-Marathon', distance_m: 21097, seconds: 5741, day: day(120), run: 'Demo half' },
    ],
    runs: runs.slice(0, 15), // newest first
    form: vitals.map((v, i) => ({
      day: v.day,
      cadence_spm: byDay.get(v.day) ? 168 + (i % 6) : null,
      ground_contact_ms: v.resting_hr ? Math.round(248 - i * 0.05 + wobble(i, 3)) : null,
      vertical_oscillation_cm: v.resting_hr ? Math.round((8.9 + wobble(i, 0.2)) * 10) / 10 : null,
      stride_length_m: v.resting_hr ? Math.round((1.12 + i * 0.0004 + wobble(i, 0.02)) * 100) / 100 : null,
    })),
    plan: {
      this_week: {
        start: iso(monday(end)),
        phase: 'build',
        km: 48,
        workouts: [
          { day: iso(monday(end)), kind: 'rest', km: 0, description: 'Rest or cross-train' },
          { day: iso(addDays(monday(end), 1)), kind: 'easy', km: 8, description: '8 km easy at 5:00–5:33/km' },
          { day: iso(addDays(monday(end), 2)), kind: 'tempo', km: 10, description: '10 km with 20 min at threshold (4:26/km)' },
          { day: iso(addDays(monday(end), 3)), kind: 'easy', km: 7, description: '7 km easy, then 6 × 20 s strides' },
          { day: iso(addDays(monday(end), 4)), kind: 'rest', km: 0, description: 'Rest' },
          { day: iso(addDays(monday(end), 5)), kind: 'easy', km: 6, description: '6 km easy' },
          { day: iso(addDays(monday(end), 6)), kind: 'long', km: 17, description: '17 km long run at easy pace' },
        ],
      },
      goal: { race: 'half marathon', date: iso(addDays(end, 63)) },
      today: null,
    },
  }
}
