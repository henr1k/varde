<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RefreshCw, Settings2, Sparkles } from '@lucide/vue'

import type { ReadinessStatus } from '@/features/coach/types'
import type { Units } from '@/features/coach/utils/coachFormat'

import CoachLoadChart from '@/features/coach/components/CoachLoadChart.vue'
import CoachPlanCalendar from '@/features/coach/components/CoachPlanCalendar.vue'
import CoachVolumeChart from '@/features/coach/components/CoachVolumeChart.vue'
import CoachWorkoutDetails from '@/features/coach/components/CoachWorkoutDetails.vue'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { LoadingState } from '@/components/ui/loading-state'
import { MetricPill } from '@/components/ui/metric-pill'
import { useToasts } from '@/composables/useToasts'
import { useCurrentUser } from '@/features/auth/composables/useCurrentUser'
import {
  isUpdatePending,
  useCoachCheckinMutation,
  useCoachContextQuery,
  useCoachDashboardQuery,
  useCoachRefreshMutation,
} from '@/features/coach/composables/useCoach'
import { daysUntil, formatDistance } from '@/features/coach/utils/coachFormat'
import { formatRelativeTime, todayIsoDate } from '@/utils/datetime'
import { inputFieldClass } from '@/components/ui/input'

const { t, locale } = useI18n()
const toasts = useToasts()
const { data: currentUser } = useCurrentUser()
const units = computed<Units>(() =>
  currentUser.value?.units === 'imperial' ? 'imperial' : 'metric',
)

const dashboardQuery = useCoachDashboardQuery()
const dashboard = computed(() => dashboardQuery.data.value)
const report = computed(() => dashboard.value?.report ?? null)
const pending = computed(() => isUpdatePending(dashboard.value))
const today = todayIsoDate()

const todayDay = computed(() => dashboard.value?.days.find((d) => d.date === today) ?? null)
const upcomingRaces = computed(() =>
  (dashboard.value?.races ?? []).filter((r) => r.raceDate >= today),
)
const latestLoad = computed(
  () => (dashboard.value?.load ?? [])[(dashboard.value?.load.length ?? 0) - 1] ?? null,
)

/** Run distance done this week and what is still planned after today. */
const week = computed(() => {
  const days = dashboard.value?.days.slice(0, 7) ?? []
  const done = days.reduce((sum, d) => sum + d.doneKm, 0)
  const remaining = days
    .filter((d) => d.date > today || (d.date === today && !d.doneNames.length))
    .reduce((sum, d) => sum + (d.workout?.distanceKm ?? 0), 0)
  return { done, remaining }
})

const READINESS_VARIANT: Record<ReadinessStatus, 'info' | 'warning' | 'destructive' | 'secondary'> =
  {
    fresh: 'info',
    ready: 'info',
    returning: 'secondary',
    tired: 'warning',
    overreached: 'destructive',
  }

const paragraphs = computed(() =>
  (report.value?.assessment ?? '').split('\n').filter((p) => p.trim()),
)

const refreshMutation = useCoachRefreshMutation()
function refresh(): void {
  refreshMutation.mutate(undefined, {
    onSuccess: () => toasts.success(t('coach.refreshRequested')),
    onError: () => toasts.error(t('coach.refreshError')),
  })
}

const checkinText = ref('')
const checkinMutation = useCoachCheckinMutation()
function sendCheckin(): void {
  const text = checkinText.value.trim()
  if (!text) {
    return
  }
  checkinMutation.mutate(text, {
    onSuccess: () => {
      checkinText.value = ''
      toasts.success(t('coach.checkin.sent'))
    },
    onError: () => toasts.error(t('coach.checkin.error')),
  })
}

const isContextOpen = ref(false)
const contextQuery = useCoachContextQuery(isContextOpen)
</script>

<template>
  <div class="flex flex-col gap-4">
    <!-- Header -->
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex flex-col gap-1">
        <h1 class="text-page-title">{{ t('coach.title') }}</h1>
        <p v-if="report" class="text-caption text-muted-foreground">
          {{
            t('coach.updated', { when: formatRelativeTime(report.createdAt, new Date(), locale) })
          }}
          · {{ report.phase }}
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <Button
          v-if="dashboard?.profile?.enabled && dashboard.configured"
          variant="outline"
          :disabled="pending || refreshMutation.isPending.value"
          @click="refresh"
        >
          <RefreshCw class="size-4" :class="pending && 'animate-spin'" aria-hidden="true" />
          {{ pending ? t('coach.refreshing') : t('coach.refresh') }}
        </Button>
        <Button variant="outline" as-child>
          <RouterLink :to="{ name: 'settings-coach' }">
            <Settings2 class="size-4" aria-hidden="true" />
            {{ t('coach.settingsLink') }}
          </RouterLink>
        </Button>
      </div>
    </div>

    <LoadingState v-if="dashboardQuery.isPending.value" />
    <ErrorState
      v-else-if="dashboardQuery.isError.value"
      :title="t('coach.error.title')"
      :description="t('coach.error.description')"
      @retry="dashboardQuery.refetch()"
    />

    <template v-else-if="dashboard">
      <Alert v-if="!dashboard.configured" kind="warning">
        <p class="font-medium">{{ t('coach.notConfigured.title') }}</p>
        <p>{{ t('coach.notConfigured.description') }}</p>
      </Alert>

      <Card v-if="!dashboard.profile?.enabled">
        <EmptyState
          :title="t('coach.notEnabled.title')"
          :description="t('coach.notEnabled.description')"
        >
          <template #icon><Sparkles class="size-6" aria-hidden="true" /></template>
          <template #action>
            <Button as-child>
              <RouterLink :to="{ name: 'settings-coach' }">{{
                t('coach.notEnabled.action')
              }}</RouterLink>
            </Button>
          </template>
        </EmptyState>
      </Card>

      <template v-else>
        <Alert v-if="pending" kind="info">
          {{ report ? t('coach.pending') : t('coach.firstPlan') }}
        </Alert>
        <Alert v-else-if="dashboard.latestAttempt?.status === 'error'" kind="error">
          {{ t('coach.failed') }}
        </Alert>

        <div v-if="report" class="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <!-- Today -->
          <Card class="flex flex-col gap-3 lg:col-span-2">
            <div class="flex flex-wrap items-center gap-2 text-caption text-muted-foreground">
              <span>{{
                new Date(`${today}T12:00:00`).toLocaleDateString(locale, {
                  weekday: 'long',
                  day: 'numeric',
                  month: 'long',
                })
              }}</span>
              <Badge :variant="READINESS_VARIANT[report.readiness.status]">
                {{ t(`coach.readiness.${report.readiness.status}`) }}
              </Badge>
            </div>
            <h2 class="text-page-title">{{ report.headline }}</h2>
            <p class="text-body">{{ report.todaySummary }}</p>
            <div v-if="todayDay?.workout" class="rounded-input border border-border p-3">
              <h3 class="mb-2 text-item-title">{{ todayDay.workout.title }}</h3>
              <CoachWorkoutDetails :workout="todayDay.workout" :units="units" />
            </div>
            <p v-if="todayDay?.doneNames.length" class="text-caption text-brand">
              {{ t('coach.today.doneToday', { activities: todayDay.doneNames.join(', ') }) }}
            </p>
            <p class="text-caption text-muted-foreground">{{ report.readiness.note }}</p>
          </Card>

          <div class="flex flex-col gap-4">
            <!-- Goals -->
            <Card class="flex flex-col gap-3">
              <h2 class="text-card-heading">{{ t('coach.goals.title') }}</h2>
              <div
                v-for="race in upcomingRaces"
                :key="race.name + race.raceDate"
                class="flex flex-col gap-0.5"
              >
                <div class="flex items-baseline justify-between gap-2">
                  <span class="text-item-title"
                    >{{ race.name }} <Badge variant="outline">{{ race.priority }}</Badge></span
                  >
                  <span class="text-caption text-muted-foreground">
                    {{ t('coach.goals.daysToGo', { days: daysUntil(race.raceDate, today) }) }}
                  </span>
                </div>
                <span class="text-caption text-muted-foreground">
                  {{ race.raceDate
                  }}<template v-if="race.distanceKm">
                    · {{ formatDistance(race.distanceKm, units) }}</template
                  >
                  <template v-if="race.targetTime">
                    · {{ t('coach.goals.goal', { time: race.targetTime }) }}</template
                  >
                </span>
              </div>
              <div
                v-for="goal in report.goalProgress"
                :key="goal.race"
                class="flex flex-col gap-1 border-t border-border pt-2"
              >
                <div class="flex items-center justify-between gap-2">
                  <span class="text-item-title">{{ goal.race }}</span>
                  <Badge
                    :variant="
                      goal.onTrack === 'off_track'
                        ? 'destructive'
                        : goal.onTrack === 'at_risk'
                          ? 'warning'
                          : 'info'
                    "
                  >
                    {{ t(`coach.goals.track.${goal.onTrack}`) }}
                  </Badge>
                </div>
                <span v-if="goal.predicted" class="text-caption">{{
                  t('coach.goals.prediction', { time: goal.predicted })
                }}</span>
                <span class="text-caption text-muted-foreground">{{ goal.summary }}</span>
              </div>
              <p
                v-if="!upcomingRaces.length && !report.goalProgress.length"
                class="text-caption text-muted-foreground"
              >
                {{ t('coach.goals.none') }}
                <RouterLink class="text-primary underline" :to="{ name: 'settings-coach' }">{{
                  t('coach.goals.add')
                }}</RouterLink>
              </p>
            </Card>

            <!-- Numbers -->
            <Card class="flex flex-col gap-3">
              <h2 class="text-card-heading">{{ t('coach.numbers.title') }}</h2>
              <div class="grid grid-cols-2 gap-2">
                <MetricPill
                  :label="t('coach.numbers.thisWeek')"
                  :value="formatDistance(week.done, units)"
                  accent="brand"
                />
                <MetricPill
                  :label="t('coach.numbers.fitness')"
                  :value="latestLoad?.ctl.toFixed(0) ?? '–'"
                  accent="info"
                />
                <MetricPill
                  :label="t('coach.numbers.fatigue')"
                  :value="latestLoad?.atl.toFixed(0) ?? '–'"
                  accent="effort"
                />
                <MetricPill
                  :label="t('coach.numbers.form')"
                  :value="
                    latestLoad ? (latestLoad.tsb > 0 ? '+' : '') + latestLoad.tsb.toFixed(0) : '–'
                  "
                />
              </div>
              <p v-if="week.remaining" class="text-caption text-muted-foreground">
                {{
                  t('coach.numbers.stillPlanned', {
                    distance: formatDistance(week.remaining, units),
                  })
                }}
              </p>
            </Card>
          </div>

          <!-- Plan -->
          <Card class="flex flex-col gap-3 lg:col-span-3">
            <h2 class="text-card-heading">{{ t('coach.plan.title') }}</h2>
            <p class="text-body">
              <span class="font-medium">{{ t('coach.plan.focus') }}:</span> {{ report.weekFocus }}
            </p>
            <CoachPlanCalendar :days="dashboard.days" :today="today" :units="units" />
            <p v-if="report.planChanges" class="text-caption text-muted-foreground">
              <span class="font-medium">{{ t('coach.plan.changes') }}:</span>
              {{ report.planChanges }}
            </p>
          </Card>

          <!-- Coach's read -->
          <Card class="flex flex-col gap-3 lg:col-span-2">
            <h2 class="text-card-heading">{{ t('coach.read.title') }}</h2>
            <p v-for="(paragraph, i) in paragraphs" :key="i" class="text-body">{{ paragraph }}</p>
            <template v-if="report.tips.length">
              <h3 class="text-section-heading">{{ t('coach.read.tips') }}</h3>
              <ul class="list-disc pl-5 text-body">
                <li v-for="tip in report.tips" :key="tip">{{ tip }}</li>
              </ul>
            </template>
          </Card>

          <!-- Watch-outs and check-in -->
          <Card class="flex flex-col gap-3">
            <h2 class="text-card-heading">{{ t('coach.flags.title') }}</h2>
            <ul v-if="report.flags.length" class="list-disc pl-5 text-body">
              <li v-for="flag in report.flags" :key="flag">{{ flag }}</li>
            </ul>
            <p v-else class="text-caption text-muted-foreground">{{ t('coach.flags.none') }}</p>

            <form
              class="flex flex-col gap-2 border-t border-border pt-3"
              @submit.prevent="sendCheckin"
            >
              <label for="coach-checkin" class="text-section-heading">{{
                t('coach.checkin.title')
              }}</label>
              <textarea
                id="coach-checkin"
                v-model="checkinText"
                :class="inputFieldClass"
                rows="3"
                maxlength="2000"
                :placeholder="t('coach.checkin.placeholder')"
                :aria-label="t('coach.checkin.label')"
              />
              <div class="flex items-center justify-between gap-2">
                <span class="text-hint">{{ t('coach.checkin.hint') }}</span>
                <Button
                  type="submit"
                  size="sm"
                  :disabled="!checkinText.trim() || checkinMutation.isPending.value"
                >
                  {{ t('coach.checkin.send') }}
                </Button>
              </div>
            </form>
            <ul v-if="dashboard.checkins.length" class="flex flex-col gap-1">
              <li
                v-for="checkin in dashboard.checkins"
                :key="checkin.id"
                class="text-caption text-muted-foreground"
              >
                <span class="text-foreground"
                  >{{ formatRelativeTime(checkin.createdAt, new Date(), locale) }}:</span
                >
                {{ checkin.text }}
              </li>
            </ul>
          </Card>

          <!-- Charts -->
          <div class="grid grid-cols-1 gap-4 md:grid-cols-2 lg:col-span-3">
            <CoachVolumeChart :weeks="dashboard.weeks" :units="units" />
            <CoachLoadChart :load="dashboard.load" />
          </div>
        </div>

        <div class="flex justify-end">
          <Button
            v-if="dashboard.latestAttempt"
            variant="ghost"
            size="sm"
            @click="isContextOpen = true"
          >
            {{ t('coach.whatTheCoachSaw') }}
          </Button>
        </div>
      </template>
    </template>

    <Dialog v-model:open="isContextOpen">
      <DialogContent :close-label="t('coach.close')" class="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{{ t('coach.contextTitle') }}</DialogTitle>
          <DialogDescription>{{ report?.model }}</DialogDescription>
        </DialogHeader>
        <LoadingState v-if="contextQuery.isPending.value" />
        <p v-else-if="contextQuery.isError.value" class="text-field-error">
          {{ t('coach.contextError') }}
        </p>
        <pre
          v-else
          class="max-h-96 overflow-auto rounded-input bg-muted p-3 text-caption whitespace-pre-wrap"
          >{{ contextQuery.data.value }}</pre>
      </DialogContent>
    </Dialog>
  </div>
</template>
