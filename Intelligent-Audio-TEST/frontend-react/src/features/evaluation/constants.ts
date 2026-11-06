/**
 * 评估维度页常量（features/evaluation；11_用例域.md §8 中文文案全量源）。
 * 视图页签/状态筛选/结果类型映射/默认权重；徽章映射走 status-badge 语义名。
 */
/**
 * 算法类型 id → 中文名。真实 label 优先取 GET /algorithm/options（页面级把
 * options 的 value→label 传进来）；ALGORITHM_LABELS 仅作无真实数据时的兜底。
 */
export const ALGORITHM_LABELS: Record<string, string> = {}

export function getAlgorithmLabel(
  algorithmType: string | null,
  labels?: Record<string, string>
): string {
  if (!algorithmType) return '—'
  return labels?.[algorithmType] ?? ALGORITHM_LABELS[algorithmType] ?? algorithmType
}

/** 双视图页签（default 胶囊，§4.1）：列表视图 / 分组视图 */
export const EVALUATION_VIEW_TABS: Array<{
  key: 'list' | 'group'
  label: string
}> = [
  { key: 'list', label: '列表视图' },
  { key: 'group', label: '分组视图' },
]

/** 状态 facet（全部状态/启用/禁用） */
export const STATUS_FILTER_OPTIONS: Array<{
  value: string
  label: string
}> = [
  { value: 'all', label: '全部状态' },
  { value: 'active', label: '启用' },
  { value: 'inactive', label: '禁用' },
]

/** 分类 facet（全部/动态分类；数据来自 useEvaluationCategories） */
export const CATEGORY_FILTER_ALL_LABEL = '全部分类'

/** 关联算法 facet（全部/动态算法；数据来自 useAlgorithmOptions） */
export const ALGORITHM_FILTER_ALL_LABEL = '全部'

/** 搜索占位（§8：搜索评估维度...） */
export const DIMENSION_SEARCH_PLACEHOLDER = '搜索评估维度...'

/** 权重滑杆范围（1-10 整数） */
export const WEIGHT_MIN = 1
export const WEIGHT_MAX = 10

/** 结果类型映射（resultType 数值 → 中文标签；LLM Judge 是维度属性而非结果类型，INT-1681） */
export const RESULT_TYPE_LABELS: Record<string, string> = {
  // INT-1732 P3-1：真实库 46/63 维度 result_type=0（旧数据，不在 §5.5 选项内），
  // 抽屉闭合态补中文标签；值照常回写，不改成 1
  '0': '未设置',
  '1': '数值',
  '2': '布尔',
  '3': '文本',
}

/** 统计方式选项（§5.5 统计方式 Select） */
export const STATISTIC_METHOD_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'average', label: '简单平均' },
  { value: 'weighted_wer', label: '加权WER (Σ分子/Σ分母)' },
  { value: 'ratio', label: '比率 (Σ数量/Σ分母, %)' },
]

/** 聚合分母口径选项 */
export const AGG_DENOMINATOR_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'case', label: '按用例 (分母=配置该维度的用例数)' },
  { value: 'round', label: '按轮次 (分母=该维度有值轮次数)' },
]

/** 评估类型选项（§5.5 基本信息「评估类型」） */
export const DIMENSION_EVALUATION_TYPE_OPTIONS: Array<{
  value: string
  label: string
}> = [
  { value: 'auto', label: '自动评估' },
  { value: 'manual', label: '人工评估' },
]

/** 维度类型选项（§5.5 层级配置「维度类型」） */
export const DIMENSION_TYPE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'main', label: '主维度' },
  { value: 'sub', label: '子维度' },
]

/** 自动合并提示条（§4.1 现 auto-merge-hint 文案逐字保留） */
export const AUTO_MERGE_HINT =
  '同一分类下、评估服务与请求模板一致的维度，评估时会自动合并为一次请求，共用一次判定结果。'

/** 分类图标占位（§5.5 分类表单；照现 categoryFields 逐字） */
export const DEFAULT_CATEGORY_ICON = 'fas fa-folder'

/** 权重更新进行中/成功文案（§4.1 权重列） */
export const WEIGHT_UPDATE_SUCCESS = '权重更新成功'
export const WEIGHT_UPDATE_FAILURE = '权重更新失败'
