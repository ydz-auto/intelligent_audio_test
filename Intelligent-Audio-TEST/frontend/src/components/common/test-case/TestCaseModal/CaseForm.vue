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

    <!-- ===== 全局背景噪声（case 级 config.background_noise，跨所有轮次持续播放）===== -->
    <div class="form-section global-noise-section">
      <div class="global-noise-header">
        <span class="global-noise-title">
          <i class="fas fa-volume-up"></i> 全局背景噪声
        </span>
        <span class="global-noise-hint">配置后跨所有轮次持续播放，优先于轮次级噪声</span>
        <button
          v-if="!hasGlobalNoise"
          type="button"
          class="btn btn-sm btn-outline-primary"
          @click="addGlobalNoise"
        >
          <i class="fas fa-plus"></i> 添加全局噪声
        </button>
        <button
          v-else
          type="button"
          class="global-noise-remove-btn"
          @click="clearGlobalNoise"
        >
          <i class="fas fa-trash-alt"></i> 移除
        </button>
      </div>

      <div v-if="hasGlobalNoise" class="global-noise-body">
        <!-- 噪声音频卡片 -->
        <div class="global-noise-field">
          <label class="global-noise-field-label">噪声音频</label>
          <div class="global-noise-card">
            <div class="global-noise-card-info">
              <div class="global-noise-card-row">
                <i class="fas fa-music global-noise-card-icon"></i>
                <span class="global-noise-card-name" :title="globalNoiseAudioDisplayName">
                  {{ globalNoiseAudioDisplayName }}
                </span>
                <span class="global-noise-card-duration" v-if="globalNoiseAudioId && getAudioDuration(globalNoiseAudioId) > 0">
                  <i class="fas fa-clock"></i> {{ formatDuration(getAudioDuration(globalNoiseAudioId)) }}
                </span>
              </div>
              <div class="global-noise-card-tags" v-if="globalNoiseAudioId && getAudioTags(globalNoiseAudioId)">
                <span class="global-noise-tag" v-for="tag in getNormalizedTags(getAudioTags(globalNoiseAudioId))" :key="tag">{{ tag }}</span>
              </div>
            </div>
            <div class="global-noise-card-actions">
              <button type="button" class="btn btn-sm btn-outline-primary" @click="openGlobalNoiseAudioModal">
                <i class="fas fa-exchange-alt"></i> 更换
              </button>
              <button type="button" class="btn btn-sm btn-outline-info" v-if="globalNoiseAudioId" @click="previewGlobalNoise">
                <i class="fas fa-play"></i> 试听
              </button>
            </div>
          </div>
        </div>

        <div class="global-noise-field-row">
          <div class="global-noise-field" style="flex:1">
            <label class="global-noise-field-label">声压级 (dB)</label>
            <input
              type="number"
              class="form-control form-control-sm"
              :value="globalNoiseConfig?.spl ?? 0"
              min="0" max="120" step="1"
              @input="updateGlobalNoise('spl', Number(($event.target as HTMLInputElement).value))"
            />
          </div>
          <div class="global-noise-field" style="flex:1">
            <label class="global-noise-field-label">循环播放</label>
            <label class="global-noise-switch">
              <input
                type="checkbox"
                :checked="globalNoiseConfig?.loop ?? true"
                @change="updateGlobalNoise('loop', ($event.target as HTMLInputElement).checked)"
              />
              <span>{{ globalNoiseConfig?.loop ? '是' : '否' }}</span>
            </label>
          </div>
        </div>

        <div class="global-noise-field">
          <label class="global-noise-field-label">播放设备（可多选）</label>
          <div class="global-noise-devices">
            <label v-for="dev in playbackDevices" :key="dev.id" class="global-noise-device-chip">
              <input
                type="checkbox"
                :value="String(dev.id)"
                :checked="isGlobalNoiseDeviceSelected(String(dev.id))"
                @change="toggleGlobalNoiseDevice(String(dev.id), ($event.target as HTMLInputElement).checked)"
              />
              <span>{{ dev.name }}</span>
            </label>
          </div>
        </div>
      </div>
      <div v-else class="global-noise-empty">
        <i class="fas fa-info-circle"></i>
        未配置全局背景噪声，点击"添加全局噪声"开始配置
      </div>
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
import { ref, computed, watch, onMounted, inject, nextTick } from 'vue';
import AlgorithmSelector from '../../AlgorithmSelector.vue';
import RoundConfigEditor from './RoundConfigEditor.vue';
import OverallEvaluationEditor from './OverallEvaluationEditor.vue';
import { useAlgorithmConfig } from '../../../../composables/useAlgorithmConfig';
import { useAlgorithmLabels } from '../../../../composables/useAlgorithmLabels';
import { tagsApi, algorithmApi } from '../../../../utils/api';
import type { TestCaseFormData, RoundConfigItem, PlaybackDevice, BackgroundNoiseConfig } from './types';

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

const { getAlgorithmOptions, getCaseAlgorithmParams: fetchCaseAlgorithmParams } = useAlgorithmConfig();
const { algorithmOptions: fallbackOptions, loadAlgorithms } = useAlgorithmLabels();

const injectedAudioConfig = inject<any>('audioConfig');
const audioConfig = props.audioConfig || injectedAudioConfig;
const injectedDimensions = inject<any[]>('availableDimensions', []);
const availableDimensions = props.dimensionConfig?.availableDimensions || injectedDimensions;

// 当外部传入 testType 时（'api' 或 'e2e'），锁定切换器
const isTestTypeLocked = computed(() => {
  return props.testType === 'api' || props.testType === 'e2e';
});

const localFormData = ref<TestCaseFormData>(createInitialFormData());
const tagsInput = ref('');
const newGroupName = ref('');
const availableTags = ref<string[]>([]);
const algorithmParams = ref<Record<string, any>>({});
const algorithmOptions = ref<{ value: string; name: string }[]>([]);
let isSyncingFromParent = false;

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
    test_type: 'api',
    config: {
      rounds: [{ roundNumber: 1, audios: [] }],
      dimensions: [],
    },
    // 新设计：algorithm_params 独立列（按轮分组），初始为空数组
    algorithm_params: [],
  } as TestCaseFormData;
}

// ---- test_type 切换 ----
function switchTestType(type: 'api' | 'e2e') {
  if (isTestTypeLocked.value && type !== props.testType) return;
  localFormData.value.test_type = type;
  emitFormData();
}

// ---- 录屏模式切换（仅 E2E 多轮用例生效）----
function onRecordModeChange(value: string) {
  const mode = value === 'case' ? 'case' : 'round';
  localFormData.value.config.record_mode = mode;
  emitFormData();
}

// ---- 轮次更新回调 ----
function handleRoundsUpdate(rounds: RoundConfigItem[]) {
  localFormData.value.config.rounds = rounds;
  emitFormData();
}

// ---- 算法参数独立列更新回调 ----
function handleAlgorithmParamsUpdate(params: any[]) {
  localFormData.value.algorithm_params = params;
  emitFormData();
}

// ---- 整体评估维度更新回调 ----
function handleOverallDimensionsUpdate(dimensions: any[]) {
  localFormData.value.config.dimensions = dimensions;
  emitFormData();
}

// ---- 音频选择请求 ----
function handleAudioSelectRequest(audioType: 'dry' | 'noise', callback: (audios: { id: string; name?: string }[]) => void) {
  // 转发到父级处理（打开音频选择弹窗），携带 callback
  emit('openAudioModal', audioType, undefined, callback);
}

// ---- 算法参数定义（从 AlgorithmSelector 获取） ----
const caseAlgorithmParams = ref<any[]>([]);
const algorithmFormSchema = ref<any>(null);

function handleAlgorithmParamsChange(params: any) {
  algorithmParams.value = params || {};
  // 如果返回了 case_algorithm_params，保存到 ref
  if (params?.caseAlgorithmParams) {
    caseAlgorithmParams.value = params.caseAlgorithmParams;
  }
  if (params?.algorithmFormSchema !== undefined) {
    algorithmFormSchema.value = params.algorithmFormSchema;
  }
  emitFormData();
}

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

// ---- 全局背景噪声（case 级 config.background_noise）----
const globalNoiseConfig = computed(() => localFormData.value.config?.background_noise as BackgroundNoiseConfig | undefined);

const hasGlobalNoise = computed(() => {
  const bg = globalNoiseConfig.value;
  return !!(bg && (bg.audioId || (bg as any).audioName || (bg as any).audio));
});

const globalNoiseAudioId = computed(() => globalNoiseConfig.value?.audioId || '');

const globalNoiseAudioDisplayName = computed(() => {
  const bg = globalNoiseConfig.value as any;
  if (!bg) return '';
  if (bg.audioId) {
    const name = audioConfig?.getAudioName?.(bg.audioId);
    if (name && name !== bg.audioId) return name;
  }
  return bg.audioName || bg.audio || '(未选择音频)';
});

const globalNoiseDeviceIdSet = computed<Set<string>>(() => {
  const bg = globalNoiseConfig.value as any;
  if (!bg) return new Set();
  const ids: string[] = Array.isArray(bg.deviceIds) ? bg.deviceIds.map(String) : [];
  const names: string[] = Array.isArray(bg.deviceNames) ? bg.deviceNames : [];
  for (const name of names) {
    const dev = playbackDevices.value.find((d: PlaybackDevice) => d.name === name);
    if (dev && !ids.includes(String(dev.id))) ids.push(String(dev.id));
  }
  return new Set(ids);
});

function isGlobalNoiseDeviceSelected(deviceId: string): boolean {
  return globalNoiseDeviceIdSet.value.has(deviceId);
}

function toggleGlobalNoiseDevice(deviceId: string, checked: boolean) {
  const current = new Set(globalNoiseDeviceIdSet.value);
  if (checked) current.add(deviceId);
  else current.delete(deviceId);
  updateGlobalNoise('deviceIds', Array.from(current));
}

function updateGlobalNoise(key: string, value: unknown) {
  if (!localFormData.value.config) return;
  const existing = (localFormData.value.config.background_noise || { audioId: '', deviceIds: [], spl: 0, loop: true }) as BackgroundNoiseConfig;
  localFormData.value.config.background_noise = { ...existing, [key]: value } as BackgroundNoiseConfig;
  emitFormData();
}

function clearGlobalNoise() {
  if (localFormData.value.config) {
    delete localFormData.value.config.background_noise;
    emitFormData();
  }
}

function addGlobalNoise() {
  // 初始化一个空的全局噪声配置，然后触发音频选择
  if (!localFormData.value.config) return;
  localFormData.value.config.background_noise = { audioId: '', deviceIds: [], spl: 60, loop: true };
  emitFormData();
  // 立即打开音频选择弹窗
  openGlobalNoiseAudioModal();
}

function openGlobalNoiseAudioModal() {
  emit('openAudioModal', 'noise', undefined, (audios: { id: string; name?: string }[]) => {
    if (audios.length > 0) {
      updateGlobalNoise('audioId', audios[0].id);
    }
  });
}

function previewGlobalNoise() {
  const audioId = globalNoiseAudioId.value;
  if (audioId) {
    emit('previewAudio', audioId, 'noise');
  }
}

// 从 audioConfig 获取音频信息的代理方法（模板中使用）
function getAudioName(audioId: string): string {
  return audioConfig?.getAudioName?.(audioId) || audioId;
}
function getAudioTags(audioId: string): string {
  return audioConfig?.getAudioTags?.(audioId) || '';
}
function getAudioDuration(audioId: string): number {
  return audioConfig?.getAudioDuration?.(audioId) || 0;
}
function formatDuration(seconds: number): string {
  return audioConfig?.formatDuration?.(seconds) || '0s';
}
function getNormalizedTags(tagsStr: string): string[] {
  return audioConfig?.getNormalizedTags?.(tagsStr) || [];
}

// ---- 旧版音频相关 computed 已迁移到 RoundConfigEditor ----

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
  // 当外部锁定 testType 时，强制使用该类型
  const forcedTestType = isTestTypeLocked.value ? (props.testType as 'api' | 'e2e') : null;
  // 后端 success_response 会递归将 snake_case 键转为 camelCase，此处归一化回 snake_case 供下游组件统一使用
  const rawAlgParams = (raw as any).algorithmParams || (raw as any).algorithm_params;
  const normalizedAlgParams = Array.isArray(rawAlgParams)
    ? rawAlgParams.map((e: any) => ({
        round_number: e.round_number ?? e.roundNumber,
        params: (e.params || []).map((p: any) => ({
          field_code: p.field_code ?? p.fieldCode,
          field_value: p.field_value ?? p.fieldValue,
        })),
      }))
    : [];
  localFormData.value = {
    id: raw.id,
    name: raw.name || '',
    description: raw.description || '',
    group: raw.group || raw.groupName || raw.group_name || '',
    tags: raw.tags || [],
    algorithmType: raw.algorithmType || raw.algorithm_type || '',
    test_type: forcedTestType || raw.test_type || 'api',
    config: raw.config?.rounds ? {
      ...raw.config,
      // 归一化全局背景噪声：camelCase → snake_case
      background_noise: (raw.config as any).background_noise ?? (raw.config as any).backgroundNoise,
    } : {
      rounds: [{ roundNumber: 1, audios: [] }],
      dimensions: [],
    },
    // 新设计：algorithm_params 作为 test_cases 独立列（按轮分组 [{round_number, params:[{field_code, field_value}]}]）
    algorithm_params: normalizedAlgParams,
  };
  // 从独立列读取第一个 round 的 params，用于 AlgorithmSelector 的 initial-params（单轮编辑器）
  const groupedAlgParams = localFormData.value.algorithm_params as any[];
  const firstEntry = groupedAlgParams.find((e: any) => e.round_number === 1) || groupedAlgParams[0];
  const roundAlgoParams = firstEntry?.params || [];
  algorithmParams.value = Array.isArray(roundAlgoParams)
    ? roundAlgoParams.reduce((acc: Record<string, any>, p: any) => { if (p.field_code) acc[p.field_code] = p.field_value; return acc; }, {})
    : {};
}

function emitFormData() {
  // 同步结构化字段：从 algorithmParams 提取 voiceprint_config 和 interferers
  // 写入后端期望的位置（case_config.voiceprint_config / round_config.interferers）
  syncStructuredFields();
  emit('update', { ...localFormData.value });
}

/**
 * 将 algorithmParams 中的声纹/干扰人参数同步到后端期望的结构化字段：
 * - voiceprint_config → config.voiceprint_config (case 级别)
 * - interferers → round.interferers (round 级别)
 *
 * 新设计：algorithmParams 作为 test_cases 独立列（按轮分组 [{round_number, params:[...]}]）
 * 这里从 localFormData 上的 algorithmParams 独立列按 round_number 读取对应轮的 params。
 * 兼容回退：若独立列缺失，则从 round.algorithmParams 读取（子组件编辑期间仍写入 round）。
 */
function syncStructuredFields() {
  const config = localFormData.value.config;
  if (!config) return;

  // 独立列：按轮分组的 algorithm_params
  const groupedAlgParams: any[] = Array.isArray((localFormData.value as any).algorithm_params)
    ? (localFormData.value as any).algorithm_params
    : [];

  const rounds = config.rounds || [];
  for (const round of rounds) {
    const roundNumber = round.roundNumber ?? 1;
    // 从独立列按 round_number 读取对应轮的 params
    const entry = groupedAlgParams.find((e: any) => e.round_number === roundNumber);
    const params = entry?.params || round.algorithmParams || [];
    const getParam = (code: string) => {
      const item = params.find((p: any) => p.field_code === code);
      return item?.field_value;
    };

    // ---- 声纹注册 → config.voiceprint_config ----
    // voiceprint 是单个对象 { audio_id, spl, playback_device_id, voiceprint_wait_time }
    const vpObj = getParam('voiceprint');
    if (vpObj && typeof vpObj === 'object' && !Array.isArray(vpObj)) {
      config.voiceprint_config = {
        enabled: true,
        audio: vpObj.audio_id ? { id: String(vpObj.audio_id) } : {},
        device: vpObj.playback_device_id ? { id: String(vpObj.playback_device_id) } : {},
        spl: vpObj.spl !== undefined ? Number(vpObj.spl) : undefined,
        waitTime: vpObj.voiceprint_wait_time !== undefined ? Number(vpObj.voiceprint_wait_time) * 1000 : undefined, // 秒→毫秒
      };
    } else {
      delete config.voiceprint_config;
    }

    // ---- 干扰人 → round.interferers ----
    const interferersRaw = getParam('interferers');
    if (interferersRaw) {
      let interfererList: any[] = [];
      if (typeof interferersRaw === 'string') {
        try { interfererList = JSON.parse(interferersRaw); } catch { interfererList = []; }
      } else if (Array.isArray(interferersRaw)) {
        interfererList = interferersRaw;
      }
      // 转换为后端期望的嵌套结构
      round.interferers = interfererList.map((item: any) => ({
        audio: (item.audio_id || item.audioId) ? { id: String(item.audio_id || item.audioId), name: item.audio_name || item.audioName || '' } : {},
        device: (item.playback_device_id || item.playbackDeviceId) ? { id: String(item.playback_device_id || item.playbackDeviceId) } : {},
        spl: item.spl !== undefined ? Number(item.spl) : undefined,
        startDelay: (item.start_delay ?? item.startDelay) !== undefined ? Number(item.start_delay ?? item.startDelay) * 1000 : 0, // 秒→毫秒
        loop: item.loop ?? false,
      }));
    } else {
      round.interferers = [];
    }

    // ---- 翻译方向 → config 顶层（后端执行器直接读取字符串） ----
    const tdStr = getParam('translation_direction');
    const srcLang = getParam('source_language');
    const tgtLang = getParam('target_language');
    if (tdStr !== undefined) config.translation_direction = tdStr;
    if (srcLang !== undefined) config.source_language = srcLang;
    if (tgtLang !== undefined) config.target_language = tgtLang;
    // 如果没有直接的 translation_direction，则从 source/target 组合
    if (!config.translation_direction && srcLang && tgtLang) {
      config.translation_direction = `${srcLang}2${tgtLang}`;
    }
  }
}

function addTags() {
  if (!localFormData.value.tags) localFormData.value.tags = [];
  const tags = tagsInput.value.split(/[，,]/).map(t => t.trim()).filter(t => t && !localFormData.value.tags?.includes(t));
  localFormData.value.tags.push(...tags);
  tagsInput.value = '';
  emitFormData();
}

function removeTag(index: number) {
  (localFormData.value.tags || []).splice(index, 1);
  emitFormData();
}

function selectTag(tag: string) {
  if (!localFormData.value.tags) localFormData.value.tags = [];
  if (!localFormData.value.tags.includes(tag)) {
    localFormData.value.tags.push(tag);
    emitFormData();
  }
}

function autoGenerateName() {
  if (localFormData.value.tags && localFormData.value.tags.length > 0) {
    const filteredTags = localFormData.value.tags.filter(t => t.length <= 25);
    const sortedTags = filteredTags.sort((a, b) => a.length - b.length);
    localFormData.value.name = sortedTags.join('-');
    emitFormData();
  }
}

function handleAlgorithmTypeChange(newType: string) {
  console.log("[CaseForm] algorithmType changed to:", newType);
  localFormData.value.algorithmType = newType;
  emitFormData();
}

// ---- 旧版音频/噪声/维度函数已迁移到 RoundConfigEditor ----

watch(() => props.formData, () => {
  isSyncingFromParent = true;
  initFormData();
  nextTick(() => {
    isSyncingFromParent = false;
  });
}, { immediate: true });

function syncConfigFromParent() {
  if (!props.formData?.config) return;
  isSyncingFromParent = true;
  const parentConfig = props.formData.config;
  if (parentConfig.rounds && Array.isArray(parentConfig.rounds)) {
    localFormData.value.config.rounds = parentConfig.rounds;
  }
  if (parentConfig.dimensions && Array.isArray(parentConfig.dimensions)) {
    localFormData.value.config.dimensions = parentConfig.dimensions;
  }
  nextTick(() => {
    isSyncingFromParent = false;
  });
}

const roundConfigRef = ref<InstanceType<typeof RoundConfigEditor> | null>(null);

const currentRoundIndex = computed(() => roundConfigRef.value?.activeRoundIndex ?? 0);

// ---- Batch operation methods (modify localFormData directly) ----
function getCurrentRoundAudiosLocal(): any[] {
  const config = localFormData.value.config;
  if (!config) return [];
  if (config.rounds && config.rounds.length > 0) {
    const roundIdx = roundConfigRef.value?.activeRoundIndex ?? 0;
    return config.rounds[roundIdx]?.audios || [];
  }
  return (config.audios as any[]) || [];
}

function applyBatchDevice(deviceId: string) {
  const audios = getCurrentRoundAudiosLocal();
  const updated = audios.map((a: any) => ({ ...a, playbackDeviceId: deviceId }));
  if (localFormData.value.config?.rounds) {
    const roundIdx = roundConfigRef.value?.activeRoundIndex ?? 0;
    const round = localFormData.value.config.rounds[roundIdx];
    if (round) {
      localFormData.value.config.rounds = localFormData.value.config.rounds.map((r: any, i: number) =>
        i === roundIdx ? { ...r, audios: updated } : r
      );
    }
  } else if (localFormData.value.config?.audios) {
    localFormData.value.config.audios = updated;
  }
  emitFormData();
}

function applyCrossDevice(deviceIds: string[]) {
  const audios = getCurrentRoundAudiosLocal();
  const updated = audios.map((a: any, idx: number) => ({
    ...a,
    playbackDeviceId: deviceIds[idx % deviceIds.length]
  }));
  if (localFormData.value.config?.rounds) {
    const roundIdx = roundConfigRef.value?.activeRoundIndex ?? 0;
    localFormData.value.config.rounds = localFormData.value.config.rounds.map((r: any, i: number) =>
      i === roundIdx ? { ...r, audios: updated } : r
    );
  } else if (localFormData.value.config?.audios) {
    localFormData.value.config.audios = updated;
  }
  emitFormData();
}

function applyBatchSpl(spl: number) {
  console.log('[applyBatchSpl] called with spl:', spl);
  console.log('[applyBatchSpl] has config:', !!localFormData.value.config);
  console.log('[applyBatchSpl] has rounds:', !!localFormData.value.config?.rounds);
  const audios = getCurrentRoundAudiosLocal();
  console.log('[applyBatchSpl] current round audios count:', audios.length);
  console.log('[applyBatchSpl] current round audios:', JSON.stringify(audios.map(a => ({id: a.audioId, spl: a.spl}))));
  if (audios.length === 0) {
    console.warn('[applyBatchSpl] No audios found, cannot apply batch SPL!');
    return;
  }
  const updated = audios.map((a: any) => ({ ...a, spl }));
  console.log('[applyBatchSpl] updated audios spl:', updated.map(a => a.spl));
  if (localFormData.value.config?.rounds) {
    const roundIdx = roundConfigRef.value?.activeRoundIndex ?? 0;
    console.log('[applyBatchSpl] updating rounds at index:', roundIdx);
    localFormData.value.config.rounds = localFormData.value.config.rounds.map((r: any, i: number) =>
      i === roundIdx ? { ...r, audios: updated } : r
    );
    console.log('[applyBatchSpl] updated round audios spl:', localFormData.value.config.rounds[roundIdx].audios.map((a: any) => a.spl));
  } else if (localFormData.value.config?.audios) {
    localFormData.value.config.audios = updated;
  }
  emitFormData();
  console.log('[applyBatchSpl] emitFormData called');
}

function applySingleDevice(audioIndex: number, deviceId: string) {
  const audios = getCurrentRoundAudiosLocal();
  const updated = audios.map((a: any, i: number) =>
    i === audioIndex ? { ...a, playbackDeviceId: deviceId } : a
  );
  if (localFormData.value.config?.rounds) {
    const roundIdx = roundConfigRef.value?.activeRoundIndex ?? 0;
    localFormData.value.config.rounds = localFormData.value.config.rounds.map((r: any, i: number) =>
      i === roundIdx ? { ...r, audios: updated } : r
    );
  } else if (localFormData.value.config?.audios) {
    localFormData.value.config.audios = updated;
  }
  emitFormData();
}

defineExpose({ syncConfigFromParent, initFormData, algorithmParams, newGroupName, currentRoundIndex, applyBatchDevice, applyCrossDevice, applyBatchSpl, applySingleDevice, getCurrentRoundAudiosLocal });

watch(() => tagSearchQuery.value, () => {
  currentTagPage.value = 1;
});

// Deep watcher removed: explicit emitFormData() calls prevent double-emit.

onMounted(async () => {
  await loadAlgorithms();
  await loadAlgorithmOptions();
  await loadAvailableTags();
  initFormData();
  // 当从 API/E2E 测试页面进入时，AlgorithmSelector 被隐藏，需手动加载算法参数
  if (isTestTypeLocked.value && localFormData.value.algorithmType) {
    await loadAlgorithmParamsForLockedMode(localFormData.value.algorithmType);
  }
});

// 在锁定模式下手动加载算法 schema 和参数定义
async function loadAlgorithmParamsForLockedMode(algoType: string) {
  if (!algoType) return;
  try {
    const [schema, caseParams] = await Promise.all([
      algorithmApi.getFormSchema(algoType),
      fetchCaseAlgorithmParams(algoType)
    ]);
    algorithmFormSchema.value = schema;
    caseAlgorithmParams.value = caseParams || [];
  } catch (e) {
    console.error('[CaseForm] 加载算法参数失败:', e);
  }
}
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
  padding: 2px 8px;
  font-size: 12px;
  font-weight: 500;
  background: var(--secondary-light);
  color: var(--secondary-color);
  border-radius: var(--border-radius-full);
  border: 1px solid transparent;
  max-width: 200px;
}

.tag-item.removable {
  padding-right: 6px;
}

.tag-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

.tag-remove {
  flex-shrink: 0;
  background: none;
  border: none;
  margin-left: 4px;
  cursor: pointer;
  color: var(--secondary-color);
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
  background: var(--secondary-color);
  color: white;
  cursor: default;
}

/* ===== test-type-switcher ===== */
.test-type-section {
  padding: 14px 20px !important;
}

.test-type-switcher-row {
  display: flex;
  align-items: center;
  gap: 16px;
}

.test-type-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.test-type-switcher {
  display: flex;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
}

.test-type-btn {
  padding: 8px 20px;
  font-size: 13px;
  font-weight: 500;
  border: none;
  background: var(--background-primary);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s ease;
}

.test-type-btn:hover {
  background: var(--background-secondary);
}

.test-type-btn.active {
  background: var(--primary-color);
  color: white;
}

.test-type-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.test-type-btn + .test-type-btn {
  border-left: 1px solid var(--border-color);
}

/* ===== round-editor-section ===== */
.round-editor-section {
  padding: 0 !important;
  background: transparent !important;
  border: none !important;
}

/* ===== 全局背景噪声 ===== */
.global-noise-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: var(--background-secondary, #f5f5f5);
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px 8px 0 0;
  border-bottom: none;
  flex-wrap: wrap;
  gap: 8px;
}
.global-noise-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #333);
  display: flex;
  align-items: center;
  gap: 6px;
}
.global-noise-title i { font-size: 12px; color: var(--text-light, #999); }
.global-noise-hint {
  font-size: 11px;
  color: var(--text-light, #999);
  flex: 1;
  min-width: 120px;
}
.global-noise-remove-btn {
  padding: 4px 10px;
  font-size: 12px;
  border: 1px solid var(--danger-color, #f44336);
  border-radius: 4px;
  background: transparent;
  color: var(--danger-color, #f44336);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
  transition: all 0.15s;
}
.global-noise-remove-btn:hover {
  background: var(--danger-color, #f44336);
  color: #fff;
}
.global-noise-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 16px;
  border: 1px dashed #ccc;
  border-radius: 0 0 8px 8px;
  color: #999;
  font-size: 13px;
}
.global-noise-body {
  background: var(--background-primary, #fff);
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 0 0 8px 8px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.global-noise-field { display: flex; flex-direction: column; gap: 3px; }
.global-noise-field-row { display: flex; gap: 12px; }
.global-noise-field-label { font-size: 12px; font-weight: 500; color: var(--text-secondary, #666); }
.global-noise-devices { display: flex; flex-wrap: wrap; gap: 8px; }
.global-noise-device-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid #d0d7de;
  border-radius: 16px;
  background: #f6f8fa;
  font-size: 12px;
  cursor: pointer;
  user-select: none;
}
.global-noise-device-chip input { margin: 0; }
.global-noise-device-chip:has(input:checked) {
  background: #e6f4ff;
  border-color: #4096ff;
  color: #1677ff;
}
.global-noise-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid #e0e7ff;
  border-radius: 6px;
  background: #f8f9ff;
}
.global-noise-card-info { flex: 1; min-width: 0; }
.global-noise-card-row { display: flex; align-items: center; gap: 6px; }
.global-noise-card-icon { color: #6366f1; font-size: 12px; }
.global-noise-card-name {
  font-size: 13px; font-weight: 500; color: #333;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 200px;
}
.global-noise-card-duration {
  font-size: 11px; color: #999;
  display: flex; align-items: center; gap: 3px; white-space: nowrap;
}
.global-noise-card-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.global-noise-tag {
  font-size: 10px; padding: 1px 6px; border-radius: 8px;
  background: #e0e7ff; color: #4f46e5;
}
.global-noise-card-actions { display: flex; gap: 4px; flex-shrink: 0; }
.global-noise-switch {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-secondary, #666);
}
.global-noise-switch input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: var(--primary-color, #ff6a00);
}
</style>
