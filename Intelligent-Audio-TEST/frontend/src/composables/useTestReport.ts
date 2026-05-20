import { ref } from 'vue'
import { reportsApi } from '../utils/api'

export interface ReportData {
  id?: string | number
  conclusion?: string
  analysis?: string
  status?: string
  [key: string]: any
}

export interface UseTestReportOptions {
  onReportUpdate?: (report: ReportData) => void
}

export function useTestReport(options: UseTestReportOptions = {}) {
  const { onReportUpdate } = options
  const report = ref<ReportData | null>(null)
  const isEditingReport = ref(false)
  const isEditingConclusion = ref(false)
  const analysisContent = ref('')

  function setReport(newReport: ReportData | null) {
    report.value = newReport
    if (newReport?.analysis) {
      analysisContent.value = newReport.analysis
    }
    if (onReportUpdate && newReport) {
      onReportUpdate(newReport)
    }
  }

  function toggleEditReport() {
    isEditingReport.value = !isEditingReport.value
  }

  function toggleEditConclusion() {
    isEditingConclusion.value = !isEditingConclusion.value
  }

  function cancelEditReport() {
    isEditingReport.value = false
  }

  function cancelEditConclusion() {
    isEditingConclusion.value = false
  }

  async function saveConclusion(content: string) {
    if (report.value) {
      report.value.conclusion = content
      report.value.analysis = content
      analysisContent.value = content
      if (report.value.id) {
        await reportsApi.update(report.value.id, report.value)
      }
    }
    isEditingConclusion.value = false
  }

  function updateAnalysisContent(content: string) {
    analysisContent.value = content
    if (report.value) {
      report.value.analysis = content
      report.value.conclusion = content
    }
  }

  function exportResults(format: string) {
    console.log(`导出报告格式: ${format}`)
  }

  function publishReport() {
    if (report.value) {
      report.value.status = report.value.status === 'draft' ? 'published' : 'draft'
    }
  }

  function startNewTest() {
    report.value = null
    isEditingReport.value = false
    isEditingConclusion.value = false
    analysisContent.value = ''
  }

  return {
    report,
    isEditingReport,
    isEditingConclusion,
    analysisContent,
    setReport,
    toggleEditReport,
    toggleEditConclusion,
    cancelEditReport,
    cancelEditConclusion,
    saveConclusion,
    updateAnalysisContent,
    exportResults,
    publishReport,
    startNewTest
  }
}