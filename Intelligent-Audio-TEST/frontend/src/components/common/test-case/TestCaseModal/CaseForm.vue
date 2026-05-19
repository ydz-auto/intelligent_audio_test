<template>
  <div class="case-form">
    <div class="form-row">
      <div class="form-group">
        <label for="caseName">用例名称 <span class="required">*</span></label>
        <div class="input-group">
          <input type="text" id="caseName" v-model="localFormData.name" class="form-control" required>
          <div class="input-group-append">
            <button type="button" class="btn btn-outline-secondary auto-generate-btn" @click="autoGenerateName" title="根据标签自动生成名称">
              <i class="fas fa-wand-magic-sparkles mr-1"></i>自动生成
            </button>
          </div>
        </div>
      </div>
      <div class="form-group">
        <label for="caseGroup">所属分组 <span class="required">*</span></label>
        <select id="caseGroup" v-model="localFormData.group" class="form-control" required>
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
        <div class="tags-container mt-2">
          <span v-for="(tag, index) in localFormData.tags" :key="index" class="tag-item">
            {{ tag }}
            <button type="button" class="tag-remove" @click="removeTag(index)">
              <i class="fas fa-times"></i>
            </button>
          </span>
        </div>
        <div v-if="availableTags && availableTags.length > 0" class="existing-tags mt-2">
          <span class="existing-tags-label">已有标签：</span>
          <span
            v-for="tag in (showAllTags ? filteredAvailableTags : filteredAvailableTags.slice(0, 15))"
            :key="tag"
            class="tag-item existing-tag"
            :class="{ 'already-added': localFormData.tags && localFormData.tags.includes(tag) }"
            @click="selectTag(tag)"
          >
            {{ tag }}
          </span>
          <span v-if="filteredAvailableTags.length > 15" class="more-tags" @click="showAllTags = !showAllTags">
            {{ showAllTags ? '收起' : `+${filteredAvailableTags.length - 15} 更多` }}
          </span>
        </div>
      </div>
    </div>

    <div class="form-row">
      <div class="form-group">
        <label for="caseDescription">描述</label>
        <textarea id="caseDescription" v-model="localFormData.description" class="form-control"></textarea>
      </div>
    </div>

    <AlgorithmSelector
      v-model="localFormData.algorithmType"
      :initial-params="algorithmParams"
      :single="true"
      @params-change="handleAlgorithmParamsChange"
      @algorithm-type-change="handleAlgorithmTypeChange"
    />

    <div class="form-section">
      <div class="audio-config-header">
        <h4>音频配置</h4>
        <div class="audio-config-actions" v-if="localFormData.config.audios && localFormData.config.audios.length > 0">
          <button type="button" class="btn btn-secondary btn-sm" @click="sortByFileName('asc')">
            <i class="fas fa-sort-alpha-up"></i> 按文件名正序
          </button>
          <button type="button" class="btn btn-secondary btn-sm" @click="sortByFileName('desc')">
            <i class="fas fa-sort-alpha-down"></i> 按文件名倒序
          </button>
          <button type="button" class="btn btn-secondary btn-sm" @click="shuffleAudioConfigs">
            <i class="fas fa-random"></i> 随机排序
          </button>
          <button type="button" class="btn btn-secondary btn-sm" @click="toggleTagSelector" v-if="getUniqueTagsFromConfigs().length > 1">
            <i class="fas fa-exchange-alt"></i> 标签交叉排列
          </button>
          <button type="button" class="btn btn-secondary btn-sm" @click="toggleTagDeviceSelector(localFormData.config.audios)" v-if="getUniqueTagsFromConfigs().length > 0">
            <i class="fas fa-tags"></i> 标签设备分配
          </button>
          <button type="button" class="btn btn-warning btn-sm" @click="$emit('openBatchDeviceModal')" v-if="hasE2eAudio">
            <i class="fas fa-desktop"></i> 批量设置设备
          </button>
          <button type="button" class="btn btn-info btn-sm" @click="$emit('openCrossDeviceModal')" v-if="hasE2eAudio">
            <i class="fas fa-random"></i> 设备交叉分配
          </button>
          <button type="button" class="btn btn-primary btn-sm" @click="$emit('openBatchSplModal')" v-if="hasE2eAudio">
            <i class="fas fa-volume-up"></i> 批量设置声压
          </button>
          <button type="button" class="btn btn-danger btn-sm" @click="clearAllAudioConfigs">
            <i class="fas fa-trash-alt"></i> 清空全部
          </button>
        </div>
      </div>

      <div class="tag-selector-for-interleave" v-if="showTagSelector && getUniqueTagsFromConfigs().length > 1">
        <div class="tag-selector-list">
          <span
            v-for="tag in getUniqueTagsFromConfigs()"
            :key="tag"
            class="tag-checkbox-item"
            :class="{ selected: selectedTagsForInterleave.includes(tag) }"
            @click="toggleTagSelection(tag)"
          >
            {{ tag }}
          </span>
        </div>
        <div class="tag-interleave-preview" v-if="selectedTagsForInterleave.length >= 2">
          <div class="preview-title">交叉顺序预览：</div>
          <div class="interleave-order-preview">
            <span v-for="(tag, index) in selectedTagsForInterleave" :key="index" class="interleave-tag">
              {{ tag }}
              <span v-if="index < selectedTagsForInterleave.length - 1" class="interleave-arrow">→</span>
            </span>
          </div>
        </div>
        <div class="tag-device-actions">
          <button type="button" class="btn btn-primary btn-sm" @click="interleaveByTags(localFormData.config.audios)" :disabled="selectedTagsForInterleave.length < 2">
            <i class="fas fa-check"></i> 确定
          </button>
          <button type="button" class="btn btn-secondary btn-sm" @click="toggleTagSelector">
            <i class="fas fa-times"></i> 取消
          </button>
        </div>
      </div>

      <div class="tag-selector-for-interleave" v-if="showTagDeviceSelector && getUniqueTagsFromConfigs().length > 0">
        <div class="tag-device-mapping-list">
          <div v-for="tag in getUniqueTagsFromConfigs()" :key="tag" class="tag-device-mapping-row">
            <span class="tag-name">{{ tag }}</span>
            <span class="arrow">→</span>
            <select :value="getDeviceForTag(tag)" @change="updateTagDeviceMapping(tag, ($event.target as HTMLSelectElement).value)" class="device-select">
              <option value="">-- 选择设备 --</option>
              <option v-for="device in playbackDevices" :key="device.id" :value="device.id">
                {{ device.name }} (通道 {{ device.channelIndex }})
              </option>
            </select>
            <span class="audio-count">({{ getTagAudioCount(tag, localFormData.config.audios) }}个音频)</span>
          </div>
        </div>
        <div class="tag-device-preview" v-if="hasValidTagDeviceMapping">
          <div class="preview-title">分配预览：</div>
          <div v-for="[tag, deviceId] in getTagDeviceMapping" :key="tag" class="preview-item">
            • {{ tag }} → {{ getDeviceName(deviceId) }}
          </div>
        </div>
        <div class="tag-device-actions">
          <button type="button" class="btn btn-primary btn-sm" @click="assignDeviceByTags(localFormData.config.audios)" :disabled="!hasValidTagDeviceMapping">
            <i class="fas fa-check"></i> 确定
          </button>
          <button type="button" class="btn btn-secondary btn-sm" @click="toggleTagDeviceSelector(localFormData.config.audios)">
            <i class="fas fa-times"></i> 取消
          </button>
        </div>
      </div>

      <div v-if="!localFormData.config.audios || localFormData.config.audios.length === 0" class="empty-state">
        <p>暂无音频配置，请添加</p>
      </div>

      <div
        v-for="(audioConfig, index) in localFormData.config.audios"
        :key="`audio-${audioConfig.audioId}-${index}`"
        class="dry-audio-item"
        :class="{ 'is-dragging': draggedAudioIndex === index, 'drag-over': dragOverAudioIndex === index }"
        draggable="true"
        @dragstart="handleAudioDragStart(index, $event)"
        @dragend="handleAudioDragEnd"
        @dragover="handleAudioDragOver(index, $event)"
        @drop="handleAudioDrop(index, $event)"
      >
        <div class="dry-audio-header">
          <div class="dry-audio-header-left">
            <span class="drag-handle" title="拖动调整顺序">
              <i class="fas fa-bars"></i>
            </span>
            <span class="dry-audio-index">音频 {{ index + 1 }}</span>
          </div>
          <div class="audio-header-actions">
            <button type="button" class="btn btn-secondary btn-sm" @click="copyAudioConfig(index)">
              <i class="fas fa-copy"></i> 复制
            </button>
            <button type="button" class="btn btn-danger btn-sm" @click="removeAudioConfig(index)">
              <i class="fas fa-trash"></i> 删除
            </button>
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label for="audioFile">音频文件 <span class="required">*</span></label>
            <div class="audio-selector-container" style="cursor: pointer;" @click="$emit('openAudioModal', 'dry', index)">
              <div class="selected-audio-info" v-if="audioConfig.audioId" :title="getAudioName(audioConfig.audioId)">
                {{ getAudioName(audioConfig.audioId) }}
              </div>
              <div class="placeholder" v-else title="未选择音频">
                未选择音频
              </div>
            </div>
            <div class="audio-actions">
              <button type="button" class="btn btn-primary" @click="$emit('openAudioModal', 'dry', index)">
                <i class="fas fa-search"></i> 选择音频
              </button>
              <button type="button" class="btn btn-secondary" @click="$emit('previewAudio', audioConfig.audioId, 'dry')" :disabled="!audioConfig.audioId">
                <i class="fas fa-play"></i> 试听
              </button>
            </div>
            <div class="audio-tags-container" v-if="audioConfig.audioId && getNormalizedTags(getAudioTags(audioConfig.audioId)).length > 0">
              <span class="audio-tags-label">标签：</span>
              <div class="audio-tags-list">
                <span v-for="tag in getNormalizedTags(getAudioTags(audioConfig.audioId))" :key="tag" class="audio-tag-item">
                  {{ tag }}
                </span>
              </div>
            </div>
          </div>

          <div class="form-group">
            <label for="testType">测试类型 <span class="required">*</span></label>
            <select v-model="audioConfig.testType" class="form-control" required>
              <option value="api">API测试</option>
              <option value="e2e">端到端测试</option>
            </select>
          </div>

          <div class="form-group" v-if="audioConfig.testType === 'e2e'">
            <label for="playbackDevice">播放设备 <span class="required">*</span></label>
            <div class="audio-selector-container" style="cursor: pointer;" @click="$emit('openDeviceModal', index)">
              <div class="selected-audio-info" v-if="audioConfig.playbackDeviceId" :title="getDeviceName(audioConfig.playbackDeviceId)">
                {{ getDeviceName(audioConfig.playbackDeviceId) }}
              </div>
              <div class="placeholder" v-else title="未选择设备">
                未选择设备
              </div>
            </div>
            <div class="audio-actions">
              <button type="button" class="btn btn-primary" @click="$emit('openDeviceModal', index)">
                <i class="fas fa-search"></i> 选择设备
              </button>
            </div>
          </div>

          <div class="form-group" v-if="audioConfig.testType === 'e2e'">
            <label for="audioSPL">声压级 (dB) <span class="required">*</span></label>
            <input type="number" v-model.number="audioConfig.spl" class="form-control" min="0" max="120" required>
          </div>

          <div class="form-group">
            <label for="playOrder">播放顺序 <span class="required">*</span></label>
            <input type="number" v-model.number="audioConfig.playOrder" class="form-control" min="0" required>
          </div>
        </div>
      </div>

      <button type="button" class="btn btn-secondary" @click="addAudioConfig">
        <i class="fas fa-plus"></i> 添加音频配置
      </button>
    </div>

    <div class="form-section" v-if="hasE2eAudio">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <h4>端到端测试配置</h4>
        <button type="button" class="btn btn-danger btn-sm" @click="clearNoiseConfig" v-if="localFormData.config.backgroundNoise.audioId || (localFormData.config.backgroundNoise.deviceIds && localFormData.config.backgroundNoise.deviceIds.length > 0)">
          <i class="fas fa-trash"></i> 删除噪声配置
        </button>
      </div>
      <div class="form-section">
        <h5>噪声配置</h5>
        <div class="form-row">
          <div class="form-group">
            <label for="noiseAudio">噪声文件</label>
            <div class="audio-selector-container" style="cursor: pointer;" @click="$emit('openAudioModal', 'noise')">
              <div class="selected-audio-info" v-if="localFormData.config.backgroundNoise.audioId" :title="getAudioName(localFormData.config.backgroundNoise.audioId)">
                {{ getAudioName(localFormData.config.backgroundNoise.audioId) }}
              </div>
              <div class="placeholder" v-else title="无">
                无
              </div>
            </div>
            <div class="audio-actions">
              <button type="button" class="btn btn-primary" @click="$emit('openAudioModal', 'noise')">
                <i class="fas fa-search"></i> 选择音频
              </button>
              <button v-if="localFormData.config.backgroundNoise.audioId" type="button" class="btn btn-secondary" @click="$emit('previewAudio', localFormData.config.backgroundNoise.audioId, 'noise')" :disabled="!localFormData.config.backgroundNoise.audioId">
                <i class="fas fa-play"></i> 试听
              </button>
            </div>
          </div>
          <div class="form-group">
            <label for="noiseAudioSPL">噪声声压级 (dB)</label>
            <input type="number" v-model.number="localFormData.config.backgroundNoise.spl" class="form-control" min="0" max="120">
          </div>
          <div class="form-group">
            <label for="noisePlaybackDevices">播放设备</label>
            <div class="audio-selector-container" style="cursor: pointer;" @click="$emit('openNoiseDeviceModal')">
              <div class="selected-audio-info" v-if="localFormData.config.backgroundNoise.deviceIds && localFormData.config.backgroundNoise.deviceIds.length > 0" :title="getNoiseDeviceNames()">
                {{ getNoiseDeviceNames() }}
              </div>
              <div class="placeholder" v-else title="未选择设备">
                未选择设备
              </div>
            </div>
            <div class="audio-actions">
              <button type="button" class="btn btn-primary" @click="$emit('openNoiseDeviceModal')">
                <i class="fas fa-search"></i> 选择设备
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="form-section">
      <h4>评测维度配置</h4>
      <p v-if="localFormData.algorithmType && associatedDimensions.length > 0" class="dimension-filter-hint">
        <i class="fas fa-filter"></i> 已根据算法类型「{{ localFormData.algorithmType }}」过滤可用维度
      </p>

      <div v-if="hasAPIAudio" class="form-sub-section">
        <h5>API测试评测维度</h5>
        <div class="dimension-cloud-container">
          <div
            v-for="dim in filteredAvailableDimensions"
            :key="dim.id"
            class="dimension-tag"
            :class="{ 'selected': isDimensionSelected(dim.name, 'api') }"
            @click="toggleDimensionSelection(dim, 'api')"
          >
            {{ dim.name }}
          </div>
        </div>

        <div class="selected-dimensions-config" v-if="localFormData.config.dimensions.api.length > 0">
          <h6>已选择维度配置</h6>
          <div v-for="(dimension, index) in localFormData.config.dimensions.api" :key="index" class="selected-dimension-config-item">
            <div class="dimension-config-header">
              <span class="dimension-config-name">{{ dimension.name }}</span>
              <button type="button" class="btn btn-xs btn-danger" @click="removeAPIDimension(index)">
                <i class="fas fa-times"></i> 移除
              </button>
            </div>
            <div class="dimension-config-fields">
              <div class="form-row">
                <div class="form-group">
                  <label>权重（0-100） <span class="required">*</span></label>
                  <input type="number" v-model.number="dimension.weight" class="form-control" min="0" max="100" required>
                </div>
                <div class="form-group">
                  <label>阈值（0-100） <span class="required">*</span></label>
                  <input type="number" v-model.number="dimension.threshold" class="form-control" min="0" max="100" required>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="hasE2eAudio" class="form-sub-section mt-4">
        <h5>端到端测试评测维度</h5>
        <div class="dimension-cloud-container">
          <div
            v-for="dim in filteredAvailableDimensions"
            :key="dim.id"
            class="dimension-tag"
            :class="{ 'selected': isDimensionSelected(dim.name, 'e2e') }"
            @click="toggleDimensionSelection(dim, 'e2e')"
          >
            {{ dim.name }}
          </div>
        </div>

        <div class="selected-dimensions-config" v-if="localFormData.config.dimensions.e2e.length > 0">
          <h6>已选择维度配置</h6>
          <div v-for="(dimension, index) in localFormData.config.dimensions.e2e" :key="index" class="selected-dimension-config-item">
            <div class="dimension-config-header">
              <span class="dimension-config-name">{{ dimension.name }}</span>
              <button type="button" class="btn btn-xs btn-danger" @click="removeE2EDimension(index)">
                <i class="fas fa-times"></i> 移除
              </button>
            </div>
            <div class="dimension-config-fields">
              <div class="form-row">
                <div class="form-group">
                  <label>权重（0-100） <span class="required">*</span></label>
                  <input type="number" v-model.number="dimension.weight" class="form-control" min="0" max="100" required>
                </div>
                <div class="form-group">
                  <label>阈值（0-100） <span class="required">*</span></label>
                  <input type="number" v-model.number="dimension.threshold" class="form-control" min="0" max="100" required>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import AlgorithmSelector from '../../AlgorithmSelector.vue';
import { useAlgorithmConfig } from '../../../../composables/useAlgorithmConfig';
import { useAlgorithmLabels } from '../../../../composables/useAlgorithmLabels';
import { testcasesApi } from '../../../../utils/api';
import { useAudioConfig } from './useAudioConfig';
import { useDimensionConfig } from './useDimensionConfig';
import type { TestCaseFormData, Dimension, AudioConfig } from './types';

const props = defineProps<{
  formData: Partial<TestCaseFormData>;
  testCaseGroups: string[];
}>();

const emit = defineEmits<{
  (e: 'update', data: TestCaseFormData): void;
  (e: 'openAudioModal', audioType: 'dry' | 'noise', index?: number): void;
  (e: 'openDeviceModal', audioIndex: number): void;
  (e: 'openNoiseDeviceModal'): void;
  (e: 'openBatchDeviceModal'): void;
  (e: 'openCrossDeviceModal'): void;
  (e: 'openBatchSplModal'): void;
  (e: 'previewAudio', audioId: string, audioType: 'dry' | 'noise'): void;
}>();

const { getAlgorithmOptions } = useAlgorithmConfig();
const { algorithmOptions: fallbackOptions, loadAlgorithms } = useAlgorithmLabels();

const localFormData = ref<TestCaseFormData>(createInitialFormData());
const tagsInput = ref('');
const newGroupName = ref('');
const showAllTags = ref(false);
const availableTags = ref<string[]>([]);
const algorithmParams = ref<Record<string, any>>({});
const algorithmOptions = ref<{ value: string; name: string }[]>([]);

const audioConfig = useAudioConfig();
const dimensionConfig = useDimensionConfig();

function createInitialFormData(): TestCaseFormData {
  return {
    id: undefined,
    name: '',
    description: '',
    group: '',
    tags: [],
    algorithmType: '',
    config: {
      audios: [{ audioId: '', testType: 'api', playbackDeviceId: '', spl: 65, playOrder: 0 }],
      dimensions: { api: [], e2e: [] },
      backgroundNoise: { audioId: '', deviceIds: [], spl: 0 }
    }
  };
}

const hasAPIAudio = computed(() => {
  return localFormData.value.config.audios.some(audio => audio.testType === 'api');
});

const hasE2eAudio = computed(() => {
  return localFormData.value.config.audios.some(audio => audio.testType === 'e2e');
});

const filteredAvailableTags = computed(() => {
  return availableTags.value.filter(tag => !(localFormData.value.tags || []).includes(tag));
});

async function loadAlgorithmOptions() {
  try {
    const options = await getAlgorithmOptions();
    algorithmOptions.value = (options || []).map((opt: any) => ({
      value: opt.value,
      name: opt.name || opt.label || opt.value
    }));
  } catch (error) {
    algorithmOptions.value = fallbackOptions.value.map((opt: any) => ({ value: opt.value, name: opt.label }));
  }
}

async function loadAvailableTags() {
  try {
    const tags = await testcasesApi.getTags();
    availableTags.value = Array.isArray(tags) ? tags : [];
  } catch (error) {
    availableTags.value = [];
  }
}

function initFormData() {
  const raw = props.formData || {};
  localFormData.value = {
    id: raw.id,
    name: raw.name || '',
    description: raw.description || '',
    group: raw.group || raw.groupName || raw.group_name || '',
    tags: raw.tags || [],
    algorithmType: raw.algorithmType || raw.algorithm_type || '',
    config: raw.config || {
      audios: [{ audioId: '', testType: 'api', playbackDeviceId: '', spl: 65, playOrder: 0 }],
      dimensions: { api: [], e2e: [] },
      backgroundNoise: { audioId: '', deviceIds: [], spl: 0 }
    }
  };
}

function addTags() {
  if (!localFormData.value.tags) localFormData.value.tags = [];
  const tags = tagsInput.value.split(/[，,]/).map(t => t.trim()).filter(t => t && !localFormData.value.tags.includes(t));
  localFormData.value.tags.push(...tags);
  tagsInput.value = '';
}

function removeTag(index: number) {
  (localFormData.value.tags || []).splice(index, 1);
}

function selectTag(tag: string) {
  if (!localFormData.value.tags) localFormData.value.tags = [];
  if (!localFormData.value.tags.includes(tag)) {
    localFormData.value.tags.push(tag);
  }
}

function autoGenerateName() {
  if (localFormData.value.tags && localFormData.value.tags.length > 0) {
    const filteredTags = localFormData.value.tags.filter(t => t.length <= 25);
    const sortedTags = filteredTags.sort((a, b) => a.length - b.length);
    localFormData.value.name = sortedTags.join('-');
  }
}

function handleAlgorithmParamsChange(params: Record<string, any>) {
  algorithmParams.value = params;
}

function handleAlgorithmTypeChange() {
  if (localFormData.value.algorithmType) {
    dimensionConfig.updateAssociatedDimensions(localFormData.value.algorithmType);
  }
}

const {
  playbackDevices,
  getAudioName,
  getAudioTags,
  getNormalizedTags,
  getDeviceName,
  getNoiseDeviceNames,
  handleAudioDragStart,
  handleAudioDragEnd,
  handleAudioDragOver,
  draggedAudioIndex,
  dragOverAudioIndex,
  showTagSelector,
  selectedTagsForInterleave,
  interleaveOrder,
  showTagDeviceSelector,
  tagDeviceMapping,
  hasValidTagDeviceMapping,
  getTagDeviceMapping,
  toggleTagSelector,
  toggleTagSelection,
  interleaveByTags,
  toggleTagDeviceSelector,
  getDeviceForTag,
  updateTagDeviceMapping,
  getTagAudioCount,
  assignDeviceByTags
} = audioConfig;

function handleAudioDrop(index: number, event: DragEvent) {
  audioConfig.handleAudioDrop(index, localFormData.value.config.audios);
}

function clearNoiseConfig() {
  audioConfig.clearNoiseConfig(localFormData.value.config.backgroundNoise);
}

function getUniqueTagsFromConfigs() {
  return audioConfig.getUniqueTagsFromConfigs(localFormData.value.config.audios);
}

function sortByFileName(order: 'asc' | 'desc') {
  audioConfig.sortByFileName(localFormData.value.config.audios, order);
}

function shuffleAudioConfigs() {
  audioConfig.shuffleAudioConfigs(localFormData.value.config.audios);
}

function clearAllAudioConfigs() {
  audioConfig.clearAllAudioConfigs(localFormData.value.config.audios);
}

function addAudioConfig() {
  audioConfig.addAudioConfig(localFormData.value.config.audios);
}

function removeAudioConfig(index: number) {
  audioConfig.removeAudioConfig(index, localFormData.value.config.audios);
}

function copyAudioConfig(index: number) {
  audioConfig.copyAudioConfig(index, localFormData.value.config.audios);
}

const {
  filteredAvailableDimensions,
  associatedDimensions
} = dimensionConfig;

function isDimensionSelected(dimensionName: string, dimensionType: 'api' | 'e2e'): boolean {
  return dimensionConfig.isDimensionSelected(dimensionName, dimensionType, localFormData.value.config.dimensions);
}

function toggleDimensionSelection(dimension: any, dimensionType: 'api' | 'e2e') {
  dimensionConfig.toggleDimensionSelection(dimension, dimensionType, localFormData.value.config.dimensions);
}

function removeAPIDimension(index: number) {
  dimensionConfig.removeAPIDimension(index, localFormData.value.config.dimensions);
}

function removeE2EDimension(index: number) {
  dimensionConfig.removeE2EDimension(index, localFormData.value.config.dimensions);
}

watch(() => props.formData, () => {
  initFormData();
}, { immediate: true, deep: true });

watch(() => localFormData.value, (newVal) => {
  emit('update', { ...newVal });
}, { deep: true });

onMounted(async () => {
  await loadAlgorithms();
  await loadAlgorithmOptions();
  await loadAvailableTags();
  await audioConfig.loadResources();
  await dimensionConfig.loadDimensions();
  initFormData();
});
</script>

<style scoped>
.case-form {
  padding: 0;
}

.form-row {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.form-group {
  flex: 1;
  min-width: 200px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #495057;
}

.required {
  color: #dc3545;
  font-weight: bold;
}

.form-control {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ced4da;
  border-radius: 6px;
  font-size: 14px;
  transition: all 0.2s;
  box-sizing: border-box;
}

.form-control:focus {
  outline: none;
  border-color: #007bff;
  box-shadow: 0 0 0 0.2rem rgba(0, 123, 255, 0.25);
}

.form-section {
  margin: 24px 0;
  padding: 20px;
  background-color: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #e9ecef;
}

.form-section h4 {
  margin-top: 0;
  margin-bottom: 16px;
  font-size: 18px;
  font-weight: 600;
  color: #343a40;
}

.form-sub-section {
  margin: 16px 0;
  padding: 16px;
  background-color: white;
  border-radius: 6px;
  border: 1px solid #e9ecef;
}

.audio-config-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.audio-config-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.dry-audio-item {
  background: white;
  border: 1px solid #e9ecef;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
}

.dry-audio-item.is-dragging {
  opacity: 0.5;
}

.dry-audio-item.drag-over {
  border-color: #007bff;
}

.dry-audio-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.dry-audio-header-left {
  display: flex;
  align-items: center;
}

.drag-handle {
  cursor: grab;
  color: #6c757d;
  margin-right: 8px;
}

.audio-selector-container {
  padding: 10px 12px;
  border: 1px solid #ced4da;
  border-radius: 6px;
  background: white;
  min-height: 42px;
}

.selected-audio-info {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.placeholder {
  color: #6c757d;
}

.audio-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.audio-tags-container {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 8px;
  padding: 8px;
  background: #f8f9fa;
  border-radius: 6px;
}

.audio-tags-label {
  font-size: 12px;
  color: #6c757d;
  flex-shrink: 0;
}

.audio-tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.audio-tag-item {
  padding: 3px 8px;
  font-size: 11px;
  cursor: default;
  background-color: transparent;
  color: var(--primary-color);
  border: 1px solid var(--primary-color);
  border-radius: var(--border-radius-full);
  white-space: nowrap;
}

.tags-container {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag-item {
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  font-size: 11px;
  cursor: default;
  background-color: transparent;
  color: var(--primary-color);
  border: 1px solid var(--primary-color);
  border-radius: var(--border-radius-full);
  white-space: nowrap;
}

.tag-remove {
  background: none;
  border: none;
  margin-left: 4px;
  cursor: pointer;
  color: #6c757d;
}

.existing-tags {
  font-size: 12px;
}

.existing-tag {
  cursor: pointer;
  margin-right: 4px;
}

.existing-tag.already-added {
  opacity: 0.5;
  cursor: not-allowed;
}

.dimension-cloud-container {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.dimension-tag {
  padding: 6px 12px;
  background: #e9ecef;
  border-radius: 16px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.dimension-tag.selected {
  background: #007bff;
  color: white;
}

.dimension-tag:hover {
  background: #ced4da;
}

.dimension-tag.selected:hover {
  background: #0056b3;
}

.selected-dimensions-config {
  margin-top: 16px;
}

.selected-dimension-config-item {
  background: white;
  border: 1px solid #e9ecef;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 8px;
}

.dimension-config-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.dimension-config-name {
  font-weight: 500;
}

.empty-state {
  text-align: center;
  padding: 24px;
  color: #6c757d;
}

.tag-selector-for-interleave {
  background: white;
  border: 1px solid #007bff;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}

.tag-selector-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.tag-checkbox-item {
  padding: 6px 12px;
  background: #e9ecef;
  border-radius: 16px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.tag-checkbox-item.selected {
  background: #007bff;
  color: white;
}

.tag-checkbox-item:hover {
  background: #ced4da;
}

.tag-checkbox-item.selected:hover {
  background: #0056b3;
}

.tag-interleave-preview {
  margin-bottom: 12px;
  padding: 12px;
  background: #f8f9fa;
  border-radius: 6px;
}

.preview-title {
  font-size: 12px;
  color: #6c757d;
  margin-bottom: 8px;
}

.interleave-order-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.interleave-tag {
  padding: 4px 8px;
  background: #007bff;
  color: white;
  border-radius: 4px;
  font-size: 12px;
}

.interleave-arrow {
  color: #6c757d;
  font-weight: bold;
}

.tag-device-actions {
  display: flex;
  gap: 8px;
}

.tag-device-mapping-list {
  margin-bottom: 12px;
}

.tag-device-mapping-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid #e9ecef;
}

.tag-device-mapping-row:last-child {
  border-bottom: none;
}

.tag-name {
  font-weight: 500;
  min-width: 80px;
}

.arrow {
  color: #6c757d;
}

.device-select {
  flex: 1;
  padding: 6px 10px;
  border: 1px solid #ced4da;
  border-radius: 4px;
  font-size: 13px;
}

.audio-count {
  color: #6c757d;
  font-size: 12px;
}

.tag-device-preview {
  margin-bottom: 12px;
  padding: 12px;
  background: #f8f9fa;
  border-radius: 6px;
}

.preview-item {
  font-size: 13px;
  margin-bottom: 4px;
}
</style>
