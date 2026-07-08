<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useTestCaseConfig } from '../../composables/useTestCaseConfig'
import AudioSelectModal from './AudioSelectModal.vue'
import AlgorithmSelector from './AlgorithmSelector.vue'
import type { AudioItem } from '../../composables/useAudioList'

interface AlgorithmRelationItem {
  algorithmType: string
  isPrimary: boolean
  weight: number
  params?: Record<string, any>
}

interface Props {
  modelValue: {
    audioType?: string
    createTestCase?: boolean
    testTypes?: ('api' | 'e2e')[]
    playbackDeviceId?: string | number
    spl?: number
    noiseAudioId?: string | number
    noiseAudioName?: string
    noiseSpl?: number
    inheritTags?: boolean
    apiDimensions?: Array<{ id: string | number; name: string }>
    e2eDimensions?: Array<{ id: string | number; name: string }>
    promptDeviceId?: string | number
    algorithmType?: string
    algorithmRelations?: AlgorithmRelationItem[]
    algorithmParams?: Record<string, any>
    promptSourceLanguage?: string
    promptTargetLanguage?: string
    promptTranslationDirection?: string
  }
  tags?: string
  audioTypeOptions?: Array<{ label: string; value: string }>
  playbackDeviceOptions?: Array<{ label: string; value: string | number }>
  deviceOptions?: Array<{ label: string; value: string | number }>
  algorithmOptions?: Array<{ label: string; value: string }>
  showTagsInput?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  audioTypeOptions: () => [],
  playbackDeviceOptions: () => [],
  deviceOptions: () => [],
  algorithmOptions: () => [],
  showTagsInput: true,
  tags: ''
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: Props['modelValue']): void
  (e: 'update:tags', value: string): void
}>()

const localConfig = ref<Props['modelValue'] | null>(null)
const localTags = ref(props.tags)

watch(() => props.tags, (newVal) => {
  if (newVal !== localTags.value) {
    localTags.value = newVal
  }
})

watch(localTags, (newVal) => {
  emit('update:tags', newVal)
})

const uploadConfig = computed({
  get: () => {
    if (!localConfig.value) {
      localConfig.value = props.modelValue
    }
    return localConfig.value
  },
  set: (val) => {
    localConfig.value = val
    emit('update:modelValue', val)
  }
})

watch(() => props.modelValue, (newVal) => {
  if (newVal && JSON.stringify(newVal) !== JSON.stringify(localConfig.value)) {
    localConfig.value = newVal
  }
}, { deep: true })

watch(() => uploadConfig.value.audioType, (newType) => {
  if (newType === 'noise') {
    uploadConfig.value = {
      ...uploadConfig.value,
      createTestCase: false,
      testTypes: ['api'],
      algorithmType: '',
      algorithmParams: [],
      apiDimensions: [],
      e2eDimensions: []
    }
  }
})

const {
  audioTypeOptions: computedAudioTypeOptions,
  hasAudioType,
  testTypeOptions,
  filteredDimensions,
  e2eFilteredDimensions,
  dimensionCount,
  isDimensionSelected,
  toggleDimensionSelection,
  ensureDimensionsLoaded,
  dimensionsLoading,
  dimensionsError,
  dimensionSearchQuery,
  e2eDimensionSearchQuery,
  updateDimensionFilter
} = useTestCaseConfig({
  audioTypeOptions: props.audioTypeOptions.length > 0 ? props.audioTypeOptions : undefined
})

const hasApiDimensions = computed(() => (uploadConfig.value.apiDimensions || []).length > 0)
const hasE2eDimensions = computed(() => (uploadConfig.value.e2eDimensions || []).length > 0)

const setApiDimensions = (dimensions: Array<{ id: string | number; name: string }>) => {
  uploadConfig.value = {
    ...uploadConfig.value,
    apiDimensions: dimensions
  }
}

const setE2eDimensions = (dimensions: Array<{ id: string | number; name: string }>) => {
  uploadConfig.value = {
    ...uploadConfig.value,
    e2eDimensions: dimensions
  }
}

const toggleApiDimension = (dim: any) => {
  toggleDimensionSelection(dim, uploadConfig.value.apiDimensions, setApiDimensions)
}

const toggleE2eDimension = (dim: any) => {
  toggleDimensionSelection(dim, uploadConfig.value.e2eDimensions, setE2eDimensions)
}

const showTestCaseConfig = computed(() => uploadConfig.value.createTestCase)
const showApiConfig = computed(() => uploadConfig.value.testTypes?.includes('api'))
const showE2eConfig = computed(() => uploadConfig.value.testTypes?.includes('e2e'))

watch([showApiConfig, showE2eConfig], ([api, e2e]) => {
  if (api || e2e) {
    ensureDimensionsLoaded()
  }
}, { immediate: true })

const noiseSelectModalVisible = ref(false)
const algorithmParams = ref<any>({})
const associatedDimensionIds = ref<number[]>([])
const algorithmRelations = ref<AlgorithmRelationItem[]>([])

const handleAlgorithmParamsChange = (params: Record<string, any>) => {
  algorithmParams.value = params
  uploadConfig.value = {
    ...uploadConfig.value,
    algorithmParams: params
  }
}

const handleAlgorithmRelationsChange = (relations: AlgorithmRelationItem[]) => {
  algorithmRelations.value = relations
  uploadConfig.value = {
    ...uploadConfig.value,
    algorithmRelations: relations
  }
}

const handleDimensionsChange = (dimensions: any[], dimensionIds: number[]) => {
  associatedDimensionIds.value = dimensionIds
  updateDimensionFilter(dimensionIds)
  if (dimensionIds.length > 0) {
    const filteredApi = (uploadConfig.value.apiDimensions || []).filter(
      (d: any) => dimensionIds.includes(Number(d.id))
    )
    const filteredE2e = (uploadConfig.value.e2eDimensions || []).filter(
      (d: any) => dimensionIds.includes(Number(d.id))
    )
    uploadConfig.value = {
      ...uploadConfig.value,
      apiDimensions: filteredApi,
      e2eDimensions: filteredE2e
    }
  }
}

const openNoiseSelectModal = () => {
  noiseSelectModalVisible.value = true
}

const handleNoiseSelect = (audio: AudioItem) => {
  uploadConfig.value = {
    ...uploadConfig.value,
    noiseAudioId: audio.id,
    noiseAudioName: audio.filename
  }
  noiseSelectModalVisible.value = false
}

const clearNoiseAudio = () => {
  uploadConfig.value = {
    ...uploadConfig.value,
    noiseAudioId: undefined,
    noiseAudioName: undefined
  }
}
</script>

<template>
  <div class="upload-options">
    <!-- 噪声选择弹窗 -->
    <AudioSelectModal
      v-if="noiseSelectModalVisible"
      :visible="noiseSelectModalVisible"
      title="选择噪声文件"
      audio-type="noise"
      :teleport-to-body="false"
      @close="noiseSelectModalVisible = false"
      @select="handleNoiseSelect"
    />

    <h4>上传选项</h4>
    
    <!-- 音频类型选择 -->
    <div class="options-grid" v-if="hasAudioType">
      <div class="option-item">
        <label>音频类型</label>
        <div class="radio-group">
          <label v-for="opt in computedAudioTypeOptions" :key="opt.value" class="radio-label">
            <input 
              type="radio" 
              :name="'audioType'" 
              :value="opt.value" 
              v-model="uploadConfig.audioType"
            >
            <span class="radio-text">{{ opt.label }}</span>
          </label>
        </div>
      </div>
    </div>
    
    <!-- 生成测试用例 -->
    <div class="options-grid" v-if="!['noise', 'prompt'].includes(uploadConfig.audioType)">
      <div class="option-item">
        <label class="checkbox-label">
          <input 
            type="checkbox" 
            v-model="uploadConfig.createTestCase"
          >
          <span class="checkbox-text">生成测试用例</span>
        </label>
      </div>
    </div>
    
    <!-- 继承音频标签 -->
    <div class="options-grid" v-if="!['noise', 'prompt'].includes(uploadConfig.audioType)">
      <div class="option-item">
        <label class="checkbox-label">
          <input 
            type="checkbox" 
            v-model="uploadConfig.inheritTags"
          >
          <span class="checkbox-text">继承音频标签</span>
        </label>
      </div>
      
      <!-- 标签输入 -->
      <div class="option-item full-width" v-if="showTagsInput">
        <label>标签</label>
        <input 
          type="text" 
          class="form-input" 
          placeholder="留空将自动生成；多个标签用逗号分隔" 
          v-model="localTags"
        >
        <p class="option-hint">留空将自动生成标签</p>
      </div>
    </div>

    <!-- 算法选择器（除噪声外都显示，单选） -->
    <AlgorithmSelector
      v-if="!['noise'].includes(uploadConfig.audioType)"
      v-model="uploadConfig.algorithmType"
      v-model:algorithm-relations="uploadConfig.algorithmRelations"
      :initial-params="algorithmParams"
      :show-params="false"
      :single="true"
      @params-change="handleAlgorithmParamsChange"
      @dimensions-change="handleDimensionsChange"
    />
    
    <!-- 提示词音频关联配置（仅在上传提示词音频时显示） -->
    <div class="options-grid" v-if="uploadConfig.audioType === 'prompt'">
      <div class="option-item full-width">
        <h4 class="section-title">提示词音频关联配置</h4>
      </div>
      <div class="option-item">
        <label>关联设备</label>
        <select v-model="uploadConfig.promptDeviceId" class="form-input custom-select">
          <option value="">请选择设备</option>
          <option v-for="opt in deviceOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
      </div>
      <div class="option-item">
        <label>源语言</label>
        <input type="text" v-model="uploadConfig.promptSourceLanguage" class="form-input" placeholder="如 zh, en">
      </div>
      <div class="option-item">
        <label>目标语言</label>
        <input type="text" v-model="uploadConfig.promptTargetLanguage" class="form-input" placeholder="如 en, ja">
      </div>
      <div class="option-item">
        <label>翻译方向</label>
        <input type="text" v-model="uploadConfig.promptTranslationDirection" class="form-input" placeholder="如 zh2en">
      </div>
    </div>
    
    <!-- 测试用例配置（仅在勾选生成测试用例时显示） -->
    <template v-if="showTestCaseConfig">
      <!-- 测试类型选择 -->
      <div class="options-grid">
        <div class="option-item full-width">
          <label>测试类型</label>
          <div class="checkbox-group">
            <label class="checkbox-label">
              <input 
                type="checkbox" 
                value="api" 
                v-model="uploadConfig.testTypes"
              >
              <span class="checkbox-text">API测试</span>
            </label>
            <label class="checkbox-label">
              <input 
                type="checkbox" 
                value="e2e" 
                v-model="uploadConfig.testTypes"
              >
              <span class="checkbox-text">E2E测试</span>
            </label>
          </div>
          <p class="option-hint">选择要生成的测试用例类型，可多选</p>
        </div>
      </div>

      <!-- API测试配置区域 -->
      <div class="test-type-config api-config" v-if="showApiConfig">
        <div class="config-header">
          <i class="fas fa-server"></i>
          <span>API测试配置</span>
        </div>
        <div class="options-grid">
          <div class="option-item full-width">
            <label>API测试评估维度 <span class="required">*</span></label>
            <div class="dimension-toolbar">
              <input
                type="text"
                class="form-input"
                placeholder="搜索评估维度"
                v-model="dimensionSearchQuery"
                @click.stop
              >
              <div class="dimension-summary" :class="{ 'has-error': !hasApiDimensions }">
                已选 {{ dimensionCount(uploadConfig.apiDimensions) }} 项
              </div>
            </div>
            <div class="tag-filter" v-if="!dimensionsLoading">
                <div
                  v-for="dim in filteredDimensions"
                  :key="dim.id"
                  class="tag-filter-item"
                  :class="{ 'active': isDimensionSelected(dim, uploadConfig.apiDimensions) }"
                  @click.stop.prevent="toggleApiDimension(dim)"
                >
                  {{ dim.name }}
                </div>
                <div v-if="filteredDimensions.length === 0" class="dimension-empty">
                  未找到匹配的维度
                </div>
              </div>
            <div class="dimension-loading" v-else>
              加载中...
            </div>
            <p class="option-hint" v-if="dimensionsError">{{ dimensionsError }}</p>
            <p class="option-hint error" v-if="!hasApiDimensions">请至少选择一个评估维度</p>
          </div>
        </div>
      </div>

      <!-- E2E测试配置区域 -->
      <div class="test-type-config e2e-config" v-if="showE2eConfig">
        <div class="config-header">
          <i class="fas fa-mobile-alt"></i>
          <span>E2E测试配置</span>
        </div>
        <div class="options-grid">
          <div class="option-item full-width">
            <label>E2E测试评估维度 <span class="required">*</span></label>
            <div class="dimension-toolbar">
              <input
                type="text"
                class="form-input"
                placeholder="搜索评估维度"
                v-model="e2eDimensionSearchQuery"
                @click.stop
              >
              <div class="dimension-summary" :class="{ 'has-error': !hasE2eDimensions }">
                已选 {{ dimensionCount(uploadConfig.e2eDimensions) }} 项
              </div>
            </div>
            <div class="tag-filter" v-if="!dimensionsLoading">
                <div
                  v-for="dim in e2eFilteredDimensions"
                  :key="dim.id"
                  class="tag-filter-item"
                  :class="{ 'active': isDimensionSelected(dim, uploadConfig.e2eDimensions) }"
                  @click.stop.prevent="toggleE2eDimension(dim)"
                >
                  {{ dim.name }}
                </div>
                <div v-if="e2eFilteredDimensions.length === 0" class="dimension-empty">
                  未找到匹配的维度
                </div>
              </div>
            <div class="dimension-loading" v-else>
              加载中...
            </div>
            <p class="option-hint error" v-if="!hasE2eDimensions">请至少选择一个评估维度</p>
          </div>
        </div>

        <div class="config-hint">
          <i class="fas fa-info-circle"></i>
          <span>播放设备、声压级、噪声等参数将在用例编辑页面的轮次配置中填写</span>
        </div>
      </div>
    </template>


  </div>
</template>

<style scoped>
.upload-options {
  padding: 20px;
  background: var(--background-primary);
  border-radius: var(--border-radius-lg);
  border: 1px solid var(--border-color);
}

.upload-options h4 {
  margin: 0 0 20px 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.options-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 20px;
  margin-bottom: 20px;
}

.option-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.option-item.full-width {
  grid-column: 1 / -1;
}

.option-item label:not(.checkbox-label):not(.radio-label) {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.option-item .required {
  color: var(--error-color);
}

.form-input {
  padding: 10px 14px;
  border: 2px solid var(--border-color);
  border-radius: var(--border-radius-md);
  font-size: 14px;
  outline: none;
  transition: all var(--transition-fast);
  background: var(--white-color);
}

.form-input:focus {
  border-color: var(--secondary-color);
  box-shadow: 0 0 0 3px var(--secondary-light);
}

.form-input::placeholder {
  color: var(--text-disabled);
}

.custom-select {
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23999' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 14px center;
  padding-right: 40px;
  cursor: pointer;
}

.checkbox-group,
.radio-group {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.checkbox-label, .radio-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 14px;
  color: var(--text-primary);
  padding: 8px 12px;
  border-radius: var(--border-radius-md);
  transition: all var(--transition-fast);
}

.checkbox-label:hover,
.radio-label:hover {
  background: var(--secondary-light);
}

.checkbox-label input[type="checkbox"],
.radio-label input[type="radio"] {
  width: 18px;
  height: 18px;
  cursor: pointer;
  accent-color: var(--secondary-color);
  position: static;
  opacity: 1;
  height: auto;
  width: auto;
}

.checkbox-label .checkbox-text {
  position: static;
  display: inline;
}

.checkbox-label .checkbox-text::before,
.checkbox-label .checkbox-text::after {
  content: none;
}

.option-hint {
  margin: 4px 0 0 0;
  font-size: 12px;
  color: var(--text-light);
}

.option-hint.error {
  color: var(--error-color);
}

.config-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  padding: 8px 12px;
  background: #f0f7ff;
  border: 1px solid #d0e3ff;
  border-radius: 6px;
  font-size: 12px;
  color: #1e40af;
}

.config-hint i {
  color: #3b82f6;
}

.audio-select-wrapper {
  display: flex;
  align-items: center;
  gap: 10px;
}

.audio-select-btn {
  flex: 1;
  justify-content: flex-start;
  text-align: left;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 10px 14px;
  background: var(--white-color);
  border: 2px dashed var(--border-color);
  border-radius: var(--border-radius-md);
  color: var(--secondary-color);
  font-weight: 500;
  transition: all var(--transition-fast);
}

.audio-select-btn:hover {
  border-color: var(--secondary-color);
  background: var(--secondary-light);
}

.clear-btn {
  flex-shrink: 0;
  color: var(--text-light);
  font-size: 13px;
  padding: 8px 12px;
  border-radius: var(--border-radius-sm);
  transition: all var(--transition-fast);
}

.clear-btn:hover {
  color: var(--error-color);
  background: var(--error-light);
}

.test-type-config {
  margin-top: 20px;
  padding: 20px;
  background-color: var(--background-primary);
  border-radius: var(--border-radius-lg);
  border: 1px solid var(--border-color);
  box-shadow: var(--shadow-sm);
}

.test-type-config .config-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 20px;
  font-weight: 600;
  color: var(--text-primary);
  font-size: 15px;
}

.test-type-config .config-header i {
  font-size: 18px;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--border-radius-md);
}

.api-config {
  border-left: 4px solid var(--secondary-color);
}

.api-config .config-header i {
  background: var(--secondary-light);
  color: var(--secondary-color);
}

.e2e-config {
  border-left: 4px solid var(--success-color);
}

.e2e-config .config-header i {
  background: var(--success-light);
  color: var(--success-color);
}

.dimension-toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}

.dimension-toolbar .form-input {
  flex: 1;
}

.dimension-summary {
  padding: 10px 14px;
  background-color: var(--background-primary);
  border-radius: var(--border-radius-md);
  font-size: 13px;
  color: var(--text-secondary);
  white-space: nowrap;
  font-weight: 500;
  border: 1px solid var(--border-color);
}

.dimension-summary.has-error {
  background-color: var(--error-light);
  color: var(--error-color);
  border-color: var(--error-color);
}

.tag-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px;
  min-height: 80px;
  max-height: 180px;
  overflow-y: auto;
}

.tag-filter-item {
  padding: 6px 12px;
  background: #f1f5f9;
  color: #64748b;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 13px;
  font-weight: 500;
}

.tag-filter-item:hover {
  background: #e2e8f0;
  color: #334155;
}

.tag-filter-item.active {
  background: #1677ff;
  color: white;
  border-color: #1677ff;
  box-shadow: 0 2px 8px rgba(22, 119, 255, 0.3);
}

.dimension-empty {
  padding: 24px;
  text-align: center;
  color: var(--text-light);
  font-size: 14px;
  width: 100%;
}

.dimension-loading {
  padding: 24px;
  text-align: center;
  color: var(--secondary-color);
  font-size: 14px;
  width: 100%;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 18px;
  border-radius: var(--border-radius-md);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  border: 2px solid transparent;
}

.btn-primary {
  background: var(--primary-gradient);
  color: var(--white-color);
  border-color: transparent;
}

.btn-primary:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.btn-secondary {
  background: var(--white-color);
  color: var(--text-primary);
  border-color: var(--border-color);
}

.btn-secondary:hover {
  border-color: var(--secondary-color);
  color: var(--secondary-color);
  background: var(--secondary-light);
}

.btn-text {
  background: transparent;
  border: none;
  padding: 6px 10px;
}

.btn-text:hover {
  color: var(--secondary-color);
  background: var(--secondary-light);
  border-radius: var(--border-radius-sm);
}

.btn-icon {
  font-size: 14px;
}
</style>
