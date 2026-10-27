/**
 * 设备管理页 API（infrastructure/api 层；接线 INT-644）。
 * 经 client.ts 统一 fetch 封装（baseURL /api/v1 → dev 代理 gateway:5000；INT-605），
 * 端点对照 api_gateway/routes/device_bp.py（/test-devices）、playback_bp.py
 * （/playback-devices）、api_bp.py（/apis）实测契约；响应 snake_case DTO 经
 * infrastructure/adapters 转 camelCase Domain（snake→camel 唯一转换层，红线③）。
 * 列表端点统一 PaginatedData { items,total,page,per_page,pages }：本页全量拉取
 * （per_page=1000，对照 Vue BATCH_LIST_PARAMS.defaultBatchPageSize），
 * 筛选/分页由 feature 层前端完成（接线前 mock 同口径）。
 * 实验室 CRUD 走 INT-655 真实端点 /laboratories（laboratory_bp.py 实测契约）；
 * occupied 后端 DTO 未暴露（§11-26）——以本地瞬时覆盖兜底（见 setDeviceOccupied）。
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
import type {
  DeviceExportFormat,
  DeviceImportResult,
} from '@/domain/models/deviceImportExport'
import { request, type ApiRequestOptions } from '@/infrastructure/api/client'
import { ApiError } from '@/infrastructure/api/api-error'
import type { TestDeviceItemDto } from '@/infrastructure/dto/test-device.dto'
import type { PlaybackDeviceItemDto } from '@/infrastructure/dto/playback-device.dto'
import type { ApiItemDto } from '@/infrastructure/dto/apis.dto'
import type { DeviceGroupItemDto } from '@/infrastructure/dto/device-group.dto'
import type { LaboratoryDto } from '@/infrastructure/dto/laboratory.dto'
import type {
  AlarmDto,
  AlarmRuleDto,
  AlarmStatsDto,
  DeviceStatusHistoryDto,
} from '@/infrastructure/dto/alarm.dto'
import { testDeviceFromDto } from '@/infrastructure/adapters/testDeviceAdapter'
import { playbackDeviceFromDto } from '@/infrastructure/adapters/playbackDeviceAdapter'
import { apiDeviceFromDto } from '@/infrastructure/adapters/apiDeviceAdapter'
import { extractEndpointApiKeys } from '@/infrastructure/adapters/api-keys'
import { deviceGroupFromDto, deviceGroupsToTree } from '@/infrastructure/adapters/deviceGroupAdapter'
import { laboratoryFromDto } from '@/infrastructure/adapters/laboratoryAdapter'
import { deviceImportResultFromDto } from '@/infrastructure/adapters/deviceImportExportAdapter'
import type { DeviceImportResultDto } from '@/infrastructure/dto/device-import-export.dto'
import {
  alarmFromDto,
  alarmRuleFromDto,
  statusEventFromDto,
} from '@/infrastructure/adapters/alarmAdapter'

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

/** 实验室列表（§6.26；GET /laboratories——INT-655 真实端点，全量拉取前端分页） */
export async function fetchLaboratories(options: ApiRequestOptions = {}): Promise<Laboratory[]> {
  const dto = await request<PaginatedDto<LaboratoryDto>>(
    'GET', '/laboratories', undefined, { ...options, params: LIST_ALL_PARAMS }
  )
  return (dto?.items ?? []).map(laboratoryFromDto)
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
  // INT-1437 密钥池：textarea 草稿拆行转 api_keys 落库；空/留空不传（后端保留既有池，不误清空）
  const keys = extractEndpointApiKeys(ep)
  if (keys.length > 0) dto.api_keys = keys
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
  pick('description', 'description')
  pick('meta', 'meta')
  // INT-1800：协议 / 流式性两列（`device_type` 已退役，本层永不发送）；
  // protocol 为空表示调用方没选，不下发该键，由后端写侧缺省 http
  if (data.protocol != null) dto.protocol = data.protocol
  if (data.streaming !== undefined) dto.streaming = data.streaming
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

/** 新增测试设备（§6.2；POST /test-devices —— 201 + data.id；INT-2074 扫描登记透出新 id 供勾选） */
export async function createTestDevice(
  input: Partial<TestDevice>,
  options: ApiRequestOptions = {}
): Promise<{ success: boolean; id?: number | null }> {
  const dto = await request<{ id?: number | null }>('POST', '/test-devices', toTestDeviceUpsertDto(input), options)
  return { success: true, id: dto?.id ?? null }
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

/** 新增播放设备（§6.2；POST /playback-devices —— 201 + data.id；INT-2074 扫描登记透出新 id） */
export async function createPlaybackDevice(
  input: Partial<PlaybackDevice>,
  options: ApiRequestOptions = {}
): Promise<{ success: boolean; id?: number | null }> {
  const dto = await request<{ id?: number | null }>('POST', '/playback-devices', toPlaybackDeviceUpsertDto(input), options)
  return { success: true, id: dto?.id ?? null }
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

/** 设备控制操作（§3.4.1；POST /test-devices/{id}/{action}；health_check 走批量端点）
 *  P2-2：操作参数按 device_command_service.control 契约放 body.params
 *  （install_app: {file_path, package_name}；uninstall_app: {package_name}）。
 *  P2-4：后端无端点的动作（播放设备 restart/reset-config/mute/unmute 等 UX 视觉稿动作）返回
 *  success:false + message，不再本地伪造成功；调用方据此提示并禁用入口。 */
export async function controlDevice(
  id: number,
  action: string,
  params: Record<string, unknown> = {},
  options: ApiRequestOptions = {}
): Promise<{ success: boolean; action?: string; id?: number; message?: string }> {
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
    // 后端未提供该操作端点：不产生请求、不伪造成功（入口在 device-row-actions 中禁用 + Tooltip）
    return { success: false, action, id, message: '后端未提供该操作（待 INT-1573）' }
  }
  const body = Object.keys(params).length > 0 ? { params } : undefined
  await request('POST', `/test-devices/${id}/${path}`, body, options)
  return { success: true, action, id }
}

/** 「测试中」占用态：本地瞬时覆盖 + 真实测试派发端点（INT-487 §3.4 注③：测试/停止测试）
 *  P3-b 返修：请求失败回滚本地覆盖（恢复原值），否则设备会一直显示「测试中」直到整页重载。 */
export async function setDeviceOccupied(
  kind: 'test' | 'playback' | 'api',
  id: number,
  occupied: boolean,
  options: ApiRequestOptions = {}
): Promise<{ success: boolean }> {
  const overrides = occupiedOverrides.get(kind) ?? new Map<number, boolean>()
  const previous = overrides.get(id)
  overrides.set(id, occupied)
  occupiedOverrides.set(kind, overrides)
  const base = kind === 'test' ? '/test-devices' : kind === 'playback' ? '/playback-devices' : '/apis'
  try {
    await request('POST', `${base}/${id}/${occupied ? 'test' : 'stop-test'}`, undefined, options)
  } catch (error) {
    if (previous === undefined) overrides.delete(id)
    else overrides.set(id, previous)
    throw error
  }
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

/* ==================== 实验室（§6.26；INT-655 laboratory_bp.py /laboratories 真实契约） ==================== */

/** 实验室可写字段（LaboratoryCreateSchema/LaboratoryUpdateSchema 字段集，camelCase → snake_case） */
type LaboratoryUpsertInput = Partial<
  Omit<
    Laboratory,
    'id' | 'createdAt' | 'updatedAt' | 'deviceCount' | 'playbackDeviceCount' | 'testCaseCount'
  >
>

function toLaboratoryUpsertDto(data: LaboratoryUpsertInput): Record<string, unknown> {
  const dto: Record<string, unknown> = {}
  const pick = <K extends keyof LaboratoryUpsertInput>(key: K, snake: string) => {
    const value = data[key]
    if (value !== undefined) dto[snake] = value
  }
  pick('code', 'code')
  pick('name', 'name')
  pick('building', 'building')
  pick('floor', 'floor')
  pick('roomNumber', 'room_number')
  pick('description', 'description')
  pick('status', 'status')
  return dto
}

/** 新建实验室（§6.26；POST /laboratories——201 + data.id；code 冲突 409） */
export async function createLaboratory(
  input: LaboratoryUpsertInput
): Promise<{ success: boolean }> {
  await request('POST', '/laboratories', toLaboratoryUpsertDto(input))
  return { success: true }
}

/** 删除实验室（§6.26；DELETE /laboratories/{id}——关联资源非空时后端 409，文案经 deleteGuard 透出） */
export async function deleteLaboratory(id: number): Promise<{ success: boolean; message?: string }> {
  return deleteGuard(() => request('DELETE', `/laboratories/${id}`, undefined))
}

/** 编辑实验室（§6.26；PUT /laboratories/{id}——P3-21 返修补「编辑」） */
export async function updateLaboratory(
  id: number,
  patch: LaboratoryUpsertInput
): Promise<{ success: boolean }> {
  await request('PUT', `/laboratories/${id}`, toLaboratoryUpsertDto(patch))
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

/* ==================== 导入导出（§3.3/§4.5；INT-816 三资源端点） ==================== */

/**
 * 页签 → 资源端点与导出文件名前缀（INT-816 device_import_export_service.py
 * `_ResourceSpec.resource/export_prefix` 实测契约）。
 * 与 features/devices 的 DevicesTabKey 同构；infrastructure 不反向依赖 features，故本地定义。
 */
export type DeviceResourceTab = 'test' | 'playback' | 'api'

const RESOURCE_ENDPOINTS: Record<
  DeviceResourceTab,
  { path: string; exportPrefix: string }
> = {
  test: { path: '/test-devices', exportPrefix: 'test_devices' },
  playback: { path: '/playback-devices', exportPrefix: 'playback_devices' },
  api: { path: '/apis', exportPrefix: 'apis' },
}

export interface DeviceExportOptions {
  /** json=默认；excel 对应后端 xlsx 文件流 */
  format?: DeviceExportFormat
  /** 导出范围非「全部」时的 id 集；空数组按不传处理（避免误导出全量） */
  ids?: number[]
}

/** 导出文件的浏览器侧文件名（后端 Content-Disposition 同名口径：`<prefix>_YYYYmmdd_HHMMSS.<ext>`） */
export function buildDeviceExportFilename(
  tab: DeviceResourceTab,
  format: DeviceExportFormat,
  now: Date = new Date()
): string {
  const pad = (value: number) => String(value).padStart(2, '0')
  const stamp =
    `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}` +
    `_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
  return `${RESOURCE_ENDPOINTS[tab].exportPrefix}_${stamp}.${format === 'excel' ? 'xlsx' : 'json'}`
}

/**
 * 导出资源（GET /{resource}/export?format=&ids=，文件流）。
 * 响应是文件流（不走 `{code,message,data}` 信封），以 blob 取流；
 * client.ts 不解包、不解析 JSON，避免把 XLSX 当 JSON 读坏。
 * 文件名按后端命名口径在前端生成——client.ts 不暴露响应头（基座文件，
 * 本卡不改），Content-Disposition 仍可在 Network 面板核对。
 */
export async function exportDeviceResource(
  tab: DeviceResourceTab,
  input: DeviceExportOptions = {},
  options: ApiRequestOptions = {}
): Promise<{ blob: Blob; filename: string }> {
  const format = input.format ?? 'json'
  const ids = input.ids && input.ids.length > 0 ? input.ids.join(',') : undefined
  const blob = await request<Blob>('GET', `${RESOURCE_ENDPOINTS[tab].path}/export`, undefined, {
    ...options,
    params: { format, ids },
    responseType: 'blob',
    unwrapResponse: false,
  })
  return { blob, filename: buildDeviceExportFilename(tab, format) }
}

/**
 * 导入资源（POST /{resource}/import，multipart 字段名 `file`；JSON/CSV/XLSX）。
 * 返回计数报告（逐行提交、不整批回滚：部分成功是后端既定口径）。
 * 无文件 / 空文件 / 不支持格式由后端 400，ApiError 透出中文 message。
 */
export async function importDeviceResource(
  tab: DeviceResourceTab,
  file: File,
  options: ApiRequestOptions = {}
): Promise<DeviceImportResult> {
  const formData = new FormData()
  formData.append('file', file)
  const dto = await request<DeviceImportResultDto>(
    'POST', `${RESOURCE_ENDPOINTS[tab].path}/import`, formData, options
  )
  return deviceImportResultFromDto(dto)
}
