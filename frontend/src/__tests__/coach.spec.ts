import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

import type { CoachDashboard } from '@/features/coach/types'

import i18n from '@/i18n'
import CoachSettingsView from '@/features/coach/views/CoachSettingsView.vue'
import { mapProfile } from '@/features/coach/services/coach'
import {
  formatPaceInput,
  formatStepDuration,
  formatStepTarget,
  optionalNumber,
  parsePace,
} from '@/features/coach/utils/coachFormat'

const calls: string[] = []
const saveProfile = vi.fn<(input: unknown) => Promise<void>>(async (_input: unknown) => {
  calls.push('profile')
})
const saveRaces = vi.fn<(races: unknown) => Promise<void>>(async (_races: unknown) => {
  calls.push('races')
})
const toastError = vi.fn<(message: string) => void>()
const toastSuccess = vi.fn<(message: string) => void>()

const dashboard: CoachDashboard = {
  configured: true,
  modelStatus: null,
  profile: mapProfile({ user_id: 1, enabled: true, available_days: ['Mon', 'Wed', 'Sat'] }),
  races: [],
  report: null,
  latestAttempt: null,
  days: [],
  load: [],
  weeks: [],
  checkins: [],
}

const mutation = (mutateAsync: (v: unknown) => Promise<void>) => ({
  mutateAsync,
  mutate: vi.fn<() => void>(),
  isPending: ref(false),
  data: ref(undefined),
})

vi.mock('@/features/coach/composables/useCoach', () => ({
  useCoachDashboardQuery: () => ({
    data: ref(dashboard),
    isPending: ref(false),
    isError: ref(false),
    refetch: vi.fn<() => void>(),
  }),
  useSaveCoachProfileMutation: () => mutation(saveProfile),
  useSaveCoachRacesMutation: () => mutation(saveRaces),
  useSaveCoachApiKeyMutation: () => mutation(vi.fn<(v: unknown) => Promise<void>>()),
  useDeleteCoachApiKeyMutation: () => mutation(vi.fn<(v: unknown) => Promise<void>>()),
  useCheckCoachModelMutation: () => mutation(vi.fn<(v: unknown) => Promise<void>>()),
}))

vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ success: toastSuccess, error: toastError }),
}))

function mountSettings() {
  return mount(CoachSettingsView, { global: { plugins: [i18n] } })
}

describe('coach settings save', () => {
  beforeEach(() => {
    calls.length = 0
    vi.clearAllMocks()
  })

  it('sends typed numbers as numbers and saves the settings before the races', async () => {
    const wrapper = mountSettings()
    const numberInputs = wrapper.findAll('input[type="number"]')
    // max HR, resting HR, then max weekly hours (race distance appears only when a race exists)
    await numberInputs[0]!.setValue('188')
    await numberInputs[1]!.setValue('')
    await numberInputs[2]!.setValue('6.5')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(toastError).not.toHaveBeenCalled()
    expect(toastSuccess).toHaveBeenCalled()
    expect(calls).toEqual(['profile', 'races'])
    expect(saveProfile.mock.calls[0]![0]).toMatchObject({
      maxHr: 188,
      restHr: null,
      maxWeeklyHours: 6.5,
      availableDays: ['Mon', 'Wed', 'Sat'],
      llmProvider: 'anthropic',
    })
  })

  it('does not save races when the settings are rejected', async () => {
    saveProfile.mockRejectedValueOnce(new Error('rejected'))
    const wrapper = mountSettings()
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(saveRaces).not.toHaveBeenCalled()
    expect(toastError).toHaveBeenCalled()
  })
})

describe('coach form helpers', () => {
  it('reads optional numbers from text or number fields', () => {
    expect(optionalNumber(185)).toBe(185)
    expect(optionalNumber(' 6.5 ')).toBe(6.5)
    expect(optionalNumber('')).toBeNull()
    expect(optionalNumber('abc')).toBeNull()
    expect(optionalNumber(Number.NaN)).toBeNull()
    expect(optionalNumber(null)).toBeNull()
  })

  it('parses and formats paces', () => {
    expect(parsePace('4:45')).toBe(285)
    expect(parsePace('')).toBeNull()
    expect(parsePace('4.45')).toBeUndefined()
    expect(formatPaceInput(285)).toBe('4:45')
  })

  it('formats device-neutral steps in both unit systems', () => {
    const step = {
      kind: 'active' as const,
      duration_type: 'distance' as const,
      duration_value: 1000,
      target_type: 'pace' as const,
      target_low: 300,
      target_high: 320,
      zone: null,
      note: '',
    }
    expect(formatStepDuration(step, 'metric')).toBe('1 km')
    expect(formatStepTarget(step, 'metric')).toBe('5:00–5:20/km')
    expect(formatStepDuration(step, 'imperial')).toBe('0.62 mi')
    expect(
      formatStepDuration({ ...step, duration_type: 'open', duration_value: null }, 'metric'),
    ).toBeNull()
    expect(
      formatStepTarget({ ...step, target_type: 'rpe', target_low: 3, target_high: 3 }, 'metric'),
    ).toBe('RPE 3')
  })
})
