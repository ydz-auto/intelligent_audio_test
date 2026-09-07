/**
 * BatchDimensionModal —— 勾选交互
 *
 * 统一模式 / 逐轮设置模式 / 多轮整体评估 三条分支的维度勾选、移除，
 * 以及逐轮模式下的轮次复制、清空、批量应用等快捷操作。
 */
import { computed, watch } from 'vue'
import { DEFAULT_WEIGHT, DEFAULT_THRESHOLD, ROUND_MODE } from './BatchDimensionModal.constants'
import type { DimensionTag, Props } from './BatchDimensionModal.types'
import type { BatchDimensionState, RoundControl } from './BatchDimensionModal.state'
import { toDimension } from './BatchDimensionModal.loaders'

/** 勾选交互上下文（依赖共享状态 + 算法维度缓存读取） */
export interface DimensionSelectionContext {
  props: Props
  state: BatchDimensionState & RoundControl
  getDimensionsByAlgorithmType: (algorithmType: string) => any[]
}

/** 创建勾选交互：统一模式 / 逐轮模式 / 多轮整体评估的维度选择逻辑 */
export function createDimensionSelection(ctx: DimensionSelectionContext) {
  const { props, state } = ctx

  // === 统一模式 ===

  // 指定轮次的勾选
  function toggleRoundNumber(rn: number) {
    const idx = state.roundNumbers.value.indexOf(rn)
    if (idx >= 0) {
      state.roundNumbers.value.splice(idx, 1)
    } else {
      state.roundNumbers.value.push(rn)
    }
  }

  // 按算法类型过滤可用维度（无关联维度时回退全量）
  const filteredAvailableDimensions = computed((): DimensionTag[] => {
    if (!props.algorithmType) {
      return state.availableDimensions.value
    }
    const associatedIds = new Set(state.availableDimensions.value.map(d => d.id))
    // Domain 维度（EvaluationDimension）经 toDimension 归一为 DimensionTag，保证三元分支类型一致
    const dimsByAlgo = ctx.getDimensionsByAlgorithmType(props.algorithmType).map(toDimension)
    const filtered = dimsByAlgo.filter((dim: DimensionTag) => associatedIds.has(dim.id))
    return filtered.length > 0 ? filtered : state.availableDimensions.value
  })

  const isDimensionSelected = (dim: DimensionTag) => {
    return state.selectedDimensions.value.some(d => d.id === dim.id)
  }

  const toggleDimension = (dim: DimensionTag) => {
    if (isDimensionSelected(dim)) {
      state.selectedDimensions.value = state.selectedDimensions.value.filter(d => d.id !== dim.id)
      delete state.dimConfigs.value[dim.id]
    } else {
      state.selectedDimensions.value.push(dim)
      state.dimConfigs.value[dim.id] = { weight: DEFAULT_WEIGHT, threshold: DEFAULT_THRESHOLD }
    }
  }

  const removeDimension = (index: number) => {
    const dim = state.selectedDimensions.value[index]
    delete state.dimConfigs.value[dim.id]
    state.selectedDimensions.value.splice(index, 1)
  }

  // === 逐轮设置模式 ===

  function isRoundDimensionSelected(rn: number, dim: DimensionTag) {
    state.ensureRoundState(rn)
    return state.roundSelectedDimensions.value[rn].some(d => d.id === dim.id)
  }

  function toggleRoundDimension(rn: number, dim: DimensionTag) {
    state.ensureRoundState(rn)
    if (isRoundDimensionSelected(rn, dim)) {
      state.roundSelectedDimensions.value[rn] = state.roundSelectedDimensions.value[rn].filter(d => d.id !== dim.id)
      delete state.roundDimConfigs.value[rn][dim.id]
    } else {
      state.roundSelectedDimensions.value[rn].push(dim)
      state.roundDimConfigs.value[rn][dim.id] = { weight: DEFAULT_WEIGHT, threshold: DEFAULT_THRESHOLD }
    }
  }

  function getRoundSelectedDimensions(rn: number): DimensionTag[] {
    state.ensureRoundState(rn)
    return state.roundSelectedDimensions.value[rn]
  }

  function removeRoundDimension(rn: number, index: number) {
    state.ensureRoundState(rn)
    const dim = state.roundSelectedDimensions.value[rn][index]
    delete state.roundDimConfigs.value[rn][dim.id]
    state.roundSelectedDimensions.value[rn].splice(index, 1)
  }

  function copyFromRound(_rn: number) {
    state.showCopySource.value = true
    const otherRounds = state.allRoundTabs.value.filter(r => r !== state.activeRoundTab.value)
    if (otherRounds.length > 0) {
      state.copySourceRound.value = otherRounds[0]
    }
  }

  // 复制源轮次的维度和配置到目标轮次（提取公共逻辑，消除重复）
  function copyRoundState(srcRn: number, dstRn: number) {
    state.ensureRoundState(srcRn)
    state.ensureRoundState(dstRn)
    state.roundSelectedDimensions.value[dstRn] = state.roundSelectedDimensions.value[srcRn].map(d => ({ ...d }))
    state.roundDimConfigs.value[dstRn] = {}
    for (const key in state.roundDimConfigs.value[srcRn]) {
      state.roundDimConfigs.value[dstRn][key] = { ...state.roundDimConfigs.value[srcRn][key] }
    }
  }

  function doCopyFromRound() {
    copyRoundState(state.copySourceRound.value, state.activeRoundTab.value)
    state.showCopySource.value = false
  }

  function clearRound(rn: number) {
    state.ensureRoundState(rn)
    state.roundSelectedDimensions.value[rn] = []
    state.roundDimConfigs.value[rn] = {}
  }

  function applyToAllRounds(srcRn: number) {
    state.ensureRoundState(srcRn)
    for (const rn of state.allRoundTabs.value) {
      if (rn === srcRn) continue
      copyRoundState(srcRn, rn)
    }
  }

  // 切换到逐轮设置时初始化各轮次状态
  watch(state.roundMode, (newMode) => {
    if (newMode === ROUND_MODE.PER_ROUND) {
      for (const rn of state.allRoundTabs.value) {
        state.ensureRoundState(rn)
      }
    }
    if (newMode !== ROUND_MODE.PER_ROUND) {
      state.showCopySource.value = false
    }
  })

  // === 多轮整体评估维度 ===

  const isMultiDimensionSelected = (dim: DimensionTag) => {
    return state.multiSelectedDimensions.value.some(d => d.id === dim.id)
  }

  const toggleMultiDimension = (dim: DimensionTag) => {
    if (isMultiDimensionSelected(dim)) {
      state.multiSelectedDimensions.value = state.multiSelectedDimensions.value.filter(d => d.id !== dim.id)
      delete state.multiDimConfigs.value[dim.id]
    } else {
      state.multiSelectedDimensions.value.push(dim)
      state.multiDimConfigs.value[dim.id] = { weight: DEFAULT_WEIGHT, threshold: DEFAULT_THRESHOLD }
    }
  }

  const removeMultiDimension = (index: number) => {
    const dim = state.multiSelectedDimensions.value[index]
    delete state.multiDimConfigs.value[dim.id]
    state.multiSelectedDimensions.value.splice(index, 1)
  }

  return {
    filteredAvailableDimensions,
    toggleRoundNumber,
    isDimensionSelected,
    toggleDimension,
    removeDimension,
    isRoundDimensionSelected,
    toggleRoundDimension,
    getRoundSelectedDimensions,
    removeRoundDimension,
    copyFromRound,
    doCopyFromRound,
    clearRound,
    applyToAllRounds,
    isMultiDimensionSelected,
    toggleMultiDimension,
    removeMultiDimension,
  }
}