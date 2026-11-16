<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { CoachInnerRepeat, CoachRepeat, CoachStep, CoachWorkout } from '@/features/coach/types'
import type { Units } from '@/features/coach/utils/coachFormat'

import { MetricPill } from '@/components/ui/metric-pill'
import {
  formatDistance,
  formatStepDuration,
  formatStepTarget,
  intensityDotClass,
  isRepeat,
} from '@/features/coach/utils/coachFormat'

defineProps<{
  /** The planned workout. */
  workout: CoachWorkout
  /** The viewer's unit system. */
  units: Units
}>()

const { t } = useI18n()

/** Flattens one level of nesting into rows with an indent level, for a simple list. */
function rows(
  steps: Array<CoachStep | CoachRepeat | CoachInnerRepeat>,
  depth = 0,
): Array<{ depth: number; repeat: number | null; step: CoachStep | null }> {
  return steps.flatMap((item) =>
    isRepeat(item)
      ? [{ depth, repeat: item.count, step: null }, ...rows(item.steps, depth + 1)]
      : [{ depth, repeat: null, step: item }],
  )
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="flex flex-wrap items-center gap-2 text-caption text-muted-foreground">
      <span
        class="size-2 rounded-full"
        :class="intensityDotClass(workout.type)"
        aria-hidden="true"
      />
      <span>{{ t(`coach.workout.type.${workout.type}`) }}</span>
      <span v-if="workout.key" class="text-effort">· {{ t('coach.today.keySession') }}</span>
    </div>

    <div
      v-if="workout.distanceKm || workout.durationMin || workout.target"
      class="flex flex-wrap gap-2"
    >
      <MetricPill
        v-if="workout.distanceKm"
        :label="t('coach.workout.distance')"
        :value="formatDistance(workout.distanceKm, units)"
      />
      <MetricPill
        v-if="workout.durationMin"
        :label="t('coach.workout.duration')"
        :value="t('coach.workout.minutes', { count: workout.durationMin })"
      />
      <MetricPill
        v-if="workout.target"
        :label="t('coach.workout.target')"
        :value="workout.target"
        accent="effort"
      />
    </div>

    <p v-if="workout.structure" class="text-body whitespace-pre-line">{{ workout.structure }}</p>

    <div v-if="workout.steps.length" class="flex flex-col gap-1">
      <h4 class="text-section-heading">{{ t('coach.workout.steps') }}</h4>
      <ol class="flex flex-col gap-1 text-caption">
        <li
          v-for="(row, index) in rows(workout.steps)"
          :key="index"
          class="flex flex-wrap items-baseline gap-x-2"
          :class="row.depth === 1 ? 'pl-4' : row.depth === 2 ? 'pl-8' : ''"
        >
          <template v-if="row.repeat !== null">
            <span class="font-medium">{{ t('coach.workout.repeat', { count: row.repeat }) }}</span>
          </template>
          <template v-else-if="row.step">
            <span class="font-medium">{{ t(`coach.workout.kind.${row.step.kind}`) }}</span>
            <span>{{ formatStepDuration(row.step, units) ?? t('coach.workout.open') }}</span>
            <span v-if="formatStepTarget(row.step, units)" class="text-effort">
              {{ formatStepTarget(row.step, units) }}
            </span>
            <span v-if="row.step.note" class="text-muted-foreground">{{ row.step.note }}</span>
          </template>
        </li>
      </ol>
    </div>

    <p v-if="workout.purpose" class="text-caption italic text-muted-foreground">
      {{ workout.purpose }}
    </p>
  </div>
</template>
