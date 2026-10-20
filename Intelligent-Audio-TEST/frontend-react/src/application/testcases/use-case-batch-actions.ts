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
import { deleteGroup } from '@/infrastructure/api/groups-api'
import {
  batchTestcaseAction,
  fetchRefreshTaskStatus,
  purgeTestcases,
} from '@/infrastructure/api/testcases-batch-api'
import {
  deleteTestCase,
  purgeTestCase,
  restoreTestCase,
} from '@/infrastructure/api/testcases-api'

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

  /** 批量弹窗关闭后刷新列表（设置成功/取消后均刷新，成本低；INT-710 真实提交后列表可见结果）。
   * 调整分组影响分组计数、管理标签影响标签登记，一并失效对应 query。 */
  useEffect(() => {
    if (batchDialog === null) return
    return () => {
      void queryClient.invalidateQueries({ queryKey: ['testcases'] })
      if (batchDialog.kind === 'group') {
        void queryClient.invalidateQueries({ queryKey: ['groups'] })
      }
      if (batchDialog.kind === 'tags') {
        void queryClient.invalidateQueries({ queryKey: ['tags'] })
      }
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
        setConfirm({ kind: 'batch-copy', count, ids })
        break
      case 'delete':
        setConfirm({ kind: 'batch-delete', count, ids })
        break
      case 'restore':
        setConfirm({ kind: 'batch-restore', count, ids })
        break
      case 'purge':
        setConfirm({ kind: 'batch-purge', count, ids })
        break
      case 'name':
        setConfirm({ kind: 'auto-name', count, ids })
        break
      case 'refresh':
        setConfirm({ kind: 'refresh', count, ids })
        break
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

  /** 确认弹窗回调（行内/分组/批量同源；INT-997 接真实接口，失败保留弹窗可重试/取消） */
  const handleConfirm = async (state: CaseConfirmState) => {
    try {
      const ids = state.ids ?? []
      switch (state.kind) {
        case 'delete':
          // INT-997：行删除接 DELETE /testcases/{id}（逻辑删除 → 回收站）
          if (ids[0]) await deleteTestCase(ids[0])
          toast.success('已移入回收站')
          break
        case 'purge':
          // INT-997：行彻底删除接 DELETE /testcases/{id}/purge（admin/owner 由服务端校验）
          if (ids[0]) await purgeTestCase(ids[0])
          toast.success('已彻底删除')
          break
        case 'restore':
          // INT-997：行恢复接 POST /testcases/{id}/restore
          if (ids[0]) await restoreTestCase(ids[0])
          toast.success(`用例「${state.name}」已恢复`)
          break
        case 'delete-group':
          // INT-997：删除分组接 DELETE /groups/{id}?cascade=true（连同组下用例，不可逆）
          if (ids[0]) await deleteGroup(ids[0], true)
          toast.success('删除分组成功')
          break
        case 'restore-all':
          // INT-997：全部恢复接 POST /testcases/batch（restore），ids 为当前回收站可见已删用例
          if (ids.length > 0) await batchTestcaseAction('restore', ids, {})
          toast.success(`已恢复 ${state.count ?? 0} 个用例`)
          break
        case 'batch-copy':
          // INT-997：批量复制接 POST /testcases/batch（copy，保留原分组、名称追加 _copy）
          await batchTestcaseAction('copy', ids, {})
          toast.success('批量复制成功')
          break
        case 'batch-delete':
          // INT-997：批量删除接 POST /testcases/batch（delete，批量软删入回收站）
          await batchTestcaseAction('delete', ids, {})
          toast.success('已批量移入回收站')
          break
        case 'batch-restore':
          // INT-997：批量恢复接 POST /testcases/batch（restore，仅已删行计入）
          await batchTestcaseAction('restore', ids, {})
          toast.success('已批量恢复')
          break
        case 'batch-purge':
          // INT-997：批量彻底删除接 POST /testcases/purge（batch 无 purge 动作，走独立路由）
          await purgeTestcases(ids)
          toast.success('已批量彻底删除')
          break
        case 'auto-name':
          // INT-710：批量自动生成名称走真实 POST /testcases/batch（auto_generate_name）
          await batchTestcaseAction('auto_generate_name', ids, {})
          toast.success('自动生成名称完成')
          break
        case 'refresh':
          // INT-710：刷新参考参数走真实 POST /testcases/batch（refresh_reference → 异步任务）
          await refreshReferenceParams(ids)
          break
      }
      await queryClient.invalidateQueries({ queryKey: ['testcases'] })
      if (state.kind === 'delete-group') {
        await queryClient.invalidateQueries({ queryKey: ['groups'] })
      }
      onClearSelection()
      setConfirm(null)
    } catch (error) {
      // 失败保留确认弹窗（用户可重试 / 取消），仅 toast 报错
      toast.error(error instanceof Error ? error.message : '操作失败')
    }
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
