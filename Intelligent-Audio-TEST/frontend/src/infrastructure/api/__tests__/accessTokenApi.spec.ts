/**
 * Access Token API 契约桩测试（INT-1155，// 待接线）
 * 覆盖：创建（明文一次 + hint 与明文末 4 位一致）/ 列表（掩码 hint）/
 * 编辑（重命名/scopes/expires/启停）/ 删除的生命周期。
 * 桩内为会话级内存表，测试按「先建后查」的相对断言书写，不依赖绝对条数。
 */
import { describe, it, expect } from 'vitest'
import { accessTokenApi } from '../accessTokenApi'

describe('accessTokenApi 契约桩（// 待接线，INT-1155）', () => {
  it('列表返回种子示例（tokenHint 为末 4 位 hex，status 枚举合法）', async () => {
    const list = await accessTokenApi.listAccessTokens()
    expect(list.length).toBeGreaterThan(0)
    for (const item of list) {
      expect(item.id).toBeGreaterThan(0)
      expect(item.name).toBeTruthy()
      expect(item.tokenHint).toMatch(/^[0-9a-f]{4}$/)
      expect(['enabled', 'disabled']).toContain(item.status)
    }
  })

  it('创建：返回明文 token（at_ + 32 hex）且 tokenHint 与明文末 4 位一致', async () => {
    const created = await accessTokenApi.createAccessToken({
      name: 'CI 测试令牌',
      scopes: ['task:read'],
      expiresAt: null,
    })
    expect(created.accessToken).toMatch(/^at_[0-9a-f]{32}$/)
    expect(created.token.tokenHint).toBe(created.accessToken.slice(-4))
    expect(created.token.name).toBe('CI 测试令牌')
    expect(created.token.scopes).toEqual(['task:read'])
    expect(created.token.expiresAt).toBeNull()
    expect(created.token.status).toBe('enabled')
  })

  it('创建后出现在列表（新增在最前）', async () => {
    const before = await accessTokenApi.listAccessTokens()
    await accessTokenApi.createAccessToken({ name: '新令牌', scopes: [], expiresAt: null })
    const after = await accessTokenApi.listAccessTokens()
    expect(after.length).toBe(before.length + 1)
    expect(after[0].name).toBe('新令牌')
  })

  it('编辑：重命名 / 换 scopes / 改 expires / 启停', async () => {
    const created = await accessTokenApi.createAccessToken({
      name: '待编辑',
      scopes: ['task:read'],
      expiresAt: null,
    })
    const updated = await accessTokenApi.updateAccessToken(created.token.id, {
      name: '已改名',
      scopes: ['report:read'],
      expiresAt: '2027-01-01T00:00:00Z',
      status: 'disabled',
    })
    expect(updated.name).toBe('已改名')
    expect(updated.scopes).toEqual(['report:read'])
    expect(updated.expiresAt).toBe('2027-01-01T00:00:00Z')
    expect(updated.status).toBe('disabled')
  })

  it('编辑：expiresAt null → 永不过期（后端 0 语义）', async () => {
    const created = await accessTokenApi.createAccessToken({
      name: '永久',
      scopes: [],
      expiresAt: '2026-11-01T00:00:00Z',
    })
    const updated = await accessTokenApi.updateAccessToken(created.token.id, { expiresAt: null })
    expect(updated.expiresAt).toBeNull()
  })

  it('删除：DELETE 后从列表移除', async () => {
    const created = await accessTokenApi.createAccessToken({ name: '待删除', scopes: [], expiresAt: null })
    const before = await accessTokenApi.listAccessTokens()
    await accessTokenApi.deleteAccessToken(created.token.id)
    const after = await accessTokenApi.listAccessTokens()
    expect(after.length).toBe(before.length - 1)
    expect(after.some((t) => t.id === created.token.id)).toBe(false)
  })
})
