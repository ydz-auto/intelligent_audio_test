/**
 * 评估维度 API 桩（infrastructure 层；11_用例域.md §3.4 facet + §4.1 评估维度页）。
 * 全部返回 mock 常量（红线④），接线时替换为真实请求（api_gateway/schemas/evaluation.py 口径）：
 *   GET  /api/v1/evaluation/dimensions/options?algorithm_type=…    （DimensionOptionsQuery；facet）
 *   GET  /api/v1/evaluation/dimensions?category_id&page&per_page&search （DimensionListData；INT-281 主/子同屏全量）
 *   GET  /api/v1/evaluation/categories                             （CategoryListData）
 *   GET  /api/v1/algorithm/options                                 （关联算法 facet/表单）
 *   POST /api/v1/evaluation/{id}/calculate                          （ScoreData 试算）
 *   POST /api/v1/evaluation/{id}/health-check                       （DimensionHealthCheckData）
 *   PUT  /api/v1/evaluation/{id}                                    （维度保存/权重更新）
 *   DELETE /api/v1/evaluation/{id}                                  （删除维度）
 *   POST /api/v1/evaluation/batch-action                            （批量启用/禁用/删除）
 */
import type {
  Dimension,
  DimensionHealthCheckData,
  EvaluationCategory,
  HealthCheckResultItem,
} from '@/domain/models/evaluationDimension'
import { MOCK_DIMENSIONS } from '../mock/testcases-mock'
import {
  MOCK_ALGORITHM_OPTIONS,
  MOCK_EVALUATION_CATEGORIES,
  MOCK_EVALUATION_DIMENSIONS,
} from '../mock/evaluation-mock'
import type { EvaluationDimensionItem } from '@/domain/models/evaluationDimension'

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

/** 评估维度全量（列表/分组双视图；主/子维度同屏聚合，前端过滤分页） */
export async function fetchEvaluationDimensions(): Promise<Dimension[]> {
  // TODO(API 接线): GET /api/v1/evaluation/dimensions?per_page=1000（INT-281 主/子同屏）
  return mockLatency([...MOCK_EVALUATION_DIMENSIONS])
}

/** 评估分类（分类 facet + 分组视图组头 + 分类表单） */
export async function fetchEvaluationCategories(): Promise<EvaluationCategory[]> {
  // TODO(API 接线): GET /api/v1/evaluation/categories?per_page=100
  return mockLatency([...MOCK_EVALUATION_CATEGORIES])
}

/** 算法选项（关联算法 facet singleSelect + 维度表单关联算法 Combobox） */
export async function fetchAlgorithmOptions(): Promise<
  Array<{ value: string; label: string }>
> {
  // TODO(API 接线): GET /api/v1/algorithm/options
  return mockLatency([...MOCK_ALGORITHM_OPTIONS])
}

/** 保存维度（新增/编辑/权重更新共用；mock 阶段成功即返回） */
export async function saveEvaluationDimension(
  _input: Partial<Dimension>
): Promise<{ success: boolean }> {
  // TODO(API 接线): POST/PUT /api/v1/evaluation/dimensions|/{id}
  return mockLatency({ success: true })
}

/** 删除维度（逻辑删除） */
export async function deleteEvaluationDimension(
  _id: number | string
): Promise<{ success: boolean }> {
  // TODO(API 接线): DELETE /api/v1/evaluation/{id}
  return mockLatency({ success: true })
}

/** 批量操作（启用/禁用/删除） */
export async function batchEvaluationDimensions(
  _ids: Array<number | string>,
  _action: 'enable' | 'disable' | 'delete'
): Promise<{ success: boolean; updatedCount: number }> {
  // TODO(API 接线): POST /api/v1/evaluation/batch-action
  return mockLatency({ success: true, updatedCount: _ids.length })
}

/** 权重滑杆提交（拖动停止 onValueCommitted 才触发，§4.1/§10-4） */
export async function updateDimensionWeight(
  _id: number | string,
  _weight: number
): Promise<{ success: boolean }> {
  // TODO(API 接线): PUT /api/v1/evaluation/{id}（载荷 { weight }）
  return mockLatency({ success: true })
}

/** 维度上移/下移（主维度整块移动、子维度仅同组内移动） */
export async function reorderDimension(
  _id: number | string,
  _direction: -1 | 1
): Promise<{ success: boolean }> {
  // TODO(API 接线): POST /api/v1/evaluation/reorder
  return mockLatency({ success: true })
}

/** 规则试算（POST /evaluation/dimensions/{id}/calculate；门槛 evaluation:dim_manage） */
export async function calculateDimensionScore(
  dimension: Dimension,
  value: number
): Promise<{ score: number; matchedRule: { condition: string; value: number; score: number } | null }> {
  // TODO(API 接线): POST /api/v1/evaluation/{id}/calculate { value }
  // mock 阶段按维度 rule 规则现场匹配（规则按序匹配命中首条即停）
  const rules = Array.isArray(dimension.rule)
    ? dimension.rule
    : typeof dimension.rule === 'object' && dimension.rule?.rules
      ? dimension.rule.rules
      : []
  for (const rule of rules) {
    const { condition, value: threshold, score } = rule
    const hit =
      condition === '>=' ? value >= threshold :
      condition === '<=' ? value <= threshold :
      condition === '>' ? value > threshold :
      condition === '<' ? value < threshold :
      condition === '=' ? value === threshold : false
    if (hit) return mockLatency({ score, matchedRule: rule })
  }
  return mockLatency({ score: 0, matchedRule: null })
}

/** 测试 API 健康（行内「测试 API」；门槛 evaluation:read） */
export async function testDimensionHealth(
  dimension: Dimension
): Promise<DimensionHealthCheckData> {
  // TODO(API 接线): POST /api/v1/evaluation/{id}/health-check
  const online = dimension.apiStatus !== 'offline'
  const results: HealthCheckResultItem[] = [
    {
      url: dimension.apiUrl ?? `https://api.example.com/evaluation/dim-${dimension.id}`,
      status: online ? 'online' : 'offline',
      statusCode: online ? 200 : 502,
      responseTime: online ? '120.50ms' : '—',
      message: online ? '健康探测完成' : '连接超时或服务不可用',
    },
  ]
  return mockLatency({
    results,
    overallStatus: online ? 'online' : 'offline',
  })
}

/** 复制维度（深拷贝 api/rule/weight 配置为新维度「{原名}（副本）」） */
export async function duplicateDimension(
  _dimension: Dimension
): Promise<{ success: boolean }> {
  // TODO(API 接线): POST /api/v1/evaluation/{id}/duplicate
  return mockLatency({ success: true })
}
