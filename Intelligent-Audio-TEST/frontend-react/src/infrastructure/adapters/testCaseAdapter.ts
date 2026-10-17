/**
 * 用例 DTO→Domain 适配器（infrastructure/adapters 层；10_测试执行.md §9）。
 * 消费 dto/ 原始 snake_case 类型，产出 domain 模型；现 Vue testCaseAdapter.ts 平移。
 */
import type {
  CaseDeviceResult,
  CaseExecutionDetail,
} from '@/domain/models/testExecution'
import type { TestCase, TestCaseListItem } from '@/domain/models/testCase'
import type {
  CaseDetailDto,
  TestCaseListItemDto,
} from '@/infrastructure/dto/testcase.dto'

export function testCaseFromDto(dto: TestCaseListItemDto): TestCase {
  const rounds = dto.config.rounds?.length ?? 1
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description,
    groupId: dto.group_id,
    groupName: dto.group_name,
    type: dto.type === 'api' ? 'api' : 'e2e',
    tags: dto.tags ?? [],
    algorithmType: dto.algorithm_type,
    rounds,
    totalDuration: dto.total_duration,
    updatedAt: dto.updated_at ?? null,
  }
}

/** 用例列表项 DTO → Domain（11_用例域.md §3.3 表格版式；INT-141 收藏/回收站字段） */
export function testCaseListItemFromDto(
  dto: TestCaseListItemDto
): TestCaseListItem {
  const rounds = dto.config.rounds?.length ?? 1
  // 音频条数由 config.rounds[].audios 派生（schemas/testcase.py RoundConfigItem.audios
  // 实测；0=无关联音频 → 预览钮置灰，11_用例域.md §3.3.2）
  const audioCount = (dto.config.rounds ?? []).reduce(
    (sum, round) => sum + ((round as { audios?: unknown[] }).audios?.length ?? 0),
    0
  )
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description,
    groupId: dto.group_id,
    groupName: dto.group_name,
    type: dto.type === 'api' ? 'api' : dto.type === 'e2e' ? 'e2e' : null,
    tags: dto.tags ?? [],
    algorithmType: dto.algorithm_type,
    createdAt: dto.created_at ?? null,
    updatedAt: dto.updated_at ?? null,
    isFavorite: dto.is_favorite ?? null,
    deleted: dto.deleted ?? null,
    deletedAt: dto.deleted_at ?? null,
    deletedByUserId: dto.deleted_by_user_id ?? null,
    totalDuration: dto.total_duration,
    rounds,
    audioCount,
  }
}

export function caseDetailFromDto(dto: CaseDetailDto): CaseExecutionDetail {
  const devices: CaseDeviceResult[] = (dto.devices ?? []).map((device) => ({
    deviceId: device.device_id,
    deviceName: device.device_name,
    status: device.status === 'pass' ? 'pass' : 'fail',
    duration: device.duration ?? 0,
    score: device.score,
    metrics: (device.metrics ?? []).map((m) => ({
      dimension: m.dimension,
      round: m.round ?? undefined,
      value: m.value == null ? '—' : String(m.value),
    })),
    asrReference: device.asr_reference,
    translationReference: device.translation_reference,
    audioResults: (device.audio_results ?? []).map((audio) => ({
      audioName: audio.audio_name,
      duration: audio.duration,
    })),
  }))

  return {
    caseId: dto.test_case_id,
    taskId: dto.task_id,
    name: dto.name,
    executionStatus: dto.execution_status,
    evaluationStatus: dto.evaluation_status,
    duration: dto.duration ?? 0,
    score: dto.score,
    devices,
  }
}
