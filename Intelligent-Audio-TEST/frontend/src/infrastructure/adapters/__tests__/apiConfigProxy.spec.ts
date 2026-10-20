/**
 * INT-839/#4：APIConfig 网络代理字段（proxy_type / proxy_url）四层镜像契约测试
 * 锁定 DTO(snake_case) ⇄ Domain(camelCase) 双向转换不丢失；NULL（不用代理）容忍为 undefined。
 */
import { describe, it, expect } from 'vitest'
import { toAPIConfig, toApiUpsertDto } from '../apiConfigAdapter'
import type { APIConfigDto } from '../../dto/apiConfigDto'
import type { APIConfig } from '../../../domain/model/apiConfig'

describe('INT-839/#4：APIConfig 代理字段 DTO ⇄ Domain 双向映射', () => {
  it('toAPIConfig：snake_case proxy_type / proxy_url → camelCase', () => {
    const domain = toAPIConfig({
      id: 1,
      name: 'A',
      proxy_type: 'socks5',
      proxy_url: 'user:pass@10.0.0.1:1080',
    } as unknown as APIConfigDto)
    expect(domain.proxyType).toBe('socks5')
    expect(domain.proxyUrl).toBe('user:pass@10.0.0.1:1080')
  })

  it('toAPIConfig：后端缺省（NULL 不用代理）→ undefined', () => {
    const domain = toAPIConfig({ id: 1, name: 'A' } as unknown as APIConfigDto)
    expect(domain.proxyType).toBeUndefined()
    expect(domain.proxyUrl).toBeUndefined()
  })

  it('toApiUpsertDto：camelCase → snake_case proxy_type / proxy_url', () => {
    const dto = toApiUpsertDto({ proxyType: 'http', proxyUrl: 'user:pass@10.0.0.1:8080' } as Partial<APIConfig>)
    expect(dto.proxy_type).toBe('http')
    expect(dto.proxy_url).toBe('user:pass@10.0.0.1:8080')
  })

  it('toApiUpsertDto：无代理时不带字段（undefined）', () => {
    const dto = toApiUpsertDto({ name: 'A' } as Partial<APIConfig>)
    expect(dto.proxy_type).toBeUndefined()
    expect(dto.proxy_url).toBeUndefined()
  })
})
