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
