/**
 * INT-1437 密钥池：apiConfigAdapter DTO⇄Domain 映射单测。
 * 读侧只映射 api_keys_summary（count + 尾号），完整密钥后端不返回/不回显。
 */
import { describe, expect, it } from 'vitest'

import { apiConfigFromDto, endpointFromDto } from '@/infrastructure/adapters/apiConfigAdapter'
import type { ApiEndpointItemDto, ApiItemDto } from '@/infrastructure/dto/apis.dto'

const BASE_ENDPOINT_DTO: ApiEndpointItemDto = {
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
  api_keys_summary: { count: 2, tails: ['a1b2', 'c3d4'] },
}

describe('endpointFromDto 密钥池摘要映射', () => {
  it('api_keys_summary → apiKeysSummary（count + 尾号 4 位透传）', () => {
    const ep = endpointFromDto(BASE_ENDPOINT_DTO)
    expect(ep.apiKeysSummary).toEqual({ count: 2, tails: ['a1b2', 'c3d4'] })
  })

  it('无摘要时 apiKeysSummary 为 null', () => {
    const ep = endpointFromDto({ ...BASE_ENDPOINT_DTO, api_keys_summary: null })
    expect(ep.apiKeysSummary).toBeNull()
  })

  it('单值端点（无密钥池）摘要为 null，其余字段照常映射', () => {
    const ep = endpointFromDto({
      ...BASE_ENDPOINT_DTO,
      api_keys_summary: null,
      max_process: 7,
      endpoint: 'https://ep.example.com/v2',
    })
    expect(ep.apiKeysSummary).toBeNull()
    expect(ep.maxProcess).toBe(7)
    expect(ep.endpoint).toBe('https://ep.example.com/v2')
  })
})

describe('apiConfigFromDto 逐端点透传摘要', () => {
  it('endpoints[].api_keys_summary 随列表映射（编辑回显依赖）', () => {
    const dto: ApiItemDto = {
      id: 1,
      name: '测试API',
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
        BASE_ENDPOINT_DTO,
        { ...BASE_ENDPOINT_DTO, id: 'ep-2', api_keys_summary: { count: 1, tails: ['f8e7'] } },
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
    const config = apiConfigFromDto(dto)
    expect(config.endpoints.map((e) => e.apiKeysSummary)).toEqual([
      { count: 2, tails: ['a1b2', 'c3d4'] },
      { count: 1, tails: ['f8e7'] },
    ])
  })
})

describe('apiConfigFromDto meta / audio_config（INT-1777）', () => {
  const BASE_DTO: ApiItemDto = {
    id: 2,
    name: 'metaAPI',
    vendor: null,
    description: null,
    status: 'online',
    meta: { version: 'v1', appendix_test: 1 },
    proxy_type: null,
    proxy_url: null,
    algorithm_type: 'voice_llm',
    default_max_process: 5,
    default_max_timeout: 30,
    default_max_audio_duration: 60,
    health_score: null,
    endpoints: [BASE_ENDPOINT_DTO],
    output_types: null,
    protocol: 'http',
    streaming: false,
    adapter_class: null,
    audio_config: { sample_rate: 16000, bit_depth: 's16', channels: 1, container: 'pcm' },
    rms_spl_mapping_id: null,
    created_at: null,
    updated_at: null,
  }

  it('meta / audio_config 透传为领域字段（编辑回填依赖）', () => {
    const config = apiConfigFromDto(BASE_DTO)
    expect(config.meta).toEqual({ version: 'v1', appendix_test: 1 })
    expect(config.audioConfig).toEqual({
      sample_rate: 16000,
      bit_depth: 's16',
      channels: 1,
      container: 'pcm',
    })
  })

  it('meta 缺省为 {}，audio_config 缺省为 null', () => {
    const config = apiConfigFromDto({ ...BASE_DTO, meta: undefined as never, audio_config: null })
    expect(config.meta).toEqual({})
    expect(config.audioConfig).toBeNull()
  })
})

describe('apiConfigFromDto 协议 × 流式性（INT-1800 / B0 §3.2）', () => {
  const BASE: ApiItemDto = {
    id: 30,
    name: '协议流式API',
    vendor: null,
    description: null,
    status: 'online',
    meta: { version: 'v1' },
    proxy_type: null,
    proxy_url: null,
    algorithm_type: 'voice_llm',
    default_max_process: 5,
    default_max_timeout: 30,
    default_max_audio_duration: 60,
    health_score: null,
    endpoints: [BASE_ENDPOINT_DTO],
    output_types: null,
    protocol: 'websocket',
    streaming: true,
    adapter_class: null,
    audio_config: null,
    rms_spl_mapping_id: null,
    created_at: null,
    updated_at: null,
  }

  it('两列原样映射为领域两维，且未引入 deviceType', () => {
    const config = apiConfigFromDto(BASE)
    expect(config.protocol).toBe('websocket')
    expect(config.streaming).toBe(true)
    expect('deviceType' in config).toBe(false)
  })

  it('读侧缺失 / 越界协议 → null（界面显示「—」，不猜协议）', () => {
    const missing = apiConfigFromDto({ ...BASE, protocol: undefined as unknown as string })
    expect(missing.protocol).toBeNull()
    const legacy = apiConfigFromDto({ ...BASE, protocol: 'https' })
    expect(legacy.protocol).toBeNull()
  })

  it('streaming 只有布尔 true 才算流式（缺省 false）', () => {
    expect(apiConfigFromDto({ ...BASE, streaming: undefined as unknown as boolean }).streaming).toBe(
      false
    )
    expect(apiConfigFromDto({ ...BASE, streaming: false }).streaming).toBe(false)
  })
})
