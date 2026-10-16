/**
 * 流程步骤态（application 层；10_测试执行.md §3.2/§4）。
 * URL search step 同步（zod 白名单 0-4 catch 0）——刷新/回退/分享保持；
 * canEnterStep 校验集中一处（照 setup-wizard validate* 模式声明式）；
 * 跳转未解锁步骤 = toast.warning + Tooltip 说明（不静默）。
 */
import { useNavigate, useSearch } from '@tanstack/react-router'
import { useCallback, useMemo } from 'react'
import { toast } from 'sonner'

import { useReadOnlyMode } from '@/application/test-execution/useReadOnlyMode'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'
import { useCaseSelectionStore } from '@/infrastructure/stores/case-selection-store'
import { useExecutionStore } from '@/infrastructure/stores/execution-store'
import { navigateWithSearch } from '@/features/test-execution/lib/navigate-search'

export type FlowStep = 0 | 1 | 2 | 3 | 4

const STEP_HINT: Record<FlowStep, string> = {
  0: '请先选择算法',
  1: '请先选择测试用例',
  2: '请先选择测试资源',
  3: '请先启动测试任务',
  4: '请等待报告生成完成',
}

/** 步骤解锁校验（声明式纯函数；step≥2 需已选算法；step=3 需任务已启动；step=4 需报告就绪） */
export function canEnterStep(
  target: number,
  state: {
    algorithmSelected: boolean
    taskStarted: boolean
    reportReady: boolean
  }
): { ok: boolean; hint?: string } {
  if (target <= 1) return { ok: true }
  if (!state.algorithmSelected) return { ok: false, hint: STEP_HINT[0] }
  if (target === 3 && !state.taskStarted) return { ok: false, hint: STEP_HINT[3] }
  if (target === 4 && !state.reportReady) return { ok: false, hint: STEP_HINT[4] }
  return { ok: true }
}

export function useFlowSteps() {
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as unknown as { step?: number }
  const readOnly = useReadOnlyMode()
  const algorithmId = useAlgorithmStore((s) => s.algorithmId)
  const taskId = useExecutionStore((s) => s.taskId)
  const reportStatus = useExecutionStore((s) => s.reportStatus)
  const caseSelection = useCaseSelectionStore()

  const step = useMemo<FlowStep>(() => {
    const raw = search.step
    return Number.isInteger(raw) && raw != null && raw >= 0 && raw <= 4 ? (raw as FlowStep) : 0
  }, [search.step])

  const reportReady = reportStatus === 'ready'

  const goToStep = useCallback(
    (target: number, opts?: { force?: boolean }) => {
      const gate = canEnterStep(target, {
        algorithmSelected: Boolean(algorithmId),
        taskStarted: taskId != null,
        reportReady,
      })
      if (!gate.ok && !opts?.force && !readOnly) {
        toast.warning(gate.hint ?? '该步骤尚未解锁')
        return
      }
      // 跨路由 search 更新（/E2ETest 与 /APITest 共用组件，to 不固定——照 reports-showcase cast 口径）
      navigateWithSearch(navigate, { step: target })
    },
    [algorithmId, taskId, reportReady, readOnly, navigate]
  )

  const nextStep = useCallback(() => {
    goToStep(Math.min(step + 1, 4) as FlowStep)
  }, [step, goToStep])

  const prevStep = useCallback(() => {
    goToStep(Math.max(step - 1, 0) as FlowStep, { force: true })
  }, [step, goToStep])

  return {
    step,
    nextStep,
    prevStep,
    goToStep,
    /** 已完成步骤（step 之前且已解锁）可回跳浏览 */
    canBrowseStep: (target: number) => {
      if (target > step) return canEnterStep(target, { algorithmSelected: Boolean(algorithmId), taskStarted: taskId != null, reportReady }).ok
      return true
    },
    hasProgress: caseSelection.manualCaseIds.length > 0 || Boolean(taskId) || algorithmId != null,
  }
}
