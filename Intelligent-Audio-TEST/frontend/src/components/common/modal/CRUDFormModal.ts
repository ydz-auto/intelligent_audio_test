import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'

import { useFormValidation } from '../../../composables/modal/useFormValidation'
import { useDeviceSelection } from '../../../composables/device/useDeviceSelection'
import { useDeviceScanning } from '../../../composables/device/useDeviceScanning'
import { devicesApi, splApi } from '../../../utils/api'

export function useCRUDFormModal(props, emit) {
  const formValues = ref({})
  const submitting = ref(false)
  const uploadedFiles = ref({})
  const syncing = ref(false)  // 防止 apiSettings ↔ requiredInputs 双向联动死循环

  const dynamicFieldOptions = ref({
    deviceUniqueId: [],
    keywords: [],
    currentSplMappingId: [],
    algorithmTypes: []
  })

  const dynamicFields = computed(() => {
    const keywordsOptions = dynamicFieldOptions.value.keywords
    const deviceUniqueIdOptions = dynamicFieldOptions.value.deviceUniqueId
    const currentSplMappingIdOptions = dynamicFieldOptions.value.currentSplMappingId
    const algorithmTypesOptions = dynamicFieldOptions.value.algorithmTypes
  
    return props.fields.map(field => {
      if (field.key === 'deviceUniqueId') {
        return { ...field, options: deviceUniqueIdOptions.length > 0 ? deviceUniqueIdOptions : field.options }
      }
      if (field.key === 'keywords') {
        return { ...field, options: keywordsOptions.length > 0 ? keywordsOptions : field.options }
      }
      if (field.key === 'currentSplMappingId') {
        return { ...field, options: currentSplMappingIdOptions.length > 0 ? currentSplMappingIdOptions : field.options }
      }
      if (field.key === 'algorithmType') {
        return { ...field, options: algorithmTypesOptions.length > 0 ? algorithmTypesOptions : field.options }
      }
      return { ...field }
    })
  })

  const groupedFields = computed(() => {
    const groups = {}
    const defaultGroup = '其他'
  
    dynamicFields.value.forEach(field => {
      if (!field || typeof field !== 'object') return
      if (field.type === 'hidden') return
      if (field.conditional && !checkCondition(field.conditional)) return
    
      const groupName = field.group || defaultGroup
      if (!groups[groupName]) {
        groups[groupName] = []
      }
      groups[groupName].push(field)
    })
  
    return groups
  })

  const getVisibleFields = (fields) => {
    if (!Array.isArray(fields)) return []
    return fields.filter(field => {
      if (!field || typeof field !== 'object') return false
      if (field.type === 'hidden') return false
      if (field.conditional) {
        return checkCondition(field.conditional)
      }
      return true
    })
  }

  const { errors: validationErrors, validateForm, clearErrors } = useFormValidation()
  const { selectedDeviceId, isPlaybackDeviceForm, isTestDeviceForm, selectDevice } = useDeviceSelection()
  const { 
    isScanning,
    addedPlaybackDevices,
    addedTestDevices,
    scanPlaybackDevices,
    scanTestDeviceSerials,
    getPlaybackDevicesDisplay,
    getTestDevicesDisplay,
    fetchAddedPlaybackDevices,
    fetchAddedTestDevices
  } = useDeviceScanning()

  const showDeviceSelector = computed(() => {
    return isPlaybackDeviceForm(props.fields) || isTestDeviceForm(props.fields)
  })

  const displayDevices = computed(() => {
    const currentDeviceId = props.mode === 'edit' 
      ? (props.formData?.device_unique_id || props.formData?.serialNumber)
      : selectedDeviceId.value
  
    if (isPlaybackDeviceForm(props.fields)) {
      return getPlaybackDevicesDisplay(currentDeviceId, props.mode === 'edit')
    }
    if (isTestDeviceForm(props.fields)) {
      return getTestDevicesDisplay(currentDeviceId, props.mode === 'edit')
    }
    return []
  })

  const isEditMode = computed(() => {
    if (props.mode === 'edit') return true
    if (props.mode === 'create') return false
    return !!props.formData.id
  })

  const handleDeviceSelect = (device) => {
    selectDevice(device, props.fields, formValues, isEditMode.value)
  }

  const handleRescanDevices = async () => {
    if (isPlaybackDeviceForm(props.fields)) {
      await fetchAddedPlaybackDevices()
      await scanPlaybackDevices()
    }
    if (isTestDeviceForm(props.fields)) {
      await fetchAddedTestDevices()
      await scanTestDeviceSerials()
    }
    selectedDeviceId.value = null
  }

  const loadDriverKeywords = async () => {
    const keywordField = props.fields.find(field => field.action === 'loadDriverKeywords')
    if (!keywordField) return
    if (dynamicFieldOptions.value.keywords.length > 0) return

    try {
      const response = await devicesApi.getDriverKeywords()
      let keywords = []
      if (response && response.data) {
        keywords = response.data
      } else if (Array.isArray(response)) {
        keywords = response
      }

      if (keywords.length > 0) {
        dynamicFieldOptions.value.keywords = keywords.map(item => ({
          value: item.keywords ? item.keywords.join(', ') : '',
          label: `${item.name || ''} (${item.system || ''})`
        }))
      }
    } catch (error) {
      console.error('加载驱动关键字失败:', error)
    }
  }

  const loadSplMappings = async () => {
    const splMappingField = props.fields.find(field => field.action === 'loadSplMappings')
    if (!splMappingField) return
    if (dynamicFieldOptions.value.currentSplMappingId.length > 0) return

    const deviceId = props.formData?.id
    if (!deviceId) return

    try {
      const response = await splApi.getByDevice(deviceId)
      let mappings = []
      if (response && response.items) {
        mappings = response.items
      } else if (Array.isArray(response)) {
        mappings = response
      }

      if (mappings.length > 0) {
        dynamicFieldOptions.value.currentSplMappingId = [
          { value: '', label: '不使用声压映射' },
          ...mappings.map(item => ({
            value: item.id,
            label: `${item.name || `映射 ${item.id}`}${(item.calibrationStatus ?? item.calibration_status) === 'calibrated' ? ' (已校准)' : ' (未校准)'}`
          }))
        ]
      } else {
        dynamicFieldOptions.value.currentSplMappingId = [{ value: '', label: '无可用声压映射' }]
      }
    } catch (error) {
      console.error('加载声压映射失败:', error)
      dynamicFieldOptions.value.currentSplMappingId = [{ value: '', label: '加载失败' }]
    }
  }

  const initFormData = async () => {
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
  
    await fetchAddedPlaybackDevices()
    await fetchAddedTestDevices()
  
    await scanPlaybackDevices()
    await scanTestDeviceSerials()
    await loadDriverKeywords()
    await loadSplMappings()
    await loadAlgorithmTypes()
  }

  const getDefaultValue = (field) => {
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

  const checkCondition = (condition) => {
    if (!condition || !condition.field) return true
    const fieldValue = formValues.value[condition.field]
    if (Array.isArray(condition.value)) {
      return condition.value.includes(fieldValue)
    }
    return fieldValue === condition.value
  }

  const handleFileUpload = ({ fieldKey, file }) => {
    if (file) {
      uploadedFiles.value[fieldKey] = file
      formValues.value[fieldKey] = file
    } else {
      uploadedFiles.value[fieldKey] = null
      formValues.value[fieldKey] = getDefaultValue(props.fields.find(f => f.key === fieldKey))
    }
  }

  const handleTestSPL = async ({ index, gainValue, splValue, gainOffset }) => {
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

  const handleTestSPLComplete = (index) => {
    console.log(`[handleTestSPLComplete] 测试声压播放完成: index=${index}`)
  }

  const handleStopSPL = async ({ index }) => {
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

  const handleButtonAction = async ({ field }) => {
    if (field.action && typeof field.action === 'string') {
      if (field.action === 'scanPlaybackDevices') {
        await fetchAddedPlaybackDevices()
        await scanPlaybackDevices()
      } else if (field.action === 'scanTestDeviceSerials') {
        await fetchAddedTestDevices()
        await scanTestDeviceSerials()
      } else if (field.action === 'loadDriverKeywords') {
        await loadDriverKeywords()
      } else if (field.action === 'loadSplMappings') {
        await loadSplMappings()
      } else if (field.action === 'loadAlgorithmTypes') {
        await loadAlgorithmTypes()
      } else {
        emit('action', { type: field.action, data: formValues.value })
      }
    }
  }

  const loadAlgorithmTypes = async () => {
    if (dynamicFieldOptions.value.algorithmTypes.length > 0) return
  
    try {
      const response = await fetch('/api/v1/algorithm/options')
      const result = await response.json()
      if (result.success && result.data && result.data.algorithms) {
        dynamicFieldOptions.value.algorithmTypes = result.data.algorithms.map((algo) => ({
          value: algo.value || algo.type,
          label: algo.name || algo.label || algo.value || algo.type
        }))
      }
    } catch (error) {
      console.error('加载算法类型选项失败:', error)
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
  
    const isPlaybackDevice = props.fields.some(f => f.key === 'deviceUniqueId' || f.key === 'sampleRate')
    if (isPlaybackDevice && !isEditMode.value) {
      const deviceUniqueId = formValues.value.deviceUniqueId || formValues.value.device_unique_id || formValues.value.name
      if (deviceUniqueId) {
        const deviceExists = addedPlaybackDevices.value.some(d => {
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
    
      const isTestDevice = props.fields.some(f => f.key === 'serialNumber' || f.key === 'systemVersion')
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
    } catch (error) {
      console.error('表单准备提交数据失败:', error)
    } finally {
      submitting.value = false
    }
  }

  onMounted(async () => {
    await initFormData()
  })

  watch(() => props.mode, async (newMode) => {
    if (newMode === 'create') {
      await scanPlaybackDevices()
      await scanTestDeviceSerials()
    }
  })

  watch(() => props.formData, (newFormData) => {
    if (newFormData && typeof newFormData === 'object') {
      const fieldKeys = Object.keys(newFormData)
      fieldKeys.forEach(key => {
        if (formValues.value[key] === undefined) {
          formValues.value[key] = newFormData[key]
        }
      })
    }
  }, { deep: true })

  watch(() => formValues.value.parentDimensionId, (newParentId) => {
    if (newParentId && props.fields) {
      const parentField = props.fields.find(f => f.key === 'parentDimensionId')
      if (parentField && parentField.options) {
        const parentOption = parentField.options.find(opt => opt.value === newParentId)
        if (parentOption) {
          if (!formValues.value.taskTypeCode && formValues.value.dimensionType === 'sub') {
            if (parentOption.taskTypeCode) {
              formValues.value.taskTypeCode = parentOption.taskTypeCode
            }
          }
          if (formValues.value.dimensionType === 'sub') {
            if (parentOption.apiSettings !== undefined && !formValues.value.apiSettings) {
              formValues.value.apiSettings = parentOption.apiSettings
            }
            if (parentOption.requiredInputs !== undefined && !formValues.value.requiredInputs) {
              formValues.value.requiredInputs = parentOption.requiredInputs
            }
          }
        }
      }
    }
  })

  // 联动：requiredInputs 变化时，同步 apiSettings.body_template.rounds[0] 的 key（值用 {{key}} 占位符）
  watch(() => formValues.value.requiredInputs, (newInputs) => {
    if (syncing.value) return
    if (!Array.isArray(newInputs) || !formValues.value.apiSettings) return
    const apiSettings = formValues.value.apiSettings
    if (!apiSettings || typeof apiSettings !== 'object') return
    if (!apiSettings.body_template || typeof apiSettings.body_template !== 'object') {
      apiSettings.body_template = {}
    }
    const bodyTpl = apiSettings.body_template
    if (!bodyTpl.rounds) bodyTpl.rounds = [{}]
    if (!bodyTpl.rounds[0]) bodyTpl.rounds[0] = {}
    const roundTpl = bodyTpl.rounds[0]

    const inputKeys = new Set(newInputs.map(i => i && i.param_code).filter(k => k))

    // 新增缺失的 key（值用 {{key}} 占位符）
    newInputs.forEach(input => {
      const key = input && input.param_code
      if (key && !(key in roundTpl)) {
        roundTpl[key] = `{{${key}}}`
      }
    })

    // 删除已不存在的参数 key（只删值是 {{xxx}} 占位符的，保留用户手写的非参数字段）
    Object.keys(roundTpl).forEach(key => {
      const val = roundTpl[key]
      if (typeof val === 'string' && val.match(/^{{(.+)}}$/) && !inputKeys.has(key)) {
        delete roundTpl[key]
      }
    })

    // 触发 APISettingsEditor 重新渲染（替换对象引用）
    syncing.value = true
    formValues.value.apiSettings = { ...apiSettings, body_template: { ...bodyTpl, rounds: [{ ...roundTpl }] } }
    nextTick(() => { syncing.value = false })
  }, { deep: true })

  // 联动：apiSettings.body_template.rounds[0] 的 key 变化时，同步 requiredInputs 的参数键名
  watch(() => {
    const apiSettings = formValues.value.apiSettings
    const round0 = apiSettings && apiSettings.body_template && apiSettings.body_template.rounds && apiSettings.body_template.rounds[0]
    if (!round0) return ''
    // 用 keys 签名捕获 key 增删/改名（值变化不触发）
    return Object.keys(round0).join('\n')
  }, (sig) => {
    if (syncing.value) return
    const inputs = formValues.value.requiredInputs
    if (!Array.isArray(inputs)) return

    const apiSettings = formValues.value.apiSettings
    const roundTpl = apiSettings?.body_template?.rounds?.[0] || {}

    // rounds[0] 的所有 key 都是参数键名（保留 round 中的顺序）
    const expectedKeys = Object.keys(roundTpl)

    const existingKeys = new Set(inputs.map(i => i && i.param_code).filter(Boolean))
    let changed = false
    const newInputs = []

    // 按 expectedKeys 顺序映射：已有则保留，否则新增
    expectedKeys.forEach(key => {
      const existing = inputs.find(i => i && i.param_code === key)
      if (existing) {
        newInputs.push(existing)
      } else {
        newInputs.push({
          param_code: key,
          param_name: '',
          field_type: 'text',
          required: true,
          default_value: '',
          help_text: ''
        })
        changed = true
      }
      existingKeys.delete(key)
    })

    // 原有但不在 expectedKeys 里的（用户在 JSON 里删/改了 key）→ 删除
    if (existingKeys.size > 0) {
      changed = true
    }

    if (changed || newInputs.length !== inputs.length) {
      syncing.value = true
      formValues.value.requiredInputs = newInputs
      nextTick(() => { syncing.value = false })
    }
  })

  onUnmounted(async () => {
    try {
      await splApi.stopTestTone()
    } catch (error) {
      console.error('停止测试音失败:', error)
    }
  })

  return {
    formValues,
    submitting,
    groupedFields,
    validationErrors,
    showDeviceSelector,
    displayDevices,
    selectedDeviceId,
    isScanning,
    isEditMode,
    handleDeviceSelect,
    handleRescanDevices,
    handleFileUpload,
    handleTestSPL,
    handleStopSPL,
    handleTestSPLComplete,
    handleButtonAction,
    handleSubmit
  }
}
