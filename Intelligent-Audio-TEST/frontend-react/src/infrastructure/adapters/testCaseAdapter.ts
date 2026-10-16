/**
 * 用例 DTO→Domain 适配器（infrastructure/adapters 层；10_测试执行.md §9）。
 * 消费 dto/ 原始 snake_case 类型，产出 domain 模型；现 Vue testCaseAdapter.ts 平移。
 */
import type {
  CaseDeviceResult,
  CaseExecutionDetail,
} from '@/domain/models/testExecution'
import type { TestCase } from '@/domain/models/testCase'
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
    updatedAt: dto.updated_at,
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
