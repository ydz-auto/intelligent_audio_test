<template>
  <teleport to="body">
    <div class="modal-overlay" v-if="visible" style="opacity: 1 !important; visibility: visible !important; pointer-events: auto !important;">
      <div class="modal-container" @click.stop>
        <div class="modal-header">
          <h3>音频试听配置</h3>
          <button type="button" class="modal-close" @click="handleClose">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-body">
          <div class="scan-status" v-if="isScanning || scanError">
            <div v-if="isScanning" class="scan-status-scanning">
              <i class="fas fa-spinner fa-spin"></i>
              <span>正在扫描可用设备...</span>
            </div>
            <div v-else-if="scanError" class="scan-status-error">
              <i class="fas fa-exclamation-circle"></i>
              <span>{{ scanError }}</span>
            </div>
          </div>

          <div class="form-section">
            <h4>选择播放模式 <span class="required">*</span></h4>
            <div class="radio-group">
              <label class="radio-item">
                <input type="radio" value="frontend" v-model="previewConfig.playbackMode">
                <span>前端扬声器播放</span>
              </label>
              <label class="radio-item">
                <input type="radio" value="backend" v-model="previewConfig.playbackMode">
                <span>后端扬声器播放</span>
              </label>
            </div>
            <p class="mode-description" v-if="previewConfig.playbackMode === 'frontend'">
              <i class="fas fa-info-circle"></i> 音频将通过浏览器前端直接播放，无需选择设备
            </p>
            <p class="mode-description" v-else>
              <i class="fas fa-info-circle"></i> 音频将通过选择的设备在后端播放，请选择播放设备
            </p>
          </div>

          <div class="form-section" v-if="props.audioType === 'dry' && previewConfig.playbackMode === 'backend'">
            <h4>选择播放设备 <span class="required">*</span></h4>
            <div class="form-group">
              <label for="playbackDevice">播放设备</label>
              <select v-model="previewConfig.playbackDeviceId" class="form-control" required>
                <option value="">请选择设备</option>
                <option v-for="device in props.playbackDevices" 
                        :key="device.id" 
                        :value="device.id">
                  {{ device.name }} (通道 {{ device.channelIndex }}) [{{ device.deviceType === 'dry' ? '干声' : device.deviceType === 'noise' ? '噪声' : device.deviceType || '未知' }}]
                </option>
              </select>
            </div>
          </div>

          <div class="form-section" v-if="audioType === 'noise' && previewConfig.playbackMode === 'backend'">
            <h4>选择噪声播放设备 <span class="required">*</span></h4>
            
            <div v-if="props.playbackDevices.length > 0" class="device-group">
              <div class="checkbox-group">
                <label v-for="device in props.playbackDevices" 
                       :key="device.id" class="checkbox-item">
                  <input type="checkbox" 
                         :value="device.id" 
                         v-model="previewConfig.noisePlaybackDeviceIds">
                  <span>{{ device.name }} (通道 {{ device.channelIndex }}) [{{ device.deviceType === 'dry' ? '干声' : device.deviceType === 'noise' ? '噪声' : device.deviceType || '未知' }}]</span>
                </label>
              </div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="handleClose">取消</button>
          <button type="button" class="btn btn-primary" @click="handlePreview" :disabled="!isFormValid">
            <i class="fas fa-play"></i> 开始试听
          </button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { playbackApi, audiosApi } from '../../../utils/api';

const props = defineProps({
  visible: { type: Boolean, default: false },
  audioId: { type: String, required: false, default: null },
  audioType: { type: String, default: 'dry' },
  playbackDevices: { type: Array, default: () => [] },
  initialSelectedDevices: { type: Array, default: () => [] },
  initialSpl: { type: Number, default: 65 },
  initialOffset: { type: Number, default: 0 }
});

const emit = defineEmits(['close', 'preview']);

const scanDevices = ref([]);
const isScanning = ref(false);
const scanError = ref('');

const previewConfig = ref({
  deviceUniqueIds: [],
  playbackDeviceId: '',
  noisePlaybackDeviceIds: [],
  playbackMode: 'frontend',
  spl: props.initialSpl,
  offset: props.initialOffset
});

watch(() => props.visible, async (newValue) => {
  if (newValue) {
    resetForm();
    await scanAvailableDevices();
  }
});

const scanAvailableDevices = async () => {
  isScanning.value = true;
  scanError.value = '';
  
  try {
    const devices = await playbackApi.scan();
    scanDevices.value = devices || [];
  } catch (error) {
    console.error('扫描设备失败:', error);
    scanError.value = '扫描设备失败，请重试';
    scanDevices.value = [];
  } finally {
    isScanning.value = false;
  }
};

const filteredDevices = computed(() => {
  const dbDeviceKeys = new Set(props.playbackDevices.map(device => `${device.name}|${device.channelIndex}`));
  
  const uniqueScanDevices = scanDevices.value.filter(scanDevice => {
    const scanDeviceKey = `${scanDevice.name}|${scanDevice.channelIndex}`;
    return !dbDeviceKeys.has(scanDeviceKey);
  });
  
  if (props.audioType === 'dry') {
    const dbDryDevices = props.playbackDevices.filter(device => device.deviceType === 'dry');
    return [...dbDryDevices, ...uniqueScanDevices];
  } else {
    const dbNoiseDevices = props.playbackDevices.filter(device => device.deviceType === 'noise');
    return [...dbNoiseDevices, ...uniqueScanDevices];
  }
});

const isFormValid = computed(() => {
  // 前端播放模式：只需要选择播放模式，不需要选择设备
  if (previewConfig.value.playbackMode === 'frontend') {
    return !!previewConfig.value.playbackMode;
  }
  
  // 后端播放模式：需要选择播放模式和设备
  if (previewConfig.value.playbackMode === 'backend') {
    if (props.audioType === 'dry') {
      return !!previewConfig.value.playbackDeviceId;
    } else if (props.audioType === 'noise') {
      return previewConfig.value.noisePlaybackDeviceIds.length > 0;
    }
  }
  
  return false;
});

const resetForm = () => {
  console.log('[AudioPreviewModal] resetForm, initialSelectedDevices:', props.initialSelectedDevices);
  const initialDevice = props.initialSelectedDevices.length > 0 ? props.initialSelectedDevices[0] : '';
  console.log('[AudioPreviewModal] initialDevice:', initialDevice);
  previewConfig.value = {
    deviceUniqueIds: initialDevice ? [initialDevice] : [],
    playbackDeviceId: initialDevice,
    noisePlaybackDeviceIds: [...props.initialSelectedDevices],
    playbackMode: previewConfig.value?.playbackMode || 'frontend',
    spl: props.initialSpl,
    offset: props.initialOffset
  };
  console.log('[AudioPreviewModal] previewConfig after reset:', previewConfig.value);
};

const stopPreview = async () => {
  try {
    console.log('[AudioPreviewModal] stopPreview called');
    if (props.audioId && previewConfig.value.playbackMode === 'backend') {
      console.log('[AudioPreviewModal] 后端播放模式，调用停止预览接口');
      await audiosApi.stopPreview(props.audioId);
      console.log('[AudioPreviewModal] 停止预览成功');
    }
  } catch (error) {
    console.error('[AudioPreviewModal] 停止预览失败:', error);
  }
};

const handleClose = async () => {
  await stopPreview();
  emit('close');
};

const handleKeyDown = async (event) => {
  if (event.key === 'Escape' && props.visible) {
    await handleClose();
  }
};

watch(() => props.visible, async (newVal) => {
  if (newVal) {
    window.addEventListener('keydown', handleKeyDown);
  } else {
    window.removeEventListener('keydown', handleKeyDown);
    await stopPreview();
  }
}, { immediate: true });

onUnmounted(async () => {
  window.removeEventListener('keydown', handleKeyDown);
  await stopPreview();
});

const handlePreview = () => {
  console.log('[AudioPreviewModal] handlePreview, previewConfig:', previewConfig.value);
  
  let deviceUniqueIds = [];
  let playbackDeviceId = '';
  let noisePlaybackDeviceIds = [];
  
  // 只有后端播放模式才需要收集设备信息
  if (previewConfig.value.playbackMode === 'backend') {
    console.log('[AudioPreviewModal] 后端播放模式，收集设备信息');
    if (props.audioType === 'dry') {
      if (previewConfig.value.playbackDeviceId) {
        deviceUniqueIds = [previewConfig.value.playbackDeviceId];
        playbackDeviceId = previewConfig.value.playbackDeviceId;
        console.log('[AudioPreviewModal] 干声设备ID:', playbackDeviceId);
      }
    } else if (props.audioType === 'noise') {
      deviceUniqueIds = [...previewConfig.value.noisePlaybackDeviceIds];
      noisePlaybackDeviceIds = [...previewConfig.value.noisePlaybackDeviceIds];
      console.log('[AudioPreviewModal] 噪声设备ID:', noisePlaybackDeviceIds);
    }
  } else {
    console.log('[AudioPreviewModal] 前端播放模式，跳过设备收集');
  }
  
  previewConfig.value.deviceUniqueIds = deviceUniqueIds;
  
  const result = {
    audioId: props.audioId,
    deviceUniqueIds: deviceUniqueIds,
    playbackMode: previewConfig.value.playbackMode,
    playbackDeviceId: playbackDeviceId,
    noisePlaybackDeviceIds: noisePlaybackDeviceIds,
    spl: previewConfig.value.spl,
    offset: previewConfig.value.offset
  };
  console.log('[AudioPreviewModal] emit preview result:', result);
  
  emit('preview', result);
  handleClose();
};

const handleMultiSelectChange = (event) => {
  const selectedOptions = Array.from(event.target.selectedOptions);
  previewConfig.value.noisePlaybackDeviceIds = selectedOptions.map(option => option.value);
};
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 10000;
  animation: fadeIn 0.3s ease;
  opacity: 1 !important;
  visibility: visible !important;
  pointer-events: auto !important;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.modal-container {
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  width: 90%;
  max-width: 600px;
  max-height: 90vh;
  overflow-y: auto;
  animation: slideIn 0.3s ease;
}

@keyframes slideIn {
  from { transform: translateY(-20px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

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

.modal-body {
  padding: 24px;
}

.form-section {
  margin-bottom: 24px;
  padding: 20px;
  background-color: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #e9ecef;
}

.form-section h4 {
  margin-top: 0;
  margin-bottom: 16px;
  font-size: 18px;
  font-weight: 600;
  color: #343a40;
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

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #495057;
}

.required {
  color: #dc3545;
  font-weight: bold;
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

.form-control:invalid {
  border-color: #dc3545;
  box-shadow: 0 0 0 0.2rem rgba(220, 53, 69, 0.25);
}

.scan-status {
  margin-bottom: 20px;
  padding: 12px;
  border-radius: 6px;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.scan-status-scanning {
  background-color: #e3f2fd;
  color: #1976d2;
  border: 1px solid #bbdefb;
}

.scan-status-error {
  background-color: #ffebee;
  color: #d32f2f;
  border: 1px solid #ffcdd2;
}

.device-group {
  margin-bottom: 20px;
  padding: 16px;
  background-color: #ffffff;
  border: 1px solid #e9ecef;
  border-radius: 6px;
}

.device-group h5 {
  margin-top: 0;
  margin-bottom: 12px;
  font-size: 16px;
  font-weight: 600;
  color: #495057;
}

.checkbox-group {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 12px;
}

.checkbox-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background-color: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.checkbox-item:hover {
  background-color: #e3f2fd;
  border-color: #bbdefb;
}

.checkbox-item input[type="checkbox"] {
  width: 18px;
  height: 18px;
  cursor: pointer;
}

.checkbox-item span {
  margin: 0;
  cursor: pointer;
  font-weight: 400;
  word-break: break-word;
}

.radio-group {
  display: flex;
  gap: 24px;
  margin-top: 8px;
}

.radio-item {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.radio-item input[type="radio"] {
  width: 18px;
  height: 18px;
  cursor: pointer;
}

.radio-item label {
  margin: 0;
  cursor: pointer;
  font-weight: 400;
}

.mode-description {
  margin-top: 12px;
  padding: 12px;
  background-color: #e3f2fd;
  border: 1px solid #bbdefb;
  border-radius: 6px;
  font-size: 14px;
  color: #1976d2;
  display: flex;
  align-items: center;
  gap: 8px;
}

.mode-description i {
  font-size: 16px;
}

.modal-footer {
  padding: 20px 24px;
  border-top: 1px solid #e9ecef;
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.btn {
  padding: 10px 24px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.btn-primary {
  background-color: #007bff;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background-color: #0056b3;
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 123, 255, 0.3);
}

.btn-primary:disabled {
  background-color: #6c757d;
  cursor: not-allowed;
  opacity: 0.65;
  transform: none;
  box-shadow: none;
}

.btn-secondary {
  background-color: #f8f9fa;
  color: #6c757d;
  border: 1px solid #dee2e6;
}

.btn-secondary:hover {
  background-color: #e9ecef;
  color: #495057;
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}
</style>
