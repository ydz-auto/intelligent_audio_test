import { ref, computed, watch, provide } from 'vue';
import { testcasesPort } from '@/composables/testCase/testcasesPort';
import { useNotification } from '../../../../composables/modal/useNotification';
import { useAudioConfig } from './useAudioConfig';
import { useDimensionConfig } from './useDimensionConfig';
import { readCamel } from '@/utils/keyTransform';
import { Visibility } from '@/domain/enums';
import { canEditResource } from '../../../../composables/visibility/useVisibility';
import type { GroupFormData, ExportFormData, AudioInfo, TestCaseFormData, TestCaseGroup } from '@/domain';

export function useTestCaseModal(props: any, emit: any) {
  const notification = useNotification();

  const audioConfig = useAudioConfig();
  const dimensionConfig = useDimensionConfig();

  provide('audioConfig', audioConfig);
  provide('dimensionConfig', dimensionConfig);
  provide('playbackDevices', audioConfig.playbackDevices);
  provide('availableDimensions', dimensionConfig.availableDimensions);

  const testCaseGroups = ref<string[]>([]);
  // INT-195：分组名→ID 对照（保存边界把 groupId 收敛到当前所选分组名，杜绝编辑回填的旧 groupId 胜出）
  const testCaseGroupItems = ref<TestCaseGroup[]>([]);
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

  // ===== INT-423/467：可见性守卫 + 分享/设为私有切换 =====

  /** 编辑资源的可见性（新建无 id 时缺省 shared） */
  const caseVisibility = computed(() =>
    caseFormData.value.visibility || Visibility.SHARED);

  /**
   * 403 守卫：编辑私有资源且非 owner（如 admin 打开他人私有用例）。
   * 私有资源对非 owner 隐藏保存/删除入口 + 提示（spec：详情/编辑非 owner 私有 → 403 提示）。
   */
  const visibilityDenied = computed(() => {
    if (!isEditMode.value || props.mode !== 'case') return false;
    if (caseVisibility.value !== Visibility.PRIVATE) return false;
    return !canEditResource({
      visibility: caseVisibility.value,
      createdByUserId: caseFormData.value.createdByUserId,
    });
  });

  /** 是否可切换可见性（owner 或共享资源；私有非 owner 无权限） */
  const canToggleVisibility = computed(() => {
    if (props.mode !== 'case' || !caseFormData.value.id) return false;
    if (visibilityDenied.value) return false;
    return canEditResource({
      visibility: caseVisibility.value,
      createdByUserId: caseFormData.value.createdByUserId,
    });
  });

  /** 分享 / 设为私有：PATCH /testcases/{id}/visibility（需 testcase:share + owner 校验） */
  const toggleVisibility = async () => {
    const id = caseFormData.value.id;
    if (id == null || !canToggleVisibility.value) return;
    const next = caseVisibility.value === Visibility.SHARED
      ? Visibility.PRIVATE
      : Visibility.SHARED;
    try {
      await testcasesPort.updateVisibility(id, next);
      caseFormData.value.visibility = next;
      notification.success(next === Visibility.SHARED ? '已改为共享' : '已设为私有');
      // 提示列表即时刷新徽标（携带 visibilityOnly 标记，handleModalSave 只刷新不重复写库）
      emit('save', {
        mode: 'case',
        isEdit: isEditMode.value,
        id: caseFormData.value.id,
        data: { ...caseFormData.value, visibilityOnly: true },
      });
      handleClose();
    } catch (error: any) {
      notification.error(error?.message || '切换可见性失败，请确认您有该资源的分享权限');
    }
  };

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
      const groupsRes = await testcasesPort.getGroups();
      const groups = groupsRes?.items || [];
      testCaseGroupItems.value = Array.isArray(groups)
        ? groups.filter((g: any) => g && g.name && g.id != null).map((g: any) => ({ id: g.id, name: g.name }))
        : [];
      testCaseGroups.value = testCaseGroupItems.value.map((g: any) => g.name);
    } catch (err) {
      console.error('加载测试用例组失败:', err);
      testCaseGroupItems.value = [];
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
    // 优先读取 case 级全局背景噪声的设备，兼容旧 backgroundNoise 字段
    const bg = (caseFormData.value.config as any)?.backgroundNoiseCase;
    audioConfig.noiseInitialSelectedDevices.value = bg?.deviceIds || [];
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

  function handleAudioSelect(audio: AudioInfo) {
    // 优先使用轮次内音频选择的 callback
    if (pendingAudioCallback.value) {
      // 将选中的音频添加到缓存
      const audioType = audio.audioType || 'dry';
      const existing = audioType === 'noise' ? audioConfig.noiseAudios.value : audioConfig.dryAudios.value;
      if (!existing.find(e => String(e.id) === String(audio.id))) {
        existing.push(audio);
      }
      pendingAudioCallback.value([{ id: String(audio.id), name: audio.name }]);
      pendingAudioCallback.value = null;
      return;
    }
    // 回退：旧版 flat config 格式（audios 与 backgroundNoise 均存在才可回退）
    const cfg = caseFormData.value.config;
    if (cfg?.audios && cfg?.backgroundNoise) {
      audioConfig.handleAudioSelect(audio, cfg.audios, cfg.backgroundNoise);
      caseFormRef.value?.syncConfigFromParent();
    }
  }

  function handleMultipleAudioSelect(audios: AudioInfo[]) {
    // 优先使用轮次内音频选择的 callback（传递全部选中音频）
    if (pendingAudioCallback.value) {
      // 将选中的音频添加到缓存，以便 getAudioDuration/getAudioTags 能查到
      audios.forEach(a => {
        const audioType = a.audioType || 'dry';
        const existing = audioType === 'noise' ? audioConfig.noiseAudios.value : audioConfig.dryAudios.value;
        if (!existing.find(e => String(e.id) === String(a.id))) {
          existing.push(a);
        }
      });
      pendingAudioCallback.value(audios.map(a => ({ id: String(a.id), name: a.name })));
      pendingAudioCallback.value = null;
      return;
    }
    // 回退：旧版 flat config 格式（audios 与 backgroundNoise 均存在才可回退）
    const cfg = caseFormData.value.config;
    if (cfg?.audios && cfg?.backgroundNoise) {
      audioConfig.handleMultipleAudioSelect(audios, cfg.audios, cfg.backgroundNoise);
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
      const cfg = caseFormData.value.config as any;
      // 优先写入 case 级全局背景噪声
      if (cfg.backgroundNoiseCase) {
        cfg.backgroundNoiseCase.deviceIds = selectedDevices;
      } else {
        // 回退到旧版 backgroundNoise 字段
        if (!cfg.backgroundNoise) {
          cfg.backgroundNoise = { audioId: '', deviceIds: [], spl: 0 };
        }
        cfg.backgroundNoise.deviceIds = selectedDevices;
      }
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
      // 旧版 flat 格式回退：批量设置声压级（e2e 判断由用例级 testType 决定）
      caseFormData.value.config.audios.forEach((audio: any) => {
        audio.spl = spl;
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
      const { MODAL_TYPES } = await import('../../../../composables/modal/constants');

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

  // 底部「导入」按钮只触发 ImportForm 校验；通过后由 @submit 回调（handleImportConfirm）
  // 执行保存。此前 footer 与 @submit 绑定同一函数且二者互相调用 child.handleSubmit →
  // emit('submit')，形成 emit 递归死循环，导入永远无法执行（INT-259）。
  function handleImportSubmit() {
    importFormRef.value?.handleSubmit();
  }

  function handleImportConfirm() {
    const file = importFormRef.value?.localFile;
    if (file) {
      emit('save', {
        mode: 'import',
        data: { file }
      });
      handleClose();
    }
  }

  // 底部「导出」按钮只触发 ExportForm 校验；通过后由 @submit 回调（handleExportConfirm）
  // 携带载荷 emit('save')，由 GlobalModalContainer resolve → useTestCaseCard.handleModalSave
  // 执行导出下载。此前二者同调 child.handleSubmit 形成 emit 递归死循环（INT-259）。
  function handleExportSubmit() {
    exportFormRef.value?.handleSubmit();
  }

  function handleExportConfirm() {
    const form = exportFormRef.value as any;
    const ids: (string | number)[] = form?.exportCaseIds ?? [];
    if (!ids.length) {
      notification.warning('没有可导出的用例');
      return;
    }
    emit('save', {
      mode: 'export',
      isEdit: false,
      data: { ...(form?.localFormData ?? {}), ids }
    });
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
      // 新建分组：清掉编辑回填的旧 groupId，交由后端按 group 名称解析/自动建组（INT-195）
      delete saveData.groupId;
    } else {
      // INT-195：提交前把 groupId 收敛到当前所选分组名，后端 group_id 优先级最高，
      // 不收敛则编辑回填的旧 groupId 会压住用户新选的分组（静默失效）
      const selected = testCaseGroupItems.value.find(g => g.name === caseFormData.value.group);
      if (!selected) {
        notification.warning(`所选分组「${caseFormData.value.group}」不存在，请重新选择`);
        return;
      }
      saveData.groupId = selected.id;
    }
    // algorithmParams 为按轮分组独立列，caseFormData 已由 CaseForm 经 RoundConfigEditor 按轮同步；
    // 不能用 CaseForm 暴露的单轮扁平对象覆写，否则后端整体替换会清空第 2+ 轮参数
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
        // 后端原始配置可能残留 snake_case，经 readCamel 兜底归一化（snake_case 字面量收敛于 utils 层）
        const noiseId = readCamel<string | number>(round.backgroundNoise, 'audioId');
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

    // algorithmParams 中的 voiceprint 和 interferers 的 audioId（adapter 已 camelize）
    const algoParams = (formData as any).algorithmParams;
    if (algoParams) {
      const vpObj = algoParams.find?.((p: any) => p.fieldCode === 'voiceprint')?.fieldValue;
      if (vpObj) {
        const vpAudioId = vpObj.audioId;
        if (vpAudioId) ids.push(vpAudioId);
      }
      const interferers = algoParams.find?.((p: any) => p.fieldCode === 'interferers')?.fieldValue;
      if (Array.isArray(interferers)) {
        interferers.forEach((inf: any) => {
          const infAudioId = inf.audioId;
          if (infAudioId) ids.push(infAudioId);
        });
      }
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
    caseVisibility,
    visibilityDenied,
    canToggleVisibility,
    toggleVisibility,
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
    handleImportConfirm,
    handleExportSubmit,
    handleExportConfirm,
    handleSubmit,
    handleGroupSave,
    handleCaseSave,
    handleClose,
  };
}
