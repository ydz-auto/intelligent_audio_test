/**
 * 已发布任务生命周期动作 API（infrastructure/api 层；接线 INT-1287）。
 * 对照 api_gateway/routes/published_task_bp.py 实测契约（权限码见 09_任务域.md §3.7）：
 *   POST /published-tasks/{id}/execute   （published_task:execute；按冻结快照创建日常任务）
 *   POST /published-tasks/{id}/versions  （published_task:version；创建新版本，name 留空沿用当前名）
 *   POST /published-tasks/{id}/archive   （published_task:archive；归档后不可直接执行）
 *   PUT  /published-tasks/{id}           （published_task:read；重命名，作用于整个版本链）
 * 请求一律经 infrastructure/api/client.ts；snake_case 契约照 published_task.py 实测透传。
 */
import { toPublishedTaskExecuteResult } from '@/infrastructure/adapters/dto/task-adapter'
import { request } from '@/infrastructure/api/client'
import type { PublishedTaskExecuteResultDto } from '@/infrastructure/dto/task.dto'
import type { PublishedTaskExecuteResult } from '@/domain/models/task'

/** 执行已发布任务（POST execute → PublishedTaskExecuteData；返回创建出的日常任务） */
export async function executePublishedTask(
  publishedTaskId: number
): Promise<PublishedTaskExecuteResult> {
  const dto = await request<PublishedTaskExecuteResultDto>(
    'POST',
    `/published-tasks/${publishedTaskId}/execute`
  )
  return toPublishedTaskExecuteResult(dto)
}

/** 创建已发布任务新版本（POST versions；name 留空沿用当前版本名称） */
export async function createPublishedTaskVersion(
  publishedTaskId: number,
  name?: string
): Promise<void> {
  const body = name?.trim() ? { name: name.trim() } : {}
  await request<unknown>('POST', `/published-tasks/${publishedTaskId}/versions`, body)
}

/** 归档已发布任务（POST archive；归档后禁止直接执行） */
export async function archivePublishedTask(publishedTaskId: number): Promise<void> {
  await request<unknown>('POST', `/published-tasks/${publishedTaskId}/archive`)
}

/** 重命名已发布任务（PUT；同步更新整个版本链） */
export async function renamePublishedTask(
  publishedTaskId: number,
  name: string
): Promise<void> {
  await request<unknown>('PUT', `/published-tasks/${publishedTaskId}`, { name })
}
