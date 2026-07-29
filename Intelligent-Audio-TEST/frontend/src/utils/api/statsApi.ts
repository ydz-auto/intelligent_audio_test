/**
 * Stats (Home dashboard) API module
 */
import { request } from './http';

export const statsApi = {
  async getStats() {
    return request<{
      testCases: number;
      tasks: number;
      devices: number;
      audioFiles: number;
    }>('GET', '/home/stats');
  },

  async getStatsDetails() {
    return request<{
      testCases: {
        total: number;
        groups: number;
      };
      tasks: {
        total: number;
        completed: number;
        running: number;
        failed: number;
      };
      devices: {
        online: number;
        offline: number;
        total: number;
      };
      audioFiles: {
        total: number;
        dry: number;
        noise: number;
        prompt: number;
        duration: {
          total: number;
          dry: number;
          noise: number;
          prompt: number;
        };
      };
      playbackDevices: number;
      apis: {
        online: number;
        offline: number;
        total: number;
      };
      reports: number;
      dimensions: {
        total: number;
        withEndpoints: number;
        endpoints: number;
      };
      updatedAt?: string;
    }>('GET', '/home/stats/details');
  },

  async getStatsSummary() {
    return request<{
      recentTasks: Array<{
        id: number;
        name: string;
        type: string;
        status: string;
        total_cases: number;
        completed_cases: number;
        created_at: string;
      }>;
      topGroups: Array<{
        id: string;
        name: string;
        case_count: number;
      }>;
      deviceStatus: {
        online: number;
        offline: number;
      };
    }>('GET', '/home/stats/summary');
  }
};
