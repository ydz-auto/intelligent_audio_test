/**
 * 执行示意图渲染数据（application 层；10_测试_execution.md §3.6.4，INT-1119 2026-10-21）。
 * 从 selectionOrder × targetModes 派生 parallelTargets/serialTargets 分组 + 阶段箭头条件；
 * 增删卡、切换模式、清空选择即时重绘（受控源唯一：useTargetModes，与卡片/载荷三处一致）。
 * 阶段箭头：并行组与串行链并存、且第一个串行目标前存在并行目标时（并行完成后串行依次启动）。
 */
import { useMemo } from 'react'

import { useTargetModes } from '@/application/test-execution/useTargetModes'
import type { Device, DeviceType } from '@/domain/models/device'
import type { ApiConfig } from '@/domain/models/apiConfig'
import type { ExecutionMode, TargetType } from '@/domain/models/testExecution'

/** 示意图目标节点（名称/图标类型已解析，Presentation 直接渲染） */
export interface DiagramTarget {
  targetType: TargetType
  targetId: number
  name: string
  mode: ExecutionMode
  /** 节点图标类型（physical/http_api/websocket_api=设备类型；api=API 目标） */
  iconKind: DeviceType | 'api'
}

export function useExecutionDiagram(devices: Device[], apis: ApiConfig[]) {
  const { payload } = useTargetModes()

  const deviceNameById = useMemo(() => {
    const map = new Map<number, string>()
    devices.forEach((d) => map.set(d.id, d.name))
    return map
  }, [devices])
  const deviceTypeById = useMemo(() => {
    const map = new Map<number, DeviceType | null>()
    devices.forEach((d) => map.set(d.id, d.type))
    return map
  }, [devices])
  const apiNameById = useMemo(() => {
    const map = new Map<number, string>()
    apis.forEach((a) => map.set(a.id, a.name))
    return map
  }, [apis])

  const targets = useMemo<DiagramTarget[]>(
    () =>
      payload.map(({ targetType, targetId, mode }) =>
        targetType === 'device'
          ? {
              targetType,
              targetId,
              name: deviceNameById.get(targetId) ?? `设备 ${targetId}`,
              mode,
              iconKind: deviceTypeById.get(targetId) ?? 'physical',
            }
          : {
              targetType,
              targetId,
              name: apiNameById.get(targetId) ?? `API ${targetId}`,
              mode,
              iconKind: 'api',
            }
      ),
    [payload, deviceNameById, deviceTypeById, apiNameById]
  )

  /** 并行目标（同阶段并发，保持选择顺序） */
  const parallelTargets = useMemo(() => targets.filter((t) => t.mode === 'parallel'), [targets])

  /** 串行目标（保持选择顺序 = 串行链顺序） */
  const serialTargets = useMemo(() => targets.filter((t) => t.mode === 'serial'), [targets])

  /** 阶段箭头：第一个串行目标前存在并行目标（并行完成后串行依次启动） */
  const firstSerialIndex = useMemo(
    () => targets.findIndex((t) => t.mode === 'serial'),
    [targets]
  )
  const hasStageArrow = firstSerialIndex > 0

  return {
    targets,
    parallelTargets,
    serialTargets,
    hasStageArrow,
    isEmpty: targets.length === 0,
  }
}
