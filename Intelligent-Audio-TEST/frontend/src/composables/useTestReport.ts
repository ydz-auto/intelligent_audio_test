import { ref } from 'vue'
import { reportsApi } from '../utils/api'

export interface ReportData {
  id?: string | number
  title?: string
  name?: string
  description?: string
  conclusion?: string
  analysis?: string
  status?: string
  type?: string
  createdAt?: string
  updatedAt?: string
  summary?: {
    totalCases?: number
    passedCases?: number
    failedCases?: number
    passRate?: number
    avgScore?: number
    [key: string]: any
  }
  [key: string]: any
}

export interface UseTestReportOptions {
  initialReport?: ReportData
  onReportUpdate?: (report: ReportData) => void
}

const DEFAULT_REPORT: ReportData = {
  id: '',
  title: '测试报告',
  name: '',
  description: '',
  conclusion: '',
  analysis: '',
  type: 'task',
  status: 'draft',
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
  summary: { totalCases: 0, passedCases: 0, failedCases: 0, passRate: 0, avgScore: 0 }
}

export function useTestReport(options: UseTestReportOptions = {}) {
  const { onReportUpdate, initialReport } = options
  const report = ref<ReportData>(initialReport || { ...DEFAULT_REPORT })
  const isEditingReport = ref(false)
  const isEditingConclusion = ref(false)
  const analysisContent = ref('')

  function setReport(newReport: ReportData | null) {
    if (newReport) {
      report.value = newReport
      if (newReport.analysis) {
        analysisContent.value = newReport.analysis
      }
      if (onReportUpdate) {
        onReportUpdate(newReport)
      }
    } else {
      report.value = { ...DEFAULT_REPORT }
      analysisContent.value = ''
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
    report.value = { ...DEFAULT_REPORT }
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