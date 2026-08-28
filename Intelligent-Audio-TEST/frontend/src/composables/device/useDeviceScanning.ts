import { ref } from 'vue'
import { devicesApi } from '../../utils/api'

export function useDeviceScanning() {
  const isScanning = ref(false)
  const scanResults = ref<any[]>([])
  const availableSerials = ref<any[]>([])
  const addedPlaybackDevices = ref<any[]>([])
  const addedTestDevices = ref<any[]>([])
  const apiPlaybackDevices = ref<any[]>([])

  const fetchAddedPlaybackDevices = async () => {
    try {
      const response = await fetch('/api/v1/playback-devices?page=1&per_page=1000')
      const result = await response.json()
      
      let devices = []
      if (result) {
        if (Array.isArray(result)) {
          devices = result
        } else if (result.data) {
          if (Array.isArray(result.data)) {
            devices = result.data
          } else if (result.data.items && Array.isArray(result.data.items)) {
            devices = result.data.items
          } else if (result.data.playback_devices && Array.isArray(result.data.playback_devices)) {
            devices = result.data.playback_devices
          }
        } else if (result.playback_devices && Array.isArray(result.playback_devices)) {
          devices = result.playback_devices
        } else if (result.devices && Array.isArray(result.devices)) {
          devices = result.devices
        }
      }
      
      addedPlaybackDevices.value = devices
      return devices
    } catch (error) {
      console.error('[useDeviceScanning] 获取已添加设备失败:', error)
      addedPlaybackDevices.value = []
      return []
    }
  }

  const fetchAddedTestDevices = async () => {
    try {
      const response = await fetch('/api/v1/test-devices?page=1&per_page=1000')
      const result = await response.json()
      
      let devices = []
      if (result && result.code === 0 && result.data && Array.isArray(result.data.items)) {
        devices = result.data.items
      } else if (result && Array.isArray(result)) {
        devices = result
      } else if (result && result.data && Array.isArray(result.data)) {
        devices = result.data
      }
      
      addedTestDevices.value = devices
      return devices
    } catch (error) {
      console.error('[useDeviceScanning] 获取已添加测试设备失败:', error)
      return []
    }
  }

  const scanPlaybackDevices = async () => {
    try {
      isScanning.value = true
      const scanResult = await fetch('/api/v1/playback-devices/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      }).then(r => r.json())
      
      let scannedDevices = []
      if (scanResult && scanResult.code === 0 && Array.isArray(scanResult.data)) {
        scannedDevices = scanResult.data
      }
      
      scanResults.value = scannedDevices
      apiPlaybackDevices.value = scannedDevices
      await fetchAddedPlaybackDevices()
      
      return scannedDevices
    } catch (error) {
      console.error('[useDeviceScanning] 扫描播放设备失败:', error)
      return []
    } finally {
      isScanning.value = false
    }
  }

  const scanTestDeviceSerials = async () => {
    try {
      isScanning.value = true
      const response = await devicesApi.getAvailableSerials()
      
      let fetchedDevices = []
      if (response) {
        if (Array.isArray(response)) {
          fetchedDevices = response
        } else if (response.data && Array.isArray(response.data)) {
          fetchedDevices = response.data
        } else if (response.devices && Array.isArray(response.devices)) {
          fetchedDevices = response.devices
        } else if (response.success === true || response.code === 0 || response.code === 200) {
          if (response.data && Array.isArray(response.data)) {
            fetchedDevices = response.data
          }
        }
      }
      
      availableSerials.value = fetchedDevices.map(device => ({
        serial: device.serial || device.serial_number || device.device_id || device.id || device.device_unique_id,
        name: device.name || device.model || '未知设备',
        system: device.system || device.platform || 'android',
        model: device.model || '未知设备',
        systemVersion: device.system_version || device.version || device.os_version || '1.0.0'
      }))
      
      await fetchAddedTestDevices()
      
      return availableSerials.value
    } catch (error) {
      console.error('[useDeviceScanning] 扫描测试设备失败:', error)
      return []
    } finally {
      isScanning.value = false
    }
  }

  const getPlaybackDevicesDisplay = (currentDeviceId, isEditMode) => {
    const addedIds = new Set()
    addedPlaybackDevices.value.forEach(d => {
      if (d.device_unique_id) addedIds.add(d.device_unique_id)
      if (d.id) addedIds.add(d.id)
      if (d.name) addedIds.add(d.name)
    })
    
    let devices = []
    
    if (scanResults.value && scanResults.value.length > 0) {
      const seen = new Set()
      devices = scanResults.value
        .filter(device => {
          const id = device.device_unique_id || device.id || device.name
          if (seen.has(id)) return false
          seen.add(id)
          return true
        })
        .map((device, index) => {
          const deviceId = device.device_unique_id || device.id || device.name
          let isAdded = false
          const deviceIdentifiers = new Set()
          if (deviceId) deviceIdentifiers.add(deviceId)
          if (device.name) deviceIdentifiers.add(device.name)
          if (device.device_unique_id) deviceIdentifiers.add(device.device_unique_id)
          if (device.id) deviceIdentifiers.add(device.id)
          
          for (const id of deviceIdentifiers) {
            if (addedIds.has(id)) {
              isAdded = true
              break
            }
          }
          
          return {
            displayKey: deviceId,
            deviceUniqueId: deviceId,
            name: device.name || `播放设备 ${index + 1}`,
            model: device.model || '未知型号',
            sampleRate: device.sample_rate,
            channelIndex: device.channel_index,
            index: index,
            isAdded: isAdded,
            isCurrent: currentDeviceId === deviceId || currentDeviceId === device.name ||
                      (currentDeviceId && deviceIdentifiers.has(currentDeviceId))
          }
        })
    }
    
    if (devices.length === 0 && apiPlaybackDevices.value && apiPlaybackDevices.value.length > 0) {
      const seen = new Set()
      devices = apiPlaybackDevices.value
        .filter(device => {
          const id = device.device_unique_id || device.id || device.name
          if (seen.has(id)) return false
          seen.add(id)
          return true
        })
        .map((device, index) => {
          const deviceId = device.device_unique_id || device.id || device.name
          let isAdded = false
          const deviceIdentifiers = new Set()
          if (deviceId) deviceIdentifiers.add(deviceId)
          if (device.name) deviceIdentifiers.add(device.name)
          if (device.device_unique_id) deviceIdentifiers.add(device.device_unique_id)
          if (device.id) deviceIdentifiers.add(device.id)
          
          for (const id of deviceIdentifiers) {
            if (addedIds.has(id)) {
              isAdded = true
              break
            }
          }
          
          return {
            displayKey: deviceId,
            deviceUniqueId: deviceId,
            name: device.name || `播放设备 ${index + 1}`,
            model: device.model || '未知型号',
            sampleRate: device.sample_rate,
            channelIndex: device.channel_index,
            index: index,
            isAdded: isAdded,
            isCurrent: currentDeviceId === deviceId || currentDeviceId === device.name ||
                      (currentDeviceId && deviceIdentifiers.has(currentDeviceId))
          }
        })
    }
    
    if (isEditMode && currentDeviceId && !devices.find(d => d.displayKey === currentDeviceId)) {
      const currentDevice = addedPlaybackDevices.value.find(d =>
        d.device_unique_id === currentDeviceId ||
        d.id === currentDeviceId ||
        d.name === currentDeviceId
      )
      if (currentDevice) {
        devices.unshift({
          displayKey: currentDeviceId,
          deviceUniqueId: currentDeviceId,
          name: currentDevice.name || currentDeviceId,
          model: currentDevice.model || '未知型号',
          sampleRate: currentDevice.sample_rate,
          channelIndex: currentDevice.channel_index,
          index: -1,
          isAdded: true,
          isCurrent: true
        })
      }
    }
    
    const displayedDeviceIds = new Set(devices.map(d => d.displayKey))
    const missingAddedDevices = addedPlaybackDevices.value.filter(d => {
      const deviceId = d.device_unique_id || d.id || d.name
      return !displayedDeviceIds.has(deviceId)
    })

    missingAddedDevices.forEach((d, index) => {
      const deviceId = d.device_unique_id || d.id || d.name
      devices.push({
        displayKey: deviceId,
        deviceUniqueId: deviceId,
        name: d.name || `播放设备 ${index + 1}`,
        model: d.model || '未知型号',
        sampleRate: d.sample_rate,
        channelIndex: d.channel_index,
        index: devices.length + index,
        isAdded: true,
        isCurrent: currentDeviceId === deviceId
      })
    })
    
    const sorted = [...devices.filter(d => d.isCurrent), ...devices.filter(d => !d.isCurrent && !d.isAdded), ...devices.filter(d => d.isCurrent === false && d.isAdded)]
    
    return sorted
  }

  const getTestDevicesDisplay = (currentDeviceId, isEditMode) => {
    const addedIds = new Set()
    addedTestDevices.value.forEach(d => {
      if (d.serial) addedIds.add(d.serial)
      if (d.device_unique_id) addedIds.add(d.device_unique_id)
      if (d.id) addedIds.add(d.id)
      if (d.name) addedIds.add(d.name)
    })
    
    let devices = []
    
    if (availableSerials.value && availableSerials.value.length > 0) {
      const seen = new Set()
      const uniqueSerials = availableSerials.value.filter(device => {
        const serial = typeof device === 'object' ? (device.serial || device.device_unique_id || device.id || device.name) : device
        if (seen.has(serial)) return false
        seen.add(serial)
        return true
      })
      
      devices = uniqueSerials.map((device, index) => {
        const serial = typeof device === 'object' ? (device.serial || device.device_unique_id || device.id || device.name) : device
        const deviceId = typeof device === 'object' ? (device.device_unique_id || device.id || device.name) : serial
        
        const isAdded = addedIds.has(serial) || addedIds.has(deviceId) ||
                      (typeof device === 'object' &&
                       (addedIds.has(device.name || '') ||
                        addedIds.has(device.serial || '') ||
                        addedIds.has(device.device_unique_id || '')))
        
        return {
          displayKey: serial,
          serial: serial,
          deviceUniqueId: deviceId,
          name: typeof device === 'object' ? (device.name || `测试设备 ${index + 1}`) : `测试设备 ${index + 1}`,
          model: typeof device === 'object' ? (device.model || '未知型号') : '未知型号',
          system: typeof device === 'object' ? device.system : undefined,
          systemVersion: typeof device === 'object' ? device.system_version : undefined,
          index: index,
          isAdded: isAdded,
          isCurrent: currentDeviceId === serial || currentDeviceId === deviceId
        }
      })
    }
    
    if (isEditMode && currentDeviceId && !devices.find(d => d.displayKey === currentDeviceId)) {
      const currentDevice = addedTestDevices.value.find(d =>
        d.serial === currentDeviceId ||
        d.device_unique_id === currentDeviceId ||
        d.id === currentDeviceId ||
        d.name === currentDeviceId
      )
      if (currentDevice) {
        devices.unshift({
          displayKey: currentDeviceId,
          serial: currentDeviceId,
          deviceUniqueId: currentDevice.device_unique_id || currentDevice.id || currentDevice.name,
          name: currentDevice.name || currentDeviceId,
          model: currentDevice.model || '未知型号',
          system: currentDevice.system,
          systemVersion: currentDevice.system_version || '未知版本',
          index: -1,
          isAdded: true,
          isCurrent: true
        })
      }
    }
    
    const sorted = [...devices.filter(d => d.isCurrent), ...devices.filter(d => !d.isCurrent && !d.isAdded), ...devices.filter(d => d.isCurrent === false && d.isAdded)]
    
    return sorted
  }

  return {
    isScanning,
    scanResults,
    availableSerials,
    addedPlaybackDevices,
    addedTestDevices,
    apiPlaybackDevices,
    fetchAddedPlaybackDevices,
    fetchAddedTestDevices,
    scanPlaybackDevices,
    scanTestDeviceSerials,
    getPlaybackDevicesDisplay,
    getTestDevicesDisplay
  }
}
