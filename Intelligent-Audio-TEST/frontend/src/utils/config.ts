/**
 * Project Configuration
 * This file contains all project-wide configuration settings
 */

export const STATIC_CONFIG = {
  basePath: '/static/',
  audioPath: '/audios/',
  imagePath: '/images/',
  logPath: '/logs/'
} as const;

export const API_CONFIG = {
  // 使用相对路径，开发环境走 Vite 代理，生产环境走 Nginx 反向代理
  baseUrl: '/api/v1',
  wsBaseUrl: ''
} as const;

export const APP_CONFIG = {
  appName: 'Task Manager',
  appVersion: '1.0.0',
  defaultPageSize: 10,
  supportedAudioFormats: ['mp3', 'wav', 'flac', 'aac', 'm4a', 'ogg', 'wma', 'alac', 'opus']
} as const;

export const LOG_CONFIG = {
  enabled: true,
  level: 'debug' as LogLevel,
  showTimestamp: true,
  disableInProduction: true
};

export type LogLevel = 'debug' | 'info' | 'warning' | 'error';
