<script setup lang="ts">
import AudioSelectModal from '../audio/AudioSelectModal.vue'
import AlgorithmSelector from '../audio/AlgorithmSelector.vue'
import { useUploadOptions } from './UploadOptions'
import type { AlgorithmRelationItem } from './UploadOptions'

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
    /** API 维度使用范围（可多选） */
    apiScopes?: ('single' | 'multi')[]
    /** E2E 维度使用范围（可多选） */
    e2eScopes?: ('single' | 'multi')[]
    /** @deprecated 旧字段，兼容用 */
    apiRoundScope?: 'single' | 'multi'
    e2eRoundScope?: 'single' | 'multi'
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

const {
  localTags,
  uploadConfig,
  computedAudioTypeOptions,
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
  updateDimensionFilter,
  hasApiDimensions,
  hasE2eDimensions,
  apiScopes,
  e2eScopes,
  toggleApiScope,
  toggleE2eScope,
  setApiDimensions,
  setE2eDimensions,
  toggleApiDimension,
  toggleE2eDimension,
  showTestCaseConfig,
  showApiConfig,
  showE2eConfig,
  noiseSelectModalVisible,
  algorithmParams,
  associatedDimensionIds,
  algorithmRelations,
  handleAlgorithmParamsChange,
  handleAlgorithmRelationsChange,
  handleDimensionsChange,
  openNoiseSelectModal,
  handleNoiseSelect,
  clearNoiseAudio,
} = useUploadOptions(props, emit)
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
                value="e2e"
                v-model="uploadConfig.testTypes"
              >
              <span class="checkbox-text">E2E测试</span>
            </label>
            <label class="checkbox-label">
              <input
                type="checkbox"
                value="api"
                v-model="uploadConfig.testTypes"
              >
              <span class="checkbox-text">API测试</span>
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
            <!-- 维度使用范围选择 -->
            <div class="round-scope-selector">
              <span class="round-scope-label">维度使用范围：</span>
              <label class="checkbox-label">
                <input type="checkbox" :checked="apiScopes.includes('single')" @change="toggleApiScope('single')">
                <span class="checkbox-text">单轮评估</span>
              </label>
              <label class="checkbox-label">
                <input type="checkbox" :checked="apiScopes.includes('multi')" @change="toggleApiScope('multi')">
                <span class="checkbox-text">多轮聚合</span>
              </label>
              <span class="round-scope-hint" v-if="apiScopes.includes('single') && apiScopes.includes('multi')">每轮独立评估 + 多轮结果聚合</span>
              <span class="round-scope-hint" v-else-if="apiScopes.includes('single')">每个轮次独立评估该维度</span>
              <span class="round-scope-hint" v-else>多轮结果聚合后评估该维度</span>
            </div>
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
            <!-- 维度使用范围选择 -->
            <div class="round-scope-selector">
              <span class="round-scope-label">维度使用范围：</span>
              <label class="checkbox-label">
                <input type="checkbox" :checked="e2eScopes.includes('single')" @change="toggleE2eScope('single')">
                <span class="checkbox-text">单轮评估</span>
              </label>
              <label class="checkbox-label">
                <input type="checkbox" :checked="e2eScopes.includes('multi')" @change="toggleE2eScope('multi')">
                <span class="checkbox-text">多轮聚合</span>
              </label>
              <span class="round-scope-hint" v-if="e2eScopes.includes('single') && e2eScopes.includes('multi')">每轮独立评估 + 多轮结果聚合</span>
              <span class="round-scope-hint" v-else-if="e2eScopes.includes('single')">每个轮次独立评估该维度</span>
              <span class="round-scope-hint" v-else>多轮结果聚合后评估该维度</span>
            </div>
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
@import './UploadOptions.css';
</style>
