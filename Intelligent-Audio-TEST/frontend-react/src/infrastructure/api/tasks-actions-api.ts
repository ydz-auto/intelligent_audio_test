/**
 * 任务生命周期动作 API（infrastructure/api 层；接线 INT-932，09_任务域.md §3.6/§4）。
 * 对照 api_gateway/routes/task_bp.py + favorite_trash_bp.py 实测契约：
 *   DELETE /tasks/{task_id}                       （task:delete；软删 → 回收站）
 *   POST   /tasks/batch-action                    （task:batch；body {action, task_ids}，action=delete）
 *   POST   /tasks/{task_id}/favorite              （task:read；收藏）
 *   DELETE /tasks/{task_id}/favorite              （task:read；取消收藏）
 *   POST   /tasks/{task_id}/restore               （task:delete；单条恢复）
 *   POST   /tasks/restore                         （task:delete；body {ids} 批量恢复）
 *   DELETE /tasks/{task_id}/purge                 （task:delete；单条彻底删除，服务端按 metadata 校验 admin/owner）
 *   POST   /tasks/purge                           （task:delete；body {ids} 批量彻底删除）
 *   DELETE /tasks/{task_id}/cases/{case_id}       （task:execute；INT-305 移除用例）
 *   PUT    /tasks/{task_id}                       （task:update；更新任务名称/描述，INT-1277 挑选合并重命名）
 * 请求一律经 infrastructure/api/client.ts；snake_case 只在 infrastructure 层出现，
 * 页面层只见 camelCase；动作端点响应 data 本层不消费，成功即返回。
 */
import { apiClient } from '@/infrastructure/api/client'

/** 单个删除（软删 → 回收站）：DELETE /tasks/{id} */
export async function deleteTask(taskId: number): Promise<void> {
  await apiClient.delete<unknown>(`/tasks/${taskId}`)
}

/** 更新任务（重命名/描述）：PUT /tasks/{id} {name?, description?}（task:update，INT-1277） */
export async function updateTask(
  taskId: number,
  patch: { name?: string; description?: string }
): Promise<void> {
  await apiClient.put<unknown>(`/tasks/${taskId}`, {
    name: patch.name,
    description: patch.description,
  })
}

/** 批量删除（回收站）：POST /tasks/batch-action {action: 'delete', task_ids} */
export async function batchDeleteTasks(taskIds: number[]): Promise<void> {
  await apiClient.post<unknown>('/tasks/batch-action', {
    action: 'delete',
    task_ids: taskIds,
  })
}

/** 收藏：POST /tasks/{id}/favorite（幂等） */
export async function favoriteTask(taskId: number): Promise<void> {
  await apiClient.post<unknown>(`/tasks/${taskId}/favorite`)
}

/** 取消收藏：DELETE /tasks/{id}/favorite（幂等） */
export async function unfavoriteTask(taskId: number): Promise<void> {
  await apiClient.delete<unknown>(`/tasks/${taskId}/favorite`)
}

/** 单条恢复（回收站 → 日常）：POST /tasks/{id}/restore */
export async function restoreTask(taskId: number): Promise<void> {
  await apiClient.post<unknown>(`/tasks/${taskId}/restore`)
}

/** 批量恢复：POST /tasks/restore {ids} */
export async function batchRestoreTasks(taskIds: number[]): Promise<void> {
  await apiClient.post<unknown>('/tasks/restore', { ids: taskIds })
}

/** 单条彻底删除：DELETE /tasks/{id}/purge（admin/owner 服务端校验） */
export async function purgeTask(taskId: number): Promise<void> {
  await apiClient.delete<unknown>(`/tasks/${taskId}/purge`)
}

/** 批量彻底删除：POST /tasks/purge {ids} */
export async function batchPurgeTasks(taskIds: number[]): Promise<void> {
  await apiClient.post<unknown>('/tasks/purge', { ids: taskIds })
}

/** 移除用例（INT-305；待执行/执行中/已完成/评估完成四阶段全允许）：DELETE /tasks/{id}/cases/{caseId} */
export async function removeTaskCase(taskId: number, caseId: string): Promise<void> {
  await apiClient.delete<unknown>(`/tasks/${taskId}/cases/${caseId}`)
}
