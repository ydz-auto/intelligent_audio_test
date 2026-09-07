/**
 * BatchDimensionModal —— 保存提交
 *
 * 将统一模式 / 逐轮设置模式 / 多轮整体评估的勾选与权重阈值配置
 * 组装为提交载荷，并触发 confirm / cancel 事件。
 */
import { ROUND_MODE, DEFAULT_WEIGHT, DEFAULT_THRESHOLD } from './BatchDimensionModal.constants'
import type {
  Props,
  Emits,
  DimensionTag,
  DimConfig,
  DimensionConfigItem,
} from './BatchDimensionModal.types'
import type { BatchDimensionState, RoundControl } from './BatchDimensionModal.state'

/** 保存提交上下文 */
export interface DimensionSubmitContext {
  props: Props
  emit: Emits
  state: BatchDimensionState & RoundControl
}

/** 创建保存提交：组装载荷并触发 confirm / cancel */
export function createDimensionSubmit(ctx: DimensionSubmitContext) {
  const { props, emit, state } = ctx

  // 将维度数组转换为带权重和阈值的配置对象（提取公共逻辑，消除三处重复）
  function buildDimensionConfigs(
    dims: DimensionTag[],
    configs: Record<string, DimConfig>
  ): DimensionConfigItem[] {
    return dims.map(dim => ({
      id: dim.id,
      name: dim.name,
      weight: configs[dim.id]?.weight ?? DEFAULT_WEIGHT,
      threshold: configs[dim.id]?.threshold ?? DEFAULT_THRESHOLD
    }))
  }

  function handleConfirm() {
    const multiDimensions = buildDimensionConfigs(state.multiSelectedDimensions.value, state.multiDimConfigs.value)

    if (state.roundMode.value === ROUND_MODE.PER_ROUND) {
      const roundDimensions: Record<number, DimensionConfigItem[]> = {}
      for (const rn of state.allRoundTabs.value) {
        state.ensureRoundState(rn)
        roundDimensions[rn] = buildDimensionConfigs(
          state.roundSelectedDimensions.value[rn],
          state.roundDimConfigs.value[rn]
        )
      }
      emit('confirm', {
        dimensions: [],
        testType: props.testType ?? '',
        roundMode: ROUND_MODE.PER_ROUND,
        roundNumbers: [],
        roundDimensions,
        multiDimensions
      })
    } else {
      const dimensions = buildDimensionConfigs(state.selectedDimensions.value, state.dimConfigs.value)
      emit('confirm', {
        dimensions,
        testType: props.testType ?? '',
        roundMode: state.roundMode.value,
        roundNumbers: state.roundNumbers.value,
        multiDimensions
      })
    }
  }

  function handleCancel() {
    emit('cancel')
  }

  return { handleConfirm, handleCancel }
}