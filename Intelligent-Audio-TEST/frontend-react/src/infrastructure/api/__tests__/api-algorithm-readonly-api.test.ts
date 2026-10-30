/**
 * T4.2「参数配置」页签取数契约（API 实例作用域）：
 * - 字段行 → GET /algorithm/params?algorithm_type=X&param_type=api&api_id=Y
 *   （策略声明 + 本 API 覆盖行解析结果；api_id 必填，算法类型级默认层已废弃）；
 * - 映射行 → GET /algorithm/mappings?algorithm_type=X&source_type=evaluation&api_id=Y
 *   （API 输出映射带 dimension_id 落在 evaluation 桶），客户端再按 source=api 过滤。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  fetchAlgorithmApiMappings,
  fetchAlgorithmApiParams,
} from '@/infrastructure/api/api-algorithm-readonly-api'
import { setSessionExpiredHandler } from '@/infrastructure/api/client'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

const fetchMock = vi.fn()

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function urlOf(index = 0): string {
  return String((fetchMock.mock.calls[index] as [string, RequestInit])[0])
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

describe('fetchAlgorithmApiParams', () => {
  it('按 algorithm_type + param_type=api + api_id 取数并转 camelCase（裸数组 data）', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        success: true,
        code: 0,
        data: [
          { id: 7, param_code: 'input_text', direction: 'input', param_type: 'text' },
          {
            id: 9,
            param_code: 'response_audio',
            direction: 'output',
            param_type: 'audio_file',
            field_path: null,
          },
        ],
      })
    )
    const params = await fetchAlgorithmApiParams('voice_llm', 42)
    expect(urlOf()).toBe(
      '/api/v1/algorithm/params?algorithm_type=voice_llm&param_type=api&api_id=42'
    )
    expect(params.map((p) => [p.paramCode, p.direction])).toEqual([
      ['input_text', 'input'],
      ['response_audio', 'output'],
    ])
  })

  it('兼容后端 config_cache 的 code/name/type 行键', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        success: true,
        code: 0,
        data: [{ id: 9, code: 'response_audio', name: '回复音频', type: 'audio_file', direction: 'output' }],
      })
    )
    const [param] = await fetchAlgorithmApiParams('voice_llm', 42)
    expect([param.paramCode, param.paramName, param.paramType]).toEqual([
      'response_audio',
      '回复音频',
      'audio_file',
    ])
  })

  it('403 原样抛出 ApiError（页签据此降级为「无权查看参数配置」）', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ success: false, code: 403, message: 'forbidden' }, 403)
    )
    await expect(fetchAlgorithmApiParams('voice_llm', 42)).rejects.toMatchObject({
      httpStatus: 403,
    })
  })
})

describe('fetchAlgorithmApiMappings', () => {
  it('请求带 source_type=evaluation + api_id，并再按 source=api 过滤', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        success: true,
        code: 0,
        data: [
          {
            id: 1,
            source: 'api',
            source_param: 'response_audio',
            source_direction: 'output',
            dimension_id: 72,
            target_param: 'audio_file',
            transform_type: 'none',
          },
          {
            id: 2,
            source: 'case_config',
            source_param: 'audios',
            dimension_id: 133,
            target_param: 'played_audios',
            transform_type: 'none',
          },
        ],
      })
    )
    const rows = await fetchAlgorithmApiMappings('voice_llm', 42)
    expect(urlOf()).toBe(
      '/api/v1/algorithm/mappings?algorithm_type=voice_llm&source_type=evaluation&api_id=42'
    )
    expect(rows.map((r) => r.sourceParam)).toEqual(['response_audio'])
  })

  it('非 api 来源行不会进入页签数据', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        success: true,
        code: 0,
        data: [{ id: 3, source: 'reference', source_param: 'query' }],
      })
    )
    expect(await fetchAlgorithmApiMappings('voice_llm', 42)).toEqual([])
  })
})
