import { ref, computed } from 'vue'
import { useModalStore } from '../../../../store/modalStore'

/**
 * 表单初始化 composable
 * 负责表单数据的初始化、草稿恢复、默认值生成、条件判断
 */
export function useFormInitializer(props: any, isEditMode: any, clearErrors: any) {
  const formValues = ref({})
  const isDraftRestored = ref(false)
  const modalStore = useModalStore()

  const draftId = computed(() => {
    if (props.mode === 'edit' && props.formData && props.formData.id) {
      return `${props.entityName}_edit_${props.formData.id}`
    }
    return `${props.entityName}_${props.mode}`
  })

  const getDefaultValue = (field: any) => {
    if (field.defaultValue !== undefined) return field.defaultValue

    switch (field.type) {
      case 'checkbox': return []
      case 'array':
        if (field.arrayItemTemplate) {
          const template = { ...field.arrayItemTemplate }
          if (field.arrayItemType === 'apiEndpoint') {
            const defaultMaxProcess = props.formData?.defaultMaxProcess || 5
            const defaultMaxTimeout = props.formData?.defaultMaxTimeout || 30
            const defaultMaxAudioDuration = props.formData?.defaultMaxAudioDuration || 60
            return [{ ...template, maxProcess: template.maxProcess || defaultMaxProcess, maxTimeout: template.maxTimeout || defaultMaxTimeout, maxAudioDuration: template.maxAudioDuration || defaultMaxAudioDuration }]
          }
          return [template]
        }
        if (field.arrayItemType === 'apiEndpoint') {
          return [{ endpoint: '', name: '', priority: 1, maxProcess: 5, maxTimeout: 30, maxAudioDuration: 60 }]
        }
        return [{ digital_gain: null, spl: null }]
      case 'number': return 0
      case 'switch': return false
      case 'apiMeta': return { protocol: 'https', environment: 'development', version: 'v1', apiKey: '' }
      case 'apiSettingsEditor': return { method: 'POST', headers: {}, body_template: {}, timeout: 30000 }
      default: return ''
    }
  }

  const checkCondition = (condition: any) => {
    if (!condition || !condition.field) return true
    const fieldValue = formValues.value[condition.field]
    if (Array.isArray(condition.value)) {
      return condition.value.includes(fieldValue)
    }
    return fieldValue === condition.value
  }

  const initFormData = async () => {
    const draft = modalStore.getDraft(draftId.value)
    if (draft) {
      formValues.value = { ...draft }
      isDraftRestored.value = true
      return
    }

    isDraftRestored.value = false
    const initialValues = {}

    if (!Array.isArray(props.fields)) return

    props.fields.forEach(field => {
      if (!field || typeof field !== 'object') return

      const hasFormData = props.formData && typeof props.formData === 'object'
      let formDataValue = hasFormData ? props.formData[field.key] : undefined

      if (formDataValue === undefined && hasFormData) {
        const camelCaseKey = field.key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase())
        formDataValue = props.formData[camelCaseKey]

        if (field.key === 'serialNumber' && formDataValue === undefined) {
          formDataValue = props.formData.serialNumber
        }
        if (field.key === 'deviceUniqueId' && formDataValue === undefined) {
          formDataValue = props.formData.deviceUniqueId
        }
      }

      let fieldValue
      if (formDataValue !== undefined && formDataValue !== null) {
        fieldValue = formDataValue

        if (field.type === 'apiMeta') {
          if (typeof fieldValue === 'string') {
            try { fieldValue = JSON.parse(fieldValue) } catch (e) { fieldValue = getDefaultValue(field) }
          } else if (typeof fieldValue !== 'object') {
            fieldValue = getDefaultValue(field)
          }
        } else if (field.type === 'array') {
          if (typeof fieldValue === 'string') {
            try { fieldValue = JSON.parse(fieldValue) } catch (e) { fieldValue = getDefaultValue(field) }
          } else if (!Array.isArray(fieldValue)) {
            fieldValue = getDefaultValue(field)
          }

          if (field.type === 'array' && field.arrayItemType === 'gainSpl' && (formDataValue === undefined || (Array.isArray(formDataValue) && formDataValue.length === 0)) && props.formData.calibration_data) {
            const calibrationData = props.formData.calibration_data
            if (calibrationData && calibrationData.points && Array.isArray(calibrationData.points)) {
              formDataValue = calibrationData.points.map(point => ({
                gainOffset: point.gainOffset !== undefined ? point.gainOffset : null,
                spl: point.spl !== undefined ? point.spl : null
              }))
            }
          }

          if (Array.isArray(fieldValue) && field.arrayItemType === 'apiEndpoint') {
            const globalDefaultMaxProcess = props.formData.defaultMaxProcess || 5
            const globalDefaultMaxTimeout = props.formData.defaultMaxTimeout || 30
            const globalDefaultMaxAudioDuration = props.formData.defaultMaxAudioDuration || 60

            fieldValue = fieldValue.map(endpoint => ({
              ...endpoint,
              url: endpoint.url || endpoint.endpoint || '',
              name: endpoint.name || '',
              priority: endpoint.priority || 1,
              maxProcess: endpoint.maxProcess || endpoint.maxProcess || globalDefaultMaxProcess,
              maxTimeout: endpoint.maxTimeout || endpoint.maxTimeout || globalDefaultMaxTimeout,
              maxAudioDuration: endpoint.maxAudioDuration || endpoint.maxAudioDuration || globalDefaultMaxAudioDuration
            }))

            if (fieldValue.length === 0) {
              fieldValue = [{
                url: '',
                name: '',
                priority: 1,
                maxProcess: globalDefaultMaxProcess,
                maxTimeout: globalDefaultMaxTimeout,
                maxAudioDuration: globalDefaultMaxAudioDuration
              }]
            }
          }
        }
      } else {
        fieldValue = getDefaultValue(field)
      }

      initialValues[field.key] = fieldValue
    })

    if (isEditMode.value && props.formData && props.formData.id !== undefined) {
      initialValues.id = props.formData.id
    }

    formValues.value = initialValues
    clearErrors()

    props.fields.forEach(field => {
      if (!field || typeof field !== 'object') return
      if (field.type === 'hidden') return
      if (field.conditional && field.conditional.field && formValues.value[field.conditional.field] === undefined) {
        const cond = field.conditional
        let defaultVal = ''
        if (cond.field === 'dimensionType') defaultVal = 'main'
        if (cond.field === 'categoryId') defaultVal = ''
        formValues.value[cond.field] = defaultVal
      }
    })
  }

  return {
    formValues,
    isDraftRestored,
    draftId,
    initFormData,
    getDefaultValue,
    checkCondition
  }
}
