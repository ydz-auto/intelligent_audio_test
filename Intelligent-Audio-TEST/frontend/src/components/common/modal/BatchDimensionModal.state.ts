/**
 * BatchDimensionModal —— 共享状态与轮次管理
 *
 * 集中声明组件级共享 refs（跨 selection/loaders/save 复用同一份响应式引用），
 * 并提供"所有轮次标签"的派生计算与轮次列表的增删、轮次状态初始化。
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { ROUND_MODE, LAST_ROUND_NUMBER } from './BatchDimensionModal.constants'
import type { DimensionTag, DimConfig, RoundMode, Props } from './BatchDimensionModal.types'

/** 组件共享状态（refs 集合） */
export interface BatchDimensionState {
  availableDimensions: Ref<DimensionTag[]>
  selectedDimensions: Ref<DimensionTag[]>
  dimConfigs: Ref<Record<string, DimConfig>>
  roundMode: Ref<RoundMode>
  roundNumbers: Ref<number[]>
  activeRoundTab: Ref<number>
  roundSelectedDimensions: Ref<Record<number, DimensionTag[]>>
  roundDimConfigs: Ref<Record<number, Record<string, DimConfig>>>
  showCopySource: Ref<boolean>
  copySourceRound: Ref<number>
  multiSelectedDimensions: Ref<DimensionTag[]>
  multiDimConfigs: Ref<Record<string, DimConfig>>
  availableRoundNumbers: Ref<number[]>
  allRoundTabs: ComputedRef<number[]>
}

/** 轮次管理方法 */
export interface RoundControl {
  addRound(): void
  removeRound(rn: number): void
  ensureRoundState(rn: number): void
}

/** 创建组件共享状态与轮次管理 */
export function createBatchDimensionState(props: Props): BatchDimensionState & RoundControl {
  const availableDimensions = ref<DimensionTag[]>([])

  // === 统一模式状态 ===
  const selectedDimensions = ref<DimensionTag[]>([])
  const dimConfigs = ref<Record<string, DimConfig>>({})
  const roundMode = ref<RoundMode>(ROUND_MODE.ALL)
  const roundNumbers = ref<number[]>([])

  // === 逐轮设置模式状态 ===
  // -1 代表"最后一轮"，正数代表具体轮次
  const activeRoundTab = ref<number>(1)
  const roundSelectedDimensions = ref<Record<number, DimensionTag[]>>({})
  const roundDimConfigs = ref<Record<number, Record<string, DimConfig>>>({})
  const showCopySource = ref(false)
  const copySourceRound = ref<number>(1)

  // === 多轮整体评估维度状态 ===
  const multiSelectedDimensions = ref<DimensionTag[]>([])
  const multiDimConfigs = ref<Record<string, DimConfig>>({})

  // 可变轮次列表（从 props.maxRoundNumbers 初始化，用户可动态增减）
  const availableRoundNumbers = ref<number[]>(
    Array.from({ length: props.maxRoundNumbers ?? 3 }, (_, i) => i + 1)
  )

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
        : LAST_ROUND_NUMBER
    }
  }

  // 所有轮次标签（包括最后一轮）
  const allRoundTabs = computed(() => {
    return [...availableRoundNumbers.value, LAST_ROUND_NUMBER]
  })

  function ensureRoundState(rn: number) {
    if (!roundSelectedDimensions.value[rn]) {
      roundSelectedDimensions.value[rn] = []
    }
    if (!roundDimConfigs.value[rn]) {
      roundDimConfigs.value[rn] = {}
    }
  }

  return {
    availableDimensions,
    selectedDimensions,
    dimConfigs,
    roundMode,
    roundNumbers,
    activeRoundTab,
    roundSelectedDimensions,
    roundDimConfigs,
    showCopySource,
    copySourceRound,
    multiSelectedDimensions,
    multiDimConfigs,
    availableRoundNumbers,
    allRoundTabs,
    addRound,
    removeRound,
    ensureRoundState,
  }
}