<template>
  <div class="case-form">
    <div class="form-section basic-info-section">
      <div class="form-row">
        <div class="form-group">
          <label for="caseName">用例名称 <span class="required">*</span></label>
          <div class="input-with-action">
            <input type="text" id="caseName" v-model="localFormData.name" class="form-control" required>
            <button type="button" class="btn btn-outline-primary btn-auto-generate" @click="autoGenerateName" title="根据标签自动生成名称">
              <i class="fas fa-wand-magic-sparkles"></i>
              <span>自动生成</span>
            </button>
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
          <div class="tags-container mt-2" v-if="localFormData.tags && localFormData.tags.length > 0">
            <span v-for="(tag, index) in localFormData.tags" :key="index" class="tag-item removable">
              {{ tag }}
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
          <textarea id="caseDescription" v-model="localFormData.description" class="form-control" rows="2"></textarea>
        </div>
      </div>
    </div>

    <AlgorithmSelector
      v-model="localFormData.algorithmType"
      :initial-params="algorithmParams"
      :single="true"
      @params-change="handleAlgorithmParamsChange"
      @algorithm-type-change="handleAlgorithmTypeChange"
    />

    <div class="form-section audio-config-section">
      <div class="section-header">
        <h4><i class="fas fa-music"></i> 音频配置</h4>
        <div class="section-actions" v-if="localFormData.config.audios && localFormData.config.audios.length > 0">
          <div class="action-group">
            <span class="action-group-label">排序</span>
            <button type="button" class="btn btn-sm btn-outline-secondary" @click="sortByFileName('asc')" title="按文件名正序">
              <i class="fas fa-sort-alpha-up"></i>
            </button>
            <button type="button" class="btn btn-sm btn-outline-secondary" @click="sortByFileName('desc')" title="按文件名倒序">
              <i class="fas fa-sort-alpha-down"></i>
            </button>
            <button type="button" class="btn btn-sm btn-outline-secondary" @click="shuffleAudioConfigs" title="随机排序">
              <i class="fas fa-random"></i>
            </button>
          </div>
          <div class="action-group" v-if="getUniqueTagsFromConfigs(localFormData.config.audios).length > 1">
            <span class="action-group-label">标签操作</span>
            <button type="button" class="btn btn-sm btn-outline-info" @click="toggleTagSelector">
              <i class="fas fa-exchange-alt"></i> 标签交叉排列
            </button>
            <button type="button" class="btn btn-sm btn-outline-info" @click="toggleTagDeviceSelector(localFormData.config.audios)">
              <i class="fas fa-tags"></i> 标签设备分配
            </button>
          </div>
          <div class="action-group" v-if="hasE2eAudio">
            <span class="action-group-label">批量操作</span>
            <button type="button" class="btn btn-sm btn-outline-warning" @click="$emit('openBatchDeviceModal')">
              <i class="fas fa-desktop"></i> 设置设备
            </button>
            <button type="button" class="btn btn-sm btn-outline-primary" @click="$emit('openCrossDeviceModal')">
              <i class="fas fa-random"></i> 设备交叉
            </button>
            <button type="button" class="btn btn-sm btn-outline-success" @click="$emit('openBatchSplModal')">
              <i class="fas fa-volume-up"></i> 设置声压
            </button>
          </div>
          <div class="action-group">
            <button type="button" class="btn btn-sm btn-outline-danger" @click="clearAllAudioConfigs">
              <i class="fas fa-trash-alt"></i> 清空
            </button>
          </div>
        </div>
      </div>

      <div class="tag-selector-panel" v-if="showTagSelector && getUniqueTagsFromConfigs(localFormData.config.audios).length > 1">
        <div class="tag-selector-list">
          <span
            v-for="tag in getUniqueTagsFromConfigs(localFormData.config.audios)"
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
        <div class="tag-selector-actions">
          <button type="button" class="btn btn-sm btn-primary" @click="interleaveByTags(localFormData.config.audios)" :disabled="selectedTagsForInterleave.length < 2">
            <i class="fas fa-check"></i> 确定
          </button>
          <button type="button" class="btn btn-sm btn-secondary" @click="toggleTagSelector">
            <i class="fas fa-times"></i> 取消
          </button>
        </div>
      </div>

      <div class="tag-selector-panel" v-if="showTagDeviceSelector && getUniqueTagsFromConfigs(localFormData.config.audios).length > 0">
        <div class="tag-device-mapping-list">
          <div v-for="tag in getUniqueTagsFromConfigs(localFormData.config.audios)" :key="tag" class="tag-device-mapping-row">
            <span class="tag-name">{{ tag }}</span>
            <span class="arrow">→</span>
            <select :value="getDeviceForTag(tag)" @change="updateTagDeviceMapping(tag, ($event.target as HTMLSelectElement).value)" class="form-control form-control-sm device-select">
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
        <div class="tag-selector-actions">
          <button type="button" class="btn btn-sm btn-primary" @click="assignDeviceByTags(localFormData.config.audios)" :disabled="!hasValidTagDeviceMapping">
            <i class="fas fa-check"></i> 确定
          </button>
          <button type="button" class="btn btn-sm btn-secondary" @click="toggleTagDeviceSelector(localFormData.config.audios)">
            <i class="fas fa-times"></i> 取消
          </button>
        </div>
      </div>

      <div v-if="!localFormData.config.audios || localFormData.config.audios.length === 0" class="empty-state">
        <i class="fas fa-music"></i>
        <p>暂无音频配置</p>
        <button type="button" class="btn btn-primary" @click="addAudioConfig">
          <i class="fas fa-plus"></i> 添加音频配置
        </button>
      </div>

      <div v-else class="audio-config-list">
        <div
          v-for="(audioConfig, index) in localFormData.config.audios"
          :key="`audio-${audioConfig.audioId}-${index}`"
          class="audio-config-card"
          :class="{ 'is-dragging': draggedAudioIndex === index, 'drag-over': dragOverAudioIndex === index }"
          draggable="true"
          @dragstart="handleAudioDragStart(index, $event)"
          @dragend="handleAudioDragEnd"
          @dragover="handleAudioDragOver(index, $event)"
          @drop="handleAudioDrop(index, $event)"
        >
          <div class="audio-card-header">
            <div class="audio-card-header-left">
              <span class="drag-handle" title="拖动调整顺序">
                <i class="fas fa-grip-vertical"></i>
              </span>
              <span class="audio-index">音频 {{ index + 1 }}</span>
              <span class="audio-name" v-if="audioConfig.audioId" :title="getAudioName(audioConfig.audioId)">
                {{ getAudioName(audioConfig.audioId) }}
              </span>
            </div>
            <div class="audio-card-actions">
              <button type="button" class="btn btn-icon btn-outline-secondary" @click="copyAudioConfig(index)" title="复制">
                <i class="fas fa-copy"></i>
              </button>
              <button type="button" class="btn btn-icon btn-outline-danger" @click="removeAudioConfig(index)" title="删除">
                <i class="fas fa-trash"></i>
              </button>
            </div>
          </div>
          <div class="audio-card-body">
            <div class="audio-field audio-field-full">
              <label>音频文件 <span class="required">*</span></label>
              <div class="audio-selector" @click="$emit('openAudioModal', 'dry', index)">
                <div class="selected-info" v-if="audioConfig.audioId">
                  {{ getAudioName(audioConfig.audioId) }}
                </div>
                <div class="placeholder" v-else>未选择音频</div>
              </div>
              <div class="audio-actions">
                <button type="button" class="btn btn-sm btn-primary" @click.stop="$emit('openAudioModal', 'dry', index)">
                  <i class="fas fa-search"></i> 选择
                </button>
                <button type="button" class="btn btn-sm btn-outline-secondary" @click.stop="$emit('previewAudio', audioConfig.audioId, 'dry')" :disabled="!audioConfig.audioId">
                  <i class="fas fa-play"></i> 试听
                </button>
              </div>
              <div class="audio-tags" v-if="audioConfig.audioId && getNormalizedTags(getAudioTags(audioConfig.audioId)).length > 0">
                <span class="audio-tags-label">标签：</span>
                <div class="audio-tags-list">
                  <span v-for="tag in getNormalizedTags(getAudioTags(audioConfig.audioId))" :key="tag" class="audio-tag">
                    {{ tag }}
                  </span>
                </div>
              </div>
            </div>
            <div class="audio-field-row">
              <div class="audio-field">
                <label>测试类型 <span class="required">*</span></label>
                <select v-model="audioConfig.testType" class="form-control">
                  <option value="api">API测试</option>
                  <option value="e2e">端到端测试</option>
                </select>
              </div>
              <div class="audio-field audio-field-sm">
                <label>播放顺序</label>
                <input type="number" v-model.number="audioConfig.playOrder" class="form-control" min="0">
              </div>
            </div>
            <template v-if="audioConfig.testType === 'e2e'">
              <div class="audio-field-row">
                <div class="audio-field">
                  <label>播放设备 <span class="required">*</span></label>
                  <div class="audio-selector" @click="$emit('openDeviceModal', index)">
                    <div class="selected-info" v-if="audioConfig.playbackDeviceId">
                      {{ getDeviceName(audioConfig.playbackDeviceId) }}
                    </div>
                    <div class="placeholder" v-else>未选择设备</div>
                  </div>
                  <button type="button" class="btn btn-sm btn-primary mt-1" @click.stop="$emit('openDeviceModal', index)">
                    <i class="fas fa-search"></i> 选择设备
                  </button>
                </div>
                <div class="audio-field audio-field-sm">
                  <label>声压级 (dB) <span class="required">*</span></label>
                  <input type="number" v-model.number="audioConfig.spl" class="form-control" min="0" max="120">
                </div>
              </div>
            </template>
          </div>
        </div>
      </div>

      <button type="button" class="btn btn-outline-primary add-audio-btn" @click="addAudioConfig" v-if="localFormData.config.audios && localFormData.config.audios.length > 0">
        <i class="fas fa-plus"></i> 添加音频配置
      </button>
    </div>

    <div class="form-section noise-config-section" v-if="hasE2eAudio">
      <div class="section-header">
        <h4><i class="fas fa-volume-up"></i> 端到端测试配置</h4>
        <button type="button" class="btn btn-sm btn-outline-danger" @click="clearNoiseConfig" v-if="localFormData.config.backgroundNoise.audioId || (localFormData.config.backgroundNoise.deviceIds && localFormData.config.backgroundNoise.deviceIds.length > 0)">
          <i class="fas fa-trash"></i> 删除噪声配置
        </button>
      </div>
      <div class="noise-config-body">
        <h5>噪声配置</h5>
        <div class="form-row">
          <div class="form-group">
            <label>噪声文件</label>
            <div class="audio-selector" @click="$emit('openAudioModal', 'noise')">
              <div class="selected-info" v-if="localFormData.config.backgroundNoise.audioId">
                {{ getAudioName(localFormData.config.backgroundNoise.audioId) }}
              </div>
              <div class="placeholder" v-else>无</div>
            </div>
            <div class="audio-actions">
              <button type="button" class="btn btn-sm btn-primary" @click="$emit('openAudioModal', 'noise')">
                <i class="fas fa-search"></i> 选择
              </button>
              <button v-if="localFormData.config.backgroundNoise.audioId" type="button" class="btn btn-sm btn-outline-secondary" @click="$emit('previewAudio', localFormData.config.backgroundNoise.audioId, 'noise')">
                <i class="fas fa-play"></i> 试听
              </button>
            </div>
          </div>
          <div class="form-group form-group-sm">
            <label>噪声声压级 (dB)</label>
            <input type="number" v-model.number="localFormData.config.backgroundNoise.spl" class="form-control" min="0" max="120">
          </div>
          <div class="form-group">
            <label>播放设备</label>
            <div class="audio-selector" @click="$emit('openNoiseDeviceModal')">
              <div class="selected-info" v-if="localFormData.config.backgroundNoise.deviceIds && localFormData.config.backgroundNoise.deviceIds.length > 0">
                {{ getNoiseDeviceNames() }}
              </div>
              <div class="placeholder" v-else>未选择设备</div>
            </div>
            <button type="button" class="btn btn-sm btn-primary mt-1" @click="$emit('openNoiseDeviceModal')">
              <i class="fas fa-search"></i> 选择设备
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="form-section dimension-config-section">
      <div class="section-header">
        <h4><i class="fas fa-chart-bar"></i> 评测维度配置</h4>
      </div>
      <p v-if="localFormData.algorithmType && associatedDimensions.length > 0" class="dimension-filter-hint">
        <i class="fas fa-filter"></i> 已根据算法类型「{{ localFormData.algorithmType }}」过滤可用维度
      </p>

      <div v-if="hasAPIAudio" class="dimension-sub-section">
        <h5>API测试评测维度</h5>
        <div class="dimension-cloud">
          <div
            v-for="dim in filteredAvailableDimensions"
            :key="dim.id"
            class="dimension-chip"
            :class="{ 'selected': isDimensionSelected(dim.name, 'api') }"
            @click="toggleDimensionSelection(dim, 'api')"
          >
            {{ dim.name }}
          </div>
        </div>
        <div class="selected-dimensions" v-if="localFormData.config.dimensions.api.length > 0">
          <div v-for="(dimension, index) in localFormData.config.dimensions.api" :key="index" class="selected-dimension-card">
            <div class="dimension-card-header">
              <span class="dimension-name">{{ dimension.name }}</span>
              <button type="button" class="btn btn-icon btn-xs btn-outline-danger" @click="removeAPIDimension(index)">
                <i class="fas fa-times"></i>
              </button>
            </div>
            <div class="dimension-card-body">
              <div class="dimension-field">
                <label>权重</label>
                <input type="number" v-model.number="dimension.weight" class="form-control" min="0" max="100">
              </div>
              <div class="dimension-field">
                <label>阈值</label>
                <input type="number" v-model.number="dimension.threshold" class="form-control" min="0" max="100">
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="hasE2eAudio" class="dimension-sub-section">
        <h5>端到端测试评测维度</h5>
        <div class="dimension-cloud">
          <div
            v-for="dim in filteredAvailableDimensions"
            :key="dim.id"
            class="dimension-chip"
            :class="{ 'selected': isDimensionSelected(dim.name, 'e2e') }"
            @click="toggleDimensionSelection(dim, 'e2e')"
          >
            {{ dim.name }}
          </div>
        </div>
        <div class="selected-dimensions" v-if="localFormData.config.dimensions.e2e.length > 0">
          <div v-for="(dimension, index) in localFormData.config.dimensions.e2e" :key="index" class="selected-dimension-card">
            <div class="dimension-card-header">
              <span class="dimension-name">{{ dimension.name }}</span>
              <button type="button" class="btn btn-icon btn-xs btn-outline-danger" @click="removeE2EDimension(index)">
                <i class="fas fa-times"></i>
              </button>
            </div>
            <div class="dimension-card-body">
              <div class="dimension-field">
                <label>权重</label>
                <input type="number" v-model.number="dimension.weight" class="form-control" min="0" max="100">
              </div>
              <div class="dimension-field">
                <label>阈值</label>
                <input type="number" v-model.number="dimension.threshold" class="form-control" min="0" max="100">
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, inject } from 'vue';
import AlgorithmSelector from '../../AlgorithmSelector.vue';
import { useAlgorithmConfig } from '../../../../composables/useAlgorithmConfig';
import { useAlgorithmLabels } from '../../../../composables/useAlgorithmLabels';
import { tagsApi } from '../../../../utils/api';
import type { TestCaseFormData, Dimension, AudioConfig, PlaybackDevice } from './types';

const props = defineProps<{
  formData: Partial<TestCaseFormData>;
  testCaseGroups: string[];
  audioConfig?: any;
  dimensionConfig?: any;
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

const injectedAudioConfig = inject<any>('audioConfig');
const injectedDimensionConfig = inject<any>('dimensionConfig');

const audioConfig = props.audioConfig || injectedAudioConfig;
const dimensionConfig = props.dimensionConfig || injectedDimensionConfig;

const localFormData = ref<TestCaseFormData>(createInitialFormData());
const tagsInput = ref('');
const newGroupName = ref('');
const availableTags = ref<string[]>([]);
const algorithmParams = ref<Record<string, any>>({});
const algorithmOptions = ref<{ value: string; name: string }[]>([]);

const TAGS_PER_PAGE = 15;
const currentTagPage = ref(1);
const tagSearchQuery = ref('');

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
    let tags = availableTags.value;
    if (tagSearchQuery.value.trim()) {
      const query = tagSearchQuery.value.toLowerCase().trim();
      tags = tags.filter(tag => tag.toLowerCase().includes(query));
    }
    return tags;
  });

  const totalTagPages = computed(() => {
    return Math.ceil(filteredAvailableTags.value.length / TAGS_PER_PAGE);
  });

  const paginatedAvailableTags = computed(() => {
    const start = (currentTagPage.value - 1) * TAGS_PER_PAGE;
    const end = start + TAGS_PER_PAGE;
    return filteredAvailableTags.value.slice(start, end);
  });

const playbackDevices = computed<PlaybackDevice[]>(() => {
  return audioConfig?.playbackDevices?.value || [];
});

const draggedAudioIndex = computed(() => audioConfig?.draggedAudioIndex?.value);
const dragOverAudioIndex = computed(() => audioConfig?.dragOverAudioIndex?.value);
const showTagSelector = computed(() => audioConfig?.showTagSelector?.value);
const selectedTagsForInterleave = computed(() => audioConfig?.selectedTagsForInterleave?.value);
const showTagDeviceSelector = computed(() => audioConfig?.showTagDeviceSelector?.value);
const hasValidTagDeviceMapping = computed(() => audioConfig?.hasValidTagDeviceMapping?.value);
const getTagDeviceMapping = computed(() => audioConfig?.getTagDeviceMapping?.value);
const filteredAvailableDimensions = computed(() => dimensionConfig?.filteredAvailableDimensions?.value || []);
const associatedDimensions = computed(() => dimensionConfig?.associatedDimensions?.value || []);

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
    const response = await tagsApi.getTagNames({ perPage: 100 });
    if (response && response.items && Array.isArray(response.items)) {
      availableTags.value = response.items;
    } else if (Array.isArray(response)) {
      availableTags.value = response;
    } else {
      availableTags.value = [];
    }
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
  if (localFormData.value.algorithmType && dimensionConfig) {
    dimensionConfig.updateAssociatedDimensions(localFormData.value.algorithmType);
  }
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
  if (localFormData.value.algorithmType && dimensionConfig) {
    dimensionConfig.updateAssociatedDimensions(localFormData.value.algorithmType);
  }
}

function getAudioName(audioId: string | number): string {
  return audioConfig?.getAudioName?.(audioId) || '未知音频';
}

function getAudioTags(audioId: string | number): string {
  return audioConfig?.getAudioTags?.(audioId) || '';
}

function getNormalizedTags(tagsStr: string): string[] {
  return audioConfig?.getNormalizedTags?.(tagsStr) || [];
}

function getDeviceName(deviceId: string | number): string {
  return audioConfig?.getDeviceName?.(deviceId) || '未知设备';
}

function getNoiseDeviceNames(): string {
  return audioConfig?.getNoiseDeviceNames?.(localFormData.value.config.backgroundNoise) || '';
}

function handleAudioDragStart(index: number, event: DragEvent) {
  audioConfig?.handleAudioDragStart?.(index, event);
}

function handleAudioDragEnd() {
  audioConfig?.handleAudioDragEnd?.();
}

function handleAudioDragOver(index: number, event: DragEvent) {
  audioConfig?.handleAudioDragOver?.(index, event);
}

function handleAudioDrop(index: number, event: DragEvent) {
  audioConfig?.handleAudioDrop?.(index, localFormData.value.config.audios);
}

function clearNoiseConfig() {
  audioConfig?.clearNoiseConfig?.(localFormData.value.config.backgroundNoise);
}

function getUniqueTagsFromConfigs() {
  return audioConfig?.getUniqueTagsFromConfigs?.(localFormData.value.config.audios) || [];
}

function sortByFileName(order: 'asc' | 'desc') {
  audioConfig?.sortByFileName?.(localFormData.value.config.audios, order);
}

function shuffleAudioConfigs() {
  audioConfig?.shuffleAudioConfigs?.(localFormData.value.config.audios);
}

function clearAllAudioConfigs() {
  audioConfig?.clearAllAudioConfigs?.(localFormData.value.config.audios);
}

function addAudioConfig() {
  audioConfig?.addAudioConfig?.(localFormData.value.config.audios);
}

function removeAudioConfig(index: number) {
  audioConfig?.removeAudioConfig?.(index, localFormData.value.config.audios);
}

function copyAudioConfig(index: number) {
  audioConfig?.copyAudioConfig?.(index, localFormData.value.config.audios);
}

function toggleTagSelector() {
  audioConfig?.toggleTagSelector?.();
}

function toggleTagSelection(tag: string) {
  audioConfig?.toggleTagSelection?.(tag);
}

function interleaveByTags(audios: AudioConfig[]) {
  audioConfig?.interleaveByTags?.(audios);
}

function toggleTagDeviceSelector(audios: AudioConfig[]) {
  audioConfig?.toggleTagDeviceSelector?.(audios);
}

function getDeviceForTag(tag: string): string {
  return audioConfig?.getDeviceForTag?.(tag) || '';
}

function updateTagDeviceMapping(tag: string, deviceId: string) {
  audioConfig?.updateTagDeviceMapping?.(tag, deviceId);
}

function getTagAudioCount(tag: string, audios: AudioConfig[]): number {
  return audioConfig?.getTagAudioCount?.(tag, audios) || 0;
}

function assignDeviceByTags(audios: AudioConfig[]) {
  audioConfig?.assignDeviceByTags?.(audios);
}

function isDimensionSelected(dimensionName: string, dimensionType: 'api' | 'e2e'): boolean {
  return dimensionConfig?.isDimensionSelected?.(dimensionName, dimensionType, localFormData.value.config.dimensions) || false;
}

function toggleDimensionSelection(dimension: any, dimensionType: 'api' | 'e2e') {
  dimensionConfig?.toggleDimensionSelection?.(dimension, dimensionType, localFormData.value.config.dimensions);
}

function removeAPIDimension(index: number) {
  dimensionConfig?.removeAPIDimension?.(index, localFormData.value.config.dimensions);
}

function removeE2EDimension(index: number) {
  dimensionConfig?.removeE2EDimension?.(index, localFormData.value.config.dimensions);
}

watch(() => props.formData, () => {
  initFormData();
}, { immediate: true, deep: true });

watch(() => tagSearchQuery.value, () => {
  currentTagPage.value = 1;
});

watch(() => localFormData.value, (newVal) => {
  emit('update', { ...newVal });
}, { deep: true });

onMounted(async () => {
  await loadAlgorithms();
  await loadAlgorithmOptions();
  await loadAvailableTags();
  if (audioConfig?.loadResources) {
    await audioConfig.loadResources();
  }
  if (dimensionConfig?.loadDimensions) {
    await dimensionConfig.loadDimensions();
  }
  initFormData();
});
</script>

<style scoped>
.case-form {
  padding: 0;
}

.form-section {
  margin-bottom: 24px;
  padding: 20px;
  background: var(--background-secondary);
  border-radius: var(--border-radius-lg);
  border: 1px solid var(--border-color);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
}

.section-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-header h4 i {
  color: var(--primary-color);
}

.section-actions {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.action-group {
  display: flex;
  align-items: center;
  gap: 6px;
}

.action-group-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-right: 4px;
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

.form-group-sm {
  max-width: 150px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-weight: 500;
  color: var(--text-primary);
  font-size: 13px;
}

.required {
  color: var(--danger-color);
}

.input-with-action {
  display: flex;
  gap: 8px;
}

.input-with-action .form-control {
  flex: 1;
}

.btn-auto-generate {
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 6px;
}

.tag-input-wrapper {
  position: relative;
}

.tags-container {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag-item {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 500;
  background: var(--primary-light);
  color: var(--primary-color);
  border-radius: var(--border-radius-full);
  border: 1px solid transparent;
}

.tag-item.removable {
  padding-right: 6px;
}

.tag-remove {
  background: none;
  border: none;
  margin-left: 4px;
  cursor: pointer;
  color: var(--primary-color);
  opacity: 0.7;
  padding: 2px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.tag-remove:hover {
  opacity: 1;
}

.existing-tags-section {
  background: white;
  border-radius: var(--border-radius-md);
  padding: 12px;
  border: 1px solid var(--border-color);
}

.existing-tags-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}

.existing-tags-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.tag-search-box {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--background-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-md);
  padding: 4px 8px;
  flex: 1;
  max-width: 200px;
}

.tag-search-box i {
  color: var(--text-secondary);
  font-size: 12px;
}

.tag-search-input {
  border: none;
  background: transparent;
  outline: none;
  font-size: 12px;
  width: 100%;
  color: var(--text-primary);
}

.tag-search-input::placeholder {
  color: var(--text-light);
}

.tag-pagination {
  display: flex;
  align-items: center;
  gap: 6px;
}

.tag-page-btn {
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  padding: 2px 6px;
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 11px;
}

.tag-page-btn:hover:not(:disabled) {
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.tag-page-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.tag-page-info {
  font-size: 11px;
  color: var(--text-secondary);
}

.existing-tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag-item.selectable {
  cursor: pointer;
  background: var(--secondary-light);
  color: var(--secondary-color);
  transition: all 0.2s ease;
}

.tag-item.selectable:hover {
  background: var(--secondary-color);
  color: white;
  transform: translateY(-1px);
}

.tag-item.selectable.already-added {
  opacity: 0.5;
  cursor: not-allowed;
  background: var(--gray-light-color);
  color: var(--text-light);
}

.tag-selector-panel {
  background: white;
  border: 2px solid var(--primary-color);
  border-radius: var(--border-radius-lg);
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
  padding: 6px 14px;
  background: var(--secondary-light);
  border-radius: var(--border-radius-full);
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s ease;
}

.tag-checkbox-item:hover {
  background: var(--secondary-color);
  color: white;
}

.tag-checkbox-item.selected {
  background: var(--primary-color);
  color: white;
}

.tag-interleave-preview {
  margin-bottom: 12px;
  padding: 12px;
  background: var(--background-secondary);
  border-radius: var(--border-radius-md);
}

.preview-title {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.interleave-order-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.interleave-tag {
  padding: 4px 10px;
  background: var(--primary-color);
  color: white;
  border-radius: 4px;
  font-size: 12px;
}

.interleave-arrow {
  color: var(--text-secondary);
  font-weight: bold;
}

.tag-selector-actions {
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
  padding: 10px 0;
  border-bottom: 1px solid var(--border-color);
}

.tag-device-mapping-row:last-child {
  border-bottom: none;
}

.tag-name {
  font-weight: 500;
  min-width: 80px;
}

.arrow {
  color: var(--text-secondary);
}

.device-select {
  flex: 1;
  max-width: 250px;
}

.audio-count {
  color: var(--text-secondary);
  font-size: 12px;
}

.tag-device-preview {
  margin-bottom: 12px;
  padding: 12px;
  background: var(--background-secondary);
  border-radius: var(--border-radius-md);
}

.preview-item {
  font-size: 13px;
  margin-bottom: 4px;
  color: var(--text-primary);
}

.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: var(--text-secondary);
}

.empty-state i {
  font-size: 48px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.empty-state p {
  margin-bottom: 16px;
}

.audio-config-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.audio-config-card {
  background: white;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-lg);
  overflow: hidden;
  transition: all 0.2s ease;
}

.audio-config-card:hover {
  box-shadow: var(--shadow-sm);
}

.audio-config-card.is-dragging {
  opacity: 0.5;
  border-style: dashed;
}

.audio-config-card.drag-over {
  border-color: var(--primary-color);
  border-width: 2px;
}

.audio-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--background-secondary);
  border-bottom: 1px solid var(--border-color);
}

.audio-card-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.drag-handle {
  cursor: grab;
  color: var(--text-secondary);
  padding: 4px;
}

.drag-handle:hover {
  color: var(--primary-color);
}

.audio-index {
  font-weight: 600;
  color: var(--text-primary);
  font-size: 13px;
}

.audio-name {
  font-size: 12px;
  color: var(--text-secondary);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.audio-card-actions {
  display: flex;
  gap: 6px;
}

.btn-icon {
  width: 32px;
  height: 32px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--border-radius-md);
}

.audio-card-body {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.audio-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.audio-field-full {
  width: 100%;
}

.audio-field-row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.audio-field-row .audio-field {
  flex: 1;
  min-width: 150px;
}

.audio-field-sm {
  max-width: 120px;
}

.audio-field label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
}

.audio-selector {
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-md);
  background: white;
  cursor: pointer;
  min-height: 40px;
  transition: all 0.2s ease;
}

.audio-selector:hover {
  border-color: var(--primary-color);
}

.selected-info {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: var(--text-primary);
}

.placeholder {
  color: var(--text-light);
  font-size: 13px;
}

.audio-actions {
  display: flex;
  gap: 6px;
  margin-top: 6px;
}

.audio-tags {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 8px;
  padding: 8px;
  background: var(--background-secondary);
  border-radius: var(--border-radius-sm);
}

.audio-tags-label {
  font-size: 11px;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.audio-tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.audio-tag {
  padding: 2px 8px;
  font-size: 11px;
  background: var(--primary-light);
  color: var(--primary-color);
  border-radius: var(--border-radius-full);
}

.add-audio-btn {
  margin-top: 12px;
}

.noise-config-body {
  background: white;
  border-radius: var(--border-radius-md);
  padding: 16px;
}

.noise-config-body h5 {
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.dimension-config-section {
  background: white;
}

.dimension-filter-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 14px;
  background: var(--info-light);
  color: var(--info-color);
  border-radius: var(--border-radius-md);
  font-size: 13px;
  margin-bottom: 16px;
}

.dimension-sub-section {
  margin-bottom: 20px;
  padding: 16px;
  background: var(--background-secondary);
  border-radius: var(--border-radius-md);
}

.dimension-sub-section:last-child {
  margin-bottom: 0;
}

.dimension-sub-section h5 {
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.dimension-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.dimension-chip {
  padding: 8px 16px;
  background: var(--secondary-light);
  color: var(--secondary-color);
  border-radius: var(--border-radius-full);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  border: 1px solid transparent;
  transition: all 0.2s ease;
}

.dimension-chip:hover {
  background: rgba(22, 119, 255, 0.15);
  border-color: var(--primary-color);
  transform: translateY(-1px);
}

.dimension-chip.selected {
  background: var(--primary-color);
  color: white;
  border-color: var(--primary-color);
}

.selected-dimensions {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.selected-dimension-card {
  background: white;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-md);
  overflow: hidden;
}

.dimension-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  background: var(--background-secondary);
  border-bottom: 1px solid var(--border-color);
}

.dimension-name {
  font-weight: 500;
  font-size: 13px;
  color: var(--text-primary);
}

.btn-xs {
  width: 24px;
  height: 24px;
  padding: 0;
  font-size: 10px;
}

.dimension-card-body {
  padding: 12px 14px;
  display: flex;
  gap: 16px;
}

.dimension-field {
  flex: 1;
}

.dimension-field label {
  display: block;
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.dimension-field .form-control {
  height: 36px;
  font-size: 13px;
}

@media (max-width: 768px) {
  .audio-card-body {
    grid-template-columns: 1fr;
  }
  
  .section-actions {
    flex-direction: column;
    align-items: flex-start;
  }
  
  .selected-dimensions {
    grid-template-columns: 1fr;
  }
}
</style>
