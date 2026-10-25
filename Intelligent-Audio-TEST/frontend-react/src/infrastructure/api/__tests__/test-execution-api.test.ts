/**
 * INT-1437 密钥池写侧契约：saveApi（POST/PUT /apis）endpoint 行内 textarea 草稿
 * 经 adapter 拆行转 api_keys 落库；留空不显式传 api_keys（保留既有池）；
 * apiKeysText 瞬态字段不回传请求体。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { API_BASE_URL, setSessionExpiredHandler } from '@/infrastructure/api/client'
import { saveApi } from '@/infrastructure/api/test-execution-api'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

const fetchMock = vi.fn()

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function queueResponses(...responses: Response[]): void {
  fetchMock.mockImplementation(() => {
    const next = responses.shift()
    if (!next) throw new Error('fetch 调用超出 mock 队列')
    return Promise.resolve(next)
  })
}

function lastCall(index = 0): [string, RequestInit] {
  return fetchMock.mock.calls[index] as [string, RequestInit]
}

describe('saveApi meta / audio_config 写侧（INT-1777）', () => {
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

  it('dirty meta → 请求体带整块 meta；audioConfig → 顶层 audio_config（不是 meta.audio_config）', async () => {
    queueResponses(jsonResponse({ success: true, code: 0, data: null }))
    await saveApi({
      id: 7,
      name: '接线测试_API',
      meta: { protocol: 'https', appendix_test: 1, method: 'POST' },
      audioConfig: { sample_rate: 16000, bit_depth: 's16', channels: 1, container: 'pcm' },
    })
    const [, init] = lastCall()
    const body = JSON.parse(String(init.body))
    expect(body.meta).toEqual({ protocol: 'https', appendix_test: 1, method: 'POST' })
    expect(body.audio_config).toEqual({
      sample_rate: 16000,
      bit_depth: 's16',
      channels: 1,
      container: 'pcm',
    })
    expect(body.meta.audio_config).toBeUndefined()
  })

  it('未触碰 meta / audio_config → 请求体不带这两个键（避免 {} 清空全表）', async () => {
    queueResponses(jsonResponse({ success: true, code: 0, data: null }))
    await saveApi({ id: 8, name: '仅改名' })
    const body = JSON.parse(String(lastCall()[1].body))
    expect('meta' in body).toBe(false)
    expect('audio_config' in body).toBe(false)
  })

  it('显式清除 audio_config → 顶层 audio_config 传 {}', async () => {
    queueResponses(jsonResponse({ success: true, code: 0, data: null }))
    await saveApi({ id: 9, name: '清除音频格式', audioConfig: {} })
    const body = JSON.parse(String(lastCall()[1].body))
    expect(body.audio_config).toEqual({})
  })
})

describe('saveApi 密钥池写侧（INT-1437）', () => {
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

  it('POST：apiKeysText 草稿拆行 → endpoints[].api_keys（每行一个 key）', async () => {
    queueResponses(jsonResponse({ success: true, code: 0, message: 'ok', data: { id: 5 } }))
    await saveApi({
      name: '密钥池API',
      endpoints: [
        {
          id: null,
          endpoint: 'https://ep.example.com/v1/asr',
          name: '主端点',
          maxProcess: 5,
          maxTimeout: 30,
          maxAudioDuration: 60,
          priority: 1,
          status: 'online',
          healthScore: null,
          description: null,
          apiKeysSummary: null,
          apiKeysText: 'sk-a1\n  sk-b2\n\nsk-c3',
        },
      ],
    })
    const [url, init] = lastCall()
    expect(url).toBe(`${API_BASE_URL}/apis`)
    expect(init.method).toBe('POST')
    const body = JSON.parse(String(init.body))
    expect(body.endpoints[0].api_keys).toEqual(['sk-a1', 'sk-b2', 'sk-c3'])
    expect('apiKeysText' in body.endpoints[0]).toBe(false)
  })

  it('PUT：textarea 留空不显式传 api_keys（后端保留既有池）', async () => {
    queueResponses(jsonResponse({ success: true, code: 0, data: null }))
    await saveApi({
      id: 5,
      name: '密钥池API',
      endpoints: [
        {
          id: null,
          endpoint: 'https://ep.example.com/v1/asr',
          name: '主端点',
          maxProcess: 5,
          maxTimeout: 30,
          maxAudioDuration: 60,
          priority: 1,
          status: 'online',
          healthScore: null,
          description: null,
          apiKeysSummary: { count: 2, tails: ['a1b2', 'c3d4'] },
          apiKeysText: '   \n',
        },
      ],
    })
    const [url, init] = lastCall()
    expect(url).toBe(`${API_BASE_URL}/apis/5`)
    expect(init.method).toBe('PUT')
    const body = JSON.parse(String(init.body))
    expect('api_keys' in body.endpoints[0]).toBe(false)
  })

  it('POST：显式 apiKeys 数组兜底 → endpoints[].api_keys', async () => {
    queueResponses(jsonResponse({ success: true, code: 0, data: { id: 6 } }))
    await saveApi({
      name: '密钥池API',
      endpoints: [
        {
          id: null,
          endpoint: 'https://ep.example.com/v2/asr',
          name: '副端点',
          maxProcess: 3,
          maxTimeout: 60,
          maxAudioDuration: 90,
          priority: 2,
          status: 'online',
          healthScore: null,
          description: null,
          apiKeysSummary: null,
          apiKeys: ['sk-x1', ' sk-x2 '],
        },
      ],
    })
    const body = JSON.parse(String(lastCall()[1].body))
    expect(body.endpoints[0].api_keys).toEqual(['sk-x1', 'sk-x2'])
  })
})
