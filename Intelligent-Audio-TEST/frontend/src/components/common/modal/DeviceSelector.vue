<template>
  <div class="device-selector-section">
    <div class="device-selector-header">
      <span class="device-selector-title">选择设备</span>
      <button 
        type="button" 
        class="btn-scan" 
        @click="$emit('rescan')"
        :disabled="isScanning"
      >
        <span v-if="isScanning" class="scanning-spinner"></span>
        {{ isScanning ? '扫描中...' : '重新扫描' }}
      </button>
    </div>
    
    <div v-if="displayDevices.length > 0" class="device-list">
      <div 
        v-for="device in displayDevices" 
        :key="device.displayKey"
        class="device-item"
        :class="{ 
          active: selectedDeviceId === device.displayKey,
          current: device.isCurrent,
          added: device.isAdded
        }"
        @click="$emit('select', device)"
      >
        <div class="device-icon">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
            <line x1="8" y1="21" x2="16" y2="21"></line>
            <line x1="12" y1="17" x2="12" y2="21"></line>
          </svg>
        </div>
        <div class="device-info">
          <div class="device-name">{{ device.name || '未知设备' }}</div>
          <div class="device-details">
            <span class="device-model" v-if="device.model">{{ device.model }}</span>
            <span class="device-id">{{ device.displayKey }}</span>
          </div>
        </div>
        <div v-if="device.isCurrent" class="current-badge">
          当前设备
        </div>
        <div v-else-if="device.isAdded" class="added-badge">
          已添加
        </div>
        <div v-else-if="selectedDeviceId === device.displayKey" class="select-badge">
          已选择
        </div>
      </div>
    </div>
    
    <div v-else-if="isScanning" class="scanning-message">
      <span class="scanning-spinner"></span>
      正在扫描设备...
    </div>
    
    <div v-else class="no-devices-message">
      未扫描到设备，请点击"重新扫描"
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  isScanning: { type: Boolean, default: false },
  displayDevices: { type: Array, default: () => [] },
  selectedDeviceId: { type: [String, Number], default: null }
})

defineEmits(['select', 'rescan'])
</script>

<style scoped>
.device-selector-section {
  background-color: #f8f9fa;
  padding: 20px;
  border-radius: 8px;
  margin-bottom: 24px;
  border: 1px solid #e9ecef;
}

.device-selector-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.device-selector-title {
  font-size: 16px;
  font-weight: 600;
  color: #343a40;
}

.btn-scan {
  background-color: #007bff;
  color: white;
  border: 1px solid transparent;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s ease;
}

.btn-scan:hover:not(:disabled) {
  background-color: transparent;
  color: var(--primary-color);
  border: 1px solid var(--primary-color);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(255, 106, 0, 0.3);
}

.btn-scan:disabled {
  background-color: #e9ecef;
  cursor: not-allowed;
  opacity: 0.65;
  transform: none;
  box-shadow: none;
}

.scanning-spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-radius: 50%;
  border-top-color: #fff;
  animation: spin 1s ease-in-out infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.device-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 300px;
  overflow-y: auto;
  padding-right: 8px;
}

.device-list::-webkit-scrollbar {
  width: 6px;
}

.device-list::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 3px;
}

.device-list::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 3px;
}

.device-list::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}

.device-item {
  background-color: white;
  padding: 16px;
  border-radius: 6px;
  border: 1px solid #e9ecef;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 16px;
}

.device-item:hover {
  border-color: var(--primary-color);
  box-shadow: 0 2px 8px rgba(255, 106, 0, 0.2);
  transform: translateY(-1px);
}

.device-item.active {
  border: 2px solid var(--primary-color);
  background-color: rgba(255, 106, 0, 0.2);
  box-shadow: 0 0 0 3px rgba(255, 106, 0, 0.3), 0 4px 12px rgba(255, 106, 0, 0.25);
  transform: translateY(-2px);
  z-index: 10;
}

.device-item.current {
  border: 2px solid var(--success-color);
  background-color: rgba(82, 196, 26, 0.2);
  box-shadow: 0 0 0 3px rgba(82, 196, 26, 0.3);
}

.device-item.added {
  border: 1px solid var(--border-color);
  background-color: rgba(108, 117, 125, 0.05);
}

.device-item.added.active {
  border: 2px solid var(--primary-color);
  background-color: rgba(255, 106, 0, 0.25);
  box-shadow: 0 0 0 3px rgba(255, 106, 0, 0.3), 0 4px 12px rgba(255, 106, 0, 0.25);
  transform: translateY(-2px);
}

.device-icon {
  color: #007bff;
}

.device-info {
  flex: 1;
}

.device-name {
  font-weight: 600;
  color: #343a40;
  margin-bottom: 4px;
}

.device-details {
  font-size: 14px;
  color: #6c757d;
}

.device-model {
  margin-right: 12px;
}

.current-badge {
  background-color: #28a745;
  color: white;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.added-badge {
  background-color: #6c757d;
  color: white;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.select-badge {
  background-color: var(--primary-color);
  color: white;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  box-shadow: 0 2px 4px rgba(255, 106, 0, 0.2);
}

.scanning-message {
  text-align: center;
  padding: 24px;
  color: #6c757d;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.no-devices-message {
  text-align: center;
  padding: 24px;
  color: #6c757d;
  background-color: white;
  border-radius: 6px;
  border: 1px dashed #dee2e6;
}
</style>
