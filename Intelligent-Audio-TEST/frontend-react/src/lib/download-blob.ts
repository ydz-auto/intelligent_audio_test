/**
 * 触发浏览器下载（Blob / 字符串 → <a download> 统一走；ext 决定 MIME）。
 * 跨 feature 共用的下载工具（INT-1642 代码审计 P3-3：原在 features/evaluation/download-blob，
 * 被 features/testcases 导出弹窗反向引用；上提到 lib 避免 feature→feature 依赖）。
 */
export function downloadBlob(
  content: string | Blob,
  filename: string,
  mime: string,
  withBom = false
): void {
  const blob =
    typeof content === 'string'
      ? new Blob([withBom ? '﻿' : '', content], { type: mime })
      : content
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}
