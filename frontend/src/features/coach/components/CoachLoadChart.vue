<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ChartRenderOptions } from '@/composables/useChartProvider'
import type { CoachDashboard } from '@/features/coach/types'

import { Card } from '@/components/ui/card'
import { themeColor } from '@/lib/themeColor'
import { useCoachChart } from '@/features/coach/composables/useCoachChart'

const props = defineProps<{
  /** Daily fitness and fatigue, oldest first. */
  load: CoachDashboard['load']
}>()

const { t, locale } = useI18n()

/** Fitness (42-day) and fatigue (7-day) as two lines on one load scale. */
const chartRender = computed<ChartRenderOptions>(() => ({
  kind: 'line',
  labels: props.load.map((p) =>
    new Date(`${p.date}T12:00:00`).toLocaleDateString(locale.value, {
      day: 'numeric',
      month: 'short',
    }),
  ),
  series: [
    {
      label: t('coach.charts.fitnessSeries'),
      data: props.load.map((p) => p.ctl),
      color: themeColor('--color-info'),
    },
    {
      label: t('coach.charts.fatigueSeries'),
      data: props.load.map((p) => p.atl),
      color: themeColor('--color-effort'),
    },
  ],
  valueFormat: (value) => value.toFixed(0),
}))

useCoachChart(chartRender)
</script>

<template>
  <Card>
    <h2 class="text-card-heading">{{ t('coach.charts.load') }}</h2>
    <div ref="chartContainer" class="relative mt-3 h-56 w-full min-w-0" />
  </Card>
</template>
