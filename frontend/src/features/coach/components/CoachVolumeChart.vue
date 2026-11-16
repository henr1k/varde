<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ChartRenderOptions } from '@/composables/useChartProvider'
import type { CoachDashboard } from '@/features/coach/types'
import type { Units } from '@/features/coach/utils/coachFormat'

import { Card } from '@/components/ui/card'
import { themeColor } from '@/lib/themeColor'
import { useCoachChart } from '@/features/coach/composables/useCoachChart'
import { kmToMiles } from '@/utils/units'

const props = defineProps<{
  /** Weekly totals, oldest first; the last entry may be next week's plan only. */
  weeks: CoachDashboard['weeks']
  /** The viewer's unit system. */
  units: Units
}>()

const { t, locale } = useI18n()

const toUnit = (km: number) =>
  Math.round((props.units === 'imperial' ? kmToMiles(km) : km) * 10) / 10

/** Weekly run distance as bars, with planned distance as a dashed second series. */
const chartRender = computed<ChartRenderOptions>(() => ({
  kind: 'bar',
  labels: props.weeks.map((w) =>
    new Date(`${w.week}T12:00:00`).toLocaleDateString(locale.value, {
      day: 'numeric',
      month: 'short',
    }),
  ),
  series: [
    {
      label: t('coach.charts.volumeSeries'),
      data: props.weeks.map((w) => toUnit(w.runKm)),
      color: themeColor('--color-brand'),
    },
    {
      label: t('coach.charts.plannedSeries'),
      data: props.weeks.map((w) => toUnit(w.plannedKm ?? 0)),
      color: themeColor('--color-info'),
      dashed: true,
    },
  ],
  valueFormat: (value) => `${value} ${props.units === 'imperial' ? 'mi' : 'km'}`,
}))

useCoachChart(chartRender)
</script>

<template>
  <Card>
    <h2 class="text-card-heading">{{ t('coach.charts.volume') }}</h2>
    <div ref="chartContainer" class="relative mt-3 h-56 w-full min-w-0" />
  </Card>
</template>
