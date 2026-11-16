import type { CoachInnerRepeat, CoachRepeat, CoachStep, WorkoutType } from '@/features/coach/types'

import { kmToMiles } from '@/utils/units'

/** The user's unit system, as stored on the user profile. */
export type Units = 'metric' | 'imperial'

/** Display order of weekdays for availability pickers. */
export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const

/** Workout types grouped by intensity, for the colour dot on calendar cells. */
const INTENSITY: Record<WorkoutType, 'easy' | 'long' | 'hard' | 'race' | 'rest' | 'other'> = {
  easy: 'easy',
  recovery: 'easy',
  strides: 'easy',
  long: 'long',
  tempo: 'hard',
  threshold: 'hard',
  intervals: 'hard',
  hills: 'hard',
  progression: 'hard',
  fartlek: 'hard',
  race: 'race',
  rest: 'rest',
  cross: 'other',
  strength: 'other',
}

/** Tailwind classes for the intensity dot (semantic brand accents only). */
const INTENSITY_DOT: Record<(typeof INTENSITY)[WorkoutType], string> = {
  easy: 'bg-brand',
  long: 'bg-info',
  hard: 'bg-effort',
  race: 'bg-hr',
  rest: 'bg-muted-foreground',
  other: 'bg-goal',
}

/**
 * Returns the dot colour class for a workout type.
 *
 * @param type - The workout type.
 * @returns A background utility class.
 */
export function intensityDotClass(type: WorkoutType): string {
  return INTENSITY_DOT[INTENSITY[type]]
}

/**
 * Formats a distance given in kilometres in the user's units.
 *
 * @param km - Distance in km.
 * @param units - The user's unit system.
 * @returns e.g. "10.0 km" or "6.2 mi".
 */
export function formatDistance(km: number, units: Units): string {
  return units === 'imperial' ? `${kmToMiles(km).toFixed(1)} mi` : `${km.toFixed(1)} km`
}

/**
 * Formats a pace given in seconds per km in the user's units.
 *
 * @param secondsPerKm - Pace in s/km.
 * @param units - The user's unit system.
 * @returns e.g. "5:30/km" or "8:51/mi".
 */
export function formatPace(secondsPerKm: number, units: Units): string {
  const perUnit = units === 'imperial' ? secondsPerKm * 1.609344 : secondsPerKm
  const total = Math.round(perUnit)
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}/${units === 'imperial' ? 'mi' : 'km'}`
}

/**
 * Formats a duration in seconds as "45 s", "2 min" or "1:30 min".
 *
 * @param seconds - Duration in seconds.
 * @returns The formatted duration.
 */
export function formatSeconds(seconds: number): string {
  if (seconds < 60) {
    return `${Math.round(seconds)} s`
  }
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return s === 0 ? `${m} min` : `${m}:${String(s).padStart(2, '0')} min`
}

/**
 * Formats a step's duration. `open` is returned as `null` so the caller can show a translated label.
 *
 * @param step - The step.
 * @param units - The user's unit system.
 * @returns The duration text, or `null` for an open step.
 */
export function formatStepDuration(step: CoachStep, units: Units): string | null {
  if (step.duration_type === 'open' || step.duration_value == null) {
    return null
  }
  if (step.duration_type === 'time') {
    return formatSeconds(step.duration_value)
  }
  const meters = step.duration_value
  if (units === 'imperial') {
    return `${kmToMiles(meters / 1000).toFixed(2)} mi`
  }
  return meters < 1000
    ? `${Math.round(meters)} m`
    : `${(meters / 1000).toFixed(meters % 1000 === 0 ? 0 : 2)} km`
}

/**
 * Formats a step's target. Returns `null` when the step has none.
 *
 * @param step - The step.
 * @param units - The user's unit system.
 * @returns e.g. "5:20–5:40/km", "130–150 bpm", "Z2 · 130–145 bpm", "RPE 3–4".
 */
export function formatStepTarget(step: CoachStep, units: Units): string | null {
  const lo = step.target_low
  const hi = step.target_high
  if (step.target_type === 'none' || lo == null || hi == null) {
    return null
  }
  switch (step.target_type) {
    case 'pace':
      return `${formatPace(lo, units).split('/')[0]}–${formatPace(hi, units)}`
    case 'hr':
      return `${Math.round(lo)}–${Math.round(hi)} bpm`
    case 'hr_zone':
      return `Z${step.zone ?? '?'} · ${Math.round(lo)}–${Math.round(hi)} bpm`
    case 'rpe':
      return lo === hi ? `RPE ${lo}` : `RPE ${lo}–${hi}`
  }
}

/**
 * Narrows a step-list item to a repeat block.
 *
 * @param item - A step or repeat.
 * @returns True for a repeat block.
 */
export function isRepeat(
  item: CoachStep | CoachRepeat | CoachInnerRepeat,
): item is CoachRepeat | CoachInnerRepeat {
  return item.kind === 'repeat'
}

/**
 * Days until a date (local midnight to local midnight).
 *
 * @param isoDate - The target date (YYYY-MM-DD).
 * @param today - Today's date (YYYY-MM-DD).
 * @returns Whole days; negative for past dates.
 */
export function daysUntil(isoDate: string, today: string): number {
  const ms = Date.parse(`${isoDate}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`)
  return Math.round(ms / 86_400_000)
}

/**
 * Reads an optional number from a form field. Vue's `v-model` turns `type="number"` inputs into
 * numbers when they hold a number and leaves an empty field as `''`, so both shapes arrive here.
 *
 * @param value - The field value.
 * @returns The number, or `null` when the field is empty or not a number.
 */
export function optionalNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined) {
    return null
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null
  }
  const trimmed = value.trim()
  if (trimmed === '') {
    return null
  }
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? parsed : null
}

/**
 * Parses a pace typed as "m:ss" into seconds per km.
 *
 * @param text - The typed pace.
 * @returns Seconds per km, `null` for an empty field, or `undefined` when the text is not a pace.
 */
export function parsePace(text: string): number | null | undefined {
  const trimmed = text.trim()
  if (!trimmed) {
    return null
  }
  const match = /^(\d{1,2}):([0-5]\d)$/.exec(trimmed)
  return match ? Number(match[1]) * 60 + Number(match[2]) : undefined
}

/**
 * Formats seconds per km as "m:ss" for the pace input.
 *
 * @param seconds - Seconds per km.
 * @returns The pace text.
 */
export function formatPaceInput(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}
