/**
 * 设备「参数策略」编排（Application 层）。
 *
 * - 策略下拉数据源：`GET /algorithm/param-profiles?algorithm_type=X&scope=device`
 *   同一响应带 `device_bindings`（device_id → profile_id）；
 * - 「另存为策略」：把本设备的**三层生效值**（算法级默认 → 绑定策略 → 本设备覆盖）
 *   收成一份 scope=device 策略，供其他设备套用；
 * - 绑定：`PUT /algorithm/device-scope/{device_id}/binding`（null = 解绑）。
 *
 * 解析优先级（后端 config_cache）：设备覆盖 > 设备绑定策略 > 算法类型级默认。
 *
 * 「另存」的读侧是 **device 作用域解析结果**（INT-2299）：
 * - 参数：`GET /algorithm/params?param_type=device&device_id=Y`，后端按三层合并并逐行带
 *   `resolved_from`，拿到的就是生效值；
 * - 映射：`GET /algorithm/mappings?device_id=Y` 同为三层解析。
 * 因此设备**已绑定策略时也能另存**，收成的新策略包含策略层生效值，改绑不会丢配置。
 */
import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

import type { ParamMapping } from '@/domain/models/algorithmConfig'
import type { AlgorithmApiParam } from '@/domain/models/apiConfig'
import {
  isParamTransformType,
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

/**
 * 三层解析结果归一：同键只保留一行（后出现的行优先，与后端合并顺序一致），
 * 并防御性挡掉解析接口意外夹带的**其它设备**覆盖行。
 */
function resolvedDeviceParams(
  rows: AlgorithmApiParam[],
  deviceId: number
): AlgorithmApiParam[] {
  const map = new Map<string, AlgorithmApiParam>()
  for (const row of rows) {
    if (row.deviceId != null && row.deviceId !== deviceId) continue
    map.set(paramKey(row), row)
  }
  return [...map.values()]
}

function toParamDraft(row: AlgorithmApiParam): ParamProfileParamDraft {
  return {
    paramCode: row.paramCode,
    paramName: row.paramName,
    // 后端存量行可能有枚举外类型（如 number）：原值透传，不收敛成 text
    paramType: row.paramType || 'text',
    direction: row.direction,
    required: row.required,
    defaultValue: row.defaultValue,
    helpText: row.helpText,
    uiOrder: row.uiOrder,
    hidden: row.hidden,
    fieldPath: row.fieldPath,
    // 无编辑控件的列按读侧原值透传（整份保存不能把它们清空，INT-2267 / INT-2281）
    label: row.label,
    validationRules: row.validationRules ?? null,
  }
}

function mappingKey(row: ParamMapping): string {
  return `${row.source}|${row.sourceParam}|${row.dimensionId ?? ''}`
}

/**
 * 两桶映射：读接口已按算法级 → 绑定策略 → 本设备覆盖解析，这里只做同键去重
 * （策略层行不带 device_id，按打底层处理）并丢弃脏行（缺源/目标）。
 */
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
 * 把本设备的**三层生效值**（算法级默认 → 绑定策略 → 本设备覆盖）收成一份
 * scope=device 策略请求体。
 *
 * 参数走 `GET /algorithm/params?device_id=Y` 的解析结果（后端按三层合并、逐行带
 * `resolved_from`），映射桶也已是三层解析——因此绑没绑策略收的都是生效值，
 * 改绑到新策略不会丢配置（INT-2341；此前只收两层时绑定态另存必然失败）。
 */
export async function buildDeviceScopeProfileInput(input: {
  algorithmType: string
  deviceId: number
  name: string
  description: string | null
}): Promise<ParamProfileInput> {
  const { algorithmType, deviceId, name, description } = input
  const [paramRows, caseMappings, evaluationMappings] = await Promise.all([
    fetchDeviceScopeParams(algorithmType, deviceId),
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
    params: resolvedDeviceParams(paramRows, deviceId).map(toParamDraft),
    mappings: effectiveMappings([...caseMappings, ...evaluationMappings], deviceId),
  }
}
