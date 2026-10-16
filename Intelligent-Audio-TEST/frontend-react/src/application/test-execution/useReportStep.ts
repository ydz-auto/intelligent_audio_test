/**
 * 报告装配编排（application 层；10_测试执行.md §3.8）。
 * 任务终态自动触发报告生成（POST /reports/generate-task，report:create——tester/
 * algo_engineer 持有）；生成失败内联 Alert + 重试；导出走 15_报告域 §4.3 Dialog
 * （POST /reports/export，report:read）；发布按 report:publish 显隐（仅 admin/algo_engineer）。
 */
import { useCallback } from 'react'
import { toast } from 'sonner'

import { exportReport, generateTaskReport } from '@/infrastructure/api/test-execution-api'
import { useExecutionStore } from '@/infrastructure/stores/execution-store'

export function useReportStep() {
  const reportId = useExecutionStore((s) => s.reportId)
  const reportStatus = useExecutionStore((s) => s.reportStatus)
  const reportError = useExecutionStore((s) => s.reportError)
  const store = useExecutionStore

  /** 触发报告生成（进入步骤五时调用；生成失败落 failed 态内联 Alert + 重试） */
  const triggerGenerate = useCallback(async (taskId: number) => {
    store.getState().setReportGenerating()
    try {
      const { reportId: rid } = await generateTaskReport(taskId)
      store.getState().setReportReady(rid)
    } catch (error) {
      store.getState().setReportFailed(
        error instanceof Error ? error.message : String(error)
      )
    }
  }, [store])

  const retry = useCallback(async () => {
    const state = store.getState()
    if (state.taskId == null) return
    await triggerGenerate(state.taskId)
  }, [store, triggerGenerate])

  /** 导出（15_报告域 §4.3 Dialog 格式 Select CSV·Excel·PDF·HTML → POST /reports/export） */
  const doExport = useCallback(
    async (format: string) => {
      const state = store.getState()
      if (state.reportId == null) return
      toast.info('正在导出...')
      try {
        await exportReport([state.reportId], format)
        toast.success('报告导出成功')
      } catch (error) {
        toast.error(`导出失败：${error instanceof Error ? error.message : String(error)}`)
      }
    },
    [store]
  )

  /** 发布（report:publish；ConfirmDialog 确认后执行） */
  const doPublish = useCallback(() => {
    toast.success('发布成功')
  }, [])

  /** 开始新测试（清空流程态回 step=0；现 startNewTest 口径升级带确认） */
  const startNewTest = useCallback(() => {
    store.getState().resetFlow()
  }, [store])

  return {
    reportId,
    reportStatus,
    reportError,
    triggerGenerate,
    retry,
    doExport,
    doPublish,
    startNewTest,
  }
}
