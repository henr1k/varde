import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { storeToRefs } from 'pinia'
import { useMutation, useQuery } from '@tanstack/vue-query'

import type {
  CoachConnectionTest,
  CoachDashboard,
  CoachProfile,
  CoachProfileInput,
  CoachRace,
} from '@/features/coach/types'

import { queryKeys } from '@/services/queryKeys'
import { useAuthStore } from '@/features/auth/stores/auth'
import { useInvalidatingMutation } from '@/composables/useInvalidatingMutation'
import {
  checkCoachModel,
  deleteCoachApiKey,
  saveCoachApiKey,
  fetchCoachContext,
  fetchCoachDashboard,
  requestCoachRefresh,
  saveCoachProfile,
  saveCoachRaces,
  sendCoachCheckin,
} from '@/features/coach/services/coach'

/** How often the dashboard is re-read while the coach is working on an update. */
const PENDING_POLL_MS = 10_000

/**
 * Whether an update is requested or running, so the page should keep polling.
 *
 * @param dashboard - The latest dashboard, if loaded.
 * @returns True while a new plan is on its way.
 */
export function isUpdatePending(dashboard: CoachDashboard | undefined): boolean {
  if (!dashboard?.profile?.enabled || !dashboard.configured) {
    return false
  }
  return Boolean(dashboard.profile.updateDueAt) || dashboard.latestAttempt?.status === 'running'
}

/**
 * The coach dashboard. Polls while an update is pending.
 *
 * @returns The dashboard query.
 */
export function useCoachDashboardQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  return useQuery({
    queryKey: queryKeys.coach.dashboard(),
    queryFn: ({ signal }) => fetchCoachDashboard(signal),
    enabled: isAuthenticated,
    refetchInterval: (query) => (isUpdatePending(query.state.data) ? PENDING_POLL_MS : false),
  })
}

/**
 * The context pack behind the latest update; fetched only while `enabled` is true.
 *
 * @param enabled - Whether to fetch (e.g. while the dialog is open).
 * @returns The context query.
 */
export function useCoachContextQuery(enabled: MaybeRefOrGetter<boolean>) {
  return useQuery({
    queryKey: queryKeys.coach.context(),
    queryFn: ({ signal }) => fetchCoachContext(signal),
    enabled: computed(() => toValue(enabled)),
  })
}

/** Saves coach settings; a new plan follows on the server. */
export function useSaveCoachProfileMutation() {
  return useInvalidatingMutation<CoachProfile, CoachProfileInput>({
    mutationKey: queryKeys.coach.all(),
    mutationFn: saveCoachProfile,
  })
}

/** Replaces the race calendar. */
export function useSaveCoachRacesMutation() {
  return useInvalidatingMutation<CoachRace[], CoachRace[]>({
    mutationKey: queryKeys.coach.all(),
    mutationFn: saveCoachRaces,
  })
}

/** Sends the coach a note. */
export function useCoachCheckinMutation() {
  return useInvalidatingMutation<void, string>({
    mutationKey: queryKeys.coach.all(),
    mutationFn: sendCoachCheckin,
  })
}

/** Asks for a new update now. */
export function useCoachRefreshMutation() {
  return useInvalidatingMutation<void, void>({
    mutationKey: queryKeys.coach.all(),
    mutationFn: () => requestCoachRefresh(),
  })
}

/** Saves the user's own API key. */
export function useSaveCoachApiKeyMutation() {
  return useInvalidatingMutation<CoachProfile, string>({
    mutationKey: queryKeys.coach.all(),
    mutationFn: saveCoachApiKey,
  })
}

/** Removes the user's own API key. */
export function useDeleteCoachApiKeyMutation() {
  return useInvalidatingMutation<void, void>({
    mutationKey: queryKeys.coach.all(),
    mutationFn: () => deleteCoachApiKey(),
  })
}

/** Checks the saved model settings against the provider (no invalidation needed). */
export function useCheckCoachModelMutation() {
  return useMutation<CoachConnectionTest, Error, void>({ mutationFn: () => checkCoachModel() })
}
