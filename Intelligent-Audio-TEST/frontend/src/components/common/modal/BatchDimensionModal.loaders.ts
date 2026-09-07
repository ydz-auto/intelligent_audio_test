/**
 * BatchDimensionModal —— 加载维度数据
 *
 * 将 Domain 维度（EvaluationDimension）归一为展示标签 DimensionTag，
 * 并按算法类型加载可用的评价维度列表。
 */
import type { EvaluationDimension } from '../../../domain'
import type { DimensionTag, Props } from './BatchDimensionModal.types'
import type { BatchDimensionState } from './BatchDimensionModal.state'

/** 将后端维度对象转换为前端 Dimension 接口（数据已通过 evaluationAdapter 转为 camelCase） */
export function toDimension(d: any): DimensionTag {
  return {
    id: d.id?.toString() || d.dimensionId?.toString() || '',
    name: d.name || d.dimensionName || '',
    description: d.description
  }
}

/** 维度加载上下文（state 的 availableDimensions 写入目标） */
export interface DimensionLoaderContext {
  props: Props
  state: BatchDimensionState
  fetchAllDimensions: (options?: { forceRefresh?: boolean }) => Promise<EvaluationDimension[]>
  fetchDimensionsByAlgorithmType: (algorithmType: string) => Promise<EvaluationDimension[]>
}

/** 创建维度加载器：按算法类型加载或全量加载（forceRefresh）并归一为展示标签 */
export function createDimensionLoader(ctx: DimensionLoaderContext) {
  const { props, state, fetchAllDimensions, fetchDimensionsByAlgorithmType } = ctx

  async function loadDimensions() {
    try {
      const dims = props.algorithmType
        ? await fetchDimensionsByAlgorithmType(props.algorithmType)
        : await fetchAllDimensions({ forceRefresh: true })
      state.availableDimensions.value = dims.map(toDimension)
    } catch (error) {
      console.error('加载评价维度失败:', error)
      state.availableDimensions.value = []
    }
  }

  return { loadDimensions }
}