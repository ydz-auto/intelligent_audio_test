import { ref, computed, watch } from 'vue'
import { useTestCaseConfig } from '../../../composables/testCase/useTestCaseConfig'
import type { AudioItem } from '../../../composables/audio/useAudioList'
import type { AudioAlgorithmRelation, DimensionConfigData } from '../../../domain/model/audio'
import { TestType, RoundMode, AudioTagSource } from '../../../domain/enums'

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

/**
 * 标签来源三选一（INT-1983，值 = 后端 tag_source 原值）：
 * 上传音频与批量从文件夹导入两个弹窗共用这一处实现，文案写清三档差异。
 */
const TAG_SOURCE_OPTIONS: Array<{ value: string; label: string; hint: string }> = [
  {
    value: AudioTagSource.BOTH,
    label: '两者都要',
    hint: '请求标签 = 手填标签 + 标注 JSON 顶层 tags；后端同时按目录路径解析标签'
  },
  {
    value: AudioTagSource.JSON,
    label: '仅 JSON tags',
    hint: '请求标签 = 手填标签 + 标注 JSON 顶层 tags；后端不再按目录路径解析'
  },
  {
    value: AudioTagSource.PATH,
    label: '仅路径解析',
    hint: '请求标签只用填写的标签，不并入标注 JSON tags；后端按目录路径解析'
  }
]

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
    filteredDimensions,
    ensureDimensionsLoaded,
    dimensionsLoading,
    dimensionsError,
    dimensionSearchQuery,
    updateDimensionFilter
  } = useTestCaseConfig({
    audioTypeOptions: props.audioTypeOptions.length > 0 ? props.audioTypeOptions : undefined
  })

  const showTestCaseConfig = computed(() => uploadConfig.value.createTestCase)

  // 标签来源：当前选中项说明（未选按默认 both 展示，实际下发口径由 uploadProcess 统一按默认 both 处理）
  const tagSourceHint = computed(() => {
    const current = uploadConfig.value.tagSource ?? AudioTagSource.BOTH
    return (TAG_SOURCE_OPTIONS.find(o => o.value === current) || TAG_SOURCE_OPTIONS[0]).hint
  })

  watch(showTestCaseConfig, (show) => {
    if (show) {
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
    filteredDimensions,
    ensureDimensionsLoaded,
    dimensionsLoading,
    dimensionsError,
    dimensionSearchQuery,
    updateDimensionFilter,
    showTestCaseConfig,
    tagSourceOptions: TAG_SOURCE_OPTIONS,
    tagSourceHint,
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
