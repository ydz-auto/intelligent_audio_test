/**
 * 用例 DTO→Domain 适配器（infrastructure/adapters 层；10_测试执行.md §9）。
 * 消费 dto/ 原始 snake_case 类型，产出 domain 模型；现 Vue testCaseAdapter.ts 平移。
 */
import type {
  CaseAudioResult,
  CaseDeviceResult,
  CaseExecutionDetail,
  CaseExecutionTarget,
  CaseMetricConfig,
  CaseMetricPoint,
  CaseMetricRow,
  CaseReferenceParam,
  CaseResultAudioField,
  CaseRoundTab,
} from '@/domain/models/testExecution'
import type { CaseResultForReview } from '@/domain/models/review'
import type {
  TestCase,
  TestCaseImportDuplicate,
  TestCaseImportPreview,
  TestCaseImportResult,
  TestCaseListItem,
  TestCasePreview,
} from '@/domain/models/testCase'
import type {
  CaseDetailDto,
  TestCaseImportPreviewDto,
  TestCaseImportResultDto,
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

/**
 * 设备标识 → 可读设备名（V9.7.10 getDeviceName:1001-1014 同口径）：
 * `result_audios` 的键与 `algorithm_results.device` 可能是设备 id（`9`）、
 * 算法侧内部标识（`9-pura90小艺-1.0.0`）或 `t<id>-<时间戳>-…`。先按 /results 结果行的
 * deviceId 匹配（最可靠），再退回内部标识 / 时间戳形态，都没有则原样展示。
 */
function resolveDeviceName(key: string, rows: CaseResultForReview[]): string {
  if (!key) return ''
  for (const row of rows) {
    if (row.deviceId != null && row.deviceName) {
      const id = String(row.deviceId)
      if (key === id || key.startsWith(`${id}-`)) return row.deviceName
    }
  }
  if (/^t\d+-\d{12}-/.test(key)) {
    const parts = key.split('-')
    if (parts.length >= 4) return parts.slice(3).join('-')
  }
  const internal = key.match(/^\d+-(.+?)-\d+(?:\.\d+)*$/)
  if (internal) return internal[1]
  return key
}

/** 目标类型中文（后端未回填 target_name 时的兜底展示前缀） */
const TARGET_TYPE_LABELS: Record<CaseExecutionTarget['targetType'], string> = {
  api: 'API',
  device: '设备',
}

/** 路由 id 缺失时的占位 */
const UNKNOWN_TARGET_ID = '—'

/**
 * 结果音频（detail `result_audios`：设备键 → 音频项，无轮次信息）。
 * 10 §5.2 ①（INT-1723 ②）：**不随轮次 Tab 过滤**，按设备分组全量展示
 * （组标题＝设备名，行＝filename，缺省 param_code，再缺省「音频N」）。
 */
function buildResultAudios(
  dto: CaseDetailDto,
  rows: CaseResultForReview[]
): CaseAudioResult[] {
  return Object.entries(dto.result_audios ?? {}).flatMap(([device, audios]) =>
    (audios ?? []).map((audio, index) => ({
      audioName: audio.filename || audio.param_code || `音频${index + 1}`,
      deviceName: resolveDeviceName(device, rows) || null,
      round: null,
      url: audio.url ?? null,
      path: null,
    }))
  )
}

/**
 * 执行结果音频字段（detail `algorithm_results` 里 `param_type=audio_file` 的项）。
 * V9.7.10 把这类项当**结果字段**（TestCaseReportDetail.vue:246/:297 播放钮），轮次标记取自
 * param_code 的 `@round:N` / `@overall` 后缀，回退 `round_number`；**不能**并进不按轮过滤的
 * 「结果音频」块（否则 7 轮用例会在每个 Tab 铺满全部音频）。
 * label 用原始参数名去掉内部后缀，轮次信息只在 chip 上展示一次（不重复）。
 */
function buildResultAudioFields(
  dto: CaseDetailDto,
  rows: CaseResultForReview[]
): CaseResultAudioField[] {
  return (dto.algorithm_results ?? [])
    .filter((r) => r.param_type === 'audio_file' && typeof r.value === 'string' && r.value)
    .map((r) => {
      const paramCode = r.param_code ?? ''
      const roundMatch = paramCode.match(/@round:(\d+)$/i)
      const overall = /@overall$/i.test(paramCode)
      const round = roundMatch
        ? Number(roundMatch[1])
        : overall
          ? null
          : (r.round_number ?? null)
      const base = paramCode.replace(/@round:\d+$/i, '').replace(/@overall$/i, '').trim()
      return {
        paramCode,
        label: base || r.label || paramCode || '音频',
        round,
        overall,
        dimensionName: r.dimension_name ?? null,
        // algorithm_results.device 是内部标识（实测 `9-pura90小艺-1.0.0`）→ 还原可读设备名
        deviceName: r.device ? resolveDeviceName(r.device, rows) || null : null,
        url: null,
        path: r.value as string,
      }
    })
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
  const resultRows = results ?? []
  /** 维度名 → 主/子层级信息（results dimensions；后端 ACL 现不下发 → 缺省按主维度平铺，V9.7.10 同口径） */
  const dimTypeByName = new Map<string, Pick<CaseMetricConfig, 'dimensionType' | 'parentDimensionName'>>()
  for (const row of resultRows) {
    for (const d of row.dimensions ?? []) {
      if (!dimTypeByName.has(d.name)) {
        dimTypeByName.set(d.name, {
          dimensionType: (d.dimensionType === 'sub' ? 'sub' : 'main') as 'main' | 'sub',
          parentDimensionName: d.parentDimensionName ?? undefined,
        })
      }
    }
  }
  const metricConfigs: CaseMetricConfig[] = (dto.metric_configs ?? []).map((c) => ({
    code: c.code,
    name: c.name,
    ...(dimTypeByName.get(c.name) ?? {}),
  }))
  // /results 行按目标 id 索引（API 行 api_id / 设备行 device_id；同目标多条取首条）
  const rowByTargetKey = new Map<string, CaseResultForReview>()
  for (const row of resultRows) {
    if (row.deviceId != null && !rowByTargetKey.has(`device:${row.deviceId}`)) {
      rowByTargetKey.set(`device:${row.deviceId}`, row)
    }
    if (row.apiId != null && !rowByTargetKey.has(`api:${row.apiId}`)) {
      rowByTargetKey.set(`api:${row.apiId}`, row)
    }
  }

  // 用例级执行目标（含未执行目标）：详情内逐目标 Tab / 指标列 / 执行结果全量展示。
  // INT-2194：历史任务 targets 可能只下发占位行（target_name / device_id / api_id 全空，
  // 仅带执行状态）——没有目标身份，兜底成「设备 —」会与 detail.devices 的真实设备并列出
  // 幽灵列 / 目标 Tab，无执行数据的用例还会因此误判 hasDeviceTable、丢掉「暂无执行结果」空态；
  // 这类占位行直接丢弃（真实设备列由下方 detail.devices 回填）。
  const targets: CaseExecutionTarget[] = (dto.targets ?? [])
    .filter((t) => !!t.target_name || t.device_id != null || t.api_id != null)
    .map((t) => {
      const targetType: CaseExecutionTarget['targetType'] =
        t.target_type === 'api' ? 'api' : 'device'
      const routeId = t.device_id ?? (t.api_id != null ? String(t.api_id) : null)
      const row = rowByTargetKey.get(
        targetType === 'api'
          ? `api:${t.api_id ?? routeId ?? ''}`
          : `device:${t.device_id ?? ''}`
      )
      return {
        taskCaseId: t.task_case_id ?? null,
        targetType,
        targetName:
          t.target_name ||
          row?.deviceName ||
          row?.apiName ||
          `${TARGET_TYPE_LABELS[targetType]} ${routeId ?? UNKNOWN_TARGET_ID}`,
        deviceId: t.device_id ?? null,
        apiId: t.api_id ?? null,
        executionStatus: t.execution_status ?? row?.executionStatus ?? null,
        evaluationStatus: t.evaluation_status ?? null,
      }
    })

  // 目标列：优先 targets 全量（API + 设备）；旧契约无 targets 时退回 detail.devices /
  // 结果行 api_name·device_name（与报告侧按设备/API 资源合并对比同口径）
  const targetNames: string[] =
    targets.length > 0
      ? targets.map((t) => t.targetName)
      : dto.devices && dto.devices.length > 0
        ? [...dto.devices]
        : Array.from(
            new Set(
              resultRows
                .map((r) => r.apiName ?? r.deviceName)
                .filter((n): n is string => !!n)
            )
          )
  for (const name of dto.devices ?? []) {
    if (name && !targetNames.includes(name)) targetNames.push(name)
  }
  for (const row of resultRows) {
    const name = row.deviceName ?? row.apiName
    if (name && !targetNames.includes(name)) targetNames.push(name)
  }

  const rowByTarget = new Map<string, CaseResultForReview>()
  for (const row of resultRows) {
    const key = row.deviceName ?? row.apiName
    if (key && !rowByTarget.has(key)) rowByTarget.set(key, row)
  }
  const targetByName = new Map(targets.map((t) => [t.targetName, t]))

  const devices: CaseDeviceResult[] = targetNames.map((targetName) => {
    const row = rowByTarget.get(targetName)
    const metrics: CaseMetricPoint[] = (row?.dimensions ?? []).map((d) => ({
      dimension: d.name,
      // round_number 0 起 = 第 n+1 轮；null = 整体评估（无轮次标记）
      round: d.roundNumber == null ? undefined : d.roundNumber + 1,
      value: d.value == null ? '—' : String(d.value),
      // INT-2088：得分/错误（评分指标「得分 / 详情·错误」数据源）
      score: d.score ?? null,
      error: d.errorMessage ?? null,
    }))
    return {
      resultId: row?.id ?? null,
      deviceId: row?.deviceId ?? null,
      deviceName: targetName,
      // 未执行目标：/results 无行 → 取目标行执行状态（pending 等），不再一律 null
      executionStatus: row?.executionStatus ?? targetByName.get(targetName)?.executionStatus ?? null,
      metrics,
      asrReference: row?.asrResult ?? null,
      translationReference: row?.translationResult ?? null,
    }
  })

  const resultAudios = buildResultAudios(dto, resultRows)
  const resultAudioFields = buildResultAudioFields(dto, resultRows)
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
    // 轮次 Tab 也吸收结果字段（algorithm_results 的 audio_file 项）/ 参考音频出现的轮次
    // （照 V9.7.10 roundTabs 从指标 key + 字段提取轮次）
    roundTabs: buildRoundTabs(devices, metricConfigs, [
      ...resultAudioFields.map((a) => a.round),
      ...referenceAudios.map((a) => a.round),
    ]),
    devices,
    targets,
    resultAudios,
    resultAudioFields,
    referenceAudios,
    results: resultRows,
    // INT-2088：参考参数 / 字段映射（网关 detail 实测已下发；用例参数缺数据源 → 恒空）
    referenceParams: normalizeReferenceParams(dto),
    fieldMapping: {
      result: toFieldParamCodes(dto.field_mapping?.result),
      reference: toFieldParamCodes(dto.field_mapping?.reference),
    },
    caseParams: {},
  }
}

/** 参考参数 DTO → Domain（{code: {type,value,segments,text,json,...}} → 补 code 键，透传其余） */
function normalizeReferenceParams(dto: CaseDetailDto): Record<string, CaseReferenceParam> {
  const result: Record<string, CaseReferenceParam> = {}
  for (const [code, value] of Object.entries(dto.reference_params ?? {})) {
    if (!value || typeof value !== 'object') continue
    result[code] = { code, ...(value as Record<string, unknown>) }
  }
  return result
}

/** 字段映射项（param_code / source_param）→ param_code 清单（report 域 field_mappings 同口径） */
function toFieldParamCodes(items?: Array<Record<string, unknown>>): string[] {
  return (items ?? [])
    .map((f) =>
      typeof f?.param_code === 'string'
        ? f.param_code
        : typeof f?.source_param === 'string'
          ? f.source_param
          : ''
    )
    .filter(Boolean)
}

/** 用例 ID（后端不同来源可能为字符串或数字）→ Domain 统一字符串 */
function toCaseId(value?: string | number | null): string | null {
  return value == null || value === '' ? null : String(value)
}

/** 导入预览 DTO → Domain（duplicates 的 existingId 统一字符串，缺失计数按清单长度兜底） */
export function testCaseImportPreviewFromDto(
  dto: TestCaseImportPreviewDto | null | undefined
): TestCaseImportPreview {
  const duplicates: TestCaseImportDuplicate[] = (dto?.duplicates ?? []).map(
    (item) => ({
      row: item.row ?? 0,
      name: item.name ?? null,
      id: toCaseId(item.id),
      existingId: toCaseId(item.existingId),
      existingName: item.existingName ?? null,
      matchedBy: item.matchedBy ?? null,
    })
  )
  return {
    totalRows: dto?.totalRows ?? 0,
    duplicates,
    duplicateCount: dto?.duplicateCount ?? duplicates.length,
    duplicateScanTruncated: dto?.duplicateScanTruncated ?? false,
    errors: (dto?.errors ?? []).map((e) => String(e)),
  }
}

/** 导入回执 DTO → Domain（snake_case 计数 → camelCase） */
export function testCaseImportResultFromDto(
  dto: TestCaseImportResultDto | null | undefined
): TestCaseImportResult {
  return {
    importedCount: dto?.imported_count ?? 0,
    updatedCount: dto?.updated_count ?? 0,
    skippedCount: dto?.skipped_count ?? 0,
    copiedCount: dto?.copied_count ?? 0,
    errors: (dto?.errors ?? []).map((e) => String(e)),
  }
}
