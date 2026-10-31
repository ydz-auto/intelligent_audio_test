/**
 * 音频管理页状态类型（features/audio-import）。
 * §5.2 validateSearch 语义的 mock 阶段本地态；接线后 URL 化。
 */

import type { AudioType } from '@/domain/models/audio'

export type AudioViewMode = 'list' | 'folder'

export type TagMode = 'or' | 'and'

/** 可见性（数据可见性设计文档 §二：仅二值 private/shared；null = 全部） */
export type AudioVisibility = 'shared' | 'private'

export interface AudioListFilters {
  search: string
  format: string | null
  audioType: AudioType | null
  sampleRate: string | null
  duration: 'short' | 'medium' | 'long' | null
  tags: string[]
  tagMode: TagMode
  /** 可见性筛选（服务端参数下发，不做前端过滤；null = 全部） */
  visibility: AudioVisibility | null
}

/** 行操作弹窗分派态（§5.3.1 + §6.13-6.15/6.23） */
export type AudioRowDialogState =
  | { kind: 'preview'; audioId: number }
  | { kind: 'metadata'; audioId: number }
  | { kind: 'convert'; audioId: number }
  | { kind: 'feature-analysis'; audioId: number }

/** 批量浮条弹窗分派态（§5.6 + §6.25；「批量设置标签」走独立 AudioBatchTagsDialog） */
export type AudioBulkDialogState =
  | { kind: 'move' }
  | { kind: 'copy' }
  | { kind: 'rename' }
  | { kind: 'modify-properties' }
