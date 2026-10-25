/**
 * INT-1938：「测试 API」页签编辑入口复用 §5.3 API 编辑弹窗（入参 ApiConfig）所需的投影。
 * 重点守会静默改数据/丢回显的字段：protocol / streaming（INT-1800 两维）、audioConfig、meta。
 * （该卡原口径里的 deviceType 已随 INT-1800 退役，改由 protocol / streaming 表达。）
 */
import { describe, expect, it } from 'vitest'

import { apiConfigFromApiDevice } from '@/features/devices/lib/api-device-to-api-config'
import type { ApiDevice } from '@/domain/models/apiDevice'

const BASE_DEVICE: ApiDevice = {
  id: 7,
  name: '语音识别API',
  vendor: 'openai',
  description: '被测 ASR',
  status: 'online',
  meta: { protocol: 'https', environment: 'production', body_template: { text: '{{audio}}' } },
  protocol: 'websocket',
  streaming: true,
  environment: 'production',
  proxyType: 'http',
  proxyUrl: 'user:pass@proxy.example.com:8080',
  algorithmType: 'asr_llm',
  defaultMaxProcess: 5,
  defaultMaxTimeout: 30,
  defaultMaxAudioDuration: 60,
  healthScore: 90,
  endpoints: [
    {
      id: 'ep-1',
      endpoint: 'https://ep.example.com/v1/asr',
      name: '主端点',
      maxProcess: 8,
      maxTimeout: 30,
      maxAudioDuration: 60,
      priority: 1,
      status: 'online',
      healthScore: 92,
      description: null,
      apiKeysSummary: { count: 2, tails: ['a1b2', 'c3d4'] },
    },
  ],
  audioConfig: { sample_rate: 16000, channels: 1 },
  rmsSplMappingId: null,
  rmsSplMappingName: null,
  occupied: false,
  createdAt: null,
  updatedAt: null,
}

describe('apiConfigFromApiDevice（设备页 → §5.3 编辑弹窗）', () => {
  it('protocol / streaming / audioConfig / meta 原样带过去（弹窗回显与合并基座）', () => {
    const api = apiConfigFromApiDevice(BASE_DEVICE)
    expect(api.id).toBe(7)
    expect(api.protocol).toBe('websocket')
    expect(api.streaming).toBe(true)
    expect(api.audioConfig).toEqual({ sample_rate: 16000, channels: 1 })
    expect(api.meta).toEqual(BASE_DEVICE.meta)
  })

  it('基础字段与端点逐项透传（端点行编辑回显）', () => {
    const api = apiConfigFromApiDevice(BASE_DEVICE)
    expect(api.name).toBe('语音识别API')
    expect(api.algorithmType).toBe('asr_llm')
    expect(api.defaultMaxProcess).toBe(5)
    expect(api.endpoints).toEqual(BASE_DEVICE.endpoints)
  })

  it('maxConcurrent 取端点 max_process 与默认并发的较大者（与 apiConfigFromDto 同口径）', () => {
    expect(apiConfigFromApiDevice(BASE_DEVICE).maxConcurrent).toBe(8)
    expect(
      apiConfigFromApiDevice({
        ...BASE_DEVICE,
        endpoints: [{ ...BASE_DEVICE.endpoints[0], maxProcess: null }],
      }).maxConcurrent
    ).toBe(5)
    expect(
      apiConfigFromApiDevice({ ...BASE_DEVICE, defaultMaxProcess: null, endpoints: [] }).maxConcurrent
    ).toBe(0)
  })

  it('未设置 audioConfig 的存量记录投影为 null；protocol 越界同样为 null（不猜协议）', () => {
    const api = apiConfigFromApiDevice({ ...BASE_DEVICE, protocol: null, audioConfig: null })
    expect(api.protocol).toBeNull()
    expect(api.audioConfig).toBeNull()
    // 'https' 不在 protocol 值域（http/websocket/sse/grpc）→ 显示「—」，不按前缀/默认值兜底
    expect(apiConfigFromApiDevice({ ...BASE_DEVICE, protocol: 'https' }).protocol).toBeNull()
  })
})
