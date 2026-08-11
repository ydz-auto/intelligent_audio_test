import type { PlaybackDevice } from '../../shared/types';

export interface TestDevice {
  id: string | number;
  name: string;
  model?: string;
  category?: string;
  keywords?: string;
  status: 'online' | 'offline' | 'testing' | 'busy' | 'error';
  lastOnlineAt?: string;
  needs_prompt_audio?: boolean;
  supportedAlgorithms?: string[];
  [key: string]: any;
}

export interface APIDevice {
  id: string | number;
  name: string;
  model?: string;
  category?: string;
  vendor?: string;
  status: 'online' | 'offline' | 'testing' | 'busy' | 'error';
  endpoints?: { endpoint: string; url?: string }[];
  algorithm_type?: string;
  algorithmType?: string;
  [key: string]: any;
}

export type DeviceUnion = TestDevice | APIDevice | PlaybackDevice;

export interface ListResponse<T> {
  items?: T[];
  pages?: number;
  total?: number;
}

export const tabs = [
  { type: 'test', label: '测试设备管理', icon: 'fas fa-microphone' },
  { type: 'api', label: '测试API管理', icon: 'fas fa-exchange-alt' },
  { type: 'playback', label: '播放设备管理', icon: 'fas fa-headphones' }
];

export const deviceStatusText: Record<string, string> = {
  online: '在线',
  offline: '离线',
  testing: '测试中',
  busy: '忙碌',
  error: '错误'
};
