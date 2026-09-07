/**
 * apiTest —— 任务进度与报告（report）
 *
 * 负责任务执行进度字段的维护（useTaskProgress，含任务完成/失败后加载报告并跳转的回调），
 * 以及报告保存与设备/用例执行对比表格的列定义。
 */
import { reportsPort } from '@/composables/report/reportsPort'
import { useTaskProgress } from '../../composables/task/useTaskProgress'
import { viewTaskReport } from '../../composables/report/useReportComparison'
import { useNotification } from '../../composables/modal/useNotification'
import { TaskStatus, TestType } from '@/domain/enums'
import type { Ref } from 'vue'
import type { Router } from 'vue-router'
import type { ReportData } from '../../composables/shared/useTestReport'

/** 任务进度与报告模块依赖 */
export interface ApiTestReportDeps {
  report: Ref<ReportData>;
  isEditingReport: Ref<boolean>;
  currentTaskId: Ref<string | number | null>;
  taskName: Ref<string>;
  currentStep: Ref<number>;
  router: Router;
}

/** 创建任务进度与报告模块 */
export function createApiTestReportModule(deps: ApiTestReportDeps) {
  const notification = useNotification()
  const { report, isEditingReport, currentTaskId, taskName, currentStep, router } = deps

  const {
    progressPercentage,
    completedTests,
    inProgressTests,
    pendingTests,
    executionFailedTests,
    evaluationFailedTests,
    totalTestCases,
    taskStatus,
    elapsedTime,
    estimatedTime,
    expectedCompleteTime,
    logs,
    associatedCases,
    apiResources,
  } = useTaskProgress({
    testType: 'API',
    currentTaskId: currentTaskId,
    onCompleted: async () => {
      console.log('[API测试] 任务完成，加载报告数据并跳转')
      try {
        if (currentTaskId.value) {
          const reportData = await viewTaskReport({
            id: currentTaskId.value,
            name: taskName.value || 'API测试任务',
            type: TestType.API,
            status: TaskStatus.COMPLETED,
            progress: 100,
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString()
          } as any)
          report.value = { ...report.value, ...reportData }
          if (report.value?.id) {
            router.push({ name: 'reportView', params: { id: report.value.id } })
          } else {
            currentStep.value = 4
          }
        }
      } catch (error) {
        console.error('[API测试] 加载报告数据失败:', error)
        currentStep.value = 4
      }
    },
    onFailed: async (progressData) => {
      console.error('[API测试] 任务执行失败:', progressData)
      try {
        if (currentTaskId.value) {
          const reportData = await viewTaskReport({
            id: currentTaskId.value,
            name: taskName.value || 'API测试任务',
            type: TestType.API,
            status: TaskStatus.FAILED,
            progress: progressPercentage.value,
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString()
          } as any)
          report.value = { ...report.value, ...reportData }
          if (report.value?.id) {
            router.push({ name: 'reportView', params: { id: report.value.id } })
          } else {
            currentStep.value = 4
          }
        }
      } catch (error) {
        console.error('[API测试] 加载报告数据失败:', error)
        currentStep.value = 4
      }
    }
  })

  const saveReport = async () => {
    try {
      if (!report.value?.id) {
        console.warn('无法保存报告：报告ID为空')
        notification.warning('无法保存报告：请先查看报告')
        return
      }
      await reportsPort.update(report.value.id, report.value)
      isEditingReport.value = false
      notification.success('报告已保存')
    } catch (error: any) {
      console.error('保存报告失败:', error)
      notification.error('保存报告失败: ' + (error.message || '未知错误'))
    }
  }

  const deviceAPIColumns = [
    { key: 'name', label: '名称', type: 'text', sortable: true },
    { key: 'type', label: '类型', type: 'text', sortable: true },
    { key: 'version', label: '版本', type: 'text', sortable: true },
    { key: 'status', label: '状态', type: 'status', sortable: true },
    { key: 'totalCases', label: '总用例数', type: 'number', sortable: true },
    { key: 'completedCases', label: '已完成用例数', type: 'number', sortable: true },
    { key: 'failedCases', label: '失败用例数', type: 'number', sortable: true },
    { key: 'successRate', label: '成功率(%)', type: 'number', sortable: true },
    { key: 'avgResponseTime', label: '平均响应时间(ms)', type: 'number', sortable: true },
    { key: 'stability', label: '稳定性(%)', type: 'number', sortable: true }
  ]

  const caseExecutionColumns = [
    { key: 'name', label: '名称', type: 'text', sortable: true },
    { key: 'total', label: '总用例数', type: 'number', sortable: true },
    { key: 'executed', label: '已执行', type: 'number', sortable: true },
    { key: 'passed', label: '通过', type: 'number', sortable: true },
    { key: 'failed', label: '失败', type: 'number', sortable: true },
    { key: 'successRate', label: '成功率', type: 'percentage', sortable: true },
    { key: 'failedRate', label: '失败率', type: 'percentage', sortable: true }
  ]

  return {
    progressPercentage,
    completedTests,
    inProgressTests,
    pendingTests,
    executionFailedTests,
    evaluationFailedTests,
    totalTestCases,
    taskStatus,
    elapsedTime,
    estimatedTime,
    expectedCompleteTime,
    logs,
    associatedCases,
    apiResources,
    saveReport,
    deviceAPIColumns,
    caseExecutionColumns
  }
}