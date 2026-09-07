/**
 * Group（用例分组）DTO —— snake_case
 * 对应后端 api_gateway/schemas/group.py::GroupItem / GroupListData /
 * GroupCreateRequest / GroupUpdateRequest / GroupMoveCasesRequest / GroupDeleteQuery
 */
import type { PaginatedDto } from './common'

/** 对应后端 GroupItem */
export interface GroupItemDto {
  id: string
  name: string
  description?: string | null
  algorithm_type?: string | null
  created_at: string
  updated_at: string
  test_case_count: number
}

/** 对应后端 GroupListData = PaginatedData[GroupItem] */
export type GroupListDto = PaginatedDto<GroupItemDto>

// ===== 请求体/查询参数（snake_case） =====

/** 对应后端 GroupCreateRequest（name 支持 groupName/group_name 双别名） */
export interface GroupCreateDto {
  id?: string
  name: string
  description?: string | null
  algorithm_type?: string | null
}

/** 对应后端 GroupUpdateRequest */
export interface GroupUpdateDto {
  name?: string | null
  description?: string | null
  algorithm_type?: string | null
}

/** 对应后端 GroupMoveCasesRequest */
export interface GroupMoveCasesDto {
  case_ids: (string | number)[]
  target_group_id: string
}

/** 对应后端 DELETE /groups/{id} 查询参数 */
export interface GroupDeleteQueryDto {
  cascade?: boolean
}
