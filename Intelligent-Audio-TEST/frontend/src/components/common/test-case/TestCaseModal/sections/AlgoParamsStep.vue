<template>
  <div class="rce-step" id="step-algo">
    <div class="rce-step-header">
      <i class="fas fa-sliders-h rce-step-icon"></i>
      <span class="rce-step-title">算法参数</span>
      <span class="rce-tag rce-tag-orange">algorithmParams</span>
    </div>

    <div v-if="apiInputParams.length > 0" class="rce-section">
      <div class="rce-sub-title">本轮输入</div>
      <div class="rce-param-grid">
        <div v-for="param in apiInputParams" :key="param.param_code" class="rce-param-item">
          <label class="rce-param-label">{{ param.param_name || param.param_code }}</label>
          <textarea
            v-if="param.param_type === 'text'"
            class="form-control form-control-sm"
            rows="2"
            :value="String(getAlgoParam(param.param_code) ?? '')"
            :placeholder="param.help_text || `输入${param.param_name}`"
            @input="setAlgoParam(param.param_code, ($event.target as HTMLTextAreaElement).value)"
          ></textarea>
          <div v-else-if="param.param_type === 'audio_file'" class="rce-audio-input">
            <input
              type="text"
              class="form-control form-control-sm"
              :value="getAlgoParam(param.param_code)"
              placeholder="选择音频..."
              readonly
              @click="$emit('openAudioSelect', (audioId: string) => setAlgoParam(param.param_code, audioId))"
            />
            <button
              type="button"
              class="btn btn-sm btn-outline-primary"
              @click="$emit('openAudioSelect', (audioId: string) => setAlgoParam(param.param_code, audioId))"
            >
              <i class="fas fa-music"></i>
            </button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="audioFileParams.length > 0" class="rce-section">
      <div class="rce-sub-title">
        <i class="fas fa-music"></i> 音频参数
      </div>
      <div class="rce-param-grid">
        <div v-for="param in audioFileParams" :key="param.param_code" class="rce-param-item">
          <label class="rce-param-label">{{ param.param_name || param.param_code }}</label>
          <div class="rce-audio-input">
            <input
              type="text"
              class="form-control form-control-sm"
              :value="getAlgoParam(param.param_code)"
              placeholder="选择音频..."
              readonly
              @click="$emit('openAudioSelect', (audioId: string) => setAlgoParam(param.param_code, audioId))"
            />
            <button
              type="button"
              class="btn btn-sm btn-outline-primary"
              @click="$emit('openAudioSelect', (audioId: string) => setAlgoParam(param.param_code, audioId))"
            >
              <i class="fas fa-music"></i>
            </button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="dynamicSchema.fields.length > 0" class="rce-section">
      <div class="rce-sub-title">
        <i class="fas fa-cogs"></i> 算法参数 ({{ testType }})
      </div>
      <DynamicForm
        :key="`algo-${round.roundNumber}`"
        :schema="dynamicSchema"
        :initial-values="initialDict"
        :scope="testType"
        :show-group-header="false"
        @update:model-value="onDynamicFormUpdate"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { RoundConfigItem, AlgorithmParamItem } from '../types'
import DynamicForm from '../../../../algorithm/DynamicForm.vue'

const COMPLEX_TYPES = new Set(['voiceprint_editor', 'interferer_list', 'noise_config'])

const PARAM_TYPE_TO_COMPONENT: Record<string, string> = {
  text: 'input',
  number: 'input-number',
  slider: 'slider',
  switch: 'switch',
  select: 'select',
  textarea: 'textarea',
}

const props = defineProps<{
  round: RoundConfigItem
  apiInputParams: any[]
  caseAlgorithmParams: any[]
  testType: 'api' | 'e2e'
}>()

const emit = defineEmits<{
  'update:round': [value: RoundConfigItem]
  'openAudioSelect': [callback: (audioId: string) => void]
}>()

function getAlgoParam(fieldCode: string, defaultValue?: unknown): unknown {
  const params = props.round.algorithmParams || []
  const item = params.find((p) => p.field_code === fieldCode)
  return item?.field_value ?? defaultValue ?? ''
}

function setAlgoParam(fieldCode: string, value: unknown) {
  const params = [...(props.round.algorithmParams || [])]
  const idx = params.findIndex((p) => p.field_code === fieldCode)
  if (idx >= 0) {
    params[idx] = { field_code: fieldCode, field_value: value }
  } else {
    params.push({ field_code: fieldCode, field_value: value })
  }
  emit('update:round', { ...props.round, algorithmParams: params })
}

const eligibleParams = computed(() => {
  return (props.caseAlgorithmParams || []).filter(
    (p: any) => !COMPLEX_TYPES.has(p.param_type) && p.param_type !== 'audio_file'
  )
})

const audioFileParams = computed(() => {
  return (props.caseAlgorithmParams || []).filter(
    (p: any) => p.param_type === 'audio_file'
  )
})

const dynamicSchema = computed(() => {
  const fields = eligibleParams.value.map((p: any) => {
    let options: { value: string; label: string }[] | undefined
    if (p.param_type === 'select' && p.options) {
      const opts = typeof p.options === 'string' ? JSON.parse(p.options) : p.options
      options = Array.isArray(opts)
        ? opts.map((o: any) => typeof o === 'string' ? { value: o, label: o } : o)
        : undefined
    }

    return {
      fieldCode: p.param_code,
      fieldName: p.param_name || p.param_code,
      fieldType: p.param_type || 'text',
      component: PARAM_TYPE_TO_COMPONENT[p.param_type] || 'input',
      required: p.required || false,
      defaultValue: p.default_value,
      options,
      validation: {
        min: p.min,
        max: p.max,
        step: p.step ?? 1,
      },
      helpText: p.help_text || '',
      scope: p.scope,
    }
  })

  return {
    algorithmType: '',
    algorithmName: '',
    groups: [],
    fields,
  }
})

const initialDict = computed(() => {
  const dict: Record<string, any> = {}
  const algoParams = props.round.algorithmParams || []
  for (const p of algoParams) {
    if (eligibleParams.value.some((ep: any) => ep.param_code === p.field_code)) {
      dict[p.field_code] = p.field_value
    }
  }
  return dict
})

function onDynamicFormUpdate(values: Record<string, any>) {
  const existingParams = [...(props.round.algorithmParams || [])]
  const eligibleCodes = new Set(eligibleParams.value.map((p: any) => p.param_code))

  for (const [fieldCode, fieldValue] of Object.entries(values)) {
    if (!eligibleCodes.has(fieldCode)) continue
    const idx = existingParams.findIndex((p) => p.field_code === fieldCode)
    if (idx >= 0) {
      existingParams[idx] = { field_code: fieldCode, field_value: fieldValue }
    } else {
      existingParams.push({ field_code: fieldCode, field_value: fieldValue })
    }
  }

  emit('update:round', { ...props.round, algorithmParams: existingParams })
}
</script>

<style scoped>
.rce-step {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid #f0f0f0;
}
.rce-step:last-child { border-bottom: none; }

.rce-step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.rce-step-icon { font-size: 14px; color: var(--primary-color, #ff6a00); }
.rce-step-title { font-size: 14px; font-weight: 600; color: var(--text-primary, #333); }

.rce-tag {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 500;
}
.rce-tag-orange { background: #fff3e8; color: #ff6a00; }

.rce-section { margin-bottom: 14px; }

.rce-sub-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #333);
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.rce-sub-title i { font-size: 12px; color: var(--text-light, #999); }

.rce-param-grid { display: flex; gap: 12px; flex-wrap: wrap; }
.rce-param-item { flex: 1; min-width: 160px; max-width: 320px; }

.rce-param-label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary, #666);
  margin-bottom: 4px;
}

.rce-audio-input { display: flex; gap: 4px; align-items: center; }
.rce-audio-input input {
  flex: 1;
  cursor: pointer;
  background: var(--background-primary, #fff) !important;
}
</style>
