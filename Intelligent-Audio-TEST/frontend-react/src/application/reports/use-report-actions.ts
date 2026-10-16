/**
 * 报告变更操作聚合（application 层）：发布/软删/恢复/彻底删除/收藏/重命名/导出。
 * 出图先：调 infrastructure API 桩 + toast 反馈 + 列表失效重拉（演示交互闭环）；
 * TODO(API 接线): 桩替换真实端点后本层无需改动（返回形保持一致）。
 */
import { useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'
import { toast } from 'sonner'

import {
  batchDeleteReports,
  deleteReport,
  exportReports,
  generateTaskReport,
  publishReport,
  purgeReport,
  regenerateReport,
  restoreReport,
  toggleReportFavorite,
  updateReport,
} from '@/infrastructure/api/reports-api'
import { useReportsUiStore } from '@/infrastructure/stores/reports-ui-store'

export function useReportActions() {
  const queryClient = useQueryClient()

  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['reports'] })
    void queryClient.invalidateQueries({ queryKey: ['reports', 'tab-counts'] })
  }, [queryClient])

  const publish = useCallback(
    async (id: number) => {
      await publishReport(id)
      toast.success('报告发布成功')
      refresh()
    },
    [refresh]
  )

  /** 取消发布（快照语义：桩写回 name 保持成功回执；TODO(API 接线): POST /reports/{id}/unpublish） */
  const unpublish = useCallback(
    async (id: number, name?: string) => {
      await updateReport(id, { name: name || undefined })
      toast.success('已取消发布')
      refresh()
    },
    [refresh]
  )

  const rename = useCallback(
    async (id: number, payload: { name?: string; description?: string }) => {
      await updateReport(id, payload)
      toast.success('报告保存成功')
      refresh()
    },
    [refresh]
  )

  const softDelete = useCallback(
    async (ids: number[]) => {
      useReportsUiStore.getState().softDelete(ids)
      await deleteReport(ids[0]).catch(() => {})
      toast.success(ids.length > 1 ? `成功删除 ${ids.length} 个报告` : '报告已删除')
      refresh()
    },
    [refresh]
  )

  const restore = useCallback(
    async (ids: number[]) => {
      useReportsUiStore.getState().restore(ids)
      await restoreReport(ids[0]).catch(() => {})
      toast.success(ids.length > 1 ? `已恢复 ${ids.length} 个报告` : '报告已恢复')
      refresh()
    },
    [refresh]
  )

  const purge = useCallback(
    async (ids: number[]) => {
      useReportsUiStore.getState().purge(ids)
      await purgeReport(ids[0]).catch(() => {})
      toast.success('已彻底删除')
      refresh()
    },
    [refresh]
  )

  const toggleFavorite = useCallback(async (id: number, nextFavorite: boolean) => {
    useReportsUiStore.getState().toggleFavorite(id)
    await toggleReportFavorite(id).catch(() => {})
    toast.success(nextFavorite ? '已收藏' : '已取消收藏')
    refresh()
  }, [refresh])

  const regenerate = useCallback(
    async (id: number) => {
      await regenerateReport(id)
      toast.success('报告已重新生成')
      refresh()
    },
    [refresh]
  )

  /** 生成报告（POST /reports/generate-task；返回新报告 id） */
  const generate = useCallback(
    async (taskId: number, name?: string, description?: string): Promise<number> => {
      const result = await generateTaskReport({ task_id: taskId, name, description })
      toast.success('报告已生成')
      refresh()
      return result.report_id
    },
    [refresh]
  )

  const exportReport = useCallback(
    async (ids: number[], format: string) => {
      await exportReports({ ids, format })
      toast.success('报告已导出')
    },
    []
  )

  return {
    publish,
    unpublish,
    rename,
    softDelete,
    restore,
    purge,
    toggleFavorite,
    regenerate,
    generate,
    exportReport,
    refresh,
  }
}

/** 批量软删/彻底删除（列表勾选浮条用） */
export function useBatchReportActions() {
  const queryClient = useQueryClient()
  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['reports'] })
    void queryClient.invalidateQueries({ queryKey: ['reports', 'tab-counts'] })
  }, [queryClient])

  const batchDelete = useCallback(
    async (ids: number[]) => {
      useReportsUiStore.getState().softDelete(ids)
      await batchDeleteReports(ids).catch(() => {})
      toast.success(`成功删除 ${ids.length} 个报告`)
      refresh()
    },
    [refresh]
  )

  const batchRestore = useCallback(
    async (ids: number[]) => {
      useReportsUiStore.getState().restore(ids)
      await restoreReport(ids[0]).catch(() => {})
      toast.success(`已恢复 ${ids.length} 个报告`)
      refresh()
    },
    [refresh]
  )

  const batchPurge = useCallback(
    async (ids: number[]) => {
      useReportsUiStore.getState().purge(ids)
      await purgeReport(ids[0]).catch(() => {})
      toast.success('已彻底删除')
      refresh()
    },
    [refresh]
  )

  return { batchDelete, batchRestore, batchPurge }
}
