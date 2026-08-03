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
        :form-data="caseFormData"
        :test-case-groups="testCaseGroups"
        :audio-config="audioConfig"
        :dimension-config="dimensionConfig"
        :test-type="props.testType"
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
      :visible="audioConfig.showBatchSplModal.value"
      :model-value="audioConfig.batchSplValue.value"
      @update:visible="(val: boolean) => audioConfig.showBatchSplModal.value = val"
      @update:model-value="(val: number) => audioConfig.batchSplValue.value = val"
      @confirm="handleBatchSplConfirm"
    />
  </div>
</template>

<script setup lang="ts">
import AudioSelectModal from '../../audio/AudioSelectModal.vue';
import AudioPreviewModal from '../../modal/AudioPreviewModal.vue';
import GlobalPlaybackDeviceModal from '../../modal/GlobalPlaybackDeviceModal.vue';
import BatchSplModal from './BatchSplModal.vue';
import GroupForm from './GroupForm.vue';
import CaseForm from './CaseForm.vue';
import ImportForm from './ImportForm.vue';
import ExportForm from './ExportForm.vue';
import { useTestCaseModal } from './index';

const props = defineProps({
  visible: { type: Boolean, default: false },
  mode: { type: String, default: 'case', validator: (value: string) => ['case', 'group', 'import', 'export'].includes(value) },
  testType: { type: String, default: 'api' },
  formData: { type: Object, default: () => ({}) },
  title: { type: String, default: '' }
});

const emit = defineEmits(['close', 'save', 'confirm']);

const {
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
} = useTestCaseModal(props, emit);
</script>

<style scoped>
@import './index.css';
</style>
