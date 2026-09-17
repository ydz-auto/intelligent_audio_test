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

const _apiBase = import.meta.env.VITE_API_BASE_URL || '/api/v1'
const _wsBase = import.meta.env.VITE_WS_BASE_URL || ''

export const API_CONFIG = {
  baseUrl: _apiBase,
  wsBaseUrl: _wsBase
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
