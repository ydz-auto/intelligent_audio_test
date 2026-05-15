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
  baseUrl: 'http://localhost:5000/api/v1',
  wsBaseUrl: 'http://localhost:5000'
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
