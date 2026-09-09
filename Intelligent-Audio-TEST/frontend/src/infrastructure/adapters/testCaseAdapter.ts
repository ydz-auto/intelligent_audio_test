/**
 * TestCase Adapter —— TestCaseDto(snake_case) ⇄ TestCase(camelCase)
 *
 * config/algorithmParams/referenceParams 为透传结构：
 * - DTO 侧键名 algorithm_params / reference_params 转为 camelCase 字段名
 * - 其内部结构（轮次、音频配置）由 camelizeKeys/snakifyKeys 做深度递归转换
 * 显式逐字段映射，禁止 ...raw/...dto 透传（分层架构对齐 W1-A）。
 */
import type { TestCase, TestCaseDraft, TagViewItem } from '../../domain/model/testCase'
import type { TagViewCaseDto, TagViewItemDto, TestCaseDto, TestCaseUpsertDto } from '../dto/testCaseDto'
import { camelizeKeys, snakifyKeys } from '../../utils/keyTransform'

// ===== DTO → Domain =====

export function toTestCase(dto: TestCaseDto): TestCase {
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description ?? undefined,
    type: dto.type ?? undefined,
    // config 深度 camelize：field_code→fieldCode, round_number→roundNumber 等
    config: dto.config ? camelizeKeys(dto.config) as TestCase['config'] : undefined,
    // algorithm_params/reference_params 深度 camelize
    algorithmParams: dto.algorithm_params ? camelizeKeys(dto.algorithm_params) as TestCase['algorithmParams'] : undefined,
    referenceParams: dto.reference_params ? camelizeKeys(dto.reference_params) as TestCase['referenceParams'] : undefined,
    groupId: dto.group_id ?? undefined,
    groupName: dto.group_name ?? undefined,
    tags: dto.tags ?? [],
    algorithmType: dto.algorithm_type ?? undefined,
    createdAt: dto.created_at ?? undefined,
    updatedAt: dto.updated_at ?? undefined,
    totalDuration: dto.total_duration ?? undefined,
  }
}

export function toTestCaseList(dtos: TestCaseDto[] | null | undefined): TestCase[] {
  return (dtos ?? []).map(toTestCase)
}

/**
 * 标签视图内层用例 → TestCase。
 * 后端 view=tag 的用例行顶层直接输出 camelCase（groupId/groupName/...），
 * 与普通列表 DTO（snake_case）不同；config/algorithmParams/referenceParams
 * 仍为原始嵌套结构，需与 toTestCase 一致做深度 camelize。
 */
export function toTagViewCase(dto: TagViewCaseDto): TestCase {
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description ?? undefined,
    type: dto.type ?? undefined,
    config: dto.config ? camelizeKeys(dto.config) as TestCase['config'] : undefined,
    algorithmParams: dto.algorithmParams ? camelizeKeys(dto.algorithmParams) as TestCase['algorithmParams'] : undefined,
    referenceParams: dto.referenceParams ? camelizeKeys(dto.referenceParams) as TestCase['referenceParams'] : undefined,
    groupId: dto.groupId ?? undefined,
    groupName: dto.groupName ?? undefined,
    tags: dto.tags ?? [],
    algorithmType: dto.algorithmType ?? undefined,
    createdAt: dto.createdAt ?? undefined,
    updatedAt: dto.updatedAt ?? undefined,
    totalDuration: dto.totalDuration ?? undefined,
  }
}

/** 标签视图 item（DTO）→ TagViewItem（Domain） */
export function toTagViewItem(dto: TagViewItemDto): TagViewItem {
  return {
    tag: dto.tag,
    testCases: (dto.testCases ?? []).map(toTagViewCase),
  }
}

// ===== Domain → DTO（请求体） =====

export function toTestCaseUpsertDto(draft: TestCaseDraft): TestCaseUpsertDto {
  return {
    name: draft.name,
    description: draft.description,
    type: draft.type,
    group_id: draft.groupId,
    tags: draft.tags,
    // config 深度 snakify：fieldCode→field_code, roundNumber→round_number 等
    config: draft.config ? snakifyKeys(draft.config) as TestCaseUpsertDto['config'] : undefined,
    // algorithmParams/referenceParams 深度 snakify
    algorithm_params: draft.algorithmParams ? snakifyKeys(draft.algorithmParams) : undefined,
    reference_params: draft.referenceParams ? snakifyKeys(draft.referenceParams) : undefined,
    algorithm_type: draft.algorithmType,
  }
}
