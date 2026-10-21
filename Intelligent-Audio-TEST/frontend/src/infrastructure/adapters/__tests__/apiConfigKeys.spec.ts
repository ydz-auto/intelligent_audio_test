/**
 * INT-1177 密钥池：APIConfig 密钥池字段四层镜像契约测试
 * 锁定 DTO(snake_case) ⇄ Domain(camelCase) 双向转换：
 * - 写侧：apiKey → api_key（后端密钥链 meta_key）；apiKeys → api_keys（轮换池，
 *   空数组不发送以保留既有池）；apiKeysSummary 摘要不回传
 * - 读侧：api_keys_summary → apiKeysSummary；meta 中 api_key / api_keys → camelCase
 */
import { describe, it, expect } from 'vitest'
import { toAPIConfig, toApiUpsertDto } from '../apiConfigAdapter'
import type { APIConfigDto } from '../../dto/apiConfigDto'
import type { APIConfig } from '../../../domain/model/apiConfig'

describe('INT-1177 密钥池：APIConfig 密钥池字段 DTO ⇄ Domain 双向映射', () => {
  it('toApiUpsertDto：apiKey(camel) → api_key(snake)，其余 meta 键透传', () => {
    const dto = toApiUpsertDto({
      name: 'A',
      meta: { protocol: 'https', apiKey: 'sk-single' },
    } as Partial<APIConfig>)
    expect(dto.meta).toEqual({ protocol: 'https', api_key: 'sk-single' })
  })

  it('toApiUpsertDto：apiKeys(camel) → api_keys(snake) 数组', () => {
    const dto = toApiUpsertDto({
      name: 'A',
      meta: { apiKeys: ['sk-a1', 'sk-b2'] },
    } as Partial<APIConfig>)
    expect(dto.meta).toEqual({ api_keys: ['sk-a1', 'sk-b2'] })
  })

  it('toApiUpsertDto：空 apiKeys 不发送（编辑未改动时保留既有池）', () => {
    const dto = toApiUpsertDto({
      name: 'A',
      meta: { apiKeys: ['', '  '] },
    } as Partial<APIConfig>)
    expect(dto.meta).toEqual({})
  })

  it('toApiUpsertDto：apiKeysSummary 摘要不回传（防污染存储）', () => {
    const dto = toApiUpsertDto({
      name: 'A',
      meta: { apiKeysSummary: { count: 1, tails: ['a1'] }, apiKey: 'sk-single' },
    } as Partial<APIConfig>)
    expect(dto.meta).toEqual({ api_key: 'sk-single' })
  })

  it('toApiUpsertDto：无 meta 时不携带 meta 字段', () => {
    const dto = toApiUpsertDto({ name: 'A' } as Partial<APIConfig>)
    expect(dto.meta).toBeUndefined()
  })

  it('toAPIConfig：api_keys_summary → apiKeysSummary', () => {
    const domain = toAPIConfig({
      id: 1,
      name: 'A',
      api_keys_summary: { count: 2, tails: ['a1b2', 'c3d4'] },
    } as unknown as APIConfigDto)
    expect(domain.apiKeysSummary).toEqual({ count: 2, tails: ['a1b2', 'c3d4'] })
  })

  it('toAPIConfig：meta 中 api_key / api_keys → camelCase（防御回显）', () => {
    const domain = toAPIConfig({
      id: 1,
      name: 'A',
      meta: { protocol: 'https', api_key: 'sk-single', api_keys: ['sk-a', 'sk-b'] },
    } as unknown as APIConfigDto)
    expect(domain.meta).toEqual({ protocol: 'https', apiKey: 'sk-single', apiKeys: ['sk-a', 'sk-b'] })
  })

  it('toAPIConfig：无摘要时 undefined', () => {
    const domain = toAPIConfig({ id: 1, name: 'A' } as unknown as APIConfigDto)
    expect(domain.apiKeysSummary).toBeUndefined()
  })
})
