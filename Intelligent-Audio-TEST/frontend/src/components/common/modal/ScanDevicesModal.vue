<template>
  <div class="scan-devices-modal">
    <div v-if="isScanning" class="scan-progress">
      <div class="progress-bar-container">
        <div class="progress-bar" :style="{ width: scanProgress + '%' }"></div>
      </div>
      <div class="progress-text">{{ scanProgress }}% - {{ scanStatus }}</div>
    </div>
    
    <div class="scan-results">
      <h4>扫描结果</h4>
      <div class="scan-devices-list">
        <div v-if="deviceType === 'test'" class="scan-device-type-section">
          <h5>测试设备 (通过 ADB/HDC 命令扫描)</h5>
          <div v-if="scanResults.length > 0" class="serial-numbers-list">
            <div v-for="device in scanResults" 
                 :key="device.serial || device.id" 
                 class="scan-device-item">
              <div class="scan-device-info">
                <h5>{{ device.name || '未命名设备' }}</h5>
                <p>
                  {{ device.system || '未知系统' }} - {{ device.serial || '无序列号' }}
                </p>
                <p v-if="device.ip">
                  IP{{ device.ip }}
                </p>
              </div>
              <div class="scan-device-actions">
                <button class="btn btn-primary" @click="handleAddDevice($event, device)">
                  <i class="fas fa-plus"></i>
                  添加
                </button>
              </div>
            </div>
          </div>
        </div>
        
        <div v-else-if="deviceType === 'playback'" class="scan-device-type-section">
          <h5>播放设备 (系统音频通道)</h5>
          <div v-if="scanResults.length > 0" class="audio-channels-list">
            <div v-for="device in scanResults" 
                 :key="(device.deviceUniqueId || '') + '_' + (device.channelIndex || 0)" 
                 class="scan-device-item">
              <div class="scan-device-info">
                <h5>{{ device.name }}</h5>
                <p>通道索引{{ device.channelIndex || 0 }}</p>
                <p>采样率{{ device.sampleRate || 48000 }} Hz</p>
              </div>
              <div class="scan-device-actions">
                <button class="btn btn-primary" @click="handleAddDevice($event, device)">
                  <i class="fas fa-plus"></i>
                  添加
                </button>
              </div>
            </div>
          </div>
        </div>
        
        <div v-else-if="deviceType === 'api'" class="scan-device-type-section">
          <h5>API 服务</h5>
          <div class="no-results">
            <p>API 暂不支持自动扫描，请手动添加</p>
          </div>
        </div>

        <div v-if="deviceType !== 'api' && scanResults.length === 0 && !isScanning" class="no-results">
          <p>未扫描到任何设备</p>
          <p>请确保 ADB 设备已连接，或选择正确的设备类型</p>
        </div>
      </div>
      
      <div v-if="deviceType !== 'api'" class="scan-actions">
        <button 
          class="btn btn-secondary" 
          @click="startScan" 
          :disabled="isScanning"
        >
          <i class="fas fa-sync-alt"></i>
          {{ isScanning ? '扫描中...' : '开始扫描' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/components/modal.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/progress.css'
import '../../../assets/styles/components/tag.css'
import '../../../assets/styles/components/log.css'

import { ref, onMounted, onUnmounted } from 'vue'
import { devicesPort } from '../../../composables/device/devicesPort'
import { playbackPort } from '../../../composables/device/playbackPort'
import type { ScannedDevice } from '../../../domain/model/device'

const props = defineProps({
  visible: { type: Boolean, default: false },
  title: { type: String, default: '扫描设备' },
  deviceType: { type: String, default: 'test' },
  options: { type: Object, default: () => ({}) },
  modalId: { type: String, default: '' },
  onConfirm: { type: [Function, Array], default: null },
  onClose: { type: [Function, Array], default: null },
  autoStartScan: { type: Boolean, default: false }
})

const emit = defineEmits(['close', 'confirm'])

const isScanning = ref(false)
const scanProgress = ref(0)
const scanStatus = ref('准备扫描')
const scanResults = ref<ScannedDevice[]>([])

let isProcessingAddDevice = false

const handleAddDevice = (event: Event, device: ScannedDevice) => {
  event.stopPropagation()
  event.preventDefault()

  if (isProcessingAddDevice) return

  isProcessingAddDevice = true
  emit('confirm', device)

  setTimeout(() => {
    isProcessingAddDevice = false
  }, 3000)
}

const startScan = async () => {
  if (isScanning.value) return

  isScanning.value = true
  scanProgress.value = 0
  scanStatus.value = '正在初始化扫描...'
  scanResults.value = []

  try {
    let devices: ScannedDevice[] = []

    if (props.deviceType === 'test') {
      scanStatus.value = '正在扫描测试设备...'
      // devicesPort.scan 已通过 adapter 返回 ScannedDevice[]（camelCase）；扫描为空/失败不注入模拟数据
      devices = await devicesPort.scan()
    } else if (props.deviceType === 'playback') {
      scanStatus.value = '正在获取系统音频设备...'
      devices = await playbackPort.scan()
    } else {
      // API 页签：功能口径照 React（16_设备域.md §6.1 / §11-11）——后端无 API 自动扫描数据源，仅手动添加
      scanStatus.value = '正在扫描 API 服务...'
    }

    scanProgress.value = 50

    // DTO → Domain 归一化已由 infrastructure adapter 完成（deviceAdapter），组件只消费 Domain 对象
    scanResults.value = devices

    scanProgress.value = 100
    scanStatus.value = '扫描完成'
  } catch (error) {
    console.error('扫描设备失败:', error)
    scanStatus.value = '扫描失败: ' + (error instanceof Error ? error.message : '未知错误')
  } finally {
    setTimeout(() => {
      isScanning.value = false
    }, 2000)
  }
}

onMounted(() => {
  if (props.autoStartScan && props.deviceType !== 'api') {
    startScan()
  }
})

onUnmounted(() => {
  if (typeof props.onClose === 'function') {
    props.onClose()
  }
})
</script>


<style scoped>
.scan-devices-modal {
  padding: 20px;
}

.scan-progress {
  margin-bottom: 20px;
  padding: 15px;
  background: var(--muted);
  border-radius: var(--radius-control);
}

.progress-bar-container {
  height: 8px;
  background: var(--border);
  border-radius: var(--radius-tag);
  overflow: hidden;
  margin-bottom: 10px;
}

.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, var(--success), var(--success-dark));
  transition: width 0.3s ease;
}

.progress-text {
  text-align: center;
  color: var(--color-gray-500);
  font-size: 14px;
}

.scan-results h4 {
  margin-bottom: 15px;
  color: var(--foreground);
}

.scan-device-type-section {
  margin-bottom: 20px;
}

.scan-device-type-section h5 {
  margin-bottom: 10px;
  color: var(--color-gray-500);
  font-size: 14px;
}

.scan-devices-list {
  max-height: 400px;
  overflow-y: auto;
}

.serial-numbers-list,
.audio-channels-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.scan-device-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 15px;
  background: var(--color-neutral-50);
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  transition: all 0.2s ease;
}

.scan-device-item:hover {
  background: var(--gray-light);
  border-color: var(--secondary);
}

.scan-device-info {
  flex: 1;
}

.scan-device-info h5 {
  margin: 0 0 5px 0;
  color: var(--foreground);
  font-size: 15px;
}

.scan-device-info p {
  margin: 3px 0;
  color: var(--color-gray-500);
  font-size: 13px;
}

.scan-device-actions {
  margin-left: 15px;
}

.no-results {
  text-align: center;
  padding: 30px;
  color: var(--color-gray-400);
}

.no-results p {
  margin: 5px 0;
}

.scan-actions {
  margin-top: 20px;
  text-align: center;
}

.btn {
  padding: 8px 16px;
  border: none;
  border-radius: var(--radius-control);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.btn-primary {
  background-color: var(--color-blue-500);
  color: white;
}

.btn-primary:hover {
  background-color: var(--color-blue-600);
}

.btn-secondary {
  background-color: var(--muted);
  color: var(--color-slate-500);
  border: 1px solid var(--color-slate-200);
}

.btn-secondary:hover {
    background-color: transparent;
    color: var(--primary);
    border-color: var(--primary);
  }

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

@media (max-width: 768px) {
  .scan-device-item {
    flex-direction: column;
    align-items: flex-start;
  }
  
  .scan-device-actions {
    margin-left: 0;
    margin-top: 10px;
    width: 100%;
  }
  
  .scan-device-actions button {
    width: 100%;
  }
}
</style>
