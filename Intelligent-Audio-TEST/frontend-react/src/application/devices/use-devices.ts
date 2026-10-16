/**
 * 设备管理页 query/mutation hooks（application 层；16_设备域.md §10 组件树落位）。
 * queryKey 前缀：['devices','test'] / ['devices','playback'] / ['devices','api'] /
 * ['devices','labs'] / ['devices','groups'] / ['devices','alarms'] / ['devices','alarm-rules'] /
 * ['devices','status-history']。增删改/确认后 invalidate 自动刷新列表与统计。
 * mock 阶段列表全量返回、前端过滤分页（接线后 URL 态化）。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type { TestDevice } from '@/domain/models/testDevice'
import type { PlaybackDevice } from '@/domain/models/playbackDevice'
import type { ApiDevice } from '@/domain/models/apiDevice'
import type { AlarmRule } from '@/domain/models/alarm'
import type { Laboratory } from '@/domain/models/laboratory'
import {
  acknowledgeAlarm,
  batchDeviceAction,
  controlDevice,
  createApiDevice,
  createLaboratory,
  createPlaybackDevice,
  createTestDevice,
  deleteAlarmRule,
  deleteApiDevice,
  deleteLaboratory,
  deletePlaybackDevice,
  deleteTestDevice,
  fetchAlarmRules,
  fetchAlarms,
  fetchApiDevices,
  fetchDeviceGroups,
  fetchLaboratories,
  fetchPlaybackDevices,
  fetchStatusHistory,
  fetchTestDevices,
  saveAlarmRule,
  scanDevices,
  updateApiDevice,
  updatePlaybackDevice,
  updateTestDevice,
} from '@/infrastructure/api/devicesApi'

/** 测试设备列表（§3.4；GET /test-devices） */
export function useTestDevices() {
  return useQuery({
    queryKey: ['devices', 'test'],
    queryFn: fetchTestDevices,
    staleTime: 30_000,
  })
}

/** 播放设备列表（§3.5；GET /playback-devices） */
export function usePlaybackDevices() {
  return useQuery({
    queryKey: ['devices', 'playback'],
    queryFn: fetchPlaybackDevices,
    staleTime: 30_000,
  })
}

/** 测试 API 列表（§3.6；GET /apis） */
export function useApiDevices() {
  return useQuery({
    queryKey: ['devices', 'api'],
    queryFn: fetchApiDevices,
    staleTime: 30_000,
  })
}

/** 实验室列表（§6.26；GET /laboratories——INT-487 后端待立项，mock 先行） */
export function useLaboratories() {
  return useQuery({
    queryKey: ['devices', 'labs'],
    queryFn: fetchLaboratories,
    staleTime: 60_000,
  })
}

/** 设备分组列表（§6.3；GET /device-groups） */
export function useDeviceGroups() {
  return useQuery({
    queryKey: ['devices', 'groups'],
    queryFn: fetchDeviceGroups,
    staleTime: 60_000,
  })
}

/** 告警列表 + 统计（§3.7；GET /alarms） */
export function useDeviceAlarms() {
  return useQuery({
    queryKey: ['devices', 'alarms'],
    queryFn: fetchAlarms,
    staleTime: 30_000,
  })
}

/** 告警规则列表（§6.6；GET /alarm-rules） */
export function useAlarmRules() {
  return useQuery({
    queryKey: ['devices', 'alarm-rules'],
    queryFn: fetchAlarmRules,
    staleTime: 60_000,
  })
}

/** 状态历史（§3.7；GET /status-history） */
export function useStatusHistory() {
  return useQuery({
    queryKey: ['devices', 'status-history'],
    queryFn: fetchStatusHistory,
    staleTime: 60_000,
  })
}

/** 设备增删改/控制/批量/扫描聚合（invalidate 联动） */
export function useDeviceMutations() {
  const queryClient = useQueryClient()

  const invalidate = (key: 'test' | 'playback' | 'api') => {
    void queryClient.invalidateQueries({ queryKey: ['devices', key] })
  }

  const invalidateAll = () => {
    void queryClient.invalidateQueries({ queryKey: ['devices'] })
  }

  const createTest = useMutation({
    mutationFn: (input: Omit<TestDevice, 'id' | 'createdAt' | 'updatedAt'>) => createTestDevice(input),
    onSuccess: () => invalidate('test'),
  })

  const updateTest = useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Partial<TestDevice> }) => updateTestDevice(id, patch),
    onSuccess: () => invalidate('test'),
  })

  const removeTest = useMutation({
    mutationFn: (id: number) => deleteTestDevice(id),
    onSuccess: () => invalidate('test'),
  })

  const createPlayback = useMutation({
    mutationFn: (input: Omit<PlaybackDevice, 'id' | 'createdAt' | 'updatedAt'>) => createPlaybackDevice(input),
    onSuccess: () => invalidate('playback'),
  })

  const updatePlayback = useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Partial<PlaybackDevice> }) => updatePlaybackDevice(id, patch),
    onSuccess: () => invalidate('playback'),
  })

  const removePlayback = useMutation({
    mutationFn: (id: number) => deletePlaybackDevice(id),
    onSuccess: () => invalidate('playback'),
  })

  const createApi = useMutation({
    mutationFn: (input: Omit<ApiDevice, 'id' | 'createdAt' | 'updatedAt'>) => createApiDevice(input),
    onSuccess: () => invalidate('api'),
  })

  const updateApi = useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Partial<ApiDevice> }) => updateApiDevice(id, patch),
    onSuccess: () => invalidate('api'),
  })

  const removeApi = useMutation({
    mutationFn: (id: number) => deleteApiDevice(id),
    onSuccess: () => invalidate('api'),
  })

  const control = useMutation({
    mutationFn: ({ id, action }: { id: number; action: string }) => controlDevice(id, action),
  })

  const batch = useMutation({
    mutationFn: ({ action, ids }: { action: string; ids: number[] }) => batchDeviceAction(action, ids),
    onSuccess: () => invalidateAll(),
  })

  const scan = useMutation({
    mutationFn: (kind: 'test' | 'playback') => scanDevices(kind),
  })

  return {
    createTest,
    updateTest,
    removeTest,
    createPlayback,
    updatePlayback,
    removePlayback,
    createApi,
    updateApi,
    removeApi,
    control,
    batch,
    scan,
    invalidateAll,
  }
}

/** 告警确认（§3.7） */
export function useAlarmMutations() {
  const queryClient = useQueryClient()

  const acknowledge = useMutation({
    mutationFn: (id: number) => acknowledgeAlarm(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['devices', 'alarms'] }),
  })

  return { acknowledge }
}

/** 告警规则 CRUD（§6.6） */
export function useAlarmRuleMutations() {
  const queryClient = useQueryClient()

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['devices', 'alarm-rules'] })

  const save = useMutation({
    mutationFn: (input: Omit<AlarmRule, 'id' | 'createdAt' | 'updatedAt'> & { id?: number }) => saveAlarmRule(input),
    onSuccess: invalidate,
  })

  const remove = useMutation({
    mutationFn: (id: number) => deleteAlarmRule(id),
    onSuccess: invalidate,
  })

  return { save, remove }
}

/** 实验室 CRUD（§6.26；INT-487 后端待立项，mock 先行） */
export function useLaboratoryMutations() {
  const queryClient = useQueryClient()

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['devices', 'labs'] })

  const create = useMutation({
    mutationFn: (
      input: Omit<Laboratory, 'id' | 'createdAt' | 'updatedAt' | 'deviceCount' | 'playbackDeviceCount' | 'testCaseCount'>
    ) => createLaboratory(input),
    onSuccess: invalidate,
  })

  const remove = useMutation({
    mutationFn: (id: number) => deleteLaboratory(id),
    onSuccess: invalidate,
  })

  return { create, remove }
}
