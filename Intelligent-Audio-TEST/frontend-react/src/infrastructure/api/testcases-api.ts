/**
 * 用例列表/详情 API 桩（infrastructure 层，11_用例域.md §3.3）。
 * 全部返回 mock 常量（红线④），接线时替换为真实请求：
 *   GET /api/v1/testcases（testcase.py TestCaseListQuery：page/per_page/keyword/tag/group_id/
 *       algorithm_type/view/include_deleted/favorite/only_deleted/dimension_id；
 *       type 为残留参数——INT-486 用例不分类型口径前端不再发送）
 *   GET /api/v1/testcases/{id}            （TestCaseDetailData）
 *   GET /api/v1/testcases/stats           （TestCaseStatsData）
 * 本桩在 application 层 use-testcases-list 分发：view=by-group 走 fetchCaseGroupView（分组行聚合），
 * view=by-tag 走 fetchTagGroupView（后端 view=tag 契约保留，前端拍平为行集合）。
 */
import type { TestCaseListItem } from '@/domain/models/testCase'
import { MOCK_TEST_CASES } from '../mock/testcases-mock'

export interface TestCaseListQuery {
  page?: number
  perPage?: number
  search?: string
  groupId?: string | null
  tags?: string[]
  dimensionId?: number | null
  algorithmType?: string | null
  favorite?: boolean
  trash?: boolean
  /** 分组聚合 / 标签聚合视图 */
  view?: string | null
}

export interface TestCaseListResult {
  items: TestCaseListItem[]
  total: number
}

/** 模拟网络延迟（视觉稿演示用；接线后删除） */
function mockLatency<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), 120))
}

/** 行级过滤（用例名称/描述/标签 LIKE，对齐 TestCaseListQuery.keyword 语义） */
function matchKeyword(item: TestCaseListItem, keyword: string): boolean {
  const kw = keyword.trim().toLowerCase()
  return (
    item.name.toLowerCase().includes(kw) ||
    (item.description ?? '').toLowerCase().includes(kw) ||
    item.tags.some((tag) => tag.toLowerCase().includes(kw))
  )
}

/**
 * 用例列表（mock 不做服务端分页，返回全量；收藏/回收站互斥守卫：
 * 进回收站清空收藏态——favoriteOnly && !trashMode 才携带 favorite，INT-215/320 口径）。
 */
export async function fetchTestCases(
  query: TestCaseListQuery
): Promise<TestCaseListResult> {
  // TODO(API 接线): GET /api/v1/testcases?…
  const { search, groupId, tags, dimensionId, favorite, trash } = query

  let items = MOCK_TEST_CASES
  if (trash) items = items.filter((c) => c.deleted)
  else items = items.filter((c) => !c.deleted)
  if (favorite && !trash) items = items.filter((c) => c.isFavorite)
  if (search) items = items.filter((c) => matchKeyword(c, search))
  // 未分组虚拟组（INT-249 口径）：facet 值 '__ungrouped__' → groupId 为空
  if (groupId === '__ungrouped__') items = items.filter((c) => c.groupId === null)
  else if (groupId) items = items.filter((c) => c.groupId === groupId)
  if (tags && tags.length > 0)
    items = items.filter((c) => tags.every((tag) => c.tags.includes(tag)))
  // dimensionId 过滤：mock 按关联评估维度近似（dimension id < 5 时命中主维度集，演示用）
  if (dimensionId)
    items = items.filter((c) =>
      c.algorithmType !== null ? dimensionId % 4 + 1 > 0 : false
    )

  return mockLatency({ items, total: items.length })
}

/** 分组视图数据（grouped-case-list 消费：分组卡 + 组内用例卡） */
export async function fetchGroupedTestCases(
  query: TestCaseListQuery
): Promise<TestCaseListResult> {
  const result = await fetchTestCases({ ...query, view: 'by-group' })
  return result
}

/** 标签视图数据（tag-case-list 消费；后端 view=tag 契约保留，前端按标签聚合为标签卡） */
export async function fetchTagGroupedTestCases(
  query: TestCaseListQuery
): Promise<TestCaseListResult> {
  const result = await fetchTestCases({ ...query, view: 'by-tag' })
  return result
}
