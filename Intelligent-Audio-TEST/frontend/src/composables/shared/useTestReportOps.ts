import { ref, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { reportsPort } from '../report/reportsPort'
import { useModalControl, MODAL_TYPES } from '../modal/useModal'
import { useTestReport } from './useTestReport'
import { viewTaskReport } from '../report/useReportComparison'
import {
  deviceApiComparisonData as storeDeviceApiComparisonData,
  caseExecutionData as storeCaseExecutionData,
  deviceApiColumns as storeDeviceApiColumns,
  caseExecutionColumns as storeCaseExecutionColumns,
} from '../../store/reportComparisonStore'
import { TaskStatus, TestType } from '@/domain/enums'

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
  const fetchReport = async (status: 'completed' | 'failed' = TaskStatus.COMPLETED, progress = 100) => {
    if (!currentTaskId.value) return
    try {
      const reportData = await viewTaskReport({
        id: currentTaskId.value,
        name: taskName.value || (testType === TestType.E2E ? 'E2E测试任务' : 'API测试任务'),
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
      await reportsPort.update(reportId, report.value)
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

  // 报告表格的对比数据（来自 reportComparisonStore，模块级单例 ReadModel）
  const deviceApiComparisonData = storeDeviceApiComparisonData
  const caseExecutionData = storeCaseExecutionData

  // 列定义（复用 store 中的唯一来源，消除重复）
  const deviceApiColumns = storeDeviceApiColumns
  const caseExecutionColumns = storeCaseExecutionColumns

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
