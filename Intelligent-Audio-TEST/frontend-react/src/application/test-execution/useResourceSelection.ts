/**
 * 资源选择编排（application 层；10_测试执行.md §3.6）。
 * 设备/API 选择 + 算法过滤（设备 supportedAlgorithms / API algorithmType 前端过滤，
 * 现 useResourceSelection.ts:54-66/68-100 口径平移）+ 临时解除态（「查看全部」仅本页生效）。
 * 过滤空态兜底：空态文案「当前算法（{名}）下没有可用{设备|API}」+ 动作钮「更换算法」。
 */
import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'

import { fetchApis, fetchDevices } from '@/infrastructure/api/test-execution-api'
import { useResourceSelectionStore } from '@/infrastructure/stores/resource-selection-store'

export function useResourceSelection(type: 'e2e' | 'api', algorithmType?: string) {
  const deviceIds = useResourceSelectionStore((s) => s.deviceIds)
  const apiIds = useResourceSelectionStore((s) => s.apiIds)
  const temporaryShowAll = useResourceSelectionStore((s) => s.temporaryShowAll)
  const store = useResourceSelectionStore

  const devicesQuery = useQuery({
    queryKey: ['test-execution', 'devices'],
    queryFn: fetchDevices,
    enabled: type === 'e2e',
    staleTime: 30_000,
  })
  const apisQuery = useQuery({
    queryKey: ['test-execution', 'apis'],
    queryFn: fetchApis,
    enabled: type === 'api',
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
    isLoading: type === 'e2e' ? devicesQuery.isLoading : apisQuery.isLoading,
  }
}
