/**
 * 用例全量 ID 圈定 API（infrastructure/api 层；INT-710 开始测试用例选择接线）。
 * POST /testcases/ids（testcase_bp.py:72-75 fetch_case_ids；testcase:read 门槛）。
 * 按筛选条件返回全量用例 ID（不分页），对照旧 Vue getIdsByFilter（toQueryParams 同款
 * camelCase→snake_case 顶层映射后作 body）。
 */
import { apiClient } from './client'
import type { TestCaseListQuery } from '@/infrastructure/api/testcases-api'

const QUERY_KEY_MAP: Record<string, string> = {
  search: 'keyword',
  groupId: 'group_id',
  dimensionId: 'dimension_id',
  algorithmType: 'algorithm_type',
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
