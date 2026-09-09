import { ref, computed, watch } from 'vue'
import { RoundMode, type RoundModeType } from '@/domain/enums'
import type { DimensionItem, DimensionConfigData } from '@/domain/model/audio'

/** 可选维度条目（父组件传入，已过滤、已搜索；面板仅消费 id/name） */
export interface DimensionOption {
  id: string | number
  name: string
}

/** 权重/阈值内部配置（key 为维度 id 字符串） */
export interface DimensionWeightThreshold {
  weight: number
  threshold: number
}

/** 默认权重 */
const DEFAULT_WEIGHT = 50
/** 默认阈值 */
const DEFAULT_THRESHOLD = 60
/** 「最后一轮」特殊轮次标记（后端按用例实际轮次数动态解析） */
const LAST_ROUND = -1

export interface DimensionConfigPanelProps {
  /** v-model 绑定（DimensionConfigData） */
  modelValue?: Partial<DimensionConfigData>
  /** 可选维度列表（已过滤、已搜索） */
  availableDimensions: DimensionOption[]
  /** 是否正在加载维度 */
  loading?: boolean
  /** 加载错误信息 */
  error?: string
  /** 是否必选 */
  required?: boolean
  /** 搜索关键字（v-model:searchQuery） */
  searchQuery?: string
  /** 最大轮次数（用于初始化逐轮 tabs） */
  maxRoundNumbers?: number
}

export type DimensionConfigPanelEmit = {
  (e: 'update:modelValue', value: DimensionConfigData): void
  (e: 'update:searchQuery', value: string): void
}

/**
 * 维度设置面板逻辑（Presentation 层 composable）：
 * 统一（all）/ 指定轮次（specific）/ 逐轮（per_round）三种单轮模式 + 多轮整体评估维度，
 * 每个维度可配置权重/阈值；输出 DimensionConfigData（camelCase Domain 结构）。
 */
export function useDimensionConfigPanel(props: DimensionConfigPanelProps, emit: DimensionConfigPanelEmit) {
  // === 从 modelValue 同步状态 ===
  const roundMode = ref<RoundModeType>(props.modelValue?.roundMode || RoundMode.ALL)
  const roundNumbers = ref<number[]>(props.modelValue?.roundNumbers || [])
  const selectedDimensions = ref<DimensionItem[]>(props.modelValue?.dimensions || [])
  const dimConfigs = ref<Record<string, DimensionWeightThreshold>>({})
  const multiSelectedDimensions = ref<DimensionItem[]>(props.modelValue?.multiDimensions || [])
  const multiDimConfigs = ref<Record<string, DimensionWeightThreshold>>({})

  // === 逐轮设置模式状态 ===
  const activeRoundTab = ref<number>(1)
  const roundSelectedDimensions = ref<Record<number, DimensionItem[]>>({})
  const roundDimConfigs = ref<Record<number, Record<string, DimensionWeightThreshold>>>({})
  const showCopySource = ref(false)
  const copySourceRound = ref<number>(1)

  // 可变轮次列表
  const availableRoundNumbers = ref<number[]>(
    Array.from({ length: props.maxRoundNumbers ?? 3 }, (_, i) => i + 1)
  )

  // 所有轮次标签（包括最后一轮）
  const allRoundTabs = computed(() => [...availableRoundNumbers.value, LAST_ROUND])

  // === 搜索 ===
  const localSearchQuery = computed({
    get: () => props.searchQuery ?? '',
    set: (val) => emit('update:searchQuery', val)
  })

  // === 统一模式方法 ===
  function toggleRoundNumber(rn: number) {
    const idx = roundNumbers.value.indexOf(rn)
    if (idx >= 0) {
      roundNumbers.value.splice(idx, 1)
    } else {
      roundNumbers.value.push(rn)
    }
    emitUpdate()
  }

  const isDimensionSelected = (dim: DimensionOption) => {
    return selectedDimensions.value.some(d => d.id === dim.id)
  }

  function toggleDimension(dim: DimensionOption) {
    if (isDimensionSelected(dim)) {
      selectedDimensions.value = selectedDimensions.value.filter(d => d.id !== dim.id)
      delete dimConfigs.value[dim.id]
    } else {
      selectedDimensions.value.push(dim)
      dimConfigs.value[dim.id] = { weight: DEFAULT_WEIGHT, threshold: DEFAULT_THRESHOLD }
    }
    emitUpdate()
  }

  function removeDimension(index: number) {
    const dim = selectedDimensions.value[index]
    delete dimConfigs.value[dim.id]
    selectedDimensions.value.splice(index, 1)
    emitUpdate()
  }

  // === 逐轮设置模式方法 ===
  function ensureRoundState(rn: number) {
    if (!roundSelectedDimensions.value[rn]) {
      roundSelectedDimensions.value[rn] = []
    }
    if (!roundDimConfigs.value[rn]) {
      roundDimConfigs.value[rn] = {}
    }
  }

  function isRoundDimensionSelected(rn: number, dim: DimensionOption) {
    ensureRoundState(rn)
    return roundSelectedDimensions.value[rn].some(d => d.id === dim.id)
  }

  function toggleRoundDimension(rn: number, dim: DimensionOption) {
    ensureRoundState(rn)
    if (isRoundDimensionSelected(rn, dim)) {
      roundSelectedDimensions.value[rn] = roundSelectedDimensions.value[rn].filter(d => d.id !== dim.id)
      delete roundDimConfigs.value[rn][dim.id]
    } else {
      roundSelectedDimensions.value[rn].push(dim)
      roundDimConfigs.value[rn][dim.id] = { weight: DEFAULT_WEIGHT, threshold: DEFAULT_THRESHOLD }
    }
    emitUpdate()
  }

  function getRoundSelectedDimensions(rn: number): DimensionItem[] {
    ensureRoundState(rn)
    return roundSelectedDimensions.value[rn]
  }

  function removeRoundDimension(rn: number, index: number) {
    ensureRoundState(rn)
    const dim = roundSelectedDimensions.value[rn][index]
    delete roundDimConfigs.value[rn][dim.id]
    roundSelectedDimensions.value[rn].splice(index, 1)
    emitUpdate()
  }

  function addRound() {
    const next = availableRoundNumbers.value.length > 0
      ? Math.max(...availableRoundNumbers.value) + 1
      : 1
    availableRoundNumbers.value.push(next)
    ensureRoundState(next)
    activeRoundTab.value = next
  }

  function removeRound(rn: number) {
    const idx = availableRoundNumbers.value.indexOf(rn)
    if (idx < 0) return
    availableRoundNumbers.value.splice(idx, 1)
    delete roundSelectedDimensions.value[rn]
    delete roundDimConfigs.value[rn]
    // 如果删的是当前激活的 tab，切到第一个可用的
    if (activeRoundTab.value === rn) {
      activeRoundTab.value = availableRoundNumbers.value.length > 0
        ? availableRoundNumbers.value[0]
        : LAST_ROUND
    }
    // 至少保留1个轮次，没有则自动补一个
    if (availableRoundNumbers.value.length === 0) {
      availableRoundNumbers.value = [1]
      ensureRoundState(1)
      if (activeRoundTab.value === LAST_ROUND) {
        activeRoundTab.value = 1
      }
    }
    emitUpdate()
  }

  function copyFromRound() {
    showCopySource.value = true
    const otherRounds = allRoundTabs.value.filter(r => r !== activeRoundTab.value)
    if (otherRounds.length > 0) {
      copySourceRound.value = otherRounds[0]
    }
  }

  function doCopyFromRound() {
    const srcRn = copySourceRound.value
    const dstRn = activeRoundTab.value
    ensureRoundState(srcRn)
    ensureRoundState(dstRn)
    roundSelectedDimensions.value[dstRn] = roundSelectedDimensions.value[srcRn].map(d => ({ ...d }))
    roundDimConfigs.value[dstRn] = {}
    for (const key in roundDimConfigs.value[srcRn]) {
      roundDimConfigs.value[dstRn][key] = { ...roundDimConfigs.value[srcRn][key] }
    }
    showCopySource.value = false
    emitUpdate()
  }

  function clearRound(rn: number) {
    ensureRoundState(rn)
    roundSelectedDimensions.value[rn] = []
    roundDimConfigs.value[rn] = {}
    emitUpdate()
  }

  function applyToAllRounds(srcRn: number) {
    ensureRoundState(srcRn)
    for (const rn of allRoundTabs.value) {
      if (rn === srcRn) continue
      ensureRoundState(rn)
      roundSelectedDimensions.value[rn] = roundSelectedDimensions.value[srcRn].map(d => ({ ...d }))
      roundDimConfigs.value[rn] = {}
      for (const key in roundDimConfigs.value[srcRn]) {
        roundDimConfigs.value[rn][key] = { ...roundDimConfigs.value[srcRn][key] }
      }
    }
    emitUpdate()
  }

  // 切换到逐轮设置时初始化各轮次状态
  watch(roundMode, (newMode) => {
    if (newMode === RoundMode.PER_ROUND) {
      for (const rn of allRoundTabs.value) {
        ensureRoundState(rn)
      }
    }
    if (newMode !== RoundMode.PER_ROUND) {
      showCopySource.value = false
    }
    emitUpdate()
  })

  // === 多轮整体评估维度方法 ===
  const isMultiDimensionSelected = (dim: DimensionOption) => {
    return multiSelectedDimensions.value.some(d => d.id === dim.id)
  }

  function toggleMultiDimension(dim: DimensionOption) {
    if (isMultiDimensionSelected(dim)) {
      multiSelectedDimensions.value = multiSelectedDimensions.value.filter(d => d.id !== dim.id)
      delete multiDimConfigs.value[dim.id]
    } else {
      multiSelectedDimensions.value.push(dim)
      multiDimConfigs.value[dim.id] = { weight: DEFAULT_WEIGHT, threshold: DEFAULT_THRESHOLD }
    }
    emitUpdate()
  }

  function removeMultiDimension(index: number) {
    const dim = multiSelectedDimensions.value[index]
    delete multiDimConfigs.value[dim.id]
    multiSelectedDimensions.value.splice(index, 1)
    emitUpdate()
  }

  // === 发射更新 ===
  function emitUpdate() {
    const multiDims: DimensionItem[] = multiSelectedDimensions.value.map(dim => ({
      id: dim.id,
      name: dim.name,
      weight: multiDimConfigs.value[dim.id]?.weight ?? DEFAULT_WEIGHT,
      threshold: multiDimConfigs.value[dim.id]?.threshold ?? DEFAULT_THRESHOLD
    }))

    if (roundMode.value === RoundMode.PER_ROUND) {
      const rd: Record<number, DimensionItem[]> = {}
      for (const rn of allRoundTabs.value) {
        ensureRoundState(rn)
        rd[rn] = roundSelectedDimensions.value[rn].map(dim => ({
          id: dim.id,
          name: dim.name,
          weight: roundDimConfigs.value[rn][dim.id]?.weight ?? DEFAULT_WEIGHT,
          threshold: roundDimConfigs.value[rn][dim.id]?.threshold ?? DEFAULT_THRESHOLD
        }))
      }
      emit('update:modelValue', {
        dimensions: [],
        roundMode: RoundMode.PER_ROUND,
        roundNumbers: [],
        roundDimensions: rd,
        multiDimensions: multiDims
      })
    } else {
      const dims: DimensionItem[] = selectedDimensions.value.map(dim => ({
        id: dim.id,
        name: dim.name,
        weight: dimConfigs.value[dim.id]?.weight ?? DEFAULT_WEIGHT,
        threshold: dimConfigs.value[dim.id]?.threshold ?? DEFAULT_THRESHOLD
      }))
      emit('update:modelValue', {
        dimensions: dims,
        roundMode: roundMode.value,
        roundNumbers: roundNumbers.value,
        multiDimensions: multiDims
      })
    }
  }

  // === 计算属性 ===
  const hasDimensions = computed(() => {
    if (roundMode.value === RoundMode.PER_ROUND) {
      return allRoundTabs.value.some(rn => getRoundSelectedDimensions(rn).length > 0)
    }
    return selectedDimensions.value.length > 0
  })
  const dimensionCount = computed(() => {
    if (roundMode.value === RoundMode.PER_ROUND) {
      return allRoundTabs.value.reduce((sum, rn) => sum + getRoundSelectedDimensions(rn).length, 0)
    }
    return selectedDimensions.value.length
  })

  return {
    RoundMode,
    LAST_ROUND,
    roundMode,
    roundNumbers,
    selectedDimensions,
    dimConfigs,
    multiSelectedDimensions,
    multiDimConfigs,
    activeRoundTab,
    availableRoundNumbers,
    allRoundTabs,
    localSearchQuery,
    roundDimConfigs,
    showCopySource,
    copySourceRound,
    toggleRoundNumber,
    isDimensionSelected,
    toggleDimension,
    removeDimension,
    isRoundDimensionSelected,
    toggleRoundDimension,
    getRoundSelectedDimensions,
    removeRoundDimension,
    addRound,
    removeRound,
    copyFromRound,
    doCopyFromRound,
    clearRound,
    applyToAllRounds,
    isMultiDimensionSelected,
    toggleMultiDimension,
    removeMultiDimension,
    emitUpdate,
    hasDimensions,
    dimensionCount
  }
}
