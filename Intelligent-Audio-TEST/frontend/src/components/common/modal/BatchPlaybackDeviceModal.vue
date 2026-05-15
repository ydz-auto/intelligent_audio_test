<template>
  <div class="batch-playback-device-modal">
    <div class="modal-header">
      <h3>{{ title }}</h3>
      <p class="case-count">将为 {{ caseCount }} 个用例设置播放设备</p>
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

      <div class="form-group">
        <label>播放设备 <span class="required">*</span></label>
        <select v-model="selectedDevice" class="form-input custom-select" required>
          <option value="">请选择设备</option>
          <option v-for="device in allDevices" 
                  :key="device.id" 
                  :value="device.id">
            {{ device.name }} (通道 {{ device.channelIndex }}) [{{ device.deviceType === 'dry' ? '干声' : device.deviceType === 'noise' ? '噪声' : device.deviceType || '未知' }}]
          </option>
        </select>
      </div>
      
      <div v-if="allDevices.length === 0 && !isScanning" class="empty-state">
        <i class="fas fa-headphones"></i>
        <p>暂无可用的播放设备</p>
      </div>
    </div>
    
    <div class="modal-footer">
      <button type="button" class="btn btn-secondary" @click="handleCancel">取消</button>
      <button type="button" class="btn btn-primary" @click="handleConfirm" :disabled="!selectedDevice">
        确定
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { playbackApi } from '../../../utils/api'

interface Props {
  modalId: string
  title?: string
  caseCount?: number
}

interface Emits {
  (e: 'close'): void
  (e: 'confirm', data: { deviceId: string }): void
  (e: 'cancel'): void
}

const props = withDefaults(defineProps<Props>(), {
  title: '批量设置播放设备',
  caseCount: 0
})

const emit = defineEmits<Emits>()

const allDevices = ref<any[]>([])
const isScanning = ref(false)
const scanError = ref('')
const selectedDevice = ref('')

const allDevicesComputed = computed(() => {
  return allDevices.value
})

async function loadDevices() {
  try {
    const result = await playbackApi.getAll()
    allDevices.value = (result as any).items || []
  } catch (error) {
    console.error('加载播放设备列表失败:', error)
    allDevices.value = []
  }
}

async function scanAvailableDevices() {
  isScanning.value = true
  scanError.value = ''
  
  try {
    const devices = await playbackApi.scan()
    const scannedDevices = devices || []
    
    const existingKeys = new Set(allDevices.value.map(d => `${d.name}|${d.channelIndex}`))
    const newDevices = scannedDevices.filter((d: any) => !existingKeys.has(`${d.name}|${d.channelIndex}`))
    
    allDevices.value = [...allDevices.value, ...newDevices]
  } catch (error) {
    console.error('扫描设备失败:', error)
    scanError.value = '扫描设备失败，请重试'
  } finally {
    isScanning.value = false
  }
}

function handleConfirm() {
  if (!selectedDevice.value) {
    return
  }
  emit('confirm', {
    deviceId: selectedDevice.value
  })
}

function handleCancel() {
  emit('cancel')
}

onMounted(async () => {
  await loadDevices()
  await scanAvailableDevices()
})
</script>

<style scoped>
.batch-playback-device-modal {
  padding: 20px;
}

.modal-header {
  margin-bottom: 20px;
}

.modal-header h3 {
  margin: 0 0 8px 0;
  font-size: 18px;
  color: #333;
}

.case-count {
  margin: 0;
  color: #666;
  font-size: 14px;
}

.modal-body {
  max-height: 400px;
  overflow-y: auto;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-weight: 500;
  color: #333;
}

.required {
  color: #dc3545;
}

.form-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
}

.form-input:focus {
  outline: none;
  border-color: #1677ff;
  box-shadow: 0 0 0 2px rgba(22, 119, 255, 0.1);
}

.scan-status-container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 8px;
  background: #f5f5f5;
  border-radius: 4px;
}

.scan-status-scanning {
  color: #1677ff;
}

.scan-status-error {
  color: #dc3545;
}

.scan-status-scanning i,
.scan-status-error i {
  margin-right: 8px;
}

.empty-state {
  padding: 30px;
  text-align: center;
  color: #999;
}

.empty-state i {
  font-size: 32px;
  margin-bottom: 10px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #eee;
}

.btn {
  padding: 8px 20px;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  border: none;
}

.btn-secondary {
  background: #f5f5f5;
  color: #333;
}

.btn-secondary:hover {
  background: #e8e8e8;
}

.btn-primary {
  background: #1677ff;
  color: #fff;
}

.btn-primary:hover {
  background: #4096ff;
}

.btn-primary:disabled {
  background: #ccc;
  cursor: not-allowed;
}

.btn-sm {
  padding: 4px 12px;
  font-size: 12px;
}
</style>
