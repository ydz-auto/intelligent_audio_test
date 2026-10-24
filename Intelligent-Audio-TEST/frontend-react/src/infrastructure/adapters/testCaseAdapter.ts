/**
 * 用例 DTO→Domain 适配器（infrastructure/adapters 层；10_测试执行.md §9）。
 * 消费 dto/ 原始 snake_case 类型，产出 domain 模型；现 Vue testCaseAdapter.ts 平移。
 */
import type {
  CaseAudioResult,
  CaseDeviceResult,
  CaseExecutionDetail,
  CaseMetricConfig,
  CaseMetricPoint,
  CaseMetricRow,
  CaseRoundTab,
} from '@/domain/models/testExecution'
import type { CaseResultForReview } from '@/domain/models/review'
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
    // 编辑回填/保存合并用：原始 config / algorithm_params / reference_params 透传
    // （值内 snake_case 契约与 Vue 基准一致，见 domain/models/testCase.ts 注释）
    config: dto.config ?? null,
    algorithmParams: dto.algorithm_params ?? null,
    referenceParams: dto.reference_params ?? null,
  }
}

/**
 * 指标行（行=指标、列=设备，V9.7.10 currentRoundTableData 同口径）：
 * 指标顺序以 metric_configs 为准，再补数据里出现但配置外的维度；只对「本 Tab 有数据」的维度出行。
 */
function buildMetricRows(
  devices: CaseDeviceResult[],
  metricConfigs: CaseMetricConfig[],
  accept: (round: number | undefined) => boolean
): CaseMetricRow[] {
  const present: string[] = []
  for (const device of devices) {
    for (const point of device.metrics) {
      if (accept(point.round) && !present.includes(point.dimension)) present.push(point.dimension)
    }
  }
  const configured = metricConfigs.map((c) => c.name)
  const dimensionOrder = [
    ...configured.filter((name) => present.includes(name)),
    ...present.filter((name) => !configured.includes(name)),
  ]

  return dimensionOrder.map((dimension) => {
    const values: Record<string, string> = {}
    for (const device of devices) {
      const point = device.metrics.find(
        (m) => m.dimension === dimension && accept(m.round)
      )
      if (point) values[device.deviceName] = point.value
    }
    return { dimension, values }
  })
}

/**
 * 轮次 Tab（V9.7.10 TestCaseReportDetail roundTabs:1119-1155 同口径）：
 * - 有轮次标记 → 「第1轮…第N轮」，轮次由维度 round + 结果音频轮次合并升序；
 * - 「整体」仅在整体维度有评估值时才出现（照 tabHasMetricData）；
 * - 无任何轮次标记 → 单个「指标」Tab（不渲染 Tab 栏；旧 Vue 的「单轮」形态）。
 * `@round:{n}` / `@overall` 只是内部键，不再作为列头（INT-1723 规范回写）。
 */
function buildRoundTabs(
  devices: CaseDeviceResult[],
  metricConfigs: CaseMetricConfig[],
  extraRounds: Array<number | null | undefined>
): CaseRoundTab[] {
  const allPoints = devices.flatMap((d) => d.metrics)
  const hasRoundTag = allPoints.some((p) => p.round != null)
  if (!hasRoundTag) {
    return [
      {
        key: 'all',
        label: '指标',
        round: null,
        kind: 'all',
        rows: buildMetricRows(devices, metricConfigs, () => true),
      },
    ]
  }

  const rounds = [
    ...new Set([
      ...allPoints.filter((p) => p.round != null).map((p) => p.round as number),
      ...extraRounds.filter((r): r is number => r != null),
    ]),
  ].sort((a, b) => a - b)

  const tabs: CaseRoundTab[] = rounds.map((round) => ({
    key: `round:${round}`,
    label: `第${round}轮`,
    round,
    kind: 'round',
    rows: buildMetricRows(devices, metricConfigs, (r) => r === round),
  }))

  // 「整体」无评估数据时不显示（照 V9.7.10 tabHasMetricData）
  const overallPoints = allPoints.filter((p) => p.round == null)
  const hasOverallData = overallPoints.some((p) => p.value !== '—')
  if (hasOverallData) {
    tabs.push({
      key: 'overall',
      label: '整体',
      round: null,
      kind: 'overall',
      rows: buildMetricRows(devices, metricConfigs, (r) => r == null),
    })
  }
  return tabs
}

/** 结果音频：result_audios（设备键 → 音频项，无轮次信息）+ algorithm_results 里 param_type=audio_file 的项 */
function buildResultAudios(dto: CaseDetailDto): CaseAudioResult[] {
  const fromResultAudios = Object.entries(dto.result_audios ?? {}).flatMap(([device, audios]) =>
    (audios ?? []).map((audio) => ({
      audioName: audio.filename ?? audio.param_code ?? '音频',
      deviceName: device || null,
      round: null,
      url: audio.url ?? null,
      path: null,
    }))
  )
  const fromAlgorithm = (dto.algorithm_results ?? [])
    .filter((r) => r.param_type === 'audio_file' && typeof r.value === 'string' && r.value)
    .map((r) => ({
      audioName: r.label ?? r.param_code,
      // algorithm_results.device 是「{id}-{设备名}-{版本}」内部标识（实测 9-pura90小艺-1.0.0），
      // 不是可读设备名 → 结果音频行只展示 label，不重复设备标识
      deviceName: null,
      // algorithm_results.round_number 为 1 起轮次（param_code `user_wav@round:1` 同值）
      round: r.round_number ?? null,
      url: null,
      path: r.value as string,
    }))
  return [...fromResultAudios, ...fromAlgorithm]
}

/** 参考/输入音频（detail audio_list；音频库 id 用于 /audios/{id}/stream 取流） */
function buildReferenceAudios(dto: CaseDetailDto): CaseAudioResult[] {
  return (dto.audio_list ?? []).map((audio) => ({
    audioName: audio.filename || `音频 ${audio.id}`,
    deviceName: null,
    audioId: audio.id ?? null,
    // audio_list 项为 camelCase（roundNumber 1 起；旧用例可能缺省）
    round: audio.roundNumber ?? audio.round_number ?? null,
    url: audio.url ?? null,
    path: null,
  }))
}

/**
 * 用例执行详情 DTO → Domain（INT-1688）。
 * 真实契约：detail.devices 是**设备名字符串数组**；维度值只在 /results 结果行的 dimensions 里
 * （round_number: null=整体、0 起=第 n+1 轮）。因此这里把 detail（名称/维度配置/音频）与
 * results（结果行/维度值/ASR）组合成弹窗需要的设备×维度结构。
 */
export function caseDetailFromDto(
  dto: CaseDetailDto,
  results: CaseResultForReview[] = []
): CaseExecutionDetail {
  const metricConfigs: CaseMetricConfig[] = (dto.metric_configs ?? []).map((c) => ({
    code: c.code,
    name: c.name,
  }))
  const resultRows = results ?? []
  const rowByDevice = new Map<string, CaseResultForReview>()
  for (const row of resultRows) {
    if (row.deviceName && !rowByDevice.has(row.deviceName)) rowByDevice.set(row.deviceName, row)
  }

  const devices: CaseDeviceResult[] = (dto.devices ?? []).map((deviceName) => {
    const row = rowByDevice.get(deviceName)
    const metrics: CaseMetricPoint[] = (row?.dimensions ?? []).map((d) => ({
      dimension: d.name,
      // round_number 0 起 = 第 n+1 轮；null = 整体评估（无轮次标记）
      round: d.roundNumber == null ? undefined : d.roundNumber + 1,
      value: d.value == null ? '—' : String(d.value),
    }))
    return {
      resultId: row?.id ?? null,
      deviceId: row?.deviceId ?? null,
      deviceName,
      executionStatus: row?.executionStatus ?? null,
      metrics,
      asrReference: row?.asrResult ?? null,
      translationReference: row?.translationResult ?? null,
    }
  })

  const resultAudios = buildResultAudios(dto)
  const referenceAudios = buildReferenceAudios(dto)

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
    metricConfigs,
    // 轮次 Tab 也吸收结果/参考音频出现的轮次（照 V9.7.10 roundTabs 从字段提取轮次）
    roundTabs: buildRoundTabs(devices, metricConfigs, [
      ...resultAudios.map((a) => a.round),
      ...referenceAudios.map((a) => a.round),
    ]),
    devices,
    resultAudios,
    referenceAudios,
    results: resultRows,
  }
}
