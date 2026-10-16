/**
 * 算法配置页常量（features/algorithm-config；17_配置运维.md §10 中文文案源）。
 * 枚举/状态 + 展示文案直接存中文，组件直接渲染（AGENTS.md §3.1 全中文硬编码）。
 */

/** 算法状态选项（§3.4 状态 facet + 列表 StatusBadge） */
export const ALGORITHM_STATUS_OPTIONS = [
  { value: 'online', label: '上线' },
  { value: 'offline', label: '下线' },
] as const

/** 算法状态 → StatusBadge 语义（§8：online=success 上线 / offline=neutral 下线） */
export const ALGORITHM_STATUS_META: Record<
  'online' | 'offline',
  { label: string; badgeVariant: 'success' | 'neutral' }
> = {
  online: { label: '上线', badgeVariant: 'success' },
  offline: { label: '下线', badgeVariant: 'neutral' },
}

/** 参数方向选项（§6.3 设备/API 参数表格） */
export const PARAM_DIRECTION_OPTIONS = [
  { value: 'input', label: '输入' },
  { value: 'output', label: '输出' },
] as const

/** 设备/API 参数类型选项（§6.3） */
export const DEVICE_PARAM_TYPE_OPTIONS = [
  { value: 'text', label: '文本' },
  { value: 'audio_stream', label: '音频流' },
  { value: 'audio_file', label: '音频文件' },
  { value: 'text_file', label: '文本文件' },
  { value: 'rttm', label: 'RTTM标注' },
  { value: 'stm', label: 'STM标注' },
  { value: 'json', label: 'JSON结构化' },
] as const

/** 用例参数类型选项（§6.3） */
export const CASE_PARAM_TYPE_OPTIONS = [
  { value: 'text', label: '文本' },
  { value: 'number', label: '数字' },
  { value: 'textarea', label: '多行文本' },
  { value: 'switch', label: '开关' },
  { value: 'slider', label: '滑块' },
  { value: 'audio_select', label: '音频选择' },
  { value: 'device_select', label: '设备选择' },
  { value: 'json', label: 'JSON结构化' },
] as const

/** 用例参数适用范围选项（§6.3） */
export const CASE_PARAM_SCOPE_OPTIONS = [
  { value: 'common', label: '通用' },
  { value: 'api', label: 'API' },
  { value: 'e2e', label: 'E2E' },
] as const

/** 参考参数类型选项（§6.4） */
export const REFERENCE_PARAM_TYPE_OPTIONS = [
  { value: 'text', label: '文本' },
  { value: 'audio', label: '音频' },
  { value: 'json', label: 'JSON' },
  { value: 'rttm', label: 'RTTM' },
  { value: 'stm', label: 'STM' },
] as const

/** 参考参数合并方式选项（§6.4） */
export const REFERENCE_PARAM_MERGE_OPTIONS = [
  { value: 'concat', label: '拼接' },
  { value: 'collect', label: '收集数组' },
  { value: 'first', label: '取第一个' },
] as const

/** 转换类型枚举（§6.5；API 映射额外支持 base64） */
export const TRANSFORM_TYPE_OPTIONS = [
  { value: 'none', label: '不转换' },
  { value: 'uppercase', label: '转大写' },
  { value: 'lowercase', label: '转小写' },
  { value: 'json_parse', label: 'JSON解析' },
] as const

export const API_TRANSFORM_TYPE_OPTIONS = [
  ...TRANSFORM_TYPE_OPTIONS,
  { value: 'base64', label: 'Base64' },
] as const

/** 列表页分页每页条数选项（§3.7 PAGE_SIZE_OPTIONS 语义） */
export const PAGE_SIZE_OPTIONS = [10, 20, 30, 50, 100]

/** 列表默认每页条数（§3.2 validateSearch pageSize catch 20） */
export const DEFAULT_PAGE_SIZE = 20

/** 搜索防抖毫秒 */
export const ALGORITHM_SEARCH_DEBOUNCE_MS = 300

/** 分组 facet 全部分组哨兵值 */
export const GROUP_FILTER_ALL = 'all'

/** 状态 facet 全部状态哨兵值 */
export const STATUS_FILTER_ALL = 'all'

/** 用例参数页签「功能特性快捷开关」hint（§6.3） */
export const FEATURE_BUNDLES_HINT = '勾选后自动批量添加/删除对应参数'

/** 参考参数分节说明（§6.4） */
export const REFERENCE_PARAMS_DESCRIPTION =
  '配置算法的参考参数，用于存储参考文本、音频、文件等数据。参考类型支持：文本、音频、RTTM、STM 等。配置的参考字段可参与评估参数映射。'

/** 评估维度分节说明（§6.6） */
export const DIMENSIONS_DESCRIPTION =
  '关联算法到评估维度，设置权重与默认维度。'

/** 导入算法说明（§7.6） */
export const IMPORT_DIALOG_DESCRIPTION =
  '粘贴或上传算法定义 JSON（与导出格式一致），导入后立即生效。'
