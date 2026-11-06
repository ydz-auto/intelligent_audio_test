/**
 * roleApi.getRoles P3-2 单测（INT-681）：用户数跨页聚合 + 失败回退。
 * getRoles 以 GET /auth/users 的 `pages` 逐页拉取聚合 role_id 计数（后端角色 dict
 * 不含 user_count），避免用户数 >100 时「用户数」列欠计。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { getRoles } from '@/infrastructure/api/roleApi'

const fetchMock = vi.fn()

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function queueResponses(...responses: Response[]): void {
  fetchMock.mockImplementation(() => {
    const next = responses.shift()
    if (!next) throw new Error('fetch 调用超出 mock 队列')
    return Promise.resolve(next)
  })
}

const ROLES = {
  success: true,
  code: 0,
  data: {
    roles: [
      { id: 1, name: 'admin', description: '超级管理员', permissions: ['*'], is_system: true },
      { id: 2, name: 'tester', description: '测试工程师', permissions: ['task:read'], is_system: true },
    ],
  },
}

function userPage(page: number, pages: number, items: Array<{ id: number; role_id: number }>) {
  return {
    success: true,
    code: 0,
    data: {
      items: items.map((item) => ({
        id: item.id,
        username: `user-${item.id}`,
        email: null,
        role_id: item.role_id,
        role_name: item.role_id === 1 ? 'admin' : 'tester',
        status: 'active',
        is_active: true,
        permissions: [],
        created_at: '',
      })),
      total: 4,
      page,
      pages,
    },
  }
}

describe('roleApi.getRoles 用户数跨页聚合（P3-2）', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('pages>1 时按响应 pages 逐页拉取聚合 role_id 计数', async () => {
    queueResponses(
      jsonResponse(ROLES),
      // 3 页用户：admin 2 人（page1+page2），tester 2 人（page1+page3）
      jsonResponse(userPage(1, 3, [
        { id: 1, role_id: 1 },
        { id: 2, role_id: 2 },
      ])),
      jsonResponse(userPage(2, 3, [{ id: 3, role_id: 1 }])),
      jsonResponse(userPage(3, 3, [{ id: 4, role_id: 2 }]))
    )

    const roles = await getRoles()
    const admin = roles.find((role) => role.id === '1')
    const tester = roles.find((role) => role.id === '2')
    expect(admin?.userCount).toBe(2)
    expect(tester?.userCount).toBe(2)
    // 聚合共请求 3 页用户（page=1/2/3）
    const urls = fetchMock.mock.calls.map(([url]) => String(url))
    expect(urls.filter((url) => url.includes('/auth/users?page=')).length).toBe(3)
  })

  it('用户列表请求失败时回退 0，不影响角色列表', async () => {
    queueResponses(
      jsonResponse(ROLES),
      jsonResponse({ success: false, code: 500, message: '用户列表失败' }, 500)
    )

    const roles = await getRoles()
    expect(roles.length).toBe(2)
    expect(roles.every((role) => role.userCount === 0)).toBe(true)
  })
})
