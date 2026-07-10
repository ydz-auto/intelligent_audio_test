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
import type { TestCaseFormData, RoundConfigItem, PlaybackDevice } from './types';

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
  localFormData.value = {
    id: raw.id,
    name: raw.name || '',
    description: raw.description || '',
    group: raw.group || raw.groupName || raw.group_name || '',
    tags: raw.tags || [],
    algorithmType: raw.algorithmType || raw.algorithm_type || '',
    test_type: forcedTestType || raw.test_type || 'api',
    config: raw.config?.rounds ? raw.config : {
      rounds: [{ roundNumber: 1, audios: [] }],
      dimensions: [],
    },
    // 新设计：algorithm_params 作为 test_cases 独立列（按轮分组 [{round_number, params:[{field_code, field_value}]}]）
    algorithm_params: Array.isArray((raw as any).algorithmParams || (raw as any).algorithm_params)
      ? ((raw as any).algorithmParams || (raw as any).algorithm_params)
      : [],
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
    const vpEnabled = getParam('voiceprintEnabled');
    const vpAudioId = getParam('voiceprintAudioId');
    const vpDeviceId = getParam('voiceprintPlaybackDeviceId');
    const vpSpl = getParam('voiceprintSpl');
    const vpWaitTime = getParam('voiceprintWaitTime');

    if (vpEnabled !== undefined || vpAudioId !== undefined) {
      config.voiceprint_config = {
        enabled: vpEnabled === true || vpEnabled === 'true',
        audio: vpAudioId ? { id: String(vpAudioId) } : {},
        device: vpDeviceId ? { id: String(vpDeviceId) } : {},
        spl: vpSpl !== undefined ? Number(vpSpl) : undefined,
        waitTime: vpWaitTime !== undefined ? Number(vpWaitTime) * 1000 : undefined, // 秒→毫秒
      };
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
        audio: item.audioId ? { id: String(item.audioId), name: item.audioName || '' } : {},
        device: item.playbackDeviceId ? { id: String(item.playbackDeviceId) } : {},
        spl: item.spl !== undefined ? Number(item.spl) : undefined,
        startDelay: item.startDelay !== undefined ? Number(item.startDelay) * 1000 : 0, // 秒→毫秒
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
</style>
