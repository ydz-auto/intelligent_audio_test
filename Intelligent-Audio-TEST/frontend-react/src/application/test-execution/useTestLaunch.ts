/**
 * 测试启动编排（application 层；10_测试执行.md §3.7 启动校验链）。
 * 校验（全部 toast.warning，照 setup-wizard toast.error 模式）→ 任务名称默认值 →
 * POST /tasks（task:create）+ POST /tasks/{id}/start（task:execute）→ 成功跳 step=3；
 * 失败 toast.error「创建或启动测试任务失败：{message}」。
 */
import { useNavigate } from '@tanstack/react-router'
import { useCallback, useMemo } from 'react'
import { toast } from 'sonner'

import { createTask, startTask } from '@/infrastructure/api/test-execution-api'
import { useExecutionStore } from '@/infrastructure/stores/execution-store'
import { useCaseSelectionStore } from '@/infrastructure/stores/case-selection-store'
import { useResourceSelectionStore } from '@/infrastructure/stores/resource-selection-store'
import { navigateWithSearch } from '@/features/test-execution/lib/navigate-search'
import type { ExecutionParams, TaskLaunchInput } from '@/domain/models/testExecution'
import type { Device } from '@/domain/models/device'
import type { ApiConfig } from '@/domain/models/apiConfig'
import type { TestCase } from '@/domain/models/testCase'

function formatNow(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function useTestLaunch() {
  const navigate = useNavigate()

  /** 启动校验链（§3.7；返回错误文案数组，空=通过） */
  const validate = useCallback(
    (opts: {
      type: 'e2e' | 'api'
      cases: TestCase[]
      devices: Device[]
      apis: ApiConfig[]
      deviceIds: number[]
      apiIds: number[]
      algorithmType?: string
    }): string[] => {
      const errors: string[] = []
      const all = opts.cases
      if (all.length === 0) {
        errors.push('当前筛选条件下没有可用的测试用例，请选择用例或调整筛选条件')
      }
      if (opts.type === 'e2e') {
        const selected = opts.devices.filter((d) => opts.deviceIds.includes(d.id))
        if (selected.length === 0) {
          errors.push('请至少选择一台在线测试设备')
        } else {
          const offline = selected.filter((d) => d.status !== 'online').map((d) => d.name)
          if (offline.length) errors.push(`以下设备处于离线状态，无法执行测试：${offline.join('、')}`)
        }
      } else {
        const selected = opts.apis.filter((a) => opts.apiIds.includes(a.id))
        if (selected.length === 0) {
          errors.push('请至少选择一个在线 API')
        } else {
          const offline = selected.filter((a) => a.status !== 'online').map((a) => a.name)
          if (offline.length) errors.push(`以下 API 处于离线状态，无法执行测试：${offline.join('、')}`)
        }
      }
      return errors
    },
    []
  )

  /** 默认任务名称（现 handleStartTask 口径：E2E测试任务_{YYYY-MM-DD HH:mm}） */
  const defaultTaskName = useCallback((type: 'e2e' | 'api') => {
    return type === 'e2e'
      ? `E2E测试任务_${formatNow()}`
      : `API测试任务_${formatNow()}`
  }, [])

  /** 创建 + 启动 + 跳 step=3 */
  const launch = useCallback(
    async (name: string, opts: {
      type: 'e2e' | 'api'
      algorithmType?: string | null
      deviceIds: number[]
      apiIds: number[]
      deviceTypes?: string[]
      params: ExecutionParams
    }) => {
      const caseStore = useCaseSelectionStore.getState()
      const input: TaskLaunchInput = {
        name,
        testType: opts.type,
        algorithmType: opts.algorithmType ?? null,
        testCaseIds: caseStore.manualCaseIds,
        filterAllMode: caseStore.filterAllMode,
        deviceIds: opts.deviceIds,
        apiIds: opts.apiIds,
        params: opts.params,
      }
      try {
        const { id } = await createTask(input)
        await startTask(id)
        useExecutionStore.getState().setTask(id, name, opts.deviceTypes)
        navigateWithSearch(navigate, { step: 3 })
      } catch (error) {
        toast.error(`创建或启动测试任务失败：${error instanceof Error ? error.message : String(error)}`)
      }
    },
    [navigate]
  )

  /** 步骤三底部摘要（§5.1 任务名称弹窗执行摘要行） */
  const summary = useCallback(
    (opts: {
      type: 'e2e' | 'api'
      caseCount: number
      resourceCount: number
      concurrency: number
    }) => {
      return opts.type === 'e2e'
        ? `${opts.caseCount} 条 · ${opts.resourceCount} 台 · 并发 ${opts.concurrency}`
        : `${opts.caseCount} 条 · ${opts.resourceCount} 个 · 并发 ${opts.concurrency}`
    },
    []
  )

  const flowSummary = useMemo(() => {
    const caseStore = useCaseSelectionStore.getState()
    const resourceStore = useResourceSelectionStore.getState()
    const execStore = useExecutionStore.getState()
    return {
      caseCount: caseStore.manualCaseIds.length,
      deviceCount: resourceStore.deviceIds.length,
      apiCount: resourceStore.apiIds.length,
      concurrency: execStore.params.concurrency,
    }
  }, [])

  return { validate, defaultTaskName, launch, summary, flowSummary }
}
