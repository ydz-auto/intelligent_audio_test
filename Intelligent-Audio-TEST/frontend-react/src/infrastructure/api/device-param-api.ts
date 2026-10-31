/**
 * 设备级参数作用域（device_id）读写（infrastructure/api 层）。
 *
 * 端点（api_gateway/routes/algorithm_bp.py）：
 * - `GET /algorithm/params?algorithm_type=X&param_type=device`
 *   → 该算法下的**全部**设备参数行（algorithm_device_params，含 device_id）；
 *   调用方按 device_id 合并：设备级行覆盖同键算法级行（device_id IS NULL）；
 * - `POST /algorithm/params` / `PUT /algorithm/params/{id}` / `DELETE /algorithm/params/{id}`
 *   → 设备级行带 `device_id`；不传即算法类型级默认。
 *
 * snake_case ↔ camelCase 只在本层做；403 原样抛 ApiError 由调用方降级。
 */
import type { ParamMapping } from '@/domain/models/algorithmConfig'
import type { AlgorithmApiParam } from '@/domain/models/apiConfig'
import { apiClient } from '@/infrastructure/api/client'
import { toParamMapping } from '@/infrastructure/dto/algorithm-config.dto'
import {
  rowsFromPayload,
  toAlgorithmApiParam,
} from '@/infrastructure/dto/api-algorithm-readonly.dto'

/** 设备参数写入体（设备级覆盖传 deviceId；算法级传 null） */
export interface DeviceParamWriteInput {
  algorithmType: string
  deviceId: number | null
  paramCode: string
  paramName: string | null
  paramType: string
  direction: 'input' | 'output'
  required: boolean
  defaultValue: string | null
  helpText: string | null
  uiOrder: number
}

function toWriteBody(input: DeviceParamWriteInput): Record<string, unknown> {
  return {
    algorithm_type: input.algorithmType,
    device_id: input.deviceId,
    param_code: input.paramCode,
    param_name: input.paramName,
    param_type: input.paramType,
    direction: input.direction,
    required: input.required,
    default_value: input.defaultValue,
    help_text: input.helpText,
    ui_order: input.uiOrder,
    param_type_source: 'device',
  }
}

/** 该算法下全部设备参数行（算法级 + 各设备级） */
export async function fetchDeviceScopeParams(
  algorithmType: string
): Promise<AlgorithmApiParam[]> {
  const payload = await apiClient.get<unknown>('/algorithm/params', {
    params: { algorithm_type: algorithmType, param_type: 'device' },
  })
  return rowsFromPayload(payload).map(toAlgorithmApiParam)
}

/** 新增设备参数（deviceId 非空 = 该设备覆盖行） */
export async function createDeviceScopeParam(
  input: DeviceParamWriteInput
): Promise<{ id: number }> {
  const dto = await apiClient.post<{ id?: number }>('/algorithm/params', toWriteBody(input))
  return { id: dto?.id ?? 0 }
}

/** 更新设备参数（含改作用域：传 deviceId 即改成该设备覆盖行） */
export async function updateDeviceScopeParam(
  paramId: number,
  input: DeviceParamWriteInput
): Promise<void> {
  await apiClient.put(`/algorithm/params/${paramId}`, toWriteBody(input))
}

/** 软删除设备参数（设备覆盖行删除即回落到算法级） */
export async function deleteDeviceScopeParam(paramId: number): Promise<void> {
  await apiClient.delete(`/algorithm/params/${paramId}`)
}

/* ───────────────── 设备级映射（param_mappings.device_id） ───────────────── */

/** 映射来源：case = 用例参数 → 设备输入；device = 设备输出 → 评估参数 */
export type DeviceMappingSource = 'case' | 'device'

/** 设备映射写入体（恒落本设备覆盖行） */
export interface DeviceMappingWriteInput {
  algorithmType: string
  deviceId: number
  source: DeviceMappingSource
  sourceParam: string
  /** case 来源恒 input；device 来源恒 output */
  sourceDirection: 'input' | 'output'
  /** device 来源必填（目标评估维度）；case 来源为 null */
  dimensionId: number | null
  targetParam: string
  transformType: string
}

function toMappingWriteBody(
  input: DeviceMappingWriteInput
): Record<string, unknown> {
  return {
    algorithm_type: input.algorithmType,
    device_id: input.deviceId,
    source_type: input.source,
    source_param: input.sourceParam,
    source_direction: input.sourceDirection,
    dimension_id: input.dimensionId,
    target_param: input.targetParam,
    transform_type: input.transformType,
  }
}

/**
 * 该算法下与设备相关的映射行（算法级打底 + 本设备覆盖）。
 *
 * 后端 `GetParamMappingForComponent(device_id=Y)` 按设备作用域解析覆盖；
 * 行带 `device_id`（null = 算法级默认）。`source_type=evaluation` 拿全桶后按
 * 设备组件语义过滤：设备输出映射 + 用例参数 → 设备输入的映射。
 */
export async function fetchDeviceScopeMappings(
  algorithmType: string,
  deviceId: number
): Promise<ParamMapping[]> {
  const payload = await apiClient.get<unknown>('/algorithm/mappings', {
    params: {
      algorithm_type: algorithmType,
      source_type: 'evaluation',
      device_id: deviceId,
    },
  })
  return rowsFromPayload(payload)
    .map(toParamMapping)
    .filter(
      (row) =>
        row.source === 'device' ||
        (row.source === 'case' && row.sourceDirection === 'input')
    )
}

/** 新增设备映射（带 device_id，仅对本设备生效） */
export async function createDeviceScopeMapping(
  input: DeviceMappingWriteInput
): Promise<void> {
  await apiClient.post('/algorithm/mappings', toMappingWriteBody(input))
}

/** 更新设备映射（显式传 device_id，保持设备作用域） */
export async function updateDeviceScopeMapping(
  mappingId: number,
  input: DeviceMappingWriteInput
): Promise<void> {
  await apiClient.put(`/algorithm/mappings/${mappingId}`, toMappingWriteBody(input))
}

/** 软删除设备映射（删除即回落到算法级映射） */
export async function deleteDeviceScopeMapping(mappingId: number): Promise<void> {
  await apiClient.delete(`/algorithm/mappings/${mappingId}`)
}
