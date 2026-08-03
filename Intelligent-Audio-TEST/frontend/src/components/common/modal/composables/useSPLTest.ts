import { splApi } from '../../../../utils/api'

/**
 * SPL 声压测试 composable
 * 负责测试音播放、停止、完成回调
 */
export function useSPLTest(formValues: any, emit: any) {
  const handleTestSPL = async ({ index, gainValue, splValue, gainOffset }: any) => {
    try {
      let deviceUniqueId = formValues.value.deviceUniqueId
      const deviceId = formValues.value.deviceId

      // 根据 deviceId 获取单个设备的详细信息
      if (deviceId) {
        const response = await fetch(`/api/v1/playback-devices/${deviceId}`)
        if (response.ok) {
          const data = await response.json()
          const device = data.data || data
          if (device) {
            deviceUniqueId = device.device_unique_id || device.deviceUniqueId
            formValues.value.deviceUniqueId = deviceUniqueId
          }
        }
      }

      if (!deviceUniqueId) {
        alert('请先选择关联设备')
        return
      }

      const response = await fetch('/api/v1/spl/test-tone', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ gain_value: gainValue, gain_offset: gainOffset, target_spl: splValue, unique_id: deviceUniqueId })
      })

      const result = await response.json()

      if (result.code === 0 || result.success) {
        setTimeout(() => { emit('test-spl-complete', index) }, 3000)
      } else {
        alert(`测试音播放失败: ${result.message || result.msg || '未知错误'}`)
      }
    } catch (error) {
      console.error('[handleTestSPL] 测试声压失败:', error)
      alert(`测试声压失败: ${error.message}`)
    }
  }

  const handleTestSPLComplete = (index: any) => {
    console.log(`[handleTestSPLComplete] 测试声压播放完成: index=${index}`)
  }

  const handleStopSPL = async ({ index }: any) => {
    try {
      let deviceUniqueId = formValues.value.deviceUniqueId
      const deviceId = formValues.value.deviceId

      // 根据 deviceId 获取单个设备的详细信息
      if (deviceId) {
        const response = await fetch(`/api/v1/playback-devices/${deviceId}`)
        if (response.ok) {
          const data = await response.json()
          const device = data.data || data
          if (device) {
            deviceUniqueId = device.device_unique_id || device.deviceUniqueId
            formValues.value.deviceUniqueId = deviceUniqueId
          }
        }
      }

      await splApi.stopTestTone(deviceUniqueId || null)
    } catch (error) {
      console.error('[handleStopSPL] 停止测试声压失败:', error)
    }
  }

  const cleanupSPL = async () => {
    try {
      await splApi.stopTestTone()
    } catch (error) {
      console.error('停止测试音失败:', error)
    }
  }

  return {
    handleTestSPL,
    handleTestSPLComplete,
    handleStopSPL,
    cleanupSPL
  }
}
