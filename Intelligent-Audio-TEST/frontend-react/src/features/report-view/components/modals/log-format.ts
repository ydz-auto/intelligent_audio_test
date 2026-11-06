/**
 * 报告日志文件大小格式化（INT-1067，文件选择 Dialog 与下载进度 Dialog 共用）。
 * 照原 log-download-progress-dialog 本地实现，抽到 modals 目录避免两处重复。
 */
export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '—'
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value.toFixed(1)} ${units[unit]}`
}
