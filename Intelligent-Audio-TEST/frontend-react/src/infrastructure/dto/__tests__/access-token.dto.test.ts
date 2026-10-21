/**
 * Access Token DTO → 领域适配器测试（INT-1153 返工，对齐 INT-1148 后端契约）：
 * - 时间字段 wire 为 ISO 字符串（expires_at=0 永不过期 / last_used_at 可 null），
 *   toAccessToken 把 ISO 解析为 Unix 毫秒，UI 不再做 seconds*1000；
 * - toAccessTokenList 兼容 items 包裹与裸数组两种后端响应；
 * - status 映射 enabled/disabled；创建响应扁平（data 顶层含 token）。
 */
import { describe, expect, it } from 'vitest'

import {
  toAccessToken,
  toAccessTokenList,
  type AccessTokenCreatedDto,
  type AccessTokenItemDto,
} from '../access-token.dto'

const EXPIRES_ISO = '2027-01-01T00:00:00'
const LAST_USED_ISO = '2026-06-01T10:30:00'
const CREATED_ISO = '2026-05-01T08:00:00'

const itemDto = (): AccessTokenItemDto => ({
  id: 42,
  name: 'Claude Code 脚本',
  token_hint: 'a1b2',
  scopes: ['task:read', 'report:read'],
  expires_at: EXPIRES_ISO,
  status: 'enabled',
  last_used_at: LAST_USED_ISO,
  last_used_ip: '10.0.0.8',
  created_at: CREATED_ISO,
})

describe('toAccessTokenList', () => {
  it('items 包裹响应 → 领域数组（snake_case → camelCase，ISO → Unix 毫秒）', () => {
    const items = toAccessTokenList({ items: [itemDto()] })
    expect(items).toHaveLength(1)
    const token = items[0]
    expect(token.id).toBe('42')
    expect(token.name).toBe('Claude Code 脚本')
    expect(token.tokenHint).toBe('a1b2')
    expect(token.scopes).toEqual(['task:read', 'report:read'])
    expect(token.expiresAt).toBe(new Date(EXPIRES_ISO).getTime())
    expect(token.status).toBe('enabled')
    expect(token.lastUsedAt).toBe(new Date(LAST_USED_ISO).getTime())
    expect(token.lastUsedIp).toBe('10.0.0.8')
    expect(token.createdAt).toBe(new Date(CREATED_ISO).getTime())
  })

  it('裸数组响应同样收敛', () => {
    const items = toAccessTokenList([itemDto()])
    expect(items).toHaveLength(1)
    expect(items[0].id).toBe('42')
  })

  it('null 响应 → 空数组', () => {
    expect(toAccessTokenList(null)).toEqual([])
  })

  it('expires_at=0 永不过期 / 空 scopes / null 时间字段归一', () => {
    const raw: AccessTokenItemDto = {
      ...itemDto(),
      status: 'disabled',
      scopes: [],
      expires_at: 0,
      last_used_at: null,
      last_used_ip: null,
      created_at: null,
    }
    const token = toAccessToken(raw)
    expect(token.status).toBe('disabled')
    expect(token.scopes).toEqual([])
    expect(token.expiresAt).toBe(0)
    expect(token.lastUsedAt).toBeNull()
    expect(token.lastUsedIp).toBeNull()
    expect(token.createdAt).toBe(0)
  })

  it('未知 status 值回落 enabled（后端枚举外值保守放行）', () => {
    const token = toAccessToken({ ...itemDto(), status: 'revoked' })
    expect(token.status).toBe('enabled')
  })
})

describe('toAccessToken（创建响应扁平形态）', () => {
  it('后端创建 data 为扁平条目 + 顶层 token，可直接收敛为领域条目', () => {
    const created: AccessTokenCreatedDto = {
      ...itemDto(),
      token: 'iatp_plaintext_only_once',
    }
    const { token, ...itemDtoOnly } = created
    expect(token).toBe('iatp_plaintext_only_once')
    const item = toAccessToken(itemDtoOnly)
    expect(item.id).toBe('42')
    expect(item.expiresAt).toBe(new Date(EXPIRES_ISO).getTime())
  })
})
