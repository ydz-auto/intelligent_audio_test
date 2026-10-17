/**
 * 挑选合并功能 mock 常量（红线④：数据一律 mock，不接真实后端，INT-600）。
 * 本文件保存的是「真实接口响应形态」——snake_case DTO（对照 api_gateway/schemas/
 * 与 cherry_pick_bp.py 实测契约），经 infrastructure/adapters/dto/cherry-pick-adapter.ts
 * 转换为 camelCase Domain 后消费；字段不返工。
 * 数字口径与 tasks-mock.ts 对齐：任务 1042/1041/1037/1036 真实名。
 */

/** 候选行 DTO（GET /tasks/cherry-picks/candidates，§11-2 未落前 case_name/device_name/result_type 为 null/缺省） */
export interface CherryPickCandidateDto {
  result_id: number
  task_id: number
  task_name: string
  case_id: string
  case_name: string | null
  device_id: number | null
  device_name: string | null
  api_id: number | null
  api_name: string | null
  result_type: string
  execution_status: string
  evaluation_status: string
  evaluated: boolean
  created_at: string
}

/** 购物车条目 DTO（CherryPickCartItem 快照，cherry_pick_repository.cart_list 实测） */
export interface PickCartEntryDto {
  item_id: string
  result_id: number
  source_task_id: number
  source_task_name: string
  source_case_id: string | null
  source_case_name: string | null
  source_device_id: number | null
  source_device_name: string | null
  source_api_id: number | null
  source_api_name: string | null
  /** §11-5 未补前为 null */
  source_result_type: string | null
  execution_status: string
  evaluation_status: string
  invalid: boolean
}

/** 购物车分组 DTO（cart_get 按来源任务分组返回） */
export interface PickCartGroupDto {
  task_id: number
  task_name: string
  entries: PickCartEntryDto[]
}

/** 挑选集 DTO */
export interface PickSetDto {
  set_id: string
  name: string
  created_at: string
  item_count: number
  entries: PickCartEntryDto[]
}

/** 复核摘要 DTO（POST /tasks/cherry-picks/cart/preview） */
export interface PickPreviewDto {
  total_results: number
  invalid_result_ids: number[]
  source_task_count: number
  device_ids: number[]
  case_count: number
  execution_status_counts: Record<string, number>
  duplicates: number
  config_inconsistent: boolean
  config_fields: string[]
  source_configs: Record<string, unknown>[]
}

/** 统一合并容器 DTO（§11-1 落地前客户端双查询合并：merged=true ∪ cherry_pick=true） */
export interface CherryPickContainerDto {
  id: number
  name: string
  description: string | null
  execution_status: string
  evaluation_status: string
  total_cases: number | null
  merge_type: 'whole' | 'picked'
  source_task_count: number
  source_result_count: number
  source_task_ids: number[]
  source_tasks: { id: number; name: string; result_count: number; status: string }[]
  created_at: string
  is_favorite: boolean
}

/** 候选行 mock（三级任务：音箱回归 / 车载唤醒 / 方言抽样；覆盖 real-time/final/streaming） */
export const MOCK_CANDIDATE_DTOS: CherryPickCandidateDto[] = [
  { result_id: 5001, task_id: 1042, task_name: '智能音箱旗舰机型全量回归 · 第 3 轮', case_id: 'c-001', case_name: '远场 3m 唤醒词响应', device_id: 1, device_name: '音箱-客厅位', api_id: null, api_name: null, result_type: 'real-time', execution_status: 'completed', evaluation_status: 'completed', evaluated: true, created_at: '2026-10-15T09:00:00' },
  { result_id: 5002, task_id: 1042, task_name: '智能音箱旗舰机型全量回归 · 第 3 轮', case_id: 'c-001', case_name: '远场 3m 唤醒词响应', device_id: 1, device_name: '音箱-客厅位', api_id: null, api_name: null, result_type: 'real-time', execution_status: 'completed', evaluation_status: 'completed', evaluated: true, created_at: '2026-10-15T09:00:02' },
  { result_id: 5003, task_id: 1042, task_name: '智能音箱旗舰机型全量回归 · 第 3 轮', case_id: 'c-001', case_name: '远场 3m 唤醒词响应', device_id: 1, device_name: '音箱-客厅位', api_id: null, api_name: null, result_type: 'final', execution_status: 'completed', evaluation_status: 'evaluating', evaluated: false, created_at: '2026-10-15T09:01:00' },
  { result_id: 5004, task_id: 1042, task_name: '智能音箱旗舰机型全量回归 · 第 3 轮', case_id: 'c-002', case_name: '远场 3m 连续对话保持', device_id: 2, device_name: '音箱-卧室位', api_id: null, api_name: null, result_type: 'real-time', execution_status: 'completed', evaluation_status: 'completed', evaluated: true, created_at: '2026-10-15T09:02:00' },
  { result_id: 5005, task_id: 1042, task_name: '智能音箱旗舰机型全量回归 · 第 3 轮', case_id: 'c-003', case_name: '近场 1m 唤醒词响应', device_id: 1, device_name: '音箱-客厅位', api_id: null, api_name: null, result_type: 'real-time', execution_status: 'completed', evaluation_status: 'completed', evaluated: true, created_at: '2026-10-15T09:03:00' },
  { result_id: 5006, task_id: 1042, task_name: '智能音箱旗舰机型全量回归 · 第 3 轮', case_id: 'c-004', case_name: '噪声环境 5m 唤醒（电视声）', device_id: 2, device_name: '音箱-卧室位', api_id: null, api_name: null, result_type: 'streaming', execution_status: 'failed', evaluation_status: 'failed', evaluated: true, created_at: '2026-10-15T09:04:00' },
  { result_id: 5010, task_id: 1041, task_name: '车载语音助手唤醒词响应测试', case_id: 'c-011', case_name: '车载 1m 唤醒词响应', device_id: 3, device_name: '车载屏-主驾位', api_id: null, api_name: null, result_type: 'real-time', execution_status: 'completed', evaluation_status: 'completed', evaluated: true, created_at: '2026-10-14T10:00:00' },
  { result_id: 5011, task_id: 1041, task_name: '车载语音助手唤醒词响应测试', case_id: 'c-011', case_name: '车载 1m 唤醒词响应', device_id: 3, device_name: '车载屏-主驾位', api_id: null, api_name: null, result_type: 'final', execution_status: 'completed', evaluation_status: 'evaluating', evaluated: false, created_at: '2026-10-14T10:01:00' },
  { result_id: 5012, task_id: 1041, task_name: '车载语音助手唤醒词响应测试', case_id: 'c-012', case_name: '车载 3m 唤醒（路噪）', device_id: 3, device_name: '车载屏-主驾位', api_id: null, api_name: null, result_type: 'real-time', execution_status: 'completed', evaluation_status: 'completed', evaluated: true, created_at: '2026-10-14T10:02:00' },
  { result_id: 5020, task_id: 1037, task_name: '多方言识别准确性抽样测试', case_id: 'c-021', case_name: '粤语唤醒词识别', device_id: 4, device_name: '方言采集盒-01', api_id: null, api_name: null, result_type: 'real-time', execution_status: 'stopped', evaluation_status: 'skipped', evaluated: false, created_at: '2026-10-13T11:05:00' },
  { result_id: 5021, task_id: 1037, task_name: '多方言识别准确性抽样测试', case_id: 'c-022', case_name: '川渝方言连续识别', device_id: 4, device_name: '方言采集盒-01', api_id: null, api_name: null, result_type: 'final', execution_status: 'stopped', evaluation_status: 'skipped', evaluated: false, created_at: '2026-10-13T11:06:00' },
]

/** 购物车条目快照 mock（含失效条目 invalid=true 演示「一键移除失效」） */
export const MOCK_CART_ENTRY_DTOS: PickCartEntryDto[] = [
  { item_id: 'ci-1', result_id: 5001, source_task_id: 1042, source_task_name: '智能音箱旗舰机型全量回归 · 第 3 轮', source_case_id: 'c-001', source_case_name: '远场 3m 唤醒词响应', source_device_id: 1, source_device_name: '音箱-客厅位', source_api_id: null, source_api_name: null, source_result_type: null, execution_status: 'completed', evaluation_status: 'completed', invalid: false },
  { item_id: 'ci-2', result_id: 5002, source_task_id: 1042, source_task_name: '智能音箱旗舰机型全量回归 · 第 3 轮', source_case_id: 'c-001', source_case_name: '远场 3m 唤醒词响应', source_device_id: 1, source_device_name: '音箱-客厅位', source_api_id: null, source_api_name: null, source_result_type: null, execution_status: 'completed', evaluation_status: 'completed', invalid: false },
  { item_id: 'ci-3', result_id: 5004, source_task_id: 1042, source_task_name: '智能音箱旗舰机型全量回归 · 第 3 轮', source_case_id: 'c-002', source_case_name: '远场 3m 连续对话保持', source_device_id: 2, source_device_name: '音箱-卧室位', source_api_id: null, source_api_name: null, source_result_type: null, execution_status: 'completed', evaluation_status: 'completed', invalid: false },
  { item_id: 'ci-4', result_id: 5010, source_task_id: 1041, source_task_name: '车载语音助手唤醒词响应测试', source_case_id: 'c-011', source_case_name: '车载 1m 唤醒词响应', source_device_id: 3, source_device_name: '车载屏-主驾位', source_api_id: null, source_api_name: null, source_result_type: null, execution_status: 'completed', evaluation_status: 'completed', invalid: false },
  { item_id: 'ci-5', result_id: 5555, source_task_id: 1041, source_task_name: '车载语音助手唤醒词响应测试', source_case_id: 'c-012', source_case_name: '车载 3m 唤醒（路噪）', source_device_id: 3, source_device_name: '车载屏-主驾位', source_api_id: null, source_api_name: null, source_result_type: null, execution_status: 'failed', evaluation_status: 'failed', invalid: true },
]

/** 购物车分组 DTO mock（cart_get 按来源任务分组返回） */
export const MOCK_CART_GROUP_DTOS: PickCartGroupDto[] = [
  { task_id: 1042, task_name: '智能音箱旗舰机型全量回归 · 第 3 轮', entries: MOCK_CART_ENTRY_DTOS.filter((e) => e.source_task_id === 1042) },
  { task_id: 1041, task_name: '车载语音助手唤醒词响应测试', entries: MOCK_CART_ENTRY_DTOS.filter((e) => e.source_task_id === 1041) },
]

/** 挑选集 DTO mock */
export const MOCK_PICK_SET_DTOS: PickSetDto[] = [
  { set_id: 'set-1', name: '远场高置信度候选集', created_at: '2026-10-14T10:00:00', item_count: 2, entries: MOCK_CART_ENTRY_DTOS.slice(0, 2) },
]

/** 复核摘要 DTO mock（POST /tasks/cherry-picks/cart/preview，零新增接口） */
export const MOCK_PICK_PREVIEW_DTO: PickPreviewDto = {
  total_results: 5,
  invalid_result_ids: [5555],
  source_task_count: 2,
  device_ids: [1, 2, 3],
  case_count: 4,
  execution_status_counts: { completed: 4, failed: 1 },
  duplicates: 1,
  config_inconsistent: true,
  config_fields: ['algorithm_type'],
  source_configs: [{ algorithm_type: 'asr_streaming' }, { algorithm_type: 'wakeword_detect' }],
}

/** 统一合并容器 DTO mock（整任务合并 ∪ 结果挑选，§11-1 落地前客户端双查询合并） */
export const MOCK_CONTAINER_DTOS: CherryPickContainerDto[] = [
  {
    id: 901,
    name: '远场识别高置信度结果挑选集',
    description: '从多轮远场识别中挑选高置信度结果合并验证。',
    execution_status: 'completed',
    evaluation_status: 'completed',
    total_cases: 32,
    merge_type: 'picked',
    source_task_count: 3,
    source_result_count: 32,
    source_task_ids: [1042, 1041, 1037],
    source_tasks: [
      { id: 1042, name: '智能音箱旗舰机型全量回归 · 第 3 轮', result_count: 18, status: 'completed' },
      { id: 1041, name: '车载语音助手唤醒词响应测试', result_count: 10, status: 'completed' },
      { id: 1037, name: '多方言识别准确性抽样测试', result_count: 4, status: 'stopped' },
    ],
    created_at: '2026-10-15T09:00:00',
    is_favorite: false,
  },
  {
    id: 900,
    name: '车载噪声环境挑选合并（第 1 期）',
    description: '车载噪声场景挑选合并验证。',
    execution_status: 'completed',
    evaluation_status: 'evaluating',
    total_cases: 18,
    merge_type: 'picked',
    source_task_count: 2,
    source_result_count: 18,
    source_task_ids: [1041, 1036],
    source_tasks: [
      { id: 1041, name: '车载语音助手唤醒词响应测试', result_count: 12, status: 'completed' },
      { id: 1036, name: 'TTS 自然度主观评估（第 2 期）', result_count: 6, status: 'completed' },
    ],
    created_at: '2026-10-13T14:20:00',
    is_favorite: true,
  },
  {
    id: 1035,
    name: 'Q3 音箱品类回归汇总',
    description: 'Q3 音箱品类全量回归合并任务（合并自 4 个任务）。',
    execution_status: 'merged',
    evaluation_status: 'completed',
    total_cases: 384,
    merge_type: 'whole',
    source_task_count: 4,
    source_result_count: 384,
    source_task_ids: [1021, 1022, 1023, 1024],
    source_tasks: [
      { id: 1021, name: '音箱唤醒词回归', result_count: 96, status: 'completed' },
      { id: 1022, name: '音箱连续对话回归', result_count: 96, status: 'completed' },
      { id: 1023, name: '音箱远场识别回归', result_count: 96, status: 'completed' },
      { id: 1024, name: '音箱播报音质回归', result_count: 96, status: 'completed' },
    ],
    created_at: '2026-10-11T10:00:00',
    is_favorite: false,
  },
]
