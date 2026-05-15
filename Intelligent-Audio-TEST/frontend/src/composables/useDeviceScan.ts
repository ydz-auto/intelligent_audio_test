import { ref, watch, type Ref } from 'vue'
import { playbackApi } from '../utils/api'

export interface DeviceScanResult {
  name?: string;
  device_unique_id?: string;
  deviceUniqueId?: string;
  model?: string;
  sample_rate?: number;
  sampleRate?: number;
  channel_index?: number;
  channelIndex?: number;
}

export interface FormField {
  key: string;
  type?: string;
  options?: any[];
  label?: string;
}

/**
 * 设备扫描composable
 * @returns {Object} 包含设备扫描相关的函数和状态
 */
export function useDeviceScan() {
  // 扫描状态
  const isScanning = ref(false)
  const scanResults = ref<DeviceScanResult[]>([])
  const scanError = ref<string | null>(null)
  
  /**
   * 扫描播放设备
   * @param {Array} fields 表单字段配置数组
   * @param {Object} formValues 表单值对象，用于自动填充扫描结果
   * @param {String} mode 表单模式（create或edit）
   * @returns {Promise<Array>} 扫描结果
   */
  const scanPlaybackDevices = async (fields: FormField[] = [], formValues: any = {}, mode: string = 'create') => {
    // 检查是否是播放设备表单
    const isPlaybackDevice = fields.some(field => 
      field.key === 'playbackType' || 
      field.key === 'playback_type' || 
      field.key === 'audioChannel' ||
      field.key === 'audio_channel' ||
      field.key === 'deviceUniqueId' ||
      field.key === 'device_unique_id' ||
      field.key === 'sampleRate' ||
      field.key === 'sample_rate' ||
      field.key === 'channelIndex' ||
      field.key === 'channel_index'
    )
    
    if (!isPlaybackDevice) return []
    
    try {
      isScanning.value = true
      scanError.value = null
      scanResults.value = []
      
      // 调用后端API扫描播放设备
      console.log('调用后端API扫描播放设备...')
      const response = await playbackApi.scan()
      scanResults.value = (response as DeviceScanResult[]) || []
      
      console.log('扫描结果:', scanResults.value)
      
      // 如果扫描到设备，自动填充第一个设备的信息
      if (scanResults.value.length > 0) {
        const firstDevice = scanResults.value[0]
        
        // 找到设备唯一标识字段并更新其选项，支持两种命名方式
        const uniqueIdField = fields.find(field => 
          field.key === 'device_unique_id' || 
          field.key === 'deviceUniqueId'
        )
        if (uniqueIdField && uniqueIdField.type === 'select') {
          // 更新选项列表 - 使用索引作为key的一部分，避免重复key
          uniqueIdField.options = scanResults.value.map((device, index) => {
            const deviceName = device.name || '设备'
            const uniqueId = device.device_unique_id || device.deviceUniqueId || ''
            // 避免标签中出现重复文本，只显示设备名或唯一标识，不要同时显示相同内容
            let label = deviceName
            if (deviceName !== uniqueId) {
              label = `${deviceName} (${uniqueId})`
            }
            return {
              value: uniqueId,
              label: label,
              index: index // 添加索引，用于生成唯一key
            }
          })
        }
        
        // 自动填充表单字段，支持两种命名方式
        // 【修复】编辑模式下不覆盖已有值，只在创建模式下自动填充
        if (formValues && mode !== 'edit') {
          // 设备唯一标识
          const deviceUniqueId = firstDevice.device_unique_id || firstDevice.deviceUniqueId
          if (!formValues.device_unique_id) formValues.device_unique_id = deviceUniqueId
          if (!formValues.deviceUniqueId) formValues.deviceUniqueId = deviceUniqueId

          // 同时填充其他相关字段
          if (firstDevice.name) formValues.name = firstDevice.name
          if (firstDevice.model) formValues.model = firstDevice.model

          // 采样率
          const sampleRate = firstDevice.sample_rate || firstDevice.sampleRate || 48000
          if (formValues.sample_rate !== undefined) formValues.sample_rate = sampleRate
          if (formValues.sampleRate !== undefined) formValues.sampleRate = sampleRate

          // 通道索引
          const channelIndex = firstDevice.channel_index || firstDevice.channelIndex || 0
          if (formValues.channel_index !== undefined) formValues.channel_index = channelIndex
          if (formValues.channelIndex !== undefined) formValues.channelIndex = channelIndex
        } else if (mode === 'edit') {
          console.log('[scanPlaybackDevices] 编辑模式下跳过自动填充，保持表单原有值')
        }
      }
      
      return scanResults.value
    } catch (error: any) {
      console.error('扫描播放设备失败:', error)
      scanError.value = '扫描播放设备失败: ' + (error.message || '未知错误')
      return []
    } finally {
      isScanning.value = false
    }
  }
  
  /**
   * 监听表单模式变化，重新扫描（如果从编辑切换到添加）
   */
  const watchModeChange = (modeRef: Ref<string>, fields: FormField[], formValues: any) => {
    watch(modeRef, (newMode) => {
      if (newMode === 'create') {
        scanPlaybackDevices(fields, formValues, newMode)
      }
    })
  }
  
  /**
   * 监听表单数据变化，重新扫描设备
   */
  const watchFormDataChange = (formDataRef: Ref<any>, fields: FormField[], formValues: any) => {
    watch(formDataRef, (newVal, oldVal) => {
      // 只有当新旧值都存在且有实际内容时才重新扫描
      if (newVal && JSON.stringify(newVal) !== JSON.stringify(oldVal)) {
        scanPlaybackDevices(fields, formValues, 'create')
      }
    }, { immediate: true, deep: true })
  }
  
  /**
   * 监听字段变化，重新扫描设备
   */
  const watchFieldsChange = (fieldsRef: Ref<FormField[]>, formValues: any) => {
    watch(fieldsRef, (newVal, oldVal) => {
      if (newVal && oldVal && JSON.stringify(newVal) !== JSON.stringify(oldVal)) {
        scanPlaybackDevices(newVal, formValues, 'create')
      }
    }, { immediate: true, deep: true })
  }
  
  return {
    isScanning,
    scanResults,
    scanError,
    scanPlaybackDevices,
    watchModeChange,
    watchFormDataChange,
    watchFieldsChange
  }
}
