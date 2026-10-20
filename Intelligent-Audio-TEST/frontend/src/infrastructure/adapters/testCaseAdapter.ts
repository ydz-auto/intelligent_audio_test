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
import { TestType } from '../../domain/enums'
import { camelizeKeys, snakifyKeys } from '../../utils/keyTransform'

// ===== DTO → Domain =====

/**
 * 列表项 type → Domain testType。
 * 后端用例纯数据化后不存类型列，type 由 derive_case_test_type 从 config
 * 形态派生，取值恒为 'api'/'e2e'；非法/缺省值不映射，避免编辑模态窗
 * 被兜底锁成 E2E 形态（INT-196）。
 */
function toTestType(type?: string | null): TestCase['testType'] {
  if (type === TestType.API || type === TestType.E2E) {
    return type
  }
  return undefined
}

export function toTestCase(dto: TestCaseDto): TestCase {
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description ?? undefined,
    type: dto.type ?? undefined,
    testType: toTestType(dto.type),
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
    isFavorite: dto.is_favorite ?? undefined,
    deleted: dto.deleted ?? false,
    deletedAt: dto.deleted_at ?? undefined,
    deletedByUserId: dto.deleted_by_user_id ?? undefined,
    totalDuration: dto.total_duration ?? undefined,
    // INT-423/467：可见性 + 归属人（两端同名，显式映射）
    visibility: dto.visibility ?? undefined,
    createdByUserId: dto.created_by_user_id ?? undefined,
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
    testType: toTestType(dto.type),
    config: dto.config ? camelizeKeys(dto.config) as TestCase['config'] : undefined,
    algorithmParams: dto.algorithmParams ? camelizeKeys(dto.algorithmParams) as TestCase['algorithmParams'] : undefined,
    referenceParams: dto.referenceParams ? camelizeKeys(dto.referenceParams) as TestCase['referenceParams'] : undefined,
    groupId: dto.groupId ?? undefined,
    groupName: dto.groupName ?? undefined,
    tags: dto.tags ?? [],
    algorithmType: dto.algorithmType ?? undefined,
    createdAt: dto.createdAt ?? undefined,
    updatedAt: dto.updatedAt ?? undefined,
    isFavorite: dto.isFavorite ?? undefined,
    deleted: dto.deleted ?? false,
    deletedAt: dto.deletedAt ?? undefined,
    deletedByUserId: dto.deletedByUserId ?? undefined,
    totalDuration: dto.totalDuration ?? undefined,
    // INT-423/467：标签视图顶层 camelCase 输出
    visibility: dto.visibility ?? undefined,
    createdByUserId: dto.createdByUserId ?? undefined,
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
  const dto: TestCaseUpsertDto = {
    name: draft.name,
    description: draft.description,
    tags: draft.tags,
    // config 深度 snakify：fieldCode→field_code, roundNumber→round_number 等
    config: draft.config ? snakifyKeys(draft.config) as TestCaseUpsertDto['config'] : undefined,
    // algorithmParams/referenceParams 深度 snakify
    algorithm_params: draft.algorithmParams ? snakifyKeys(draft.algorithmParams) : undefined,
    reference_params: draft.referenceParams ? snakifyKeys(draft.referenceParams) : undefined,
    algorithm_type: draft.algorithmType,
    // INT-423/467：新建/编辑可见性（缺省不发，后端回落 shared）
    visibility: draft.visibility,
  };
  // 分组归属：groupId 存在时优先；新建分组流（handleCaseSave）清掉 groupId 仅携带 group 名，
  // 此时回退 group 名交后端按名称解析/自动建组（与 task_service create/update 契约一致，INT-195）
  if (draft.groupId != null && draft.groupId !== '') {
    dto.group_id = draft.groupId;
  } else if (draft.group) {
    dto.group = draft.group;
  }
  return dto;
}
