/**
 * 设备「另存为策略」请求体拼装（INT-2271）：
 * ① 未绑定策略时只收「算法级打底 + 本设备覆盖」两层（同键覆盖、其它设备的行不串入、脏映射丢弃）；
 * ② 设备已绑定策略时直接拒绝——两层结果会丢掉绑定策略层的生效值；
 * ③ 策略列表还没读到（绑定状态未知）时同样拒绝，避免「加载态仍可另存」。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ParamMapping } from '@/domain/models/algorithmConfig'
import type { AlgorithmApiParam } from '@/domain/models/apiConfig'

const { fetchParamsMock, fetchMappingsMock } = vi.hoisted(() => ({
  fetchParamsMock: vi.fn(async (_algorithmType: string): Promise<AlgorithmApiParam[]> => []),
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
  label: null,
  paramType: 'text',
  direction: 'input',
  required: true,
  defaultValue: '算法级默认',
  helpText: null,
  uiOrder: 0,
  hidden: false,
  fieldPath: null,
}

const DEVICE_ROW: AlgorithmApiParam = {
  ...ALGO_ROW,
  id: 2,
  deviceId: 5,
  paramName: '本设备输入文本',
  defaultValue: '本设备覆盖值',
  uiOrder: 1,
}

const OTHER_DEVICE_ROW: AlgorithmApiParam = {
  ...ALGO_ROW,
  id: 3,
  deviceId: 6,
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
  fetchParamsMock.mockResolvedValue([OTHER_DEVICE_ROW, ALGO_ROW, DEVICE_ROW])
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
  it('未绑定时收成两层：算法级打底 + 本设备覆盖，其它设备行不串入、脏映射丢弃', async () => {
    const payload = await buildDeviceScopeProfileInput({ ...BASE_INPUT, boundProfileId: null })

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
    })

    // 两桶映射合并；脏行（缺源参数）被丢弃
    expect(payload.mappings).toHaveLength(2)
    expect(payload.mappings.map((row) => row.source).sort()).toEqual(['case', 'device'])

    expect(fetchParamsMock).toHaveBeenCalledWith('asr')
    expect(fetchMappingsMock).toHaveBeenCalledWith('asr', 5, 'case')
    expect(fetchMappingsMock).toHaveBeenCalledWith('asr', 5, 'evaluation')
  })

  it('设备已绑定策略时拒绝另存（两层结果会丢策略层生效值）', async () => {
    await expect(
      buildDeviceScopeProfileInput({ ...BASE_INPUT, boundProfileId: 12 })
    ).rejects.toThrow(/已绑定策略/)
    expect(fetchParamsMock).not.toHaveBeenCalled()
    expect(fetchMappingsMock).not.toHaveBeenCalled()
  })

  it('策略列表未读到（绑定状态未知）时同样拒绝另存', async () => {
    await expect(
      buildDeviceScopeProfileInput({ ...BASE_INPUT, boundProfileId: undefined })
    ).rejects.toThrow(/策略列表尚未读取/)
    expect(fetchParamsMock).not.toHaveBeenCalled()
  })
})
