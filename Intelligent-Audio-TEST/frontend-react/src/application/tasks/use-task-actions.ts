/**
 * 任务生命周期动作 mutation 聚合（application 层；接线 INT-932）。
 * 覆盖行操作（删除/收藏/恢复/彻底删除/暂停/继续/停止/重命名）与批量操作
 * （批量删除/批量恢复/批量彻底删除），以及详情页暂停/继续/停止/移除用例。
 * 成功后统一失效 ['tasks'] 前缀 query（列表/详情一并刷新，分页/筛选不变）；
 * 失败统一 toast 错误（ApiError.userMessage 中文文案）。
 * 任务对比（§6）为报告域动作，经 reports-api.compareReports 生成对比报告后跳转，见页面层。
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { ApiError } from '@/infrastructure/api/api-error'
import {
  batchDeleteTasks,
  batchPurgeTasks,
  batchRestoreTasks,
  deleteTask,
  favoriteTask,
  purgeTask,
  removeTaskCase,
  restoreTask,
  unfavoriteTask,
  updateTask,
} from '@/infrastructure/api/tasks-actions-api'
import { controlTask, stopTask } from '@/infrastructure/api/tasks-control-api'

/** 错误 → 可展示文案（复用 reexecute-scope-dialog 同款收敛） */
function toErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.userMessage || error.message || fallback
  return fallback
}

export function useTaskActions() {
  const queryClient = useQueryClient()

  /** 列表/详情前缀统一失效（批量/行操作后刷新当前筛选态列表与详情） */
  const invalidateTasks = () => {
    void queryClient.invalidateQueries({ queryKey: ['tasks'] })
  }

  const remove = useMutation({
    mutationFn: (taskId: number) => deleteTask(taskId),
    onSuccess: () => {
      toast.success('已移入回收站')
      invalidateTasks()
    },
    onError: (error) => toast.error(toErrorMessage(error, '删除失败')),
  })

  const batchRemove = useMutation({
    mutationFn: (taskIds: number[]) => batchDeleteTasks(taskIds),
    onSuccess: (_data, taskIds) => {
      toast.success(`已批量移入回收站 ${taskIds.length} 个`)
      invalidateTasks()
    },
    onError: (error) => toast.error(toErrorMessage(error, '批量删除失败')),
  })

  const favorite = useMutation({
    mutationFn: (taskId: number) => favoriteTask(taskId),
    onSuccess: () => {
      toast.success('已加入收藏')
      invalidateTasks()
    },
    onError: (error) => toast.error(toErrorMessage(error, '收藏失败')),
  })

  const unfavorite = useMutation({
    mutationFn: (taskId: number) => unfavoriteTask(taskId),
    onSuccess: () => {
      toast.success('已取消收藏')
      invalidateTasks()
    },
    onError: (error) => toast.error(toErrorMessage(error, '取消收藏失败')),
  })

  const restore = useMutation({
    mutationFn: (taskId: number) => restoreTask(taskId),
    onSuccess: () => {
      toast.success('已恢复')
      invalidateTasks()
    },
    onError: (error) => toast.error(toErrorMessage(error, '恢复失败')),
  })

  const batchRestore = useMutation({
    mutationFn: (taskIds: number[]) => batchRestoreTasks(taskIds),
    onSuccess: (_data, taskIds) => {
      toast.success(`已批量恢复 ${taskIds.length} 个`)
      invalidateTasks()
    },
    onError: (error) => toast.error(toErrorMessage(error, '批量恢复失败')),
  })

  const purge = useMutation({
    mutationFn: (taskId: number) => purgeTask(taskId),
    onSuccess: () => {
      toast.success('已彻底删除')
      invalidateTasks()
    },
    onError: (error) => toast.error(toErrorMessage(error, '彻底删除失败')),
  })

  const batchPurge = useMutation({
    mutationFn: (taskIds: number[]) => batchPurgeTasks(taskIds),
    onSuccess: (_data, taskIds) => {
      toast.success(`已批量彻底删除 ${taskIds.length} 个`)
      invalidateTasks()
    },
    onError: (error) => toast.error(toErrorMessage(error, '批量彻底删除失败')),
  })

  const control = useMutation({
    mutationFn: ({ taskId, action }: { taskId: number; action: 'pause' | 'resume' }) =>
      controlTask(taskId, action),
    onSuccess: (_data, { action }) => {
      toast.success(action === 'pause' ? '任务已暂停' : '任务已继续')
      invalidateTasks()
    },
    onError: (error) => toast.error(toErrorMessage(error, '控制任务失败')),
  })

  const stop = useMutation({
    mutationFn: (taskId: number) => stopTask(taskId),
    onSuccess: () => {
      toast.success('任务已停止')
      invalidateTasks()
    },
    onError: (error) => toast.error(toErrorMessage(error, '停止任务失败')),
  })

  const removeCase = useMutation({
    mutationFn: ({ taskId, caseId }: { taskId: number; caseId: string }) =>
      removeTaskCase(taskId, caseId),
    onSuccess: () => {
      toast.success('已移除用例')
      invalidateTasks()
    },
    onError: (error) => toast.error(toErrorMessage(error, '移除用例失败')),
  })

<<<<<<< HEAD
  const rename = useMutation({
    mutationFn: ({
      taskId,
      patch,
    }: {
      taskId: number
      patch: { name?: string; description?: string }
    }) => updateTask(taskId, patch),
=======
  /** 重命名（INT-1290：PUT /tasks/{id} {name}；成功后列表/详情经 ['tasks'] 前缀统一刷新） */
  const rename = useMutation({
    mutationFn: ({ taskId, name }: { taskId: number; name: string }) =>
      updateTaskName(taskId, name),
>>>>>>> 8c00cec08 (chore(agent): uncommitted changes from task)
    onSuccess: () => {
      toast.success('任务名称已更新')
      invalidateTasks()
    },
<<<<<<< HEAD
    onError: (error) => toast.error(toErrorMessage(error, '更新任务失败')),
=======
    onError: (error) => toast.error(toErrorMessage(error, '重命名失败')),
>>>>>>> 8c00cec08 (chore(agent): uncommitted changes from task)
  })

  return {
    remove,
    batchRemove,
    favorite,
    unfavorite,
    restore,
    batchRestore,
    purge,
    batchPurge,
    control,
    stop,
    removeCase,
    rename,
  }
}
