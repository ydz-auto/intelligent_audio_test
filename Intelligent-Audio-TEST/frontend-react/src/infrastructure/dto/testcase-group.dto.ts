/**
 * 用例分组 DTO（infrastructure/dto 层——snake_case 唯一出现层；11_用例域.md §3.5）。
 * 形态对照 api_gateway/schemas/group.py GroupItem / GroupListData 实测逐字段。
 */
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'

/** GET /groups 列表项（group.py GroupItem；description/algorithm_type 后端为 None 时省略） */
export interface GroupItemDto {
  id: string
  name: string
  description?: string | null
  algorithm_type?: string | null
  created_at: string
  updated_at: string
  test_case_count: number
}

/** GET /groups 列表响应（group.py GroupListData：PaginatedData 信封内 items） */
export interface GroupListDataDto {
  items: GroupItemDto[]
  total: number
  page: number
  per_page: number
  pages: number
}

/** GroupItemDto → Domain TestCaseGroup（显式逐字段映射；后端省略 null 字段时兜底 null） */
export function toTestCaseGroup(dto: GroupItemDto): TestCaseGroup {
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description ?? null,
    algorithmType: dto.algorithm_type ?? null,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
    testCaseCount: dto.test_case_count,
  }
}
