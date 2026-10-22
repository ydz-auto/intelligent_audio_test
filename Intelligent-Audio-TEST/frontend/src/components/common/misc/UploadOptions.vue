<script setup lang="ts">
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/components/form.css'
import '../../../assets/styles/components/navigation.css'
import '../../../assets/styles/components/tag.css'
import '../../../assets/styles/components/log.css'
import '../../../assets/styles/layouts/main.css'

import AudioSelectModal from '../audio/AudioSelectModal.vue'
import AlgorithmSelector from '../audio/AlgorithmSelector.vue'
import DimensionConfigPanel from './DimensionConfigPanel.vue'
import { useUploadOptions } from './UploadOptions'
import type { AlgorithmRelationItem } from './UploadOptions'
import type { DimensionConfigData } from '@/domain/model/audio'

interface Props {
  modelValue: {
    audioType?: string
    createTestCase?: boolean
    testTypes?: ('api' | 'e2e')[]
    playbackDeviceId?: string | number | null
    spl?: number
    noiseAudioId?: string | number | null
    noiseAudioName?: string
    noiseSpl?: number
    inheritTags?: boolean
    /** API 维度配置（DimensionConfigPanel 结构：统一/指定轮次/逐轮 + 多轮整体评估） */
    apiDimensionConfig?: DimensionConfigData
    /** E2E 维度配置（DimensionConfigPanel 结构：统一/指定轮次/逐轮 + 多轮整体评估） */
    e2eDimensionConfig?: DimensionConfigData
    promptDeviceId?: string | number
    algorithmType?: string
    algorithmRelations?: AlgorithmRelationItem[]
    algorithmParams?: Record<string, any> | any[]
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
  filteredDimensions,
  ensureDimensionsLoaded,
  dimensionsLoading,
  dimensionsError,
  dimensionSearchQuery,
  updateDimensionFilter,
  showTestCaseConfig,
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
      <!-- 评估维度单组（INT-714 口径修订：不再按 E2E/API 分型平铺两组；用例类型由后端默认落库） -->
      <div class="options-grid">
        <div class="option-item full-width">
          <label>评估维度 <span class="required">*</span></label>
          <DimensionConfigPanel
            v-model="uploadConfig.e2eDimensionConfig"
            v-model:searchQuery="dimensionSearchQuery"
            :available-dimensions="filteredDimensions"
            :loading="dimensionsLoading"
            :error="dimensionsError"
            :required="true"
          />
          <div class="config-hint">
            <i class="fas fa-info-circle"></i>
            <span>播放设备、声压级、噪声等参数将在用例编辑页面的轮次配置中填写</span>
          </div>
        </div>
      </div>
    </template>


  </div>
</template>

<style scoped>
@import './UploadOptions.css';


/* config-header - 自全局样式就近迁移 */
.config-header {
  display: flex;
  align-items: center;
  cursor: pointer;
  padding: 8px 0;
  border-top: 1px solid var(--border);
  transition: background-color 0.2s ease;
}

.config-header:hover {
  background-color: var(--muted);
}

</style>
