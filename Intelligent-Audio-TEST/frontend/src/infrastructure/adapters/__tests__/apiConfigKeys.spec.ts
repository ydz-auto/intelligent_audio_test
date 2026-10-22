/**
 * INT-1177 密钥池（endpoint 级，INT-1230 审计 D1'/D6' 返工口径）：
 * APIConfig 端点级密钥池字段四层镜像契约测试
 * 锁定 DTO(snake_case) ⇄ Domain(camelCase) 双向转换：
 * - 写侧：endpoints[].apiKeysText（textarea 草稿，每行一个 key，可整段粘贴
 *   自动拆行）→ endpoints[].api_keys 落库；留空不发送（保留既有池）
 * - 写侧：显式 endpoints[].apiKeys → api_keys
 * - 读侧：endpoints[].api_keys_summary → apiKeysSummary（完整密钥零回显）；
 *   meta 中 api_key → camelCase（单值回退链）
 * - meta 不再承载 apiKeys/apiKeysSummary（端点级返工：防御剔除残留）
 */
import { describe, it, expect } from 'vitest'
import { toAPIConfig, toApiUpsertDto } from '../apiConfigAdapter'
import type { APIConfigDto, ApiEndpointDto } from '../../dto/apiConfigDto'
import type { APIConfig, ApiEndpoint } from '../../../domain/model/apiConfig'

describe('INT-1177 端点级密钥池：APIConfig DTO ⇄ Domain 双向映射', () => {
  it('toApiUpsertDto：apiKeysText 草稿 → endpoints[].api_keys 数组（换行拆行）', () => {
    const dto = toApiUpsertDto({
      name: 'A',
      endpoints: [{
        endpoint: 'https://ep.example.com',
        apiKeysText: 'sk-a1\nsk-b2  \n\n  sk-c3',
      }] as ApiEndpoint[],
    } as Partial<APIConfig>)
    expect(dto.endpoints?.[0].api_keys).toEqual(['sk-a1', 'sk-b2', 'sk-c3'])
  })

  it('toApiUpsertDto：apiKeysText 留空不发送 api_keys（编辑未改动保留既有池）', () => {
    const dto = toApiUpsertDto({
      name: 'A',
      endpoints: [{
        endpoint: 'https://ep.example.com',
        apiKeysText: '   \n',
      }] as ApiEndpoint[],
    } as Partial<APIConfig>)
    expect(dto.endpoints?.[0].api_keys).toBeUndefined()
  })

  it('toApiUpsertDto：显式 apiKeys → endpoints[].api_keys', () => {
    const dto = toApiUpsertDto({
      name: 'A',
      endpoints: [{
        endpoint: 'https://ep.example.com',
        apiKeys: ['sk-a1', 'sk-b2'],
      }] as ApiEndpoint[],
    } as Partial<APIConfig>)
    expect(dto.endpoints?.[0].api_keys).toEqual(['sk-a1', 'sk-b2'])
  })

  it('toApiUpsertDto：apiKeysText 草稿不回传自身（瞬态字段）', () => {
    const dto = toApiUpsertDto({
      name: 'A',
      endpoints: [{
        endpoint: 'https://ep.example.com',
        apiKeysText: 'sk-a1',
      }] as ApiEndpoint[],
    } as Partial<APIConfig>)
    const epDto = dto.endpoints?.[0] as ApiEndpointDto
    expect('apiKeysText' in epDto).toBe(false)
  })

  it('toApiUpsertDto：apiKey(camel) → meta.api_key(snake)，其余 meta 键透传', () => {
    const dto = toApiUpsertDto({
      name: 'A',
      meta: { protocol: 'https', apiKey: 'sk-single' },
    } as Partial<APIConfig>)
    expect(dto.meta).toEqual({ protocol: 'https', api_key: 'sk-single' })
  })

  it('toApiUpsertDto：meta 不再承载 apiKeys/apiKeysSummary（防御剔除残留）', () => {
    const dto = toApiUpsertDto({
      name: 'A',
      meta: {
        apiKey: 'sk-single',
        apiKeys: ['sk-a', 'sk-b'],
        apiKeysSummary: { count: 2, tails: ['a', 'b'] },
      } as any,
    } as Partial<APIConfig>)
    expect(dto.meta).toEqual({ api_key: 'sk-single' })
  })

  it('toApiUpsertDto：无 meta 时不携带 meta 字段', () => {
    const dto = toApiUpsertDto({ name: 'A' } as Partial<APIConfig>)
    expect(dto.meta).toBeUndefined()
  })

  it('toAPIConfig：endpoints[].api_keys_summary → apiKeysSummary（逐端点）', () => {
    const domain = toAPIConfig({
      id: 1,
      name: 'A',
      endpoints: [{
        endpoint: 'https://ep.example.com',
        api_keys_summary: { count: 2, tails: ['a1b2', 'c3d4'] },
      }],
    } as unknown as APIConfigDto)
    expect(domain.endpoints?.[0].apiKeysSummary).toEqual({ count: 2, tails: ['a1b2', 'c3d4'] })
  })

  it('toAPIConfig：meta 中 api_key → camelCase（单值回退链）', () => {
    const domain = toAPIConfig({
      id: 1,
      name: 'A',
      meta: { protocol: 'https', api_key: 'sk-single' },
    } as unknown as APIConfigDto)
    expect(domain.meta).toEqual({ protocol: 'https', apiKey: 'sk-single' })
  })

  it('toAPIConfig：meta 中残留 api_keys 不再映射到 meta.apiKeys（防御剔除）', () => {
    const domain = toAPIConfig({
      id: 1,
      name: 'A',
      meta: { api_keys: ['sk-a', 'sk-b'] },
    } as unknown as APIConfigDto)
    // 后端读侧已剥离完整 api_keys；残留仅防御透传（不做 camelCase 映射）
    expect(domain.meta).toEqual({ api_keys: ['sk-a', 'sk-b'] })
  })

  it('toAPIConfig：无摘要时 apiKeysSummary undefined', () => {
    const domain = toAPIConfig({
      id: 1,
      name: 'A',
      endpoints: [{ endpoint: 'https://ep.example.com' }],
    } as unknown as APIConfigDto)
    expect(domain.endpoints?.[0].apiKeysSummary).toBeUndefined()
  })
})
