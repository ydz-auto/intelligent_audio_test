import { ref, computed, watch } from 'vue'
import { useTestCaseConfig } from '../../../composables/testCase/useTestCaseConfig'
import type { AudioItem } from '../../../composables/audio/useAudioList'
import type { AudioAlgorithmRelation, DimensionConfigData } from '../../../domain/model/audio'
import { TestType, RoundMode } from '../../../domain/enums'

// 音频-算法关联：归集到 Domain 的 AudioAlgorithmRelation（params 值类型 any → unknown 兼容），
// AlgorithmRelationItem 仅作兼容别名 re-export（UploadOptions.vue 引用）
export type AlgorithmRelationItem = AudioAlgorithmRelation

/** 空维度配置（DimensionConfigPanel 初始结构） */
const EMPTY_DIMENSION_CONFIG: DimensionConfigData = {
  dimensions: [],
  roundMode: RoundMode.ALL,
  roundNumbers: [],
  multiDimensions: []
}

/** 判断维度配置是否已选维度（per_round 模式遍历逐轮配置） */
function hasConfiguredDimensions(cfg?: DimensionConfigData): boolean {
  if (!cfg) return false
  if (cfg.roundMode === RoundMode.PER_ROUND) {
    return Object.values(cfg.roundDimensions || {}).some(dims => dims.length > 0)
  }
  return (cfg.dimensions || []).length > 0
}

/** 按算法关联维度过滤维度配置（dimensions/roundDimensions/multiDimensions 同步过滤） */
function filterDimensionConfig(
  cfg: DimensionConfigData | undefined,
  dimensionIds: number[]
): DimensionConfigData | undefined {
  if (!cfg) return cfg
  const keep = (dims?: DimensionConfigData['dimensions']) =>
    (dims || []).filter(d => dimensionIds.includes(Number(d.id)))
  const roundDimensions = cfg.roundDimensions
    ? (Object.fromEntries(
        Object.entries(cfg.roundDimensions).map(([rn, dims]) => [rn, keep(dims)])
      ) as DimensionConfigData['roundDimensions'])
    : undefined
  return {
    ...cfg,
    dimensions: keep(cfg.dimensions),
    roundDimensions,
    multiDimensions: keep(cfg.multiDimensions)
  }
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
        testTypes: [TestType.E2E],
        algorithmType: '',
        algorithmParams: [],
        apiDimensionConfig: { ...EMPTY_DIMENSION_CONFIG },
        e2eDimensionConfig: { ...EMPTY_DIMENSION_CONFIG }
      }
    }
  })

  const {
    audioTypeOptions: computedAudioTypeOptions,
    hasAudioType,
    testTypeOptions,
    filteredDimensions,
    e2eFilteredDimensions,
    ensureDimensionsLoaded,
    dimensionsLoading,
    dimensionsError,
    dimensionSearchQuery,
    e2eDimensionSearchQuery,
    updateDimensionFilter
  } = useTestCaseConfig({
    audioTypeOptions: props.audioTypeOptions.length > 0 ? props.audioTypeOptions : undefined
  })

  const hasApiDimensions = computed(() => hasConfiguredDimensions(uploadConfig.value.apiDimensionConfig))
  const hasE2eDimensions = computed(() => hasConfiguredDimensions(uploadConfig.value.e2eDimensionConfig))

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
      uploadConfig.value = {
        ...uploadConfig.value,
        apiDimensionConfig: filterDimensionConfig(uploadConfig.value.apiDimensionConfig, dimensionIds),
        e2eDimensionConfig: filterDimensionConfig(uploadConfig.value.e2eDimensionConfig, dimensionIds)
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
    ensureDimensionsLoaded,
    dimensionsLoading,
    dimensionsError,
    dimensionSearchQuery,
    e2eDimensionSearchQuery,
    updateDimensionFilter,
    hasApiDimensions,
    hasE2eDimensions,
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
