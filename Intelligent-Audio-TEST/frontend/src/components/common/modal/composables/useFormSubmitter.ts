import { ref } from 'vue'
import { useModalStore } from '../../../../store/modalStore'

/**
 * 表单提交 composable
 * 负责表单验证、文件上传管理、错误滚动定位、提交数据组装
 */
export function useFormSubmitter(
  props: any,
  emit: any,
  formValues: any,
  validationErrors: any,
  validateForm: any,
  addedPlaybackDevices: any,
  isEditMode: any,
  draftId: any,
  getDefaultValue: any,
  checkCondition: any
) {
  const submitting = ref(false)
  const uploadedFiles = ref({})
  const modalStore = useModalStore()

  const handleFileUpload = ({ fieldKey, file }: any) => {
    if (file) {
      uploadedFiles.value[fieldKey] = file
      formValues.value[fieldKey] = file
    } else {
      uploadedFiles.value[fieldKey] = null
      formValues.value[fieldKey] = getDefaultValue(props.fields.find((f: any) => f.key === fieldKey))
    }
  }

  const scrollToFirstError = () => {
    const errorKeys = Object.keys(validationErrors)
    if (errorKeys.length === 0) return

    const firstErrorKey = errorKeys[0]
    const arrayFieldElement = document.querySelector(`.array-field[data-field-key="${firstErrorKey}"]`)
    if (arrayFieldElement) {
      arrayFieldElement.scrollIntoView({ behavior: 'smooth', block: 'center' })
      return
    }

    const fieldErrorElement = document.querySelector(`.field-error[data-field="${firstErrorKey}"]`)
    if (fieldErrorElement) {
      fieldErrorElement.scrollIntoView({ behavior: 'smooth', block: 'center' })
      return
    }

    const dataFieldElement = document.querySelector(`[data-field-key="${firstErrorKey}"]`)
    if (dataFieldElement) {
      dataFieldElement.scrollIntoView({ behavior: 'smooth', block: 'center' })
      return
    }

    const modalContent = document.querySelector('.crud-form-modal')
    if (modalContent) {
      modalContent.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }

  const handleSubmit = async () => {
    if (!validateForm(props.fields, formValues.value)) {
      const firstError = Object.values(validationErrors)[0]
      if (firstError) {
        scrollToFirstError()
      }
      return
    }

    const isPlaybackDevice = props.fields.some((f: any) => f.key === 'deviceUniqueId' || f.key === 'sampleRate')
    if (isPlaybackDevice && !isEditMode.value) {
      const deviceUniqueId = formValues.value.deviceUniqueId || formValues.value.device_unique_id || formValues.value.name
      if (deviceUniqueId) {
        const deviceExists = addedPlaybackDevices.value.some((d: any) => {
          const addedId = d.deviceUniqueId || d.device_unique_id || d.name
          return addedId === deviceUniqueId
        })

        if (deviceExists) {
          alert('该播放设备已存在，不允许重复添加')
          return
        }
      }
    }

    submitting.value = true

    try {
      const submitData = {}

      props.fields.forEach(field => {
        if (field && field.key) {
          if (field.conditional && !checkCondition(field.conditional)) return

          let value = formValues.value[field.key]

          if (field.arrayItemType === 'apiEndpoint' && Array.isArray(value)) {
            value = value.map(item => ({ ...item, endpoint: item.url || item.endpoint || '', url: item.url || item.endpoint || '' }))
          }

          if (value === undefined || value === '') {
            value = null
          }

          submitData[field.key] = value
        }
      })

      if (formValues.value.id) {
        submitData.id = formValues.value.id
      }

      const isTestDevice = props.fields.some((f: any) => f.key === 'serialNumber' || f.key === 'systemVersion')
      if (isTestDevice) {
        const requiredTestFields = ['name', 'model', 'type', 'system', 'systemVersion', 'appName', 'appVersion']
        requiredTestFields.forEach(key => {
          if (submitData[key] === undefined || submitData[key] === null) {
            submitData[key] = formValues.value[key] || (key === 'type' ? 'phone' : 'Unknown')
          }
        })
      }

      let isMultipart = false
      const formData = new FormData()

      Object.keys(uploadedFiles.value).forEach(fieldKey => {
        if (uploadedFiles.value[fieldKey]) {
          isMultipart = true
          formData.append(fieldKey, uploadedFiles.value[fieldKey])
        }
      })

      if (isMultipart) {
        Object.keys(submitData).forEach(key => {
          if (submitData[key] !== null) {
            if (typeof submitData[key] === 'object') {
              formData.append(key, JSON.stringify(submitData[key]))
            } else {
              formData.append(key, submitData[key])
            }
          }
        })
      }

      const finalPayload = isMultipart ? formData : submitData

      emit('confirm', { data: finalPayload, mode: isEditMode.value ? 'edit' : 'create', isMultipart: isMultipart })
      modalStore.clearDraft(draftId.value)
    } catch (error) {
      console.error('表单准备提交数据失败:', error)
    } finally {
      submitting.value = false
    }
  }

  return {
    submitting,
    uploadedFiles,
    handleFileUpload,
    handleSubmit
  }
}
