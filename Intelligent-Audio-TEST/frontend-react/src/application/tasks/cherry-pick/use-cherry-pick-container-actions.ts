/**
 * 合并容器批量操作 mutation 聚合（application/tasks/cherry-pick，18_挑选合并交互重设计.md §2.3
 * DataTablePage 批量浮条；INT-1278 接线——容器级批量操作从「待接线」禁用占位转为真实请求）。
 * 容器即任务（TaskMergeRelation / TaskCherryPickRelation 一等公民，status=completed）：
 *   批量删除  POST /tasks/batch-action {action:'delete', task_ids}（软删进回收站，task:batch）
 *   批量收藏  POST /tasks/{id}/favorite 逐容器（幂等；task:read，无批量收藏端点）
 * 成功后统一失效 ['tasks'] 前缀（容器列表 queryKey ['tasks','cherry-picks',…] 一并刷新）；
 * 失败统一 toast 错误（ApiError.userMessage 中文文案）。清空选择由页面层在 onSuccess 处理。
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { ApiError } from '@/infrastructure/api/api-error'
import {
  batchDeleteTasks,
  favoriteTask,
} from '@/infrastructure/api/tasks-actions-api'

/** 错误 → 可展示文案（复用 useTaskActions 同款收敛） */
function toErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.userMessage || error.message || fallback
  return fallback
}

export function useCherryPickContainerActions() {
  const queryClient = useQueryClient()

  /** 容器列表/任务列表前缀统一失效（批量删除/收藏后刷新当前筛选态容器列表） */
  const invalidateTasks = () => {
    void queryClient.invalidateQueries({ queryKey: ['tasks'] })
  }

  /** 批量删除（软删进回收站）：POST /tasks/batch-action {action:'delete', task_ids} */
  const batchRemove = useMutation({
    mutationFn: (containerIds: number[]) => batchDeleteTasks(containerIds),
    onSuccess: (_data, containerIds) => {
      toast.success(`已批量移入回收站 ${containerIds.length} 个`)
      invalidateTasks()
    },
    onError: (error) => toast.error(toErrorMessage(error, '批量删除失败')),
  })

  /** 批量收藏：POST /tasks/{id}/favorite 逐容器（幂等；无批量端点，按选中容器循环） */
  const batchFavorite = useMutation({
    mutationFn: async (containerIds: number[]) => {
      for (const id of containerIds) {
        await favoriteTask(id)
      }
    },
    onSuccess: (_data, containerIds) => {
      toast.success(`已批量收藏 ${containerIds.length} 个`)
      invalidateTasks()
    },
    onError: (error) => toast.error(toErrorMessage(error, '批量收藏失败')),
  })

  return { batchRemove, batchFavorite }
}
