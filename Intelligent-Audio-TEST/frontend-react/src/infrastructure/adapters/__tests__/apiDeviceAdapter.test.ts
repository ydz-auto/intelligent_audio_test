/**
 * INT-1437 密钥池：apiDeviceAdapter DTO⇄Domain 映射单测。
 * 设备管理页「测试API」页签读侧只映射 api_keys_summary（count + 尾号）。
 */
import { describe, expect, it } from 'vitest'

import { apiDeviceFromDto } from '@/infrastructure/adapters/apiDeviceAdapter'
import type { ApiItemDto } from '@/infrastructure/dto/apis.dto'

const BASE_API_DTO: ApiItemDto = {
  id: 1,
  name: '语音识别API',
  vendor: 'openai',
  description: null,
  status: 'online',
  meta: {},
  proxy_type: null,
  proxy_url: null,
  algorithm_type: null,
  default_max_process: 5,
  default_max_timeout: 30,
  default_max_audio_duration: 60,
  health_score: 90,
  endpoints: [
    {
      id: 'ep-1',
      endpoint: 'https://ep.example.com/v1/asr',
      name: '主端点',
      max_process: 5,
      max_timeout: 30,
      max_audio_duration: 60,
      status: 'online',
      health_score: 92,
      priority: 1,
      description: null,
      api_keys_summary: { count: 3, tails: ['a1b2', 'c3d4', 'e5f6'] },
    },
  ],
  output_types: null,
  protocol: 'http',
  streaming: false,
  adapter_class: null,
  audio_config: null,
  rms_spl_mapping_id: null,
  created_at: null,
  updated_at: null,
}

describe('apiDeviceFromDto 密钥池摘要映射', () => {
  it('endpoints[].api_keys_summary → apiKeysSummary（count + 尾号透传）', () => {
    const device = apiDeviceFromDto(BASE_API_DTO)
    expect(device.endpoints[0].apiKeysSummary).toEqual({ count: 3, tails: ['a1b2', 'c3d4', 'e5f6'] })
  })

  it('无摘要端点 → apiKeysSummary 为 null', () => {
    const dto: ApiItemDto = {
      ...BASE_API_DTO,
      endpoints: [{ ...BASE_API_DTO.endpoints[0], api_keys_summary: null }],
    }
    const device = apiDeviceFromDto(dto)
    expect(device.endpoints[0].apiKeysSummary).toBeNull()
  })

  it('多端点逐项透传摘要（编辑抽屉回显依赖）', () => {
    const dto: ApiItemDto = {
      ...BASE_API_DTO,
      endpoints: [
        BASE_API_DTO.endpoints[0],
        { ...BASE_API_DTO.endpoints[0], id: 'ep-2', api_keys_summary: null },
      ],
    }
    const device = apiDeviceFromDto(dto)
    expect(device.endpoints.map((e) => e.apiKeysSummary)).toEqual([
      { count: 3, tails: ['a1b2', 'c3d4', 'e5f6'] },
      null,
    ])
  })
})

describe('apiDeviceFromDto 协议来源（INT-1800：只读 protocol 列）', () => {
  it('协议取 protocol 列，不读 meta.protocol、不按端点前缀推断', () => {
    const dto: ApiItemDto = {
      ...BASE_API_DTO,
      meta: { protocol: 'wss', environment: 'testing' },
      protocol: 'websocket',
      streaming: true,
      endpoints: [{ ...BASE_API_DTO.endpoints[0], endpoint: 'https://ep.example.com/v1/asr' }],
    }
    const device = apiDeviceFromDto(dto)
    expect(device.protocol).toBe('websocket')
    expect(device.streaming).toBe(true)
    expect(device.environment).toBe('testing')
  })

  it('protocol 列缺失 → null（即便 meta.protocol / 端点前缀能给值，也不兜底）', () => {
    const dto: ApiItemDto = {
      ...BASE_API_DTO,
      meta: { protocol: 'wss' },
      protocol: undefined as unknown as string,
      streaming: false,
      endpoints: [{ ...BASE_API_DTO.endpoints[0], endpoint: 'wss://ep.example.com/v1/asr' }],
    }
    const device = apiDeviceFromDto(dto)
    expect(device.protocol).toBeNull()
    expect(device.streaming).toBe(false)
  })
})

describe('apiDeviceFromDto audio_config（INT-1938 编辑弹窗回显）', () => {
  it('audio_config 透传（顶层列，非 meta.audio_config）', () => {
    const device = apiDeviceFromDto({
      ...BASE_API_DTO,
      audio_config: { sample_rate: 16000, bit_depth: 's16', channels: 1, container: 'pcm' },
    })
    expect(device.audioConfig).toEqual({
      sample_rate: 16000,
      bit_depth: 's16',
      channels: 1,
      container: 'pcm',
    })
  })

  it('未设置的存量记录映射为 null（不写成 undefined）', () => {
    const device = apiDeviceFromDto(BASE_API_DTO)
    expect(device.audioConfig).toBeNull()
  })
})
