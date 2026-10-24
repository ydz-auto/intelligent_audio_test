/**
 * 音频上传 API（infrastructure 层；INT-714 接线——导入音频 + 生成测试用例真实流程）。
 * 对照后端 api_gateway/routes/audio_bp.py 上传族 + 旧 Vue uploadProcess.ts：
 *   POST /api/v1/audios/upload/init          → { task_id }（每批一次，多文件复用）
 *   POST /api/v1/audios/upload/register      → files[]（file_id/total_chunks/chunk_size）
 *   POST /api/v1/audios/upload/chunk         （multipart：file_id/chunk_index/total_chunks/task_id/chunk）
 *   POST /api/v1/audios/upload/merge         → { audio_id, test_case_id, test_case_count }
 * 载荷字段全 snake_case（MergeChunksRequest 契约；INT-714 口径修订：test_types 不再由前端传——
 * 用户不再选择用例类型，merge 缺省时后端 audio 服务默认 ['api'] 落库
 * （round_config_service.py data.get('test_types', ['api'])）；create_test_case 控制是否生成）。
 * md5 不做浏览器计算（无 spark-md5 依赖），注册传空串，后端不据此秒传；同批同名文件避免重复入库。
 */
import { apiClient } from './client'
import type {
  UploadDevicePlan,
  UploadDimensionPlan,
} from '@/domain/models/uploadRoundScope'

/** 上传任务初始化（POST /upload/init） */
export async function initUploadTask(): Promise<string> {
  const dto = await apiClient.post<{ task_id?: string }>('/audios/upload/init', {})
  const taskId = dto?.task_id
  if (!taskId) throw new Error('初始化上传任务失败：未返回 task_id')
  return taskId
}

/** 播放设备选项（GET /playback-devices；上传选项「播放设备」下拉，真实数据） */
export interface PlaybackDeviceOption {
  id: number
  name: string
  model: string
  deviceType: string
  /** 通道号（§5.7.4 重新扫描按 name|channelIndex 去重，同名同型号不同通道不能被吞） */
  channelIndex: number | null
}

export async function fetchPlaybackDevices(): Promise<PlaybackDeviceOption[]> {
  const dto = await apiClient.get<{
    items?: Array<{
      id?: number
      name?: string
      model?: string | null
      device_type?: string | null
      channel_index?: number | null
    }>
  }>('/playback-devices', { params: { page: 1, per_page: 100 } })
  return (dto?.items ?? []).map((d) => ({
    id: Number(d.id),
    name: d.name ?? '',
    model: d.model ?? '',
    deviceType: d.device_type ?? '',
    channelIndex: d.channel_index ?? null,
  }))
}

/** 注册待上传文件（POST /upload/register；返回每个文件的 file_id 与分片参数） */
export interface RegisteredUploadFile {
  fileId: string
  filename: string
  totalChunks: number
  chunkSize: number
  status: string
}

export async function registerUploadFiles(
  taskId: string,
  files: Array<{ name: string; size: number; relativePath?: string }>
): Promise<RegisteredUploadFile[]> {
  const dto = await apiClient.post<{ files?: Array<Record<string, unknown>> }>(
    '/audios/upload/register',
    {
      task_id: taskId,
      files: files.map((f) => ({
        name: f.name,
        size: f.size,
        md5: '',
        relative_path: f.relativePath ?? '',
      })),
    }
  )
  return (dto?.files ?? []).map((f) => ({
    fileId: String(f.file_id ?? ''),
    filename: String(f.filename ?? ''),
    totalChunks: Number(f.total_chunks ?? 1),
    chunkSize: Number(f.chunk_size ?? 5 * 1024 * 1024),
    status: String(f.status ?? 'pending'),
  }))
}

/** 上传单个分片（POST /upload/chunk，multipart） */
export async function uploadChunk(
  taskId: string,
  fileId: string,
  chunkIndex: number,
  totalChunks: number,
  chunk: Blob
): Promise<void> {
  const form = new FormData()
  form.append('file_id', fileId)
  form.append('chunk_index', String(chunkIndex))
  form.append('total_chunks', String(totalChunks))
  form.append('task_id', taskId)
  form.append('chunk', chunk, 'chunk')
  await apiClient.post('/audios/upload/chunk', form)
}

/** merge 载荷单轮音频（schemas/testcase.py TestCaseAudioConfigItem：audio_name/play_order/spl/playback_device_id） */
export interface UploadRoundAudioConfig {
  /** 音频文件名（后端按它在本上传任务内匹配 audio_id） */
  audio_name: string
  /** 同轮内播放顺序（1..n 升序） */
  play_order: number
  /** 音频 id（组内先前文件 merge 返回后回填；未回填时后端按 audio_name 兜底匹配） */
  audio_id?: number
  spl?: number
  /** 播放设备（§5.7.7：逐轮设备写这里，不写顶层 playback_device_id） */
  playback_device_id?: number
  playback_device_name?: string
  background_noise?: unknown
  [key: string]: unknown
}

/** merge 载荷单轮配置（RoundConfigItem 子集；INT-1613：多轮由 JSON 用例文件定义） */
export interface UploadRoundConfig {
  /** 轮次号按数组下标 1..N 升序连续写（§5.7.6：下标 i = 第 i+1 轮） */
  round_number: number
  audios: UploadRoundAudioConfig[]
  background_noise?: unknown
  [key: string]: unknown
}

/** 提交的评估维度条目（§5.7.7：`{id, name, weight, threshold, round_scope}`；name 必填） */
export interface UploadDimensionItem {
  id: number
  name: string
  weight?: number
  threshold?: number
  /** single = 单轮维度（轮内 evaluation.dimensions）；multi = 多轮整体（顶层 dimensions 归并） */
  round_scope: 'single' | 'multi'
}

/** 生成测试用例配置（merge 载荷 test_case_config；照 TestCaseUploadConfig/RoundConfigItem 实测） */
export interface UploadTestCaseConfig {
  /** 是否生成测试用例（原 test_types.length>0 语义；用例类型由后端默认落库） */
  createTestCase: boolean
  /** 整组轮次（文件夹导入：JSON 用例解析结果或按文件夹推断；缺省时按当前文件单轮） */
  rounds?: UploadRoundConfig[]
  algorithmType: string | null
  algorithmParams: Array<{ field_code: string; field_value: unknown }>
  /** 单轮维度条目（各轮实际用到的 id 并集，含 name/weight；§5.7.7） */
  dimensions: UploadDimensionItem[]
  /** 多轮整体维度条目（顶层 round_scope='multi'；§5.7.7 阶段 B） */
  multiDimensions?: UploadDimensionItem[]
  /** 维度三档计划（§5.7.3）；不传 = dimensions 统一作用于所有轮次（阶段 A 口径） */
  dimensionPlan?: UploadDimensionPlan
  /** 播放设备三档计划（§5.7.4）；不传 = playbackDeviceId 统一作用于所有轮次 */
  devicePlan?: UploadDevicePlan
  /** 顶层 default_playback_device_id（all/specific = 统一值、per_round = 第 1 轮值；§5.7.7） */
  playbackDeviceId: number | null
  spl: number
  noiseAudioId: number | null
  noiseSpl: number
  inheritTags: boolean
  groupName: string | undefined
  tags: string[]
  audioType: string
  /** 标注文件解析结果（{format, code, data, source_language, target_language}；merge 载荷 annotations 落库） */
  annotations?: unknown[]
}

export interface MergeChunksResult {
  audioId: number | null
  /** 合并后音频真实名称（组内 rounds 回填 audio_id 的匹配键；后端 data.name） */
  audioName: string | null
  testCaseId: string | null
  testCaseCount: number
}

/** 维度 id 集 → 提交条目（元数据取 config.dimensions 目录；缺目录时回退「维度 {id}」保证 name 必填） */
function toDimensionItems(
  config: UploadTestCaseConfig,
  ids: number[]
): UploadDimensionItem[] {
  return ids.map((id) => {
    const numeric = Number(id)
    const found = config.dimensions.find((d) => d.id === numeric)
    return found ?? { id: numeric, name: `维度 ${numeric}`, round_scope: 'single' }
  })
}

/**
 * 单轮播放设备取值（§5.7.4 / §5.7.7）：
 * - 所有轮次：统一值；
 * - 指定轮次：勾中轮用统一值，未勾中的轮不写（保留 JSON 标注值 / 后端兜底）；
 * - 逐轮设置：各轮各自值，未设置的轮不写。
 */
function resolveRoundDeviceId(
  config: UploadTestCaseConfig,
  roundNumber: number
): number | null {
  const plan = config.devicePlan
  if (!plan || plan.mode === 'all') return config.playbackDeviceId
  if (plan.mode === 'specific') {
    return plan.specificRounds.includes(roundNumber) ? plan.uniformId : null
  }
  return plan.perRoundIds[roundNumber] ?? null
}

/**
 * 单轮评估维度取值（§5.7.3 / §5.7.7 阶段 B）：
 * - 所有轮次：轮内不写（统一集走顶层 dimensions，避免与顶层双口径）；
 * - 指定轮次 / 逐轮设置：轮内显式写（含空数组），顶层只放 multi。
 */
function resolveRoundDimensions(
  config: UploadTestCaseConfig,
  roundNumber: number
): UploadDimensionItem[] | null {
  const plan = config.dimensionPlan
  if (!plan || plan.mode === 'all') return null
  if (plan.mode === 'specific') {
    return toDimensionItems(
      config,
      plan.specificRounds.includes(roundNumber) ? plan.uniformIds : []
    )
  }
  return toDimensionItems(config, plan.perRoundIds[roundNumber] ?? [])
}

/**
 * merge 载荷轮次（§5.7.6/§5.7.7）：
 * - 整组 rounds 优先（文件夹导入的 JSON 用例解析结果 / 按文件夹推断），缺省时按当前文件单轮；
 * - `round_number` 一律按数组下标重写 1..N（JSON 里原有编号可能缺省或乱序）；
 * - 播放设备按三档写进 `audios[].playback_device_id`（只补空缺，不覆盖 JSON 自带值）；
 * - 评估维度按三档写 `rounds[].evaluation.dimensions`（「所有轮次」档不写，走顶层统一集）。
 */
function buildMergeRounds(
  config: UploadTestCaseConfig,
  filename: string
): UploadRoundConfig[] {
  const source =
    config.rounds && config.rounds.length > 0
      ? config.rounds
      : [{ round_number: 1, audios: [{ audio_name: filename, play_order: 1 }] }]
  return source.map((round, index) => {
    const roundNumber = index + 1
    const deviceId = resolveRoundDeviceId(config, roundNumber)
    const roundDimensions = config.createTestCase
      ? resolveRoundDimensions(config, roundNumber)
      : null
    return {
      ...round,
      round_number: roundNumber,
      audios: (round.audios ?? []).map((audio) =>
        deviceId != null && audio.playback_device_id == null
          ? { ...audio, playback_device_id: deviceId }
          : { ...audio }
      ),
      ...(roundDimensions != null
        ? { evaluation: { dimensions: roundDimensions } }
        : {}),
    }
  })
}

/**
 * 顶层 dimensions（§5.7.7）：
 * - 「所有轮次」档 = 统一 single 集 + multi 集（后端对未自带 evaluation 的轮次回填该集）；
 * - 「指定轮次」/「逐轮设置」= 只放 multi（逐轮 single 已写在轮内，顶层不放逐轮维度）。
 *
 * 「所有轮次」档只取 `dimensionPlan.uniformIds`（= UI 当前显示的已选集合）。
 * `config.dimensions` 是各档用到的 id 并集（兼作逐轮条目的 name/weight 目录），含切档前
 * 逐轮档的残留值，直接当统一集会把旧值一并提交（审计 P2-1）。
 */
function buildTopLevelDimensions(
  config: UploadTestCaseConfig
): UploadDimensionItem[] | undefined {
  if (!config.createTestCase) return undefined
  const multi = config.multiDimensions ?? []
  const plan = config.dimensionPlan
  if (!plan) return [...config.dimensions, ...multi]
  if (plan.mode !== 'all') return multi
  return [...toDimensionItems(config, [...new Set(plan.uniformIds)]), ...multi]
}

/** 合并分片 + 按需生成测试用例（POST /upload/merge） */
export async function mergeChunks(
  taskId: string,
  fileId: string,
  filename: string,
  config: UploadTestCaseConfig
): Promise<MergeChunksResult> {
  const createTestCase = config.createTestCase
  const dto = await apiClient.post<{
    audio_id?: number | string
    name?: string
    test_case_id?: string | null
    test_case_count?: number
  }>('/audios/upload/merge', {
    file_id: fileId,
    task_id: taskId,
    create_test_case: createTestCase,
    // test_types 不传（INT-714 口径修订）：前端不再暴露用例类型选择，后端缺省默认 ['api'] 落库
    audio_type: config.audioType,
    algorithm_type: config.algorithmType ?? '',
    algorithm_params: config.algorithmParams,
    algorithm_relations: [],
    // 顶层 dimensions：所有轮次档 = single + multi；逐轮/指定轮档 = 只放 multi（§5.7.7）
    dimensions: buildTopLevelDimensions(config),
    tags: config.tags,
    inherit_tags: config.inheritTags,
    spl: config.spl,
    noise_audio_id: config.noiseAudioId,
    noise_spl: config.noiseSpl,
    // §5.7.7：顶层键名是 default_playback_device_id（建用例链路唯一消费的兜底缺省键）
    default_playback_device_id: config.playbackDeviceId,
    description: '',
    asr_text: '',
    annotations: config.annotations ?? [],
    test_case_config: {
      rounds: buildMergeRounds(config, filename),
      group_name: config.groupName || undefined,
      inherit_tags: config.inheritTags,
    },
  })
  return {
    audioId: dto?.audio_id != null ? Number(dto.audio_id) : null,
    audioName: dto?.name ?? null,
    testCaseId: dto?.test_case_id ?? null,
    testCaseCount: Number(dto?.test_case_count ?? 0),
  }
}

/** 单个文件完整上传（注册→分片→合并），带进度回调（0-100 每分片步进） */
export async function uploadSingleFile(
  taskId: string,
  file: File,
  config: UploadTestCaseConfig,
  onProgress?: (percent: number) => void
): Promise<MergeChunksResult> {
  const [registered] = await registerUploadFiles(taskId, [
    { name: file.name, size: file.size },
  ])
  if (!registered?.fileId) throw new Error(`注册文件失败：${file.name}`)

  const chunkSize = registered.chunkSize > 0 ? registered.chunkSize : 5 * 1024 * 1024
  const totalChunks = Math.max(1, Math.ceil(file.size / chunkSize))
  const actualTotal = registered.totalChunks || totalChunks

  for (let i = 0; i < totalChunks; i++) {
    const start = i * chunkSize
    const end = Math.min(start + chunkSize, file.size)
    const chunk = file.slice(start, end)
    await uploadChunk(taskId, registered.fileId, i, actualTotal, chunk)
    onProgress?.(Math.round(((i + 1) / totalChunks) * 90))
  }
  onProgress?.(95)
  const result = await mergeChunks(taskId, registered.fileId, file.name, config)
  onProgress?.(100)
  return result
}
