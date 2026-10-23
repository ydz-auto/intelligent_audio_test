/**
 * 测试启动编排（application 层；10_测试执行.md §3.7 启动校验链；INT-486 2026-10-16
 * 追加口径：开始测试不再分 E2E/API——校验设备/API 任一在线即可启动，混合执行）。
 * 校验（全部 toast.warning，照 setup-wizard toast.error 模式）→ 任务名称默认值 →
 * POST /tasks（task:create）+ POST /tasks/{id}/start（task:execute）→ 成功跳 step=3；
 * 失败 toast.error「创建或启动测试任务失败：{message}」。
 * INT-1119（2026-10-21）：载荷附逐目标 target_modes（selectionOrder × targetModes 同源派生，
 * §3.6.5），不再携带全局 execution_mode/serial_first。
 */
import { useNavigate } from '@tanstack/react-router'
import { useCallback, useMemo } from 'react'
import { toast } from 'sonner'

import { createTask, startTask } from '@/infrastructure/api/test-execution-api'
import { useExecutionStore } from '@/infrastructure/stores/execution-store'
import { useCaseSelectionStore } from '@/infrastructure/stores/case-selection-store'
import { useResourceSelectionStore } from '@/infrastructure/stores/resource-selection-store'
import { deriveTargetModes } from '@/application/test-execution/useTargetModes'
import { navigateWithSearch } from '@/features/test-execution/lib/navigate-search'
import { deriveApiTargetDeviceType } from '@/domain/models/apiConfig'
import type {
  ExecutionParams,
  TargetDeviceAssignment,
  TaskLaunchInput,
} from '@/domain/models/testExecution'
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
      const selectedDevices = opts.devices.filter((d) => opts.deviceIds.includes(d.id))
      const selectedApis = opts.apis.filter((a) => opts.apiIds.includes(a.id))
      if (selectedDevices.length === 0 && selectedApis.length === 0) {
        errors.push('请至少选择一台在线设备或一个在线 API')
      } else {
        const offlineDevices = selectedDevices
          .filter((d) => d.status !== 'online')
          .map((d) => d.name)
        if (offlineDevices.length) {
          errors.push(`以下设备处于离线状态，无法执行测试：${offlineDevices.join('、')}`)
        }
        const offlineApis = selectedApis
          .filter((a) => a.status !== 'online')
          .map((a) => a.name)
        if (offlineApis.length) {
          errors.push(`以下 API 处于离线状态，无法执行测试：${offlineApis.join('、')}`)
        }
      }
      return errors
    },
    []
  )

  /** 默认任务名称（2026-10-16 口径：不再分 E2E/API 模式） */
  const defaultTaskName = useCallback(() => {
    return `测试任务_${formatNow()}`
  }, [])

  /** 创建 + 启动 + 跳 step=3 */
  const launch = useCallback(
    async (name: string, opts: {
      algorithmType?: string | null
      deviceIds: number[]
      apiIds: number[]
      deviceTypes?: string[]
      /** 被测 API 全量配置（INT-1433：组装 case_devices 时取 deviceType / 按端点协议派生） */
      apis: ApiConfig[]
      params: ExecutionParams
    }) => {
      const caseStore = useCaseSelectionStore.getState()
      const resourceStore = useResourceSelectionStore.getState()
      const execStore = useExecutionStore.getState()
      // INT-1119：逐目标模式载荷与 UI 同源（selectionOrder × targetModes 派生），
      // 保选中顺序、恰好覆盖全部选中目标一次（缺省=并行）
      const targetModes = deriveTargetModes(resourceStore.selectionOrder, execStore.targetModes)
      // INT-1433：逐目标设备类型分配（device_type 三值）——按选中顺序取每个目标：
      // 物理设备 → physical；API → 显式 deviceType 或按端点协议派生（websocket_api Realtime
      // 路由前置）。createTask 按解析后的用例集展开为 case_devices，后端按
      // (case_id, device_type, device_id) 落多条 TaskCase——同一用例在多个目标间执行。
      const targetDeviceAssignments: TargetDeviceAssignment[] = resourceStore.selectionOrder
        .map(({ targetType, targetId }): TargetDeviceAssignment | null => {
          if (targetType === 'device') {
            return { deviceType: 'physical', deviceId: String(targetId) }
          }
          const api = opts.apis.find((a) => a.id === targetId)
          if (!api) return null
          return { deviceType: deriveApiTargetDeviceType(api), deviceId: String(targetId) }
        })
        .filter((x): x is TargetDeviceAssignment => x !== null)
      const input: TaskLaunchInput = {
        name,
        // 用例不分类型（test_type 残留列待 INT-79 废弃），任务不再声明测试类型
        testType: null,
        algorithmType: opts.algorithmType ?? null,
        testCaseIds: caseStore.manualCaseIds,
        filterAllMode: caseStore.filterAllMode,
        // INT-646 代码审计 P2：filter-all 圈定按当前筛选条件（case-selection store
        // 由 StepCases 持续同步），非仅算法维度
        caseFilter: caseStore.filter,
        deviceIds: opts.deviceIds,
        apiIds: opts.apiIds,
        targetModes,
        targetDeviceAssignments,
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

  /** 步骤三底部摘要（§5.1 任务名称弹窗执行摘要行；存在串行目标时附「· 串行 {s} 个目标」） */
  const summary = useCallback(
    (opts: {
      caseCount: number
      deviceCount: number
      apiCount: number
      concurrency: number
      serialCount?: number
    }) => {
      const base = `${opts.caseCount} 条 · ${opts.deviceCount} 台 · ${opts.apiCount} 个 · 并发 ${opts.concurrency}`
      return opts.serialCount != null && opts.serialCount > 0
        ? `${base} · 串行 ${opts.serialCount} 个目标`
        : base
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
