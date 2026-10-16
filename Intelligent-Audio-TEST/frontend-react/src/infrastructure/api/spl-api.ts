/**
 * 物理域 SPL 映射 API 桩（infrastructure 层；16_设备域.md §10 组件树落位）。
 * 红线④：全部返回 mock 常量（spl-mock），接线时替换为真实请求：
 *   GET    /api/v1/spl                            列表（keyword/calibration_status/device_id/page/per_page）
 *   GET    /api/v1/spl/stats                       统计（SplStatsData 四字段）
 *   GET    /api/v1/spl/{id}                        详情
 *   GET    /api/v1/spl/{id}/history                校准历史（SplHistoryItem）
 *   POST   /api/v1/spl                             新增映射
 *   PUT    /api/v1/spl/{id}                        编辑映射（距离/频率变更重置校准，§6.7）
 *   DELETE /api/v1/spl/{id}                        删除映射
 *   POST   /api/v1/spl/{id}/calibrate              执行校准（现状后端为模拟校准，§11-12）
 *   GET    /api/v1/playback-devices                关联播放设备 facet 选项
 */
import type {
  PlaybackDeviceRef,
  SplHistoryItem,
  SplMapping,
  SplStats,
} from '@/domain/models/splMapping'
import {
  MOCK_PLAYBACK_DEVICE_REFS,
  MOCK_SPL_HISTORY,
  MOCK_SPL_MAPPINGS,
  MOCK_SPL_STATS,
} from '../mock/spl-mock'

/** 模拟网络延迟（视觉稿演示用；接线后删除） */
function mockLatency<T>(value: T, ms = 180): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms))
}

/** mock 内存库（页面内增删改操作在运行时可变） */
let splStore: SplMapping[] = [...MOCK_SPL_MAPPINGS]
let historyStore: SplHistoryItem[] = [...MOCK_SPL_HISTORY]

/** 新 id（mock 阶段自增；接线后走后端自增） */
let nextSplId = 1000
function freshId(): number {
  nextSplId += 1
  return nextSplId
}

/** 当前 mock 内存库（供 feature 内读取；接线后删除） */
export function peekSplMappings(): SplMapping[] {
  return splStore
}

/** 列表（§4.2；GET /spl；mock 阶段全量返回，前端过滤分页） */
export async function fetchSplMappings(): Promise<SplMapping[]> {
  // TODO(API 接线): GET /api/v1/spl
  return mockLatency([...splStore])
}

/** 统计（§4.1.2；GET /spl/stats，SplStatsData） */
export async function fetchSplStats(): Promise<SplStats> {
  // TODO(API 接线): GET /api/v1/spl/stats
  const calibrated = splStore.filter((m) => m.calibrationStatus === 'calibrated').length
  return mockLatency({
    ...MOCK_SPL_STATS,
    total: splStore.length,
    calibrated,
    uncalibrated: splStore.length - calibrated,
    associatedDevices: new Set(splStore.map((m) => m.deviceId).filter((id): id is number => id != null)).size,
  })
}

/** 关联播放设备 facet 选项（§4.1.1；GET /playback-devices） */
export async function fetchPlaybackDeviceRefs(): Promise<PlaybackDeviceRef[]> {
  // TODO(API 接线): GET /api/v1/playback-devices
  return mockLatency([...MOCK_PLAYBACK_DEVICE_REFS])
}

/** 校准历史（§6.9；GET /spl/{id}/history） */
export async function fetchSplHistory(_id: number): Promise<SplHistoryItem[]> {
  // TODO(API 接线): GET /api/v1/spl/{id}/history
  return mockLatency([...historyStore])
}

/** 新增映射（§6.7；POST /spl；deviceName/deviceModel 由关联播放设备派生） */
export async function createSplMapping(
  input: Omit<SplMapping, 'id' | 'createdAt' | 'updatedAt' | 'deviceName' | 'deviceModel'>
): Promise<SplMapping> {
  // TODO(API 接线): POST /api/v1/spl
  const now = new Date().toISOString()
  const device = MOCK_PLAYBACK_DEVICE_REFS.find((d) => d.id === input.deviceId)
  const mapping: SplMapping = {
    ...input,
    deviceName: device?.name ?? null,
    deviceModel: device?.model ?? null,
    id: freshId(),
    createdAt: now,
    updatedAt: now,
  }
  splStore = [mapping, ...splStore]
  return mockLatency(mapping, 160)
}

/** 编辑映射（§6.7；PUT /spl/{id}；距离/频率变更重置为未校准在 feature 内处理） */
export async function updateSplMapping(
  id: number,
  patch: Partial<SplMapping>
): Promise<SplMapping | undefined> {
  // TODO(API 接线): PUT /api/v1/spl/{id}
  const target = splStore.find((m) => m.id === id)
  if (!target) return mockLatency(undefined, 80)
  const updated: SplMapping = {
    ...target,
    ...patch,
    updatedAt: new Date().toISOString(),
  }
  splStore = splStore.map((m) => (m.id === id ? updated : m))
  return mockLatency(updated, 120)
}

/** 删除映射（§4.2.1；DELETE /spl/{id}） */
export async function deleteSplMapping(
  id: number
): Promise<{ success: boolean; message?: string }> {
  // TODO(API 接线): DELETE /api/v1/spl/{id}
  const target = splStore.find((m) => m.id === id)
  if (!target) return mockLatency({ success: false, message: '映射不存在' }, 80)
  splStore = splStore.filter((m) => m.id !== id)
  return mockLatency({ success: true }, 120)
}

/** 执行校准（§4.2.1；POST /spl/{id}/calibrate；现状后端为模拟校准 §11-12） */
export async function calibrateSplMapping(
  id: number,
  points: Array<{ spl: number; gainOffset: number }>
): Promise<{ success: boolean; calibrationStatus: string; message?: string }> {
  // TODO(API 接线): POST /api/v1/spl/{id}/calibrate
  const target = splStore.find((m) => m.id === id)
  if (!target) return mockLatency({ success: false, calibrationStatus: 'uncalibrated', message: '映射不存在' }, 80)
  const updated: SplMapping = {
    ...target,
    calibrationStatus: 'calibrated',
    calibrationData: {
      points: points.map((p) => ({
        spl: p.spl,
        gainOffset: p.gainOffset,
        digitalGain: p.gainOffset,
        baseLevel: -30,
        finalLevel: -30 + (p.gainOffset ?? 0),
      })),
    },
    updatedAt: new Date().toISOString(),
  }
  splStore = splStore.map((m) => (m.id === id ? updated : m))
  historyStore = [
    {
      id: freshId(),
      calibrationData: updated.calibrationData,
      distance: updated.distance,
      testFrequency: updated.testFrequency,
      createdAt: updated.updatedAt,
    },
    ...historyStore,
  ]
  return mockLatency({ success: true, calibrationStatus: 'calibrated' }, 200)
}

/** 供测试清理内存库（vitest 用例内独立初始化） */
export function __resetSplMock(): void {
  splStore = [...MOCK_SPL_MAPPINGS]
  historyStore = [...MOCK_SPL_HISTORY]
  nextSplId = 1000
}
