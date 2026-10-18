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
