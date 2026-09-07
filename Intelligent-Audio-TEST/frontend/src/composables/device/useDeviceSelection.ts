import { ref, type Ref } from 'vue'

/** 设备选择表单字段（极简视图，原 FormField 改名避免与 DynamicFormField/算法 FormField 混淆） */
export interface DeviceFormField {
  key: string
  type?: string
  options?: any[]
  label?: string
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
        formValues.system = device.system
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
