/** 触发浏览器下载（Blob → <a download> 统一走；ext 决定 MIME） */
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
