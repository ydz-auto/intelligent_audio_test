import { ref, computed, watch, onMounted } from 'vue'
import { useTestCaseConfig } from '../../../composables/testCase/useTestCaseConfig'
import type { AudioItem } from '../../../composables/audio/useAudioList'

export interface AlgorithmRelationItem {
  algorithmType: string
  isPrimary: boolean
  weight: number
  params?: Record<string, any>
}

export function useUploadOptions(props: any, emit: any) {
  const localConfig = ref<any>(null)
  const localTags = ref(props.tags)

  watch(() => props.tags, (newVal: any) => {
    if (newVal !== localTags.value) {
      localTags.value = newVal
    }
  })

  watch(localTags, (newVal: any) => {
    emit('update:tags', newVal)
  })

  const uploadConfig = computed({
    get: () => {
      if (!localConfig.value) {
        localConfig.value = props.modelValue
      }
      return localConfig.value
    },
    set: (val: any) => {
      localConfig.value = val
      emit('update:modelValue', val)
    }
  })

  watch(() => props.modelValue, (newVal: any) => {
    if (newVal && JSON.stringify(newVal) !== JSON.stringify(localConfig.value)) {
      localConfig.value = newVal
    }
  }, { deep: true })

  watch(() => uploadConfig.value.audioType, (newType: any) => {
    if (newType === 'noise') {
      uploadConfig.value = {
        ...uploadConfig.value,
        createTestCase: false,
        testTypes: ['api'],
        algorithmType: '',
        algorithmParams: [],
        apiDimensions: [],
        e2eDimensions: []
      }
      apiScopes.value = ['single']
      e2eScopes.value = ['single']
    }
  })

  const {
    audioTypeOptions: computedAudioTypeOptions,
    hasAudioType,
    testTypeOptions,
    filteredDimensions,
    e2eFilteredDimensions,
    dimensionCount,
    isDimensionSelected,
    toggleDimensionSelection,
    ensureDimensionsLoaded,
    dimensionsLoading,
    dimensionsError,
    dimensionSearchQuery,
    e2eDimensionSearchQuery,
    updateDimensionFilter
  } = useTestCaseConfig({
    audioTypeOptions: props.audioTypeOptions.length > 0 ? props.audioTypeOptions : undefined
  })

  const hasApiDimensions = computed(() => (uploadConfig.value.apiDimensions || []).length > 0)
  const hasE2eDimensions = computed(() => (uploadConfig.value.e2eDimensions || []).length > 0)

  // API/E2E 维度的使用范围（可多选：单轮+多轮）
  const apiScopes = ref<('single' | 'multi')[]>(
    (props.modelValue as any).apiScopes || ['single']
  )
  const e2eScopes = ref<('single' | 'multi')[]>(
    (props.modelValue as any).e2eScopes || ['single']
  )

  const toggleApiScope = (scope: 'single' | 'multi') => {
    if (apiScopes.value.includes(scope)) {
      if (apiScopes.value.length > 1) {
        apiScopes.value = apiScopes.value.filter(s => s !== scope)
      }
    } else {
      apiScopes.value = [...apiScopes.value, scope]
    }
    uploadConfig.value = { ...uploadConfig.value, apiScopes: apiScopes.value }
  }

  const toggleE2eScope = (scope: 'single' | 'multi') => {
    if (e2eScopes.value.includes(scope)) {
      if (e2eScopes.value.length > 1) {
        e2eScopes.value = e2eScopes.value.filter(s => s !== scope)
      }
    } else {
      e2eScopes.value = [...e2eScopes.value, scope]
    }
    uploadConfig.value = { ...uploadConfig.value, e2eScopes: e2eScopes.value }
  }

  const setApiDimensions = (dimensions: Array<{ id: string | number; name: string }>) => {
    uploadConfig.value = {
      ...uploadConfig.value,
      apiDimensions: dimensions
    }
  }

  const setE2eDimensions = (dimensions: Array<{ id: string | number; name: string }>) => {
    uploadConfig.value = {
      ...uploadConfig.value,
      e2eDimensions: dimensions
    }
  }

  const toggleApiDimension = (dim: any) => {
    toggleDimensionSelection(dim, uploadConfig.value.apiDimensions, setApiDimensions)
  }

  const toggleE2eDimension = (dim: any) => {
    toggleDimensionSelection(dim, uploadConfig.value.e2eDimensions, setE2eDimensions)
  }

  const showTestCaseConfig = computed(() => uploadConfig.value.createTestCase)
  const showApiConfig = computed(() => uploadConfig.value.testTypes?.includes('api'))
  const showE2eConfig = computed(() => uploadConfig.value.testTypes?.includes('e2e'))

  watch([showApiConfig, showE2eConfig], ([api, e2e]: any) => {
    if (api || e2e) {
      ensureDimensionsLoaded()
    }
  }, { immediate: true })

  const noiseSelectModalVisible = ref(false)
  const algorithmParams = ref<any>({})
  const associatedDimensionIds = ref<number[]>([])
  const algorithmRelations = ref<AlgorithmRelationItem[]>([])

  const handleAlgorithmParamsChange = (params: Record<string, any>) => {
    algorithmParams.value = params
    uploadConfig.value = {
      ...uploadConfig.value,
      algorithmParams: params
    }
  }

  const handleAlgorithmRelationsChange = (relations: AlgorithmRelationItem[]) => {
    algorithmRelations.value = relations
    uploadConfig.value = {
      ...uploadConfig.value,
      algorithmRelations: relations
    }
  }

  const handleDimensionsChange = (dimensions: any[], dimensionIds: number[]) => {
    associatedDimensionIds.value = dimensionIds
    updateDimensionFilter(dimensionIds)
    if (dimensionIds.length > 0) {
      const filteredApi = (uploadConfig.value.apiDimensions || []).filter(
        (d: any) => dimensionIds.includes(Number(d.id))
      )
      const filteredE2e = (uploadConfig.value.e2eDimensions || []).filter(
        (d: any) => dimensionIds.includes(Number(d.id))
      )
      uploadConfig.value = {
        ...uploadConfig.value,
        apiDimensions: filteredApi,
        e2eDimensions: filteredE2e
      }
    }
  }

  const openNoiseSelectModal = () => {
    noiseSelectModalVisible.value = true
  }

  const handleNoiseSelect = (audio: AudioItem) => {
    uploadConfig.value = {
      ...uploadConfig.value,
      noiseAudioId: audio.id,
      noiseAudioName: audio.filename
    }
    noiseSelectModalVisible.value = false
  }

  const clearNoiseAudio = () => {
    uploadConfig.value = {
      ...uploadConfig.value,
      noiseAudioId: undefined,
      noiseAudioName: undefined
    }
  }

  return {
    localTags,
    uploadConfig,
    computedAudioTypeOptions,
    hasAudioType,
    testTypeOptions,
    filteredDimensions,
    e2eFilteredDimensions,
    dimensionCount,
    isDimensionSelected,
    toggleDimensionSelection,
    ensureDimensionsLoaded,
    dimensionsLoading,
    dimensionsError,
    dimensionSearchQuery,
    e2eDimensionSearchQuery,
    updateDimensionFilter,
    hasApiDimensions,
    hasE2eDimensions,
    apiScopes,
    e2eScopes,
    toggleApiScope,
    toggleE2eScope,
    setApiDimensions,
    setE2eDimensions,
    toggleApiDimension,
    toggleE2eDimension,
    showTestCaseConfig,
    showApiConfig,
    showE2eConfig,
    noiseSelectModalVisible,
    algorithmParams,
    associatedDimensionIds,
    algorithmRelations,
    handleAlgorithmParamsChange,
    handleAlgorithmRelationsChange,
    handleDimensionsChange,
    openNoiseSelectModal,
    handleNoiseSelect,
    clearNoiseAudio,
  }
}
