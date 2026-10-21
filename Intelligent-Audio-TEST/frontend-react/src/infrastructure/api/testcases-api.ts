/**
 * 用例列表 API（infrastructure/api 层；接线 INT-639，经统一 client.ts）。
 * 对照后端 api_gateway/routes/testcase_bp.py + schemas/testcase.py TestCaseListQuery：
 *   GET /api/v1/testcases?page&per_page&keyword&tag&group_id&algorithm_type&
 *       favorite&only_deleted&dimension_id&type（INT-486 口径：前端不再发送 type）
 * 普通视图返回 TestCaseListData（PaginatedData 内 TestCaseListItem snake_case）；
 * view=tag 为后端契约保留项（Vue 端用），本前端标签视图由平铺行按 tag 客户端聚合
 * （11_用例域.md §3.6），故一律走普通列表（不传 view）。
 * snake→camel 转换收敛在 adapters/dto；application/domain 层只见 camelCase Domain。
 */
import { apiClient } from './client'
import type { TestCaseListItem } from '@/domain/models/testCase'
import { testCaseListItemFromDto } from '@/infrastructure/adapters/testCaseAdapter'
import type { TestCaseListDataDto } from '@/infrastructure/dto/testcase.dto'

export interface TestCaseListQuery {
  page?: number
  perPage?: number
  search?: string
  groupId?: string | null
  /** 标签筛选（INT-592 单选：后端 tag 参数为单值） */
  tag?: string | null
  dimensionId?: number | null
  algorithmType?: string | null
  favorite?: boolean
  trash?: boolean
  /** 分组聚合 / 标签聚合视图（前端拍平；后端 view=tag 契约不消费，见文件头） */
  view?: string | null
}

export interface TestCaseListResult {
  items: TestCaseListItem[]
  total: number
}

/** 列表页当前为客户端懒加载分页（§3.3「已显示 n / 总 条 · 加载更多」），拉大页供前端切分 */
const LIST_PAGE_SIZE = 100

/**
 * 用例列表（真实 GET /testcases）。
 * 未分组虚拟组（INT-249）：后端 group_id 为精确匹配、无 '__ungrouped__' 哨兵，
 * 照 Vue fetchCasesByGroup('__ungrouped__') 口径——不携带 group_id 拉大页后前端过滤；
 * 收藏/回收站互斥守卫：trash 时仅 only_deleted（favorite 清空，INT-215/320 口径）。
 */
export async function fetchTestCases(
  query: TestCaseListQuery
): Promise<TestCaseListResult> {
  const ungrouped = query.groupId === '__ungrouped__'
  const dto = await apiClient.get<TestCaseListDataDto>('/testcases', {
    params: {
      page: query.page ?? 1,
      per_page: query.perPage ?? LIST_PAGE_SIZE,
      keyword: query.search,
      group_id: ungrouped ? undefined : query.groupId,
      tag: query.tag,
      dimension_id: query.dimensionId,
      algorithm_type: query.algorithmType,
      favorite: query.favorite && !query.trash ? true : undefined,
      only_deleted: query.trash ? true : undefined,
    },
  })
  let items = (dto.items ?? []).map(testCaseListItemFromDto)
  if (ungrouped) items = items.filter((c) => c.groupId === null)
  return { items, total: dto.total }
}

/** 分组视图数据（grouped-case-list 消费：分组卡 + 组内用例卡；客户端按 groupId 聚合） */
export async function fetchGroupedTestCases(
  query: TestCaseListQuery
): Promise<TestCaseListResult> {
  return fetchTestCases(query)
}

/** 标签视图数据（tag-case-list 消费：前端按 tag 聚合为标签卡；后端 view=tag 契约不消费） */
export async function fetchTagGroupedTestCases(
  query: TestCaseListQuery
): Promise<TestCaseListResult> {
  return fetchTestCases(query)
}

/**
 * 收藏/取消收藏（POST/DELETE /testcases/{id}/favorite，testcase:read；幂等）。
 * 开始测试用例选择行内收藏（INT-1138）：调用后由调用方就地回写列表缓存，不整表重拉。
 */
export async function setTestCaseFavorite(
  id: string,
  favorite: boolean
): Promise<void> {
  if (favorite) await apiClient.post(`/testcases/${id}/favorite`)
  else await apiClient.delete(`/testcases/${id}/favorite`)
}

/** 复制用例（POST /testcases/{id}/copy，testcase:copy；返回新用例 id） */
export async function copyTestCase(id: string): Promise<string> {
  const dto = await apiClient.post<{ id?: string | number }>(`/testcases/${id}/copy`)
  return dto?.id != null ? String(dto.id) : ''
}

/** 软删用例（DELETE /testcases/{id} → 移入回收站；恢复/彻底删除走 /restore /purge） */
export async function deleteTestCase(id: string): Promise<void> {
  await apiClient.delete(`/testcases/${id}`)
}

/** 批量恢复（POST /testcases/restore，{ids}，testcase:delete；返回 restored_count） */
export async function restoreTestCases(ids: string[]): Promise<number> {
  const dto = await apiClient.post<{ restored_count?: number }>(
    '/testcases/restore',
    { ids }
  )
  return dto?.restored_count ?? 0
}

/** 批量彻底删除（POST /testcases/purge，{ids}，testcase:delete；返回 purged_count） */
export async function purgeTestCases(ids: string[]): Promise<number> {
  const dto = await apiClient.post<{ purged_count?: number }>(
    '/testcases/purge',
    { ids }
  )
  return dto?.purged_count ?? 0
}
