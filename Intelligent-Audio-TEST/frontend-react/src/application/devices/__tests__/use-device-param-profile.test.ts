/**
 * 设备「另存为策略」请求体拼装（INT-2271 / INT-2341）：
 * ① 参数取 device 作用域三层解析结果（算法级默认 → 绑定策略 → 本设备覆盖），
 *    同键覆盖、其它设备的行不串入、脏映射丢弃；
 * ② 已绑定策略时同样可另存（读接口已解析策略层，不再依赖策略列表 / boundProfileId）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ParamMapping } from '@/domain/models/algorithmConfig'
import type { AlgorithmApiParam } from '@/domain/models/apiConfig'

const { fetchParamsMock, fetchMappingsMock } = vi.hoisted(() => ({
  fetchParamsMock: vi.fn(
    async (_algorithmType: string, _deviceId?: number): Promise<AlgorithmApiParam[]> => []
  ),
  fetchMappingsMock: vi.fn(
    async (
      _algorithmType: string,
      _deviceId: number,
      _bucket?: string
    ): Promise<ParamMapping[]> => []
  ),
}))

vi.mock('@/infrastructure/api/device-param-api', () => ({
  fetchDeviceScopeParams: fetchParamsMock,
  fetchDeviceScopeMappings: fetchMappingsMock,
}))

vi.mock('@/infrastructure/api/param-profile-api', () => ({
  listProfiles: vi.fn(),
}))

import { buildDeviceScopeProfileInput } from '../use-device-param-profile'

const ALGO_ROW: AlgorithmApiParam = {
  id: 1,
  deviceId: null,
  paramCode: 'input_text',
  paramName: '输入文本',
  label: '输入文本(展示名)',
  paramType: 'text',
  direction: 'input',
  required: true,
  defaultValue: '算法级默认',
  helpText: null,
  validationRules: '{"max":10}',
  uiOrder: 0,
  hidden: false,
  fieldPath: null,
  resolvedFrom: 'algorithm',
}

/** 策略层生效行：device_id 为空（策略属于算法类型），值来自绑定策略 */
const PROFILE_ROW: AlgorithmApiParam = {
  ...ALGO_ROW,
  id: 0,
  paramName: '策略输入文本',
  defaultValue: '策略层生效值',
  resolvedFrom: 'profile',
  profileParamId: 77,
}

const DEVICE_ROW: AlgorithmApiParam = {
  ...ALGO_ROW,
  id: 2,
  deviceId: 5,
  paramName: '本设备输入文本',
  defaultValue: '本设备覆盖值',
  uiOrder: 1,
  resolvedFrom: 'device',
}

const OTHER_DEVICE_ROW: AlgorithmApiParam = {
  ...ALGO_ROW,
  id: 3,
  deviceId: 6,
  paramCode: 'other_param',
  paramName: '别的设备覆盖',
  defaultValue: '别的设备值',
}

const CASE_MAPPING: ParamMapping = {
  id: 11,
  source: 'case',
  sourceDirection: 'input',
  sourceParam: 'input_text',
  paramName: null,
  dimensionId: null,
  dimensionName: null,
  targetParam: 'input_text',
  targetParamName: null,
  transformType: 'none',
  deviceId: null,
}

const EVALUATION_MAPPING: ParamMapping = {
  id: 12,
  source: 'device',
  sourceDirection: 'output',
  sourceParam: 'asr_text',
  paramName: null,
  dimensionId: 72,
  dimensionName: '逐轮话轮评估',
  targetParam: 'text',
  targetParamName: null,
  transformType: 'none',
  deviceId: 5,
}

/** 源/目标缺失的脏行：拼装时丢弃 */
const DIRTY_MAPPING: ParamMapping = {
  ...EVALUATION_MAPPING,
  id: 13,
  sourceParam: '',
}

beforeEach(() => {
  vi.clearAllMocks()
  // 解析接口只返回一行/键；这里故意多塞一份同键行与其它设备行，验证归一逻辑
  fetchParamsMock.mockResolvedValue([
    OTHER_DEVICE_ROW,
    ALGO_ROW,
    PROFILE_ROW,
    DEVICE_ROW,
  ])
  fetchMappingsMock.mockImplementation(async (_algorithmType, _deviceId, bucket) =>
    bucket === 'case' ? [CASE_MAPPING, DIRTY_MAPPING] : [EVALUATION_MAPPING]
  )
})

const BASE_INPUT = {
  algorithmType: 'asr',
  deviceId: 5,
  name: '接线测试_设备策略',
  description: null,
}

describe('buildDeviceScopeProfileInput', () => {
  it('收成三层生效值：同键取本设备覆盖、其它设备行不串入、脏映射丢弃', async () => {
    const payload = await buildDeviceScopeProfileInput(BASE_INPUT)

    expect(payload.scope).toBe('device')
    expect(payload.algorithmType).toBe('asr')
    expect(payload.status).toBe('online')
    expect(payload.config).toBeNull()

    // 同键 (param_code, direction) 由本设备覆盖，且只保留一行
    expect(payload.params).toHaveLength(1)
    expect(payload.params[0]).toMatchObject({
      paramCode: 'input_text',
      paramName: '本设备输入文本',
      defaultValue: '本设备覆盖值',
      direction: 'input',
      required: true,
      // 无编辑控件的列原值透传（INT-2267 / INT-2281）
      label: '输入文本(展示名)',
      validationRules: '{"max":10}',
    })

    // 两桶映射合并；脏行（缺源参数）被丢弃
    expect(payload.mappings).toHaveLength(2)
    expect(payload.mappings.map((row) => row.source).sort()).toEqual(['case', 'device'])

    // 读侧必须带 device_id（三层解析），否则只拿到算法级 + 全部原始行
    expect(fetchParamsMock).toHaveBeenCalledWith('asr', 5)
    expect(fetchMappingsMock).toHaveBeenCalledWith('asr', 5, 'case')
    expect(fetchMappingsMock).toHaveBeenCalledWith('asr', 5, 'evaluation')
  })

  it('策略层行成为生效值时按策略层取值（绑定态另存不再被拒绝）', async () => {
    // 设备没有覆盖行时，解析结果里的同键行来自策略层
    fetchParamsMock.mockResolvedValue([ALGO_ROW, PROFILE_ROW])

    const payload = await buildDeviceScopeProfileInput(BASE_INPUT)

    expect(payload.params).toHaveLength(1)
    expect(payload.params[0]).toMatchObject({
      paramCode: 'input_text',
      paramName: '策略输入文本',
      defaultValue: '策略层生效值',
    })
  })
})
