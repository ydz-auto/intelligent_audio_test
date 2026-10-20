/**
 * 设备管理页 API（infrastructure/api 层；接线 INT-644）。
 * 经 client.ts 统一 fetch 封装（baseURL /api/v1 → dev 代理 gateway:5000；INT-605），
 * 端点对照 api_gateway/routes/device_bp.py（/test-devices）、playback_bp.py
 * （/playback-devices）、api_bp.py（/apis）实测契约；响应 snake_case DTO 经
 * infrastructure/adapters 转 camelCase Domain（snake→camel 唯一转换层，红线③）。
 * 列表端点统一 PaginatedData { items,total,page,per_page,pages }：本页全量拉取
 * （per_page=1000，对照 Vue BATCH_LIST_PARAMS.defaultBatchPageSize），
 * 筛选/分页由 feature 层前端完成（接线前 mock 同口径）。
 * INT-487 待后端：laboratories CRUD 无端点（§11-24，mock 先行 + FEAT 证据）、
 * lab_id/lab_name/occupied 后端 DTO 未暴露（§11-25/26）——occupied 以本地瞬时
 * 覆盖兜底（见 setDeviceOccupied），lab 字段落地后接线不返工。
 */
import type { TestDevice } from '@/domain/models/testDevice'
import type { PlaybackDevice } from '@/domain/models/playbackDevice'
import type { ApiDevice, ApiEndpoint } from '@/domain/models/apiDevice'
import type {
  Alarm,
  AlarmRule,
  AlarmStats,
  DeviceStatusEvent,
} from '@/domain/models/alarm'
import type { Laboratory } from '@/domain/models/laboratory'
import type { DeviceGroup } from '@/domain/models/deviceGroup'
import { request, type ApiRequestOptions } from '@/infrastructure/api/client'
import { ApiError } from '@/infrastructure/api/api-error'
import type { TestDeviceItemDto } from '@/infrastructure/dto/test-device.dto'
import type { PlaybackDeviceItemDto } from '@/infrastructure/dto/playback-device.dto'
import type { ApiItemDto } from '@/infrastructure/dto/apis.dto'
import type { DeviceGroupItemDto } from '@/infrastructure/dto/device-group.dto'
import type {
  AlarmDto,
  AlarmRuleDto,
  AlarmStatsDto,
  DeviceStatusHistoryDto,
} from '@/infrastructure/dto/alarm.dto'
import { testDeviceFromDto } from '@/infrastructure/adapters/testDeviceAdapter'
import { playbackDeviceFromDto } from '@/infrastructure/adapters/playbackDeviceAdapter'
import { apiDeviceFromDto } from '@/infrastructure/adapters/apiDeviceAdapter'
import { deviceGroupFromDto, deviceGroupsToTree } from '@/infrastructure/adapters/deviceGroupAdapter'
import {
  alarmFromDto,
  alarmRuleFromDto,
  statusEventFromDto,
} from '@/infrastructure/adapters/alarmAdapter'
import { MOCK_LABORATORIES } from '../mock/devices-mock'

/** 后端统一分页信封（api_gateway/schemas/common.py PaginatedData） */
interface PaginatedDto<T> {
  items: T[]
  total: number
  page: number
  per_page: number
  pages: number
}

/** 列表全量拉取参数（筛选/分页前端做；对照 Vue BATCH_LIST_PARAMS） */
const LIST_ALL_PARAMS = { page: 1, per_page: 1000 }

/** 扫描结果行（device.py DeviceScanItem / playback.py PlaybackScanItem，snake_case 直出） */
export interface ScannedDeviceRowDto {
  serial?: string | null
  model?: string | null
  system?: string | null
  system_version?: string | null
  ip?: string | null
  status?: string | null
  is_registered?: boolean
  id?: number | string | null
  name?: string | null
  type?: string | null
  device_unique_id?: string | null
  channel_index?: number | null
  sample_rate?: number | null
  /** P3-1 返修：扫描响应含真实 app_name/app_version（后端 DeviceScanItem 透传），预填不再硬编码默认值 */
  app_name?: string | null
  app_version?: string | null
}

/* ==================== INT-487「测试中」占用态本地瞬时覆盖 ==================== */

/** 后端未暴露 occupied/testing（§11-26）；测试/停止测试动作后本地覆盖维持徽章（落地后换占用查询端点） */
const occupiedOverrides = new Map<'test' | 'playback' | 'api', Map<number, boolean>>()

function applyOccupied<T extends { id: number; occupied: boolean }>(
  kind: 'test' | 'playback' | 'api',
  items: T[]
): T[] {
  const overrides = occupiedOverrides.get(kind)
  if (!overrides || overrides.size === 0) return items
  return items.map((item) => {
    const override = overrides.get(item.id)
    return override === undefined ? item : { ...item, occupied: override }
  })
}

/* ==================== 列表查询（全量拉取，feature 层前端筛选分页） ==================== */

/** 测试设备列表（§3.4；GET /test-devices） */
export async function fetchTestDevices(options: ApiRequestOptions = {}): Promise<TestDevice[]> {
  const dto = await request<PaginatedDto<TestDeviceItemDto>>(
    'GET', '/test-devices', undefined, { ...options, params: LIST_ALL_PARAMS }
  )
  return applyOccupied('test', (dto?.items ?? []).map(testDeviceFromDto))
}

/** 驱动关键字（V9.7.10 添加测试设备 keywords 选项来源 loadDriverKeywords；GET /test-devices/driver-keywords） */
export interface DriverKeywordItem {
  name: string
  keywords: string
  system: string
}

export async function fetchDriverKeywords(options: ApiRequestOptions = {}): Promise<DriverKeywordItem[]> {
  const dto = await request<DriverKeywordItem[]>(
    'GET', '/test-devices/driver-keywords', undefined, options
  )
  return dto ?? []
}

/** 播放设备列表（§3.5；GET /playback-devices） */
export async function fetchPlaybackDevices(options: ApiRequestOptions = {}): Promise<PlaybackDevice[]> {
  const dto = await request<PaginatedDto<PlaybackDeviceItemDto>>(
    'GET', '/playback-devices', undefined, { ...options, params: LIST_ALL_PARAMS }
  )
  return applyOccupied('playback', (dto?.items ?? []).map(playbackDeviceFromDto))
}

/** 测试 API 列表（§3.6；GET /apis） */
export async function fetchApiDevices(options: ApiRequestOptions = {}): Promise<ApiDevice[]> {
  const dto = await request<PaginatedDto<ApiItemDto>>(
    'GET', '/apis', undefined, { ...options, params: LIST_ALL_PARAMS }
  )
  return applyOccupied('api', (dto?.items ?? []).map(apiDeviceFromDto))
}

/** 实验室列表（§6.26；GET /laboratories——INT-487 后端 CRUD 未立项，mock 先行） */
export async function fetchLaboratories(): Promise<Laboratory[]> {
  return [...MOCK_LABORATORIES]
}

/** 设备分组列表（§6.3；GET /test-devices/device-groups——INT-832 起每项含 parent_id，返回嵌套树） */
export async function fetchDeviceGroups(options: ApiRequestOptions = {}): Promise<DeviceGroup[]> {
  const dto = await request<PaginatedDto<DeviceGroupItemDto>>(
    'GET', '/test-devices/device-groups', undefined,
    { ...options, params: LIST_ALL_PARAMS }
  )
  // INT-832：列表扁平分页、每项含 parent_id，树由前端按 parentId 建（children）
  return deviceGroupsToTree((dto?.items ?? []).map(deviceGroupFromDto))
}

/** 设备分组详情（§6.3；GET /test-devices/device-groups/{id}——列表 device_ids 恒空，真实成员以详情为准，P2-1） */
export async function fetchDeviceGroupDetail(
  id: string,
  options: ApiRequestOptions = {}
): Promise<DeviceGroup> {
  const dto = await request<DeviceGroupItemDto>(
    'GET', `/test-devices/device-groups/${id}`, undefined, options
  )
  return deviceGroupFromDto(dto)
}

/* ==================== 设备分组 CRUD（§6.3；device_bp.py /test-devices/device-groups 实测契约） ==================== */

/** 新建分组（POST /test-devices/device-groups；DeviceGroupCreateSchema：name/description/group_type/device_ids） */
export async function createDeviceGroup(
  input: { name: string; description?: string | null; groupType?: DeviceGroup['groupType']; deviceIds?: number[] },
  options: ApiRequestOptions = {}
): Promise<{ success: boolean; message?: string }> {
  const body: Record<string, unknown> = {
    name: input.name,
    description: input.description ?? null,
    group_type: input.groupType ?? 'test',
    device_ids: input.deviceIds ?? [],
  }
  await request('POST', '/test-devices/device-groups', body, options)
  return { success: true }
}

/** 编辑分组（PUT /test-devices/device-groups/{id}；DeviceGroupUpdateSchema：name/description/group_type） */
export async function updateDeviceGroup(
  id: string,
  patch: { name?: string; description?: string | null; groupType?: DeviceGroup['groupType'] },
  options: ApiRequestOptions = {}
): Promise<{ success: boolean; message?: string }> {
  const body: Record<string, unknown> = {
    name: patch.name,
    description: patch.description,
    group_type: patch.groupType,
  }
  await request('PUT', `/test-devices/device-groups/${id}`, body, options)
  return { success: true }
}

/** 移动分组（INT-864/INT-832；PUT /test-devices/device-groups/{id}/move，body {parent_id: string|null}） */
export async function moveDeviceGroup(
  id: string,
  parentId: string | null,
  options: ApiRequestOptions = {}
): Promise<{ success: boolean }> {
  await request('PUT', `/test-devices/device-groups/${id}/move`, { parent_id: parentId }, options)
  return { success: true }
}

/** 删除分组（DELETE /test-devices/device-groups/{id}；含成员需 cascade=true 先移出，§11-5 口径） */
export async function deleteDeviceGroup(
  id: string,
  cascade = true,
  options: ApiRequestOptions = {}
): Promise<{ success: boolean; message?: string }> {
  return deleteGuard(() =>
    request('DELETE', `/test-devices/device-groups/${id}`, undefined, {
      ...options,
      params: { ...(options.params ?? {}), cascade },
    })
  )
}

/** 添加成员（POST /test-devices/device-groups/{id}/devices；DeviceGroupMembersRequest：device_ids） */
export async function addDevicesToGroup(
  id: string,
  deviceIds: number[],
  options: ApiRequestOptions = {}
): Promise<{ success: boolean; added?: number; message?: string }> {
  const dto = await request<{ added?: number }>(
    'POST', `/test-devices/device-groups/${id}/devices`, { device_ids: deviceIds }, options
  )
  return { success: true, added: dto?.added ?? 0 }
}

/** 移除成员（POST /test-devices/device-groups/{id}/remove-devices；DeviceGroupMembersRequest：device_ids） */
export async function removeDevicesFromGroup(
  id: string,
  deviceIds: number[],
  options: ApiRequestOptions = {}
): Promise<{ success: boolean; removed?: number; message?: string }> {
  const dto = await request<{ removed?: number }>(
    'POST', `/test-devices/device-groups/${id}/remove-devices`, { device_ids: deviceIds }, options
  )
  return { success: true, removed: dto?.removed ?? 0 }
}

/** 告警列表 + 统计（§3.7；GET /test-devices/alarms，响应 data.stats） */
export async function fetchAlarms(
  options: ApiRequestOptions = {}
): Promise<{ alarms: Alarm[]; stats: AlarmStats }> {
  const dto = await request<PaginatedDto<AlarmDto> & { stats?: AlarmStatsDto }>(
    'GET', '/test-devices/alarms', undefined,
    { ...options, params: { page: 1, per_page: 500 } }
  )
  return {
    alarms: (dto?.items ?? []).map(alarmFromDto),
    stats: toAlarmStats(dto?.stats),
  }
}

function toAlarmStats(stats: AlarmStatsDto | undefined): AlarmStats {
  return {
    active: stats?.active ?? 0,
    acknowledged: stats?.acknowledged ?? 0,
    resolved: stats?.resolved ?? 0,
    total: stats?.total ?? 0,
  }
}

/** 告警规则列表（§6.6；GET /test-devices/alarm-rules） */
export async function fetchAlarmRules(options: ApiRequestOptions = {}): Promise<AlarmRule[]> {
  const dto = await request<PaginatedDto<AlarmRuleDto>>(
    'GET', '/test-devices/alarm-rules', undefined,
    { ...options, params: { page: 1, per_page: 100 } }
  )
  return (dto?.items ?? []).map(alarmRuleFromDto)
}

/** 状态历史（§3.7；GET /test-devices/status-history） */
export async function fetchStatusHistory(options: ApiRequestOptions = {}): Promise<DeviceStatusEvent[]> {
  const dto = await request<PaginatedDto<DeviceStatusHistoryDto>>(
    'GET', '/test-devices/status-history', undefined,
    { ...options, params: { page: 1, per_page: 200 } }
  )
  return (dto?.items ?? []).map(statusEventFromDto)
}

/* ==================== 变更操作（camelCase Domain → snake_case 请求体，对照后端 Create/Update Schema） ==================== */

/** DeviceCreateSchema/DeviceUpdateSchema 字段集（高级设置/占位字段后端 schema 未覆盖，不发送） */
function toTestDeviceUpsertDto(data: Partial<TestDevice>): Record<string, unknown> {
  const dto: Record<string, unknown> = {}
  const pick = <K extends keyof TestDevice>(key: K, snake: string) => {
    const value = data[key]
    if (value !== undefined) dto[snake] = value
  }
  pick('name', 'name')
  pick('model', 'model')
  pick('type', 'type')
  pick('system', 'system')
  pick('systemVersion', 'system_version')
  pick('appName', 'app_name')
  pick('appVersion', 'app_version')
  pick('description', 'description')
  pick('location', 'location')
  pick('maxAudioDuration', 'max_audio_duration')
  pick('needsPromptAudio', 'needs_prompt_audio')
  pick('connectionType', 'connection_type')
  pick('keywords', 'keywords')
  pick('serialNumber', 'serial_number')
  pick('ip', 'ip')
  pick('status', 'status')
  pick('supportedAlgorithms', 'supported_algorithms')
  return dto
}

/** PlaybackCreateSchema/PlaybackUpdateSchema 字段集（INT-381 补口字段后端 schema 未覆盖，不发送） */
function toPlaybackDeviceUpsertDto(data: Partial<PlaybackDevice>): Record<string, unknown> {
  const dto: Record<string, unknown> = {}
  const pick = <K extends keyof PlaybackDevice>(key: K, snake: string) => {
    const value = data[key]
    if (value !== undefined) dto[snake] = value
  }
  pick('name', 'name')
  pick('model', 'model')
  pick('deviceType', 'device_type')
  pick('sampleRate', 'sample_rate')
  pick('channelIndex', 'channel_index')
  pick('deviceUniqueId', 'device_unique_id')
  pick('description', 'description')
  pick('status', 'status')
  pick('currentSplMappingId', 'current_spl_mapping_id')
  return dto
}

function toApiEndpointUpsertDto(ep: ApiEndpoint): Record<string, unknown> {
  const dto: Record<string, unknown> = {}
  if (ep.endpoint !== undefined) dto.endpoint = ep.endpoint
  if (ep.name !== undefined) dto.name = ep.name
  if (ep.maxProcess !== undefined) dto.max_process = ep.maxProcess
  if (ep.maxTimeout !== undefined) dto.max_timeout = ep.maxTimeout
  if (ep.maxAudioDuration !== undefined) dto.max_audio_duration = ep.maxAudioDuration
  if (ep.priority !== undefined) dto.priority = ep.priority
  if (ep.status !== undefined) dto.status = ep.status
  if (ep.description !== undefined) dto.description = ep.description
  return dto
}

/** ApiCreateInput/ApiUpdateInput 字段集（camelCase 端点行 → snake_case） */
function toApiDeviceUpsertDto(data: Partial<ApiDevice>): Record<string, unknown> {
  const dto: Record<string, unknown> = {}
  const pick = <K extends keyof ApiDevice>(key: K, snake: string) => {
    const value = data[key]
    if (value !== undefined) dto[snake] = value
  }
  pick('name', 'name')
  pick('vendor', 'vendor')
  pick('apiUrl', 'api_url')
  pick('description', 'description')
  pick('meta', 'meta')
  pick('algorithmType', 'algorithm_type')
  pick('defaultMaxProcess', 'default_max_process')
  pick('defaultMaxTimeout', 'default_max_timeout')
  pick('defaultMaxAudioDuration', 'default_max_audio_duration')
  pick('status', 'status')
  pick('rmsSplMappingId', 'rms_spl_mapping_id')
  // INT-1029：每 API 代理配置（api_test_service ApiCreateInput/ApiUpdateInput 契约 proxy_type/proxy_url）
  pick('proxyType', 'proxy_type')
  pick('proxyUrl', 'proxy_url')
  if (data.endpoints !== undefined) {
    dto.endpoints = data.endpoints.map(toApiEndpointUpsertDto)
  }
  return dto
}

/** 删除失败收敛为 { success:false, message }（复用服务端中文文案，UI toast 直呈） */
async function deleteGuard(action: () => Promise<unknown>): Promise<{ success: boolean; message?: string }> {
  try {
    await action()
    return { success: true }
  } catch (error) {
    if (error instanceof ApiError) return { success: false, message: error.userMessage }
    return { success: false, message: '操作失败，请重试' }
  }
}

/** 新增测试设备（§6.2；POST /test-devices） */
export async function createTestDevice(
  input: Omit<TestDevice, 'id' | 'createdAt' | 'updatedAt'>,
  options: ApiRequestOptions = {}
): Promise<{ success: boolean }> {
  await request('POST', '/test-devices', toTestDeviceUpsertDto(input), options)
  return { success: true }
}

/** 编辑测试设备（§6.2；PUT /test-devices/{id}） */
export async function updateTestDevice(
  id: number,
  patch: Partial<TestDevice>,
  options: ApiRequestOptions = {}
): Promise<{ success: boolean }> {
  await request('PUT', `/test-devices/${id}`, toTestDeviceUpsertDto(patch), options)
  return { success: true }
}

/** 删除测试设备（§3.4.1；DELETE /test-devices/{id}；被测试任务占用由后端拦截） */
export async function deleteTestDevice(
  id: number,
  options: ApiRequestOptions = {}
): Promise<{ success: boolean; message?: string }> {
  return deleteGuard(() => request('DELETE', `/test-devices/${id}`, undefined, options))
}

/** 新增播放设备（§6.2；POST /playback-devices） */
export async function createPlaybackDevice(
  input: Omit<PlaybackDevice, 'id' | 'createdAt' | 'updatedAt'>,
  options: ApiRequestOptions = {}
): Promise<{ success: boolean }> {
  await request('POST', '/playback-devices', toPlaybackDeviceUpsertDto(input), options)
  return { success: true }
}

/** 编辑播放设备（§6.2；PUT /playback-devices/{id}） */
export async function updatePlaybackDevice(
  id: number,
  patch: Partial<PlaybackDevice>,
  options: ApiRequestOptions = {}
): Promise<{ success: boolean }> {
  await request('PUT', `/playback-devices/${id}`, toPlaybackDeviceUpsertDto(patch), options)
  return { success: true }
}

/** 删除播放设备（§3.5；DELETE /playback-devices/{id}） */
export async function deletePlaybackDevice(
  id: number,
  options: ApiRequestOptions = {}
): Promise<{ success: boolean; message?: string }> {
  return deleteGuard(() => request('DELETE', `/playback-devices/${id}`, undefined, options))
}

/** 新增测试 API（§6.2；POST /apis） */
export async function createApiDevice(
  input: Omit<ApiDevice, 'id' | 'createdAt' | 'updatedAt'>,
  options: ApiRequestOptions = {}
): Promise<{ success: boolean }> {
  await request('POST', '/apis', toApiDeviceUpsertDto(input), options)
  return { success: true }
}

/** 编辑测试 API（§6.2；PUT /apis/{id}） */
export async function updateApiDevice(
  id: number,
  patch: Partial<ApiDevice>,
  options: ApiRequestOptions = {}
): Promise<{ success: boolean }> {
  await request('PUT', `/apis/${id}`, toApiDeviceUpsertDto(patch), options)
  return { success: true }
}

/** 删除测试 API（§3.6；DELETE /apis/{id}） */
export async function deleteApiDevice(
  id: number,
  options: ApiRequestOptions = {}
): Promise<{ success: boolean; message?: string }> {
  return deleteGuard(() => request('DELETE', `/apis/${id}`, undefined, options))
}

/** 关联声压映射（§6.4；POST /playback-devices/{id}/associate-spl，body camelCase splMappingId 实测） */
export async function associatePlaybackSpl(
  deviceId: number,
  splMappingId: number,
  options: ApiRequestOptions = {}
): Promise<{ success: boolean; message?: string }> {
  await request('POST', `/playback-devices/${deviceId}/associate-spl`, { splMappingId }, options)
  return { success: true }
}

/** 设备操作端点路径段（device_bp 固定段；health_check/api_health_check 走独立端点） */
function controlActionToPath(action: string): string | null {
  switch (action) {
    case 'connect': return 'connect'
    case 'disconnect': return 'disconnect'
    case 'reboot': return 'reboot'
    case 'shutdown': return 'shutdown'
    case 'install_app': return 'install-app'
    case 'uninstall_app': return 'uninstall-app'
    default: return null
  }
}

/** 设备控制操作（§3.4.1；POST /test-devices/{id}/{action}；health_check 走批量端点） */
export async function controlDevice(
  id: number,
  action: string,
  options: ApiRequestOptions = {}
): Promise<{ success: boolean; action?: string; id?: number }> {
  if (action === 'health_check') {
    await request('POST', '/test-devices/health-check', { device_ids: [id] }, options)
    return { success: true, action, id }
  }
  if (action === 'api_health_check') {
    await request('POST', `/apis/${id}/health`, undefined, options)
    return { success: true, action, id }
  }
  const path = controlActionToPath(action)
  if (!path) {
    // 后端无此操作端点（播放设备 restart/reset-config/mute/unmute 等 UX 视觉稿动作，
    // 无 Vue 对位/未立项 → 本地幂等成功，不产生真实调用）
    return { success: true, action, id }
  }
  await request('POST', `/test-devices/${id}/${path}`, undefined, options)
  return { success: true, action, id }
}

/** 「测试中」占用态：本地瞬时覆盖 + 真实测试派发端点（INT-487 §3.4 注③：测试/停止测试） */
export async function setDeviceOccupied(
  kind: 'test' | 'playback' | 'api',
  id: number,
  occupied: boolean,
  options: ApiRequestOptions = {}
): Promise<{ success: boolean }> {
  const overrides = occupiedOverrides.get(kind) ?? new Map<number, boolean>()
  overrides.set(id, occupied)
  occupiedOverrides.set(kind, overrides)
  const base = kind === 'test' ? '/test-devices' : kind === 'playback' ? '/playback-devices' : '/apis'
  await request('POST', `${base}/${id}/${occupied ? 'test' : 'stop-test'}`, undefined, options)
  return { success: true }
}

/** 批量设备操作（§3.8；POST /test-devices/batch；delete 前端串行 §11-7；health_check 后端 batch 白名单内） */
export async function batchDeviceAction(
  action: string,
  ids: number[],
  options: ApiRequestOptions = {}
): Promise<{
  action: string
  total: number
  successCount: number
  replayedCount: number
  results: Array<{ id: number; success: boolean; message: string | null }>
}> {
  const dto = await request<{
    action?: string
    total?: number
    success_count?: number
    results?: Array<{ id: number | string; success?: boolean; message?: string }>
    idempotent_replay?: boolean
  }>('POST', '/test-devices/batch', { action, device_ids: ids }, options)
  const results = (dto?.results ?? []).map((row) => ({
    id: Number(row.id),
    success: row.success ?? false,
    message: row.message ?? null,
  }))
  const total = dto?.total ?? results.length
  return {
    action: dto?.action ?? action,
    total,
    successCount: dto?.success_count ?? 0,
    replayedCount: dto?.idempotent_replay ? total : 0,
    results,
  }
}

/** 确认告警（§3.7；POST /test-devices/alarms/{id}/acknowledge，acknowledged_by 后端注入 request.username） */
export async function acknowledgeAlarm(
  id: number,
  options: ApiRequestOptions = {}
): Promise<{ success: boolean }> {
  await request('POST', `/test-devices/alarms/${id}/acknowledge`, {}, options)
  return { success: true }
}

/** 保存告警规则（§6.6；POST/PUT /test-devices/alarm-rules[/{id}]） */
export async function saveAlarmRule(
  input: Omit<AlarmRule, 'id' | 'createdAt' | 'updatedAt'> & { id?: number },
  options: ApiRequestOptions = {}
): Promise<{ success: boolean }> {
  const body = {
    name: input.name,
    metric_type: input.metricType,
    threshold_value: input.thresholdValue,
    severity: input.severity,
    notify_email: input.notifyEmail,
    enabled: input.enabled,
  }
  if (input.id != null) {
    await request('PUT', `/test-devices/alarm-rules/${input.id}`, body, options)
  } else {
    await request('POST', '/test-devices/alarm-rules', body, options)
  }
  return { success: true }
}

/** 删除告警规则（§6.6；DELETE /test-devices/alarm-rules/{id}） */
export async function deleteAlarmRule(
  id: number,
  options: ApiRequestOptions = {}
): Promise<{ success: boolean; message?: string }> {
  return deleteGuard(() => request('DELETE', `/test-devices/alarm-rules/${id}`, undefined, options))
}

/* ==================== 实验室（§6.26；INT-487 后端 /laboratories CRUD 未立项，mock 先行） ==================== */

let laboratoryStore: Laboratory[] = [...MOCK_LABORATORIES]
let nextLabId = 100

function now(): string {
  return new Date().toISOString()
}

/** 新建实验室（§6.26；POST /laboratories——INT-487 后端待立项，mock 先行） */
export async function createLaboratory(
  input: Omit<Laboratory, 'id' | 'createdAt' | 'updatedAt' | 'deviceCount' | 'playbackDeviceCount' | 'testCaseCount'>
): Promise<{ success: boolean }> {
  const lab: Laboratory = {
    ...input,
    id: nextLabId++,
    deviceCount: 0,
    playbackDeviceCount: 0,
    testCaseCount: 0,
    createdAt: now(),
    updatedAt: now(),
  }
  laboratoryStore = [lab, ...laboratoryStore]
  return { success: true }
}

/** 删除实验室（§6.26；DELETE /laboratories/{id}——INT-487 后端待立项，mock 先行） */
export async function deleteLaboratory(id: number): Promise<{ success: boolean; message?: string }> {
  laboratoryStore = laboratoryStore.filter((l) => l.id !== id)
  return { success: true }
}

/** 编辑实验室（§6.26；PUT /laboratories/{id}——INT-487 后端待立项，mock 先行；P3-21 返修补「编辑」） */
export async function updateLaboratory(
  id: number,
  patch: Partial<
    Omit<Laboratory, 'id' | 'createdAt' | 'updatedAt' | 'deviceCount' | 'playbackDeviceCount' | 'testCaseCount'>
  >
): Promise<{ success: boolean }> {
  laboratoryStore = laboratoryStore.map((l) =>
    l.id === id ? { ...l, ...patch, updatedAt: now() } : l
  )
  return { success: true }
}

/** 扫描设备（§6.1；POST /test-devices/scan（ADB/HDC）+ /playback-devices/scan（系统音频通道），API 分支恒空 §11-11） */
export async function scanDevices(
  kind: 'test' | 'playback',
  options: ApiRequestOptions = {}
): Promise<ScannedDeviceRowDto[]> {
  const dto = await request<ScannedDeviceRowDto[]>(
    'POST', kind === 'test' ? '/test-devices/scan' : '/playback-devices/scan',
    undefined, options
  )
  return dto ?? []
}
