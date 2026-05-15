import { ref, computed, watch } from 'vue';
import { useModalStore } from '../store/modalStore';
import { playbackApi, audiosApi, testcasesApi } from '../utils/api';
import { normalizeTestCaseConfig } from '../utils/utils';
import { useAlgorithmConfig } from './useAlgorithmConfig';
import { useAlgorithmLabels } from './useAlgorithmLabels';
import { useDimensions } from './useDimensions';

export interface AudioItem {
  id: string | number;
  name: string;
  audioType?: string;
  tags?: string | string[];
}

export interface PlaybackDevice {
  id: string | number;
  name: string;
  channelIndex?: number;
}

export interface Dimension {
  id: string | number;
  name: string;
  description?: string;
}

export interface AlgorithmOption {
  value: string;
  name: string;
}

export interface AssociatedDimension {
  id: number;
  name: string;
  description?: string;
  type?: string;
  weight: number;
  is_default: boolean;
}

export interface TestCaseGroupItem {
  name?: string;
  group?: string;
  id?: string | number;
  [key: string]: unknown;
}

export interface ImportPreviewItem {
  name: string;
  type: string;
  group: string;
  operation: 'update' | 'insert';
}

export interface ImportPreviewData {
  total: number;
  items: ImportPreviewItem[];
  audioConfigsCount: number;
  apiDimensionsCount: number;
  e2eDimensionsCount: number;
  tagsCount: number;
  groupsCount: number;
  sheetNames: string[];
}

export interface GroupStat {
  name: string;
  total: number;
  api: number;
  e2e: number;
}

export interface TestCase {
  id?: string | number;
  name?: string;
  group_name?: string;
  group?: string;
  groupName?: string;
  group_id?: string | number;
  groupId?: string | number;
  type?: string | string[];
  testType?: string | string[];
  config?: {
    audios?: Array<{
      testType: string;
      audioId?: string;
    }>;
  };
}

export interface LocalFormData {
  id?: string | number;
  name?: string;
  group?: string;
  groupId?: string | number;
  group_id?: string | number;
  tags?: string[];
  description?: string;
  algorithmType?: string;
  algorithm_params?: Array<{ fieldCode: string; fieldValue: unknown }>;
  reference_params?: Array<{ fieldCode: string; fieldValue: unknown }>;
  config: {
    audios: Array<{
      audioId: string;
      testType: string;
      playbackDeviceId?: string;
      spl?: number;
      playOrder: number;
    }>;
    dimensions: {
      api: Array<{ id?: string | number; name: string; weight: number; threshold: number }>;
      e2e: Array<{ id?: string | number; name: string; weight: number; threshold: number }>;
    };
    backgroundNoise: {
      audioId: string;
      deviceIds: string[];
      spl: number;
    };
  };
  _originalGroup?: string;
  _originalGroupId?: string | number;
}

export interface UseTestCaseModalOptions {
  mode: 'case' | 'group' | 'import' | 'export';
  formData?: Record<string, unknown>;
}

export function useTestCaseModal(options: UseTestCaseModalOptions) {
  const modalStore = useModalStore();
  const isDraftRestored = ref(false);
  const isInitializing = ref(false);

  const {
    getAlgorithmOptions,
    getFormSchema,
    getAssociatedDimensions
  } = useAlgorithmConfig();

  const { algorithmOptions: fallbackOptions, loadAlgorithms } = useAlgorithmLabels();

  const { fetchAllDimensions, fetchDimensionsByAlgorithmType } = useDimensions();

  const draftId = computed(() => {
    if (options.formData?.id) {
      return null;
    }
    if (options.mode === 'case') return 'addTestCase';
    if (options.mode === 'group') return 'addTestGroup';
    return null;
  });

  const isEditMode = computed(() => {
    if (options.mode === 'group') {
      return !!options.formData?.name;
    } else if (options.mode === 'case') {
      return !!options.formData?.id;
    }
    return false;
  });

  const algorithmOptions = ref<AlgorithmOption[]>([
    { value: 'translation', name: '翻译' },
    { value: 'asr', name: 'ASR识别' },
    { value: 'speaker_recognition', name: '说话人识别' },
    { value: 'tts', name: '语音合成' },
    { value: 'asr_eval', name: 'ASR评估' }
  ]);

  const algorithmParams = ref<Record<string, unknown>>({});
  const referenceParams = ref<Record<string, unknown>>({});
  const associatedDimensions = ref<AssociatedDimension[]>([]);

  const testCaseGroups = ref<string[]>([]);
  const tagsInput = ref('');
  const newGroupName = ref('');
  const availableTags = ref<string[]>([]);
  const showAllTags = ref(false);

  const playbackDevices = ref<PlaybackDevice[]>([]);
  const dryAudios = ref<AudioItem[]>([]);
  const noiseAudios = ref<AudioItem[]>([]);
  const availableDimensions = ref<Dimension[]>([]);

  const localFormData = ref<LocalFormData>(initFormData());

  async function performInitialization() {
    if (isInitializing.value) {
      return;
    }
    isInitializing.value = true;

    algorithmParams.value = {};
    referenceParams.value = {};

    try {
      await Promise.all([
        loadTestGroups(),
        loadAlgorithmOptions(),
        loadAvailableTags()
      ]);

      const data = initFormData();
      localFormData.value = data;

      tagsInput.value = '';

      if (data.algorithmType) {
        await loadAlgorithmFormSchema(data.algorithmType as string);
        await loadDimensions(data.algorithmType as string);
      } else {
        await loadDimensions();
      }
    } finally {
      setTimeout(() => {
        isInitializing.value = false;
      }, 0);
    }
  }

  function initFormData(): LocalFormData {
    const rawFormData = options.formData ?? {};
    let initialAlgorithmType = '';
    if (rawFormData.algorithmType !== undefined && rawFormData.algorithmType !== '') {
      initialAlgorithmType = rawFormData.algorithmType as string;
    }

    if (!isEditMode.value && draftId.value) {
      const draft = modalStore.getDraft(draftId.value);
      if (draft) {
        const formDataCopy = JSON.parse(JSON.stringify(rawFormData));
        const mergedData = { ...draft };
        for (const key of Object.keys(formDataCopy)) {
          const value = (formDataCopy as Record<string, unknown>)[key];
          if (value !== '' && value !== null && value !== undefined) {
            if (typeof value === 'object' && Object.keys(value).length > 0) {
              (mergedData as Record<string, unknown>)[key] = value;
            } else if (typeof value !== 'object') {
              (mergedData as Record<string, unknown>)[key] = value;
            }
          }
        }
        modalStore.clearDraft(draftId.value);
        isDraftRestored.value = true;
        return mergedData as LocalFormData;
      }
    }

    isDraftRestored.value = false;
    const rawFormDataForCopy = JSON.parse(JSON.stringify(rawFormData));

    if (!rawFormDataForCopy.config) {
      rawFormDataForCopy.config = {};
    }

    const normalizedConfig = normalizeTestCaseConfig(rawFormDataForCopy.config);
    delete (normalizedConfig as Record<string, unknown>).apiAudios;
    delete (normalizedConfig as Record<string, unknown>).dryAudios;
    rawFormDataForCopy.config = normalizedConfig;

    if (!Array.isArray(rawFormDataForCopy.config.audios) || rawFormDataForCopy.config.audios.length === 0) {
      rawFormDataForCopy.config.audios = [
        {
          audioId: '',
          testType: 'api',
          playbackDeviceId: '',
          spl: 65,
          playOrder: 0
        }
      ];
    }

    if (!rawFormDataForCopy.config.dimensions || Array.isArray(rawFormDataForCopy.config.dimensions)) {
      rawFormDataForCopy.config.dimensions = { api: [], e2e: [] };
    } else {
      rawFormDataForCopy.config.dimensions.api = rawFormDataForCopy.config.dimensions.api || [];
      rawFormDataForCopy.config.dimensions.e2e = rawFormDataForCopy.config.dimensions.e2e || [];
    }

    if (!rawFormDataForCopy.config.backgroundNoise) {
      rawFormDataForCopy.config.backgroundNoise = { audioId: '', deviceIds: [], spl: 0 };
    } else {
      rawFormDataForCopy.config.backgroundNoise.audioId = rawFormDataForCopy.config.backgroundNoise.audioId ?? '';
      rawFormDataForCopy.config.backgroundNoise.deviceIds = Array.isArray(rawFormDataForCopy.config.backgroundNoise.deviceIds)
        ? rawFormDataForCopy.config.backgroundNoise.deviceIds
        : rawFormDataForCopy.config.backgroundNoise.deviceId
          ? [rawFormDataForCopy.config.backgroundNoise.deviceId]
          : [];
      rawFormDataForCopy.config.backgroundNoise.spl = rawFormDataForCopy.config.backgroundNoise.spl ?? 0;
    }

    if (!rawFormDataForCopy.tags) {
      rawFormDataForCopy.tags = [];
    }

    if (rawFormDataForCopy.group === undefined || rawFormDataForCopy.group === '') {
      rawFormDataForCopy.group = rawFormDataForCopy.groupName || rawFormDataForCopy.group_name || '';
    }

    delete rawFormDataForCopy.algorithm_params;
    delete rawFormDataForCopy.reference_params;

    rawFormDataForCopy._originalGroup = rawFormDataForCopy.group;
    rawFormDataForCopy._originalGroupId = rawFormDataForCopy.groupId || rawFormDataForCopy.group_id || '';

    if (!rawFormDataForCopy.algorithmType) {
      rawFormDataForCopy.algorithmType = rawFormDataForCopy.algorithm_type || initialAlgorithmType || '';
    }

    if (rawFormDataForCopy.algorithm_params || rawFormDataForCopy.algorithmParams) {
      const params = rawFormDataForCopy.algorithm_params || rawFormDataForCopy.algorithmParams || [];
      if (Array.isArray(params)) {
        algorithmParams.value = params.reduce((acc: Record<string, unknown>, item: Record<string, unknown>) => {
          const code = (item.fieldCode || item.field_code) as string;
          const value = item.fieldValue || item.field_value;
          if (code) {
            acc[code] = value;
          }
          return acc;
        }, {});
      } else {
        algorithmParams.value = params;
      }
    }

    if (rawFormDataForCopy.reference_params || rawFormDataForCopy.referenceParams) {
      const params = rawFormDataForCopy.reference_params || rawFormDataForCopy.referenceParams || [];
      if (Array.isArray(params)) {
        referenceParams.value = params.reduce((acc: Record<string, unknown>, item: Record<string, unknown>) => {
          const code = (item.fieldCode || item.field_code) as string;
          const value = item.fieldValue || item.field_value;
          if (code) {
            acc[code] = value;
          }
          return acc;
        }, {});
      } else {
        referenceParams.value = params;
      }
    }

    return rawFormDataForCopy as LocalFormData;
  }

  async function loadTestGroups() {
    try {
      const groupsRes = await testcasesApi.getGroups();
      const groups = groupsRes?.items || [];
      testCaseGroups.value = Array.isArray(groups) ? groups.map((group: TestCaseGroupItem) => {
        return group.name || group.group || group.id || String(group);
      }).filter(Boolean) : [];
    } catch (err) {
      console.error('加载测试用例组失败:', err);
      testCaseGroups.value = [];
    }
  }

  async function loadAvailableTags() {
    try {
      const tags = await testcasesApi.getTags();
      let parsedTags: string[] = [];
      if (Array.isArray(tags)) {
        parsedTags = tags;
      } else if (tags && typeof tags === 'object') {
        if ((tags as Record<string, unknown>).data && Array.isArray((tags as Record<string, unknown>).data)) {
          parsedTags = (tags as { data: string[] }).data;
        } else if ((tags as Record<string, unknown>).items && Array.isArray((tags as Record<string, unknown>).items)) {
          parsedTags = (tags as { items: string[] }).items;
        }
      }
      availableTags.value = parsedTags;
    } catch (error) {
      console.error('加载标签列表失败:', error);
      availableTags.value = [];
    }
  }

  async function loadAlgorithmOptions() {
    try {
      const options = await getAlgorithmOptions();
      algorithmOptions.value = (options || []).map((opt: Record<string, unknown>) => ({
        value: opt.value as string,
        name: (opt.name || opt.label || opt.value) as string
      }));
    } catch (error) {
      console.error('加载算法选项失败:', error);
      algorithmOptions.value = fallbackOptions.value.length > 0
        ? fallbackOptions.value.map((opt: Record<string, unknown>) => ({ value: opt.value as string, name: opt.label as string }))
        : [
          { value: 'translation', name: '翻译' },
          { value: 'asr', name: 'ASR识别' },
          { value: 'speaker_recognition', name: '说话人识别' },
          { value: 'tts', name: '语音合成' },
          { value: 'asr_eval', name: 'ASR评估' }
        ];
    }
  }

  async function loadAlgorithmFormSchema(algorithmType: string) {
    if (!algorithmType) {
      algorithmParams.value = {};
      associatedDimensions.value = [];
      return;
    }

    const savedParams = { ...algorithmParams.value };

    try {
      const schema = await getFormSchema(algorithmType);
      algorithmParams.value = savedParams;

      if (schema?.fields) {
        const newParams: Record<string, unknown> = {};
        schema.fields.forEach((field: Record<string, unknown>) => {
          const fieldCode = field.fieldCode as string;
          if (savedParams[fieldCode] !== undefined) {
            newParams[fieldCode] = savedParams[fieldCode];
          } else if (field.defaultValue !== undefined) {
            newParams[fieldCode] = field.defaultValue;
          }
        });

        for (const [key, value] of Object.entries(savedParams)) {
          if (newParams[key] === undefined) {
            newParams[key] = value;
          }
        }
        algorithmParams.value = newParams;
      }

      const dimResult = await getAssociatedDimensions(algorithmType);
      if (dimResult && dimResult.dimensions) {
        associatedDimensions.value = dimResult.dimensions;

        const defaultDim = dimResult.dimensions.find((d: Record<string, unknown>) => d.is_default);
        if (defaultDim) {
          const existingApiDim = localFormData.value.config.dimensions.api.find(
            (d: Record<string, unknown>) => d.id === defaultDim.id || d.name === defaultDim.name
          );
          if (!existingApiDim) {
            localFormData.value.config.dimensions.api.push({
              id: defaultDim.id as number,
              name: defaultDim.name as string,
              weight: (defaultDim.weight as number) || 50,
              threshold: 80
            });
          }
        }
      } else {
        associatedDimensions.value = [];
      }
    } catch (error) {
      console.error('加载算法表单Schema失败:', error);
      associatedDimensions.value = [];
    }
  }

  async function loadDimensions(algorithmType?: string) {
    try {
      let dimensions;
      if (algorithmType) {
        dimensions = await fetchDimensionsByAlgorithmType(algorithmType);
      } else {
        dimensions = await fetchAllDimensions({ forceRefresh: true });
      }
      const uniqueDimensions: Dimension[] = [];
      const dimensionNames = new Set<string>();
      for (const dim of dimensions as Dimension[]) {
        if (!dimensionNames.has(dim.name)) {
          dimensionNames.add(dim.name);
          uniqueDimensions.push(dim);
        }
      }
      availableDimensions.value = uniqueDimensions;
    } catch (err) {
      console.error('加载评测维度失败:', err);
      availableDimensions.value = [];
    }
  }

  async function loadResources() {
    try {
      const [devicesRes, allAudiosRes] = await Promise.all([
        playbackApi.getAll({ perPage: 1000 }),
        audiosApi.getAll({ perPage: 1000 })
      ]);

      playbackDevices.value = Array.isArray(devicesRes?.items) ? devicesRes.items as PlaybackDevice[] : [];
      const audios: AudioItem[] = Array.isArray(allAudiosRes?.items) ? allAudiosRes.items : [];

      dryAudios.value = audios.filter((a: AudioItem) => a.audioType === 'dry');
      noiseAudios.value = audios.filter((a: AudioItem) => a.audioType === 'noise');
    } catch (err) {
      console.error('加载资源失败:', err);
    }
  }

  const hasAPIAudio = computed(() => {
    if (!localFormData.value.config?.audios) return false;
    return localFormData.value.config.audios.some((audio: Record<string, unknown>) => audio.testType === 'api');
  });

  const hasE2eAudio = computed(() => {
    if (!localFormData.value.config?.audios) return false;
    return localFormData.value.config.audios.some((audio: Record<string, unknown>) => audio.testType === 'e2e');
  });

  function selectTag(tag: string) {
    if (!localFormData.value.tags) {
      localFormData.value.tags = [];
    }
    if (!localFormData.value.tags.includes(tag)) {
      localFormData.value.tags.push(tag);
    }
    tagsInput.value = '';
  }

  function addTags() {
    if (!localFormData.value.tags) {
      localFormData.value.tags = [];
    }

    const tags = tagsInput.value
      .split(/[，,]/)
      .map(tag => tag.trim())
      .filter(tag => tag && !localFormData.value.tags?.includes(tag));

    localFormData.value.tags = [...(localFormData.value.tags || []), ...tags];
    tagsInput.value = '';
  }

  function removeTag(index: number) {
    localFormData.value.tags?.splice(index, 1);
  }

  function autoGenerateName() {
    const tags = localFormData.value.tags;
    if (tags && tags.length > 0) {
      const filteredTags = tags.filter((tag: string) => tag.length <= 25);
      const sortedTags = filteredTags.sort((a: string, b: string) => a.length - b.length);
      localFormData.value.name = sortedTags.join('-');
    }
  }

  function handleAlgorithmParamsChange(params: Record<string, unknown>) {
    algorithmParams.value = params;
  }

  function handleAlgorithmTypeChange() {
    loadAlgorithmFormSchema(localFormData.value.algorithmType || '');
  }

  function addAudioConfig() {
    if (!localFormData.value.config.audios) {
      localFormData.value.config.audios = [];
    }
    localFormData.value.config.audios.push({
      audioId: '',
      testType: 'api',
      playbackDeviceId: '',
      spl: 65,
      playOrder: localFormData.value.config.audios.length
    });
  }

  function removeAudioConfig(index: number) {
    if (localFormData.value.config.audios && localFormData.value.config.audios.length > 0) {
      localFormData.value.config.audios.splice(index, 1);
      localFormData.value.config.audios.forEach((audio: Record<string, unknown>, i: number) => {
        audio.playOrder = i;
      });
    }
  }

  function copyAudioConfig(index: number) {
    const source = localFormData.value.config.audios[index];
    if (source) {
      const copy = JSON.parse(JSON.stringify(source));
      copy.audioId = '';
      copy.playOrder = localFormData.value.config.audios.length;
      localFormData.value.config.audios.push(copy);
    }
  }

  function clearAllAudioConfigs() {
    localFormData.value.config.audios = [];
  }

  function sortByFileName(order: 'asc' | 'desc') {
    const sorted = [...localFormData.value.config.audios].sort((a, b) => {
      const nameA = getAudioName(a.audioId).toLowerCase();
      const nameB = getAudioName(b.audioId).toLowerCase();
      if (order === 'asc') {
        return nameA.localeCompare(nameB);
      } else {
        return nameB.localeCompare(nameA);
      }
    });
    sorted.forEach((audio: Record<string, unknown>, i: number) => {
      audio.playOrder = i;
    });
    localFormData.value.config.audios = sorted;
  }

  function shuffleAudioConfigs() {
    const shuffled = [...localFormData.value.config.audios];
    for (let i = shuffled.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
    }
    shuffled.forEach((audio: Record<string, unknown>, i: number) => {
      audio.playOrder = i;
    });
    localFormData.value.config.audios = shuffled;
  }

  function getAudioName(audioId: string | number): string {
    const allAudios = [...dryAudios.value, ...noiseAudios.value];
    const audio = allAudios.find(a => String(a.id) === String(audioId));
    return audio ? audio.name : '未知音频';
  }

  function getAudioTags(audioId: string | number): string {
    const allAudios = [...dryAudios.value, ...noiseAudios.value];
    const audio = allAudios.find(a => String(a.id) === String(audioId));
    if (audio && audio.tags) {
      if (Array.isArray(audio.tags)) {
        return audio.tags.join(', ');
      }
      return String(audio.tags);
    }
    return '';
  }

  function getDeviceName(deviceId: string | number): string {
    const device = playbackDevices.value.find(d => String(d.id) === String(deviceId));
    if (device) {
      return `${device.name} (通道 ${device.channelIndex})`;
    }
    const deviceIdStr = String(deviceId);
    const scanDeviceMatch = deviceIdStr.match(/^(.*)-(\d+)$/);
    if (scanDeviceMatch) {
      return `${scanDeviceMatch[1]} (通道 ${scanDeviceMatch[2]}) [扫描]`;
    }
    return '未知设备';
  }

  function getNoiseDeviceNames(): string {
    const deviceIds = localFormData.value.config.backgroundNoise.deviceIds || [];
    if (deviceIds.length === 0) return '';
    const names = deviceIds.map(id => getDeviceName(id));
    return names.join(', ');
  }

  function clearNoiseConfig() {
    localFormData.value.config.backgroundNoise.audioId = '';
    localFormData.value.config.backgroundNoise.deviceIds = [];
    localFormData.value.config.backgroundNoise.spl = 0;
  }

  function toggleDimensionSelection(dimension: Dimension, dimensionType: 'api' | 'e2e') {
    const dimensions = localFormData.value.config.dimensions[dimensionType];
    const index = dimensions.findIndex((dim: Record<string, unknown>) => dim.name === dimension.name);

    if (index > -1) {
      dimensions.splice(index, 1);
    } else {
      dimensions.push({
        id: dimension.id,
        name: dimension.name,
        weight: 50,
        threshold: 80
      });
    }
  }

  function addAPIDimension() {
    if (!localFormData.value.config.dimensions.api) {
      localFormData.value.config.dimensions.api = [];
    }
    localFormData.value.config.dimensions.api.push({ name: '', weight: 0, threshold: 0 });
  }

  function removeAPIDimension(index: number) {
    if (localFormData.value.config.dimensions?.api && localFormData.value.config.dimensions.api.length > 1) {
      localFormData.value.config.dimensions.api.splice(index, 1);
    }
  }

  function addE2EDimension() {
    if (!localFormData.value.config.dimensions.e2e) {
      localFormData.value.config.dimensions.e2e = [];
    }
    localFormData.value.config.dimensions.e2e.push({ name: '', weight: 0, threshold: 0 });
  }

  function removeE2EDimension(index: number) {
    if (localFormData.value.config.dimensions?.e2e && localFormData.value.config.dimensions.e2e.length > 1) {
      localFormData.value.config.dimensions.e2e.splice(index, 1);
    }
  }

  function syncAudioTagsToCase() {
    if (!localFormData.value.tags) {
      localFormData.value.tags = [];
    }

    const allTags = new Set<string>();
    const allAudios = [...dryAudios.value, ...noiseAudios.value];

    if (localFormData.value.config.audios) {
      localFormData.value.config.audios.forEach((audioConfig: Record<string, unknown>) => {
        if (audioConfig.audioId) {
          const audio = allAudios.find(a => String(a.id) === String(audioConfig.audioId));
          if (audio && audio.tags) {
            const tags = Array.isArray(audio.tags) ? audio.tags : String(audio.tags).split(',');
            tags.forEach((tag: string) => {
              const trimmedTag = tag.trim();
              if (trimmedTag) {
                allTags.add(trimmedTag);
              }
            });
          }
        }
      });
    }

    if (localFormData.value.config.backgroundNoise?.audioId) {
      const noiseAudio = allAudios.find(a => String(a.id) === String(localFormData.value.config.backgroundNoise.audioId));
      if (noiseAudio && noiseAudio.tags) {
        const tags = Array.isArray(noiseAudio.tags) ? noiseAudio.tags : String(noiseAudio.tags).split(',');
        tags.forEach((tag: string) => {
          const trimmedTag = tag.trim();
          if (trimmedTag) {
            allTags.add(trimmedTag);
          }
        });
      }
    }

    allTags.forEach((tag: string) => {
      if (!localFormData.value.tags?.includes(tag)) {
        localFormData.value.tags.push(tag);
      }
    });
  }

  function validateForm(): boolean {
    const data = localFormData.value;

    if (options.mode === 'group') {
      if (!data.name || data.name.trim() === '') {
        alert('请输入测试用例组名称');
        return false;
      }
      return true;
    } else if (options.mode === 'case') {
      if (!data.name || data.name.trim() === '') {
        alert('请输入测试用例名称');
        return false;
      }

      if (!data.group || data.group.trim() === '') {
        alert('请选择所属分组');
        return false;
      }

      if (data.group === 'new-group' && (!newGroupName.value || newGroupName.value.trim() === '')) {
        alert('请输入新分组名称');
        return false;
      }

      if (!data.config || !data.config.audios || data.config.audios.length === 0) {
        alert('请添加至少一个音频配置');
        return false;
      }

      for (let i = 0; i < data.config.audios.length; i++) {
        const audio = data.config.audios[i];
        if (!audio.audioId) {
          alert(`请选择音频配置 ${i + 1} 的音频文件`);
          return false;
        }

        if (!audio.testType) {
          alert(`请选择音频配置 ${i + 1} 的测试类型`);
          return false;
        }

        if (audio.testType === 'e2e') {
          if (!audio.playbackDeviceId) {
            alert(`请选择音频配置 ${i + 1} 的播放设备`);
            return false;
          }

          if (!audio.spl || (audio.spl as number) < 0 || (audio.spl as number) > 120) {
            alert(`请输入音频配置 ${i + 1} 的有效声压级`);
            return false;
          }
        }

        if (audio.playOrder === undefined || (audio.playOrder as number) < 0) {
          alert(`请输入音频配置 ${i + 1} 的有效播放顺序`);
          return false;
        }
      }

      if (data.config.dimensions?.api) {
        for (let i = 0; i < data.config.dimensions.api.length; i++) {
          const dim = data.config.dimensions.api[i];
          if (!dim.name || dim.name.trim() === '') {
            alert(`请输入 API 评测维度 ${i + 1} 的名称`);
            return false;
          }

          if (dim.weight === undefined || dim.weight < 0 || dim.weight > 100) {
            alert(`请输入 API 评测维度 ${i + 1} 的有效权重`);
            return false;
          }

          if (dim.threshold === undefined || dim.threshold < 0 || dim.threshold > 100) {
            alert(`请输入 API 评测维度 ${i + 1} 的有效阈值`);
            return false;
          }
        }
      }

      if (data.config.dimensions?.e2e) {
        for (let i = 0; i < data.config.dimensions.e2e.length; i++) {
          const dim = data.config.dimensions.e2e[i];
          if (!dim.name || dim.name.trim() === '') {
            alert(`请输入端到端评测维度 ${i + 1} 的名称`);
            return false;
          }

          if (dim.weight === undefined || dim.weight < 0 || dim.weight > 100) {
            alert(`请输入端到端评测维度 ${i + 1} 的有效权重`);
            return false;
          }

          if (dim.threshold === undefined || dim.threshold < 0 || dim.threshold > 100) {
            alert(`请输入端到端评测维度 ${i + 1} 的有效阈值`);
            return false;
          }
        }
      }

      return true;
    }

    return true;
  }

  function getSaveData(): Record<string, unknown> {
    if (tagsInput.value && tagsInput.value.trim()) {
      addTags();
    }

    if (!validateForm()) {
      throw new Error('Form validation failed');
    }

    const saveData = Object.assign({}, localFormData.value);

    const keysToDelete = ['algorithm_params', 'algorithmParams', 'reference_params', 'referenceParams'];
    keysToDelete.forEach(key => {
      delete saveData[key];
    });

    if (saveData.groupId) {
      saveData.group_id = saveData.groupId;
    }

    if (localFormData.value.algorithmType && Object.keys(algorithmParams.value).length > 0) {
      saveData.algorithm_params = Object.entries(algorithmParams.value).map(([fieldCode, fieldValue]) => ({
        fieldCode,
        fieldValue
      }));
    }

    if (localFormData.value.algorithmType && Object.keys(referenceParams.value).length > 0) {
      saveData.reference_params = Object.entries(referenceParams.value).map(([fieldCode, fieldValue]) => ({
        fieldCode,
        fieldValue
      }));
    }

    if (localFormData.value.algorithmType) {
      saveData.algorithm_type = localFormData.value.algorithmType;
    }

    if (options.mode === 'case' && saveData.group === 'new-group' && newGroupName.value) {
      saveData.group = newGroupName.value;
    }

    if (options.mode === 'case') {
      const originalGroup = localFormData.value._originalGroup || '';
      if (saveData.group === 'new-group' || (saveData.group && saveData.group !== originalGroup)) {
        delete saveData.groupId;
        delete saveData.group_id;
      }
    }

    return saveData;
  }

  return {
    isDraftRestored,
    isInitializing,
    isEditMode,
    draftId,
    localFormData,
    algorithmOptions,
    algorithmParams,
    referenceParams,
    associatedDimensions,
    testCaseGroups,
    tagsInput,
    newGroupName,
    availableTags,
    showAllTags,
    playbackDevices,
    dryAudios,
    noiseAudios,
    availableDimensions,
    hasAPIAudio,
    hasE2eAudio,
    performInitialization,
    loadResources,
    loadAlgorithmFormSchema,
    loadDimensions,
    selectTag,
    addTags,
    removeTag,
    autoGenerateName,
    handleAlgorithmParamsChange,
    handleAlgorithmTypeChange,
    addAudioConfig,
    removeAudioConfig,
    copyAudioConfig,
    clearAllAudioConfigs,
    sortByFileName,
    shuffleAudioConfigs,
    getAudioName,
    getAudioTags,
    getDeviceName,
    getNoiseDeviceNames,
    clearNoiseConfig,
    toggleDimensionSelection,
    addAPIDimension,
    removeAPIDimension,
    addE2EDimension,
    removeE2EDimension,
    syncAudioTagsToCase,
    validateForm,
    getSaveData
  };
}
