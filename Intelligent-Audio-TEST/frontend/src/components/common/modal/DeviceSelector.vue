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

.device-details{
    font-size: 14px;
    color: var(--text-secondary);
}




.device-selector-section{
  background-color: var(--muted);
  padding: 20px;
  border-radius: 8px;
  margin-bottom: 24px;
  border: 1px solid var(--muted);
}

.device-selector-header{
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.device-selector-title{
  font-size: 16px;
  font-weight: 600;
  color: var(--foreground);
}

.btn-scan{
  background-color: var(--secondary);
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

.btn-scan:hover:not(:disabled){
  background-color: transparent;
  color: var(--primary-color);
  border: 1px solid var(--primary-color);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--primary) 30%, transparent);
}

.btn-scan:disabled{
  background-color: var(--muted);
  cursor: not-allowed;
  opacity: 0.65;
  transform: none;
  box-shadow: none;
}

.scanning-spinner{
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid color-mix(in srgb, var(--color-white) 30%, transparent);
  border-radius: 50%;
  border-top-color: var(--background);
  animation: spin 1s ease-in-out infinite;
}

@keyframes spin{
  to { transform: rotate(360deg); }
}

.device-list{
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 300px;
  overflow-y: auto;
  padding-right: 8px;
}

.device-list::-webkit-scrollbar{
  width: 6px;
}

.device-list::-webkit-scrollbar-track{
  background: var(--color-neutral-100);
  border-radius: 3px;
}

.device-list::-webkit-scrollbar-thumb{
  background: var(--color-gray-300);
  border-radius: 3px;
}

.device-list::-webkit-scrollbar-thumb:hover{
  background: var(--color-gray-400);
}

.device-item{
  background-color: white;
  padding: 16px;
  border-radius: 6px;
  border: 1px solid var(--muted);
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 16px;
}

.device-item:hover{
  border-color: var(--primary-color);
  box-shadow: 0 2px 8px color-mix(in srgb, var(--primary) 20%, transparent);
  transform: translateY(-1px);
}

.device-item.active{
  border: 2px solid var(--primary-color);
  background-color: color-mix(in srgb, var(--primary) 20%, transparent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--primary) 30%, transparent), 0 4px 12px color-mix(in srgb, var(--primary) 25%, transparent);
  transform: translateY(-2px);
  z-index: 10;
}

.device-item.current{
  border: 2px solid var(--success-color);
  background-color: color-mix(in srgb, var(--success) 20%, transparent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--success) 30%, transparent);
}

.device-item.added{
  border: 1px solid var(--border-color);
  background-color: color-mix(in srgb, var(--muted-foreground) 5%, transparent);
}

.device-item.added.active{
  border: 2px solid var(--primary-color);
  background-color: color-mix(in srgb, var(--primary) 25%, transparent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--primary) 30%, transparent), 0 4px 12px color-mix(in srgb, var(--primary) 25%, transparent);
  transform: translateY(-2px);
}

.device-icon{
  color: var(--secondary);
}

.device-info{
  flex: 1;
}

.device-name{
  font-weight: 600;
  color: var(--foreground);
  margin-bottom: 4px;
}



.device-model{
  margin-right: 12px;
}

.current-badge{
  background-color: var(--success);
  color: white;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.added-badge{
  background-color: var(--muted-foreground);
  color: white;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.select-badge{
  background-color: var(--primary-color);
  color: white;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  box-shadow: 0 2px 4px color-mix(in srgb, var(--primary) 20%, transparent);
}

.scanning-message{
  text-align: center;
  padding: 24px;
  color: var(--muted-foreground);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.no-devices-message{
  text-align: center;
  padding: 24px;
  color: var(--muted-foreground);
  background-color: white;
  border-radius: 6px;
  border: 1px dashed var(--border);
}
</style>
