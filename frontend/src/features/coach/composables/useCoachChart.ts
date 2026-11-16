import {
  onBeforeUnmount,
  onMounted,
  toValue,
  useTemplateRef,
  watch,
  type MaybeRefOrGetter,
} from 'vue'

import type { ChartInstance, ChartRenderOptions } from '@/composables/useChartProvider'

import { useChartProvider } from '@/composables/useChartProvider'
import { useRenderProvidersReady } from '@/providers'

/**
 * Mounts a chart into the component's `chartContainer` ref once the chart provider is ready,
 * updates it when the options change and destroys it on unmount.
 *
 * @param render - Chart options (reactive).
 */
export function useCoachChart(render: MaybeRefOrGetter<ChartRenderOptions>): void {
  const ready = useRenderProvidersReady()
  const container = useTemplateRef<HTMLElement>('chartContainer')
  let instance: ChartInstance | null = null

  /** Mounts the chart once the provider is ready and the container exists. */
  function mountChart(): void {
    if (instance || !container.value || !ready.value) {
      return
    }
    instance = useChartProvider().provider.mount(container.value, toValue(render))
  }

  onMounted(mountChart)
  watch(ready, mountChart)
  watch(
    () => toValue(render),
    (next) => (instance ? instance.update(next) : mountChart()),
  )
  onBeforeUnmount(() => {
    instance?.destroy()
    instance = null
  })
}
