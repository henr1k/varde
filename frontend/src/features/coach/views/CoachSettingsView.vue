<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Plus, Trash2 } from '@lucide/vue'

import type {
  CoachDashboard,
  CoachRace,
  Effort,
  LlmProvider,
  RacePriority,
  Weekday,
} from '@/features/coach/types'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ErrorState } from '@/components/ui/error-state'
import { FormField } from '@/components/ui/form-field'
import { Input, inputFieldClass } from '@/components/ui/input'
import { LoadingState } from '@/components/ui/loading-state'
import { Select } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { useToasts } from '@/composables/useToasts'
import {
  useCheckCoachModelMutation,
  useCoachDashboardQuery,
  useDeleteCoachApiKeyMutation,
  useSaveCoachApiKeyMutation,
  useSaveCoachProfileMutation,
  useSaveCoachRacesMutation,
} from '@/features/coach/composables/useCoach'
import {
  WEEKDAYS,
  formatPaceInput,
  optionalNumber,
  parsePace,
} from '@/features/coach/utils/coachFormat'
import { HttpError } from '@/services/http'

const { t } = useI18n()
const toasts = useToasts()

const dashboardQuery = useCoachDashboardQuery()
const saveProfile = useSaveCoachProfileMutation()
const saveRaces = useSaveCoachRacesMutation()

/** Form state as strings, so empty inputs stay empty instead of becoming 0. */
const form = reactive({
  enabled: false,
  primaryGoal: '',
  maxHr: '' as string | number,
  restHr: '' as string | number,
  thresholdPace: '',
  experience: '',
  language: '',
  availableDays: [...WEEKDAYS] as Weekday[],
  longRunDay: '' as Weekday | '',
  maxWeeklyHours: '' as string | number,
  health: '',
  preferences: '',
  constraints: '',
  llmProvider: 'anthropic' as LlmProvider,
  llmModel: '',
  llmBaseUrl: '',
  llmEffort: '' as Effort | '',
})
const races = ref<Array<CoachRace & { key: number }>>([])
let nextKey = 0

/** Fills the form from the stored settings, once, when they first load. */
function fill(dashboard: CoachDashboard): void {
  const p = dashboard.profile
  if (p) {
    Object.assign(form, {
      enabled: p.enabled,
      primaryGoal: p.primaryGoal,
      maxHr: p.maxHr?.toString() ?? '',
      restHr: p.restHr?.toString() ?? '',
      thresholdPace: p.thresholdPaceSecPerKm ? formatPaceInput(p.thresholdPaceSecPerKm) : '',
      experience: p.experience,
      language: p.language,
      availableDays: p.availableDays.length ? [...p.availableDays] : [...WEEKDAYS],
      longRunDay: p.longRunDay ?? '',
      maxWeeklyHours: p.maxWeeklyHours?.toString() ?? '',
      health: p.health,
      preferences: p.preferences,
      constraints: p.constraints,
      llmProvider: p.llmProvider ?? 'anthropic',
      llmModel: p.llmModel,
      llmBaseUrl: p.llmBaseUrl,
      llmEffort: p.llmEffort ?? '',
    })
  }
  races.value = dashboard.races.map((r) => ({ ...r, key: nextKey++ }))
}

let filled = false
watch(
  () => dashboardQuery.data.value,
  (dashboard) => {
    if (dashboard && !filled) {
      filled = true
      fill(dashboard)
    }
  },
  { immediate: true },
)

const paceError = computed(() =>
  parsePace(form.thresholdPace) === undefined
    ? t('coach.settings.thresholdPaceInvalid')
    : undefined,
)

function toggleDay(day: Weekday): void {
  form.availableDays = form.availableDays.includes(day)
    ? form.availableDays.filter((d) => d !== day)
    : WEEKDAYS.filter((d) => d === day || form.availableDays.includes(d))
}

function addRace(): void {
  races.value.push({
    key: nextKey++,
    name: '',
    raceDate: '',
    distanceKm: null,
    targetTime: '',
    priority: 'A',
    notes: '',
  })
}

function removeRace(key: number): void {
  races.value = races.value.filter((r) => r.key !== key)
}

/** Model ids offered as suggestions; any id the provider accepts can be typed. */
const MODEL_SUGGESTIONS: Record<LlmProvider, string[]> = {
  anthropic: ['claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5'],
  openai_compatible: [],
}
const EFFORTS: Effort[] = ['low', 'medium', 'high', 'xhigh', 'max']

const modelStatus = computed(() => dashboardQuery.data.value?.modelStatus ?? null)
const apiKeyHint = computed(() => dashboardQuery.data.value?.profile?.apiKeyHint ?? null)
const apiKey = ref('')
const saveKey = useSaveCoachApiKeyMutation()
const deleteKey = useDeleteCoachApiKeyMutation()
const checkModel = useCheckCoachModelMutation()

function saveApiKey(): void {
  saveKey.mutate(apiKey.value, {
    onSuccess: () => {
      apiKey.value = ''
      toasts.success(t('coach.settings.model.keySaved'))
    },
    onError: () => toasts.error(t('coach.settings.model.keyError')),
  })
}

function removeApiKey(): void {
  deleteKey.mutate(undefined, {
    onSuccess: () => toasts.success(t('coach.settings.model.keyRemoved')),
    onError: () => toasts.error(t('coach.settings.model.keyError')),
  })
}

function runCheck(): void {
  checkModel.mutate(undefined, {
    onError: () => toasts.error(t('coach.settings.model.checkError')),
  })
}

const isSaving = computed(() => saveProfile.isPending.value || saveRaces.isPending.value)

/** The server's own explanation for a rejected save, when it gave one in plain text. */
function saveErrorText(error: unknown): string {
  if (error instanceof HttpError && typeof error.detail === 'string' && error.status < 500) {
    return `${t('coach.settings.saveError')} ${error.detail}`
  }
  return t('coach.settings.saveError')
}

/**
 * Saves the settings, then the races. The settings go first because they are the part the
 * server validates most (e.g. a model server URL), so a rejected save stores nothing.
 */
async function save(): Promise<void> {
  const pace = parsePace(form.thresholdPace)
  if (pace === undefined) {
    return
  }
  try {
    await saveProfile.mutateAsync({
      enabled: form.enabled,
      maxHr: optionalNumber(form.maxHr),
      restHr: optionalNumber(form.restHr),
      thresholdPaceSecPerKm: pace,
      experience: form.experience,
      availableDays: form.availableDays,
      longRunDay: form.longRunDay || null,
      maxWeeklyHours: optionalNumber(form.maxWeeklyHours),
      health: form.health,
      preferences: form.preferences,
      constraints: form.constraints,
      language: form.language,
      primaryGoal: form.primaryGoal,
      llmProvider: form.llmProvider,
      llmModel: form.llmModel,
      llmBaseUrl: form.llmBaseUrl,
      llmEffort: form.llmEffort || null,
    })
    await saveRaces.mutateAsync(
      races.value
        .filter((r) => r.name.trim() && r.raceDate)
        .map((race) => ({
          name: race.name,
          raceDate: race.raceDate,
          distanceKm: optionalNumber(race.distanceKm),
          targetTime: race.targetTime,
          priority: race.priority,
          notes: race.notes,
        })),
    )
    toasts.success(t('coach.settings.saved'))
  } catch (error) {
    toasts.error(saveErrorText(error))
  }
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="flex flex-col gap-1">
      <h1 class="text-page-title">{{ t('coach.settings.title') }}</h1>
      <p class="text-body">{{ t('coach.settings.subtitle') }}</p>
    </div>

    <LoadingState v-if="dashboardQuery.isPending.value" />
    <ErrorState
      v-else-if="dashboardQuery.isError.value"
      :title="t('coach.error.title')"
      :description="t('coach.error.description')"
      @retry="dashboardQuery.refetch()"
    />

    <form v-else class="flex flex-col gap-3" @submit.prevent="save">
      <Card class="flex items-start justify-between gap-4">
        <div class="flex flex-col gap-1">
          <span class="text-item-title">{{ t('coach.settings.enabled') }}</span>
          <span class="text-hint">{{ t('coach.settings.enabledHint') }}</span>
        </div>
        <Switch v-model="form.enabled" :aria-label="t('coach.settings.enabled')" />
      </Card>

      <Card class="flex flex-col gap-3">
        <div class="flex flex-col gap-1">
          <h2 class="text-card-heading">{{ t('coach.settings.model.title') }}</h2>
          <p class="text-hint">{{ t('coach.settings.model.subtitle') }}</p>
        </div>
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <FormField :label="t('coach.settings.model.provider')">
            <template #default="{ fieldId }">
              <Select :id="fieldId" v-model="form.llmProvider">
                <option value="anthropic">
                  {{ t('coach.settings.model.providers.anthropic') }}
                </option>
                <option value="openai_compatible">
                  {{ t('coach.settings.model.providers.openai_compatible') }}
                </option>
              </Select>
            </template>
          </FormField>
          <FormField
            :label="t('coach.settings.model.model')"
            :hint="
              form.llmProvider === 'anthropic'
                ? t('coach.settings.model.modelHintAnthropic')
                : t('coach.settings.model.modelHintOpenai')
            "
          >
            <template #default="{ fieldId, describedBy }">
              <Input
                :id="fieldId"
                v-model="form.llmModel"
                list="coach-model-suggestions"
                maxlength="200"
                :aria-describedby="describedBy"
                :placeholder="
                  form.llmProvider === 'anthropic' ? 'claude-opus-5-5' : 'gpt-5.1 / llama3.1'
                "
              />
            </template>
          </FormField>
          <div v-if="form.llmProvider === 'openai_compatible'" class="sm:col-span-2">
            <FormField
              :label="t('coach.settings.model.baseUrl')"
              :hint="t('coach.settings.model.baseUrlHint')"
            >
              <template #default="{ fieldId: urlFieldId, describedBy: urlDescribedBy }">
                <Input
                  :id="urlFieldId"
                  v-model="form.llmBaseUrl"
                  inputmode="url"
                  maxlength="500"
                  :placeholder="t('coach.settings.model.baseUrlPlaceholder')"
                  :aria-describedby="urlDescribedBy"
                />
              </template>
            </FormField>
          </div>
          <FormField
            v-if="form.llmProvider === 'anthropic'"
            :label="t('coach.settings.model.effort')"
            :hint="t('coach.settings.model.effortHint')"
          >
            <template #default="{ fieldId, describedBy }">
              <Select :id="fieldId" v-model="form.llmEffort" :aria-describedby="describedBy">
                <option value="">{{ t('coach.settings.model.serverDefault') }}</option>
                <option v-for="e in EFFORTS" :key="e" :value="e">{{ e }}</option>
              </Select>
            </template>
          </FormField>
        </div>

        <datalist id="coach-model-suggestions">
          <option v-for="m in MODEL_SUGGESTIONS[form.llmProvider]" :key="m" :value="m"></option>
        </datalist>

        <div class="flex flex-col gap-2 border-t border-border pt-3">
          <h3 class="text-section-heading">{{ t('coach.settings.model.apiKey') }}</h3>
          <p class="text-hint">
            {{
              apiKeyHint
                ? t('coach.settings.model.keySavedHint', { hint: apiKeyHint })
                : t('coach.settings.model.noKeyHint')
            }}
          </p>
          <div class="flex flex-col gap-2 sm:flex-row">
            <Input
              v-model="apiKey"
              type="password"
              autocomplete="off"
              maxlength="500"
              :aria-label="t('coach.settings.model.apiKey')"
              :placeholder="
                apiKeyHint
                  ? t('coach.settings.model.replaceKey')
                  : t('coach.settings.model.pasteKey')
              "
            />
            <Button
              type="button"
              variant="outline"
              :disabled="apiKey.trim().length < 8 || saveKey.isPending.value"
              @click="saveApiKey"
            >
              {{ t('coach.settings.model.saveKey') }}
            </Button>
            <Button
              v-if="apiKeyHint"
              type="button"
              variant="ghost"
              :disabled="deleteKey.isPending.value"
              @click="removeApiKey"
            >
              {{ t('coach.settings.model.removeKey') }}
            </Button>
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-3 border-t border-border pt-3">
          <Button
            type="button"
            variant="outline"
            :disabled="checkModel.isPending.value"
            @click="runCheck"
          >
            {{ t('coach.settings.model.check') }}
          </Button>
          <span
            v-if="checkModel.data.value"
            class="text-caption"
            :class="checkModel.data.value.ok ? 'text-brand' : 'text-destructive'"
            aria-live="polite"
          >
            {{ checkModel.data.value.detail }}
          </span>
          <span v-else-if="modelStatus" class="text-caption text-muted-foreground">
            {{
              modelStatus.usable
                ? t('coach.settings.model.using', { model: modelStatus.detail })
                : modelStatus.detail
            }}
          </span>
        </div>
        <p class="text-hint">{{ t('coach.settings.model.checkHint') }}</p>
      </Card>

      <Card class="flex flex-col gap-3">
        <h2 class="text-card-heading">{{ t('coach.settings.goalsTitle') }}</h2>
        <FormField :label="t('coach.settings.primaryGoal')">
          <template #default="{ fieldId }">
            <textarea
              :id="fieldId"
              v-model="form.primaryGoal"
              :class="inputFieldClass"
              rows="2"
              maxlength="2000"
              :placeholder="t('coach.settings.primaryGoalPlaceholder')"
            />
          </template>
        </FormField>

        <div class="flex flex-col gap-1">
          <h3 class="text-section-heading">{{ t('coach.settings.racesTitle') }}</h3>
          <p class="text-hint">{{ t('coach.settings.racesHint') }}</p>
        </div>
        <div
          v-for="race in races"
          :key="race.key"
          class="grid grid-cols-2 gap-2 border-t border-border pt-3 md:grid-cols-12 md:items-end"
        >
          <FormField :label="t('coach.settings.raceName')" class="col-span-2 md:col-span-4">
            <template #default="{ fieldId }"
              ><Input :id="fieldId" v-model="race.name" maxlength="250"
            /></template>
          </FormField>
          <FormField :label="t('coach.settings.raceDate')" class="md:col-span-2">
            <template #default="{ fieldId }"
              ><Input :id="fieldId" v-model="race.raceDate" type="date"
            /></template>
          </FormField>
          <FormField :label="t('coach.settings.raceDistance')" class="md:col-span-2">
            <template #default="{ fieldId }">
              <input
                :id="fieldId"
                v-model.number="race.distanceKm"
                :class="inputFieldClass"
                type="number"
                min="0.1"
                step="0.1"
                inputmode="decimal"
              />
            </template>
          </FormField>
          <FormField :label="t('coach.settings.raceTarget')" class="md:col-span-2">
            <template #default="{ fieldId }">
              <Input :id="fieldId" v-model="race.targetTime" maxlength="20" placeholder="1:45:00" />
            </template>
          </FormField>
          <FormField :label="t('coach.settings.racePriority')" class="md:col-span-1">
            <template #default="{ fieldId }">
              <Select :id="fieldId" v-model="race.priority">
                <option v-for="p in ['A', 'B', 'C'] as RacePriority[]" :key="p" :value="p">
                  {{ p }}
                </option>
              </Select>
            </template>
          </FormField>
          <div class="flex justify-end md:col-span-1">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              :aria-label="t('coach.settings.removeRace', { name: race.name })"
              @click="removeRace(race.key)"
            >
              <Trash2 class="size-4" aria-hidden="true" />
            </Button>
          </div>
          <FormField :label="t('coach.settings.raceNotes')" class="col-span-2 md:col-span-12">
            <template #default="{ fieldId }"
              ><Input :id="fieldId" v-model="race.notes" maxlength="1000"
            /></template>
          </FormField>
        </div>
        <Button type="button" variant="outline" class="self-start" @click="addRace">
          <Plus class="size-4" aria-hidden="true" />
          {{ t('coach.settings.addRace') }}
        </Button>
      </Card>

      <Card class="flex flex-col gap-3">
        <h2 class="text-card-heading">{{ t('coach.settings.aboutTitle') }}</h2>
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <FormField :label="t('coach.settings.maxHr')" :hint="t('coach.settings.maxHrHint')">
            <template #default="{ fieldId, describedBy }">
              <input
                :id="fieldId"
                v-model="form.maxHr"
                :class="inputFieldClass"
                type="number"
                min="100"
                max="230"
                :aria-describedby="describedBy"
              />
            </template>
          </FormField>
          <FormField :label="t('coach.settings.restHr')" :hint="t('coach.settings.restHrHint')">
            <template #default="{ fieldId, describedBy }">
              <input
                :id="fieldId"
                v-model="form.restHr"
                :class="inputFieldClass"
                type="number"
                min="25"
                max="110"
                :aria-describedby="describedBy"
              />
            </template>
          </FormField>
          <FormField
            :label="t('coach.settings.thresholdPace')"
            :hint="t('coach.settings.thresholdPaceHint')"
            :error="paceError"
          >
            <template #default="{ fieldId, describedBy }">
              <Input
                :id="fieldId"
                v-model="form.thresholdPace"
                placeholder="4:45"
                :aria-describedby="describedBy"
              />
            </template>
          </FormField>
          <FormField :label="t('coach.settings.language')">
            <template #default="{ fieldId }"
              ><Input :id="fieldId" v-model="form.language" maxlength="50" placeholder="English"
            /></template>
          </FormField>
        </div>
        <FormField :label="t('coach.settings.experience')">
          <template #default="{ fieldId }">
            <textarea
              :id="fieldId"
              v-model="form.experience"
              :class="inputFieldClass"
              rows="2"
              maxlength="2000"
              :placeholder="t('coach.settings.experiencePlaceholder')"
            />
          </template>
        </FormField>
      </Card>

      <Card class="flex flex-col gap-3">
        <h2 class="text-card-heading">{{ t('coach.settings.availabilityTitle') }}</h2>
        <fieldset class="flex flex-col gap-2">
          <legend class="mb-1 text-section-heading">{{ t('coach.settings.availableDays') }}</legend>
          <div class="flex flex-wrap gap-2">
            <label
              v-for="day in WEEKDAYS"
              :key="day"
              class="flex cursor-pointer items-center gap-2 rounded-input border border-border px-3 py-1.5 text-body"
            >
              <input
                type="checkbox"
                :checked="form.availableDays.includes(day)"
                @change="toggleDay(day)"
              />
              {{ t(`coach.settings.weekday.${day}`) }}
            </label>
          </div>
        </fieldset>
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <FormField :label="t('coach.settings.longRunDay')">
            <template #default="{ fieldId }">
              <Select :id="fieldId" v-model="form.longRunDay">
                <option value="">{{ t('coach.settings.noPreference') }}</option>
                <option v-for="day in WEEKDAYS" :key="day" :value="day">
                  {{ t(`coach.settings.weekday.${day}`) }}
                </option>
              </Select>
            </template>
          </FormField>
          <FormField :label="t('coach.settings.maxWeeklyHours')">
            <template #default="{ fieldId }">
              <input
                :id="fieldId"
                v-model="form.maxWeeklyHours"
                :class="inputFieldClass"
                type="number"
                min="0.5"
                max="40"
                step="0.5"
              />
            </template>
          </FormField>
        </div>
        <FormField :label="t('coach.settings.health')">
          <template #default="{ fieldId }">
            <textarea
              :id="fieldId"
              v-model="form.health"
              :class="inputFieldClass"
              rows="2"
              maxlength="2000"
              :placeholder="t('coach.settings.healthPlaceholder')"
            />
          </template>
        </FormField>
        <FormField :label="t('coach.settings.preferences')">
          <template #default="{ fieldId }">
            <textarea
              :id="fieldId"
              v-model="form.preferences"
              :class="inputFieldClass"
              rows="2"
              maxlength="2000"
              :placeholder="t('coach.settings.preferencesPlaceholder')"
            />
          </template>
        </FormField>
        <FormField :label="t('coach.settings.constraints')">
          <template #default="{ fieldId }">
            <textarea
              :id="fieldId"
              v-model="form.constraints"
              :class="inputFieldClass"
              rows="2"
              maxlength="2000"
              :placeholder="t('coach.settings.constraintsPlaceholder')"
            />
          </template>
        </FormField>
      </Card>

      <div class="flex justify-end">
        <Button type="submit" :disabled="isSaving || Boolean(paceError)">{{
          t('coach.settings.save')
        }}</Button>
      </div>
    </form>
  </div>
</template>
