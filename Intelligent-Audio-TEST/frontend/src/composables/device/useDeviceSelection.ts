import { ref, type Ref } from 'vue'

export interface FormField {
  key: string
  type?: string
  options?: any[]
  label?: string
}

export function useDeviceSelection() {
  const selectedDeviceId = ref<string | null>(null)

  const isPlaybackDeviceForm = (fields: FormField[]) => {
    return fields.some(field =>
      field.key === 'playbackType' ||
      field.key === 'audioChannel' ||
      field.key === 'deviceUniqueId' ||
      field.key === 'device_unique_id' ||
      field.key === 'sampleRate' ||
      field.key === 'sample_rate' ||
      field.key === 'channelIndex' ||
      field.key === 'channel_index'
    )
  }

  const isTestDeviceForm = (fields: FormField[]) => {
    return fields.some(field =>
      field.key === 'serialNumber' ||
      field.key === 'system' ||
      field.key === 'systemVersion' ||
      field.key === 'system_version' ||
      field.key === 'connectionType' ||
      field.key === 'connection_type'
    )
  }

  const selectDevice = (device: any, fields: FormField[], formValuesRef: Ref<any>, isEditMode: boolean) => {
    selectedDeviceId.value = device.displayKey || device.device_unique_id || device.serial

    const formValues = formValuesRef.value

    const deviceUniqueId = device.device_unique_id || device.id || device.serial
    if (deviceUniqueId) {
      const uniqueIdField = fields.find(f => f.key === 'deviceUniqueId' || f.key === 'device_unique_id')
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

    const srField = fields.find(f => f.key === 'sampleRate' || f.key === 'sample_rate')
    if (srField) {
      formValues[srField.key] = device.sample_rate || 48000
    }

    const ciField = fields.find(f => f.key === 'channelIndex' || f.key === 'channel_index')
    if (ciField) {
      formValues[ciField.key] = device.channel_index !== undefined ? device.channel_index : 0
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
    if (device.system_version) {
      const svField = fields.find(f => f.key === 'systemVersion')
      if (svField) {
        formValues.systemVersion = device.system_version
      }
    }
    if (device.app_name) {
      const appField = fields.find(f => f.key === 'appName')
      if (appField) {
        formValues.appName = device.app_name
      }
    }
    if (device.app_version) {
      const appVField = fields.find(f => f.key === 'appVersion')
      if (appVField) {
        formValues.appVersion = device.app_version
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
