/**
 * 资源选择编排（application 层；10_测试执行.md §3.6；INT-486 2026-10-16 追加口径：
 * 开始测试不再分 E2E/API——设备与 API 同屏同选，本 hook 同时加载设备与 API 两列表）。
 * 算法过滤（设备 supportedAlgorithms / API algorithmType 前端过滤，
 * 现 useResourceSelection.ts:54-66/68-100 口径平移）+ 临时解除态（「查看全部」仅本页生效）。
 * 过滤空态兜底：空态文案「当前算法（{名}）下没有可用资源」+ 动作钮「更换算法」。
 * INT-2074：mergeScannedDevices —— 开始测试页「扫描设备」勾选结果合并进资源选择：
 * 未注册测试设备经真实 POST /test-devices 登记、未注册播放通道经 POST /playback-devices
 * 登记（按 device_unique_id 去重），刷新设备网格后勾选新设备 id（在线态、可直接进入下一步）。
 */
import { useCallback, useMemo } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { fetchApis, fetchDevices } from '@/infrastructure/api/test-execution-api'
import {
  createPlaybackDevice,
  createTestDevice,
  fetchPlaybackDevices,
} from '@/infrastructure/api/devicesApi'
import { useResourceSelectionStore } from '@/infrastructure/stores/resource-selection-store'
import { normalizeDeviceSystem } from '@/features/devices/lib/device-system'
import type { DeviceScanRow, DeviceScanSelection } from '@/domain/models/deviceScan'
import { resolveScanConnectionType } from '@/domain/models/deviceScan'
import type { PlaybackDevice } from '@/domain/models/playbackDevice'
import type { TestDevice } from '@/domain/models/testDevice'

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

/** 扫描测试设备行 → 登记入参（INT-2074；照 §6.1 handleAdd 预填口径 + 在线态 + 当前算法） */
function toScannedTestDeviceInput(
  row: DeviceScanRow,
  algorithmType?: string
): Partial<TestDevice> {
  return {
    name: row.name ?? row.serial ?? '未知设备',
    model: row.model ?? '',
    type: 'physical',
    system: normalizeDeviceSystem(row.system)?.label ?? 'Android',
    systemVersion: row.system_version ?? '未知',
    appName: row.app_name ?? 'Default App',
    appVersion: row.app_version ?? '1.0.0',
    ip: row.ip ?? undefined,
    connectionType: resolveScanConnectionType(row).value,
    serialNumber: row.serial ?? undefined,
    status: 'online',
    // 与步骤二算法过滤同源：仅在当前算法生效时登记进该算法（避免被前端过滤隐藏）
    supportedAlgorithms: algorithmType ? [algorithmType] : undefined,
  }
}

/** 扫描播放通道行 → 登记入参（照 §6.1 handleAdd 预填口径 + 在线态） */
function toScannedPlaybackDeviceInput(row: DeviceScanRow): Partial<PlaybackDevice> {
  return {
    name: row.name ?? row.device_unique_id ?? '未知通道',
    model: row.model ?? '',
    deviceType: (row.type as PlaybackDevice['deviceType']) ?? 'dry',
    sampleRate: row.sample_rate ?? 48000,
    channelIndex: row.channel_index ?? 0,
    deviceUniqueId: row.device_unique_id ?? '',
    status: 'online',
  }
}

export function useResourceSelection(algorithmType?: string) {
  const queryClient = useQueryClient()
  const deviceIds = useResourceSelectionStore((s) => s.deviceIds)
  const apiIds = useResourceSelectionStore((s) => s.apiIds)
  const temporaryShowAll = useResourceSelectionStore((s) => s.temporaryShowAll)
  const store = useResourceSelectionStore

  const devicesQuery = useQuery({
    queryKey: ['test-execution', 'devices'],
    queryFn: fetchDevices,
    staleTime: 30_000,
  })
  const apisQuery = useQuery({
    queryKey: ['test-execution', 'apis'],
    queryFn: fetchApis,
    staleTime: 30_000,
  })

  /** 算法过滤（设备按 supportedAlgorithms / API 按 algorithmType；解除态显示全部） */
  const filteredDevices = useMemo(() => {
    const all = devicesQuery.data ?? []
    if (temporaryShowAll || !algorithmType) return all
    return all.filter(
      (d) => d.supportedAlgorithms == null || d.supportedAlgorithms.includes(algorithmType)
    )
  }, [devicesQuery.data, algorithmType, temporaryShowAll])

  const filteredApis = useMemo(() => {
    const all = apisQuery.data ?? []
    if (temporaryShowAll || !algorithmType) return all
    return all.filter((a) => a.algorithmType == null || a.algorithmType === algorithmType)
  }, [apisQuery.data, algorithmType, temporaryShowAll])

  const isTemporary = temporaryShowAll && Boolean(algorithmType)

  /**
   * INT-2074：扫描结果合并进资源选择。
   * ① 测试设备：已注册（数字 id）直接勾选；未注册真实登记（POST /test-devices → data.id）；
   * ② 播放通道：按 device_unique_id 与现有播放设备列表去重后真实登记（不进步骤二网格，
   *    供设备管理页播放列表选用）；③ 刷新设备网格后勾选新设备 id（在线态可进入下一步）。
   * 返回实际登记/勾选的测试设备数与播放通道数（播放通道失败/去重跳过不阻断测试设备流程）。
   */
  const mergeScannedDevices = useCallback(
    async (selection: DeviceScanSelection): Promise<{ test: number; playback: number }> => {
      // 现有设备列表：未注册判定兜底查重（后端 is_registered 按「名称」匹配不可靠——
      // _device_repository_impl.get_all_device_serials 返回 name 列表，serial/model 精确匹配常落空，
      // 同 serial 重扫会重复登记，前端按 serial/name 查重复用）
      const existingDevices = await queryClient.fetchQuery({
        queryKey: ['test-execution', 'devices'],
        queryFn: fetchDevices,
        staleTime: 30_000,
      })
      const newTestIds: number[] = []
      let addedTest = 0

      for (const row of selection.test) {
        const registeredId = row.is_registered && typeof row.id === 'number' ? row.id : null
        if (registeredId != null) {
          newTestIds.push(registeredId)
          addedTest += 1
          continue
        }
        // 同 serial / 同名已存在 → 复用现有设备（不重复登记）
        const existing = existingDevices.find(
          (d) =>
            (row.serial != null && d.serialNumber === row.serial) ||
            (row.name != null && d.name === row.name)
        )
        if (existing) {
          newTestIds.push(existing.id)
          addedTest += 1
          continue
        }
        try {
          const created = await createTestDevice(toScannedTestDeviceInput(row, algorithmType))
          if (created.id != null) {
            newTestIds.push(created.id)
            addedTest += 1
          }
        } catch (error) {
          toast.error(`测试设备「${row.name ?? row.serial ?? ''}」登记失败：${errorText(error)}`)
        }
      }

      let addedPlayback = 0
      if (selection.playback.length > 0) {
        try {
          const existing = await queryClient.fetchQuery({
            queryKey: ['devices', 'playback'],
            queryFn: fetchPlaybackDevices,
            staleTime: 30_000,
          })
          const existingIds = new Set(
            existing.map((d) => d.deviceUniqueId).filter((id): id is string => Boolean(id))
          )
          for (const row of selection.playback) {
            const uniqueId = row.device_unique_id
            if (uniqueId && existingIds.has(uniqueId)) continue
            try {
              const created = await createPlaybackDevice(toScannedPlaybackDeviceInput(row))
              if (created.id != null) {
                addedPlayback += 1
                if (uniqueId) existingIds.add(uniqueId)
              }
            } catch (error) {
              toast.error(`播放通道「${row.name ?? ''}」登记失败：${errorText(error)}`)
            }
          }
          void queryClient.invalidateQueries({ queryKey: ['devices', 'playback'] })
        } catch (error) {
          toast.error(`播放通道列表加载失败，未登记新通道：${errorText(error)}`)
        }
      }

      // 刷新设备网格（含新登记设备）后勾选新设备 id
      if (newTestIds.length > 0) {
        await queryClient.refetchQueries({ queryKey: ['test-execution', 'devices'], type: 'active' })
        const current = useResourceSelectionStore.getState()
        current.selectAllDevices([...new Set([...current.deviceIds, ...newTestIds])])
      }

      return { test: addedTest, playback: addedPlayback }
    },
    [algorithmType, queryClient]
  )

  return {
    devices: filteredDevices,
    apis: filteredApis,
    allDevices: devicesQuery.data ?? [],
    allApis: apisQuery.data ?? [],
    deviceIds,
    apiIds,
    toggleDevice: (id: number) => store.getState().toggleDevice(id),
    toggleApi: (id: number) => store.getState().toggleApi(id),
    selectAllDevices: (ids: number[]) => store.getState().selectAllDevices(ids),
    selectAllApis: (ids: number[]) => store.getState().selectAllApis(ids),
    removeDevice: (id: number) => store.getState().removeDevice(id),
    removeApi: (id: number) => store.getState().removeApi(id),
    clearResources: () => store.getState().clearResources(),
    setTemporaryShowAll: (value: boolean) => store.getState().setTemporaryShowAll(value),
    isTemporary,
    isLoading: devicesQuery.isLoading || apisQuery.isLoading,
    mergeScannedDevices,
  }
}
