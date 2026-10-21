/**
 * 用例批量操作 API（infrastructure/api 层；INT-710 接线）。
 * POST /testcases/batch（testcase_bp.py:68 batch_action → TestCaseCommandService.batch_action），
 * 载荷对照旧 Vue testcasesApi.toBatchActionDto 的 camelCase→snake_case 顶层映射
 * （算法/设备/声压/噪声/维度/参考刷新/移动/复制/标签/自动命名）。
 * 顶层显式映射上行为 snake_case（Infrastructure 独占），值内 Dict 为动态结构原样透传——
 * 与 Vue 基准一致（如 playback_devices.deviceId 保持 camelCase，后端 gRPC 实体层消费）。
 * 页面/应用层只见 camelCase 领域载荷。
 */
import { apiClient } from './client'

/** 批量操作动作（对照旧 Vue testcasesApi.batchAction 的 action 取值） */
export type TestcaseBatchAction =
  | 'update_algorithm_params'
  | 'update_playback_devices'
  | 'update_spl'
  | 'update_noise'
  | 'update_dimensions'
  | 'refresh_reference'
  | 'auto_generate_name'
  | 'move_to_group'
  | 'copy_to_group'
  | 'copy_by_group'
  | 'add_tags'
  | 'remove_tags'
  | 'rename_tag'

/** 轮次范围（§5.3.5 口径）：所有轮次统一 / 指定轮次统一 / 逐轮设置每轮可不同 */
export type TestcaseRoundMode = 'all' | 'specific' | 'per_round'

export interface TestcaseBatchPayload {
  /** 专属参数（update_algorithm_params）：{fieldCode: value} */
  algorithmParams?: Record<string, unknown>
  /** 播放设备（update_playback_devices）：{ deviceId }（deviceId camelCase 透传，Vue 基准） */
  playbackDevices?: Record<string, unknown>
  /** 声压（update_spl）：数值或 { value }（Vue 基准 { value }） */
  spl?: number | Record<string, unknown>
  /** 噪声（update_noise） */
  noiseAudioId?: number | string
  noiseSpl?: number
  noiseDeviceIds?: (number | string)[]
  /** 评估维度（update_dimensions）：主维度数组 + testType + 可选 roundDimensions/multiDimensions */
  dimensions?: Array<Record<string, unknown>>
  testType?: string
  roundDimensions?: Record<string, unknown[]>
  multiDimensions?: Array<Record<string, unknown>>
  /** 目标分组（move_to_group / copy_to_group） */
  targetGroupId?: string
  /** 按分组整体复制（copy_by_group，task_service TestCaseBatchCopyMoveMixin._batch_copy_by_group） */
  groupName?: string
  /** 标签（add_tags / remove_tags） */
  tags?: string[]
  oldTagName?: string
  newTagName?: string
  /** 应用层级（声压/设备/噪声用；target/case-bg/segment-bg/interferer/voiceprint 或 Vue 口径 audio/caseBackgroundNoise/...） */
  targets?: string[]
  /** 轮次范围（三档） */
  roundMode?: TestcaseRoundMode
  roundNumbers?: number[]
  /** 逐轮设置（per_round）：{轮次号: 值}，"-1" 代表最后一轮（后端动态解析） */
  roundValues?: Record<string, unknown>
  /** 整体设置（case 级跨轮次）：如整体背景噪声 */
  caseLevel?: Record<string, unknown>
}

export interface TestcaseBatchResult {
  /** 异步任务（refresh_reference 返回 task_id） */
  taskId?: string | null
  updatedCount?: number
  failedCount?: number
  refreshedTestCaseIds?: string[]
}

/** camelCase → snake_case 顶层 key 映射（对照 Vue BATCH_ACTION_KEY_MAP，值内 Dict 原样透传） */
const BATCH_ACTION_KEY_MAP: Record<string, string> = {
  algorithmParams: 'algorithm_params',
  playbackDevices: 'playback_devices',
  noiseAudioId: 'noise_audio_id',
  noiseSpl: 'noise_spl',
  noiseDeviceIds: 'noise_device_ids',
  targetGroupId: 'target_group_id',
  groupName: 'group_name',
  roundMode: 'round_mode',
  roundNumbers: 'round_numbers',
  roundDimensions: 'round_dimensions',
  multiDimensions: 'multi_dimensions',
  oldTagName: 'old_tag_name',
  newTagName: 'new_tag_name',
  roundValues: 'round_values',
  caseLevel: 'case_level',
}

/** 批量操作请求体：浅层显式映射上行为 snake_case（Infrastructure 独占），未识别 key 原样透传 */
function toBatchActionDto(
  action: TestcaseBatchAction,
  ids: string[],
  payload: TestcaseBatchPayload
): Record<string, unknown> {
  const body: Record<string, unknown> = { action, ids }
  for (const [key, value] of Object.entries(payload)) {
    if (value === undefined || value === null) continue
    const snakeKey = BATCH_ACTION_KEY_MAP[key] ?? key
    body[snakeKey] = value
  }
  return body
}

/** 批量操作统一出口（POST /testcases/batch） */
export async function batchTestcaseAction(
  action: TestcaseBatchAction,
  ids: string[],
  payload: TestcaseBatchPayload = {}
): Promise<TestcaseBatchResult> {
  const raw = await apiClient.post<Record<string, unknown>>(
    '/testcases/batch',
    toBatchActionDto(action, ids, payload)
  )
  return {
    taskId:
      (raw?.task_id as string | undefined) ??
      (raw?.taskId as string | undefined) ??
      null,
    updatedCount:
      (raw?.updated_count as number | undefined) ??
      (raw?.updatedCount as number | undefined) ??
      0,
    failedCount:
      (raw?.failed_count as number | undefined) ??
      (raw?.failedCount as number | undefined) ??
      0,
    refreshedTestCaseIds:
      (raw?.refreshed_test_case_ids as string[] | undefined) ??
      (raw?.refreshedTestCaseIds as string[] | undefined) ??
      [],
  }
}

/** 参考刷新任务状态（GET /testcases/refresh_task/{taskId}；对照 Vue pollRefreshTaskStatus） */
export interface RefreshTaskStatus {
  taskId: string
  status: string
  total: number
  updated: number
  failed: number
  progress: number
  startedAt: string | null
  completedAt: string | null
  failedCases: string[]
  errorMessage: string | null
}

export async function fetchRefreshTaskStatus(
  taskId: string
): Promise<RefreshTaskStatus> {
  const dto = await apiClient.get<Record<string, unknown>>(
    `/testcases/refresh_task/${taskId}`
  )
  return {
    taskId: (dto?.task_id as string) ?? taskId,
    status: (dto?.status as string) ?? 'unknown',
    total: (dto?.total as number) ?? 0,
    updated: (dto?.updated as number) ?? 0,
    failed: (dto?.failed as number) ?? 0,
    progress: (dto?.progress as number) ?? 0,
    startedAt: (dto?.started_at as string) ?? null,
    completedAt: (dto?.completed_at as string) ?? null,
    failedCases: ((dto?.failed_cases as string[]) ?? []).slice(0, 10),
    errorMessage: (dto?.error_message as string) ?? null,
  }
}
