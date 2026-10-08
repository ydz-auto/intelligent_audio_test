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
      :key="p.fieldCode ?? p.paramCode"
      class="rce-section"
    >
      <AudioSelectEditor
        :model-value="currentAlgoParams"
        :param-name="p.paramName ?? p.fieldName ?? p.paramCode"
        :field-code="p.fieldCode ?? p.paramCode"
        @update:model-value="onAlgoParamsUpdate"
        @open-audio-select="openAudioSelect"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch, inject } from 'vue'
import type { RoundConfigItem, AlgorithmParamItem } from '@/domain'
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
    (p: any) => !EXCLUDED_TYPES.has(p.paramType) && !EXCLUDED_CODES.has(p.paramCode)
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
      fieldCode: p.paramCode,
      fieldName: p.paramName ?? p.paramCode,
      fieldType: p.paramType ?? 'text',
      component: PARAM_TYPE_TO_COMPONENT[p.paramType] || 'input',
      required: p.required || false,
      defaultValue: p.defaultValue,
      validation: { min: p.min, max: p.max, step: p.step ?? 1 },
      helpText: p.helpText || '',
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
    const pType = p.fieldType ?? p.paramType
    const pCode = p.fieldCode ?? p.paramCode
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
  const eligibleCodes = new Set(eligibleParams.value.map((p: any) => p.fieldCode ?? p.paramCode))
  for (const p of algoParams) {
    const code = p.fieldCode
    if (eligibleCodes.has(code)) {
      dict[code] = p.fieldValue
    }
  }
  return dict
})

function onDynamicFormUpdate(values: Record<string, any>) {
  // 以独立列 params 为基础（若不存在则用 round.algorithmParams 兼容）
  const existingParams: AlgorithmParamItem[] = [...currentAlgoParams.value]
  const eligibleCodes = new Set(eligibleParams.value.map((p: any) => p.fieldCode ?? p.paramCode))
  for (const [fieldCode, fieldValue] of Object.entries(values)) {
    if (!eligibleCodes.has(fieldCode)) continue
    const idx = existingParams.findIndex((p) => p.fieldCode === fieldCode)
    if (idx >= 0) {
      existingParams[idx] = { fieldCode, fieldValue }
    } else {
      existingParams.push({ fieldCode, fieldValue })
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
  border-bottom: 1px solid var(--gray-light);
}
.rce-step:last-child { border-bottom: none; }

.rce-step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.rce-step-icon { font-size: 14px; color: var(--primary-color, var(--primary)); }
.rce-step-title { font-size: 14px; font-weight: 600; color: var(--text-primary, var(--foreground)); }

.rce-tag {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 500;
}
.rce-tag-orange { background: var(--color-orange-50); color: var(--primary); }

.rce-section { margin-bottom: 14px; }

.rce-sub-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, var(--foreground));
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.rce-sub-title i { font-size: 12px; color: var(--text-light, var(--color-gray-400)); }

.rce-audio-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid var(--color-indigo-100);
  border-radius: 6px;
  background: var(--muted);
}
.rce-audio-card-info { display: flex; align-items: center; gap: 6px; min-width: 0; }
.rce-audio-card-icon { color: var(--color-indigo-500); font-size: 12px; }
.rce-audio-card-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--foreground);
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
  border: 1px dashed var(--color-gray-300);
  border-radius: 6px;
  cursor: pointer;
  color: var(--color-gray-400);
  font-size: 13px;
}
.rce-audio-empty:hover { border-color: var(--color-indigo-500); color: var(--color-indigo-500); background: var(--muted); }
</style>
