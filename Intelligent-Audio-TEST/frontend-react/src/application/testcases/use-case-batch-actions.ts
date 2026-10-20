/**
 * 用例批量弹窗状态编排（application 层；INT-1026 /testcases 与 /start-test 双挂）。
 * 组头「批量修改」九项 + 批量浮条共用同一状态机：
 * 七件套弹窗（用例专属参数/播放设备/声压/评估维度/调整分组/噪声/管理标签）
 * + 两确认（标签生成名称/用例参考更新）；渲染装配在 CaseBatchActionsHost。
 * ids 沿用 GroupedCaseList resolveCaseIds 语义（组内勾选优先、否则组内全量）；
 * name/refresh 确认执行用弹窗打开时捕获的 ids（INT-1026 修复点：组头无勾选时
 * 也正确作用于组内全量，替代旧实现读页级勾选集）。
 */
import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { BatchActionKey } from '@/features/testcases/components/case-bulk-actions'
import type { CaseConfirmState } from '@/features/testcases/modals/case-confirms'
import {
  batchTestcaseAction,
  fetchRefreshTaskStatus,
} from '@/infrastructure/api/testcases-batch-api'

/** 七件套批量弹窗（对应组头「批量修改」/批量浮条同源载荷，BatchActionKey 子集） */
export type BatchDialogKind =
  | 'dimensions'
  | 'group'
  | 'tags'
  | 'params'
  | 'device'
  | 'spl'
  | 'noise'

export interface BatchDialogState {
  kind: BatchDialogKind
  count: number
  ids: string[]
}

export function useCaseBatchActions({
  onClearSelection,
}: {
  /** 确认执行后清空本页勾选集（/testcases 本地 Set / /start-test 用例选择 store） */
  onClearSelection: () => void
}) {
  const queryClient = useQueryClient()
  const [batchDialog, setBatchDialog] = useState<BatchDialogState | null>(null)
  const [confirm, setConfirm] = useState<CaseConfirmState | null>(null)

  /** 批量弹窗关闭后刷新列表（设置成功/取消后均刷新，成本低；INT-710 真实提交后列表可见结果） */
  useEffect(() => {
    if (batchDialog === null) return
    return () => {
      void queryClient.invalidateQueries({ queryKey: ['testcases'] })
    }
  }, [batchDialog, queryClient])

  const openBatch = (action: BatchActionKey, ids: string[]) => {
    const count = ids.length
    switch (action) {
      case 'dimensions':
      case 'group':
      case 'tags':
      case 'params':
      case 'device':
      case 'spl':
      case 'noise':
        setBatchDialog({ kind: action, count, ids })
        break
      case 'copy':
        setConfirm({ kind: 'batch-copy', count })
        break
      case 'delete':
        setConfirm({ kind: 'batch-delete', count })
        break
      case 'restore':
        setConfirm({ kind: 'batch-restore', count })
        break
      case 'purge':
        setConfirm({ kind: 'batch-purge', count })
        break
      case 'name':
        setConfirm({ kind: 'auto-name', count, ids })
        break
      case 'refresh':
        setConfirm({ kind: 'refresh', count, ids })
        break
      default:
        toast.success('批量操作执行成功（演示：完整弹窗随接线批次落地）')
    }
  }

  /** 刷新参考参数（§5.3.9）：POST /testcases/batch → task_id → 1s 轮询完成统计 */
  const refreshReferenceParams = async (ids: string[]) => {
    try {
      const result = await batchTestcaseAction('refresh_reference', ids, {})
      if (result.taskId) {
        void pollRefreshTask(result.taskId)
        toast.success('已提交刷新任务')
      } else {
        toast.success(`已成功刷新 ${ids.length} 个用例的参考参数`)
      }
      queryClient.invalidateQueries({ queryKey: ['testcases'] })
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '刷新用例参考失败')
    }
  }

  const pollRefreshTask = async (taskId: string) => {
    try {
      let status = await fetchRefreshTaskStatus(taskId)
      while (status.status !== 'completed' && status.status !== 'failed') {
        await new Promise((r) => setTimeout(r, 1000))
        status = await fetchRefreshTaskStatus(taskId)
      }
      if (status.status === 'completed') {
        toast.success(`用例参考更新完成！成功刷新: ${status.updated} 个｜失败: ${status.failed} 个`)
      } else {
        toast.error('用例参考更新任务执行失败，请稍后重试')
      }
      queryClient.invalidateQueries({ queryKey: ['testcases'] })
    } catch {
      // 轮询失败不阻断（后台任务仍可能完成）
    }
  }

  /** 确认弹窗回调（行内/分组/批量同源；执行后清空勾选并关闭确认） */
  const handleConfirm = (state: CaseConfirmState) => {
    switch (state.kind) {
      case 'delete':
        toast.success('已移入回收站')
        break
      case 'purge':
        toast.success('已彻底删除')
        break
      case 'restore':
        toast.success(`用例「${state.name}」已恢复`)
        break
      case 'delete-group':
        toast.success('删除分组成功')
        break
      case 'restore-all':
        toast.success(`已恢复 ${state.count ?? 0} 个用例`)
        break
      case 'batch-copy':
        toast.success('批量复制成功')
        break
      case 'batch-delete':
        toast.success('已批量移入回收站')
        break
      case 'batch-restore':
        toast.success('已批量恢复')
        break
      case 'batch-purge':
        toast.success('已批量彻底删除')
        break
      case 'auto-name':
        // INT-710：批量自动生成名称走真实 POST /testcases/batch（auto_generate_name）
        void (async () => {
          try {
            await batchTestcaseAction('auto_generate_name', state.ids ?? [], {})
            toast.success('自动生成名称完成')
            await queryClient.invalidateQueries({ queryKey: ['testcases'] })
          } catch (error) {
            toast.error(error instanceof Error ? error.message : '自动生成名称失败')
          }
        })()
        break
      case 'refresh':
        // INT-710：刷新参考参数走真实 POST /testcases/batch（refresh_reference → 异步任务）
        void refreshReferenceParams(state.ids ?? [])
        break
    }
    onClearSelection()
    setConfirm(null)
  }

  return {
    batchDialog,
    setBatchDialog,
    confirm,
    setConfirm,
    openBatch,
    handleConfirm,
    /** 任一批量弹窗/确认打开（页级 ESC 清选守卫用） */
    isBatchOpen: batchDialog != null || confirm != null,
  }
}
