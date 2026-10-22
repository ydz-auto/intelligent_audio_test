/**
 * 用例全量 ID 圈定 API（infrastructure/api 层；INT-710 开始测试用例选择接线）。
 * POST /testcases/ids（testcase_bp.py:72-75 fetch_case_ids；testcase:read 门槛）。
 * 按筛选条件返回全量用例 ID（不分页），对照旧 Vue getIdsByFilter（toQueryParams 同款
 * camelCase→snake_case 顶层映射后作 body）。
 * 契约（task_service/application/testcase/testcase_query_service.py fetch_case_ids）：
 * body 只认 group（分组**名**）/ search / tag / algorithm_type / dimension_id /
 * only_deleted——与 GET /testcases 的 keyword/group_id 不同端点不同键；group_id 会被后端
 * 静默忽略导致圈定全库（INT-1267 审计 P1，Vue toggleGroupSelection 传分组名对位）。
 */
import { apiClient } from './client'
import type { TestCaseListQuery } from '@/infrastructure/api/testcases-api'

const QUERY_KEY_MAP: Record<string, string> = {
  search: 'search',
  group: 'group',
  dimensionId: 'dimension_id',
  algorithmType: 'algorithm_type',
  trash: 'only_deleted',
}

/** 全量圈定（POST /testcases/ids）：返回符合筛选条件的全部用例 id */
export async function fetchCaseIdsByFilter(
  query: TestCaseListQuery
): Promise<{ ids: string[]; total: number }> {
  const body: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue
    const snakeKey = QUERY_KEY_MAP[key] ?? key
    body[snakeKey] = value
  }
  const dto = await apiClient.post<{ ids?: Array<string | number>; total?: number }>(
    '/testcases/ids',
    body
  )
  return {
    ids: (dto?.ids ?? []).map(String),
    total: dto?.total ?? (dto?.ids ?? []).length,
  }
}
