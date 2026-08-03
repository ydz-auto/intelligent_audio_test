import { ref, computed, watch, provide } from 'vue';
import { testcasesApi } from '../../../../utils/api';
import { useNotification } from '../../../../composables/modal/useNotification';
import { useAudioConfig } from './useAudioConfig';
import { useDimensionConfig } from './useDimensionConfig';
import type { TestCaseFormData, GroupFormData, ExportFormData, AudioItem } from './types';

export function useTestCaseModal(props: any, emit: any) {
  const notification = useNotification();

  const audioConfig = useAudioConfig();
  const dimensionConfig = useDimensionConfig();

  provide('audioConfig', audioConfig);
  provide('dimensionConfig', dimensionConfig);
  provide('playbackDevices', audioConfig.playbackDevices);
  provide('availableDimensions', dimensionConfig.availableDimensions);

  const testCaseGroups = ref<string[]>([]);
  const caseFormData = ref<Partial<TestCaseFormData>>({});
  const groupFormData = ref<GroupFormData>({ name: '', description: '', algorithmType: '' });
  const caseFormRef = ref<any>(null);
  const importFormRef = ref<any>(null);
  const exportFormRef = ref<any>(null);
  const pendingAudioCallback = ref<((audios: { id: string; name?: string }[]) => void) | null>(null);

  const isEditMode = computed(() => {
    if (props.mode === 'group') {
      return !!props.formData.name;
    } else if (props.mode === 'case') {
      return !!props.formData.id;
    }
    return false;
  });

  const isSubmitDisabled = computed(() => {
    if (props.mode === 'export') {
      return !exportFormRef.value?.localFormData?.groups?.length;
    }
    return false;
  });

  function getModalTitle() {
    if (props.title) return props.title;
    switch (props.mode) {
      case 'case':
        return isEditMode.value ? '编辑测试用例' : '新增测试用例';
      case 'group':
        return isEditMode.value ? '编辑测试用例组' : '创建测试用例组';
      case 'import':
        return '批量导入测试用例';
      case 'export':
        return '批量导出测试用例';
      default:
        return '测试用例管理';
    }
  }

  function getSubmitButtonText() {
    switch (props.mode) {
      case 'import':
        return '导入';
      case 'export':
        return '导出';
      default:
        return '保存';
    }
  }

  async function loadTestGroups() {
    try {
      const groupsRes = await testcasesApi.getGroups();
      const groups = groupsRes?.items || [];
      testCaseGroups.value = Array.isArray(groups)
        ? groups.map((group: any) => group.name || group.group || group.id || String(group)).filter(Boolean)
        : [];
    } catch (err) {
      console.error('加载测试用例组失败:', err);
      testCaseGroups.value = [];
    }
  }

  function handleGroupUpdate(data: GroupFormData) {
    groupFormData.value = data;
  }

  function handleCaseUpdate(data: TestCaseFormData) {
    caseFormData.value = data;
  }

  function handleImportUpdate(data: { file: File | null }) {
    console.log('Import update:', data);
  }

  function handleExportUpdate(data: ExportFormData & { ids: (string | number)[] }) {
    console.log('Export update:', data);
  }

  function openAudioSelectModal(audioType: 'dry' | 'noise', index?: number, callback?: (audios: { id: string; name?: string }[]) => void) {
    audioConfig.currentAudioType.value = audioType;
    audioConfig.currentAudioIndex.value = index ?? null;
    pendingAudioCallback.value = callback || null;
    audioConfig.showAudioModal.value = true;
  }

  function openDeviceSelectModal(audioIndex: number) {
    audioConfig.currentDeviceAudioIndex.value = audioIndex;
    const audios = getCurrentRoundAudios();
    const audio = audios[audioIndex];
    audioConfig.initialSelectedDevices.value = audio?.playbackDeviceId ? [audio.playbackDeviceId] : [];
    audioConfig.showDeviceModal.value = true;
  }

  function openNoiseDeviceSelectModal() {
    audioConfig.noiseInitialSelectedDevices.value = caseFormData.value.config?.backgroundNoise?.deviceIds || [];
    audioConfig.showNoiseDeviceModal.value = true;
  }

  function getCurrentRoundAudios(): any[] {
    // Prefer CaseForm's local data
    if (caseFormRef.value?.getCurrentRoundAudiosLocal) {
      return caseFormRef.value.getCurrentRoundAudiosLocal();
    }
    const config = caseFormData.value.config;
    if (!config) return [];
    if (config.rounds && config.rounds.length > 0) {
      const roundIdx = caseFormRef.value?.currentRoundIndex?.value ?? 0;
      return config.rounds[roundIdx]?.audios || [];
    }
    return config.audios || [];
  }

  function openBatchDeviceModal() {
    const audios = getCurrentRoundAudios();
    const configured = audios.filter((a: any) => a.playbackDeviceId);
    audioConfig.batchInitialSelectedDevices.value = configured.length > 0 ? [configured[0].playbackDeviceId] : [];
    audioConfig.showBatchDeviceModal.value = true;
  }

  function openBatchSplModal() {
    console.log('[openBatchSplModal] called');
    const audios = getCurrentRoundAudios();
    console.log('[openBatchSplModal] audios count:', audios.length);
    audioConfig.batchSplValue.value = audios.length > 0 ? (audios[0].spl || 65) : 65;
    console.log('[openBatchSplModal] setting showBatchSplModal to true');
    audioConfig.showBatchSplModal.value = true;
    console.log('[openBatchSplModal] showBatchSplModal.value:', audioConfig.showBatchSplModal.value);
  }

  function openCrossDeviceModal() {
    const audios = getCurrentRoundAudios();
    const deviceIds = [...new Set(audios.map((a: any) => a.playbackDeviceId).filter(Boolean))] as string[];
    audioConfig.crossDeviceInitialSelectedDevices.value = deviceIds;
    audioConfig.showCrossDeviceModal.value = true;
  }

  function handleAudioSelect(audio: AudioItem) {
    // 优先使用轮次内音频选择的 callback
    if (pendingAudioCallback.value) {
      // 将选中的音频添加到缓存
      const audioType = (audio as any).audioType || 'dry';
      const existing = audioType === 'noise' ? audioConfig.noiseAudios.value : audioConfig.dryAudios.value;
      if (!existing.find((e: AudioItem) => String(e.id) === String(audio.id))) {
        existing.push(audio as AudioItem);
      }
      pendingAudioCallback.value([{ id: String(audio.id), name: audio.name }]);
      pendingAudioCallback.value = null;
      return;
    }
    // 回退：旧版 flat config 格式
    if (caseFormData.value.config) {
      audioConfig.handleAudioSelect(audio, caseFormData.value.config.audios, caseFormData.value.config.backgroundNoise);
      caseFormRef.value?.syncConfigFromParent();
    }
  }

  function handleMultipleAudioSelect(audios: AudioItem[]) {
    // 优先使用轮次内音频选择的 callback（传递全部选中音频）
    if (pendingAudioCallback.value) {
      // 将选中的音频添加到缓存，以便 getAudioDuration/getAudioTags 能查到
      audios.forEach(a => {
        const audioType = (a as any).audioType || 'dry';
        const existing = audioType === 'noise' ? audioConfig.noiseAudios.value : audioConfig.dryAudios.value;
        if (!existing.find((e: AudioItem) => String(e.id) === String(a.id))) {
          existing.push(a as AudioItem);
        }
      });
      pendingAudioCallback.value(audios.map(a => ({ id: String(a.id), name: a.name })));
      pendingAudioCallback.value = null;
      return;
    }
    // 回退：旧版 flat config 格式
    if (caseFormData.value.config) {
      audioConfig.handleMultipleAudioSelect(audios, caseFormData.value.config.audios, caseFormData.value.config.backgroundNoise);
      caseFormRef.value?.syncConfigFromParent();
    }
  }

  function handleDeviceSelect(selectedDevices: string[]) {
    if (selectedDevices.length === 0) return;
    if (caseFormRef.value?.applySingleDevice) {
      const audioIdx = audioConfig.currentDeviceAudioIndex.value;
      if (audioIdx !== null) {
        caseFormRef.value.applySingleDevice(audioIdx, selectedDevices[0]);
      }
    } else if (caseFormData.value.config?.audios) {
      audioConfig.handleDeviceSelect(selectedDevices, caseFormData.value.config.audios);
      caseFormRef.value?.syncConfigFromParent();
    }
  }

  function handleNoiseDeviceSelect(selectedDevices: string[]) {
    if (caseFormData.value.config) {
      audioConfig.handleNoiseDeviceSelect(selectedDevices, caseFormData.value.config.backgroundNoise);
      caseFormRef.value?.syncConfigFromParent();
    }
  }

  function handleBatchDeviceSelect(selectedDevices: string[]) {
    if (selectedDevices.length === 0) return;
    if (caseFormRef.value?.applyBatchDevice) {
      caseFormRef.value.applyBatchDevice(selectedDevices[0]);
    } else if (caseFormData.value.config?.audios) {
      audioConfig.handleBatchDeviceSelect(selectedDevices, caseFormData.value.config.audios);
      caseFormRef.value?.syncConfigFromParent();
    }
  }

  function handleCrossDeviceSelect(selectedDevices: string[]) {
    if (selectedDevices.length === 0) return;
    if (caseFormRef.value?.applyCrossDevice) {
      caseFormRef.value.applyCrossDevice(selectedDevices);
    } else if (caseFormData.value.config?.audios) {
      audioConfig.handleCrossDeviceSelect(selectedDevices, caseFormData.value.config.audios);
      caseFormRef.value?.syncConfigFromParent();
    }
  }

  function handleBatchSplConfirm(spl: number) {
    console.log('[handleBatchSplConfirm] called with spl:', spl);
    console.log('[handleBatchSplConfirm] caseFormRef:', caseFormRef.value);
    console.log('[handleBatchSplConfirm] applyBatchSpl exists:', !!caseFormRef.value?.applyBatchSpl);

    if (caseFormRef.value?.applyBatchSpl) {
      console.log('[handleBatchSplConfirm] calling applyBatchSpl');
      caseFormRef.value.applyBatchSpl(spl);
    } else if (caseFormData.value.config?.audios) {
      console.log('[handleBatchSplConfirm] fallback to legacy mode');
      caseFormData.value.config.audios.forEach((audio: any) => {
        if (audio.testType === 'e2e') {
          audio.spl = spl;
        }
      });
      caseFormRef.value?.syncConfigFromParent();
    }
  }

  function handlePreviewAudio(audioId: string, audioType: 'dry' | 'noise') {
    audioConfig.currentPreviewAudioId.value = audioId;
    audioConfig.currentPreviewAudioType.value = audioType;

    // 从 rounds 架构中查找音频对应的设备和声压级
    const rounds = caseFormData.value.config?.rounds || [];
    for (const round of rounds) {
      if (audioType === 'dry') {
        const audio = (round.audios || []).find(a => a.audioId === audioId);
        if (audio) {
          audioConfig.currentPreviewDeviceId.value = audio.playbackDeviceId || null;
          audioConfig.currentPreviewSpl.value = audio.spl || 65;
          break;
        }
      } else if (audioType === 'noise') {
        const noise = round.backgroundNoise;
        if (noise && noise.audioId === audioId) {
          const deviceIds = noise.deviceIds || [];
          audioConfig.currentPreviewDeviceId.value = deviceIds.length > 0 ? deviceIds[0] : null;
          audioConfig.currentPreviewSpl.value = noise.spl || 65;
          break;
        }
      }
    }

    audioConfig.currentPreviewOffset.value = 0;
    audioConfig.showAudioPreviewModal.value = true;
  }

  async function handleAudioPreview(previewData: {
    audioId: string;
    playbackDeviceId?: string;
    noisePlaybackDeviceIds?: string[];
    playbackMode?: string;
    spl?: number;
    offset?: number;
  }) {
    try {
      const { getModalManager } = await import('../../../../utils/modalManager');
      const { MODAL_TYPES } = await import('../../../../shared/types');

      const modalManager = getModalManager();
      modalManager.open(MODAL_TYPES.AUDIO_PLAYER, {
        visible: true,
        title: '音频播放',
        audioId: previewData.audioId,
        audioType: audioConfig.currentPreviewAudioType.value,
        isTestCasePreview: false,
        playbackDevices: audioConfig.playbackDevices.value,
        selectedPlaybackDevices: previewData.playbackDeviceId ? [previewData.playbackDeviceId] : previewData.noisePlaybackDeviceIds || [],
        playbackMode: previewData.playbackMode || 'frontend',
        spl: previewData.spl || 65,
        offset: previewData.offset || 0
      });
    } catch (err: unknown) {
      console.error('打开音频播放器失败:', err);
      notification.error('音频试听失败', (err as Error).message || '未知错误');
    }
  }

  function handleImportSubmit() {
    importFormRef.value?.handleSubmit();
    if (importFormRef.value?.localFile) {
      emit('save', {
        mode: 'import',
        data: { file: importFormRef.value.localFile }
      });
      handleClose();
    }
  }

  function handleExportSubmit() {
    exportFormRef.value?.handleSubmit();
  }

  function handleSubmit() {
    switch (props.mode) {
      case 'import':
        handleImportSubmit();
        break;
      case 'export':
        handleExportSubmit();
        break;
      case 'group':
        handleGroupSave();
        break;
      case 'case':
      default:
        handleCaseSave();
        break;
    }
  }

  function handleGroupSave() {
    if (!groupFormData.value.name || groupFormData.value.name.trim() === '') {
      notification.warning('请输入测试用例组名称');
      return;
    }
    emit('save', {
      mode: 'group',
      isEdit: isEditMode.value,
      data: { ...groupFormData.value }
    });
    handleClose();
  }

  function handleCaseSave() {
    if (!caseFormData.value.name || caseFormData.value.name.trim() === '') {
      notification.warning('请输入测试用例名称');
      return;
    }
    if (!caseFormData.value.group) {
      notification.warning('请选择所属分组');
      return;
    }
    const saveData: any = { ...caseFormData.value };
    if (caseFormData.value.group === 'new-group') {
      const caseForm = caseFormRef.value as any;
      const newGroupName = typeof caseForm?.newGroupName === 'string'
        ? caseForm.newGroupName.trim()
        : caseForm?.newGroupName?.value?.trim();
      if (!newGroupName) {
        notification.warning('请输入新分组名称');
        return;
      }
      saveData.group = newGroupName;
      saveData.createNewGroup = true;
    }
    if (caseFormRef.value) {
      const formAlgParams = (caseFormRef.value as any).algorithmParams;
      if (formAlgParams && Object.keys(formAlgParams).length > 0) {
        saveData.algorithmParams = formAlgParams;
      }
    }
    emit('save', {
      mode: 'case',
      isEdit: isEditMode.value,
      id: caseFormData.value.id,
      data: saveData
    });
    handleClose();
  }

  function handleClose() {
    emit('close');
  }

  watch(() => props.visible, (newVal) => {
    if (newVal) {
      loadTestGroups();
      if (props.mode === 'case') {
        caseFormData.value = JSON.parse(JSON.stringify(props.formData || {}));
        const configuredAudioIds = extractConfiguredAudioIds(caseFormData.value);
        audioConfig.loadResources(configuredAudioIds);
        dimensionConfig.loadDimensions();
      }
    }
  }, { immediate: true });

  function extractConfiguredAudioIds(formData: any): (string | number)[] {
    const ids: (string | number)[] = [];
    const config = formData?.config;
    if (!config) return ids;

    // Rounds-based format (new architecture)
    if (config.rounds && Array.isArray(config.rounds)) {
      config.rounds.forEach((round: any) => {
        if (Array.isArray(round.audios)) {
          round.audios.forEach((audio: any) => {
            if (audio.audioId) ids.push(audio.audioId);
          });
        }
        const noiseId = round.backgroundNoise?.audioId ?? round.backgroundNoise?.audio_id;
        if (noiseId) ids.push(noiseId);
      });
    }

    // Legacy flat format fallback
    if (config.audios && Array.isArray(config.audios)) {
      config.audios.forEach((audio: any) => {
        if (audio.audioId) ids.push(audio.audioId);
      });
    }
    if (config.backgroundNoise?.audioId) {
      ids.push(config.backgroundNoise.audioId);
    }

    return ids;
  }

  return {
    audioConfig,
    dimensionConfig,
    testCaseGroups,
    caseFormData,
    groupFormData,
    caseFormRef,
    importFormRef,
    exportFormRef,
    isEditMode,
    isSubmitDisabled,
    getModalTitle,
    getSubmitButtonText,
    handleGroupUpdate,
    handleCaseUpdate,
    handleImportUpdate,
    handleExportUpdate,
    openAudioSelectModal,
    openDeviceSelectModal,
    openNoiseDeviceSelectModal,
    openBatchDeviceModal,
    openBatchSplModal,
    openCrossDeviceModal,
    handleAudioSelect,
    handleMultipleAudioSelect,
    handleDeviceSelect,
    handleNoiseDeviceSelect,
    handleBatchDeviceSelect,
    handleCrossDeviceSelect,
    handleBatchSplConfirm,
    handlePreviewAudio,
    handleAudioPreview,
    handleImportSubmit,
    handleExportSubmit,
    handleSubmit,
    handleGroupSave,
    handleCaseSave,
    handleClose,
  };
}
