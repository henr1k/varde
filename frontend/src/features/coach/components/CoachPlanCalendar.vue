<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { CoachDay, DayStatus } from '@/features/coach/types'
import type { Units } from '@/features/coach/utils/coachFormat'

import CoachWorkoutDetails from '@/features/coach/components/CoachWorkoutDetails.vue'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { formatDistance, intensityDotClass } from '@/features/coach/utils/coachFormat'
import { cn } from '@/lib/utils'

const props = defineProps<{
  /** Fourteen days, Monday of this week first. */
  days: CoachDay[]
  /** Today's date (YYYY-MM-DD). */
  today: string
  /** The viewer's unit system. */
  units: Units
}>()

const { t, locale } = useI18n()

const weeks = computed(() => [
  { label: t('coach.plan.thisWeek'), days: props.days.slice(0, 7) },
  { label: t('coach.plan.nextWeek'), days: props.days.slice(7, 14) },
])

const STATUS_VARIANT: Record<
  DayStatus,
  'secondary' | 'destructive' | 'warning' | 'info' | 'outline'
> = {
  done: 'info',
  rest: 'secondary',
  partial: 'warning',
  over: 'warning',
  extra: 'warning',
  missed: 'destructive',
  pending: 'outline',
}

/** Formats a calendar date as a short weekday and day of month in the active locale. */
function dayLabel(iso: string): { weekday: string; day: string } {
  const date = new Date(`${iso}T12:00:00`)
  return {
    weekday: date.toLocaleDateString(locale.value, { weekday: 'short' }),
    day: date.toLocaleDateString(locale.value, { day: 'numeric' }),
  }
}

const selected = ref<CoachDay | null>(null)
const isOpen = computed({
  get: () => selected.value !== null,
  set: (open) => {
    if (!open) {
      selected.value = null
    }
  },
})
</script>

<template>
  <div class="flex flex-col gap-3">
    <section v-for="week in weeks" :key="week.label" class="flex flex-col gap-2">
      <h3 class="text-caption text-muted-foreground">{{ week.label }}</h3>
      <ul class="grid grid-cols-1 gap-2 md:grid-cols-7">
        <li v-for="day in week.days" :key="day.date">
          <button
            type="button"
            :class="
              cn(
                'flex h-full w-full flex-col gap-1 rounded-input border border-border p-2 text-left transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring md:min-h-28',
                day.date === today && 'border-primary',
                day.date < today && 'bg-muted/50',
              )
            "
            :aria-label="
              [
                dayLabel(day.date).weekday,
                dayLabel(day.date).day,
                day.workout?.title ?? t('coach.plan.noPlan'),
              ].join(' ')
            "
            @click="selected = day"
          >
            <span
              class="flex items-center justify-between gap-1 text-caption text-muted-foreground"
            >
              <span>{{ dayLabel(day.date).weekday }} {{ dayLabel(day.date).day }}</span>
              <Badge v-if="day.status" :variant="STATUS_VARIANT[day.status]">
                {{ t(`coach.plan.status.${day.status}`) }}
              </Badge>
            </span>
            <template v-if="day.workout">
              <span class="flex items-center gap-1.5 text-caption text-muted-foreground">
                <span
                  class="size-2 rounded-full"
                  :class="intensityDotClass(day.workout.type)"
                  aria-hidden="true"
                />
                {{ t(`coach.workout.type.${day.workout.type}`) }}
              </span>
              <span class="text-item-title">{{ day.workout.title }}</span>
              <span
                v-if="day.workout.distanceKm || day.workout.durationMin"
                class="text-caption text-muted-foreground"
              >
                <template v-if="day.workout.distanceKm">{{
                  formatDistance(day.workout.distanceKm, units)
                }}</template>
                <template v-if="day.workout.distanceKm && day.workout.durationMin"> · </template>
                <template v-if="day.workout.durationMin">
                  {{ t('coach.workout.minutes', { count: day.workout.durationMin }) }}
                </template>
              </span>
            </template>
            <span v-else-if="!day.doneNames.length" class="text-caption text-muted-foreground">
              {{ day.date < today ? t('coach.plan.noPlan') : '' }}
            </span>
            <span v-if="day.doneNames.length" class="mt-auto text-caption text-brand">
              ✓
              {{
                day.doneKm
                  ? formatDistance(day.doneKm, units)
                  : t('coach.workout.minutes', { count: day.doneMinutes })
              }}
            </span>
          </button>
        </li>
      </ul>
    </section>

    <Dialog v-model:open="isOpen">
      <DialogContent v-if="selected" :close-label="t('coach.close')">
        <DialogHeader>
          <DialogTitle>{{ selected.workout?.title ?? t('coach.plan.noPlan') }}</DialogTitle>
          <DialogDescription>
            {{
              new Date(`${selected.date}T12:00:00`).toLocaleDateString(locale, {
                weekday: 'long',
                day: 'numeric',
                month: 'long',
              })
            }}
          </DialogDescription>
        </DialogHeader>
        <CoachWorkoutDetails v-if="selected.workout" :workout="selected.workout" :units="units" />
        <p v-if="selected.doneNames.length" class="text-caption text-brand">
          {{ t('coach.workout.done') }}: {{ selected.doneNames.join(', ') }}
        </p>
      </DialogContent>
    </Dialog>
  </div>
</template>
