/**
 * 执行流程 store（infrastructure/stores 层；10_测试执行.md §4）。
 * 执行参数 + 进行中任务 id + 报告装配态；内存态（刷新丢，任务在任务管理可续看）。
 */
import { create } from 'zustand'

import type { ExecutionParams } from '@/domain/models/testExecution'
import { DEFAULT_EXECUTION_PARAMS } from '@/domain/models/testExecution'

type ExecutionState = {
  params: ExecutionParams
  /** 进行中任务 id（启动成功写入；URL step=3 依赖） */
  taskId: number | null
  taskName: string | null
  /** 任务 device_types（启动时落定；执行装配 hasRealtimeDevice/isApi 依据） */
  deviceTypes: string[]
  /** 报告装配态（终态自动触发 generate；report:create） */
  reportId: number | null
  reportStatus: 'idle' | 'generating' | 'ready' | 'failed'
  reportError: string | null
  setParams: (patch: Partial<ExecutionParams>) => void
  resetParams: () => void
  setTask: (taskId: number, taskName: string, deviceTypes?: string[]) => void
  setReportGenerating: () => void
  setReportReady: (reportId: number) => void
  setReportFailed: (message: string) => void
  resetReport: () => void
  resetFlow: () => void
}

export const useExecutionStore = create<ExecutionState>((set) => ({
  params: { ...DEFAULT_EXECUTION_PARAMS },
  taskId: null,
  taskName: null,
  deviceTypes: [],
  reportId: null,
  reportStatus: 'idle',
  reportError: null,

  setParams: (patch) => set((s) => ({ params: { ...s.params, ...patch } })),

  resetParams: () => set({ params: { ...DEFAULT_EXECUTION_PARAMS } }),

  setTask: (taskId, taskName, deviceTypes = []) =>
    set({ taskId, taskName, deviceTypes }),

  setReportGenerating: () =>
    set({ reportStatus: 'generating', reportId: null, reportError: null }),

  setReportReady: (reportId) => set({ reportStatus: 'ready', reportId }),

  setReportFailed: (message) => set({ reportStatus: 'failed', reportError: message }),

  resetReport: () => set({ reportId: null, reportStatus: 'idle', reportError: null }),

  resetFlow: () =>
    set({
      params: { ...DEFAULT_EXECUTION_PARAMS },
      taskId: null,
      taskName: null,
      deviceTypes: [],
      reportId: null,
      reportStatus: 'idle',
      reportError: null,
    }),
}))
