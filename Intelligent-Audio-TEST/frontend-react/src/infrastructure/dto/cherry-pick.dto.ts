/**
 * 挑选合并真实接口 DTO（infrastructure/dto 层——snake_case 唯一出现层；18_挑选合并交互重设计.md §7.3）。
 * 形态对照 cherry_pick_bp.py + cherry_pick_service.py（task_service）实测契约：
 * 候选行缺 case_name/device_name/api_name/result_type（§11-2 未补前前端按 ID/缺省降级）；
 * 购物车条目为溯源快照子集（缺 case/device/api 名称字段与 evaluation_status，§11-5 未补前为 null/缺省）。
 */
import type { TaskListItemDto } from '@/infrastructure/dto/task.dto'

/** 候选行 DTO（GET /tasks/cherry-picks/candidates，task_service.list_candidates 实测） */
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
  evaluated: boolean
  created_at: string | null
}

/** 候选行分页信封（candidates 响应：{ items, total, page, per_page }） */
export interface CherryPickCandidatePageDto {
  items: CherryPickCandidateDto[]
  total: number
  page: number
  per_page: number
}

/** 购物车条目 DTO（cherry_pick_repository.cart_list 实测快照） */
export interface PickCartEntryDto {
  item_id: number
  result_id: number
  source_task_id: number
  source_task_name: string
  source_case_id: string | null
  source_device_id: number | null
  source_api_id: number | null
  execution_status: string
  created_at: string | null
  /** 下单前校验：源结果已删除时 true（cherry_pick_service.cart_get 派生） */
  invalid: boolean
}

/** 购物车分组 DTO（cart_get 响应：按来源任务分组，条目键为 items） */
export interface PickCartGroupDto {
  source_task_id: number
  source_task_name: string
  items: PickCartEntryDto[]
}

/** 购物车响应 DTO（GET /tasks/cherry-picks/cart） */
export interface PickCartDto {
  groups: PickCartGroupDto[]
  total: number
  invalid_item_ids: number[]
}

/** 挑选集摘要 DTO（sets_list 响应项：{ set_id, name, description, item_count, created_at }） */
export interface PickSetDto {
  set_id: number
  name: string
  description: string | null
  item_count: number
  created_at: string | null
}

/** 复核摘要 DTO（POST /tasks/cherry-picks/preview，task_service.preview 实测） */
export interface PickPreviewDto {
  total_results: number
  invalid_result_ids: number[]
  source_task_count: number
  source_task_ids: number[]
  device_ids: number[]
  device_names: string[]
  case_count: number
  execution_status_counts: Record<string, number>
  duplicates: Array<{ device_id: number | null; case_id: string | null; count: number }>
  config_inconsistent: boolean
  config_fields: string[]
  source_configs: Array<{
    task_id: number
    task_name: string
    algorithm_type: string | null
    algorithm_params: Record<string, unknown> | null
    config: Record<string, unknown> | null
  }>
}

/** 统一合并容器 DTO（§11-1 落地前客户端双查询合并：merged=true ∪ cherry_pick=true → TaskListItemDto 行） */
export type CherryPickContainerDto = TaskListItemDto

/** 下单响应 DTO（action=merge → {task_id, result_count}；reexecute → {task_id, case_count, started}；
 *  reevaluate → {submitted_task_ids, failed, cleared}；交集 task_id） */
export interface CheckoutResultDto {
  task_id?: number | null
  result_count?: number | null
  case_count?: number | null
  started?: boolean | null
  submitted_task_ids?: number[]
  failed?: Array<{ task_id: number; message: string }>
  cleared?: boolean | null
}
