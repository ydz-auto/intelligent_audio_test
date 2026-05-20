import { ref } from 'vue'
import { reportsApi } from '@/api/reports'

export interface ReportData {
  id?: string
  conclusion?: string
  analysis?: string
  [key: string]: any
}

export interface UseTestReportOptions {
  onReportUpdate?: (report: ReportData) => void
}

export function useTestReport(options: UseTestReportOptions = {}) {
  const report = ref<ReportData | null>(null)
  const isEditingReport = ref(false)
  const isEditingConclusion = ref(false)
  const analysisContent = ref('')

  function setReport(newReport: ReportData | null) {
    report.value = newReport
    if (newReport?.analysis) {
      analysisContent.value = newReport.analysis
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
      if (report.value.id) {
        await reportsApi.update(report.value.id, report.value)
      }
      if (options.onReportUpdate) {
        options.onReportUpdate(report.value)
      }
    }
    isEditingConclusion.value = false
  }

  async function saveReport() {
    if (report.value?.id) {
      await reportsApi.update(report.value.id, report.value)
      if (options.onReportUpdate) {
        options.onReportUpdate(report.value)
      }
    }
    isEditingReport.value = false
  }

  function exportResults(format: string) {
    console.log(`导出报告格式: ${format}`)
  }

  function publishReport() {
    console.log('发布报告')
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
    saveReport,
    exportResults,
    publishReport,
    startNewTest
  }
}