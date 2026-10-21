import { ref, type Ref } from 'vue'

/** 设备选择表单字段（极简视图，原 FormField 改名避免与 DynamicFormField/算法 FormField 混淆） */
export interface DeviceFormField {
  key: string
  type?: string
  options?: any[]
  label?: string
}

/** 测试设备系统归一（INT-1105 对齐 React INT-1029 mergeScanPrefill 的 system 归一）：
 * 后端 scan 返 system 可能为大写/别名（iOS/Android/HarmonyOS），表单 select 选项为小写原值
 * （ios/android/harmony），回填时统一归一，避免 select 命中不了选项而空白。
 * 空值原样返回（不强行写默认系统，保留用户已填值）。 */
function normalizeSystem(system?: string): string | undefined {
  if (!system) return system
  const s = system.toLowerCase()
  if (s.includes('harmony')) return 'harmony'
  if (s.includes('ios')) return 'ios'
  if (s.includes('android')) return 'android'
  return system
}

export function useDeviceSelection() {
  const selectedDeviceId = ref<string | null>(null)

  const isPlaybackDeviceForm = (fields: DeviceFormField[]) => {
    return fields.some(field =>
      field.key === 'playbackType' ||
      field.key === 'audioChannel' ||
      field.key === 'deviceUniqueId' ||
      field.key === 'sampleRate' ||
      field.key === 'channelIndex'
    )
  }

  const isTestDeviceForm = (fields: DeviceFormField[]) => {
    return fields.some(field =>
      field.key === 'serialNumber' ||
      field.key === 'system' ||
      field.key === 'systemVersion' ||
      field.key === 'connectionType'
    )
  }

  const selectDevice = (device: any, fields: DeviceFormField[], formValuesRef: Ref<any>, isEditMode: boolean) => {
    selectedDeviceId.value = device.displayKey || device.deviceUniqueId || device.serial

    const formValues = formValuesRef.value

    const deviceUniqueId = device.deviceUniqueId || device.id || device.serial
    if (deviceUniqueId) {
      const uniqueIdField = fields.find(f => f.key === 'deviceUniqueId')
      if (uniqueIdField) {
        formValues[uniqueIdField.key] = deviceUniqueId
      }
    }

    if (device.name && (!isEditMode || !formValues.name)) {
      formValues.name = device.name
    }
    if (device.model) {
      formValues.model = device.model
    }

    const srField = fields.find(f => f.key === 'sampleRate')
    if (srField) {
      formValues[srField.key] = device.sampleRate || 48000
    }

    const ciField = fields.find(f => f.key === 'channelIndex')
    if (ciField) {
      formValues[ciField.key] = device.channelIndex !== undefined ? device.channelIndex : 0
    }

    if (device.serial) {
      const serialField = fields.find(f => f.key === 'serialNumber')
      if (serialField) {
        formValues[serialField.key] = device.serial
      }
    }
    if (device.system) {
      const systemField = fields.find(f => f.key === 'system')
      if (systemField) {
        formValues.system = normalizeSystem(device.system)
      }
    }
    if (device.systemVersion) {
      const svField = fields.find(f => f.key === 'systemVersion')
      if (svField) {
        formValues.systemVersion = device.systemVersion
      }
    }
    if (device.appName) {
      const appField = fields.find(f => f.key === 'appName')
      if (appField) {
        formValues.appName = device.appName
      }
    }
    if (device.appVersion) {
      const appVField = fields.find(f => f.key === 'appVersion')
      if (appVField) {
        formValues.appVersion = device.appVersion
      }
    }

    // INT-1105 扫描回填补齐（对齐 React INT-1029 mergeScanPrefill）：
    // 测试设备 IP（表单键 ip / ipAddress / ip_address 兜底）；播放设备类型仅落合法选项 dry/noise
    const ip = device.ip || device.ipAddress || device.ip_address
    if (ip) {
      const ipField = fields.find(f => f.key === 'ip' || f.key === 'ipAddress' || f.key === 'ip_address')
      if (ipField) {
        formValues[ipField.key] = ip
      }
    }

    const deviceType = device.deviceType || device.type
    if (deviceType === 'dry' || deviceType === 'noise') {
      const dtField = fields.find(f => f.key === 'deviceType')
      if (dtField) {
        formValues[dtField.key] = deviceType
      }
    }

    return formValues
  }

  const resetSelection = () => {
    selectedDeviceId.value = null
  }

  return {
    selectedDeviceId,
    isPlaybackDeviceForm,
    isTestDeviceForm,
    selectDevice,
    resetSelection
  }
}
