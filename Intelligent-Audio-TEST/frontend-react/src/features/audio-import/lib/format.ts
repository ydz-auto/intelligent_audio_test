/**
 * 音频展示格式化（features/audio-import/lib；§5.3 列渲染 formatFileSize/formatDuration）。
 * 默认 locale，不传语言码（AGENTS.md §3.1）。
 */

/** 文件大小（字节 → 可读；`formatFileSize` 语义） */
export function formatFileSize(bytes: number | null): string {
  if (bytes == null) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

/** 时长（秒 → 「mm:ss」；§5.3 列渲染） */
export function formatDuration(seconds: number | null): string {
  if (seconds == null) return '—'
  const total = Math.max(0, Math.round(seconds))
  const minutes = Math.floor(total / 60)
  const secs = total % 60
  return `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
}

/** 时长 facet 归类（§5.3.2：短≤30s / 中 30s-5min / 长>5min） */
export function durationBucket(seconds: number | null): 'short' | 'medium' | 'long' | null {
  if (seconds == null) return null
  if (seconds <= 30) return 'short'
  if (seconds <= 300) return 'medium'
  return 'long'
}

/**
 * 创建时间格式化（mono tabular）。
 * INT-2211：后端下发裸 UTC，统一走共享工具按 UTC 解析后转本地展示。
 */
export { formatDateTime } from '@/lib/date-time'

