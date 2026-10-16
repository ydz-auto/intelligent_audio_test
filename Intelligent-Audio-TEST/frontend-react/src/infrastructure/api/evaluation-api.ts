/**
 * 评估维度 API 桩（infrastructure 层，11_用例域.md §3.4 评估维度 facet）。
 * 全部返回 mock 常量（红线④），接线时替换为真实请求：
 *   GET /api/v1/evaluation/dimensions/options?algorithm_type=…
 *       （evaluation.py DimensionOptionsQuery；主维度，type≠sub 过滤照现 loadDimensionOptions 口径）
 * 完整维度管理端点归评估维度页卡（features/evaluation）。
 */
import type { EvaluationDimensionItem } from '@/domain/models/evaluationDimension'
import { MOCK_DIMENSIONS } from '../mock/testcases-mock'

/** 模拟网络延迟（视觉稿演示用；接线后删除） */
function mockLatency<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), 120))
}

/** 维度选项（facet singleSelect；仅主维度，子维度折叠进主维度 Popover 内滚动） */
export async function fetchDimensionOptions(
  _algorithmType?: string
): Promise<EvaluationDimensionItem[]> {
  // TODO(API 接线): GET /api/v1/evaluation/dimensions/options?algorithm_type=…
  return mockLatency(MOCK_DIMENSIONS.filter((d) => d.dimensionType !== 'sub'))
}
