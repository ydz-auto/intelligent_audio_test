/**
 * SPL (Sound Pressure Level) API module
 */
import type {
  SPLMapping,
  SPLQueryParams,
  CalibrationData,
  PaginatedResponse
} from '../../shared/types';
import { request, type RequestOptions } from './http';

export const splApi = {
  async getAll(params: SPLQueryParams = {}, options: RequestOptions = {}) {
    return request<PaginatedResponse<SPLMapping>>('GET', '/spl', null, { ...options, params });
  },

  async getOne(id: string | number) {
    return request<SPLMapping>('GET', `/spl/${id}`);
  },

  async getByDevice(deviceId: string | number, options: RequestOptions = {}) {
    return request<{items: SPLMapping[], total: number}>('GET', `/spl/by-device/${deviceId}`, null, options);
  },

  async create(splData: Partial<SPLMapping>) {
    return request<SPLMapping>('POST', '/spl', splData);
  },

  async update(id: string | number, splData: Partial<SPLMapping>) {
    return request<void>('PUT', `/spl/${id}`, splData);
  },

  async delete(id: string | number) {
    return request<void>('DELETE', `/spl/${id}`);
  },

  async calibrate(id: string | number, calibrationData: any) {
    return request<CalibrationData>('POST', `/spl/${id}/calibrate`, calibrationData);
  },

  async getHistory(id: string | number) {
    return request<PaginatedResponse<any>>('GET', `/spl/${id}/history`);
  },

  async getCalibrationData(id: string | number) {
    return request<any>('GET', `/spl/${id}/calibration-data`);
  },

  async getStats() {
    return request<{
      total: number;
      calibrated: number;
      uncalibrated: number;
      associatedDevices: number;
    }>('GET', '/spl/stats');
  },

  async stopTestTone(uniqueId?: string | null) {
    return request<any>('POST', '/spl/test-tone/stop', { unique_id: uniqueId ?? undefined });
  }
};
