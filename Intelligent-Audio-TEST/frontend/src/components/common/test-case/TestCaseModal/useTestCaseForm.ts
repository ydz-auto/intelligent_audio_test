import { ref, computed, watch } from 'vue';
import { useModalStore } from '../../../../store/modalStore';
import { testcasesApi } from '../../../../utils/api';
import { normalizeTestCaseConfig } from '../../../../utils/utils';
import type { TestCaseFormData, GroupFormData, TestCaseGroupItem, AudioConfig, DimensionConfig } from './types';

export function useTestCaseForm(
  props: {
    visible: boolean;
    mode: string;
    formData: Record<string, any>;
  },
  emit: (event: 'close' | 'save', ...args: any[]) => void
) {
  const modalStore = useModalStore();
  const isDraftRestored = ref(false);
  const isInitializing = ref(false);

  const draftId = computed(() => {
    if (props.formData?.id) return null;
    if (props.mode === 'case') return 'addTestCase';
    if (props.mode === 'group') return 'addTestGroup';
    return null;
  });

  const isEditMode = computed(() => {
    if (props.mode === 'group') {
      return !!props.formData.name;
    } else if (props.mode === 'case') {
      return !!props.formData.id;
    }
    return false;
  });

  const testCaseGroups = ref<string[]>([]);
  const availableTags = ref<string[]>([]);
  const tagsInput = ref('');
  const newGroupName = ref('');
  const showAllTags = ref(false);

  const localFormData = ref<TestCaseFormData>(createInitialFormData());

  function createInitialFormData(): TestCaseFormData {
    return {
      id: undefined,
      name: '',
      description: '',
      group: '',
      tags: [],
      algorithmType: '',
      config: {
        audios: [],
        dimensions: { api: [], e2e: [] },
        backgroundNoise: { audioId: '', deviceIds: [], spl: 0 }
      }
    };
  }

  function initFormData(): TestCaseFormData {
    const rawFormData = props.formData ?? {};
    let initialAlgorithmType = '';
    if (rawFormData.algorithmType !== undefined && rawFormData.algorithmType !== '') {
      initialAlgorithmType = rawFormData.algorithmType;
    }

    if (!isEditMode.value && draftId.value) {
      const draft = modalStore.getDraft(draftId.value);
      if (draft) {
        const formDataCopy = JSON.parse(JSON.stringify(rawFormData));
        const mergedData = { ...draft };
        for (const key of Object.keys(formDataCopy)) {
          const value = formDataCopy[key];
          if (value !== '' && value !== null && value !== undefined) {
            if (typeof value === 'object' && Object.keys(value).length > 0) {
              mergedData[key] = value;
            } else if (typeof value !== 'object') {
              mergedData[key] = value;
            }
          }
        }
        modalStore.clearDraft(draftId.value);
        isDraftRestored.value = true;
        return mergedData;
      }
    }

    isDraftRestored.value = false;
    const formDataCopy = JSON.parse(JSON.stringify(rawFormData));

    if (!formDataCopy.config) {
      formDataCopy.config = {};
    }

    const normalizedConfig = normalizeTestCaseConfig(formDataCopy.config);
    delete normalizedConfig.apiAudios;
    delete normalizedConfig.dryAudios;
    formDataCopy.config = normalizedConfig;

    if (!Array.isArray(formDataCopy.config.audios) || formDataCopy.config.audios.length === 0) {
      formDataCopy.config.audios = [
        { audioId: '', testType: 'api', playbackDeviceId: '', spl: 65, playOrder: 0 }
      ];
    }

    if (!formDataCopy.config.dimensions || Array.isArray(formDataCopy.config.dimensions)) {
      formDataCopy.config.dimensions = { api: [], e2e: [] };
    } else {
      formDataCopy.config.dimensions.api = formDataCopy.config.dimensions.api || [];
      formDataCopy.config.dimensions.e2e = formDataCopy.config.dimensions.e2e || [];
    }

    if (!formDataCopy.config.backgroundNoise) {
      formDataCopy.config.backgroundNoise = { audioId: '', deviceIds: [], spl: 0 };
    } else {
      formDataCopy.config.backgroundNoise.audioId = formDataCopy.config.backgroundNoise.audioId ?? '';
      formDataCopy.config.backgroundNoise.deviceIds = Array.isArray(formDataCopy.config.backgroundNoise.deviceIds)
        ? formDataCopy.config.backgroundNoise.deviceIds
        : formDataCopy.config.backgroundNoise.deviceId
          ? [formDataCopy.config.backgroundNoise.deviceId]
          : [];
      formDataCopy.config.backgroundNoise.spl = formDataCopy.config.backgroundNoise.spl ?? 0;
    }

    if (!formDataCopy.tags) {
      formDataCopy.tags = [];
    }

    if (formDataCopy.group === undefined || formDataCopy.group === '') {
      formDataCopy.group = formDataCopy.groupName || formDataCopy.group_name || '';
    }

    delete formDataCopy.algorithm_params;
    delete formDataCopy.reference_params;

    formDataCopy._originalGroup = formDataCopy.group;
    formDataCopy._originalGroupId = formDataCopy.groupId || formDataCopy.group_id || '';

    if (!formDataCopy.algorithmType) {
      formDataCopy.algorithmType = formDataCopy.algorithm_type || initialAlgorithmType || '';
    }

    return formDataCopy;
  }

  async function loadTestGroups() {
    try {
      const groupsRes = await testcasesApi.getGroups();
      const groups = groupsRes?.items || [];
      testCaseGroups.value = Array.isArray(groups)
        ? groups.map((group: TestCaseGroupItem) => {
            return group.name || group.group || group.id || String(group);
          }).filter(Boolean)
        : [];
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
        if ((tags as any).data && Array.isArray((tags as any).data)) {
          parsedTags = (tags as any).data;
        } else if ((tags as any).items && Array.isArray((tags as any).items)) {
          parsedTags = (tags as any).items;
        }
      }
      availableTags.value = parsedTags;
    } catch (error) {
      console.error('加载标签列表失败:', error);
      availableTags.value = [];
    }
  }

  const filteredAvailableTags = computed(() => {
    const tags = availableTags.value;
    if (!Array.isArray(tags)) return [];
    return tags.filter(tag => !(localFormData.value.tags || []).includes(tag));
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
      .filter(tag => tag && !localFormData.value.tags.includes(tag));
    localFormData.value.tags = [...localFormData.value.tags, ...tags];
    tagsInput.value = '';
  }

  function removeTag(index: number) {
    (localFormData.value.tags || []).splice(index, 1);
  }

  function autoGenerateName() {
    const tags = localFormData.value.tags;
    if (tags && tags.length > 0) {
      const filteredTags = tags.filter((tag: string) => tag.length <= 25);
      const sortedTags = filteredTags.sort((a: string, b: string) => a.length - b.length);
      localFormData.value.name = sortedTags.join('-');
    }
  }

  function validateForm(): boolean {
    const data = localFormData.value;

    if (props.mode === 'group') {
      if (!data.name || data.name.trim() === '') {
        alert('请输入测试用例组名称');
        return false;
      }
      return true;
    }

    if (props.mode === 'case') {
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
          if (!audio.spl || audio.spl < 0 || audio.spl > 120) {
            alert(`请输入音频配置 ${i + 1} 的有效声压级`);
            return false;
          }
        }
        if (audio.playOrder === undefined || audio.playOrder < 0) {
          alert(`请输入音频配置 ${i + 1} 的有效播放顺序`);
          return false;
        }
      }

      if (data.config.dimensions.api) {
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

      if (data.config.dimensions.e2e) {
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
    }

    return true;
  }

  function handleSave(algorithmParams: Record<string, any>, referenceParams: Record<string, any>) {
    if (tagsInput.value && tagsInput.value.trim()) {
      addTags();
    }

    if (!validateForm()) {
      return;
    }

    const saveData = Object.assign({}, localFormData.value);

    const keysToDelete = ['algorithm_params', 'algorithmParams', 'reference_params', 'referenceParams'];
    keysToDelete.forEach(key => delete saveData[key]);

    if (saveData.groupId) {
      saveData.group_id = saveData.groupId;
    }

    if (localFormData.value.algorithmType && Object.keys(algorithmParams).length > 0) {
      saveData.algorithm_params = Object.entries(algorithmParams).map(([fieldCode, fieldValue]) => ({
        fieldCode,
        fieldValue
      }));
    }

    if (localFormData.value.algorithmType && Object.keys(referenceParams).length > 0) {
      saveData.reference_params = Object.entries(referenceParams).map(([fieldCode, fieldValue]) => ({
        fieldCode,
        fieldValue
      }));
    }

    if (localFormData.value.algorithmType) {
      saveData.algorithm_type = localFormData.value.algorithmType;
    }

    if (props.mode === 'case' && saveData.group === 'new-group' && newGroupName.value) {
      saveData.group = newGroupName.value;
    }

    if (props.mode === 'case') {
      const originalGroup = localFormData.value._originalGroup || '';
      if (saveData.group === 'new-group' || (saveData.group && saveData.group !== originalGroup)) {
        delete saveData.groupId;
        delete saveData.group_id;
      }
    }

    emit('save', {
      mode: props.mode,
      isEdit: isEditMode.value,
      id: localFormData.value.id,
      data: saveData
    });
  }

  watch(() => localFormData.value, (newValues) => {
    if (isInitializing.value) return;
    if (!isEditMode.value && draftId.value && newValues && Object.keys(newValues).length > 0) {
      modalStore.setDraft(draftId.value, newValues);
    }
  }, { deep: true });

  watch(() => tagsInput.value, (newValue) => {
    if (newValue.endsWith(',') || newValue.endsWith('，')) {
      addTags();
    }
  });

  watch(() => localFormData.value.group, (newValue) => {
    if (newValue !== 'new-group') {
      newGroupName.value = '';
    }
  });

  return {
    localFormData,
    isEditMode,
    isInitializing,
    isDraftRestored,
    testCaseGroups,
    availableTags,
    filteredAvailableTags,
    tagsInput,
    newGroupName,
    showAllTags,
    draftId,
    initFormData,
    loadTestGroups,
    loadAvailableTags,
    selectTag,
    addTags,
    removeTag,
    autoGenerateName,
    validateForm,
    handleSave
  };
}

export function useGroupForm(
  props: {
    visible: boolean;
    mode: string;
    formData: Record<string, any>;
  },
  emit: (event: 'close' | 'save', ...args: any[]) => void
) {
  const localFormData = ref<GroupFormData>({
    name: '',
    description: '',
    algorithmType: ''
  });

  const isEditMode = computed(() => !!props.formData.name);

  function initFormData(): GroupFormData {
    return {
      name: props.formData.name || '',
      description: props.formData.description || '',
      algorithmType: props.formData.algorithmType || props.formData.algorithm_type || ''
    };
  }

  function validateForm(): boolean {
    if (!localFormData.value.name || localFormData.value.name.trim() === '') {
      alert('请输入测试用例组名称');
      return false;
    }
    return true;
  }

  function handleSave() {
    if (!validateForm()) return;
    emit('save', {
      mode: 'group',
      isEdit: isEditMode.value,
      data: { ...localFormData.value }
    });
  }

  return {
    localFormData,
    isEditMode,
    initFormData,
    validateForm,
    handleSave
  };
}
