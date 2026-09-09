/**
 * Audio（音频资产）领域模型 —— camelCase
 * 对应后端 api_gateway/schemas/audio.py::AudioItem / AudioListData /
 * AudioListStats / AudioIdsData / TagListData / AudioAlgorithmRelationItem
 *
 * 枚举值保持后端原值（如 'dry' / 'noise' / 'prompt'），只转字段名。
 */
import { UploadStatus, TestType, RoundMode, type RoundModeType } from '@/domain/enums'

export type AudioAssetType = 'dry' | 'noise' | 'prompt' | 'mixed' | (string & {})

/** 音频标注条目（后端 annotations: List[Dict]，结构保持宽松但不开放索引签名） */
export interface AudioAnnotation {
  code?: string
  format?: string
  name?: string
  data?: unknown
  sourceLanguage?: string
  targetLanguage?: string
  [key: string]: unknown
}

/** 音频翻译条目（前端本地结构，随上传标注携带） */
export interface AudioTranslation {
  text: string
  direction: string
}

/** 音频文件完整模型（对应 AudioItem） */
export interface AudioInfo {
  id: string | number
  name: string
  originalFilename?: string
  filePath?: string
  size?: number
  duration?: number
  format?: string
  sampleRate?: number
  channels?: number
  bitrate?: number
  /** 音频类型（后端 audio_type 原值） */
  audioType?: AudioAssetType
  asrText?: string
  description?: string
  sourceLanguage?: string
  tags: string[]
  annotations: AudioAnnotation[]
  createdAt?: string
  updatedAt?: string
  /** 前端本地兼容别名（历史消费方依赖，W2 清理） */
  filename?: string
  filepath?: string
  /** 历史本地字段：音频类型（与 audioType 同值，历史消费方使用） */
  type?: AudioAssetType
  translations?: AudioTranslation[]
}

export type Audio = AudioInfo

/** 音频列表统计（对应 AudioListStats） */
export interface AudioListStats {
  totalFiles: number
  /** 人类可读的总大小，如 "1.2 GB" */
  totalSize: string
  /** 人类可读的总时长，如 "03:25:11" */
  totalDuration: string
  todayUploads: number
}

/** 上传中的文件（前端本地状态，非后端契约） */
export interface AudioUploadFile {
  file: File
  id: string
  fileId: string
  name: string
  size: number
  progress: number
  status: typeof UploadStatus[keyof typeof UploadStatus]
  error?: string
  md5?: string
  uploadedSize?: number
  totalChunks?: number
  chunkSize?: number
  uploadedChunks?: number[]
  audioId?: string | number
  folderGroupName?: string
  /** 前端本地兼容别名（历史消费方使用 errorMessage 展示上传失败原因，与 error 同值，W 清理） */
  errorMessage?: string
  /** 最子级文件夹名（无文件夹结构时为去扩展名的文件名），用于按分组独立创建测试用例 */
  groupKey?: string
  asrText?: string
  translations?: AudioTranslation[]
  tags?: string[]
  annotations?: AudioAnnotation[]
}

export interface AudioUploadTask {
  id: string
  files: AudioUploadFile[]
  /** 上传选项（camelCase key，Domain 定义见本文件 AudioUploadOptions） */
  options: AudioUploadOptions
  progress: number
  status: typeof UploadStatus[keyof typeof UploadStatus]
  totalFiles?: number
  completedFiles?: number
  failedFiles?: number
  totalSize?: number
  uploadedSize?: number
  startTime?: string
  endTime?: string
}

/** 音频-算法关联（对应 AudioAlgorithmRelationItem） */
export interface AudioAlgorithmRelation {
  algorithmType: string
  isPrimary: boolean
  weight: number
  params?: Record<string, unknown>
}

/** 标签列表（对应 TagListData：items + total 包装） */
export interface AudioTagList {
  items: string[]
  total: number
}

/** 音频 ID 列表查询结果（对应 AudioIdsData） */
export interface AudioIdsResult {
  ids: number[]
  total: number
}

// ===== 上传相关（前端本地状态，camelCase） =====

/** 上传选项（前端本地状态：camelCase key；发往后端时由 uploadProcess 转换） */
export interface AudioUploadOptions {
  audioType: 'dry' | 'noise' | 'prompt' | 'mixed'
  createTestCase: boolean
  tags: string[]
  description?: string
  testTypes: (typeof TestType[keyof typeof TestType])[]
  /** @deprecated 已移到 CaseForm 的 RoundConfigEditor 里配置 */
  playbackDeviceId?: string | number | null
  /** @deprecated 已移到 CaseForm 的 RoundConfigEditor 里配置 */
  spl?: number
  /** @deprecated 已移到 CaseForm 的 RoundConfigEditor 里配置 */
  noiseAudioId?: string | number | null
  /** @deprecated 已移到 CaseForm 的 RoundConfigEditor 里配置 */
  noiseSpl?: number
  inheritTags?: boolean
  /** 评估维度数组，每条可带 testType 标记属于 api/e2e（由 DimensionConfigData 展开而来） */
  dimensions?: SelectedEvaluationDimension[]
  /** API 维度设置（DimensionConfigPanel 结构：统一/指定轮次/逐轮 + 多轮整体评估维度） */
  apiDimensionConfig?: DimensionConfigData
  /** E2E 维度设置（DimensionConfigPanel 结构：统一/指定轮次/逐轮 + 多轮整体评估维度） */
  e2eDimensionConfig?: DimensionConfigData
  algorithmType?: string
  algorithmRelations?: Array<{
    algorithmType: string
    isPrimary: boolean
    weight: number
    params?: Record<string, any>
  }>
  algorithmParams?: any[]
  promptDeviceId?: string | number | null
  promptSourceLanguage?: string
  promptTargetLanguage?: string
  promptTranslationDirection?: string
  promptAlgorithmType?: string
  groupNameType?: 'root' | 'folder' | 'custom'
  customGroupName?: string
}

/** 评估维度选择项（camelCase 域模型；上行经 Infrastructure toEvaluationDimensionDto 转为后端协议原文 test_type/round_scope） */
export interface SelectedEvaluationDimension {
  id: number | string
  name: string
  weight?: number
  threshold?: number
  /** 标记该维度属于哪种测试类型，'api' / 'e2e'，未标记则通用 */
  testType?: typeof TestType[keyof typeof TestType]
  /** 维度使用范围：'single' = 每轮独立评估，'multi' = 多轮聚合评估。默认 'single' */
  roundScope?: 'single' | 'multi'
  /** 指定生效轮次（specific 模式展开后携带）；未指定则适用所有轮次。-1 表示最后一轮 */
  roundNumber?: number
}

/** 维度配置条目（维度设置面板的输出单元，可带权重/阈值） */
export interface DimensionItem {
  id: string | number
  name: string
  weight?: number
  threshold?: number
}

/** 维度配置数据（上传选项中的维度设置面板结构，对齐 DimensionConfigPanel 输出） */
export interface DimensionConfigData {
  /** 统一模式（all）/ 指定轮次（specific）共用的维度列表 */
  dimensions: DimensionItem[]
  /** 轮次模式：all = 所有轮次统一，specific = 指定轮次，per_round = 逐轮设置 */
  roundMode: RoundModeType
  /** specific 模式下选中的轮次序号列表（-1 = 最后一轮） */
  roundNumbers: number[]
  /** per_round 模式下逐轮维度（key 为轮次序号，-1 = 最后一轮） */
  roundDimensions?: Record<number, DimensionItem[]>
  /** 多轮整体评估维度（roundScope = 'multi'） */
  multiDimensions?: DimensionItem[]
}

/** 评估维度配置 */
export interface EvaluationDimensionsConfig {
  dimensions: SelectedEvaluationDimension[]
}

/** 音频统计摘要（前端展示用） */
export interface AudioStats {
  total: number
  dry: number
  noise: number
  prompt: number
  mixed: number
  totalFiles: number
  totalSize: string
  totalDuration: string
  todayUploads: number
}

/** 音频查询参数（前端 Domain；adapter 负责转 snake_case） */
export interface AudioQueryParams {
  page: number
  perPage: number
  search?: string
  keyword?: string
  type?: string
  /** 标签过滤参数：普通标签为字符串，带模式的标签为 { name, mode } 对象 */
  tags?: (string | { name: string; mode: string })[]
  sortBy?: string
  order?: 'asc' | 'desc'
  audioType?: string
  format?: string
  sampleRate?: string
  duration?: string
  direction?: string
}

/** 文件夹树节点（前端通用视图模型：服务端目录树 / 客户端构建树共用） */
export interface FolderNode {
  name: string
  path?: string
  count?: number
  fileCount?: number
  hasChildren?: boolean
  files: unknown[]
  folders: FolderNode[]
}
