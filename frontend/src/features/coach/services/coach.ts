import type {
  CoachDashboard,
  CoachConnectionTest,
  CoachDashboardDto,
  CoachProfile,
  CoachProfileInput,
  CoachProfileDto,
  CoachProfileUpdateDto,
  CoachRace,
  CoachRaceDto,
  CoachRaceWriteDto,
  CoachReport,
  CoachWorkout,
  CoachWorkoutDto,
} from '@/features/coach/types'

import { apiFetch } from '@/services/http'

type ReportDto = NonNullable<CoachDashboardDto['report']>

/**
 * Maps a planned workout to the camel-cased model; steps keep their device-neutral shape.
 *
 * @param dto - Raw workout.
 * @returns The workout model.
 */
export function mapWorkout(dto: CoachWorkoutDto): CoachWorkout {
  return {
    date: dto.date,
    type: dto.type,
    sport: dto.sport,
    title: dto.title,
    distanceKm: dto.distance_km ?? null,
    durationMin: dto.duration_min ?? null,
    target: dto.target,
    structure: dto.structure,
    purpose: dto.purpose,
    key: dto.key,
    steps: dto.steps,
  }
}

/**
 * Maps a stored coach update. A report without content (running or failed) keeps empty text fields.
 *
 * @param dto - Raw report.
 * @returns The report model.
 */
export function mapReport(dto: ReportDto): CoachReport {
  const r = dto.report
  return {
    id: dto.id,
    createdAt: dto.created_at,
    trigger: dto.trigger,
    model: dto.model,
    status: dto.status,
    error: dto.error ?? null,
    validationIssues: dto.validation_issues ?? [],
    headline: r?.headline ?? '',
    todaySummary: r?.today_summary ?? '',
    readiness: { status: r?.readiness.status ?? 'ready', note: r?.readiness.note ?? '' },
    assessment: r?.recent_assessment ?? '',
    phase: r?.phase ?? '',
    weekFocus: r?.week_focus ?? '',
    planChanges: r?.plan_changes ?? '',
    goalProgress: (r?.goal_progress ?? []).map((g) => ({
      race: g.race,
      onTrack: g.on_track,
      predicted: g.predicted,
      summary: g.summary,
    })),
    flags: r?.flags ?? [],
    tips: r?.tips ?? [],
  }
}

/**
 * Maps stored coach settings.
 *
 * @param dto - Raw settings.
 * @returns The settings model.
 */
export function mapProfile(dto: CoachProfileDto): CoachProfile {
  return {
    enabled: dto.enabled,
    maxHr: dto.max_hr ?? null,
    restHr: dto.rest_hr ?? null,
    thresholdPaceSecPerKm: dto.threshold_pace_s_per_km ?? null,
    experience: dto.experience ?? '',
    availableDays: dto.available_days ?? [],
    longRunDay: dto.long_run_day ?? null,
    maxWeeklyHours: dto.max_weekly_hours ?? null,
    health: dto.health ?? '',
    preferences: dto.preferences ?? '',
    constraints: dto.constraints ?? '',
    language: dto.language ?? '',
    primaryGoal: dto.primary_goal ?? '',
    llmProvider: dto.llm_provider ?? null,
    llmModel: dto.llm_model ?? '',
    llmBaseUrl: dto.llm_base_url ?? '',
    llmEffort: dto.llm_effort ?? null,
    apiKeyHint: dto.llm_api_key_hint ?? null,
    updateDueAt: dto.update_due_at ?? null,
    updateTrigger: dto.update_trigger ?? null,
  }
}

/**
 * Maps a stored race.
 *
 * @param dto - Raw race.
 * @returns The race model.
 */
export function mapRace(dto: CoachRaceDto): CoachRace {
  return {
    name: dto.name,
    raceDate: dto.race_date,
    distanceKm: dto.distance_km ?? null,
    targetTime: dto.target_time ?? '',
    priority: dto.priority ?? 'A',
    notes: dto.notes ?? '',
  }
}

/**
 * Maps the dashboard payload.
 *
 * @param dto - Raw dashboard.
 * @returns The dashboard model.
 */
export function mapDashboard(dto: CoachDashboardDto): CoachDashboard {
  return {
    configured: dto.configured,
    modelStatus: dto.model_status ?? null,
    profile: dto.profile ? mapProfile(dto.profile) : null,
    races: dto.races.map(mapRace),
    report: dto.report ? mapReport(dto.report) : null,
    latestAttempt: dto.latest_attempt ? mapReport(dto.latest_attempt) : null,
    days: dto.days.map((d) => ({
      date: d.date,
      workout: d.workout ? mapWorkout(d.workout) : null,
      doneKm: d.done_km,
      doneMinutes: d.done_minutes,
      doneNames: d.done_names,
      status: d.status ?? null,
    })),
    load: dto.load,
    weeks: dto.weeks.map((w) => ({
      week: w.week,
      runKm: w.run_km,
      runs: w.runs,
      longKm: w.long_km,
      plannedKm: w.planned_km ?? null,
    })),
    checkins: dto.checkins.map((c) => ({ id: c.id, text: c.text, createdAt: c.created_at })),
  }
}

/**
 * Fetches the coach dashboard for the signed-in user.
 *
 * @param signal - Optional abort signal.
 * @returns The dashboard.
 * @throws {HttpError} When the request fails.
 */
export async function fetchCoachDashboard(signal?: AbortSignal): Promise<CoachDashboard> {
  return mapDashboard(await apiFetch<CoachDashboardDto>('/coach', { signal }))
}

/**
 * Fetches the context pack the coach saw on its latest update.
 *
 * @param signal - Optional abort signal.
 * @returns The Markdown context.
 * @throws {HttpError} When the request fails (404 before the first update).
 */
export async function fetchCoachContext(signal?: AbortSignal): Promise<string> {
  return apiFetch<string>('/coach/context', { signal, responseType: 'text' })
}

/**
 * Saves coach settings.
 *
 * @param profile - The settings to save.
 * @returns The stored settings.
 * @throws {HttpError} When the request fails.
 */
export async function saveCoachProfile(profile: CoachProfileInput): Promise<CoachProfile> {
  const blank = (value: string) => (value.trim() === '' ? null : value.trim())
  const body: CoachProfileUpdateDto = {
    enabled: profile.enabled,
    max_hr: profile.maxHr,
    rest_hr: profile.restHr,
    threshold_pace_s_per_km: profile.thresholdPaceSecPerKm,
    experience: blank(profile.experience),
    available_days: profile.availableDays,
    long_run_day: profile.longRunDay,
    max_weekly_hours: profile.maxWeeklyHours,
    health: blank(profile.health),
    preferences: blank(profile.preferences),
    constraints: blank(profile.constraints),
    language: blank(profile.language),
    primary_goal: blank(profile.primaryGoal),
    llm_provider: profile.llmProvider,
    llm_model: blank(profile.llmModel),
    llm_base_url: profile.llmProvider === 'openai_compatible' ? blank(profile.llmBaseUrl) : null,
    llm_effort: profile.llmProvider === 'openai_compatible' ? null : profile.llmEffort,
  }
  const dto = await apiFetch<CoachProfileDto>('/coach/profile', {
    method: 'PUT',
    body: JSON.stringify(body),
  })
  return mapProfile(dto)
}

/**
 * Replaces the race calendar.
 *
 * @param races - The full new list.
 * @returns The stored races.
 * @throws {HttpError} When the request fails.
 */
export async function saveCoachRaces(races: CoachRace[]): Promise<CoachRace[]> {
  const body: CoachRaceWriteDto[] = races.map((r) => ({
    name: r.name.trim(),
    race_date: r.raceDate,
    distance_km: r.distanceKm,
    target_time: r.targetTime.trim() || null,
    priority: r.priority,
    notes: r.notes.trim() || null,
  }))
  const dtos = await apiFetch<CoachRaceDto[]>('/coach/races', {
    method: 'PUT',
    body: JSON.stringify(body),
  })
  return dtos.map(mapRace)
}

/**
 * Sends the coach a note.
 *
 * @param text - The note.
 * @throws {HttpError} When the request fails.
 */
export async function sendCoachCheckin(text: string): Promise<void> {
  await apiFetch('/coach/checkins', { method: 'POST', body: JSON.stringify({ text }) })
}

/**
 * Asks for a new coach update.
 *
 * @throws {HttpError} 409 when the coach is not enabled.
 */
export async function requestCoachRefresh(): Promise<void> {
  await apiFetch('/coach/refresh', { method: 'POST' })
}

/**
 * Saves the user's own API key. The key is stored encrypted and never returned.
 *
 * @param apiKey - The key.
 * @returns The stored settings (with only the key's last characters).
 * @throws {HttpError} When the request fails.
 */
export async function saveCoachApiKey(apiKey: string): Promise<CoachProfile> {
  const dto = await apiFetch<CoachProfileDto>('/coach/api-key', {
    method: 'PUT',
    body: JSON.stringify({ api_key: apiKey.trim() }),
  })
  return mapProfile(dto)
}

/**
 * Removes the user's own API key.
 *
 * @throws {HttpError} When the request fails.
 */
export async function deleteCoachApiKey(): Promise<void> {
  await apiFetch('/coach/api-key', { method: 'DELETE', responseType: 'void' })
}

/**
 * Checks the saved model settings against the provider without generating a plan.
 *
 * @returns Whether the provider accepted the credentials and offers the model.
 * @throws {HttpError} When the request fails.
 */
export async function checkCoachModel(): Promise<CoachConnectionTest> {
  return apiFetch<CoachConnectionTest>('/coach/model/test', { method: 'POST' })
}
