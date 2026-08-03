import { ref, computed, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { reportsApi } from '../../utils/api'
import { useModalControl, MODAL_TYPES } from '../modal/useModal'
import { useTestReport } from './useTestReport'
import reportService from '../../services/reportService'

interface UseTestReportOpsOptions {
  testType: 'e2e' | 'api'
  currentTaskId: Ref<string | number | null>
  taskName: Ref<string>
  onReportReady?: () => void
  onReportFailed?: () => void
}

/**
 * 报告相关操作：查看任务报告、保存报告、编辑/结论切换
 * 封装 e2e/api 共同的报告获取和保存逻辑
 */
export function useTestReportOps(options: UseTestReportOpsOptions) {
  const { testType, currentTaskId, taskName, onReportReady, onReportFailed } = options
  const router = useRouter()
  const modalManager = useModalControl()

  const {
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
    exportResults,
    publishReport,
    startNewTest,
  } = useTestReport()

  const reportTables = ref<any[]>([])

  /** 查看任务报告（e2e/api 共用），完成后根据是否有 id 决定跳转或回退步骤 */
  const fetchReport = async (status: 'completed' | 'failed' = 'completed', progress = 100) => {
    if (!currentTaskId.value) return
    try {
      const reportData = await reportService.viewTaskReport({
        id: currentTaskId.value,
        name: taskName.value || (testType === 'e2e' ? 'E2E测试任务' : 'API测试任务'),
        type: testType,
        status,
        progress,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      } as any)
      if (reportData) {
        report.value = { ...report.value, ...reportData } as any
        analysisContent.value = (report.value as any)?.analysis || ''
        reportTables.value = (report.value as any)?.tables || []
      }
    } catch (error) {
      console.error('[useTestReportOps] 获取报告失败:', error)
      const errorMessage = error instanceof Error ? error.message : '生成报告失败，请检查任务状态'
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '报告生成失败',
        content: errorMessage,
        confirmText: '确定',
        cancelText: '关闭',
        danger: true,
      })
    }
  }

  /** 任务完成/失败后统一处理报告加载和页面跳转 */
  const handleTaskEnd = async (status: 'completed' | 'failed', progress = 100) => {
    await fetchReport(status, progress)
    if (report.value?.id) {
      router.push({ name: 'reportView', params: { id: report.value.id } })
      onReportReady?.()
    } else {
      onReportFailed?.()
    }
  }

  /** 保存报告（e2e/api 共用） */
  const saveReport = async () => {
    try {
      const reportId = report.value?.id
      if (!reportId) {
        throw new Error('无法保存报告：报告ID为空')
      }
      await reportsApi.update(reportId, report.value)
      isEditingReport.value = false
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '保存成功',
        content: '报告已成功保存',
        confirmText: '确定',
        cancelText: '',
      })
    } catch (error) {
      console.error('[useTestReportOps] 保存报告失败:', error)
      modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '保存失败',
        content: `保存报告失败: ${error instanceof Error ? error.message : String(error)}`,
        confirmText: '确定',
        cancelText: '',
        danger: true,
      })
    }
  }

  // 报告表格的对比数据（来自 reportService）
  const deviceApiComparisonData = computed(() => reportService.deviceApiComparisonData.value)
  const caseExecutionData = computed(() => reportService.caseExecutionData.value)

  // 列定义
  const deviceApiColumns = [
    { key: 'name', label: '名称', type: 'text', sortable: true },
    { key: 'type', label: '类型', type: 'text', sortable: true },
    { key: 'version', label: '版本', type: 'text', sortable: true },
    { key: 'status', label: '状态', type: 'status', sortable: true },
    { key: 'totalCases', label: '总用例数', type: 'number', sortable: true },
    { key: 'completedCases', label: '已完成用例数', type: 'number', sortable: true },
    { key: 'failedCases', label: '失败用例数', type: 'number', sortable: true },
    { key: 'successRate', label: '成功率(%)', type: 'number', sortable: true },
    { key: 'avgResponseTime', label: '平均响应时间(ms)', type: 'number', sortable: true },
    { key: 'stability', label: '稳定性(%)', type: 'number', sortable: true },
  ]

  const caseExecutionColumns = [
    { key: 'name', label: '名称', type: 'text', sortable: true },
    { key: 'total', label: '总用例数', type: 'number', sortable: true },
    { key: 'executed', label: '已执行', type: 'number', sortable: true },
    { key: 'passed', label: '通过', type: 'number', sortable: true },
    { key: 'failed', label: '失败', type: 'number', sortable: true },
    { key: 'successRate', label: '成功率', type: 'percentage', sortable: true },
    { key: 'failedRate', label: '失败率', type: 'percentage', sortable: true },
  ]

  return {
    report,
    isEditingReport,
    isEditingConclusion,
    analysisContent,
    reportTables,
    deviceApiComparisonData,
    caseExecutionData,
    deviceApiColumns,
    caseExecutionColumns,
    setReport,
    toggleEditReport,
    toggleEditConclusion,
    cancelEditReport,
    cancelEditConclusion,
    saveConclusion,
    exportResults,
    publishReport,
    startNewTest,
    fetchReport,
    handleTaskEnd,
    saveReport,
  }
}
