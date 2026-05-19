<template>
  <teleport to="body">
    <div
      class="modal-overlay"
      v-if="props.visible"
      @click="handleMaskClick($event)"
      style="
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background-color: rgba(0, 0, 0, 0.5);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 9999 !important;
      "
    >
      <div
        class="modal-container"
        @click.stop
        style="
          background-color: #fff;
          border-radius: 12px;
          box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
          max-height: 90vh;
          max-width: 800px;
          width: 90%;
          overflow: hidden;
          display: flex;
          flex-direction: column;
        "
      >
        <div class="modal-header">
          <h3>{{ getModalTitle() }}</h3>
          <button type="button" class="modal-close" @click="handleClose">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-body" style="flex: 1; overflow-y: auto; padding: 24px;">
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
        <div class="modal-footer">
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
      </div>
    </div>
  </teleport>

  <AudioSelectModal
    :visible="showAudioModal"
    :audio-type="currentAudioType"
    :is-multi-select="true"
    title="选择音频文件"
    @close="showAudioModal = false"
    @select="handleAudioSelect"
    @select-multiple="handleMultipleAudioSelect"
  />

  <AudioPreviewModal
    :visible="showAudioPreviewModal"
    :audio-id="currentPreviewAudioId ?? undefined"
    :audio-type="currentPreviewAudioType"
    :playback-devices="playbackDevices"
    :initial-selected-devices="currentPreviewDeviceId ? [currentPreviewDeviceId] : []"
    :initial-spl="currentPreviewSpl"
    :initial-offset="currentPreviewOffset"
    @close="showAudioPreviewModal = false"
    @preview="handleAudioPreview"
  />

  <GlobalPlaybackDeviceModal
    :visible="showDeviceModal"
    title="选择播放设备"
    :is-multi-select="false"
    :initial-selected-devices="initialSelectedDevices"
    :playback-devices="playbackDevices"
    audio-type="dry"
    :show-scan-devices="false"
    @close="showDeviceModal = false"
    @confirm="handleDeviceSelect"
  />

  <GlobalPlaybackDeviceModal
    :visible="showNoiseDeviceModal"
    title="选择噪声播放设备"
    :is-multi-select="true"
    :initial-selected-devices="noiseInitialSelectedDevices"
    :playback-devices="playbackDevices"
    audio-type="noise"
    :show-scan-devices="false"
    :is-required="false"
    @close="showNoiseDeviceModal = false"
    @confirm="handleNoiseDeviceSelect"
  />

  <GlobalPlaybackDeviceModal
    :visible="showBatchDeviceModal"
    title="批量设置播放设备"
    :is-multi-select="false"
    :initial-selected-devices="batchInitialSelectedDevices"
    :playback-devices="playbackDevices"
    audio-type="dry"
    :show-scan-devices="false"
    @close="showBatchDeviceModal = false"
    @confirm="handleBatchDeviceSelect"
  />

  <GlobalPlaybackDeviceModal
    :visible="showCrossDeviceModal"
    title="选择设备进行交叉分配"
    :is-multi-select="true"
    :initial-selected-devices="crossDeviceInitialSelectedDevices"
    :playback-devices="playbackDevices"
    audio-type="noise"
    :show-scan-devices="false"
    :is-required="true"
    @close="showCrossDeviceModal = false"
    @confirm="handleCrossDeviceSelect"
  />

  <div class="modal-overlay" v-if="showBatchSplModal" @click="showBatchSplModal = false">
    <div class="modal-container" @click.stop style="max-width: 400px;">
      <div class="modal-header">
        <h3>批量设置声压</h3>
        <button type="button" class="modal-close" @click="showBatchSplModal = false">
          <i class="fas fa-times"></i>
        </button>
      </div>
      <div class="modal-body">
        <div class="form-group">
          <label for="batchSplInput">声压级 (dB)</label>
          <input type="number" id="batchSplInput" v-model.number="batchSplValue" class="form-control" min="0" max="120" placeholder="请输入0-120之间的声压级">
        </div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-secondary" @click="showBatchSplModal = false">取消</button>
        <button type="button" class="btn btn-primary" @click="handleBatchSplConfirm">
          <i class="fas fa-check"></i> 确认
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { testcasesApi } from '../../../../utils/api';
import AudioSelectModal from '../../AudioSelectModal.vue';
import AudioPreviewModal from '../../modal/AudioPreviewModal.vue';
import GlobalPlaybackDeviceModal from '../../modal/GlobalPlaybackDeviceModal.vue';
import GroupForm from './GroupForm.vue';
import CaseForm from './CaseForm.vue';
import ImportForm from './ImportForm.vue';
import ExportForm from './ExportForm.vue';
import { useAudioConfig } from './useAudioConfig';
import type { TestCaseFormData, GroupFormData, ExportFormData, AudioItem } from './types';

const props = defineProps({
  visible: { type: Boolean, default: false },
  mode: { type: String, default: 'case', validator: (value: string) => ['case', 'group', 'import', 'export'].includes(value) },
  testType: { type: String, default: 'api' },
  formData: { type: Object, default: () => ({}) }
});

const emit = defineEmits(['close', 'save']);

const audioConfig = useAudioConfig();

const {
  playbackDevices,
  showAudioModal,
  showDeviceModal,
  showNoiseDeviceModal,
  showBatchDeviceModal,
  showCrossDeviceModal,
  showBatchSplModal,
  showAudioPreviewModal,
  currentAudioType,
  currentAudioIndex,
  currentDeviceAudioIndex,
  initialSelectedDevices,
  noiseInitialSelectedDevices,
  batchInitialSelectedDevices,
  crossDeviceInitialSelectedDevices,
  batchSplValue,
  currentPreviewAudioId,
  currentPreviewAudioType,
  currentPreviewDeviceId,
  currentPreviewSpl,
  currentPreviewOffset,
  loadResources,
  handleAudioSelect: audioHandleAudioSelect,
  handleMultipleAudioSelect: audioHandleMultipleAudioSelect,
  handleDeviceSelect: audioHandleDeviceSelect,
  handleNoiseDeviceSelect: audioHandleNoiseDeviceSelect,
  handleBatchDeviceSelect: audioHandleBatchDeviceSelect,
  handleCrossDeviceSelect: audioHandleCrossDeviceSelect
} = audioConfig;

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
  currentAudioType.value = audioType;
  currentAudioIndex.value = index ?? null;
  showAudioModal.value = true;
}

function openDeviceSelectModal(audioIndex: number) {
  currentDeviceAudioIndex.value = audioIndex;
  const audio = caseFormData.value.config?.audios?.[audioIndex];
  initialSelectedDevices.value = audio?.playbackDeviceId ? [audio.playbackDeviceId] : [];
  showDeviceModal.value = true;
}

function openNoiseDeviceSelectModal() {
  noiseInitialSelectedDevices.value = caseFormData.value.config?.backgroundNoise?.deviceIds || [];
  showNoiseDeviceModal.value = true;
}

function openBatchDeviceModal() {
  const e2eAudios = caseFormData.value.config?.audios?.filter(a => a.testType === 'e2e' && a.playbackDeviceId) || [];
  batchInitialSelectedDevices.value = e2eAudios.length > 0 ? [e2eAudios[0].playbackDeviceId!] : [];
  showBatchDeviceModal.value = true;
}

function openBatchSplModal() {
  const e2eAudios = caseFormData.value.config?.audios?.filter(a => a.testType === 'e2e') || [];
  batchSplValue.value = e2eAudios.length > 0 ? e2eAudios[0].spl : 65;
  showBatchSplModal.value = true;
}

function openCrossDeviceModal() {
  const e2eAudios = caseFormData.value.config?.audios?.filter(a => a.testType === 'e2e') || [];
  const deviceIds = [...new Set(e2eAudios.map(a => a.playbackDeviceId).filter(Boolean))];
  crossDeviceInitialSelectedDevices.value = deviceIds;
  showCrossDeviceModal.value = true;
}

function handleAudioSelect(audio: AudioItem) {
  if (caseFormData.value.config) {
    audioHandleAudioSelect(audio, caseFormData.value.config.audios, caseFormData.value.config.backgroundNoise);
  }
}

function handleMultipleAudioSelect(audios: AudioItem[]) {
  if (caseFormData.value.config) {
    audioHandleMultipleAudioSelect(audios, caseFormData.value.config.audios, caseFormData.value.config.backgroundNoise);
  }
}

function handleDeviceSelect(selectedDevices: string[]) {
  if (caseFormData.value.config) {
    audioHandleDeviceSelect(selectedDevices, caseFormData.value.config.audios);
  }
}

function handleNoiseDeviceSelect(selectedDevices: string[]) {
  if (caseFormData.value.config) {
    audioHandleNoiseDeviceSelect(selectedDevices, caseFormData.value.config.backgroundNoise);
  }
}

function handleBatchDeviceSelect(selectedDevices: string[]) {
  if (caseFormData.value.config) {
    audioHandleBatchDeviceSelect(selectedDevices, caseFormData.value.config.audios);
  }
}

function handleCrossDeviceSelect(selectedDevices: string[]) {
  if (caseFormData.value.config) {
    audioHandleCrossDeviceSelect(selectedDevices, caseFormData.value.config.audios);
  }
}

function handleBatchSplConfirm() {
  if (caseFormData.value.config) {
    caseFormData.value.config.audios.forEach(audio => {
      if (audio.testType === 'e2e') {
        audio.spl = batchSplValue.value;
      }
    });
  }
  showBatchSplModal.value = false;
}

function handlePreviewAudio(audioId: string, audioType: 'dry' | 'noise') {
  currentPreviewAudioId.value = audioId;
  currentPreviewAudioType.value = audioType;

  if (audioType === 'dry' && caseFormData.value.config) {
    const audio = caseFormData.value.config.audios.find(a => a.audioId === audioId);
    if (audio) {
      currentPreviewDeviceId.value = audio.playbackDeviceId || null;
      currentPreviewSpl.value = audio.spl || 65;
    }
  } else if (audioType === 'noise' && caseFormData.value.config) {
    const deviceIds = caseFormData.value.config.backgroundNoise.deviceIds || [];
    currentPreviewDeviceId.value = deviceIds.length > 0 ? deviceIds[0] : null;
    currentPreviewSpl.value = caseFormData.value.config.backgroundNoise.spl || 65;
  }

  currentPreviewOffset.value = 0;
  showAudioPreviewModal.value = true;
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
      audioType: currentPreviewAudioType.value,
      isTestCasePreview: false,
      playbackDevices: playbackDevices.value,
      selectedPlaybackDevices: previewData.playbackDeviceId ? [previewData.playbackDeviceId] : previewData.noisePlaybackDeviceIds || [],
      playbackMode: previewData.playbackMode || 'frontend',
      spl: previewData.spl || 65,
      offset: previewData.offset || 0
    });
  } catch (err: unknown) {
    console.error('打开音频播放器失败:', err);
    alert('音频试听失败: ' + ((err as Error).message || '未知错误'));
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
    alert('请输入测试用例组名称');
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
    alert('请输入测试用例名称');
    return;
  }
  if (!caseFormData.value.group) {
    alert('请选择所属分组');
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

function handleMaskClick(event: MouseEvent) {
  if (event.target === event.currentTarget) {
    return;
  }
}

function handleKeyDown(event: KeyboardEvent) {
  if (event.key === 'Escape' && props.visible) {
    handleClose();
  }
}

watch(() => props.visible, (newVal) => {
  if (newVal) {
    window.addEventListener('keydown', handleKeyDown);
    loadTestGroups();
    loadResources();
  } else {
    window.removeEventListener('keydown', handleKeyDown);
  }
}, { immediate: true });

onMounted(() => {
  loadTestGroups();
});

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown);
});
</script>

<style scoped>
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid #e9ecef;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
}

.modal-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #343a40;
}

.modal-close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #6c757d;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  transition: all 0.2s;
}

.modal-close:hover {
  color: #343a40;
  background-color: #e9ecef;
  transform: rotate(90deg);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid #e9ecef;
  background: #f8f9fa;
}

.btn {
  padding: 10px 20px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary {
  background: #007bff;
  color: white;
  border: none;
}

.btn-primary:hover {
  background: #0056b3;
}

.btn-primary:disabled {
  background: #6c757d;
  cursor: not-allowed;
}

.btn-secondary {
  background: #6c757d;
  color: white;
  border: none;
}

.btn-secondary:hover {
  background: #5a6268;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #495057;
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
</style>
