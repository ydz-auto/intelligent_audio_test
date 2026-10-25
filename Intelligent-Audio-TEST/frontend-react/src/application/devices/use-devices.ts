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
import type { DeviceGroup } from '@/domain/models/deviceGroup'
import {
  acknowledgeAlarm,
  addDevicesToGroup,
  associatePlaybackSpl,
  batchDeviceAction,
  controlDevice,
  createApiDevice,
  createDeviceGroup,
  createLaboratory,
  createPlaybackDevice,
  createTestDevice,
  deleteAlarmRule,
  deleteApiDevice,
  deleteDeviceGroup,
  deleteLaboratory,
  deletePlaybackDevice,
  deleteTestDevice,
  fetchAlarmRules,
  fetchAlarms,
  fetchApiDevices,
  fetchDeviceGroupDetail,
  fetchDeviceGroups,
  fetchDriverKeywords,
  fetchLaboratories,
  fetchPlaybackDevices,
  fetchStatusHistory,
  fetchTestDevices,
  moveDeviceGroup,
  removeDevicesFromGroup,
  saveAlarmRule,
  scanDevices,
  setDeviceOccupied,
  updateApiDevice,
  updateDeviceGroup,
  updateLaboratory,
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

/** 实验室列表（§6.26；GET /laboratories——INT-655 真实端点） */
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

/** 设备分组详情（§6.3；GET /device-groups/{id}——列表 device_ids 恒空，展开/筛选时按需拉取真实成员，P2-1） */
export function useDeviceGroupDetailQuery(groupId: string | null) {
  return useQuery({
    queryKey: ['devices', 'groups', groupId],
    queryFn: () => fetchDeviceGroupDetail(groupId as string),
    enabled: groupId != null,
    staleTime: 30_000,
  })
}

/** 驱动关键字（§6.2/V9.7.10 loadDriverKeywords；GET /test-devices/driver-keywords） */
export function useDriverKeywords() {
  return useQuery({
    queryKey: ['devices', 'driver-keywords'],
    queryFn: fetchDriverKeywords,
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
    mutationFn: ({
      id,
      action,
      params,
    }: {
      id: number
      action: string
      /** P2-2：操作参数（install_app: file_path/package_name；uninstall_app: package_name） */
      params?: Record<string, unknown>
    }) => controlDevice(id, action, params),
  })

  /** 「测试中」占用态本地瞬时态兜底（INT-487：置/清 occupied + 列表失效刷新）
   *  P3-b：请求失败时 infrastructure 已回滚覆盖，这里再失效一次，把请求期间可能已取到覆盖值的列表拉回真实态 */
  const setOccupied = useMutation({
    mutationFn: ({
      kind,
      id,
      occupied,
    }: {
      kind: 'test' | 'playback' | 'api'
      id: number
      occupied: boolean
    }) => setDeviceOccupied(kind, id, occupied),
    onSuccess: () => invalidateAll(),
    onError: () => invalidateAll(),
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
    setOccupied,
    batch,
    scan,
    invalidateAll,
  }
}

/** 设备分组 CRUD（§6.3；INT-721 接线 device_bp /test-devices/device-groups 真实端点） */
export function useDeviceGroupMutations() {
  const queryClient = useQueryClient()

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['devices', 'groups'] })

  const create = useMutation({
    mutationFn: (input: { name: string; description?: string | null; groupType?: DeviceGroup['groupType']; deviceIds?: number[] }) =>
      createDeviceGroup(input),
    onSuccess: invalidate,
  })

  const update = useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: { name?: string; description?: string | null; groupType?: DeviceGroup['groupType'] } }) =>
      updateDeviceGroup(id, patch),
    onSuccess: invalidate,
  })

  /** 移动分组到新父级/根（INT-864；成功刷新分组树） */
  const move = useMutation({
    mutationFn: ({ id, parentId }: { id: string; parentId: string | null }) =>
      moveDeviceGroup(id, parentId),
    onSuccess: invalidate,
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteDeviceGroup(id, true),
    onSuccess: invalidate,
  })

  const addMembers = useMutation({
    mutationFn: ({ id, deviceIds }: { id: string; deviceIds: number[] }) => addDevicesToGroup(id, deviceIds),
    onSuccess: invalidate,
  })

  const removeMembers = useMutation({
    mutationFn: ({ id, deviceIds }: { id: string; deviceIds: number[] }) => removeDevicesFromGroup(id, deviceIds),
    onSuccess: invalidate,
  })

  return { create, update, move, remove, addMembers, removeMembers }
}

/** 关联声压映射（§6.4；POST /playback-devices/{id}/associate-spl） */
export function useAssociateSplMutation() {
  const queryClient = useQueryClient()
  const associate = useMutation({
    mutationFn: ({ deviceId, splMappingId }: { deviceId: number; splMappingId: number }) =>
      associatePlaybackSpl(deviceId, splMappingId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['devices', 'playback'] }),
  })
  return { associate }
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

/** 实验室 CRUD（§6.26；INT-655 /laboratories 真实端点，成功失效列表重拉） */
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

  const update = useMutation({
    mutationFn: ({
      id,
      patch,
    }: {
      id: number
      patch: Partial<
        Omit<Laboratory, 'id' | 'createdAt' | 'updatedAt' | 'deviceCount' | 'playbackDeviceCount' | 'testCaseCount'>
      >
    }) => updateLaboratory(id, patch),
    onSuccess: invalidate,
  })

  return { create, remove, update }
}
