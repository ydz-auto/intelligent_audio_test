import { ref, computed } from 'vue'
import { evaluationApi } from '../utils/api'
import { useDimensions } from './useDimensions'

export interface SelectedDimension {
  id: number | string
  name: string
  weight?: number
  threshold?: number
}

export interface DimensionsConfig {
  api: SelectedDimension[]
  e2e: SelectedDimension[]
}

export interface TestTypeOption {
  label: string
  value: 'api' | 'e2e'
}

export interface TranslationDirectionOption {
  label: string
  value: string | number
}

export interface GroupNameTypeOption {
  label: string
  value: 'root' | 'folder' | 'custom'
}

export interface AudioTypeOption {
  label: string
  value: string
}

export interface UseTestCaseConfigOptions {
  translationDirectionOptions?: TranslationDirectionOption[]
  defaultSpl?: number
  audioTypeOptions?: AudioTypeOption[]
  dimensionFilterIds?: number[]
}

export function useTestCaseConfig(options: UseTestCaseConfigOptions = {}) {
  const {
    translationDirectionOptions: initialTranslationOptions = [],
    defaultSpl = 65.0,
    audioTypeOptions: initialAudioTypeOptions = [],
    dimensionFilterIds: initialDimensionFilterIds = []
  } = options

  const availableDimensions = ref<any[]>([])
  const dimensionFilterIdSet = ref<Set<number>>(new Set(initialDimensionFilterIds))
  const dimensionSearchQuery = ref('')
  const e2eDimensionSearchQuery = ref('')
  const dimensionsLoading = ref(false)
  const dimensionsError = ref('')

  const translationDirectionOptions = ref<TranslationDirectionOption[]>(initialTranslationOptions)
  const hasTranslationDirection = computed(() => translationDirectionOptions.value.length > 0)

  const audioTypeOptions = ref<AudioTypeOption[]>(initialAudioTypeOptions.length > 0 ? initialAudioTypeOptions : [
    { label: '干声', value: 'dry' },
    { label: '噪声', value: 'noise' },
    { label: '提示词', value: 'prompt' },
    { label: '混合', value: 'mixed' }
  ])
  const hasAudioType = computed(() => audioTypeOptions.value.length > 0)

  const groupNameTypeOptions: GroupNameTypeOption[] = [
    { label: '根目录', value: 'root' },
    { label: '文件夹名', value: 'folder' },
    { label: '自定义', value: 'custom' }
  ]

  const testTypeOptions: TestTypeOption[] = [
    { label: 'API测试', value: 'api' },
    { label: 'E2E测试', value: 'e2e' }
  ]

  const updateDimensionFilter = (ids: number[]) => {
    dimensionFilterIdSet.value = new Set(ids)
  }

  const filteredDimensions = computed(() => {
    let dims = availableDimensions.value
    if (dimensionFilterIdSet.value.size > 0) {
      dims = dims.filter(dim => dimensionFilterIdSet.value.has(Number(dim.id)))
    }
    if (!dimensionSearchQuery.value) return dims
    const query = dimensionSearchQuery.value.toLowerCase()
    return dims.filter(dim =>
      String(dim?.name || '').toLowerCase().includes(query) ||
      String(dim?.description || '').toLowerCase().includes(query) ||
      String(dim?.keywords || '').toLowerCase().includes(query) ||
      String(dim?.id || '').toLowerCase().includes(query)
    )
  })

  const e2eFilteredDimensions = computed(() => {
    let dims = availableDimensions.value
    if (dimensionFilterIdSet.value.size > 0) {
      dims = dims.filter(dim => dimensionFilterIdSet.value.has(Number(dim.id)))
    }
    if (!e2eDimensionSearchQuery.value) return dims
    const query = e2eDimensionSearchQuery.value.toLowerCase()
    return dims.filter(dim =>
      String(dim?.name || '').toLowerCase().includes(query) ||
      String(dim?.description || '').toLowerCase().includes(query) ||
      String(dim?.keywords || '').toLowerCase().includes(query) ||
      String(dim?.id || '').toLowerCase().includes(query)
    )
  })

  const apiSelectedDimensions = computed(() => {
    return (dimensions: DimensionsConfig | undefined) =>
      dimensions?.api || []
  })

  const e2eSelectedDimensions = computed(() => {
    return (dimensions: DimensionsConfig | undefined) =>
      dimensions?.e2e || []
  })

  const apiDimensionCount = computed(() => {
    return (dimensions: DimensionsConfig | undefined) =>
      (dimensions?.api || []).length
  })

  const e2eDimensionCount = computed(() => {
    return (dimensions: DimensionsConfig | undefined) =>
      (dimensions?.e2e || []).length
  })

  const isApiDimensionSelected = (dimension: any, dimensions: DimensionsConfig | undefined) => {
    const id = dimension?.id
    return (dimensions?.api || []).some((d: any) => d?.id === id)
  }

  const isE2eDimensionSelected = (dimension: any, dimensions: DimensionsConfig | undefined) => {
    const id = dimension?.id
    return (dimensions?.e2e || []).some((d: any) => d?.id === id)
  }

  const toggleApiDimensionSelection = (dimension: any, dimensions: DimensionsConfig | undefined, setDimensions: (dims: DimensionsConfig) => void) => {
    if (!dimension || !dimensions) return
    const list = [...(dimensions.api || [])]
    
    const existingIndex = list.findIndex(d => d?.id === dimension.id)
    if (existingIndex >= 0) {
      list.splice(existingIndex, 1)
    } else {
      list.push({
        id: dimension.id,
        name: dimension.name,
        weight: 50,
        threshold: 80
      })
    }
    
    setDimensions({
      ...dimensions,
      api: list
    })
  }

  const toggleE2eDimensionSelection = (dimension: any, dimensions: DimensionsConfig | undefined, setDimensions: (dims: DimensionsConfig) => void) => {
    if (!dimension || !dimensions) return
    const list = [...(dimensions.e2e || [])]
    
    const existingIndex = list.findIndex(d => d?.id === dimension.id)
    if (existingIndex >= 0) {
      list.splice(existingIndex, 1)
    } else {
      list.push({
        id: dimension.id,
        name: dimension.name,
        weight: 50,
        threshold: 80
      })
    }
    
    setDimensions({
      ...dimensions,
      e2e: list
    })
  }

  const ensureDimensionsLoaded = async () => {
    if (dimensionsLoading.value) return
    if (availableDimensions.value.length > 0) return
    dimensionsLoading.value = true
    dimensionsError.value = ''
    try {
      const { fetchAllDimensions } = useDimensions()
      const dimensions = await fetchAllDimensions()
      availableDimensions.value = dimensions
    } catch (e) {
      dimensionsError.value = '加载评估维度失败'
      availableDimensions.value = []
    } finally {
      dimensionsLoading.value = false
    }
  }

  return {
    availableDimensions,
    dimensionSearchQuery,
    e2eDimensionSearchQuery,
    dimensionsLoading,
    dimensionsError,
    updateDimensionFilter,
    translationDirectionOptions,
    hasTranslationDirection,
    computedTranslationOptions: translationDirectionOptions,
    audioTypeOptions,
    hasAudioType,
    groupNameTypeOptions,
    testTypeOptions,
    filteredDimensions,
    e2eFilteredDimensions,
    apiSelectedDimensions,
    e2eSelectedDimensions,
    apiDimensionCount,
    e2eDimensionCount,
    isApiDimensionSelected,
    isE2eDimensionSelected,
    toggleApiDimensionSelection,
    toggleE2eDimensionSelection,
    ensureDimensionsLoaded,
    defaultSpl
  }
}

export function createDefaultUploadConfig() {
  return {
    testTypes: ['api'] as ('api' | 'e2e')[],
    dimensions: { api: [], e2e: [] } as DimensionsConfig,
    spl: 65.0,
    noiseSpl: 60.0,
    noiseAudioId: null as string | number | null,
    noiseAudioName: '',
    groupNameType: 'root' as 'root' | 'folder' | 'custom',
    inheritTags: true,
    createTestCase: false,
    translationDirectionId: '' as string | number,
    customGroupName: '',
    audioType: 'dry' as string,
    playbackDeviceId: null as string | number | null,
    promptDeviceId: '' as string | number,
    promptSourceLanguage: '',
    promptTargetLanguage: '',
    promptTranslationDirection: '',
    algorithmType: '',
    algorithmRelations: [] as Array<{ algorithmType: string; isPrimary: boolean; weight: number; params?: Record<string, any> }>,
    algorithmParams: [] as any[]
  }
}
