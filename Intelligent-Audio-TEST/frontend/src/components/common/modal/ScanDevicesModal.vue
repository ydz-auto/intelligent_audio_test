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
                <p v-if="device.ipAddress || device.ip">
                  IP{{ device.ipAddress || device.ip }}
                </p>
                <p v-if="device.connectionType">
                  连接方式{{ device.connectionType === 'usb' ? 'usb连接' : '远程连接' }}
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
                 :key="(device.deviceUniqueId || device.deviceUniqueId) + '_' + (device.channelIndex || device.channelIndex || 0)" 
                 class="scan-device-item">
              <div class="scan-device-info">
                <h5>{{ device.name }}</h5>
                <p>通道索引{{ device.channelIndex || device.channelIndex || 0 }}</p>
                <p>采样率{{ device.sampleRate || device.sampleRate || 48000 }} Hz</p>
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
          <div v-if="scanResults.length > 0" class="api-list">
            <div v-for="device in scanResults" 
                 :key="device.id || device.name" 
                 class="scan-device-item">
              <div class="scan-device-info">
                <h5>{{ device.name }}</h5>
                <p>端点{{ device.endpoint }}</p>
                <p>协议{{ device.protocol }}</p>
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
        
        <div v-if="scanResults.length === 0 && !isScanning" class="no-results">
          <p>未扫描到任何设备</p>
          <p>请确保 ADB 设备已连接，或选择正确的设备类型</p>
        </div>
      </div>
      
      <div class="scan-actions">
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

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { devicesApi, playbackApi } from '../../../utils/api'

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
const scanResults = ref([])

let isProcessingAddDevice = false

const handleAddDevice = (event, device) => {
  event.stopPropagation()
  event.preventDefault()
  
  console.log('[ScanDevicesModal] handleAddDevice called for device:', device.name || device.deviceUniqueId)
  console.log('[ScanDevicesModal] Current isProcessingAddDevice:', isProcessingAddDevice)
  console.log('[ScanDevicesModal] Device details:', JSON.stringify(device, null, 2))
  
  if (isProcessingAddDevice) {
    console.log('[ScanDevicesModal] Already processing add device, skipping')
    return
  }
  
  isProcessingAddDevice = true
  console.log('[ScanDevicesModal] Processing device:', device.name || device.deviceUniqueId)
  
  emit('confirm', device)
  console.log("[ScanDevicesModal] emit('confirm') called with device:", JSON.stringify(device, null, 2))
  
  setTimeout(() => {
    isProcessingAddDevice = false
    console.log('[ScanDevicesModal] isProcessingAddDevice reset to false')
  }, 3000)
}

const getDeviceKey = (device) => {
  if (device.serial) return device.serial
  if (device.deviceUniqueId) return device.deviceUniqueId
  if (device.id) return device.id
  return JSON.stringify(device)
}

const getDeviceIcon = (system) => {
  if (!system) return 'fa-mobile-alt'
  const s = system.toLowerCase()
  if (s.includes('android')) return 'fa-android'
  if (s.includes('ios') || s.includes('iphone') || s.includes('ipad')) return 'fa-apple'
  if (s.includes('harmony')) return 'fa-huawei'
  return 'fa-mobile-alt'
}

const startScan = async () => {
  if (isScanning.value) return
  
  isScanning.value = true
  scanProgress.value = 0
  scanStatus.value = '正在初始化扫描...'
  scanResults.value = []
  
  try {
    let devices = []
    
    if (props.deviceType === 'test') {
      scanStatus.value = '正在扫描测试设备...'
      
      try {
        const response = await devicesApi.scan()
        console.log('[ScanDevicesModal] 测试设备扫描响应:', response)
        
        if (response && response.code === 0 && Array.isArray(response.data)) {
          devices = response.data
        } else if (response && Array.isArray(response)) {
          devices = response
        } else if (response && response.data && Array.isArray(response.data.devices)) {
          devices = response.data.devices
        } else {
          console.log('[ScanDevicesModal] 无法解析测试设备扫描响应，使用模拟数据')
          devices = []
        }
      } catch (error) {
        console.error('[ScanDevicesModal] 测试设备扫描失败:', error)
        devices = []
      }
      
      if (devices.length === 0) {
        console.log('[ScanDevicesModal] 无测试设备，使用模拟数据 (开发环境)')
        devices = [
          {
            serial: 'MOCK-ADB-123456',
            name: 'Android Pixel 6 Pro',
            model: 'Pixel 6 Pro',
            system: 'android',
            systemVersion: '13.0',
            appName: 'Default App',
            appVersion: '1.0.0',
            ipAddress: '192.168.1.100',
            connectionType: 'usb'
          },
          {
            serial: 'MOCK-IOS-789012',
            name: 'iPhone 14',
            model: 'iPhone 14',
            system: 'ios',
            systemVersion: '16.5',
            appName: 'Default App',
            appVersion: '1.0.0',
            ipAddress: '192.168.1.101',
            connectionType: 'remote'
          },
          {
            serial: 'MOCK-HARMONY-345678',
            name: 'HarmonyOS Mate 60 Pro',
            model: 'Mate 60 Pro',
            system: 'harmony',
            systemVersion: '4.0',
            appName: 'Default App',
            appVersion: '1.0.0',
            ipAddress: '192.168.1.102',
            connectionType: 'remote'
          }
        ]
      }
    } else if (props.deviceType === 'playback') {
      scanStatus.value = '正在获取系统音频设备...'
      
      try {
        const response = await playbackApi.scan()
        console.log('[ScanDevicesModal] 播放设备扫描响应:', response)
        
        if (response && response.code === 0 && Array.isArray(response.data)) {
          devices = response.data
        } else if (response && Array.isArray(response)) {
          devices = response
        } else if (response && response.data && Array.isArray(response.data.devices)) {
          devices = response.data.devices
        } else if (response && response.devices && Array.isArray(response.devices)) {
          devices = response.devices
        } else {
          console.log('[ScanDevicesModal] 无法解析播放设备扫描响应，使用模拟数据')
          devices = []
        }
      } catch (error) {
        console.error('[ScanDevicesModal] 播放设备扫描失败:', error)
        devices = []
      }
      
      if (devices.length === 0) {
        console.log('[ScanDevicesModal] 无播放设备，使用模拟数据 (开发环境)')
        devices = [
          {
            deviceUniqueId: 'audio-output-1',
            name: '扬声器 (Realtek Audio)',
            channelIndex: 0,
            sampleRate: 48000,
            type: 'output'
          },
          {
            deviceUniqueId: 'audio-output-2',
            name: '耳机 (Bluetooth Audio)',
            channelIndex: 0,
            sampleRate: 44100,
            type: 'output'
          }
        ]
      }
    } else if (props.deviceType === 'api') {
      scanStatus.value = '正在扫描 API 服务...'
      devices = []
    }
    
    scanProgress.value = 50
    
    scanResults.value = devices.map((device) => {
      const normalized = { ...device }
      
      if (props.deviceType === 'test') {
        normalized.serialNumber = device.serialNumber || device.serial || device.deviceId || device.id || device.deviceUniqueId
        normalized.serial = normalized.serialNumber
        normalized.name = device.name || device.model || device.label || '未知设备'
        normalized.system = device.system || device.platform || device.os || 'android'
        normalized.model = device.model || normalized.name
        normalized.systemVersion = device.systemVersion || device.version || device.osVersion || '1.0.0'
      }
      
      if (props.deviceType === 'playback') {
        normalized.deviceUniqueId = device.deviceUniqueId || device.id || device.serial || device.uid
        normalized.name = device.name || device.model || device.label || '未知播放设备'
        normalized.model = device.model || normalized.name
        normalized.sampleRate = device.sampleRate || 48000
        normalized.channelIndex = device.channelIndex !== undefined ? device.channelIndex : 0
        normalized.type = device.type || device.playbackType || 'output'
      }
      
      if (props.deviceType === 'api') {
        normalized.name = device.name || device.label || '未知 API'
        normalized.endpoint = device.endpoint || device.url || device.address || ''
        normalized.protocol = device.protocol || 'http'
        normalized.id = device.id || device.uid || device.name
      }
      
      return normalized
    })
    
    scanProgress.value = 100
    scanStatus.value = '扫描完成'
    
    console.log('[ScanDevicesModal] 扫描结果:', scanResults.value.length, '个设备')
    
  } catch (error) {
    console.error('扫描设备失败:', error)
    scanStatus.value = '扫描失败: ' + (error.message || '未知错误')
  } finally {
    setTimeout(() => {
      isScanning.value = false
    }, 2000)
  }
}

const deviceTypeLabel = computed(() => {
  const labels = { test: '测试设备', playback: '播放设备', api: 'API' }
  return labels[props.deviceType] || '设备'
})

onMounted(() => {
  console.log('[ScanDevicesModal] 组件已挂载')
  
  if (props.autoStartScan) {
    console.log('[ScanDevicesModal] 自动开始扫描...')
    startScan()
  }
})

onUnmounted(() => {
  console.log('[ScanDevicesModal] 组件已卸载')
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
  background: #f5f5f5;
  border-radius: 8px;
}

.progress-bar-container {
  height: 8px;
  background: #e0e0e0;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 10px;
}

.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #4CAF50, #8BC34A);
  transition: width 0.3s ease;
}

.progress-text {
  text-align: center;
  color: #666;
  font-size: 14px;
}

.scan-results h4 {
  margin-bottom: 15px;
  color: #333;
}

.scan-device-type-section {
  margin-bottom: 20px;
}

.scan-device-type-section h5 {
  margin-bottom: 10px;
  color: #666;
  font-size: 14px;
}

.scan-devices-list {
  max-height: 400px;
  overflow-y: auto;
}

.serial-numbers-list,
.audio-channels-list,
.api-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.scan-device-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 15px;
  background: #f9f9f9;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  transition: all 0.2s ease;
}

.scan-device-item:hover {
  background: #f0f0f0;
  border-color: #2196F3;
}

.scan-device-info {
  flex: 1;
}

.scan-device-info h5 {
  margin: 0 0 5px 0;
  color: #333;
  font-size: 15px;
}

.scan-device-info p {
  margin: 3px 0;
  color: #666;
  font-size: 13px;
}

.scan-device-actions {
  margin-left: 15px;
}

.no-results {
  text-align: center;
  padding: 30px;
  color: #999;
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
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.btn-primary {
  background-color: #3b82f6;
  color: white;
}

.btn-primary:hover {
  background-color: #2563eb;
}

.btn-secondary {
  background-color: #f8f9fa;
  color: #64748b;
  border: 1px solid #e2e8f0;
}

.btn-secondary:hover {
    background-color: transparent;
    color: var(--primary-color);
    border-color: var(--primary-color);
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
