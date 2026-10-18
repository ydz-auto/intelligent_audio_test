/**
 * 挑选合并真实接口 DTO（infrastructure/dto，18_挑选合并交互重设计.md §8，INT-713）。
 * 对照 api_gateway/routes/cherry_pick_bp.py + task_service/application/task/cherry_pick_service.py
 * + task_service/infrastructure/persistence/cherry_pick_repository.py 实测响应形态。
 * snake_case 唯一出现层；经 adapters/dto/cherry-pick-adapter.ts 转 camelCase Domain。
 * 后端缺口（§11-2/§11-5，INT-713 开 FEAT）：candidates 未返 case_name/device_name/api_name/
 * result_type；cart 快照未返 source_result_type/source_case_name/source_device_name——
 * 前端按设计降级（缺名显示 ID、result_type 折叠为「结果类型待补充」），不写兼容层。
 */

/** 候选行（GET /tasks/cherry-picks/candidates，list_candidates 实测） */
export interface CherryPickCandidateDto {
  result_id: number
  task_id: number
  task_name: string
  task_status: string
  case_id: string
  device_id: number | null
  api_id: number | null
  algorithm_type: string | null
  execution_status: string
  /** 结果级已评估（评估维度行存在性，_evaluated_result_ids 批量解析） */
  evaluated: boolean
  created_at: string | null
}

/** 购物车条目快照（cherry_pick_repository._cart_item_to_dict + cart_get invalid 标注） */
export interface CherryPickCartItemDto {
  item_id: number
  result_id: number
  source_task_id: number
  source_task_name: string | null
  source_case_id: string | null
  source_device_id: number | null
  source_api_id: number | null
  execution_status: string
  created_at: string | null
  /** 源结果已删除标注（cart_get 逐行 _results_exist 判定） */
  invalid: boolean
}

/** 购物车分组（cart_get 按来源任务分组返回） */
export interface CherryPickCartGroupDto {
  source_task_id: number
  source_task_name: string | null
  items: CherryPickCartItemDto[]
}

/** 购物车读（GET /tasks/cherry-picks/cart） */
export interface CherryPickCartDto {
  groups: CherryPickCartGroupDto[]
  total: number
  invalid_item_ids: number[]
}

/** 挑选集列表项（sets_list → {items: [...]}） */
export interface CherryPickSetListItemDto {
  set_id: number
  name: string
  description: string | null
  item_count: number
  created_at: string | null
}

/** 另存挑选集结果（cart_save_as_set → {set_id, name, item_count}） */
export interface CherryPickSaveSetResultDto {
  set_id: number
  name: string
  item_count: number
}

/** 复核摘要（POST /tasks/cherry-picks/preview，preview() 实测） */
export interface CherryPickPreviewDto {
  total_results: number
  invalid_result_ids: number[]
  source_task_count: number
  source_task_ids: number[]
  device_ids: number[]
  device_names: (string | null)[]
  case_count: number
  execution_status_counts: Record<string, number>
  /** 同设备同用例多来源组（preview 返回 [{device_id, case_id, count}]，前端展示组数） */
  duplicates: { device_id: number | null; case_id: string | null; count: number }[]
}

/** 加购结果（cart_add → {added, missing, duplicated}） */
export interface CherryPickAddResultDto {
  added: number[]
  missing: number[]
  duplicated: number[]
}

/** 移除/清空结果（cart_remove/cart_clear → {removed}） */
export interface CherryPickRemoveResultDto {
  removed: number
}

/** 恢复挑选集进购物车（set_to_cart → cart_add 同构） */
export interface CherryPickRestoreResultDto {
  added: number[]
  missing: number[]
  duplicated: number[]
}

/** 下单 merge（checkout_merge → {task_id, result_count}） */
export interface CherryPickMergeResultDto {
  task_id: number
  result_count: number
}

/** 下单 reexecute（checkout_reexecute → {task_id, case_count, started}） */
export interface CherryPickReexecuteResultDto {
  task_id: number
  case_count: number
  started: boolean
}

/** 下单 reevaluate（checkout_reevaluate → {submitted_task_ids, failed, cleared}） */
export interface CherryPickReevaluateResultDto {
  submitted_task_ids: number[]
  failed: { task_id: number; message: string }[]
  cleared: boolean
}

/* ============================================================
 * 统一合并容器（§11-1 落地前客户端双查询合并）
 * 数据源：GET /tasks?merged=true ∪ GET /tasks?cherry_pick=true（task_read_model 实测）
 * ============================================================ */

/** 合并容器来源任务简报（TaskSourceBrief；cherry-pick 容器 read model 未填 → 溯源端点补） */
export interface TaskSourceBriefDto {
  id: number
  name: string
  status: string | null
  total_cases: number | null
  completed_cases: number | null
  failed_cases: number | null
  created_at: string | null
}

/** 任务列表容器行（合并容器映射用字段子集；tasks list 实测） */
export interface TaskContainerItemDto {
  id: number
  name: string
  description: string | null
  status: string
  execution_status: string
  evaluation_status: string
  total_cases: number | null
  created_at: string | null
  is_favorite: boolean
  is_cherry_pick: boolean
  source_tasks: TaskSourceBriefDto[]
  devices: { id: number; name: string; status: string }[]
  apis: { id: number; name: string; status: string }[]
}

/** 任务列表分页信封（tasks list / testcases list 统一形态） */
export interface TaskListPageDto<T> {
  items: T[]
  total: number
  page: number
  per_page: number
  pages: number
}

/** 挑选溯源（GET /tasks/{id}/cherry-pick-source，source_trace() 实测） */
export interface CherryPickSourceTraceDto {
  task_id: number
  is_cherry_pick: boolean
  total: number
  groups: {
    source_task_id: number
    source_task_name: string | null
    results: {
      result_id: number
      source_task_id: number
      source_task_name: string | null
      source_case_id: string | null
      source_device_id: number | null
      source_api_id: number | null
      missing: boolean
    }[]
  }[]
}

/** 测试设备（GET /test-devices，设备名装饰源） */
export interface TestDeviceBriefDto {
  id: number
  name: string
}

/** 测试 API（GET /apis，API 名装饰源） */
export interface TestApiBriefDto {
  id: number
  name: string
}

/** 测试用例（GET /testcases 分页，用例名装饰源） */
export interface TestCaseBriefDto {
  id: string
  name: string
}
