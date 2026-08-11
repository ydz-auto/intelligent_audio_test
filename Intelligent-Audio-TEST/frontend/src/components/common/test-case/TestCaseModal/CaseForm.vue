<template>
  <div class="case-form">
    <div class="form-section basic-info-section">
      <div class="form-row">
        <div class="form-group">
          <label for="caseName">用例名称 <span class="required">*</span></label>
          <div class="input-with-action">
            <input type="text" id="caseName" v-model="localFormData.name" class="form-control" required @input="emitFormData">
            <button type="button" class="btn btn-outline-primary btn-auto-generate" @click="autoGenerateName" title="根据标签自动生成名称">
              <i class="fas fa-wand-magic-sparkles"></i>
              <span>自动生成</span>
            </button>
          </div>
        </div>
        <div class="form-group">
          <label for="caseGroup">所属分组 <span class="required">*</span></label>
          <select id="caseGroup" v-model="localFormData.group" class="form-control" required @change="emitFormData">
            <option value="" disabled>请选择分组</option>
            <option v-for="group in testCaseGroups" :key="group" :value="group">{{ group }}</option>
            <option value="new-group">+ 新建分组</option>
          </select>
          <input v-if="localFormData.group === 'new-group'" type="text" class="form-control mt-2" placeholder="输入新分组名称" v-model="newGroupName">
        </div>
      </div>

      <div class="form-row">
        <div class="form-group">
          <label for="caseTags">标签</label>
          <div class="tag-input-wrapper">
            <input
              type="text"
              id="caseTags"
              v-model="tagsInput"
              class="form-control"
              placeholder="输入标签，按回车或逗号添加"
              @keydown.enter.prevent="addTags"
            >
          </div>
          <div class="tags-container mt-2" v-if="localFormData.tags && localFormData.tags.length > 0">
            <span v-for="(tag, index) in localFormData.tags" :key="index" class="tag-item removable">
              <span class="tag-text" :title="tag">{{ tag }}</span>
              <button type="button" class="tag-remove" @click="removeTag(index)">
                <i class="fas fa-times"></i>
              </button>
            </span>
          </div>
          <div v-if="availableTags && availableTags.length > 0" class="existing-tags-section mt-2">
            <div class="existing-tags-header">
              <span class="existing-tags-label">已有标签：</span>
              <div class="tag-search-box">
                <i class="fas fa-search"></i>
                <input type="text" v-model="tagSearchQuery" placeholder="搜索标签..." class="tag-search-input">
              </div>
              <div class="tag-pagination" v-if="totalTagPages > 1">
                <button type="button" class="tag-page-btn" :disabled="currentTagPage === 1" @click="currentTagPage--">
                  <i class="fas fa-chevron-left"></i>
                </button>
                <span class="tag-page-info">{{ currentTagPage }} / {{ totalTagPages }}</span>
                <button type="button" class="tag-page-btn" :disabled="currentTagPage === totalTagPages" @click="currentTagPage++">
                  <i class="fas fa-chevron-right"></i>
                </button>
              </div>
            </div>
            <div class="existing-tags-list">
              <span
                v-for="tag in paginatedAvailableTags"
                :key="tag"
                class="tag-item selectable"
                :class="{ 'already-added': localFormData.tags && localFormData.tags.includes(tag) }"
                @click="selectTag(tag)"
              >
                {{ tag }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div class="form-row">
        <div class="form-group">
          <label for="caseDescription">描述</label>
          <textarea id="caseDescription" v-model="localFormData.description" class="form-control" rows="2" @input="emitFormData"></textarea>
        </div>
      </div>
    </div>

    <AlgorithmSelector
      v-if="!isTestTypeLocked"
      v-model="localFormData.algorithmType"
      :initial-params="algorithmParams"
      :single="true"
      :show-params="false"
      @params-change="handleAlgorithmParamsChange"
      @algorithm-type-change="handleAlgorithmTypeChange"
    />

    <!-- ===== test_type 切换器（仅用例管理页面显示） ===== -->
    <div class="form-section test-type-section" v-if="!isTestTypeLocked">
      <div class="test-type-switcher-row">
        <label class="test-type-label">测试类型</label>
        <div class="test-type-switcher">
          <button
            type="button"
            class="test-type-btn"
            :class="{ active: localFormData.test_type === 'api' }"
            @click="switchTestType('api')"
          >
            <i class="fas fa-cloud"></i> API
          </button>
          <button
            type="button"
            class="test-type-btn"
            :class="{ active: localFormData.test_type === 'e2e' }"
            @click="switchTestType('e2e')"
          >
            <i class="fas fa-microchip"></i> E2E
          </button>
        </div>
      </div>
    </div>

    <!-- ===== 轮次配置编辑器（替换旧的音频/噪声/维度三大区块） ===== -->
    <div class="form-section round-editor-section">
      <RoundConfigEditor
        ref="roundConfigRef"
        v-model="localFormData.config.rounds"
        :test-type="localFormData.test_type || 'api'"
        :case-algorithm-params="caseAlgorithmParams"
        :algorithm-type="localFormData.algorithmType"
        :algorithm-form-schema="algorithmFormSchema"
        :algorithm-params="localFormData.algorithm_params"
        @update:model-value="handleRoundsUpdate"
        @update:algorithm-params="handleAlgorithmParamsUpdate"
        @open-audio-select="handleAudioSelectRequest"
        @open-device-modal="(audioIndex: number) => emit('openDeviceModal', audioIndex)"
        @open-batch-device-modal="() => emit('openBatchDeviceModal')"
        @open-cross-device-modal="() => emit('openCrossDeviceModal')"
        @open-batch-spl-modal="() => emit('openBatchSplModal')"
        @preview-audio="(audioId: string, audioType: 'dry' | 'noise') => emit('previewAudio', audioId, audioType)"
      />
    </div>

    <!-- ===== 全局背景噪声（config.background_noise，多轮共享）===== -->
    <div v-if="localFormData.config.rounds && localFormData.config.rounds.length > 1" class="form-section global-noise-section">
      <GlobalNoiseEditor
        v-model="localFormData.config.background_noise as any"
        :playback-devices="playbackDevices"
        @update:model-value="handleGlobalNoiseUpdate"
        @open-audio-select="handleAudioSelectRequest"
        @preview-audio="(audioId: string) => emit('previewAudio', audioId)"
      />
    </div>

    <!-- ===== 整体评估维度（config.dimensions）===== -->
    <div v-if="localFormData.config.rounds && localFormData.config.rounds.length > 1" class="form-section overall-eval-section">
      <OverallEvaluationEditor
        v-model="localFormData.config.dimensions"
        :available-dimensions="availableDimensions"
        :algorithm-type="localFormData.algorithmType"
        @update:model-value="handleOverallDimensionsUpdate"
      />
    </div>

      <!-- RoundConfigEditor 已替换旧的音频/噪声/维度配置区块 -->
  </div>
</template>

<script setup lang="ts">
import AlgorithmSelector from '../../audio/AlgorithmSelector.vue';
import RoundConfigEditor from './RoundConfigEditor.vue';
import OverallEvaluationEditor from './OverallEvaluationEditor.vue';
import GlobalNoiseEditor from './GlobalNoiseEditor.vue';
import type { TestCaseFormData } from './types';
import { useCaseForm } from './CaseForm';

const props = defineProps<{
  formData: Partial<TestCaseFormData>;
  testCaseGroups: string[];
  audioConfig?: any;
  dimensionConfig?: any;
  testType?: string;
}>();

const emit = defineEmits<{
  (e: 'update', data: TestCaseFormData): void;
  (e: 'openAudioModal', audioType: 'dry' | 'noise', index?: number, callback?: (audios: { id: string; name?: string }[]) => void): void;
  (e: 'openDeviceModal', audioIndex: number): void;
  (e: 'openNoiseDeviceModal'): void;
  (e: 'openBatchDeviceModal'): void;
  (e: 'openCrossDeviceModal'): void;
  (e: 'openBatchSplModal'): void;
  (e: 'previewAudio', audioId: string, audioType: 'dry' | 'noise'): void;
}>();

const {
  localFormData,
  emitFormData,
  autoGenerateName,
  tagsInput,
  addTags,
  removeTag,
  tagSearchQuery,
  totalTagPages,
  currentTagPage,
  paginatedAvailableTags,
  selectTag,
  newGroupName,
  isTestTypeLocked,
  switchTestType,
  algorithmParams,
  caseAlgorithmParams,
  algorithmFormSchema,
  handleAlgorithmParamsChange,
  handleAlgorithmTypeChange,
  handleRoundsUpdate,
  handleAlgorithmParamsUpdate,
  handleAudioSelectRequest,
  handleOverallDimensionsUpdate,
  availableDimensions,
  roundConfigRef,
  syncConfigFromParent,
  initFormData,
  currentRoundIndex,
  applyBatchDevice,
  applyCrossDevice,
  applyBatchSpl,
  applySingleDevice,
  getCurrentRoundAudiosLocal,
} = useCaseForm(props, emit);

defineExpose({ syncConfigFromParent, initFormData, algorithmParams, newGroupName, currentRoundIndex, applyBatchDevice, applyCrossDevice, applyBatchSpl, applySingleDevice, getCurrentRoundAudiosLocal });
</script>

<style scoped>
@import './CaseForm.css';
</style>
