/**
 * T4.4 / T4.3：参数策略 API 契约单测。
 * 锁定 8 条路由的 HTTP 方法 / 路径 / body 字段名（snake_case）与响应计数收敛。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ParamProfileInput } from '@/domain/models/paramProfile'
import {
  bindApiProfile,
  cloneProfile,
  createProfile,
  deleteProfile,
  getProfile,
  listProfiles,
  saveApiScopeOverrides,
  updateProfile,
} from '@/infrastructure/api/param-profile-api'
import { setSessionExpiredHandler } from '@/infrastructure/api/client'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

const fetchMock = vi.fn()

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function callOf(index = 0): [string, RequestInit] {
  return fetchMock.mock.calls[index] as [string, RequestInit]
}

function bodyOf(index = 0): Record<string, unknown> {
  const init = callOf(index)[1]
  return typeof init.body === 'string' ? JSON.parse(init.body) : {}
}

function ok(data: unknown) {
  return jsonResponse({ success: true, code: 0, data })
}

const SAMPLE_INPUT: ParamProfileInput = {
  scope: 'api',
  algorithmType: 'voice_llm',
  name: 'ASR 输出策略',
  description: null,
  status: 'online',
  params: [
    {
      paramCode: 'asr_text',
      paramName: 'ASR 文本',
      paramType: 'text',
      direction: 'output',
      required: false,
      defaultValue: null,
      helpText: null,
      uiOrder: 1,
      hidden: false,
      fieldPath: 'data.items[0].text',
    },
  ],
  mappings: [
    {
      source: 'api',
      sourceDirection: 'output',
      sourceParam: 'asr_text',
      targetParam: 'text',
      dimensionId: 72,
      transformType: 'none',
    },
  ],
}

const PROFILE_RAW = {
  id: 12,
  scope: 'api',
  algorithm_type: 'voice_llm',
  name: 'ASR 输出策略',
  description: null,
  status: 'online',
  cloned_from: null,
  params: [{ id: 3, param_code: 'asr_text', direction: 'output', param_type: 'text' }],
  mappings: [{ id: 4, source: 'api', source_param: 'asr_text', target_param: 'text' }],
}

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
  authTokenStore.clear()
  setSessionExpiredHandler(null)
})

afterEach(() => {
  vi.unstubAllGlobals()
  authTokenStore.clear()
  setSessionExpiredHandler(null)
})

describe('参数策略 CRUD', () => {
  it('GET /algorithm/param-profiles 带 algorithm_type + scope，读取 { profiles, total, bindings }', async () => {
    fetchMock.mockResolvedValueOnce(
      ok({ profiles: [PROFILE_RAW], total: 1, bindings: [{ api_id: 21, profile_id: 12 }] })
    )
    const result = await listProfiles('voice_llm', 'api')
    expect(callOf()[0]).toBe('/api/v1/algorithm/param-profiles?algorithm_type=voice_llm&scope=api')
    expect(result.profiles[0].algorithmType).toBe('voice_llm')
    expect(result.profiles[0].params[0].paramCode).toBe('asr_text')
    expect(result.bindings).toEqual([{ apiId: 21, profileId: 12 }])
  })

  it('GET /algorithm/param-profiles 无 bindings 时回落空数组', async () => {
    fetchMock.mockResolvedValueOnce(ok({ profiles: [PROFILE_RAW], total: 1 }))
    const result = await listProfiles('voice_llm', 'api')
    expect(result.bindings).toEqual([])
  })

  it('GET /algorithm/param-profiles/{id} 读取详情', async () => {
    fetchMock.mockResolvedValueOnce(ok(PROFILE_RAW))
    const profile = await getProfile(12)
    expect(callOf()[0]).toBe('/api/v1/algorithm/param-profiles/12')
    expect(profile.mappings[0]).toMatchObject({ sourceParam: 'asr_text', transformType: 'none' })
  })

  it('POST 新建：body 为 snake_case（scope / algorithm_type / params / mappings）', async () => {
    fetchMock.mockResolvedValueOnce(ok(PROFILE_RAW))
    await createProfile(SAMPLE_INPUT)
    const [url, init] = callOf()
    expect(url).toBe('/api/v1/algorithm/param-profiles')
    expect(init.method).toBe('POST')
    const body = bodyOf()
    expect(body.algorithm_type).toBe('voice_llm')
    expect(body.scope).toBe('api')
    expect(body.params).toEqual([
      expect.objectContaining({
        param_code: 'asr_text',
        param_type: 'text',
        direction: 'output',
        ui_order: 1,
        field_path: 'data.items[0].text',
      }),
    ])
    expect(body.mappings).toEqual([
      expect.objectContaining({
        source: 'api',
        source_direction: 'output',
        source_param: 'asr_text',
        target_param: 'text',
        dimension_id: 72,
        transform_type: 'none',
      }),
    ])
  })

  it('PUT 更新：路径带 id，body 与新建同构', async () => {
    fetchMock.mockResolvedValueOnce(ok(PROFILE_RAW))
    await updateProfile(12, SAMPLE_INPUT)
    const [url, init] = callOf()
    expect(url).toBe('/api/v1/algorithm/param-profiles/12')
    expect(init.method).toBe('PUT')
    expect(bodyOf().name).toBe('ASR 输出策略')
  })

  it('POST /{id}/clone：body 只含 name / description', async () => {
    fetchMock.mockResolvedValueOnce(ok(PROFILE_RAW))
    await cloneProfile(12, { name: '副本', description: '说明' })
    const [url] = callOf()
    expect(url).toBe('/api/v1/algorithm/param-profiles/12/clone')
    expect(bodyOf()).toEqual({ name: '副本', description: '说明' })
  })

  it('DELETE /{id}：data=boolean', async () => {
    fetchMock.mockResolvedValueOnce(ok(true))
    await expect(deleteProfile(12)).resolves.toBe(true)
    expect(callOf()[0]).toBe('/api/v1/algorithm/param-profiles/12')
  })
})

describe('API 作用域绑定 / 覆盖', () => {
  it('PUT binding：body = { profile_id }，返回绑定结果', async () => {
    fetchMock.mockResolvedValueOnce(ok({ api_id: 21, profile_id: 12 }))
    const result = await bindApiProfile(21, 12)
    const [url, init] = callOf()
    expect(url).toBe('/api/v1/algorithm/api-scope/21/binding')
    expect(init.method).toBe('PUT')
    expect(bodyOf()).toEqual({ profile_id: 12 })
    expect(result).toEqual({ apiId: 21, profileId: 12 })
  })

  it('PUT binding 传 null 表示解绑', async () => {
    fetchMock.mockResolvedValueOnce(ok({ api_id: 21, profile_id: null }))
    expect(await bindApiProfile(21, null)).toEqual({ apiId: 21, profileId: null })
    expect(bodyOf()).toEqual({ profile_id: null })
  })

  it('PUT overrides：body = { algorithm_type, api_params, mappings }', async () => {
    fetchMock.mockResolvedValueOnce(
      ok({
        params_created: 1,
        params_updated: 0,
        params_deleted: 0,
        mappings_created: 1,
        mappings_updated: 0,
        mappings_deleted: 2,
      })
    )
    const result = await saveApiScopeOverrides(21, {
      algorithmType: 'voice_llm',
      params: SAMPLE_INPUT.params,
      mappings: SAMPLE_INPUT.mappings,
    })
    const [url, init] = callOf()
    expect(url).toBe('/api/v1/algorithm/api-scope/21/overrides')
    expect(init.method).toBe('PUT')
    const body = bodyOf() as {
      algorithm_type: unknown
      api_params: Array<Record<string, unknown>>
      mappings: Array<Record<string, unknown>>
    }
    expect(body.algorithm_type).toBe('voice_llm')
    expect(Array.isArray(body.api_params)).toBe(true)
    expect(body.api_params[0]).toMatchObject({ param_code: 'asr_text', direction: 'output' })
    expect(body.mappings[0]).toMatchObject({ source: 'api', dimension_id: 72 })
    expect(result).toEqual({
      paramsCreated: 1,
      paramsUpdated: 0,
      paramsDeleted: 0,
      mappingsCreated: 1,
      mappingsUpdated: 0,
      mappingsDeleted: 2,
    })
  })

  it('403 原样抛出 ApiError', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ success: false, code: 403, message: 'forbidden' }, 403))
    await expect(bindApiProfile(21, 12)).rejects.toMatchObject({ httpStatus: 403 })
  })
})
