/**
 * 执行示意图渲染数据（application 层；10_测试_execution.md §3.6.4，INT-1119 2026-10-21）。
 * 从 selectionOrder × targetModes 派生**双道**（设备道 / API 道）并行/串行分组 + 道内阶段箭头；
 * 增删卡、切换模式、清空选择即时重绘（受控源唯一：useTargetModes，与卡片/载荷三处一致）。
 * 双道语义（2026-10-21 负责人口径修正）：设备与 API 两条独立执行道互不等待、始终并发；
 * 串行目标仅等**同类道内**前序（含同类型并行目标）；道内阶段箭头 = 该道第一个串行目标前
 * 存在并行目标（该道并行完成后串行依次启动）。道间不画阶段箭头。
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

/** 单条执行道（设备道 / API 道）：道内并行组 + 串行链 + 道内阶段箭头 */
export interface ExecutionLane {
  targetType: TargetType
  parallelTargets: DiagramTarget[]
  serialTargets: DiagramTarget[]
  /** 阶段箭头：该道内第一个串行目标前存在并行目标（该道并行完成后串行依次启动） */
  hasStageArrow: boolean
}

/**
 * 按道派生并行组 / 串行链 + 道内阶段箭头（道内顺序 = 选择顺序 = 串行链顺序）。
 * 阶段箭头仅按**道内**位置判定——道外（另一类型）并行目标不触发箭头，体现设备/API 互不等待。
 */
function buildLane(targetType: TargetType, laneTargets: DiagramTarget[]): ExecutionLane {
  return {
    targetType,
    parallelTargets: laneTargets.filter((t) => t.mode === 'parallel'),
    serialTargets: laneTargets.filter((t) => t.mode === 'serial'),
    hasStageArrow: laneTargets.findIndex((t) => t.mode === 'serial') > 0,
  }
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

  /** 双道：设备道 / API 道各自独立（互不等待；空道折叠，不出现在 lanes 中） */
  const deviceLane = useMemo(
    () => buildLane('device', targets.filter((t) => t.targetType === 'device')),
    [targets]
  )
  const apiLane = useMemo(
    () => buildLane('api', targets.filter((t) => t.targetType === 'api')),
    [targets]
  )

  const lanes = useMemo<ExecutionLane[]>(
    () =>
      [deviceLane, apiLane].filter(
        (lane) => lane.parallelTargets.length + lane.serialTargets.length > 0
      ),
    [deviceLane, apiLane]
  )

  return {
    lanes,
    isEmpty: targets.length === 0,
  }
}
