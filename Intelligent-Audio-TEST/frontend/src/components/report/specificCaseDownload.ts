// -*- coding: utf-8 -*-
/**
 * 报告具体用例「下载日志」两段流程（INT-1055 重做，INT-1071 接线）：
 *   1. 日志文件选择 Dialog（§4.10a：文件列表 + 大小 + 全选/多选 + 已选合计）
 *      → 数据源 GET /reports/{id}/cases/{cid}/logs（INT-1062 真实端点）
 *   2. 确认 → GET /reports/{id}/cases/{cid}/logs/download?files=[...] 打包所选
 *      → 下载进度 Dialog（§4.10b）
 * 文件列表加载失败 / 无文件时退化为整包下载（缺省 files，向后兼容）。
 */
import { computed, ref } from 'vue'
import { useNotification } from '../../composables/modal/useNotification'
import { reportsPort } from '@/composables/report/reportsPort'
import { downloadBlob } from '../../utils/utils'
import { formatFileSize } from '../../utils/audioUtils'
import type { CaseLogFile } from '../../domain/model/report'

export function createDownloadLogic(deps: {
  props: any
  isDownloadingLog: any
  downloadingCaseName: any
  downloadProgress: any
  downloadSpeed: any
  downloadSize: any
  downloadTotal: any
  downloadFileCount: any
}) {
  const { props, isDownloadingLog, downloadingCaseName, downloadProgress, downloadSpeed, downloadSize, downloadTotal, downloadFileCount } = deps

  // ===== 日志文件选择 Dialog（§4.10a） =====
  const showLogFileDialog = ref(false)
  const logDialogCaseName = ref('')
  const logDialogCaseId = ref('')
  const logDialogCase = ref<any>(null)
  const logFiles = ref<CaseLogFile[]>([])
  const logFilesLoading = ref(false)
  const logFilesError = ref('')
  const selectedLogFiles = ref<string[]>([])

  /** 已选合计（§4.10a：「已选 {n} 个 / 共 {m} 个 · 总大小 {size}」） */
  const selectedFilesCount = computed(() => selectedLogFiles.value.length)
  const selectedFilesSize = computed(() =>
    logFiles.value
      .filter((f) => selectedLogFiles.value.includes(f.name))
      .reduce((sum, f) => sum + (Number(f.size) || 0), 0),
  )
  const allSelected = computed(() => logFiles.value.length > 0 && selectedLogFiles.value.length === logFiles.value.length)

  function getCaseId(caseItem: any): string {
    return String(caseItem?.id ?? caseItem?.testCaseId ?? '')
  }

  async function loadLogFiles() {
    const reportId = props.reportData?.id
    if (!reportId) return
    logFilesLoading.value = true
    logFilesError.value = ''
    try {
      const files = await reportsPort.listCaseLogFiles(reportId, logDialogCaseId.value || getCaseId(logDialogCase.value))
      logFiles.value = files || []
      // 默认全选（§4.10a 底栏「下载所选文件」默认全选）
      selectedLogFiles.value = (files || []).map((f) => f.name)
    } catch (error: any) {
      logFiles.value = []
      selectedLogFiles.value = []
      // P3：列表加载失败用友好文案（原样透出后端 "Not Found" 过于技术化），真实原因留 console 排查
      console.error('日志文件列表加载失败:', error?.message || error?.detail || error)
      logFilesError.value = '日志文件列表加载失败'
    } finally {
      logFilesLoading.value = false
    }
  }

  function openLogFileDialog(caseItem: any) {
    const reportId = props.reportData?.id
    const caseId = getCaseId(caseItem)
    if (!reportId || !caseId) return
    logDialogCase.value = caseItem
    logDialogCaseName.value = caseItem?.name || caseId
    logDialogCaseId.value = caseId
    logFiles.value = []
    selectedLogFiles.value = []
    logFilesError.value = ''
    showLogFileDialog.value = true
    void loadLogFiles()
  }

  function closeLogFileDialog() {
    showLogFileDialog.value = false
    logDialogCase.value = null
    logDialogCaseId.value = ''
    logDialogCaseName.value = ''
    logFiles.value = []
    selectedLogFiles.value = []
    logFilesError.value = ''
  }

  function toggleLogFile(name: string) {
    const idx = selectedLogFiles.value.indexOf(name)
    if (idx > -1) selectedLogFiles.value.splice(idx, 1)
    else selectedLogFiles.value.push(name)
  }

  function toggleSelectAllLogFiles() {
    if (allSelected.value) selectedLogFiles.value = []
    else selectedLogFiles.value = logFiles.value.map((f) => f.name)
  }

  // ===== 下载（§4.10b） =====
  async function downloadLogFiles(files: string[], caseInfo: { caseId: string; caseName: string }) {
    const notification = useNotification()
    const reportId = props.reportData?.id
    if (!reportId) {
      notification.error('无法获取报告ID')
      return
    }
    if (!caseInfo.caseId) {
      notification.error('无法获取用例ID')
      return
    }

    isDownloadingLog.value = true
    downloadingCaseName.value = caseInfo.caseName || caseInfo.caseId
    downloadProgress.value = 0
    downloadSpeed.value = ''
    downloadSize.value = ''
    downloadTotal.value = ''
    downloadFileCount.value = files.length

    try {
      // 流式读取（同旧 Vue getReader / React ReadableStream 先例）：真实进度 % + 500ms 采样速度
      // JWT 注入在 reportsApi 内照 client.ts（localStorage auth_token）
      const { blob } = await reportsPort.downloadCaseLogs(reportId, caseInfo.caseId, files, (p) => {
        if (p.total > 0) {
          downloadTotal.value = formatFileSize(p.total)
          downloadProgress.value = Math.round((p.loaded / p.total) * 100)
        }
        downloadSize.value = formatFileSize(p.loaded)
        if (p.speed > 0) downloadSpeed.value = formatFileSize(p.speed) + '/s'
      })

      downloadTotal.value = formatFileSize(blob.size)
      downloadSize.value = formatFileSize(blob.size)
      downloadProgress.value = 100

      downloadBlob(blob, `case_${caseInfo.caseId}_logs.zip`)

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
        downloadFileCount.value = 0
      }, 500)
    }
  }

  /** 确认：按所选文件打包下载（未选任何文件时退化为整包，后端缺省 files 即整包） */
  async function confirmDownloadSelected() {
    const caseId = logDialogCaseId.value || getCaseId(logDialogCase.value)
    const caseName = logDialogCaseName.value
    const files = selectedLogFiles.value.length > 0 ? [...selectedLogFiles.value] : []
    closeLogFileDialog()
    await downloadLogFiles(files, { caseId, caseName })
  }

  /** 文件列表加载失败 / 无文件时的兜底：整包下载（缺省 files，向后兼容） */
  async function downloadAllLogZip() {
    const caseId = logDialogCaseId.value || getCaseId(logDialogCase.value)
    const caseName = logDialogCaseName.value
    closeLogFileDialog()
    await downloadLogFiles([], { caseId, caseName })
  }

  return {
    showLogFileDialog,
    logDialogCaseName,
    logFiles,
    logFilesLoading,
    logFilesError,
    selectedLogFiles,
    selectedFilesCount,
    selectedFilesSize,
    allSelected,
    openLogFileDialog,
    closeLogFileDialog,
    loadLogFiles,
    toggleLogFile,
    toggleSelectAllLogFiles,
    confirmDownloadSelected,
    downloadAllLogZip,
    downloadLogFiles,
  }
}
