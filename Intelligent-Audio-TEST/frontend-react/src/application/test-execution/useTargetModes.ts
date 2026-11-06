/**
 * 逐目标执行模式派生（application 层；10_测试执行.md §3.6.5，INT-1119 2026-10-21）。
 * 从 selectionOrder × targetModes 派生 target_modes 载荷与卡片受控值——**唯一受控源**：
 * 卡片 SegmentedControl / 底部示意图 / 请求载荷三处由它驱动，天然一致，无事件竞态。
 * 缺省（未记录模式项）视为并行；取消选择由 resource store 同步删项。
 */
import { useCallback, useMemo } from 'react'

import type { ExecutionMode, TargetMode, TargetType } from '@/domain/models/testExecution'
import { useExecutionStore } from '@/infrastructure/stores/execution-store'
import { useResourceSelectionStore } from '@/infrastructure/stores/resource-selection-store'
import type { SelectionEntry } from '@/infrastructure/stores/resource-selection-store'

/** 派生 target_modes 载荷（纯函数；launch 侧与 UI 同源调用） */
export function deriveTargetModes(
  selectionOrder: SelectionEntry[],
  targetModes: Record<string, ExecutionMode>
): TargetMode[] {
  return selectionOrder.map(({ targetType, targetId }) => ({
    targetType,
    targetId,
    mode: targetModes[`${targetType}:${targetId}`] ?? 'parallel',
  }))
}

export function useTargetModes() {
  const selectionOrder = useResourceSelectionStore((s) => s.selectionOrder)
  const targetModes = useExecutionStore((s) => s.targetModes)
  const setTargetMode = useExecutionStore((s) => s.setTargetMode)

  /** 某目标当前模式（缺省=并行；唯一受控源，卡片受控值同源） */
  const getMode = useCallback(
    (targetType: TargetType, targetId: number): ExecutionMode =>
      targetModes[`${targetType}:${targetId}`] ?? 'parallel',
    [targetModes]
  )

  /** 某目标切换模式（即时写 execution store，示意图/载荷同步刷新） */
  const setMode = useCallback(
    (targetType: TargetType, targetId: number, mode: ExecutionMode) => {
      setTargetMode(targetType, targetId, mode)
    },
    [setTargetMode]
  )

  /** target_modes 载荷（保选中顺序；恰好覆盖全部选中目标一次） */
  const payload = useMemo(
    () => deriveTargetModes(selectionOrder, targetModes),
    [selectionOrder, targetModes]
  )

  /** 串行目标数（§5.1 任务名称弹窗摘要「串行 {s} 个目标」） */
  const serialCount = useMemo(
    () => payload.filter((item) => item.mode === 'serial').length,
    [payload]
  )

  return { payload, serialCount, getMode, setMode }
}
