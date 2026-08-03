import { ref, computed } from 'vue'
import { devicesApi, splApi } from '../../../../utils/api'

/**
 * 动态字段加载 composable
 * 负责动态选项加载（驱动关键字、SPL映射、算法类型）和字段分组计算
 */
export function useDynamicFieldLoader(props: any, checkCondition: any) {
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

  const loadDriverKeywords = async () => {
    const keywordField = props.fields.find((field: any) => field.action === 'loadDriverKeywords')
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
    const splMappingField = props.fields.find((field: any) => field.action === 'loadSplMappings')
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

  const loadAlgorithmTypes = async () => {
    if (dynamicFieldOptions.value.algorithmTypes.length > 0) return

    try {
      const response = await fetch('/api/v1/algorithm/options')
      const result = await response.json()
      if (result.success && result.data && result.data.algorithms) {
        dynamicFieldOptions.value.algorithmTypes = result.data.algorithms.map((algo: any) => ({
          value: algo.value || algo.type,
          label: algo.name || algo.label || algo.value || algo.type
        }))
      }
    } catch (error) {
      console.error('加载算法类型选项失败:', error)
    }
  }

  return {
    dynamicFieldOptions,
    dynamicFields,
    groupedFields,
    loadDriverKeywords,
    loadSplMappings,
    loadAlgorithmTypes
  }
}
