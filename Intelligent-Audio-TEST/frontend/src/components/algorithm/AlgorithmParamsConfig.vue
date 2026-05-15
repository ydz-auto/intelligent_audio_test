<template>
  <div class="algorithm-params-config">
    <div class="algorithm-selection">
      <label class="section-label">支持算法:</label>
      <div class="algorithm-checkboxes">
        <label 
          v-for="algo in availableAlgorithms" 
          :key="algo.type" 
          class="algorithm-checkbox"
          :class="{ 'algorithm-checkbox--checked': selectedAlgorithms.includes(algo.type) }"
        >
          <input 
            type="checkbox" 
            :value="algo.type" 
            v-model="selectedAlgorithms"
            @change="handleAlgorithmToggle(algo.type)"
          />
          <span class="checkbox-label">{{ algo.name }}</span>
        </label>
      </div>
    </div>
    
    <div v-if="selectedAlgorithms.length > 0" class="algorithm-params-section">
      <label class="section-label">算法参数配置:</label>
      <div class="params-panels">
        <div 
          v-for="algoType in selectedAlgorithms" 
          :key="algoType" 
          class="params-panel"
        >
          <div class="params-panel-header" @click="togglePanel(algoType)">
            <span class="panel-title">
              <i :class="isPanelExpanded(algoType) ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
              {{ getAlgorithmName(algoType) }} 参数
            </span>
          </div>
          <div v-show="isPanelExpanded(algoType)" class="params-panel-body">
            <DynamicForm
              v-if="formSchemas[algoType]"
              :algorithm-type="algoType"
              :model-value="getAlgorithmParams(algoType)"
              @update:model-value="handleParamsChange(algoType, $event)"
            />
            <div v-else class="no-params">
              <span>该算法暂无可配置参数</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import DynamicForm from './DynamicForm.vue'
import { useAlgorithmConfig, type AlgorithmDefinition, type FormSchema } from '../../composables/useAlgorithmConfig'

interface AlgorithmConfig {
  enabled: boolean
  default_params?: Record<string, any>
  notes?: string
}

const props = withDefaults(defineProps<{
  supportedAlgorithms?: string[]
  algorithmConfigs?: Record<string, AlgorithmConfig>
}>(), {
  supportedAlgorithms: () => [],
  algorithmConfigs: () => ({})
})

const emit = defineEmits<{
  'update:supportedAlgorithms': [value: string[]]
  'update:algorithmConfigs': [value: Record<string, AlgorithmConfig>]
}>()

const { loadAlgorithms, getFormSchema, algorithms } = useAlgorithmConfig()

const selectedAlgorithms = ref<string[]>([...props.supportedAlgorithms])
const localConfigs = ref<Record<string, AlgorithmConfig>>({ ...props.algorithmConfigs })
const expandedPanels = ref<Set<string>>(new Set())
const formSchemas = ref<Record<string, FormSchema | null>>({})

const availableAlgorithms = computed(() => {
  return algorithms.value.map(algo => ({
    type: algo.type,
    name: algo.name
  }))
})

const algorithmNameMap: Record<string, string> = {
  'translation': '翻译',
  'asr': 'ASR',
  'speaker_recognition': '说话人识别',
  'tts': 'TTS',
  'speaker_verification': '声纹验证',
  'speaker_identification': '说话人识别'
}

const getAlgorithmName = (type: string): string => {
  const algo = algorithms.value.find(a => a.type === type)
  return algo?.name || algorithmNameMap[type] || type
}

const isPanelExpanded = (algoType: string): boolean => {
  return expandedPanels.value.has(algoType)
}

const togglePanel = (algoType: string) => {
  if (expandedPanels.value.has(algoType)) {
    expandedPanels.value.delete(algoType)
  } else {
    expandedPanels.value.add(algoType)
  }
}

const getAlgorithmParams = (algoType: string): Record<string, any> => {
  return localConfigs.value[algoType]?.default_params || {}
}

const handleAlgorithmToggle = async (algoType: string) => {
  if (selectedAlgorithms.value.includes(algoType)) {
    if (!localConfigs.value[algoType]) {
      localConfigs.value[algoType] = {
        enabled: true,
        default_params: {}
      }
      expandedPanels.value.add(algoType)
      
      if (!formSchemas.value[algoType]) {
        formSchemas.value[algoType] = await getFormSchema(algoType)
      }
    }
  } else {
    delete localConfigs.value[algoType]
    expandedPanels.value.delete(algoType)
  }
  
  emit('update:supportedAlgorithms', [...selectedAlgorithms.value])
  emit('update:algorithmConfigs', { ...localConfigs.value })
}

const handleParamsChange = (algoType: string, params: Record<string, any>) => {
  if (!localConfigs.value[algoType]) {
    localConfigs.value[algoType] = {
      enabled: true,
      default_params: {}
    }
  }
  localConfigs.value[algoType].default_params = params
  emit('update:algorithmConfigs', { ...localConfigs.value })
}

const loadFormSchemas = async () => {
  for (const algoType of selectedAlgorithms.value) {
    if (!formSchemas.value[algoType]) {
      formSchemas.value[algoType] = await getFormSchema(algoType)
    }
    expandedPanels.value.add(algoType)
  }
}

watch(() => props.supportedAlgorithms, (newVal) => {
  selectedAlgorithms.value = [...newVal]
  loadFormSchemas()
}, { immediate: true })

watch(() => props.algorithmConfigs, (newVal) => {
  localConfigs.value = { ...newVal }
}, { immediate: true, deep: true })

onMounted(async () => {
  await loadAlgorithms()
  await loadFormSchemas()
})
</script>

<style scoped>
.algorithm-params-config {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-label {
  font-weight: 600;
  color: #374151;
  margin-bottom: 8px;
  display: block;
}

.algorithm-checkboxes {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.algorithm-checkbox {
  display: inline-flex;
  align-items: center;
  padding: 6px 12px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  background-color: #fff;
}

.algorithm-checkbox:hover {
  border-color: #3b82f6;
  background-color: #eff6ff;
}

.algorithm-checkbox--checked {
  border-color: #3b82f6;
  background-color: #dbeafe;
}

.algorithm-checkbox input {
  margin-right: 8px;
}

.checkbox-label {
  font-size: 14px;
  color: #374151;
}

.params-panels {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.params-panel {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}

.params-panel-header {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  background-color: #f9fafb;
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.params-panel-header:hover {
  background-color: #f3f4f6;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
  color: #374151;
}

.panel-title i {
  font-size: 12px;
  color: #6b7280;
  transition: transform 0.2s ease;
}

.params-panel-body {
  padding: 16px;
  background-color: #fff;
  border-top: 1px solid #e5e7eb;
}

.no-params {
  color: #9ca3af;
  font-size: 14px;
  text-align: center;
  padding: 16px;
}
</style>
