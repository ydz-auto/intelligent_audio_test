/**
 * useApiParamConfig 分桶契约（INT-2281）：
 * 读侧 `/algorithm/mappings` 返回「算法级 + 本 API 级」合并的原始集合，页签三个桶互斥：
 * - `source='api'` → `mappings`（输出映射编辑器）；
 * - `source='case'` + `source_direction='input'` → `inputMappings`（输入映射编辑器）；
 * - 其余本 API 覆盖行（device、case+output 等页签不展示的来源）→ `otherMappings`，
 *   保存时按原值透传，避免整份同步把它们软删；
 * - 算法级行（`api_id=null`）不进 `otherMappings`——否则会在本 API 下造出重复覆盖行。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ParamMapping } from '@/domain/models/algorithmConfig'
import type { AlgorithmApiParam } from '@/domain/models/apiConfig'

const {
  fetchParamsMock,
  fetchMappingsMock,
  fetchCaseParamsMock,
  fetchDimensionsMock,
} = vi.hoisted(() => ({
  fetchParamsMock: vi.fn(async (): Promise<AlgorithmApiParam[]> => []),
  fetchMappingsMock: vi.fn(async (): Promise<ParamMapping[]> => []),
  fetchCaseParamsMock: vi.fn(async (): Promise<AlgorithmApiParam[]> => []),
  fetchDimensionsMock: vi.fn(async () => []),
}))

vi.mock('@/infrastructure/api/api-algorithm-readonly-api', () => ({
  fetchAlgorithmApiParams: fetchParamsMock,
  fetchAlgorithmApiMappings: fetchMappingsMock,
  fetchAlgorithmCaseParams: fetchCaseParamsMock,
}))

vi.mock('@/infrastructure/api/algorithm-config-api', () => ({
  fetchDimensionParams: vi.fn(async () => []),
}))

vi.mock('@/infrastructure/api/evaluation-api', () => ({
  fetchEvaluationDimensions: fetchDimensionsMock,
}))

vi.mock('@/infrastructure/api/param-profile-api', () => ({
  listProfiles: vi.fn(async () => ({ profiles: [], bindings: [] })),
}))

import { useApiParamConfig } from '../useApiParamConfig'

function param(overrides: Partial<AlgorithmApiParam> = {}): AlgorithmApiParam {
  return {
    id: 1,
    paramCode: 'resp_text',
    paramName: '响应文本',
    label: null,
    paramType: 'text',
    direction: 'output',
    required: false,
    defaultValue: null,
    helpText: null,
    uiOrder: 0,
    hidden: false,
    fieldPath: null,
    ...overrides,
  }
}

function mapping(id: number, overrides: Partial<ParamMapping> = {}): ParamMapping {
  return {
    id,
    source: 'api',
    sourceDirection: 'output',
    sourceParam: `src_${id}`,
    paramName: null,
    dimensionId: null,
    dimensionName: null,
    targetParam: `tgt_${id}`,
    targetParamName: null,
    transformType: 'none',
    apiId: null,
    ...overrides,
  }
}

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

describe('useApiParamConfig 映射分桶（INT-2281）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('api 行进 mappings、case+input 进 inputMappings、其余本 API 行进 otherMappings', async () => {
    fetchParamsMock.mockResolvedValue([
      param({ id: 1, paramCode: 'resp_text', direction: 'output' }),
      param({ id: 2, paramCode: 'query_text', direction: 'input' }),
    ])
    fetchMappingsMock.mockResolvedValue([
      mapping(1, { source: 'api', apiId: 42 }),
      mapping(2, { source: 'case', sourceDirection: 'input', apiId: 42 }),
      mapping(3, { source: 'device', sourceDirection: null, apiId: 42 }),
      mapping(4, { source: 'case', sourceDirection: 'output', apiId: 42 }),
      // 算法级行：api_id=null，不是本 API 的覆盖行
      mapping(5, { source: 'device', sourceDirection: null, apiId: null }),
      mapping(6, { source: 'reference', sourceDirection: null, apiId: null }),
    ])

    const { result } = renderHook(() => useApiParamConfig(42, 'voice_llm', true), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.state).toBe('ready'))

    expect(result.current.mappings.map((row) => row.id)).toEqual([1])
    expect(result.current.inputMappings.map((row) => row.id)).toEqual([2])
    // device + case/输出 是页签不展示但要原值透传的本 API 覆盖行；算法级行不进来
    expect(result.current.otherMappings.map((row) => row.id)).toEqual([3, 4])
    expect(result.current.noOutputDeclared).toBe(false)
  })

  it('算法级 api 行照旧展示在输出映射桶（api_id 不影响 api 来源分桶）', async () => {
    fetchParamsMock.mockResolvedValue([param({ id: 1 })])
    fetchMappingsMock.mockResolvedValue([
      mapping(1, { source: 'api', apiId: null }),
      mapping(2, { source: 'api', apiId: 42 }),
    ])

    const { result } = renderHook(() => useApiParamConfig(42, 'voice_llm', true), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.state).toBe('ready'))

    expect(result.current.mappings.map((row) => row.id)).toEqual([1, 2])
    expect(result.current.otherMappings).toEqual([])
    expect(result.current.inputMappings).toEqual([])
  })

  it('没有 output 字段声明时 noOutputDeclared=true（C0 判定）', async () => {
    fetchParamsMock.mockResolvedValue([param({ id: 2, direction: 'input' })])
    fetchMappingsMock.mockResolvedValue([])

    const { result } = renderHook(() => useApiParamConfig(42, 'voice_llm', true), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.state).toBe('ready'))
    expect(result.current.outputParams).toEqual([])
    expect(result.current.noOutputDeclared).toBe(true)
  })
})
