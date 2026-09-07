/**
 * Devices API module
 *
 * 出口契约：camelCase Domain（domain/model/device.ts）。
 * 请求体/查询参数：显式 snake_case（per_page 等，APIModel 双兼容）。
 */
import { request, type RequestOptions } from '../http/client';
import { APP_CONFIG } from '../../utils/config';
import type { PaginatedDto } from '../dto/common';
import type {
  DeviceItemDto,
  DeviceListDto,
  DeviceStatusItemDto,
  DeviceScanItemDto,
  PlaybackDeviceListDto,
  ScannedDeviceDto,
} from '../dto/deviceDto';
import type {
  Device,
  DeviceStatusInfo,
  DeviceTestData,
  DriverKeyword,
  PlaybackDevice,
  ScannedDevice,
} from '../../domain/model/device';
import type { Paginated } from '../../domain/model/common';
import {
  toDevice,
  toDevicePage,
  toDeviceList,
  toDeviceStatusList,
  toScannedDeviceList,
  toDeviceTestData,
  toPlaybackDevicePage,
  toPlaybackDeviceList,
  toDeviceUpsertDto,
  normalizeScannedDeviceList,
} from '../adapters/deviceAdapter';

/** 设备列表查询参数（snake_case 发往后端） */
export interface DeviceListQueryParams {
  page?: number
  per_page?: number
  keyword?: string
  status?: string
  device_type?: string
  algorithm_type?: string
}

/** 全量获取默认分页参数（避免魔法值；首页 + 大批量，用于"取全部"场景） */
export const BATCH_LIST_PARAMS: DeviceListQueryParams = { page: 1, per_page: APP_CONFIG.defaultBatchPageSize }

/** 播放设备列表查询参数（camelCase 域契约；snake_case 化在 Infrastructure 内部完成） */
export interface PlaybackDeviceListQuery {
  page?: number
  perPage?: number
  keyword?: string
  status?: string
  deviceType?: string
  algorithmType?: string
}

/** camelCase 播放设备查询 → snake_case HTTP query（后端 DeviceListQueryParams 契约） */
function toDeviceListQueryDto(query: PlaybackDeviceListQuery): DeviceListQueryParams {
  const params: DeviceListQueryParams = {}
  if (query.page !== undefined) params.page = query.page
  if (query.perPage !== undefined) params.per_page = query.perPage
  if (query.keyword !== undefined) params.keyword = query.keyword
  if (query.status !== undefined) params.status = query.status
  if (query.deviceType !== undefined) params.device_type = query.deviceType
  if (query.algorithmType !== undefined) params.algorithm_type = query.algorithmType
  return params
}

export const devicesApi = {
  /** 设备分页列表（PaginatedData[DeviceItem] → Paginated<Device>） */
  async getAll(params: DeviceListQueryParams = {}, options: RequestOptions = {}): Promise<Paginated<Device>> {
    const dto = await request<PaginatedDto<DeviceItemDto> | DeviceItemDto[]>(
      'GET', '/test-devices', null, { ...options, params }
    );
    return toDevicePage(dto as PaginatedDto<DeviceItemDto>);
  },

  /** 设备数组兜底（返回扁平数组） */
  async getAllFlat(params: DeviceListQueryParams = {}, options: RequestOptions = {}): Promise<Device[]> {
    const dto = await request<PaginatedDto<DeviceItemDto> | DeviceItemDto[]>(
      'GET', '/test-devices', null, { ...options, params }
    );
    return toDeviceList(dto);
  },

  /** 设备详情 */
  async getOne(id: string | number, options: RequestOptions = {}): Promise<Device> {
    const dto = await request<DeviceItemDto>('GET', `/test-devices/${id}`, null, options);
    return toDevice(dto);
  },

  /** 创建设备（后端双兼容 snake_case/camelCase，此处显式 snake_case） */
  async create(deviceData: Partial<Device>, options: RequestOptions = {}) {
    return request('POST', '/test-devices', toDeviceUpsertDto(deviceData), options);
  },

  /** 更新设备 */
  async update(id: string | number, deviceData: Partial<Device>, options: RequestOptions = {}) {
    return request('PUT', `/test-devices/${id}`, toDeviceUpsertDto(deviceData), options);
  },

  async delete(id: string | number) {
    return request<void>('DELETE', `/test-devices/${id}`);
  },

  /** 批量健康检查（请求体 device_ids，响应 DeviceHealthItem[]） */
  async healthCheck(deviceIds: (string | number)[] = []): Promise<DeviceStatusInfo[]> {
    const dto = await request<DeviceStatusItemDto[]>(
      'POST', '/test-devices/health-check', { device_ids: deviceIds }
    );
    return toDeviceStatusList(dto);
  },

  /** 批量获取设备状态（轮询降级，响应 { items, total }） */
  async getStatuses(ids?: (string | number)[], options: RequestOptions = {}): Promise<DeviceStatusInfo[]> {
    const dto = await request<{ items: DeviceStatusItemDto[] } | DeviceStatusItemDto[]>(
      'GET', '/test-devices/status', null, { ...options, params: ids ? { ids: ids.join(',') } : {} }
    );
    const items = Array.isArray(dto) ? dto : (dto?.items ?? []);
    return toDeviceStatusList(items);
  },

  /** 扫描物理设备 */
  async scan(options: RequestOptions = {}): Promise<ScannedDevice[]> {
    const dto = await request<DeviceScanItemDto[]>('POST', '/test-devices/scan', null, options);
    return toScannedDeviceList(dto);
  },

  /** 测试设备（唤醒） */
  async test(id: string | number): Promise<DeviceTestData> {
    const dto = await request<DeviceTestDataDtoShape>('POST', `/test-devices/${id}/test`);
    return toDeviceTestData(dto);
  },

  async stopTest(id: string | number) {
    return request('POST', `/test-devices/${id}/stop-test`);
  },

  /** 可用设备序列号详情列表（自动填充；宽松 DTO → Domain ScannedDevice） */
  async getAvailableSerials(options: RequestOptions = {}): Promise<ScannedDevice[]> {
    const dto = await request<ScannedDeviceDto[] | null | undefined>('GET', '/test-devices/serials', null, options);
    return normalizeScannedDeviceList(dto);
  },

  /** 已注册驱动关键字（宽松 DTO → Domain DriverKeyword[]） */
  async getDriverKeywords(options: RequestOptions = {}): Promise<DriverKeyword[]> {
    const dto = await request<unknown>('GET', '/test-devices/driver-keywords', null, options);
    return toDriverKeywords(dto);
  },

  /**
   * 播放设备分页列表（分页包装 → Paginated<PlaybackDevice>）
   * 入参为 camelCase 查询对象（PlaybackDeviceListQuery），Infrastructure 内部转 snake_case 发往后端
   */
  async getPlaybackDevices(params: PlaybackDeviceListQuery = {}, options: RequestOptions = {}): Promise<Paginated<PlaybackDevice>> {
    const dto = await request<PaginatedDto<PlaybackDeviceListDto['items'][number]>>(
      'GET', '/playback-devices', null, { ...options, params: toDeviceListQueryDto(params) }
    );
    return toPlaybackDevicePage({ items: (dto as any)?.items ?? [], ...(dto as any) } as PaginatedDto<PlaybackDeviceListDto['items'][number]>);
  },

  /** 播放设备数组兜底 */
  async getPlaybackDevicesFlat(params: PlaybackDeviceListQuery = {}, options: RequestOptions = {}): Promise<PlaybackDevice[]> {
    const dto = await request<PaginatedDto<PlaybackDeviceListDto['items'][number]> | PlaybackDeviceListDto['items'][number][]>(
      'GET', '/playback-devices', null, { ...options, params: toDeviceListQueryDto(params) }
    );
    return toPlaybackDeviceList(dto);
  },
};

/** DeviceTestData DTO 形状（局部别名，避免直接暴露 DTO 命名冲突） */
type DeviceTestDataDtoShape = { id: number | string; status: string; wakeup_command?: string };

/** DriverKeyword DTO 形状（局部别名，避免直接暴露 DTO 命名冲突） */
type DriverKeywordDtoShape = { name?: string; system?: string; keywords?: string[] };

/**
 * 驱动关键字响应 → Domain DriverKeyword[]
 * 兼容裸数组 / { data: [] } / { items: [] } 三种包裹形态（后端各环境可能不同）
 */
function toDriverKeywords(response: unknown): DriverKeyword[] {
  const envelope = response as
    | DriverKeywordDtoShape[]
    | { data?: DriverKeywordDtoShape[]; items?: DriverKeywordDtoShape[] }
    | null
    | undefined
  const list = Array.isArray(envelope)
    ? envelope
    : Array.isArray(envelope?.data)
      ? envelope.data!
      : Array.isArray(envelope?.items)
        ? envelope.items!
        : []
  return list.map(({ name, system, keywords }) => ({
    name: name ?? '',
    system: system ?? '',
    keywords: keywords ?? [],
  }))
}
