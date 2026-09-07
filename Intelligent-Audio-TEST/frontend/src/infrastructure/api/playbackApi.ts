/**
 * Playback devices API module
 *
 * 出口契约：camelCase Domain（domain/model/device.ts）。
 * DTO → Domain 转换在 api 层内部完成，业务层只消费领域类型。
 */
import { request, type RequestOptions } from '../http/client';
import { toPlaybackDevice, toPlaybackDeviceList, toPlaybackScannedDeviceList } from '../adapters/deviceAdapter';
import type { PaginatedDto } from '../dto/common';
import type { PlaybackDeviceItemDto, PlaybackScanItemDto } from '../dto/deviceDto';
import type { PlaybackDevice, ScannedDevice } from '../../domain/model/device';

export const playbackApi = {
  /** 播放设备列表（兼容分页/数组响应 → 一律展平为 Domain 数组） */
  async getAll(params: Record<string, any> = {}, options: RequestOptions = {}): Promise<PlaybackDevice[]> {
    const dto = await request<PaginatedDto<PlaybackDeviceItemDto> | PlaybackDeviceItemDto[]>(
      'GET', '/playback-devices', null, { ...options, params }
    );
    return toPlaybackDeviceList(dto);
  },

  /** 播放设备详情（DTO → Domain） */
  async getOne(id: string | number): Promise<PlaybackDevice> {
    const dto = await request<PlaybackDeviceItemDto>('GET', `/playback-devices/${id}`);
    return toPlaybackDevice(dto);
  },

  async create(deviceData: any, options: RequestOptions = {}) {
    return request('POST', '/playback-devices', deviceData, options);
  },

  async update(id: string | number, deviceData: any, options: RequestOptions = {}) {
    return request('PUT', `/playback-devices/${id}`, deviceData, options);
  },

  async delete(id: string | number) {
    return request('DELETE', `/playback-devices/${id}`);
  },

  async scan(): Promise<ScannedDevice[]> {
    const raw = await request<any>('POST', '/playback-devices/scan');
    // 兼容多种响应包装：数组 / { data: [...] } / { devices: [...] }
    let dtos: PlaybackScanItemDto[] = [];
    if (Array.isArray(raw)) {
      dtos = raw as PlaybackScanItemDto[];
    } else if (raw && Array.isArray(raw.data)) {
      dtos = raw.data;
    } else if (raw && Array.isArray(raw.devices)) {
      dtos = raw.devices;
    } else if (raw && raw.data && Array.isArray(raw.data.devices)) {
      dtos = raw.data.devices;
    }
    return toPlaybackScannedDeviceList(dtos);
  },

  async associateSpl(id: string | number, splMappingId: string | number) {
    return request('POST', `/playback-devices/${id}/associate-spl`, { splMappingId: splMappingId });
  },

  async test(id: string | number) {
    return request('POST', `/playback-devices/${id}/test`);
  },

  async stopTest(id: string | number) {
    return request('POST', `/playback-devices/${id}/stop-test`);
  },

  async checkStatus() {
    return request('GET', '/playback-devices/check-status');
  }
};
