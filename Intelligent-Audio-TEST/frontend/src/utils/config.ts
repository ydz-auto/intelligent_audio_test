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
  // 使用相对路径，由 vite.config.ts 的 server.proxy 转发到后端 api_gateway:6000
  // 避免跨端口 CORS 问题；WebSocket 也走同源代理
  baseUrl: '/api/v1',
  wsBaseUrl: ''  // 同源，Socket.IO 由 vite 代理 /socket.io
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
