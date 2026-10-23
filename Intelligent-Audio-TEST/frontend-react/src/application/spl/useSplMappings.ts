/**
 * 物理域 SPL 映射 query hooks（application 层；16_设备域.md §10 组件树落位）。
 * queryKey 前缀 ['spl'] / ['spl-stats'] / ['playback-device-refs'] / ['spl-history']；
 * 增删改/校准后 invalidate 自动刷新列表与统计。
 * 列表由 GET /spl 全量返回、前端过滤分页（URL 态化待后续卡）。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type {
  PlaybackDeviceRef,
  SplHistoryItem,
  SplMapping,
  SplStats,
  SplTestToneInput,
} from '@/domain/models/splMapping'
import {
  calibrateSplMapping,
  createSplMapping,
  deleteSplMapping,
  fetchPlaybackDeviceRefs,
  fetchPlaybackDeviceUniqueId,
  fetchSplHistory,
  fetchSplMappings,
  fetchSplMappingsByDevice,
  fetchSplStats,
  playSplTestTone,
  stopSplTestTone,
  updateSplMapping,
} from '@/infrastructure/api/spl-api'

/** 物理域映射列表（§4.2；GET /spl；enabled=false 时不下发请求，INT-1215 权限守卫后置防御） */
export function useSplMappings(enabled: boolean = true) {
  return useQuery({
    queryKey: ['spl'],
    queryFn: fetchSplMappings,
    staleTime: 30_000,
    enabled,
  })
}

/** 某播放设备的声压映射（§6.4 关联弹窗/播放表单编辑；GET /spl/by-device/{id}，V9.7.10 loadSplMappings 同源） */
export function useSplMappingsByDevice(deviceId: number | null) {
  return useQuery({
    queryKey: ['spl-by-device', deviceId],
    queryFn: () => fetchSplMappingsByDevice(deviceId as number),
    enabled: deviceId != null,
    staleTime: 30_000,
  })
}

/** 物理域统计（§4.1.2；GET /spl/stats；enabled=false 时不下发请求，INT-1215 权限守卫后置防御） */
export function useSplStats(enabled: boolean = true) {
  return useQuery({
    queryKey: ['spl-stats'],
    queryFn: fetchSplStats,
    staleTime: 30_000,
    enabled,
  })
}

/** 关联播放设备 facet 选项（§4.1.1；GET /playback-devices；enabled=false 时不下发请求，INT-1215 权限守卫后置防御） */
export function usePlaybackDeviceRefs(enabled: boolean = true) {
  return useQuery({
    queryKey: ['playback-device-refs'],
    queryFn: fetchPlaybackDeviceRefs,
    staleTime: 5 * 60_000,
    enabled,
  })
}

/** 校准历史（§6.9；GET /spl/{id}/history） */
export function useSplHistory(id: number | null) {
  return useQuery({
    queryKey: ['spl-history', id],
    queryFn: () => fetchSplHistory(id as number),
    enabled: id != null,
    staleTime: 30_000,
  })
}

/** 物理域增删改/校准（聚合 CRUD + invalidate） */
export function useSplMutations() {
  const queryClient = useQueryClient()

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['spl'] })
    void queryClient.invalidateQueries({ queryKey: ['spl-stats'] })
  }

  const create = useMutation({
    mutationFn: (
      input: Omit<SplMapping, 'id' | 'createdAt' | 'updatedAt' | 'deviceName' | 'deviceModel'>
    ) => createSplMapping(input),
    onSuccess: invalidate,
  })

  const update = useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Partial<SplMapping> }) =>
      updateSplMapping(id, patch),
    onSuccess: invalidate,
  })

  const remove = useMutation({
    mutationFn: (id: number) => deleteSplMapping(id),
    onSuccess: invalidate,
  })

  const calibrate = useMutation({
    mutationFn: ({ id }: { id: number }) => calibrateSplMapping(id),
    onSuccess: invalidate,
  })

  return { create, update, remove, calibrate, invalidate }
}

/** SPL 测试音播放/停止（§6.5；POST /spl/test-tone、POST /spl/test-tone/stop，真实后端扬声器） */
export function useSplTestTone() {
  const play = useMutation({
    mutationFn: (input: SplTestToneInput) => playSplTestTone(input),
  })

  const stop = useMutation({
    mutationFn: (uniqueId: string | null) => stopSplTestTone(uniqueId),
  })

  return { play, stop }
}

/** 关闭弹窗/卸载时兜底停止测试音（失败静默，不打扰用户；V9.7.10 onUnmounted splApi.stopTestTone 同源） */
export async function stopSplTestToneQuietly(uniqueId: string | null): Promise<void> {
  try {
    await stopSplTestTone(uniqueId)
  } catch {
    // 关闭路径停止失败不阻断（扬声器侧无播放时后端亦返回成功）
  }
}

/** 播放前解析播放设备系统唯一标识（§6.5；GET /playback-devices/{id} → device_unique_id） */
export function resolvePlaybackDeviceUniqueId(deviceId: number): Promise<string | null> {
  return fetchPlaybackDeviceUniqueId(deviceId)
}

export type { PlaybackDeviceRef, SplHistoryItem, SplStats }
