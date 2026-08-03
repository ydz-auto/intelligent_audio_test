import { ref, computed, watch, onMounted, inject, nextTick } from 'vue';
import { useAlgorithmConfig } from '../../../../composables/algorithm/useAlgorithmConfig';
import { useAlgorithmLabels } from '../../../../composables/algorithm/useAlgorithmLabels';
import { tagsApi, algorithmApi } from '../../../../utils/api';
import type { TestCaseFormData, RoundConfigItem, PlaybackDevice } from './types';

export function useCaseForm(props: any, emit: any) {
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

  const roundConfigRef = ref<any>(null);

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

  return {
    // 模板用到的
    localFormData,
    emitFormData,
    autoGenerateName,
    tagsInput,
    addTags,
    removeTag,
    availableTags,
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
    // defineExpose 用到的
    syncConfigFromParent,
    initFormData,
    currentRoundIndex,
    applyBatchDevice,
    applyCrossDevice,
    applyBatchSpl,
    applySingleDevice,
    getCurrentRoundAudiosLocal,
  };
}
