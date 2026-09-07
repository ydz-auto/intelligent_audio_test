/**
 * Group Adapter —— GroupDto(snake_case) → Group Domain(camelCase)
 *
 * 出口契约：domain/model/testCase.ts::TestCaseGroup（消费方既有依赖，保持稳定）；
 * 查询参数/请求体转换在同文件下半部分。
 */
import type { TestCaseGroup } from '../../domain/model/testCase'
import type {
  GroupItemDto,
  GroupListDto,
  GroupCreateDto,
  GroupUpdateDto,
  GroupMoveCasesDto,
} from '../dto/groupDto'
import { toPaginated } from './commonAdapter'

// ===== DTO → Domain =====

/** GroupItemDto → TestCaseGroup（显式逐字段映射） */
export function toGroup(dto: GroupItemDto): TestCaseGroup {
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description ?? undefined,
    algorithmType: dto.algorithm_type ?? undefined,
    createdAt: dto.created_at || undefined,
    updatedAt: dto.updated_at || undefined,
    testCaseCount: dto.test_case_count ?? 0,
  }
}

/** 分组分页 → Paginated（复用 commonAdapter.toPaginated） */
export function toGroupList(dto: GroupListDto | null | undefined) {
  return toPaginated(dto, toGroup)
}

// ===== Domain → DTO（查询参数/请求体） =====

/**
 * 分组列表查询 → snake_case query
 * 后端 GroupListQuery：page / per_page（含 page_size 别名）/ algorithm_type /
 * test_type（含 type 别名）
 */
export function toGroupQueryDto(params: {
  page?: number
  perPage?: number
  algorithmType?: string
  testType?: string
  type?: string
  keyword?: string
}): Record<string, string | number> {
  const query: Record<string, string | number> = {}
  if (params.page !== undefined) query.page = params.page
  if (params.perPage !== undefined) query.per_page = params.perPage
  if (params.algorithmType) query.algorithm_type = params.algorithmType
  if (params.testType) query.test_type = params.testType
  else if (params.type) query.type = params.type
  if (params.keyword) query.keyword = params.keyword
  return query
}

/** 创建分组请求体：camelCase 表单 → GroupCreateDto */
export function toGroupCreateDto(input: {
  name: string
  description?: string
  algorithmType?: string
  id?: string
}): GroupCreateDto {
  return {
    id: input.id,
    name: input.name,
    description: input.description,
    algorithm_type: input.algorithmType,
  }
}

/** 更新分组请求体：camelCase 表单 → GroupUpdateDto */
export function toGroupUpdateDto(input: {
  name?: string
  description?: string
  algorithmType?: string
}): GroupUpdateDto {
  return {
    name: input.name,
    description: input.description,
    algorithm_type: input.algorithmType,
  }
}

/** 移动用例请求体：snake_case 键组装（sourceId 后端不消费，仅按需传 target） */
export function toGroupMoveCasesDto(targetGroupId: string, caseIds: (string | number)[]): GroupMoveCasesDto {
  return {
    case_ids: caseIds,
    target_group_id: targetGroupId,
  }
}
