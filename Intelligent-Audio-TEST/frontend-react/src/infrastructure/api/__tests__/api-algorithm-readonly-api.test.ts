/**
 * INT-1778 只读页签取数契约：
 * - 输出字段 → GET /algorithm/params?algorithm_type=X&param_type=api（C0 判定同一次请求）；
 * - 映射 → GET /algorithm/mappings?algorithm_type=X&source_type=api，且客户端按 source=api 再过滤
 *   （后端 gRPC ListMappings 只按 algorithm_type 组查询，source_type 过滤不生效）。
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
  it('按 algorithm_type + param_type=api 取数并转 camelCase', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        success: true,
        code: 0,
        data: {
          items: [
            { id: 7, param_code: 'input_text', direction: 'input', param_type: 'text' },
            {
              id: 9,
              param_code: 'response_audio',
              direction: 'output',
              param_type: 'audio_file',
              field_path: null,
            },
          ],
          total: 2,
        },
      })
    )
    const params = await fetchAlgorithmApiParams('voice_llm')
    expect(urlOf()).toBe('/api/v1/algorithm/params?algorithm_type=voice_llm&param_type=api')
    expect(params.map((p) => [p.paramCode, p.direction])).toEqual([
      ['input_text', 'input'],
      ['response_audio', 'output'],
    ])
  })

  it('403 原样抛出 ApiError（页签据此降级为「无权查看算法配置」）', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ success: false, code: 403, message: 'forbidden' }, 403)
    )
    await expect(fetchAlgorithmApiParams('voice_llm')).rejects.toMatchObject({ httpStatus: 403 })
  })
})

describe('fetchAlgorithmApiMappings', () => {
  it('请求带 source_type=api，并再按 source=api 过滤（后端过滤不生效）', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        success: true,
        code: 0,
        data: {
          items: [
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
          total: 2,
        },
      })
    )
    const rows = await fetchAlgorithmApiMappings('voice_llm')
    expect(urlOf()).toBe('/api/v1/algorithm/mappings?algorithm_type=voice_llm&source_type=api')
    expect(rows.map((r) => r.sourceParam)).toEqual(['response_audio'])
  })

  it('后端忽略 source_type 时不会把非 api 行当映射展示', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        success: true,
        code: 0,
        data: { items: [{ id: 3, source: 'reference', source_param: 'query' }], total: 1 },
      })
    )
    expect(await fetchAlgorithmApiMappings('voice_llm')).toEqual([])
  })
})
