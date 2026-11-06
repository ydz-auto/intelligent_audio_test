/**
 * skill 包下载 hook（application 层，INT-1153）。
 * 下载 GET /api/v1/agent/skill?base_url=…（ZIP 二进制流）→ Blob → <a download> 触发。
 */
import { useCallback, useState } from 'react'

import { downloadSkill } from '@/infrastructure/api/accessTokenApi'

/** 触发浏览器下载（Blob → <a download> 统一走） */
function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export function useSkillDownload() {
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const download = useCallback(
    async (baseUrl: string): Promise<boolean> => {
      setDownloading(true)
      setError(null)
      try {
        const blob = await downloadSkill(baseUrl)
        triggerBlobDownload(blob, 'intelligent-audio-test-skill.zip')
        return true
      } catch (err) {
        setError(
          err instanceof Error && err.message
            ? err.message
            : 'skill 包下载失败，请稍后重试'
        )
        return false
      } finally {
        setDownloading(false)
      }
    },
    []
  )

  return { downloading, error, download, resetError: () => setError(null) }
}
