<template>
  <teleport to="body">
    <div class="modal-overlay" v-if="visible" style="opacity: 1 !important; visibility: visible !important; pointer-events: auto !important; z-index: 13002 !important;">
      <div class="modal-container" @click.stop>
        <div class="modal-header">
          <h3>{{ audioType === 'dry' ? '选择播放设备' : '选择噪声播放设备' }}<span class="required" v-if="isRequired">*</span></h3>
          <button type="button" class="modal-close" @click="handleClose">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-body">
          <div class="scan-status-container">
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
            <div class="scan-actions">
              <button 
                class="btn btn-secondary btn-sm" 
                @click="scanAvailableDevices"
                :disabled="isScanning"
              >
                <i class="fas fa-sync-alt"></i>
                重新扫描
              </button>
            </div>
          </div>

          <div v-if="audioType === 'dry'" class="form-section">
            <select v-model="selectedDevice" class="form-control" required>
              <option value="">请选择设备</option>
              <option v-for="device in filteredDryDevices" 
                      :key="device.id" 
                      :value="device.id">
                {{ device.name }} (通道 {{ device.channelIndex }}) [{{ device.deviceType === 'dry' ? '干声' : device.deviceType === 'noise' ? '噪声' : device.deviceType || '未知' }}]
              </option>
            </select>
          </div>
          
          <div v-else-if="audioType === 'noise'">
            <div v-if="Array.isArray(playbackDevices) && playbackDevices.length > 0" class="device-group">
              <h5>已选设备</h5>
              <div class="checkbox-group">
                <label v-for="device in playbackDevices"
                       :key="device.id"
                       class="checkbox-item">
                  <input type="checkbox"
                         :value="device.id"
                         v-model="selectedDevices">
                  <span>{{ device.name }} (通道 {{ device.channelIndex }}) [{{ device.deviceType === 'dry' ? '干声' : device.deviceType === 'noise' ? '噪声' : device.deviceType || '未知' }}]</span>
                </label>
              </div>
            </div>
            <div v-if="Array.isArray(filteredScanDevices) && filteredScanDevices.length > 0" class="device-group">
              <h5>可用播放设备</h5>
              <div class="checkbox-group">
                <label v-for="device in filteredScanDevices"
                       :key="device.id"
                       class="checkbox-item">
                  <input type="checkbox"
                         :value="device.id"
                         v-model="selectedDevices">
                  <span>{{ device.name }} (通道 {{ device.channelIndex }}) [{{ device.deviceType === 'dry' ? '干声' : device.deviceType === 'noise' ? '噪声' : device.deviceType || '未知' }}]</span>
                </label>
              </div>
            </div>
          </div>

          <div v-if="(audioType === 'dry' && filteredDryDevices.length === 0 && filteredScanDevices.length === 0) ||
                    (audioType === 'noise' && playbackDevices.length === 0 && filteredScanDevices.length === 0)"
               class="empty-state">
            <i class="fas fa-headphones"></i>
            <p>暂无可用的播放设备</p>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="handleClose">取消</button>
          <button type="button" class="btn btn-primary" @click="handleConfirm" :disabled="!isFormValid">
            <i class="fas fa-check"></i> 确认选择
          </button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { playbackApi } from '../../../utils/api'

const props = defineProps({
  visible: { type: Boolean, default: false },
  title: { type: String, default: '选择播放设备' },
  isMultiSelect: { type: Boolean, default: false },
  initialSelectedDevices: { type: Array, default: () => [] },
  playbackDevices: { type: Array, default: () => [] },
  audioType: { type: String, default: 'dry' },
  showScanDevices: { type: Boolean, default: true }, // 是否显示扫描设备
  isRequired: { type: Boolean, default: false } // 是否必选
})

const emit = defineEmits(['close', 'confirm'])

const scanDevices = ref([])
const isScanning = ref(false)
const scanError = ref('')
const selectedDevices = ref([...props.initialSelectedDevices])
const selectedDevice = ref(props.initialSelectedDevices.length > 0 ? props.initialSelectedDevices[0] : '')

const filteredDryDevices = computed(() => {
  const devices = Array.isArray(props.playbackDevices) ? props.playbackDevices : []
  return devices
})

const actualMultiSelect = computed(() => {
  if (props.audioType === 'noise') {
    return true
  }
  if (props.audioType === 'dry') {
    return false
  }
  return props.isMultiSelect
})

const isFormValid = computed(() => {
  if (props.audioType === 'dry') {
    return !!selectedDevice.value
  } else if (props.audioType === 'noise') {
    if (props.isRequired) {
      return selectedDevices.value.length > 0
    }
    return true
  }
  return false
})

watch(() => props.visible, async (newValue) => {
  if (newValue) {
    resetForm()
    await scanAvailableDevices()
  }
})

watch(() => props.initialSelectedDevices, (newValue) => {
  selectedDevices.value = [...newValue]
}, { deep: true })

const scanAvailableDevices = async () => {
  isScanning.value = true
  scanError.value = ''
  
  try {
    const devices = await playbackApi.scan()
    scanDevices.value = devices || []
  } catch (error) {
    console.error('扫描设备失败:', error)
    scanError.value = '扫描设备失败，请重试'
    scanDevices.value = []
  } finally {
    isScanning.value = false
  }
}

const filteredScanDevices = computed(() => {
  const devices = Array.isArray(props.playbackDevices) ? props.playbackDevices : []
  const dbDeviceKeys = new Set(devices.map(device => `${device.name}|${device.channelIndex}`))

  return scanDevices.value
    .filter(scanDevice => {
      const scanDeviceKey = `${scanDevice.name}|${scanDevice.channelIndex}`
      return !dbDeviceKeys.has(scanDeviceKey)
    })
    .map(scanDevice => ({
      ...scanDevice,
      id: `${scanDevice.deviceUniqueId}_${scanDevice.channelIndex}`
    }))
})

const resetForm = () => {
  selectedDevices.value = [...props.initialSelectedDevices]
  selectedDevice.value = props.initialSelectedDevices.length > 0 ? props.initialSelectedDevices[0] : ''
}

const handleClose = () => {
  emit('close')
}

const handleKeyDown = (event) => {
  if (event.key === 'Escape' && props.visible) {
    handleClose()
  }
}

watch(() => props.visible, (newVal) => {
  if (newVal) {
    window.addEventListener('keydown', handleKeyDown)
  } else {
    window.removeEventListener('keydown', handleKeyDown)
  }
}, { immediate: true })

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown)
})

const handleConfirm = () => {
  let result = []
  if (props.audioType === 'dry') {
    if (selectedDevice.value) {
      result = [selectedDevice.value]
    }
  } else {
    result = selectedDevices.value
  }
  emit('confirm', result)
  handleClose()
}
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
  z-index: 13002;
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
  max-width: 700px;
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

.scan-status-container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  gap: 12px;
  flex-wrap: wrap;
}

.scan-status {
  flex: 1;
  padding: 12px;
  border-radius: 6px;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.scan-actions {
  display: flex;
  align-items: center;
}

.btn-sm {
  padding: 6px 12px;
  font-size: 12px;
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

.checkbox-item input[type="checkbox"]:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.checkbox-item span {
  margin: 0;
  cursor: pointer;
  font-weight: 400;
  word-break: break-word;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: #6c757d;
}

.empty-state i {
  font-size: 48px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.empty-state p {
  margin: 0;
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

.form-control {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ced4da;
  border-radius: 6px;
  font-size: 14px;
  box-sizing: border-box;
}

.required {
  color: #dc3545;
}
</style>
