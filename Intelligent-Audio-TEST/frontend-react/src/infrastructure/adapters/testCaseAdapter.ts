/**
 * 用例 DTO→Domain 适配器（infrastructure/adapters 层；10_测试执行.md §9）。
 * 消费 dto/ 原始 snake_case 类型，产出 domain 模型；现 Vue testCaseAdapter.ts 平移。
 */
import type {
  CaseDeviceResult,
  CaseExecutionDetail,
} from '@/domain/models/testExecution'
import type {
  TestCase,
  TestCaseListItem,
  TestCasePreview,
} from '@/domain/models/testCase'
import type {
  CaseDetailDto,
  TestCaseListItemDto,
  TestCasePreviewDto,
} from '@/infrastructure/dto/testcase.dto'

/**
 * 用例试听 DTO → Domain（§5.2；preview_type/playback_mode 后端默认 backend，这里归一为二值）。
 * audio_stream_urls 多轮时优先使用，单轮回退到 audio_stream_url（后端两键并存）。
 */
export function testCasePreviewFromDto(dto: TestCasePreviewDto): TestCasePreview {
  const urls = (dto.audio_stream_urls ?? []).filter(
    (url): url is string => typeof url === 'string' && url.length > 0
  )
  const single =
    typeof dto.audio_stream_url === 'string' && dto.audio_stream_url.length > 0
      ? dto.audio_stream_url
      : null
  return {
    testCaseId: dto.test_case_id,
    previewTaskId: dto.preview_task_id ?? null,
    status: dto.status,
    message: dto.message ?? null,
    duration:
      dto.duration != null && Number.isFinite(Number(dto.duration))
        ? Number(dto.duration)
        : null,
    playbackMode: dto.playback_mode === 'frontend' ? 'frontend' : 'backend',
    audioId: dto.audio_id ?? null,
    audioStreamUrl: single ?? urls[0] ?? null,
    audioStreamUrls: urls.length > 0 ? urls : single ? [single] : [],
  }
}

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
    // 编辑回填/保存合并用：原始 config / algorithm_params / reference_params 透传
    // （值内 snake_case 契约与 Vue 基准一致，见 domain/models/testCase.ts 注释）
    config: dto.config ?? null,
    algorithmParams: dto.algorithm_params ?? null,
    referenceParams: dto.reference_params ?? null,
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
    // 后端实测返回 case_name（无 name 字段）；name 留底兼容
    name: dto.case_name ?? dto.name ?? '',
    executionStatus: dto.execution_status,
    evaluationStatus: dto.evaluation_status,
    // INT-1066 返工 P3：后端 duration 为 null 时保持 null（头部不渲染「耗时」，旧 Vue 同口径）
    duration: dto.duration ?? null,
    score: dto.score,
    algorithmType: dto.algorithm_type ?? null,
    algorithmResults: (dto.algorithm_results ?? []).map((r) => ({
      paramCode: r.param_code,
      paramType: r.param_type ?? undefined,
      label: r.label ?? undefined,
      roundNumber: r.round_number ?? undefined,
      dimensionName: r.dimension_name ?? undefined,
      device: r.device ?? undefined,
      value: r.value,
      rounds: r.rounds,
    })),
    devices,
  }
}
