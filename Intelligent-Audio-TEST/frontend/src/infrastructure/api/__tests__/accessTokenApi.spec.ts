/**
 * Access Token API 真实接线测试（INT-1389）
 * 覆盖：列表（GET /auth/access-tokens → items 映射）/ 创建（POST → data 扁平条目+顶层 token 明文）/
 * 编辑（PATCH → 回读 GET 详情）/ 删除（DELETE）。
 * request 被 mock，断言真实端点 + 载荷，不再有内存桩。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../../http/client', () => ({
  request: vi.fn(),
}))

import { request } from '../../http/client'
import { accessTokenApi } from '../accessTokenApi'

const mockedRequest = vi.mocked(request)

/** 符合后端 _access_token_to_dict 输出形态的条目（INT-1148） */
const ITEM = {
  id: 7,
  user_id: 1,
  name: 'CI 集成令牌',
  token_hint: 'a3f2',
  scopes: ['task:read', 'report:read'],
  status: 'enabled',
  expires_at: 0,
  last_used_at: null,
  last_used_ip: null,
  created_at: '2026-10-20T02:00:00Z',
}

beforeEach(() => {
  mockedRequest.mockReset()
})

describe('accessTokenApi 真实接线（INT-1389）', () => {
  it('列表：GET /auth/access-tokens → items 数组映射为 domain', async () => {
    mockedRequest.mockResolvedValueOnce({ total: 1, items: [ITEM] })
    const list = await accessTokenApi.listAccessTokens()
    expect(mockedRequest).toHaveBeenCalledWith('GET', '/auth/access-tokens', null, expect.anything())
    expect(list).toHaveLength(1)
    expect(list[0]).toMatchObject({
      id: 7,
      name: 'CI 集成令牌',
      tokenHint: 'a3f2',
      scopes: ['task:read', 'report:read'],
      status: 'enabled',
      expiresAt: null, // 0 → null（永不过期）
    })
  })

  it('创建：POST body（scopes 空→null、expiresAt null→0），明文经扁平 data.token 仅一次', async () => {
    const plain = `at_${'ab'.repeat(16)}`
    mockedRequest.mockResolvedValueOnce({ ...ITEM, token: plain })
    const created = await accessTokenApi.createAccessToken({
      name: 'CI 集成令牌',
      scopes: ['task:read'],
      expiresAt: null,
    })
    expect(mockedRequest).toHaveBeenCalledWith('POST', '/auth/access-tokens', {
      name: 'CI 集成令牌',
      scopes: ['task:read'],
      expires_at: 0,
    }, expect.anything())
    expect(created.accessToken).toBe(plain)
    expect(created.token).toMatchObject({ id: 7, name: 'CI 集成令牌', tokenHint: 'a3f2' })
  })

  it('创建：scopes 空数组 → null（继承全部权限）', async () => {
    mockedRequest.mockResolvedValueOnce({ ...ITEM, scopes: [], token: 'at_x' })
    await accessTokenApi.createAccessToken({ name: '空 scopes', scopes: [], expiresAt: null })
    expect(mockedRequest).toHaveBeenCalledWith('POST', '/auth/access-tokens', {
      name: '空 scopes',
      scopes: null,
      expires_at: 0,
    }, expect.anything())
  })

  it('编辑：PATCH 载荷只含给定字段（undefined 不发送）→ 回读 GET 详情', async () => {
    mockedRequest
      .mockResolvedValueOnce(undefined) // PATCH 成功 {success, message} 无 data
      .mockResolvedValueOnce({ ...ITEM, name: '已改名', status: 'disabled' })
    const updated = await accessTokenApi.updateAccessToken(7, {
      name: '已改名',
      scopes: ['report:read'],
      expiresAt: '2027-01-01T00:00:00Z',
      status: 'disabled',
    })
    expect(mockedRequest).toHaveBeenNthCalledWith(1, 'PATCH', '/auth/access-tokens/7', {
      name: '已改名',
      scopes: ['report:read'],
      expires_at: '2027-01-01T00:00:00Z',
      status: 'disabled',
    }, expect.anything())
    expect(mockedRequest).toHaveBeenNthCalledWith(2, 'GET', '/auth/access-tokens/7', null, expect.anything())
    expect(updated).toMatchObject({ name: '已改名', status: 'disabled' })
  })

  it('编辑：只启停（status）时 PATCH 载荷无其余字段', async () => {
    mockedRequest
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce({ ...ITEM, status: 'disabled' })
    await accessTokenApi.updateAccessToken(7, { status: 'disabled' })
    expect(mockedRequest).toHaveBeenNthCalledWith(1, 'PATCH', '/auth/access-tokens/7', {
      status: 'disabled',
    }, expect.anything())
  })

  it('编辑：expiresAt null → 0（永不过期）；expiresAt undefined → 不发送', async () => {
    mockedRequest
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce(ITEM)
    await accessTokenApi.updateAccessToken(7, { expiresAt: null })
    expect(mockedRequest).toHaveBeenNthCalledWith(1, 'PATCH', '/auth/access-tokens/7', {
      expires_at: 0,
    }, expect.anything())
  })

  it('删除：DELETE /auth/access-tokens/{id}', async () => {
    mockedRequest.mockResolvedValueOnce(undefined)
    await accessTokenApi.deleteAccessToken(7)
    expect(mockedRequest).toHaveBeenCalledWith('DELETE', '/auth/access-tokens/7', null, expect.anything())
  })
})
