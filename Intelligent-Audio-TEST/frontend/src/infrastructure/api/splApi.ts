/**
 * SPL (Sound Pressure Level) API module
 * 出口契约：Domain（camelCase）；DTO 转换全部收敛在 adapters。
 * 查询参数/请求体显式 snake_case（per_page/calibration_status/device_id 等）。
 */
import { request, type RequestOptions } from '../http/client';
import { toPaginated } from '../adapters/commonAdapter';
import {
  toSPLMapping,
  toSPLStats,
  toSPLHistory,
  toSPLByDevice,
  toSPLQueryDto,
  toSPLUpsertDto,
  toSPLPlayToneDto,
  toSPLStopToneDto,
} from '../adapters/splAdapter';
import type { SplMappingItemDto, SplMappingListDto, SplHistoryDto, SplByDeviceDto, SplStatsDto } from '../dto/splDto';
import type {
  SPLMapping,
  SPLQuery,
  SPLStats,
  SPLHistoryList,
  SPLByDeviceList,
  SPLPlayToneInput,
  CalibrationData,
} from '../../domain/model/spl';

export const splApi = {
  /** SPL 映射分页列表 → Paginated<SPLMapping>（camelCase） */
  async getAll(params: SPLQuery = {}, options: RequestOptions = {}) {
    const dto = await request<SplMappingListDto>('GET', '/spl', null, {
      ...options,
      params: toSPLQueryDto(params),
    });
    return toPaginated(dto, toSPLMapping);
  },

  async getOne(id: string | number, options: RequestOptions = {}): Promise<SPLMapping> {
    const dto = await request<SplMappingItemDto>('GET', `/spl/${id}`, null, options);
    return toSPLMapping(dto);
  },

  /** 按设备的映射列表（非分页结构：items + total） */
  async getByDevice(deviceId: string | number, options: RequestOptions = {}): Promise<SPLByDeviceList> {
    const dto = await request<SplByDeviceDto>('GET', `/spl/by-device/${deviceId}`, null, options);
    return toSPLByDevice(dto);
  },

  /** 创建映射：camelCase → snake_case 请求体（返回 IdData） */
  async create(splData: Partial<SPLMapping> & { digital_gain?: number | null }, options: RequestOptions = {}) {
    return request('POST', '/spl', toSPLUpsertDto(splData, 'create'), options);
  },

  async update(id: string | number, splData: Partial<SPLMapping> & { digital_gain?: number | null }, options: RequestOptions = {}) {
    return request<void>('PUT', `/spl/${id}`, toSPLUpsertDto(splData, 'update'), options);
  },

  async delete(id: string | number, options: RequestOptions = {}) {
    return request<void>('DELETE', `/spl/${id}`, null, options);
  },

  /** 触发校准（返回校准数据） */
  async calibrate(id: string | number, options: RequestOptions = {}): Promise<CalibrationData> {
    return request<CalibrationData>('POST', `/spl/${id}/calibrate`, null, options);
  },

  /** 校准历史（items + total） */
  async getHistory(id: string | number, options: RequestOptions = {}): Promise<SPLHistoryList> {
    const dto = await request<SplHistoryDto>('GET', `/spl/${id}/history`, null, options);
    return toSPLHistory(dto);
  },

  /** 最新校准数据（calibration_data JSON blob 透传） */
  async getCalibrationData(id: string | number, options: RequestOptions = {}): Promise<CalibrationData> {
    return request<CalibrationData>('GET', `/spl/${id}/calibration-data`, null, options);
  },

  /** SPL 统计（total/calibrated/uncalibrated/associatedDevices） */
  async getStats(options: RequestOptions = {}): Promise<SPLStats> {
    const dto = await request<SplStatsDto>('GET', '/spl/stats', null, options);
    return toSPLStats(dto);
  },

  /** 播放测试音（请求体 gain_value/gain_offset/target_spl/unique_id） */
  async playTestTone(input: SPLPlayToneInput = {}, options: RequestOptions = {}) {
    return request('POST', '/spl/test-tone', toSPLPlayToneDto(input), options);
  },

  /** 停止测试音（请求体 unique_id） */
  async stopTestTone(uniqueId?: string | null, options: RequestOptions = {}) {
    return request('POST', '/spl/test-tone/stop', toSPLStopToneDto(uniqueId), options);
  }
};

export type { SPLMapping };
