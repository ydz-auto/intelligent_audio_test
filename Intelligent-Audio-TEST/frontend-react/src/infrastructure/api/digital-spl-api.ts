/**
 * 数字域 RMS-SPL 映射 API 桩（infrastructure 层；16_设备域.md §10 组件树落位）。
 * 红线④：全部返回 mock 常量（spl-mock），接线时替换为真实请求：
 *   GET    /api/v1/digital-spl                      列表（api_id/calibration_status 服务端过滤）
 *   GET    /api/v1/digital-spl/{id}                 详情
 *   POST   /api/v1/digital-spl                      新增映射（RmsSplMappingCreateRequest）
 *   PUT    /api/v1/digital-spl/{id}                 编辑映射
 *   DELETE /api/v1/digital-spl/{id}                 删除映射
 *   POST   /api/v1/digital-spl/{id}/calibrate       数字校准（点集全量替换，409 互斥）
 *   POST   /api/v1/digital-spl/by-api/{apiId}/set-default  设默认/清除默认
 *   GET    /api/v1/apis                             关联 API facet 选项（含 rmsSplMappingId 默认指针）
 */
import type {
  ApiConfigRef,
  ApiRmsSplMapping,
} from '@/domain/models/digitalSpl'
import {
  MOCK_API_REFS,
  MOCK_DIGITAL_SPL_MAPPINGS,
} from '../mock/spl-mock'

/** 模拟网络延迟（视觉稿演示用；接线后删除） */
function mockLatency<T>(value: T, ms = 180): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms))
}

/** mock 内存库（页面内增删改操作在运行时可变） */
let digitalStore: ApiRmsSplMapping[] = [...MOCK_DIGITAL_SPL_MAPPINGS]
let apiRefsStore: ApiConfigRef[] = [...MOCK_API_REFS]

/** 新 id（mock 阶段自增；接线后走后端自增） */
let nextDigitalId = 2000
function freshId(): number {
  nextDigitalId += 1
  return nextDigitalId
}

/** 当前 mock 内存库（供 feature 内读取；接线后删除） */
export function peekDigitalSplMappings(): ApiRmsSplMapping[] {
  return digitalStore
}

/** 列表（§4.3；GET /digital-spl；mock 阶段全量返回，前端过滤分页） */
export async function fetchDigitalSplMappings(): Promise<ApiRmsSplMapping[]> {
  // TODO(API 接线): GET /api/v1/digital-spl
  return mockLatency([...digitalStore])
}

/** 被测 API facet 选项（§4.1.1；GET /apis，含 rmsSplMappingId 默认指针） */
export async function fetchApiRefs(): Promise<ApiConfigRef[]> {
  // TODO(API 接线): GET /api/v1/apis
  return mockLatency([...apiRefsStore])
}

/** 新增映射（§6.12；POST /digital-spl） */
export async function createDigitalSplMapping(
  input: Omit<ApiRmsSplMapping, 'id' | 'createdAt' | 'updatedAt'>
): Promise<ApiRmsSplMapping> {
  // TODO(API 接线): POST /api/v1/digital-spl
  const now = new Date().toISOString()
  const mapping: ApiRmsSplMapping = {
    ...input,
    id: freshId(),
    createdAt: now,
    updatedAt: now,
  }
  digitalStore = [mapping, ...digitalStore]
  return mockLatency(mapping, 160)
}

/** 编辑映射（§6.12；PUT /digital-spl/{id}） */
export async function updateDigitalSplMapping(
  id: number,
  patch: Partial<ApiRmsSplMapping>
): Promise<ApiRmsSplMapping | undefined> {
  // TODO(API 接线): PUT /api/v1/digital-spl/{id}
  const target = digitalStore.find((m) => m.id === id)
  if (!target) return mockLatency(undefined, 80)
  const updated: ApiRmsSplMapping = {
    ...target,
    ...patch,
    updatedAt: new Date().toISOString(),
  }
  digitalStore = digitalStore.map((m) => (m.id === id ? updated : m))
  return mockLatency(updated, 120)
}

/** 删除映射（§4.3.1；DELETE /digital-spl/{id}） */
export async function deleteDigitalSplMapping(
  id: number
): Promise<{ success: boolean; message?: string }> {
  // TODO(API 接线): DELETE /api/v1/digital-spl/{id}
  const target = digitalStore.find((m) => m.id === id)
  if (!target) return mockLatency({ success: false, message: '映射不存在' }, 80)
  digitalStore = digitalStore.filter((m) => m.id !== id)
  apiRefsStore = apiRefsStore.map((api) =>
    api.rmsSplMappingId === id ? { ...api, rmsSplMappingId: null } : api
  )
  return mockLatency({ success: true }, 120)
}

/** 数字校准（§6.10；POST /digital-spl/{id}/calibrate；点集全量替换并置已校准） */
export async function calibrateDigitalSplMapping(
  id: number,
  points: Array<{ targetSpl: number; gainLinear: number; rmsDbfs: number | null }>
): Promise<{ success: boolean; message?: string }> {
  // TODO(API 接线): POST /api/v1/digital-spl/{id}/calibrate
  const target = digitalStore.find((m) => m.id === id)
  if (!target) return mockLatency({ success: false, message: '映射不存在' }, 80)
  const updated: ApiRmsSplMapping = {
    ...target,
    calibrationStatus: 'calibrated',
    calibrationPoints: points,
    updatedAt: new Date().toISOString(),
  }
  digitalStore = digitalStore.map((m) => (m.id === id ? updated : m))
  // 模拟 409：id=23 关联同一 API(101) 且已有一条默认(21)——mock 阶段直接成功；接线后按后端分布式锁冲突返回 409
  return mockLatency({ success: true }, 220)
}

/** 设默认/清除默认（§4.3.1；POST /digital-spl/by-api/{apiId}/set-default，mapping_id 空清除） */
export async function setDefaultDigitalSplMapping(
  apiId: number,
  mappingId: number | null
): Promise<{ success: boolean }> {
  // TODO(API 接线): POST /api/v1/digital-spl/by-api/{apiId}/set-default
  apiRefsStore = apiRefsStore.map((api) =>
    api.id === apiId ? { ...api, rmsSplMappingId: mappingId } : api
  )
  return mockLatency({ success: true }, 140)
}

/** 供测试清理内存库（vitest 用例内独立初始化） */
export function __resetDigitalSplMock(): void {
  digitalStore = [...MOCK_DIGITAL_SPL_MAPPINGS]
  apiRefsStore = [...MOCK_API_REFS]
  nextDigitalId = 2000
}
