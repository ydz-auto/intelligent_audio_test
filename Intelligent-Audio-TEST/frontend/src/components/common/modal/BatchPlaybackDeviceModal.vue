<template>
  <div class="batch-playback-device-modal">
    <div class="modal-header">
      <h3>{{ title }}</h3>
      <p class="case-count">{{ selectionMode === 'selected' ? '您勾选了' : '将对' }} {{ caseCount }} 个用例设置播放设备</p>
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

      <div class="scope-section">
        <label>轮次范围</label>
        <div class="radio-group">
          <label class="radio-label">
            <input type="radio" :value="'all'" v-model="roundMode" />
            <span>所有轮次</span>
          </label>
          <label class="radio-label">
            <input type="radio" :value="'specific'" v-model="roundMode" />
            <span>指定轮次</span>
          </label>
        </div>
        <div class="round-checkboxs" v-if="roundMode === 'specific'">
          <label v-for="rn in availableRoundNumbers" :key="rn"
                 :class="{ checked: roundNumbers.includes(rn) }"
                 @click="toggleRoundNumber(rn)">
            第{{ rn }}轮
          </label>
        </div>
      </div>

      <div class="scope-section">
        <label>应用层级（可多选）</label>
        <div class="level-checkboxs">
          <label class="level-label">
            <input type="checkbox" value="audio" v-model="targets" />
            <span>目标人音频</span>
          </label>
          <label class="level-label">
            <input type="checkbox" value="caseBackgroundNoise" v-model="targets" />
            <span>case级背景噪声</span>
          </label>
          <label class="level-label">
            <input type="checkbox" value="segmentBackgroundNoise" v-model="targets" />
            <span>segment级背景噪声</span>
          </label>
          <label class="level-label">
            <input type="checkbox" value="interferer" v-model="targets" />
            <span>干扰人</span>
          </label>
          <label class="level-label">
            <input type="checkbox" value="voiceprint" v-model="targets" />
            <span>声纹</span>
          </label>
        </div>
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
import { playbackPort } from '../../../composables/device/playbackPort'

interface Props {
  modalId: string
  title?: string
  caseCount?: number
  maxRoundNumbers?: number
  selectionMode?: string
}

interface Emits {
  (e: 'close'): void
  (e: 'confirm', data: { deviceId: string; targets: string[]; roundMode: string; roundNumbers: number[] }): void
  (e: 'cancel'): void
}

const props = withDefaults(defineProps<Props>(), {
  title: '批量设置播放设备',
  caseCount: 0,
  maxRoundNumbers: 3,
  selectionMode: 'all'
})

const emit = defineEmits<Emits>()

const allDevices = ref<any[]>([])
const isScanning = ref(false)
const scanError = ref('')
const selectedDevice = ref('')
const roundMode = ref<'all' | 'specific'>('all')
const roundNumbers = ref<number[]>([])
const targets = ref<string[]>(['audio'])

const availableRoundNumbers = computed(() => {
  return Array.from({ length: props.maxRoundNumbers }, (_, i) => i + 1)
})

function toggleRoundNumber(rn: number) {
  const idx = roundNumbers.value.indexOf(rn)
  if (idx >= 0) {
    roundNumbers.value.splice(idx, 1)
  } else {
    roundNumbers.value.push(rn)
  }
}

const allDevicesComputed = computed(() => {
  return allDevices.value
})

async function loadDevices() {
  try {
    // playbackPort.getAll 已展平为 Domain 数组
    allDevices.value = await playbackPort.getAll()
  } catch (error) {
    console.error('加载播放设备列表失败:', error)
    allDevices.value = []
  }
}

async function scanAvailableDevices() {
  isScanning.value = true
  scanError.value = ''
  
  try {
    const devices = await playbackPort.scan()
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
    deviceId: selectedDevice.value,
    targets: targets.value,
    roundMode: roundMode.value,
    roundNumbers: roundNumbers.value
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

.modal-header h3 {
  margin: 0 0 8px 0;
  font-size: 18px;
  color: var(--foreground);
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
  color: var(--foreground);
}

.required {
  color: var(--destructive);
}

.form-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--color-gray-300);
  border-radius: 4px;
  font-size: 14px;
}

.form-input:focus {
  outline: none;
  border-color: var(--secondary);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--secondary) 10%, transparent);
}

.scan-status-container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 8px;
  background: var(--muted);
  border-radius: 4px;
}

.scan-status-scanning {
  color: var(--secondary);
}

.scan-status-error {
  color: var(--destructive);
}

.scan-status-scanning i,
.scan-status-error i {
  margin-right: 8px;
}

.empty-state {
  padding: 30px;
  text-align: center;
  color: var(--color-gray-400);
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
  border-top: 1px solid var(--color-gray-200);
}

.btn {
  padding: 8px 20px;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  border: none;
}

.btn-secondary {
  background: var(--muted);
  color: var(--foreground);
}

.btn-primary {
  background: var(--secondary);
  color: var(--background);
}

.btn-primary:disabled {
  background: var(--color-gray-300);
  cursor: not-allowed;
}

.btn-sm {
  padding: 4px 12px;
  font-size: 12px;
}
.radio-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
}
.radio-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  cursor: pointer;
}
</style>
