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
