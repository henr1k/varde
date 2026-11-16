import type { Schemas } from '@/types'

/** Raw dashboard payload (snake_case wire shape). */
export type CoachDashboardDto = Schemas['CoachDashboard']
/** Raw coach settings payload. */
export type CoachProfileDto = Schemas['CoachProfileRead']
/** Body for saving coach settings. */
export type CoachProfileUpdateDto = Schemas['CoachProfileUpdate']
/** Raw race payload. */
export type CoachRaceDto = Schemas['CoachRaceRead']
/** Body for one race when replacing the race list. */
export type CoachRaceWriteDto = Schemas['CoachRaceWrite']
/** Raw planned workout. */
export type CoachWorkoutDto = Schemas['CoachWorkout']
/** One step of a planned workout (device-neutral). */
export type CoachStep = Schemas['CoachWorkoutStep']
/** A repeat block (top level). */
export type CoachRepeat = Schemas['CoachRepeat']
/** A repeat nested inside another repeat. */
export type CoachInnerRepeat = Schemas['CoachInnerRepeat']
/** Raw structured report written by the coach. */
export type CoachReportOutputDto = Schemas['CoachReportOutput']

export type Weekday = NonNullable<CoachProfileUpdateDto['long_run_day']>
export type WorkoutType = CoachWorkoutDto['type']
export type ReadinessStatus = CoachReportOutputDto['readiness']['status']
export type GoalTrack = CoachReportOutputDto['goal_progress'][number]['on_track']
export type DayStatus = NonNullable<Schemas['CoachPlanDayRead']['status']>
export type RacePriority = NonNullable<CoachRaceWriteDto['priority']>
export type LlmProvider = NonNullable<CoachProfileUpdateDto['llm_provider']>
export type Effort = NonNullable<CoachProfileUpdateDto['llm_effort']>
/** Which model the coach will use for this user, and whether it can run. */
export type CoachModelStatus = Schemas['CoachModelStatus']
/** Result of a connection check against the user's model provider. */
export type CoachConnectionTest = Schemas['CoachConnectionTest']

/** A planned workout, camel-cased. `steps` keep the device-neutral wire shape. */
export interface CoachWorkout {
  date: string
  type: WorkoutType
  sport: CoachWorkoutDto['sport']
  title: string
  distanceKm: number | null
  durationMin: number | null
  target: string
  structure: string
  purpose: string
  key: boolean
  steps: Array<CoachStep | CoachRepeat>
}

/** The coach's report for one update. */
export interface CoachReport {
  id: number
  createdAt: string
  trigger: string
  model: string
  status: 'running' | 'ok' | 'error'
  error: string | null
  validationIssues: string[]
  headline: string
  todaySummary: string
  readiness: { status: ReadinessStatus; note: string }
  assessment: string
  phase: string
  weekFocus: string
  planChanges: string
  goalProgress: Array<{ race: string; onTrack: GoalTrack; predicted: string; summary: string }>
  flags: string[]
  tips: string[]
}

/** One calendar day: what was planned and what was done. */
export interface CoachDay {
  date: string
  workout: CoachWorkout | null
  doneKm: number
  doneMinutes: number
  doneNames: string[]
  status: DayStatus | null
}

/** Coach settings. */
export interface CoachProfile {
  enabled: boolean
  maxHr: number | null
  restHr: number | null
  thresholdPaceSecPerKm: number | null
  experience: string
  availableDays: Weekday[]
  longRunDay: Weekday | null
  maxWeeklyHours: number | null
  health: string
  preferences: string
  constraints: string
  language: string
  primaryGoal: string
  /** `null` uses the server default (Anthropic). */
  llmProvider: LlmProvider | null
  /** `null` uses the server's default model. */
  llmModel: string
  llmBaseUrl: string
  /** `null` uses the server's default effort. */
  llmEffort: Effort | null
  /** Last characters of the user's own API key, or `null` when none is saved. */
  apiKeyHint: string | null
  updateDueAt: string | null
  updateTrigger: string | null
}

/** The editable settings sent on save (the API key is saved separately). */
export type CoachProfileInput = Omit<CoachProfile, 'updateDueAt' | 'updateTrigger' | 'apiKeyHint'>

/** A race on the calendar. */
export interface CoachRace {
  name: string
  raceDate: string
  distanceKm: number | null
  targetTime: string
  priority: RacePriority
  notes: string
}

/** Everything the coach page shows. */
export interface CoachDashboard {
  configured: boolean
  modelStatus: CoachModelStatus | null
  profile: CoachProfile | null
  races: CoachRace[]
  report: CoachReport | null
  latestAttempt: CoachReport | null
  days: CoachDay[]
  load: Array<{ date: string; load: number; ctl: number; atl: number; tsb: number }>
  weeks: Array<{
    week: string
    runKm: number
    runs: number
    longKm: number
    plannedKm: number | null
  }>
  checkins: Array<{ id: number; text: string; createdAt: string }>
}
