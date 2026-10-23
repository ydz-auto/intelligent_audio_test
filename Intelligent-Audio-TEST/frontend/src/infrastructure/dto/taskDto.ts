/**
 * Task DTO —— snake_case
 * 与后端 api_gateway/schemas/task.py 一一对应（serialize_by_alias=False 输出 snake_case）。
 */

/** 任务关联设备简报（TaskDeviceBrief） */
export interface TaskDeviceBriefDto {
  id: number
  name: string
  status?: string | null
  model?: string | null
}

/** 任务关联 API 简报（TaskApiBrief） */
export interface TaskApiBriefDto {
  id: number
  name: string
  status?: string | null
}

/** 合并任务来源任务摘要（TaskSourceBrief → source_tasks[]） */
export interface TaskSourceBriefDto {
  id: number
  name: string
  status?: string | null
  total_cases?: number | null
  completed_cases?: number | null
  failed_cases?: number | null
  created_at?: string | null
}

/** 任务关联报告项（TaskReportsData.reports[]） */
export interface TaskReportItemDto {
  id: number
  name: string
  status: string
  type: string
  created_at?: string
}

/** 任务关联报告聚合（TaskReportsData） */
export interface TaskReportsDataDto {
  count: number
  reports: TaskReportItemDto[]
}

// ===== 列表 / 详情 =====

/** 列表项（TaskListItem） */
export interface TaskDto {
  id: number | string
  name: string
  description?: string | null
  status: string
  /** INT-301：任务级执行状态（纯执行域，评估推进不落此字段） */
  execution_status?: string | null
  /** INT-301：任务级评估状态（pending/evaluating/completed/failed/skipped） */
  evaluation_status?: string | null
  device_types?: string[]
  progress?: number | null
  config?: Record<string, any>
  algorithm_type?: string | null
  algorithm_params?: Record<string, any> | null
  started_at?: string | null
  completed_at?: string | null
  expected_total_time?: string | number | null
  expected_complete_time?: string | null
  used_time?: string | null
  total_cases?: number | null
  case_count?: number | null
  device_count?: number | null
  completed_cases?: number | null
  failed_cases?: number | null
  /** INT-340：任务下已复核结果条数（覆盖提醒 + 报告页「人工复核」标记） */
  review_count?: number
  tags: string[]
  created_at?: string | null
  updated_at?: string | null
  finished_at?: string | null
  error?: string | null
  deleted?: boolean
  /** INT-215：回收站字段（与后端 TaskListItem 对齐） */
  deleted_at?: string | null
  deleted_by_user_id?: number | null
  /** INT-339：挑选合并容器标记（task_cherry_pick_relations 存在性判定） */
  is_cherry_pick?: boolean
  /** INT-577：统一合并容器「合并方式」（whole=整任务合并 / picked=结果挑选） */
  merge_type?: 'whole' | 'picked' | null
  /** INT-577：容器来源任务数 / 来源结果数 */
  source_task_count?: number | null
  source_result_count?: number | null
  /** INT-423/467：资源可见性（shared/private，后端 Visibility 原值） */
  visibility?: string | null
  /** INT-423/467：资源归属人 user_id（owner 判定；缺失按非私有处理） */
  created_by_user_id?: number | null
  result?: any
  reports?: TaskReportsDataDto | null
  devices: TaskDeviceBriefDto[]
  apis: TaskApiBriefDto[]
  source_tasks?: TaskSourceBriefDto[] | null
}

/** 任务详情关联用例简报（TaskCaseBrief） */
export interface TaskCaseBriefDto {
  case_id: string
  name: string
  status?: string | null
  execution_status?: string | null
  evaluation_status?: string | null
  started_at?: string | null
  completed_at?: string | null
  duration?: number | null
  error_message?: string | null
  group_name?: string | null
  tags: string[]
  /** INT-302/F3：本任务用例聚合的评估维度 [{id, name}]（重评估维度勾选候选集） */
  evaluation_dimensions?: Array<{ id: number | string; name?: string | null } | null> | null
  /** INT-340：该用例下是否存在人工复核结果 */
  reviewed?: boolean
}

/** 任务详情（TaskDetailData；在列表项字段之上新增 cases） */
export interface TaskDetailDto extends TaskDto {
  cases: TaskCaseBriefDto[]
}

// ===== 请求体 =====

/** 逐目标执行模式条目（INT-1115 §5.2.4：target_type ∈ {device, api}；target_id int；mode 复用 ExecutionMode） */
export interface TargetModeDto {
  target_type: 'device' | 'api'
  target_id: number
  mode: 'parallel' | 'serial'
}

/** 任务创建请求体（TaskCreateRequest） */
export interface TaskCreateDto {
  name: string
  description?: string | null
  /** INT-282：执行口径（api/e2e）。后端 task.type 已废弃（差异#2 收尾），
   * TaskCreateRequest extra="ignore" 会静默忽略；显式携带以对齐基线契约 */
  type?: string
  config?: Record<string, any>
  created_by?: string | null
  /** INT-423/467：新建可见性（默认 shared；后端缺省回落 shared） */
  visibility?: string
  case_ids?: string[]
  device_ids?: number[]
  api_ids?: number[]
  /** INT-1434：用例级被测设备选择（对应 TaskCaseDeviceAssignment 列表；
   * 所选用例 × 选中目标 笛卡尔积；缺省后端按用例配置形态派生兜底，零回归） */
  case_devices?: TaskCaseDeviceAssignmentDto[]
  /** INT-1115：逐目标执行模式（列表顺序 = 选中顺序 = 串行链顺序；缺省/空数组 = 全目标并行）。
   * 废弃顶层 execution_mode/serial_first：后端提交旧字段一律 422，前端不再携带 */
  target_modes?: TargetModeDto[]
  tags?: string[]
  algorithm_type?: string | null
  algorithm_params?: Record<string, any> | null
}

/** 用例级被测设备选择（TaskCaseDeviceAssignment，INT-1434） */
export interface TaskCaseDeviceAssignmentDto {
  case_id: string
  device_type?: string
  device_id?: string | number
  lab_id?: number
}

/** 任务更新请求体（网关 update 直传 JSON，未走 schema 校验） */
export interface TaskUpdateDto {
  name?: string
  description?: string
}

/** 任务启动响应（TaskStartData） */
export interface TaskStartDto {
  task_id: string
  start_time?: unknown
  status: string
  expected_total_time?: number | null
  expected_complete_time?: string | null
}

/** 任务动态调整用例响应（TaskUpdateCasesData） */
export interface TaskUpdateCasesDto {
  task_id: string
  total_count: number
}

/** 任务统计响应（TaskStatsData） */
export interface TaskStatsDto {
  total: number
  completed: number
  failed: number
  pending: number
  skipped: number
  pass_rate: number
  tag_stats: Record<string, any>
}

/** 任务批量操作请求体（TaskBatchActionRequest） */
export interface TaskBatchActionDto {
  action: string
  task_ids: Array<number | string>
}

/** 任务合并请求体（TaskMergeRequest） */
export interface TaskMergeDto {
  task_ids: Array<number | string>
}

/** 任务动态调整用例请求体（TaskUpdateCasesRequest） */
export interface TaskUpdateCasesRequestDto {
  action: string
  case_ids: Array<number | string>
}

/** 任务列表查询参数（TaskListQuery） */
export interface TaskListQueryDto {
  page: number
  per_page: number
  status?: string
  algorithm_type?: string
  search?: string
  start_date?: string
  end_date?: string
  // INT-216：收藏 / 回收站过滤（后端 TaskListQuery.favorite/deleted）
  favorite?: boolean
  deleted?: boolean
  // INT-301：评估状态过滤（与执行状态并列）
  evaluation_status?: string
  // INT-298：merged=true 仅合并容器任务（后端 TaskListQuery.merged）
  merged?: boolean
  // INT-339：cherry_pick=true 仅挑选合并容器任务（后端 TaskListQuery.cherry_pick）
  cherry_pick?: boolean
  // INT-577：合并方式快捷筛选（whole|picked，后端 TaskListQuery.merge_type）
  merge_type?: 'whole' | 'picked'
  // INT-577：返回合并容器统计块（后端 TaskListQuery.stats）
  stats?: boolean
  // INT-301 F1：执行状态过滤（复用派生口径，命中行执行徽章 == 筛选值）
  execution_status?: string
  // INT-423/467：可见性过滤（private|shared；服务端行级过滤，私有仅当前用户可见）
  visibility?: string
  // INT-273：派生任务类型过滤（api/e2e/mixed）
  task_type?: string
}

/** INT-577：合并容器统计（GET /tasks 响应 stats 块；merged ∪ cherry_pick 并集） */
export interface TaskContainerStatsDto {
  total: number
  whole: number
  picked: number
}

// ===== 任务域全量聚合统计（GET /tasks/stats，INT-200）=====

/** 趋势分桶项（{key, count} 序列） */
export interface TaskTrendBucketDto {
  key: string
  count: number
}

/** 任务域全量聚合统计（TaskDomainStatsData，snake_case 契约） */
export interface TaskDomainStatsDto {
  total: number
  deleted_total: number
  status_counts: Record<string, number>
  type_counts: { api: number; e2e: number; mixed: number }
  trend: TaskTrendBucketDto[]
  granularity: string
}
