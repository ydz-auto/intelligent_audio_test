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
 * 用例保存载荷（camelCase Domain 写侧；对照 api_gateway/schemas/testcase.py
 * TestCaseCreateSchema/TestCaseUpdateSchema，Vue testcasesApi.create/update 口径）。
 * config/algorithmParams/referenceParams 值内动态结构原样透传（snake_case 契约，
 * 与 batch API「顶层映射、值内 Dict 透传」一致）。
 */
export interface TestCaseMutatePayload {
  name: string
  description?: string | null
  /** 分组 id（新建「+ 新建分组」时缺省，改走 group 字段） */
  groupId?: string | null
  /** 新建分组名（group_id 缺省时后端按名建组） */
  group?: string | null
  tags?: string[]
  algorithmType?: string | null
  config?: Record<string, unknown> | null
  algorithmParams?: unknown
  referenceParams?: unknown
  /** INT-590：评估策略引用（写时物化；后端契约：显式空字符串 '' 清引用，null/缺省沿用既有引用） */
  strategyId?: string | null
  strategyOverrides?: Record<string, unknown> | null
}

/** 写侧 camelCase → snake_case 顶层映射（值内动态结构原样透传，Vue convertTestCaseFormData 口径） */
const MUTATE_KEY_MAP: Record<string, string> = {
  groupId: 'group_id',
  algorithmType: 'algorithm_type',
  algorithmParams: 'algorithm_params',
  referenceParams: 'reference_params',
  strategyId: 'strategy_id',
  strategyOverrides: 'strategy_overrides',
}

function toTestCaseMutateDto(
  payload: TestCaseMutatePayload
): Record<string, unknown> {
  const body: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(payload)) {
    if (value === undefined) continue
    const snakeKey = MUTATE_KEY_MAP[key] ?? key
    body[snakeKey] = value
  }
  return body
}

/** 创建测试用例（POST /testcases；对照 Vue testcasesApi.create → StringIdData） */
export async function createTestCase(
  payload: TestCaseMutatePayload
): Promise<{ id: string }> {
  const dto = await apiClient.post<{ id?: string | number }>(
    '/testcases',
    toTestCaseMutateDto(payload)
  )
  return { id: String(dto?.id ?? '') }
}

/** 更新测试用例（PUT /testcases/{id}；对照 Vue testcasesApi.update） */
export async function updateTestCase(
  id: string,
  payload: TestCaseMutatePayload
): Promise<void> {
  await apiClient.put(`/testcases/${id}`, toTestCaseMutateDto(payload))
}

/**
 * 删除测试用例（DELETE /testcases/{id}；逻辑删除 → 回收站，Vue testcasesApi.delete）。
 * 若该用例正被活跃任务引用，后端返回错误码 201。
 */
export async function deleteTestCase(id: string): Promise<void> {
  await apiClient.delete(`/testcases/${id}`)
}

/** 复制测试用例（POST /testcases/{id}/copy；深度克隆，新名称默认为「原名称_copy」，返回新用例 id） */
export async function copyTestCase(id: string): Promise<string> {
  const dto = await apiClient.post<{ id?: string | number }>(`/testcases/${id}/copy`)
  return dto?.id != null ? String(dto.id) : ''
}

/** 恢复单个测试用例（POST /testcases/{id}/restore；favorite_trash_bp INT-141） */
export async function restoreTestCase(id: string): Promise<void> {
  await apiClient.post(`/testcases/${id}/restore`)
}

/** 彻底删除单个测试用例（DELETE /testcases/{id}/purge；admin/owner 由服务端按 metadata 校验） */
export async function purgeTestCase(id: string): Promise<void> {
  await apiClient.delete(`/testcases/${id}/purge`)
}

/** 收藏 / 取消收藏（POST/DELETE /testcases/{id}/favorite；INT-141 per-user，需带 Bearer 身份；
 *  testcase:read 幂等）。开始测试用例选择行内收藏（INT-1138）：调用后由调用方就地回写列表缓存，
 *  不整表重拉。 */
export async function setTestCaseFavorite(
  id: string,
  favorite: boolean
): Promise<void> {
  if (favorite) await apiClient.post(`/testcases/${id}/favorite`)
  else await apiClient.delete(`/testcases/${id}/favorite`)
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
