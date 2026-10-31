/**
 * 设备「参数策略」编排（Application 层）。
 *
 * - 策略下拉数据源：`GET /algorithm/param-profiles?algorithm_type=X&scope=device`
 *   同一响应带 `device_bindings`（device_id → profile_id）；
 * - 「另存为策略」：把本设备**在抽屉里读得到**的参数与映射（算法级打底 + 本设备覆盖）
 *   收成一份 scope=device 策略，供其他设备套用；
 * - 绑定：`PUT /algorithm/device-scope/{device_id}/binding`（null = 解绑）。
 *
 * 解析优先级（后端 config_cache）：设备覆盖 > 设备绑定策略 > 算法类型级默认。
 *
 * **「另存」只覆盖两层**：网关 `GET /algorithm/params` 没有 `device_id`（`AlgorithmParamListQuery`），
 * 只能拿到该算法下全部原始行，拿不到三层解析结果（映射桶 `GET /algorithm/mappings?device_id=`
 * 已是三层解析）。因此设备**已绑定策略时禁止另存**——`buildDeviceScopeProfileInput` 直接抛错，
 * 抽屉按钮同步禁用——否则收成的策略会丢掉策略层生效值，随后改绑还会把原策略永久旁路。
 * 三层展示与放开另存待 INT-2299（网关按 device_id 返回解析结果 + 层来源标识）。
 */
import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

import type { ParamMapping } from '@/domain/models/algorithmConfig'
import type { AlgorithmApiParam } from '@/domain/models/apiConfig'
import {
  isParamTransformType,
  isParamType,
  type ParamProfile,
  type ParamProfileInput,
  type ParamProfileMappingDraft,
  type ParamProfileParamDraft,
} from '@/domain/models/paramProfile'
import {
  fetchDeviceScopeMappings,
  fetchDeviceScopeParams,
} from '@/infrastructure/api/device-param-api'
import { listProfiles } from '@/infrastructure/api/param-profile-api'

export const deviceProfileQueryKeys = {
  profiles: (algorithmType: string) => ['devices', 'param-profiles', algorithmType] as const,
}

export interface DeviceParamProfileOptions {
  /** 本算法类型下 scope=device 的策略 */
  profiles: ParamProfile[]
  /** 本设备已绑定的策略 id（未绑定 = null） */
  boundProfileId: number | null
  isLoading: boolean
  isError: boolean
}

/** 策略下拉数据源（设备「参数配置」弹窗） */
export function useDeviceParamProfileOptions(
  algorithmType: string,
  enabled: boolean,
  deviceId: number
): DeviceParamProfileOptions {
  const active = enabled && Boolean(algorithmType)
  const query = useQuery({
    queryKey: deviceProfileQueryKeys.profiles(algorithmType),
    queryFn: () => listProfiles(algorithmType, 'device'),
    enabled: active,
    // 绑定 / 另存后即时回读，避免多设备并行改同一策略时读旧值
    staleTime: 0,
    retry: false,
  })

  const boundProfileId = useMemo(() => {
    const binding = (query.data?.deviceBindings ?? []).find(
      (item) => item.deviceId === deviceId
    )
    return binding ? binding.profileId : null
  }, [query.data, deviceId])

  return {
    profiles: query.data?.profiles ?? [],
    boundProfileId,
    isLoading: active && query.isLoading,
    isError: query.isError,
  }
}

function paramKey(row: AlgorithmApiParam): string {
  return `${row.paramCode}|${row.direction}`
}

/** 算法级打底 → 本设备覆盖（同键覆盖）；不含设备绑定策略层（见文件头） */
function effectiveDeviceParams(
  rows: AlgorithmApiParam[],
  deviceId: number
): AlgorithmApiParam[] {
  const map = new Map<string, AlgorithmApiParam>()
  for (const row of rows) {
    if (row.deviceId == null) map.set(paramKey(row), row)
  }
  for (const row of rows) {
    if (row.deviceId === deviceId) map.set(paramKey(row), row)
  }
  return [...map.values()]
}

function toParamDraft(row: AlgorithmApiParam): ParamProfileParamDraft {
  return {
    paramCode: row.paramCode,
    paramName: row.paramName,
    paramType: isParamType(row.paramType) ? row.paramType : 'text',
    direction: row.direction,
    required: row.required,
    defaultValue: row.defaultValue,
    helpText: row.helpText,
    uiOrder: row.uiOrder,
    hidden: row.hidden,
    fieldPath: row.fieldPath,
  }
}

function mappingKey(row: ParamMapping): string {
  return `${row.source}|${row.sourceParam}|${row.dimensionId ?? ''}`
}

/** 两桶映射：算法级打底 → 本设备覆盖（同键覆盖），脏行（缺源/目标）丢弃 */
function effectiveMappings(rows: ParamMapping[], deviceId: number): ParamProfileMappingDraft[] {
  const map = new Map<string, ParamMapping>()
  for (const row of rows) {
    if (row.deviceId == null) map.set(mappingKey(row), row)
  }
  for (const row of rows) {
    if (row.deviceId === deviceId) map.set(mappingKey(row), row)
  }
  return [...map.values()]
    .filter((row) => row.sourceParam && row.targetParam)
    .map((row) => ({
      source: row.source === 'device' ? 'device' : 'case',
      sourceDirection: row.sourceDirection === 'input' ? 'input' : 'output',
      sourceParam: row.sourceParam,
      targetParam: row.targetParam,
      dimensionId: row.dimensionId,
      transformType: isParamTransformType(row.transformType) ? row.transformType : 'none',
    }))
}

/**
 * 把设备**两层**（算法级打底 + 本设备覆盖）的参数 + 映射收成一份 scope=device 策略请求体。
 *
 * 设备已绑定策略时不允许调用：这两层不含策略层，收成的策略会丢掉原策略的生效值，
 * 抽屉随后还会把本设备改绑到新策略。策略列表还没读到（`boundProfileId === undefined`）
 * 时同样拒绝——判不了是否已绑定，宁可不让另存。三层取值待 INT-2299 的读接口（见文件头）。
 */
export async function buildDeviceScopeProfileInput(input: {
  algorithmType: string
  deviceId: number
  name: string
  description: string | null
  /** 本设备当前绑定的策略 id；`undefined` = 策略列表未读到（无法判定绑定），同样禁止另存 */
  boundProfileId: number | null | undefined
}): Promise<ParamProfileInput> {
  const { algorithmType, deviceId, name, description, boundProfileId } = input
  if (boundProfileId === undefined) {
    throw new Error('策略列表尚未读取，无法确认本设备是否已绑定策略，暂不能另存为新策略')
  }
  if (boundProfileId != null) {
    throw new Error(
      '设备已绑定策略：另存为新策略只收「算法级 + 本设备覆盖」两层，会丢失策略层生效值，请改用「克隆当前策略」'
    )
  }
  const [paramRows, caseMappings, evaluationMappings] = await Promise.all([
    fetchDeviceScopeParams(algorithmType),
    fetchDeviceScopeMappings(algorithmType, deviceId, 'case'),
    fetchDeviceScopeMappings(algorithmType, deviceId, 'evaluation'),
  ])
  return {
    scope: 'device',
    algorithmType,
    name,
    description,
    status: 'online',
    config: null,
    params: effectiveDeviceParams(paramRows, deviceId).map(toParamDraft),
    mappings: effectiveMappings([...caseMappings, ...evaluationMappings], deviceId),
  }
}
