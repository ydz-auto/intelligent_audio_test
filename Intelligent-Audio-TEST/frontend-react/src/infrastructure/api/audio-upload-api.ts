/**
 * 音频上传 API（infrastructure 层；INT-714 接线——导入音频 + 生成测试用例真实流程）。
 * 对照后端 api_gateway/routes/audio_bp.py 上传族 + 旧 Vue uploadProcess.ts：
 *   POST /api/v1/audios/upload/init          → { task_id }（每批一次，多文件复用）
 *   POST /api/v1/audios/upload/register      → files[]（file_id/total_chunks/chunk_size）
 *   POST /api/v1/audios/upload/chunk         （multipart：file_id/chunk_index/total_chunks/task_id/chunk）
 *   POST /api/v1/audios/upload/merge         → { audio_id, test_case_id, test_case_count }
 * 载荷字段全 snake_case（MergeChunksRequest 契约；test_types/dimensions/algorithm_type/
 * algorithm_params/test_case_config 由后端 audio 服务消费生成对应类型用例，实测 e2e/api 均落 type）。
 * md5 不做浏览器计算（无 spark-md5 依赖），注册传空串，后端不据此秒传；同批同名文件避免重复入库。
 */
import { apiClient } from './client'

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
}

export async function fetchPlaybackDevices(): Promise<PlaybackDeviceOption[]> {
  const dto = await apiClient.get<{
    items?: Array<{
      id?: number
      name?: string
      model?: string | null
      device_type?: string | null
    }>
  }>('/playback-devices', { params: { page: 1, per_page: 100 } })
  return (dto?.items ?? []).map((d) => ({
    id: Number(d.id),
    name: d.name ?? '',
    model: d.model ?? '',
    deviceType: d.device_type ?? '',
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

/** 生成测试用例配置（merge 载荷 test_case_config；照 TestCaseUploadConfig/RoundConfigItem 实测） */
export interface UploadTestCaseConfig {
  /** e2e / api；空数组 = 不生成用例 */
  testTypes: string[]
  algorithmType: string | null
  algorithmParams: Array<{ field_code: string; field_value: unknown }>
  dimensions: number[]
  playbackDeviceId: number | null
  spl: number
  noiseAudioId: number | null
  noiseSpl: number
  inheritTags: boolean
  groupName: string | undefined
  tags: string[]
  audioType: string
}

export interface MergeChunksResult {
  audioId: number | null
  testCaseId: string | null
  testCaseCount: number
}

/** 合并分片 + 按需生成测试用例（POST /upload/merge） */
export async function mergeChunks(
  taskId: string,
  fileId: string,
  filename: string,
  config: UploadTestCaseConfig
): Promise<MergeChunksResult> {
  const createTestCase = config.testTypes.length > 0
  const dto = await apiClient.post<{
    audio_id?: number | string
    test_case_id?: string | null
    test_case_count?: number
  }>('/audios/upload/merge', {
    file_id: fileId,
    task_id: taskId,
    create_test_case: createTestCase,
    test_types: createTestCase ? config.testTypes : undefined,
    audio_type: config.audioType,
    algorithm_type: config.algorithmType ?? '',
    algorithm_params: config.algorithmParams,
    algorithm_relations: [],
    dimensions: createTestCase ? config.dimensions : undefined,
    tags: config.tags,
    inherit_tags: config.inheritTags,
    spl: config.spl,
    noise_audio_id: config.noiseAudioId,
    noise_spl: config.noiseSpl,
    playback_device_id: config.playbackDeviceId,
    description: '',
    asr_text: '',
    annotations: [],
    test_case_config: {
      rounds: [
        {
          round_number: 1,
          audios: [{ audio_name: filename, play_order: 1 }],
        },
      ],
      group_name: config.groupName || undefined,
      inherit_tags: config.inheritTags,
    },
  })
  return {
    audioId: dto?.audio_id != null ? Number(dto.audio_id) : null,
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
