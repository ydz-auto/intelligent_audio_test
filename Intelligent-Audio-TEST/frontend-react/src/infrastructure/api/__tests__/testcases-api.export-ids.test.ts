/**
 * fetchAllTestCaseIdsByFilter（INT-1642 代码审计 P2 返工：导出「按当前筛选」的全量圈定）。
 * 契约：逐页翻 GET /testcases 到最后一页，收藏 / 回收站 / 分组（含未分组哨兵前端过滤）/
 * 标签 / 维度 / 算法全部生效——不退化成全库，也不退化成仅当前页。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  API_BASE_URL,
  setSessionExpiredHandler,
} from '@/infrastructure/api/client'
import { fetchAllTestCaseIdsByFilter } from '@/infrastructure/api/testcases-api'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

const fetchMock = vi.fn()

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** 列表行 DTO 最小形态（adapter 只读 id/name/config.rounds/group_id 等） */
function row(id: string, groupId: string | null = 'g-1') {
  return {
    id,
    name: `用例_${id}`,
    description: null,
    group_id: groupId,
    group_name: groupId ? `分组_${groupId}` : null,
    type: null,
    tags: [],
    config: { rounds: [{ round_number: 1 }] },
    algorithm_type: 'algo-x',
    created_at: '2026-10-20T00:00:00Z',
    updated_at: '2026-10-20T00:00:00Z',
    is_favorite: true,
    deleted: false,
    total_duration: 10,
  }
}

function pageEnvelope(
  items: ReturnType<typeof row>[],
  total: number,
  pages: number
) {
  return {
    success: true,
    code: 0,
    message: 'Success',
    data: { items, total, page: 1, per_page: 200, pages },
  }
}

function queueResponses(...responses: Response[]): void {
  fetchMock.mockImplementation(() => {
    const next = responses.shift()
    if (!next) throw new Error('fetch 调用超出 mock 队列')
    return Promise.resolve(next)
  })
}

function calledUrls(): string[] {
  return fetchMock.mock.calls.map(([url]) => String(url))
}

describe('fetchAllTestCaseIdsByFilter（INT-1642 导出范围圈定）', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
    authTokenStore.clear()
    setSessionExpiredHandler(null)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    authTokenStore.clear()
    setSessionExpiredHandler(null)
  })

  it('按 pages 逐页翻完，返回全部命中的 id（不退化仅第一页）', async () => {
    queueResponses(
      jsonResponse(pageEnvelope([row('tc-1'), row('tc-2')], 3, 2)),
      jsonResponse(pageEnvelope([row('tc-3')], 3, 2))
    )

    const ids = await fetchAllTestCaseIdsByFilter({ favorite: true })

    expect(ids).toEqual(['tc-1', 'tc-2', 'tc-3'])
    const urls = calledUrls()
    expect(urls).toHaveLength(2)
    expect(urls[0]).toContain(`${API_BASE_URL}/testcases?`)
    expect(urls[0]).toContain('page=1')
    expect(urls[0]).toContain('favorite=true')
    expect(urls[1]).toContain('page=2')
  })

  it('收藏 / 回收站：favorite 与 only_deleted 各按列表口径下发（互斥不双带）', async () => {
    queueResponses(
      jsonResponse(pageEnvelope([row('tc-fav')], 1, 1)),
      jsonResponse(pageEnvelope([row('tc-trash')], 1, 1))
    )

    await fetchAllTestCaseIdsByFilter({ favorite: true })
    await fetchAllTestCaseIdsByFilter({ trash: true })

    const [favUrl, trashUrl] = calledUrls()
    expect(favUrl).toContain('favorite=true')
    expect(favUrl).not.toContain('only_deleted')
    expect(trashUrl).toContain('only_deleted=true')
    expect(trashUrl).not.toContain('favorite')
  })

  it('未分组哨兵：服务端不带 group_id，按 groupId=null 前端过滤后仍逐页翻完', async () => {
    queueResponses(
      jsonResponse(
        pageEnvelope([row('tc-u1', null), row('tc-g1', 'g-1')], 4, 2)
      ),
      jsonResponse(
        pageEnvelope([row('tc-u2', null), row('tc-g2', 'g-2')], 4, 2)
      )
    )

    const ids = await fetchAllTestCaseIdsByFilter({
      groupId: '__ungrouped__',
    })

    expect(ids).toEqual(['tc-u1', 'tc-u2'])
    const urls = calledUrls()
    expect(urls).toHaveLength(2)
    expect(urls[0]).not.toContain('group_id')
    expect(urls[1]).toContain('page=2')
  })
})
