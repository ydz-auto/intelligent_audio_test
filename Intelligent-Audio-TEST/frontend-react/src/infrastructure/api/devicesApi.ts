/**
 * 设备管理页 API 桩（infrastructure 层；16_设备域.md §10 组件树落位）。
 * 红线④：全部返回 mock 常量（devices-mock），接线时替换为真实请求：
 *   GET /api/v1/test-devices        列表（keyword/status/lab_id/group_id/page/per_page）
 *   GET /api/v1/playback-devices    列表（keyword/device_type/lab_id/page/per_page）
 *   GET /api/v1/apis                列表（§3.6；后端 GET 无权限门槛见 §11-10）
 *   GET /api/v1/laboratories        CRUD（INT-487 后端待立项，mock 先行）
 *   GET /api/v1/alarms(/stats)      告警列表 + 统计（get_alarm_stats）
 *   GET /api/v1/alarm-rules         告警规则 CRUD
 *   GET /api/v1/status-history      状态历史
 *   POST /api/v1/test-devices/batch 批量操作（BATCH_ACTIONS 白名单不含 delete，§11-7）
 *   POST /api/v1/test-devices/scan  扫描设备（API 分支恒空，§11-11）
 */
import type { TestDevice } from '@/domain/models/testDevice'
import type { PlaybackDevice } from '@/domain/models/playbackDevice'
import type { ApiDevice } from '@/domain/models/apiDevice'
import type {
  Alarm,
  AlarmRule,
  AlarmStats,
  DeviceStatusEvent,
} from '@/domain/models/alarm'
import type { Laboratory } from '@/domain/models/laboratory'
import type { DeviceGroup } from '@/domain/models/deviceGroup'
import {
  MOCK_ALARMS,
  MOCK_ALARM_RULES,
  MOCK_API_DEVICES,
  MOCK_DEVICE_GROUPS,
  MOCK_LABORATORIES,
  MOCK_PLAYBACK_DEVICES,
  MOCK_SPL_MAPPING_REFS,
  MOCK_STATUS_HISTORY,
  MOCK_TEST_DEVICES,
} from '../mock/devices-mock'

/** 模拟网络延迟（视觉稿演示用；接线后删除） */
function mockLatency<T>(value: T, ms = 160): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms))
}

/** mock 内存库（页面内增删改操作在运行时可变；接线后删除） */
let testDeviceStore: TestDevice[] = [...MOCK_TEST_DEVICES]
let playbackDeviceStore: PlaybackDevice[] = [...MOCK_PLAYBACK_DEVICES]
let apiDeviceStore: ApiDevice[] = [...MOCK_API_DEVICES]
let laboratoryStore: Laboratory[] = [...MOCK_LABORATORIES]
let alarmStore: Alarm[] = [...MOCK_ALARMS]
let alarmRuleStore: AlarmRule[] = [...MOCK_ALARM_RULES]

/** 新 id（mock 阶段自增；接线后走后端自增） */
let nextDeviceId = 1000
let nextLabId = 100
let nextRuleId = 910

function freshDeviceId(): number {
  nextDeviceId += 1
  return nextDeviceId
}

/** 当前 mock 内存库（供 feature 内读取；接线后删除） */
export function peekTestDevices(): TestDevice[] {
  return testDeviceStore
}

/* ==================== 实验室名 / 映射名 refs 装饰（接线后由后端返回 lab_name） ==================== */

function decorateTestDevice(devices: TestDevice[]): TestDevice[] {
  return devices.map((device) => ({
    ...device,
    labName: device.labName ?? laboratoryStore.find((l) => l.id === device.labId)?.name ?? null,
  }))
}

function decoratePlaybackDevice(devices: PlaybackDevice[]): PlaybackDevice[] {
  return devices.map((device) => ({
    ...device,
    labName: device.labName ?? laboratoryStore.find((l) => l.id === device.labId)?.name ?? null,
    currentSplMappingName:
      device.currentSplMappingName ??
      MOCK_SPL_MAPPING_REFS.find((ref) => ref.id === device.currentSplMappingId)?.name ??
      null,
  }))
}

/** 测试中 API id 集合（INT-487 统计「测试中API」口径 mock 本地装饰） */
const API_OCCUPIED_IDS: ReadonlySet<number> = new Set([13])

function decorateApiDevice(devices: ApiDevice[]): ApiDevice[] {
  return devices.map((device) => ({
    ...device,
    occupied: API_OCCUPIED_IDS.has(device.id),
    rmsSplMappingName:
      device.rmsSplMappingName ??
      MOCK_SPL_MAPPING_REFS.find((ref) => ref.id === device.rmsSplMappingId)?.name ??
      null,
  }))
}

/* ==================== 列表查询 ==================== */

/** 测试设备列表（§3.4；GET /test-devices） */
export async function fetchTestDevices(): Promise<TestDevice[]> {
  // TODO(API 接线): GET /api/v1/test-devices
  return mockLatency(decorateTestDevice([...testDeviceStore]))
}

/** 播放设备列表（§3.5；GET /playback-devices） */
export async function fetchPlaybackDevices(): Promise<PlaybackDevice[]> {
  // TODO(API 接线): GET /api/v1/playback-devices
  return mockLatency(decoratePlaybackDevice([...playbackDeviceStore]))
}

/** 测试 API 列表（§3.6；GET /apis） */
export async function fetchApiDevices(): Promise<ApiDevice[]> {
  // TODO(API 接线): GET /api/v1/apis
  return mockLatency(decorateApiDevice([...apiDeviceStore]))
}

/** 实验室列表（§6.26；GET /api/v1/laboratories——INT-487 后端待立项） */
export async function fetchLaboratories(): Promise<Laboratory[]> {
  // TODO(API 接线): GET /api/v1/laboratories
  return mockLatency([...laboratoryStore])
}

/** 设备分组列表（§6.3；GET /device-groups） */
export async function fetchDeviceGroups(): Promise<DeviceGroup[]> {
  // TODO(API 接线): GET /api/v1/device-groups
  return mockLatency(structuredClone(MOCK_DEVICE_GROUPS))
}

/** 告警列表 + 统计（§3.7；GET /alarms，响应内 data.stats） */
export async function fetchAlarms(): Promise<{ alarms: Alarm[]; stats: AlarmStats }> {
  // TODO(API 接线): GET /api/v1/alarms?status=&severity=&device_id=&page=&per_page
  const active = alarmStore.filter((a) => a.status === 'active').length
  const acknowledged = alarmStore.filter((a) => a.status === 'acknowledged').length
  const resolved = alarmStore.filter((a) => a.status === 'resolved').length
  return mockLatency({
    alarms: [...alarmStore],
    stats: {
      active,
      acknowledged,
      resolved,
      total: alarmStore.length,
    },
  })
}

/** 告警规则列表（§6.6；GET /alarm-rules） */
export async function fetchAlarmRules(): Promise<AlarmRule[]> {
  // TODO(API 接线): GET /api/v1/alarm-rules
  return mockLatency([...alarmRuleStore])
}

/** 状态历史（§3.7；GET /status-history） */
export async function fetchStatusHistory(): Promise<DeviceStatusEvent[]> {
  // TODO(API 接线): GET /api/v1/status-history?device_ids=&event_type=&start_time=&end_time=
  return mockLatency([...MOCK_STATUS_HISTORY])
}

/* ==================== 变更操作（mock 内存库；接线后替换为真实请求） ==================== */

/** 新增测试设备（§6.2；POST /test-devices） */
export async function createTestDevice(input: Omit<TestDevice, 'id' | 'createdAt' | 'updatedAt'>) {
  // TODO(API 接线): POST /api/v1/test-devices
  const device: TestDevice = { ...input, id: freshDeviceId(), createdAt: now(), updatedAt: now() }
  testDeviceStore = [device, ...testDeviceStore]
  await mockLatency(null, 120)
  return { success: true, device }
}

/** 编辑测试设备（§6.2；PUT /test-devices/{id}） */
export async function updateTestDevice(id: number, patch: Partial<TestDevice>) {
  // TODO(API 接线): PUT /api/v1/test-devices/{id}
  testDeviceStore = testDeviceStore.map((d) =>
    d.id === id ? { ...d, ...patch, updatedAt: now() } : d
  )
  await mockLatency(null, 120)
  return { success: true }
}

/** 删除测试设备（§3.4.1；DELETE /test-devices/{id}；被测试任务占用拦截 §11-1 toast） */
export async function deleteTestDevice(id: number) {
  // TODO(API 接线): DELETE /api/v1/test-devices/{id}
  const target = testDeviceStore.find((d) => d.id === id)
  if (target?.occupied) return { success: false, message: '该设备已关联测试任务，无法删除' }
  testDeviceStore = testDeviceStore.filter((d) => d.id !== id)
  await mockLatency(null, 120)
  return { success: true }
}

/** 新增播放设备（§6.2；POST /playback-devices） */
export async function createPlaybackDevice(
  input: Omit<PlaybackDevice, 'id' | 'createdAt' | 'updatedAt'>
) {
  // TODO(API 接线): POST /api/v1/playback-devices
  const device: PlaybackDevice = { ...input, id: freshDeviceId(), createdAt: now(), updatedAt: now() }
  playbackDeviceStore = [device, ...playbackDeviceStore]
  await mockLatency(null, 120)
  return { success: true, device }
}

/** 编辑播放设备（§6.2；PUT /playback-devices/{id}） */
export async function updatePlaybackDevice(id: number, patch: Partial<PlaybackDevice>) {
  // TODO(API 接线): PUT /api/v1/playback-devices/{id}
  playbackDeviceStore = playbackDeviceStore.map((d) =>
    d.id === id ? { ...d, ...patch, updatedAt: now() } : d
  )
  await mockLatency(null, 120)
  return { success: true }
}

/** 删除播放设备（§3.5；DELETE /playback-devices/{id}） */
export async function deletePlaybackDevice(id: number) {
  // TODO(API 接线): DELETE /api/v1/playback-devices/{id}
  playbackDeviceStore = playbackDeviceStore.filter((d) => d.id !== id)
  await mockLatency(null, 120)
  return { success: true }
}

/** 新增测试 API（§6.2；POST /apis） */
export async function createApiDevice(input: Omit<ApiDevice, 'id' | 'createdAt' | 'updatedAt'>) {
  // TODO(API 接线): POST /api/v1/apis
  const device: ApiDevice = { ...input, id: freshDeviceId(), createdAt: now(), updatedAt: now() }
  apiDeviceStore = [device, ...apiDeviceStore]
  await mockLatency(null, 120)
  return { success: true, device }
}

/** 编辑测试 API（§6.2；PUT /apis/{id}——复用 INT-355 §5.3 口径） */
export async function updateApiDevice(id: number, patch: Partial<ApiDevice>) {
  // TODO(API 接线): PUT /api/v1/apis/{id}
  apiDeviceStore = apiDeviceStore.map((d) =>
    d.id === id ? { ...d, ...patch, updatedAt: now() } : d
  )
  await mockLatency(null, 120)
  return { success: true }
}

/** 删除测试 API（§3.6；DELETE /apis/{id}） */
export async function deleteApiDevice(id: number) {
  // TODO(API 接线): DELETE /api/v1/apis/{id}
  apiDeviceStore = apiDeviceStore.filter((d) => d.id !== id)
  await mockLatency(null, 120)
  return { success: true }
}

/** 设备控制操作（§3.4.1；POST /test-devices/{id}/{action}，mock 幂等成功） */
export async function controlDevice(id: number, action: string) {
  // TODO(API 接线): POST /api/v1/test-devices/{id}/{action}
  await mockLatency(null, 200)
  return { success: true, action, id }
}

/** 「测试中」占用态本地瞬时态兜底（INT-487 §3.4 注③：后端 occupied/testing 待立项，
 * 落地前前端「测试/停止测试」动作置/清 occupied；接线后改调占用查询/任务派发端点） */
export async function setDeviceOccupied(
  kind: 'test' | 'playback' | 'api',
  id: number,
  occupied: boolean
) {
  // TODO(API 接线): POST /api/v1/tasks/{id}/start|stop 联动占用状态
  if (kind === 'test') {
    testDeviceStore = testDeviceStore.map((d) => (d.id === id ? { ...d, occupied } : d))
  } else if (kind === 'playback') {
    playbackDeviceStore = playbackDeviceStore.map((d) => (d.id === id ? { ...d, occupied } : d))
  } else {
    apiDeviceStore = apiDeviceStore.map((d) => (d.id === id ? { ...d, occupied } : d))
  }
  await mockLatency(null, 80)
  return { success: true }
}

/** 批量设备操作（§3.8；POST /test-devices/batch；delete 前端串行 §11-7） */
const executedBatchKeys = new Set<string>()

export async function batchDeviceAction(action: string, ids: number[]) {
  // TODO(API 接线): POST /api/v1/test-devices/batch
  await mockLatency(null, 220)
  // 幂等键模拟：同 action + 同 id 集合重复提交 → 命中幂等回放（P2-6 返修：部分失败与回放区分）
  const key = `${action}:${[...ids].sort((a, b) => a - b).join(',')}`
  const replayed = executedBatchKeys.has(key)
  executedBatchKeys.add(key)
  const successCount = ids.length
  return {
    action,
    total: ids.length,
    successCount,
    replayedCount: replayed ? ids.length : 0,
    results: ids.map((id) => ({
      id,
      success: true,
      message: replayed ? '命中幂等回放，未重复执行' : null,
    })),
  }
}

/** 确认告警（§3.7；POST /alarms/{id}/acknowledge，acknowledged_by 后端注入 request.username） */
export async function acknowledgeAlarm(id: number) {
  // TODO(API 接线): POST /api/v1/alarms/{id}/acknowledge
  alarmStore = alarmStore.map((a) =>
    a.id === id ? { ...a, status: 'acknowledged', acknowledgedBy: '当前用户' } : a
  )
  await mockLatency(null, 120)
  return { success: true }
}

/** 保存告警规则（§6.6；POST/PUT /alarm-rules） */
export async function saveAlarmRule(input: Omit<AlarmRule, 'id' | 'createdAt' | 'updatedAt'> & { id?: number }) {
  // TODO(API 接线): POST/PUT /api/v1/alarm-rules
  if (input.id) {
    alarmRuleStore = alarmRuleStore.map((r) => (r.id === input.id ? { ...r, ...input, updatedAt: now() } : r))
  } else {
    const rule: AlarmRule = { ...input, id: nextRuleId++, createdAt: now(), updatedAt: now() }
    alarmRuleStore = [rule, ...alarmRuleStore]
  }
  await mockLatency(null, 120)
  return { success: true }
}

/** 删除告警规则（§6.6；DELETE /alarm-rules/{id}） */
export async function deleteAlarmRule(id: number) {
  // TODO(API 接线): DELETE /api/v1/alarm-rules/{id}
  alarmRuleStore = alarmRuleStore.filter((r) => r.id !== id)
  await mockLatency(null, 120)
  return { success: true }
}

/** 新建实验室（§6.26；POST /laboratories——INT-487 后端待立项，mock 先行） */
export async function createLaboratory(input: Omit<Laboratory, 'id' | 'createdAt' | 'updatedAt' | 'deviceCount' | 'playbackDeviceCount' | 'testCaseCount'>) {
  // TODO(API 接线): POST /api/v1/laboratories
  const lab: Laboratory = { ...input, id: nextLabId++, deviceCount: 0, playbackDeviceCount: 0, testCaseCount: 0, createdAt: now(), updatedAt: now() }
  laboratoryStore = [lab, ...laboratoryStore]
  await mockLatency(null, 120)
  return { success: true }
}

/** 删除实验室（§6.26；DELETE /laboratories/{id}） */
export async function deleteLaboratory(id: number) {
  // TODO(API 接线): DELETE /api/v1/laboratories/{id}
  laboratoryStore = laboratoryStore.filter((l) => l.id !== id)
  await mockLatency(null, 120)
  return { success: true }
}

/** 编辑实验室（§6.26；PUT /laboratories/{id}——P3-21 返修补「编辑」操作） */
export async function updateLaboratory(
  id: number,
  patch: Partial<Omit<Laboratory, 'id' | 'createdAt' | 'updatedAt' | 'deviceCount' | 'playbackDeviceCount' | 'testCaseCount'>>
) {
  // TODO(API 接线): PUT /api/v1/laboratories/{id}
  laboratoryStore = laboratoryStore.map((l) =>
    l.id === id ? { ...l, ...patch, updatedAt: now() } : l
  )
  await mockLatency(null, 120)
  return { success: true }
}

/** 扫描设备（§6.1；POST /test-devices/scan；API 分支恒空 §11-11） */
export async function scanDevices(kind: 'test' | 'playback') {
  // TODO(API 接线): POST /api/v1/test-devices/scan（ADB/HDC）+ /playback-devices/scan（系统音频通道）
  await mockLatency(null, 1400)
  if (kind === 'test') {
    return [
      { serial: 'SN-SCAN-1001', model: '旗舰 S1', system: 'harmony', status: 'online', is_registered: false, id: null, name: null, type: 'physical', system_version: '3.2.1', app_name: null, app_version: null, ip: '192.168.1.51' },
      { serial: 'SN-SCAN-1002', model: 'Xiaomi 14', system: 'android', status: 'online', is_registered: false, id: null, name: null, type: 'physical', system_version: '14', app_name: null, app_version: null, ip: '192.168.1.52' },
      { serial: 'SN-A001-8821', model: '旗舰 S1', system: 'harmony', status: 'online', is_registered: true, id: 1, name: '音箱-客厅位', type: 'physical', system_version: '3.2.1', app_name: null, app_version: null, ip: '192.168.1.21' },
    ]
  }
  return [
    { name: 'Speaker Out 1', model: '系统音频通道', device_unique_id: 'AUDIO-OUT-01', channel_index: 0, sample_rate: 48000, type: 'dry', status: 'online' },
    { name: 'Speaker Out 2', model: '系统音频通道', device_unique_id: 'AUDIO-OUT-02', channel_index: 1, sample_rate: 48000, type: 'noise', status: 'offline' },
  ]
}

function now(): string {
  return new Date().toISOString()
}
