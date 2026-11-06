/**
 * 声压级映射管理页状态类型（features/spl-mapping）。
 * §4.1 validateSearch 语义的本地筛选状态（尚未 URL 化；数据来自真实接口）。
 */

import type { SplDeviceType } from '@/domain/models/splMapping'

export type SplDomain = 'device' | 'digital'

export type CalibrationFilter = 'all' | 'calibrated' | 'uncalibrated'

/** 双口径共用筛选（§4.1.1：搜索 + 校准状态 + 关联设备/关联 API） */
export interface SplListFilters {
  search: string
  calibrationStatus: CalibrationFilter
  /** 物理域：关联播放设备 id */
  deviceId: string | null
  /** 数字域：关联 API id */
  apiId: string | null
}

/** 物理域行操作弹窗分派态（§4.2.1 + §6.7-6.9） */
export type DeviceSplDialogState =
  | { kind: 'create' }
  | { kind: 'edit'; mappingId: number }
  | { kind: 'detail'; mappingId: number }
  | { kind: 'history'; mappingId: number }

/** 数字域行操作弹窗分派态（§4.3.1 + §6.10-6.12） */
export type DigitalSplDialogState =
  | { kind: 'create' }
  | { kind: 'edit'; mappingId: number }
  | { kind: 'calibrate'; mappingId: number }
  | { kind: 'detail'; mappingId: number }

/** 批量 SPL 配置弹窗态（§6.22） */
export type BatchSplDialogState = {
  mappingIds: number[]
  count: number
}

/** 设备类型筛选值（物理域 facet） */
export type DeviceTypeFilter = SplDeviceType | null
