import { useNotification } from '../../composables/modal/useNotification'
import { reportsPort } from '@/composables/report/reportsPort'
import { HttpStatus } from '../../domain/enums'
import { downloadBlob } from '../../utils/utils'
import { formatFileSize } from '../../utils/audioUtils'

export function createDownloadLogic(deps: {
  props: any
  isDownloadingLog: any
  downloadingCaseName: any
  downloadProgress: any
  downloadSpeed: any
  downloadSize: any
  downloadTotal: any
}) {
  const { props, isDownloadingLog, downloadingCaseName, downloadProgress, downloadSpeed, downloadSize, downloadTotal } = deps

  async function downloadCaseLogZip(caseItem: any) {
    const notification = useNotification()
    const reportId = props.reportData?.id
    if (!reportId) {
      console.error('无法获取报告ID')
      notification.error('无法获取报告ID')
      return
    }

    const caseId = caseItem.id
    if (!caseId) {
      console.error('无法获取用例ID')
      notification.error('无法获取用例ID')
      return
    }

    isDownloadingLog.value = true
    downloadingCaseName.value = caseItem.name || caseId
    downloadProgress.value = 0
    downloadSpeed.value = ''
    downloadSize.value = ''
    downloadTotal.value = ''

    try {
      // 走 reportsPort.downloadCaseLogs（Blob 通道，JWT 由 client.ts 拦截器注入）
      const blob = await reportsPort.downloadCaseLogs(reportId, caseId)

      // Blob 无法流式获取进度，直接展示总大小并触发下载
      downloadTotal.value = formatFileSize(blob.size)
      downloadSize.value = formatFileSize(blob.size)
      downloadProgress.value = 100

      downloadBlob(blob, `case_${caseId}_logs.zip`)

      notification.success('日志下载成功')
    } catch (error: any) {
      console.error('下载日志失败:', error)
      const errorMsg = error?.message || error?.detail || '下载日志失败，请稍后重试'
      notification.error(errorMsg)
    } finally {
      setTimeout(() => {
        isDownloadingLog.value = false
        downloadingCaseName.value = ''
        downloadProgress.value = 0
        downloadSpeed.value = ''
        downloadSize.value = ''
        downloadTotal.value = ''
      }, 500)
    }
  }

  return { downloadCaseLogZip }
}
