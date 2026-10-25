/**
 * INT-1437 密钥池写侧契约：devicesApi createApiDevice/updateApiDevice（POST/PUT /apis）
 * 端点行内 textarea 草稿经 adapter 拆行转 api_keys；留空不显式传（保留既有池）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { API_BASE_URL, setSessionExpiredHandler } from '@/infrastructure/api/client'
import { createApiDevice, updateApiDevice } from '@/infrastructure/api/devicesApi'
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

describe('createApiDevice/updateApiDevice 密钥池写侧（INT-1437）', () => {
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

  it('createApiDevice：apiKeysText 草稿拆行 → endpoints[].api_keys', async () => {
    queueResponses(jsonResponse({ success: true, code: 0, data: { id: 7 } }))
    await createApiDevice({
      name: '设备API',
      vendor: 'openai',
      description: null,
      status: 'offline',
      meta: { environment: 'testing' },
      protocol: 'http',
      streaming: false,
      environment: 'testing',
      proxyType: null,
      proxyUrl: null,
      algorithmType: 'voice_llm',
      defaultMaxProcess: 5,
      defaultMaxTimeout: 30,
      defaultMaxAudioDuration: 60,
      healthScore: null,
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
          apiKeysText: 'sk-dev-1\r\nsk-dev-2',
        },
      ],
      rmsSplMappingId: null,
      rmsSplMappingName: null,
      occupied: false,
      // INT-1938：ApiDevice 新增的列（只读进模型，POST 不提交）
      audioConfig: null,
    })
    const [url, init] = lastCall()
    expect(url).toBe(`${API_BASE_URL}/apis`)
    expect(init.method).toBe('POST')
    const body = JSON.parse(String(init.body))
    expect(body.endpoints[0].api_keys).toEqual(['sk-dev-1', 'sk-dev-2'])
    expect('apiKeysText' in body.endpoints[0]).toBe(false)
    expect('apiKeysSummary' in body.endpoints[0]).toBe(false)
    // INT-1938：设备抽屉新增不写 device_type / audio_config（只给模型补列，供 §5.3 弹窗回显）
    expect('device_type' in body).toBe(false)
    expect('audio_config' in body).toBe(false)
  })

  it('updateApiDevice：留空不显式传 api_keys（保留既有池）', async () => {
    queueResponses(jsonResponse({ success: true, code: 0, data: null }))
    await updateApiDevice(7, {
      name: '设备API改名',
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
          apiKeysText: '',
        },
      ],
    })
    const [url, init] = lastCall()
    expect(url).toBe(`${API_BASE_URL}/apis/7`)
    expect(init.method).toBe('PUT')
    const body = JSON.parse(String(init.body))
    expect('api_keys' in body.endpoints[0]).toBe(false)
  })
})
