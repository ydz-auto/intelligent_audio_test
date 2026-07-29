/**
 * Devices API module
 */
import { request, type RequestOptions } from './http';

export const devicesApi = {
  async getAll(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request('GET', '/test-devices', null, { ...options, params });
  },

  async getOne(id: string | number) {
    return request('GET', `/test-devices/${id}`);
  },

  async create(deviceData: any, options: RequestOptions = {}) {
    return request('POST', '/test-devices', deviceData, options);
  },

  async update(id: string | number, deviceData: any, options: RequestOptions = {}) {
    return request('PUT', `/test-devices/${id}`, deviceData, options);
  },

  async delete(id: string | number) {
    return request('DELETE', `/test-devices/${id}`);
  },

  async healthCheck(deviceIds: (string | number)[] = []) {
    return request('POST', '/test-devices/health-check', { deviceIds: deviceIds });
  },

  async getStatuses() {
    return request('GET', '/test-devices/status');
  },

  async scan() {
    return request('POST', '/test-devices/scan');
  },

  async test(id: string | number) {
    return request('POST', `/test-devices/${id}/test`);
  },

  async stopTest(id: string | number) {
    return request('POST', `/test-devices/${id}/stop-test`);
  },

  async getAvailableSerials() {
    return request('GET', '/test-devices/serials');
  },

  async getDriverKeywords() {
    return request('GET', '/test-devices/driver-keywords');
  },

  async getPlaybackDevices(options: RequestOptions = {}) {
    return request('GET', '/playback-devices', null, options);
  }
};
