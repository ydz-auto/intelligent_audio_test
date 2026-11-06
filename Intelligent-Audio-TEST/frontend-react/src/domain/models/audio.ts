/**
 * 音频域领域模型（domain 层；16_设备域.md §5 落位）。
 * 形态对照 api_gateway/schemas/audio.py AudioItem 实测：
 * id/name/original_filename/file_path/duration/size/sample_rate/channels/bitrate/
 * format/audio_type/asr_text/description/source_language/tags/annotations/created_at/updated_at。
 * 展示层只见 camelCase Domain；snake_case 转换落在 infrastructure/adapters/audioAdapter.ts。
 */

/** 音频类型（audio_type；§5.3.2 全实测选项） */
export type AudioType = 'dry' | 'noise' | 'prompt' | 'mixed'

export interface AudioAsset {
  id: number
  name: string
  originalFilename: string | null
  filePath: string | null
  /** 时长（秒） */
  duration: number | null
  /** 大小（字节） */
  size: number | null
  /** 采样率（Hz） */
  sampleRate: number | null
  channels: number | null
  bitrate: number | null
  /** 格式：MP3/WAV/FLAC/AAC/M4A（大写） */
  format: string | null
  audioType: AudioType | null
  asrText: string | null
  description: string | null
  sourceLanguage: string | null
  tags: string[]
  annotations: Array<Record<string, unknown>>
  createdAt: string | null
  updatedAt: string | null
}

/**
 * 格式转换参数（§3.3.1；POST /audios/{id}/convert 对照 ConvertFormatRequest）。
 * 附加参数全部可选，不传时后端保持仅转换格式的原行为；
 * 位深度仅对无损格式（WAV/FLAC）生效，比特率仅对有损格式（MP3/AAC）生效。
 */
export interface AudioConvertOptions {
  /** 目标格式（输出白名单 MP3/WAV/FLAC/AAC） */
  format: string
  /** 目标采样率（Hz，支持 8000-192000） */
  sampleRate?: number
  /** 目标声道数（1-8） */
  channels?: number
  /** 目标位深度（bit，支持 8/16/24/32） */
  bitDepth?: number
  /** 目标比特率（kbps，如 128/320） */
  bitrate?: number
}

/** 音频列表统计（GET /audios 响应内 data.stats，AudioListStats 实测） */
export interface AudioListStats {
  totalFiles: number
  totalSize: string
  totalDuration: string
  todayUploads: number
}

/** 文件夹树节点（§5.5；POST /audios/folder-tree，depth 1/10 增量） */
export interface AudioFolderNode {
  /** 文件夹路径（parentPath/name） */
  path: string
  name: string
  /** 直接子文件夹数 */
  count: number
  /** 文件夹内音频文件数 */
  fileCount: number
  depth: number
  children: AudioFolderNode[]
}

/** 频谱特征（§6.23；GET /audios/{id}/features → spectral） */
export interface AudioSpectralFeatures {
  /** 基频范围下限（Hz） */
  fundamentalRangeLow: number
  /** 基频范围上限（Hz） */
  fundamentalRangeHigh: number
  /** 主频（Hz） */
  dominantFrequency: number
  /** 谐波失真（%，0-100） */
  harmonicDistortion: number
}

/** 能量分布（features → energy） */
export interface AudioEnergyFeatures {
  /** 平均能量（dBFS） */
  averageEnergyDb: number
  /** 峰值能量（dBFS） */
  peakEnergyDb: number
  /** 能量集中度（0-1） */
  energyConcentration: number
}

/** 时域特征（features → time_domain） */
export interface AudioTimeDomainFeatures {
  /** 过零率（0-1） */
  zeroCrossingRate: number
  /** 有效时长占比（0-1） */
  activeDurationRatio: number
  /** 起始时间（秒） */
  onsetTime: number
}

/** 音频特征分析结果（§6.23 特征分区；audioId/duration 供与音频行时长对照） */
export interface AudioFeatures {
  spectral: AudioSpectralFeatures
  energy: AudioEnergyFeatures
  timeDomain: AudioTimeDomainFeatures
  audioId: number
  /** 分析样本时长（秒） */
  duration: number
}

/** 音频质量评估（§6.23 质量评估分区；GET /audios/{id}/quality） */
export interface AudioQuality {
  /** 信噪比（dB） */
  snrDb: number
  /** 动态范围（dB） */
  dynamicRangeDb: number
  /** 频率响应评分（0-100） */
  frequencyResponseScore: number
  /** 综合质量评分（0-100） */
  qualityScore: number
  audioId: number
  /** 分析样本时长（秒） */
  duration: number
}

/** 处理操作类型（§6.23 处理操作：降噪 / 增益调整 / 剪辑） */
export type AudioProcessOperation = 'denoise' | 'gain' | 'trim'

/** 处理产物落位方式：new=生成新音频记录；overwrite=覆盖原文件（破坏性） */
export type AudioProcessMode = 'new' | 'overwrite'

/** 处理操作请求（POST /audios/{id}/process；参数按 operation 取用） */
export interface AudioProcessRequest {
  operation: AudioProcessOperation
  /** 默认 new（生成新文件并建新音频记录）；overwrite 改原记录 file_path */
  mode?: AudioProcessMode
  /** 增益调整量（dB，仅 operation=gain） */
  gainDb?: number
  /** 剪辑起点（毫秒，仅 operation=trim） */
  startMs?: number
  /** 剪辑终点（毫秒，仅 operation=trim；缺省到音频末尾） */
  endMs?: number | null
}

/** 处理结果（POST /audios/{id}/process） */
export interface AudioProcessResult {
  audioId: number
  operation: AudioProcessOperation
  mode: AudioProcessMode
  /** 处理产物格式（统一 wav） */
  format: string
  /** 处理产物存储路径 */
  filePath: string
  /** 处理产物时长（秒） */
  duration: number
  /** 处理产物大小（字节） */
  size: number
  /** mode=new 时生成的新音频记录 id；overwrite 为 null */
  newAudioId: number | null
}
