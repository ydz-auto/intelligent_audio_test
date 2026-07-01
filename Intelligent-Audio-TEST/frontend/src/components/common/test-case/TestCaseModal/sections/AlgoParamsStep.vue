<template>
  <div class="rce-step" id="step-algo">
    <div class="rce-step-header">
      <i class="fas fa-sliders-h rce-step-icon"></i>
      <span class="rce-step-title">算法参数</span>
      <span class="rce-tag rce-tag-orange">algorithmParams</span>
    </div>

    <!-- API 输入参数 -->
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
            :placeholder="param.help_text"
            @input="setAlgoParam(param.param_code, ($event.target as HTMLTextAreaElement).value)"
          ></textarea>
        </div>
      </div>
    </div>

    <!-- 算法参数 (DynamicForm) -->
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
import { computed, ref, onMounted, watch } from 'vue'
import type { RoundConfigItem } from '../types'
import DynamicForm from '../../../../algorithm/DynamicForm.vue'
import { algorithmApi } from '../../../../../utils/api'

// 这些类型不在算法参数步骤显示，由其他步骤处理
const EXCLUDED_TYPES = new Set([
  'voiceprint_editor', 'noise_config',
  'audio_select', 'audio_file'
])

// 这些 param_code 由专门步骤处理，不在算法参数步骤显示
const EXCLUDED_CODES = new Set([
  'interferers',
  'voiceprintEnabled',
  'voiceprintAudioId',
  'voiceprintPlaybackDeviceId',
  'voiceprintSpl',
  'voiceprintWaitTime',
  'overlap_rate',
  'overlap_time',
])

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
  algorithmFormSchema?: any
  testType: 'api' | 'e2e'
}>()

const emit = defineEmits<{
  'update:round': [value: RoundConfigItem]
}>()

// 动态选项缓存：param_code → options 列表
const dynamicOptions = ref<Record<string, { value: string; label: string }[]>>({})

// 加载 select 类型参数的动态选项（从 options_source 加载）
async function loadDynamicOptions() {
  const params = eligibleParams.value
  const needLoad = params.filter((p: any) => {
    const paramType = p.param_type || p.fieldType
    const optionsSource = p.options_source || p.optionsSource
    return paramType === 'select' && optionsSource && !dynamicOptions.value[p.param_code || p.fieldCode]
  })
  if (needLoad.length === 0) return
  // 通过后端 API 获取选项（按 algorithmType 批量获取）
  const algoType = props.algorithmFormSchema?.algorithmType || ''
  if (algoType) {
    try {
      const result = await algorithmApi.getParamOptions(algoType)
      const options = (result as any)?.options || {}
      for (const [code, opts] of Object.entries(options)) {
        dynamicOptions.value[code] = opts as any
      }
    } catch (e) {
      console.error('[AlgoParamsStep] 加载动态选项失败:', e)
    }
  }
}

onMounted(() => {
  loadDynamicOptions()
})

watch(() => props.caseAlgorithmParams, () => {
  loadDynamicOptions()
}, { deep: true })

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
  if (props.algorithmFormSchema?.fields) {
    return props.algorithmFormSchema.fields.filter(
      (f: any) => !EXCLUDED_TYPES.has(f.fieldType) && !EXCLUDED_CODES.has(f.fieldCode)
    )
  }
  return (props.caseAlgorithmParams || []).filter(
    (p: any) => !EXCLUDED_TYPES.has(p.param_type) && !EXCLUDED_CODES.has(p.param_code)
  )
})

const dynamicSchema = computed(() => {
  if (props.algorithmFormSchema?.fields) {
    const fields = eligibleParams.value
    return {
      algorithmType: props.algorithmFormSchema.algorithmType || '',
      algorithmName: props.algorithmFormSchema.algorithmName || '',
      groups: [],
      fields,
    }
  }
  const fields = eligibleParams.value.map((p: any) => {
    let options: { value: string; label: string }[] | undefined
    if (p.param_type === 'select') {
      // 优先使用动态加载的选项
      const code = p.param_code
      if (code && dynamicOptions.value[code]) {
        options = dynamicOptions.value[code]
      } else if (p.options) {
        const opts = typeof p.options === 'string' ? JSON.parse(p.options) : p.options
        options = Array.isArray(opts)
          ? opts.map((o: any) => typeof o === 'string' ? { value: o, label: o } : o)
          : undefined
      }
    }
    return {
      fieldCode: p.param_code,
      fieldName: p.param_name || p.param_code,
      fieldType: p.param_type || 'text',
      component: PARAM_TYPE_TO_COMPONENT[p.param_type] || 'input',
      required: p.required || false,
      defaultValue: p.default_value,
      options,
      validation: { min: p.min, max: p.max, step: p.step ?? 1 },
      helpText: p.help_text || '',
      scope: p.scope,
    }
  })
  return { algorithmType: '', algorithmName: '', groups: [], fields }
})

const initialDict = computed(() => {
  const dict: Record<string, any> = {}
  const algoParams = props.round.algorithmParams || []
  const eligibleCodes = new Set(eligibleParams.value.map((p: any) => p.fieldCode || p.param_code))
  for (const p of algoParams) {
    const code = p.field_code
    if (eligibleCodes.has(code)) {
      dict[code] = p.field_value
    }
  }
  return dict
})

function onDynamicFormUpdate(values: Record<string, any>) {
  const existingParams = [...(props.round.algorithmParams || [])]
  const eligibleCodes = new Set(eligibleParams.value.map((p: any) => p.fieldCode || p.param_code))
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
</style>