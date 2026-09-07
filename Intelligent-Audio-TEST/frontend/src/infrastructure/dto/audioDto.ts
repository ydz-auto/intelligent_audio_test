/**
 * Audio（音频资产）DTO —— snake_case
 * 对应后端 api_gateway/schemas/audio.py::AudioItem / AudioListData /
 * AudioListStats / AudioIdsData / TagListData / AudioAlgorithmRelationItem
 */

/** 对应 AudioItem */
export interface AudioItemDto {
  id: number | string
  name: string
  original_filename?: string
  file_path?: string
  duration?: number
  size?: number
  sample_rate?: number
  channels?: number
  bitrate?: number
  format?: string
  audio_type?: string
  asr_text?: string
  description?: string
  source_language?: string
  tags?: string[]
  annotations?: Record<string, unknown>[]
  created_at?: string
  updated_at?: string
}

/** 对应 AudioListStats */
export interface AudioListStatsDto {
  total_files: number
  total_size: string
  total_duration: string
  today_uploads: number
}

/** 对应 AudioListData（PaginatedData[AudioItem] + stats） */
export interface AudioListDto {
  items: AudioItemDto[]
  total: number
  page: number
  per_page: number
  pages: number
  stats: AudioListStatsDto
}

/** 对应 AudioIdsData */
export interface AudioIdsDto {
  ids: number[]
  total: number
}

/** 对应 TagListData（音频标签） */
export interface AudioTagListDto {
  items: string[]
  total: number
}

/** 对应 AudioAlgorithmRelationItem */
export interface AudioAlgorithmRelationDto {
  algorithm_type: string
  is_primary: boolean
  weight: number
  params?: Record<string, unknown>
}
