/**
 * 设备相关展示标签 —— domain/constants
 * 与 reportLabels.ts 同模式：状态 → 中文标签映射集中管理
 */

/** 设备状态 → 中文标签（testing 为前端本地健康检查态，busy/error 为历史扩展态） */
export const DEVICE_STATUS_TEXT: Record<string, string> = {
  online: '在线',
  offline: '离线',
  testing: '测试中',
  busy: '忙碌',
  error: '错误'
} as const;
