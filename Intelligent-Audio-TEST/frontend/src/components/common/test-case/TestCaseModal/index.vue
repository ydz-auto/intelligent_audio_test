<template>
  <div class="test-case-modal-content">
    <div class="modal-body-content">
      <GroupForm
        v-if="props.mode === 'group'"
        :form-data="props.formData"
        @update="handleGroupUpdate"
      />
      <CaseForm
        v-else-if="props.mode === 'case'"
        ref="caseFormRef"
        :form-data="props.formData"
        :test-case-groups="testCaseGroups"
        :audio-config="audioConfig"
        :dimension-config="dimensionConfig"
        @update="handleCaseUpdate"
        @open-audio-modal="openAudioSelectModal"
        @open-device-modal="openDeviceSelectModal"
        @open-noise-device-modal="openNoiseDeviceSelectModal"
        @open-batch-device-modal="openBatchDeviceModal"
        @open-cross-device-modal="openCrossDeviceModal"
        @open-batch-spl-modal="openBatchSplModal"
        @preview-audio="handlePreviewAudio"
      />
      <ImportForm
        v-else-if="props.mode === 'import'"
        ref="importFormRef"
        @update="handleImportUpdate"
        @submit="handleImportSubmit"
      />
      <ExportForm
        v-else-if="props.mode === 'export'"
        ref="exportFormRef"
        :test-case-groups="testCaseGroups"
        :test-type="props.testType"
        @update="handleExportUpdate"
        @submit="handleExportSubmit"
      />
    </div>
    <div class="modal-footer-content">
      <button type="button" class="btn btn-secondary" @click="handleClose">取消</button>
      <button
        type="button"
        class="btn btn-primary"
        :disabled="isSubmitDisabled"
        @click="handleSubmit"
      >
        {{ getSubmitButtonText() }}
      </button>
    </div>

    <AudioSelectModal
      :visible="audioConfig.showAudioModal.value"
      :audio-type="audioConfig.currentAudioType.value"
      :is-multi-select="true"
      title="选择音频文件"
      @close="audioConfig.showAudioModal.value = false"
      @select="handleAudioSelect"
      @select-multiple="handleMultipleAudioSelect"
    />

    <AudioPreviewModal
      :visible="audioConfig.showAudioPreviewModal.value"
      :audio-id="audioConfig.currentPreviewAudioId.value ?? undefined"
      :audio-type="audioConfig.currentPreviewAudioType.value"
      :playback-devices="audioConfig.playbackDevices.value"
      :initial-selected-devices="audioConfig.currentPreviewDeviceId.value ? [audioConfig.currentPreviewDeviceId.value] : []"
      :initial-spl="audioConfig.currentPreviewSpl.value"
      :initial-offset="audioConfig.currentPreviewOffset.value"
      @close="audioConfig.showAudioPreviewModal.value = false"
      @preview="handleAudioPreview"
    />

    <GlobalPlaybackDeviceModal
      :visible="audioConfig.showDeviceModal.value"
      title="选择播放设备"
      :is-multi-select="false"
      :initial-selected-devices="audioConfig.initialSelectedDevices.value"
      :playback-devices="audioConfig.playbackDevices.value"
      audio-type="dry"
      :show-scan-devices="false"
      @close="audioConfig.showDeviceModal.value = false"
      @confirm="handleDeviceSelect"
    />

    <GlobalPlaybackDeviceModal
      :visible="audioConfig.showNoiseDeviceModal.value"
      title="选择噪声播放设备"
      :is-multi-select="true"
      :initial-selected-devices="audioConfig.noiseInitialSelectedDevices.value"
      :playback-devices="audioConfig.playbackDevices.value"
      audio-type="noise"
      :show-scan-devices="false"
      :is-required="false"
      @close="audioConfig.showNoiseDeviceModal.value = false"
      @confirm="handleNoiseDeviceSelect"
    />

    <GlobalPlaybackDeviceModal
      :visible="audioConfig.showBatchDeviceModal.value"
      title="批量设置播放设备"
      :is-multi-select="false"
      :initial-selected-devices="audioConfig.batchInitialSelectedDevices.value"
      :playback-devices="audioConfig.playbackDevices.value"
      audio-type="dry"
      :show-scan-devices="false"
      @close="audioConfig.showBatchDeviceModal.value = false"
      @confirm="handleBatchDeviceSelect"
    />

    <GlobalPlaybackDeviceModal
      :visible="audioConfig.showCrossDeviceModal.value"
      title="选择设备进行交叉分配"
      :is-multi-select="true"
      :initial-selected-devices="audioConfig.crossDeviceInitialSelectedDevices.value"
      :playback-devices="audioConfig.playbackDevices.value"
      audio-type="noise"
      :show-scan-devices="false"
      :is-required="true"
      @close="audioConfig.showCrossDeviceModal.value = false"
      @confirm="handleCrossDeviceSelect"
    />

    <BatchSplModal
      v-model="audioConfig.batchSplValue.value"
      v-model:visible="audioConfig.showBatchSplModal.value"
      @confirm="handleBatchSplConfirm"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, provide } from 'vue';
import { testcasesApi } from '../../../../utils/api';
import { useNotification } from '../../../../composables/useNotification';
import AudioSelectModal from '../../AudioSelectModal.vue';
import AudioPreviewModal from '../../modal/AudioPreviewModal.vue';
import GlobalPlaybackDeviceModal from '../../modal/GlobalPlaybackDeviceModal.vue';
import BatchSplModal from './BatchSplModal.vue';
import GroupForm from './GroupForm.vue';
import CaseForm from './CaseForm.vue';
import ImportForm from './ImportForm.vue';
import ExportForm from './ExportForm.vue';
import { useAudioConfig } from './useAudioConfig';
import { useDimensionConfig } from './useDimensionConfig';
import type { TestCaseFormData, GroupFormData, ExportFormData, AudioItem } from './types';

const props = defineProps({
  visible: { type: Boolean, default: false },
  mode: { type: String, default: 'case', validator: (value: string) => ['case', 'group', 'import', 'export'].includes(value) },
  testType: { type: String, default: 'api' },
  formData: { type: Object, default: () => ({}) },
  title: { type: String, default: '' }
});

const emit = defineEmits(['close', 'save', 'confirm']);

const notification = useNotification();

const audioConfig = useAudioConfig();
const dimensionConfig = useDimensionConfig();

provide('audioConfig', audioConfig);
provide('dimensionConfig', dimensionConfig);

const testCaseGroups = ref<string[]>([]);
const caseFormData = ref<Partial<TestCaseFormData>>({});
const groupFormData = ref<GroupFormData>({ name: '', description: '', algorithmType: '' });
const caseFormRef = ref<InstanceType<typeof CaseForm> | null>(null);
const importFormRef = ref<InstanceType<typeof ImportForm> | null>(null);
const exportFormRef = ref<InstanceType<typeof ExportForm> | null>(null);

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

function openAudioSelectModal(audioType: 'dry' | 'noise', index?: number) {
  if (!caseFormData.value.config) {
    caseFormData.value.config = {
      audios: [{ audioId: '', testType: 'api', playbackDeviceId: '', spl: 65, playOrder: 0 }],
      dimensions: { api: [], e2e: [] },
      backgroundNoise: { audioId: '', deviceIds: [], spl: 0 }
    };
  }
  audioConfig.currentAudioType.value = audioType;
  audioConfig.currentAudioIndex.value = index ?? null;
  audioConfig.showAudioModal.value = true;
}

function openDeviceSelectModal(audioIndex: number) {
  audioConfig.currentDeviceAudioIndex.value = audioIndex;
  const audio = caseFormData.value.config?.audios?.[audioIndex];
  audioConfig.initialSelectedDevices.value = audio?.playbackDeviceId ? [audio.playbackDeviceId] : [];
  audioConfig.showDeviceModal.value = true;
}

function openNoiseDeviceSelectModal() {
  audioConfig.noiseInitialSelectedDevices.value = caseFormData.value.config?.backgroundNoise?.deviceIds || [];
  audioConfig.showNoiseDeviceModal.value = true;
}

function openBatchDeviceModal() {
  const e2eAudios = caseFormData.value.config?.audios?.filter(a => a.testType === 'e2e' && a.playbackDeviceId) || [];
  audioConfig.batchInitialSelectedDevices.value = e2eAudios.length > 0 ? [e2eAudios[0].playbackDeviceId!] : [];
  audioConfig.showBatchDeviceModal.value = true;
}

function openBatchSplModal() {
  const e2eAudios = caseFormData.value.config?.audios?.filter(a => a.testType === 'e2e') || [];
  audioConfig.batchSplValue.value = e2eAudios.length > 0 ? e2eAudios[0].spl : 65;
  audioConfig.showBatchSplModal.value = true;
}

function openCrossDeviceModal() {
  const e2eAudios = caseFormData.value.config?.audios?.filter(a => a.testType === 'e2e') || [];
  const deviceIds = [...new Set(e2eAudios.map(a => a.playbackDeviceId).filter(Boolean))];
  audioConfig.crossDeviceInitialSelectedDevices.value = deviceIds;
  audioConfig.showCrossDeviceModal.value = true;
}

function handleAudioSelect(audio: AudioItem) {
  if (caseFormData.value.config) {
    audioConfig.handleAudioSelect(audio, caseFormData.value.config.audios, caseFormData.value.config.backgroundNoise);
  }
}

function handleMultipleAudioSelect(audios: AudioItem[]) {
  if (caseFormData.value.config) {
    audioConfig.handleMultipleAudioSelect(audios, caseFormData.value.config.audios, caseFormData.value.config.backgroundNoise);
  }
}

function handleDeviceSelect(selectedDevices: string[]) {
  if (caseFormData.value.config) {
    audioConfig.handleDeviceSelect(selectedDevices, caseFormData.value.config.audios);
  }
}

function handleNoiseDeviceSelect(selectedDevices: string[]) {
  if (caseFormData.value.config) {
    audioConfig.handleNoiseDeviceSelect(selectedDevices, caseFormData.value.config.backgroundNoise);
  }
}

function handleBatchDeviceSelect(selectedDevices: string[]) {
  if (caseFormData.value.config) {
    audioConfig.handleBatchDeviceSelect(selectedDevices, caseFormData.value.config.audios);
  }
}

function handleCrossDeviceSelect(selectedDevices: string[]) {
  if (caseFormData.value.config) {
    audioConfig.handleCrossDeviceSelect(selectedDevices, caseFormData.value.config.audios);
  }
}

function handleBatchSplConfirm(spl: number) {
  if (caseFormData.value.config) {
    caseFormData.value.config.audios.forEach(audio => {
      if (audio.testType === 'e2e') {
        audio.spl = spl;
      }
    });
  }
}

function handlePreviewAudio(audioId: string, audioType: 'dry' | 'noise') {
  audioConfig.currentPreviewAudioId.value = audioId;
  audioConfig.currentPreviewAudioType.value = audioType;

  if (audioType === 'dry' && caseFormData.value.config) {
    const audio = caseFormData.value.config.audios.find(a => a.audioId === audioId);
    if (audio) {
      audioConfig.currentPreviewDeviceId.value = audio.playbackDeviceId || null;
      audioConfig.currentPreviewSpl.value = audio.spl || 65;
    }
  } else if (audioType === 'noise' && caseFormData.value.config) {
    const deviceIds = caseFormData.value.config.backgroundNoise.deviceIds || [];
    audioConfig.currentPreviewDeviceId.value = deviceIds.length > 0 ? deviceIds[0] : null;
    audioConfig.currentPreviewSpl.value = caseFormData.value.config.backgroundNoise.spl || 65;
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
  emit('save', {
    mode: 'case',
    isEdit: isEditMode.value,
    id: caseFormData.value.id,
    data: { ...caseFormData.value }
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
      const configuredAudioIds = extractConfiguredAudioIds(props.formData);
      audioConfig.loadResources(configuredAudioIds);
      dimensionConfig.loadDimensions();
    }
  }
}, { immediate: true });

function extractConfiguredAudioIds(formData: any): (string | number)[] {
  const ids: (string | number)[] = [];
  if (formData?.config?.audios && Array.isArray(formData.config.audios)) {
    formData.config.audios.forEach((audio: any) => {
      if (audio.audioId) {
        ids.push(audio.audioId);
      }
    });
  }
  if (formData?.config?.backgroundNoise?.audioId) {
    ids.push(formData.config.backgroundNoise.audioId);
  }
  return ids;
}

onMounted(() => {
  loadTestGroups();
});
</script>

<style scoped>
.test-case-modal-content {
  width: 100%;
}

.modal-body-content {
  max-height: 70vh;
  overflow-y: auto;
  padding: 20px;
}

.modal-footer-content {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid var(--border-color);
  background: var(--background-secondary);
}
</style>
