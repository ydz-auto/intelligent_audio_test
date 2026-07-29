/**
 * Playback devices API module
 */
import { request, type RequestOptions } from './http';

export const playbackApi = {
  async getAll(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request('GET', '/playback-devices', null, { ...options, params });
  },

  async getOne(id: string | number) {
    return request('GET', `/playback-devices/${id}`);
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

  async getStatuses() {
    return request('GET', '/playback-devices/status');
  },

  async scan() {
    return request('POST', '/playback-devices/scan');
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
