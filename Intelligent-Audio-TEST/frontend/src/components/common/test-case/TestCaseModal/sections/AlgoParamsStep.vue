<template>
  <div class="rce-step" id="step-algo">
    <div class="rce-step-header">
      <i class="fas fa-sliders-h rce-step-icon"></i>
      <span class="rce-step-title">用例参数</span>
      <span class="rce-tag rce-tag-orange">algorithmParams</span>
    </div>

    <!-- 用例参数 (DynamicForm) -->
    <div v-if="dynamicSchema.fields.length > 0" class="rce-section">
      <div class="rce-sub-title">
        <i class="fas fa-cogs"></i> 用例参数 ({{ testType }})
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

    <!-- audio_select 类型参数（DynamicForm 不支持，用音频卡片渲染） -->
    <div
      v-for="p in audioSelectParams"
      :key="p.fieldCode || p.param_code"
      class="rce-section"
    >
      <AudioSelectEditor
        :model-value="currentAlgoParams"
        :param-name="p.param_name || p.fieldName || p.param_code"
        :field-code="p.fieldCode || p.param_code"
        @update:model-value="onAlgoParamsUpdate"
        @open-audio-select="openAudioSelect"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch, inject } from 'vue'
import type { RoundConfigItem, AlgorithmParamItem } from '../types'
import DynamicForm from '../../../../algorithm/DynamicForm.vue'
import AudioSelectEditor from '../AudioSelectEditor.vue'

// 这些类型不在算法参数步骤显示，由其他步骤处理
const EXCLUDED_TYPES = new Set([
  'voiceprint_editor', 'noise_config',
  'audio_select', 'audio_file'
])

// 这些 param_code 由专门步骤处理，不在算法参数步骤显示
const EXCLUDED_CODES = new Set([
  'interferers',
  'voiceprint',
  // 旧格式兼容：数据库可能仍存有旧的 5 个拆分字段，不在此显示
])

const PARAM_TYPE_TO_COMPONENT: Record<string, string> = {
  text: 'input',
  number: 'input-number',
  slider: 'slider',
  switch: 'switch',
  textarea: 'textarea',
}

const props = defineProps<{
  round: RoundConfigItem
  caseAlgorithmParams: any[]
  algorithmFormSchema?: any
  testType: 'api' | 'e2e'
  /** 当前轮的算法参数（来自独立列 algorithm_params 按轮匹配后的 params 数组） */
  roundAlgorithmParams?: AlgorithmParamItem[]
}>()

const emit = defineEmits<{
  'update:round': [value: RoundConfigItem]
  /** 算法参数更新（独立列格式 params 数组） */
  'update:round-algo-params': [params: AlgorithmParamItem[]]
  /** 打开音频选择弹窗（audio_select 类型参数使用） */
  'open-audio-select': [audioType: 'dry' | 'noise', callback: (audios: { id: string; name?: string }[]) => void]
}>()

onMounted(() => {
})

watch(() => props.caseAlgorithmParams, () => {
}, { deep: true })

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
    return {
      fieldCode: p.param_code,
      fieldName: p.param_name || p.param_code,
      fieldType: p.param_type || 'text',
      component: PARAM_TYPE_TO_COMPONENT[p.param_type] || 'input',
      required: p.required || false,
      defaultValue: p.default_value,
      validation: { min: p.min, max: p.max, step: p.step ?? 1 },
      helpText: p.help_text || '',
      scope: p.scope,
    }
  })
  return { algorithmType: '', algorithmName: '', groups: [], fields }
})

// 当前轮的算法参数：优先从独立列 roundAlgorithmParams 读取，兼容回退到 round.algorithmParams
const currentAlgoParams = computed<AlgorithmParamItem[]>(() => {
  if (props.roundAlgorithmParams && props.roundAlgorithmParams.length > 0) {
    return props.roundAlgorithmParams
  }
  // 兼容回退：子组件编辑期间可能仍写入 round.algorithmParams
  return (props.round.algorithmParams as AlgorithmParamItem[]) || []
})

// audio_select 类型参数：DynamicForm 不支持，用 AudioSelectEditor 渲染
const audioSelectParams = computed(() => {
  const all = props.algorithmFormSchema?.fields
    ? props.algorithmFormSchema.fields
    : (props.caseAlgorithmParams || [])
  return all.filter((p: any) => {
    const pType = p.fieldType || p.param_type
    const pCode = p.fieldCode || p.param_code
    return pType === 'audio_select' && !EXCLUDED_CODES.has(pCode)
  })
})

// audio_select 参数更新
function onAlgoParamsUpdate(params: AlgorithmParamItem[]) {
  emit('update:round-algo-params', params)
  emit('update:round', { ...props.round, algorithmParams: params })
}

// 打开音频选择弹窗
function openAudioSelect(callback: (audios: { id: string; name?: string }[]) => void) {
  emit('open-audio-select', 'dry', callback)
}

const initialDict = computed(() => {
  const dict: Record<string, any> = {}
  const algoParams = currentAlgoParams.value
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
  // 以独立列 params 为基础（若不存在则用 round.algorithmParams 兼容）
  const existingParams: AlgorithmParamItem[] = [...currentAlgoParams.value]
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
  // 通知父级更新独立列 params
  emit('update:round-algo-params', existingParams)
  // 同时写入 round.algorithmParams 保持兼容（CaseForm.syncStructuredFields 兜底）
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

.rce-audio-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid #e0e7ff;
  border-radius: 6px;
  background: #f8f9ff;
}
.rce-audio-card-info { display: flex; align-items: center; gap: 6px; min-width: 0; }
.rce-audio-card-icon { color: #6366f1; font-size: 12px; }
.rce-audio-card-name {
  font-size: 13px;
  font-weight: 500;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rce-audio-card-actions { display: flex; gap: 4px; flex-shrink: 0; }
.rce-audio-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 16px;
  border: 1px dashed #ccc;
  border-radius: 6px;
  cursor: pointer;
  color: #999;
  font-size: 13px;
}
.rce-audio-empty:hover { border-color: #6366f1; color: #6366f1; background: #f8f9ff; }
</style>
