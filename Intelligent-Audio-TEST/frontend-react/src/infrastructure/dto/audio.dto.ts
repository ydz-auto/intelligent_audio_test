/**
 * 音频 DTO（infrastructure/dto 层；snake_case 与后端 api_gateway/schemas/audio.py 对齐）。
 * 展示层不感知 snake_case；字段映射统一在 adapters/audioAdapter.ts。
 */

export interface AudioItemDto {
  id: number
  name: string
  original_filename: string | null
  file_path: string | null
  duration: number | null
  size: number | null
  sample_rate: number | null
  channels: number | null
  bitrate: number | null
  format: string | null
  audio_type: string | null
  asr_text: string | null
  description: string | null
  source_language: string | null
  tags: string[]
  annotations: Array<Record<string, unknown>>
  created_at: string | null
  updated_at: string | null
}

export interface AudioListStatsDto {
  total_files: number
  total_size: string
  total_duration: string
  today_uploads: number
}

/** 对应 AudioListData（PaginatedData[AudioItem] + stats；GET /audios 响应信封内 data） */
export interface AudioListDto {
  items: AudioItemDto[]
  total: number
  page: number
  per_page: number
  pages: number
  stats: AudioListStatsDto
}

/** 对应 TagListData（音频标签名，INT-297 统一分页信封；GET /audios/tags 响应信封内 data） */
export interface AudioTagListDto {
  items: string[]
  total: number
  page?: number
  per_page?: number
  pages?: number
}

/** 文件夹树节点（POST /audios/folder-tree 递归节点；file_count/folders 后端原值） */
export interface FolderTreeNodeDto {
  name?: string
  path?: string
  count?: number
  file_count?: number
  has_children?: boolean
  files?: Array<Record<string, unknown>>
  folders?: FolderTreeNodeDto[]
}

/** 对应文件夹树响应（data = { tree, folders, total, folder_count }） */
export interface FolderTreeDto {
  tree: FolderTreeNodeDto
  folders: FolderTreeNodeDto[]
  total: number
  folder_count: number
}

/** 频谱特征（GET /audios/{id}/features → data.spectral；audio_service compute_features 产出） */
export interface AudioSpectralFeaturesDto {
  /** 基频下限（Hz） */
  fundamental_range_low: number
  /** 基频上限（Hz） */
  fundamental_range_high: number
  /** 主频（Hz） */
  dominant_frequency: number
  /** 谐波失真（%，0-100） */
  harmonic_distortion: number
}

/** 能量分布（data.energy） */
export interface AudioEnergyFeaturesDto {
  /** 平均能量（dBFS） */
  average_energy_db: number
  /** 峰值能量（dBFS） */
  peak_energy_db: number
  /** 能量集中度（0-1，1-谱平坦度） */
  energy_concentration: number
}

/** 时域特征（data.time_domain） */
export interface AudioTimeDomainFeaturesDto {
  /** 过零率（0-1） */
  zero_crossing_rate: number
  /** 有效时长占比（0-1） */
  active_duration_ratio: number
  /** 起始时间（秒） */
  onset_time: number
}

/** 特征分析响应（GET /audios/{id}/features → 信封 data；三组特征 + audio_id/duration） */
export interface AudioFeaturesDto {
  spectral: AudioSpectralFeaturesDto
  energy: AudioEnergyFeaturesDto
  time_domain: AudioTimeDomainFeaturesDto
  audio_id: number
  duration: number
}

/** 质量评估响应（GET /audios/{id}/quality → 信封 data；INT-820/实测 200 同字段） */
export interface AudioQualityDto {
  /** 信噪比（dB） */
  snr_db: number
  /** 动态范围（dB） */
  dynamic_range_db: number
  /** 频率响应评分（0-100） */
  frequency_response_score: number
  /** 综合质量评分（0-100 整数） */
  quality_score: number
  audio_id: number
  duration: number
}

/**
 * 处理结果（POST /audios/{id}/process → 信封 data）。
 * mode=new 时回 new_audio_id（新音频记录），mode=overwrite 时原地改写 file_path，
 * 两种模式都回处理产物的 file_path/format/duration/size。
 */
export interface AudioProcessResultDto {
  audio_id: number
  operation: string
  mode: string
  format: string
  file_path: string
  duration: number
  size: number
  new_audio_id?: number | null
}
