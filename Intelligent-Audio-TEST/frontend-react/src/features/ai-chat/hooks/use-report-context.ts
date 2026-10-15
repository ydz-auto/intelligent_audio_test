/**
 * 报告上下文选择器数据（interfaces 层 hooks；08_AI对话页.md §3.5）。
 * 数据源 GET /reports（report:read 可先行）+ GET /tasks（task:read）；
 * mock 常量（红线④），后续接线换 reportsApi/tasksApi。
 */
import { useMemo } from 'react'

import type {
  ReportContextOption,
  ReportContextType,
} from '@/domain/models/aiChat'
import { usePermissions } from '@/application/hooks/use-permissions'
import {
  MOCK_REPORTS,
  MOCK_TASKS,
} from '@/infrastructure/mock/ai-chat-mock'

const TYPE_BADGES: Record<ReportContextType, string> = {
  task: '测试报告',
  comparison: '对比报告',
  secondary_comparison: '二次对比',
  task_context: '任务',
}

export type ReportContextGroupType = ReportContextType

export type ReportContextGroup = {
  type: ReportContextGroupType
  label: string
  options: ReportContextOption[]
}

export function useReportContext() {
  const { hasPermission } = usePermissions()
  const canReadTask = hasPermission('task:read')

  const groups = useMemo<ReportContextGroup[]>(() => {
    const reportOptions: ReportContextOption[] = MOCK_REPORTS.map((report) => ({
      id: String(report.id),
      label: report.name,
      type: report.type,
      badge: TYPE_BADGES[report.type] ?? '测试报告',
      description: report.description ?? undefined,
    }))

    const taskOptions: ReportContextOption[] = canReadTask
      ? MOCK_TASKS.map((task) => ({
          id: String(task.id),
          label: task.name,
          type: 'task_context' as const,
          badge: '任务',
          description: `算法：${task.algorithm_type ?? '—'} · 状态：${task.status === 'completed' ? '已完成' : task.status}`,
        }))
      : []

    const groups: ReportContextGroup[] = [
      {
        type: 'task',
        label: '测试报告',
        options: reportOptions.filter((item) => item.type === 'task'),
      },
      {
        type: 'comparison',
        label: '对比报告',
        options: reportOptions.filter((item) => item.type === 'comparison'),
      },
      {
        type: 'secondary_comparison',
        label: '二次对比',
        options: reportOptions.filter(
          (item) => item.type === 'secondary_comparison'
        ),
      },
      {
        type: 'task_context',
        label: '任务',
        options: taskOptions,
      },
    ]
    return groups.filter((group) => group.options.length > 0)
  }, [canReadTask])

  return { groups }
}
