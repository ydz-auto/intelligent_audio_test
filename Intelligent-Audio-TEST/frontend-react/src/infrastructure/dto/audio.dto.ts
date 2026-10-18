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

/** GET /audios 响应 data（AudioListData：items + total + stats，schemas/audio.py 实测） */
export interface AudioListDataDto {
  items: AudioItemDto[]
  total: number
  stats: AudioListStatsDto
}

/** 文件夹树节点（POST /audios/folder-tree 响应 data.tree 嵌套 folders/files，INT-714 实测） */
export interface AudioFolderNodeDto {
  name: string
  path: string
  /** 子节点（含文件）数量（根=全部音频数；子文件夹=其下音频总数） */
  count: number
  /** 当前文件夹直接包含的音频文件数 */
  file_count: number
  has_children: boolean
  files: unknown[]
  folders: AudioFolderNodeDto[]
}

/** 文件夹树根（响应 data.tree） */
export interface AudioFolderTreeDto extends AudioFolderNodeDto {}
