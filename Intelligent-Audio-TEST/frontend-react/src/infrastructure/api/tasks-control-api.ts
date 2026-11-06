/**
 * 任务控制类 API（infrastructure/api 层；接线 INT-694，09_任务域.md §5.7）。
 * 对照 api_gateway/routes/task_bp.py + evaluation_bp.py 实测：
 *   POST /tasks/{task_id}/retry        （task:execute；INT-302 按用例选择：body {case_ids, mode}）
 *   POST /evaluation/task/reevaluate   （evaluation:execute；TaskReevaluateInput：
 *       task_id/reevaluate_type/reextract_device_output/case_ids/dimension_ids/mode）
 *   POST /tasks/{task_id}/control      （task:execute；body {action: pause|resume}，INT-932 接线）
 *   POST /tasks/{task_id}/stop         （task:execute；停止任务，INT-932 接线）
 * 请求一律经 infrastructure/api/client.ts；snake_case 只在 infrastructure/dto 层出现，
 * DTO→Domain 转换收敛在 adapters/dto/task-adapter，页面层只见 camelCase。
 */
import type { TaskReevaluateResult, TaskRetryResult } from '@/domain/models/task'
import { apiClient } from '@/infrastructure/api/client'
import {
  toTaskReevaluateResult,
  toTaskRetryResult,
} from '@/infrastructure/adapters/dto/task-adapter'
import type {
  TaskReevaluateResultDto,
  TaskRetryResultDto,
} from '@/infrastructure/dto/task.dto'

/** 重新执行范围（§5.7 三选项） */
export type ReexecuteScopeMode = 'all' | 'failed_only' | 'selected'

/** 重新执行：POST /tasks/{id}/retry（缺省整任务语义；caseIds 仅 mode=selected 携带） */
export async function retryTask(
  taskId: number,
  payload: { mode: ReexecuteScopeMode; caseIds?: string[] }
): Promise<TaskRetryResult> {
  const dto = await apiClient.post<TaskRetryResultDto>(`/tasks/${taskId}/retry`, {
    case_ids: payload.mode === 'selected' ? (payload.caseIds ?? []) : [],
    mode: payload.mode,
  })
  return toTaskRetryResult(dto)
}

/** 重新评估：POST /evaluation/task/reevaluate（dimensionIds 空数组 = 不过滤全量；reextract 默认 false） */
export async function reevaluateTask(
  taskId: number,
  payload: {
    mode: ReexecuteScopeMode
    caseIds?: string[]
    /** 空数组 = 全选（不过滤），仅显式子集时下发（对齐 ReexecuteOptionsModal INT-302 口径） */
    dimensionIds?: number[]
    reextractDeviceOutput?: boolean
  }
): Promise<TaskReevaluateResult> {
  const dto = await apiClient.post<TaskReevaluateResultDto>('/evaluation/task/reevaluate', {
    task_id: taskId,
    reevaluate_type: payload.mode,
    reextract_device_output: payload.reextractDeviceOutput ?? false,
    case_ids: payload.mode === 'selected' ? (payload.caseIds ?? []) : [],
    dimension_ids: payload.dimensionIds ?? [],
    mode: payload.mode,
  })
  return toTaskReevaluateResult(dto)
}

/** 控制动作（暂停/继续）：POST /tasks/{id}/control {action: 'pause'|'resume'} */
export async function controlTask(
  taskId: number,
  action: 'pause' | 'resume'
): Promise<void> {
  await apiClient.post<unknown>(`/tasks/${taskId}/control`, { action })
}

/** 停止任务：POST /tasks/{id}/stop */
export async function stopTask(taskId: number): Promise<void> {
  await apiClient.post<unknown>(`/tasks/${taskId}/stop`)
}
