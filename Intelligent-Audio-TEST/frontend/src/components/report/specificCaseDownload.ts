import { useNotification } from '../../composables/modal/useNotification'
import { reportsApi } from '../../utils/api'

export function formatFileSize(bytes: number) {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

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
    const reportId = props.reportData?.id || props.reportData?.report_id
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
      const downloadUrl = reportsApi.getCaseLogsDownloadUrl(reportId, caseId)
      const response = await fetch(downloadUrl)

      if (!response.ok) {
        let errorMsg = '下载日志失败'
        try {
          const errorData = await response.json()
          errorMsg = errorData?.message || errorData?.detail || errorMsg
        } catch {
          if (response.status === HttpStatus.NOT_FOUND) {
            errorMsg = '未找到用例日志目录'
          } else if (response.status === HttpStatus.SERVER_ERROR) {
            errorMsg = '服务器内部错误'
          }
        }
        notification.error(errorMsg)
        return
      }

      const contentLength = response.headers.get('content-length')
      const totalBytes = contentLength ? parseInt(contentLength, 10) : 0
      downloadTotal.value = formatFileSize(totalBytes)

      if (!response.body) {
        const blob = await response.blob()
        const url = window.URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.setAttribute('download', `case_${caseId}_logs.zip`)
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        window.URL.revokeObjectURL(url)
        notification.success('日志下载成功')
        return
      }

      const reader = response.body.getReader()
      const chunks: any[] = []
      let receivedBytes = 0
      let lastTime = Date.now()
      let lastBytes = 0

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        chunks.push(value)
        receivedBytes += value.length
        downloadSize.value = formatFileSize(receivedBytes)

        if (totalBytes > 0) {
          downloadProgress.value = Math.round((receivedBytes / totalBytes) * 100)
        }

        const now = Date.now()
        const timeDiff = now - lastTime
        if (timeDiff >= 500) {
          const bytesDiff = receivedBytes - lastBytes
          const speed = bytesDiff / (timeDiff / 1000)
          downloadSpeed.value = formatFileSize(speed) + '/s'
          lastTime = now
          lastBytes = receivedBytes
        }
      }

      const blob = new Blob(chunks, { type: 'application/zip' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `case_${caseId}_logs.zip`)
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)

      downloadProgress.value = 100
      notification.success('日志下载成功')
    } catch (error: any) {
      console.error('下载日志失败:', error)
      const errorMsg = error?.message || '下载日志失败，请稍后重试'
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
