/**
 * Access Token DTO → 领域适配器测试（INT-1153）：
 * toAccessTokenList 兼容 items 包裹与裸数组两种后端响应；status 映射 enabled/disabled；
 * null 时间字段 → null（列表「从未使用」口径）。
 */
import { describe, expect, it } from 'vitest'

import {
  toAccessToken,
  toAccessTokenList,
  type AccessTokenItemDto,
} from '../access-token.dto'

const itemDto = (): AccessTokenItemDto => ({
  id: 42,
  name: 'Claude Code 脚本',
  token_hint: 'a1b2',
  scopes: ['task:read', 'report:read'],
  expires_at: 1_800_000_000,
  status: 'enabled',
  last_used_at: 1_700_000_000,
  last_used_ip: '10.0.0.8',
  created_at: 1_690_000_000,
})

describe('toAccessTokenList', () => {
  it('items 包裹响应 → 领域数组（snake_case → camelCase）', () => {
    const items = toAccessTokenList({ items: [itemDto()] })
    expect(items).toHaveLength(1)
    const token = items[0]
    expect(token.id).toBe('42')
    expect(token.name).toBe('Claude Code 脚本')
    expect(token.tokenHint).toBe('a1b2')
    expect(token.scopes).toEqual(['task:read', 'report:read'])
    expect(token.expiresAt).toBe(1_800_000_000)
    expect(token.status).toBe('enabled')
    expect(token.lastUsedAt).toBe(1_700_000_000)
    expect(token.lastUsedIp).toBe('10.0.0.8')
  })

  it('裸数组响应同样收敛', () => {
    const items = toAccessTokenList([itemDto()])
    expect(items).toHaveLength(1)
    expect(items[0].id).toBe('42')
  })

  it('null 响应 → 空数组', () => {
    expect(toAccessTokenList(null)).toEqual([])
  })

  it('status disabled / 空 scopes / 零 expires / null 时间字段透传', () => {
    const raw = {
      ...itemDto(),
      status: 'disabled',
      scopes: [],
      expires_at: 0,
      last_used_at: null,
      last_used_ip: null,
    }
    const token = toAccessToken(raw)
    expect(token.status).toBe('disabled')
    expect(token.scopes).toEqual([])
    expect(token.expiresAt).toBe(0)
    expect(token.lastUsedAt).toBeNull()
    expect(token.lastUsedIp).toBeNull()
  })

  it('未知 status 值回落 enabled（后端枚举外值保守放行）', () => {
    const token = toAccessToken({ ...itemDto(), status: 'revoked' })
    expect(token.status).toBe('enabled')
  })
})
