/**
 * INT-2025：APIConfig 协议 / 流式性两维 DTO ⇄ Domain 映射。
 * 写侧必须提交 protocol + streaming，且**永不出现已废弃的 device_type**（后端非空即 400）。
 */
import { describe, it, expect } from 'vitest'
import { toAPIConfig, toApiUpsertDto } from '../apiConfigAdapter'
import type { APIConfigDto } from '../../dto/apiConfigDto'
import type { APIConfig } from '../../../domain/model/apiConfig'

describe('INT-2025：APIConfig 协议 / 流式性映射', () => {
  it('toAPIConfig：snake_case protocol / streaming → camelCase', () => {
    const domain = toAPIConfig({
      id: 1,
      name: 'API-A',
      protocol: 'websocket',
      streaming: true,
    } as unknown as APIConfigDto)
    expect(domain.protocol).toBe('websocket')
    expect(domain.streaming).toBe(true)
  })

  it('toAPIConfig：后端未返回两列 → undefined（不猜协议）', () => {
    const domain = toAPIConfig({ id: 1, name: 'API-A' } as unknown as APIConfigDto)
    expect(domain.protocol).toBeUndefined()
    expect(domain.streaming).toBeUndefined()
  })

  it('toApiUpsertDto：带 protocol / streaming，且不含 device_type 键', () => {
    const dto = toApiUpsertDto({ name: 'API-A', protocol: 'sse', streaming: true } as Partial<APIConfig>)
    expect(dto.protocol).toBe('sse')
    expect(dto.streaming).toBe(true)
    expect('device_type' in dto).toBe(false)
  })
})
