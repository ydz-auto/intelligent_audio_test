/**
 * 报告上下文选择器数据（interfaces 层 hooks；08_AI对话页.md §3.5 / §3.7）。
 * 数据源一律真实接口（INT-2473 接线）：
 * - GET /reports（report:read，favorite=false / deleted=false，按更新时间倒序）；
 * - GET /tasks（task:read，status=completed，任务作为「任务上下文」）。
 * 取不到的上下文 → 空列表 + 错误态；不回落到 infrastructure/mock。
 * 选项带来源 ID（报告 #id / 任务 #id），绑定后写入会话 config.reportContext*，
 * 工作台据此列报告文档并显示来源卡。
 */
import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'

import type {
  ReportContextOption,
  ReportContextType,
} from '@/domain/models/aiChat'
import { usePermissions } from '@/application/hooks/use-permissions'
import {
  fetchReportList,
  fetchCompletedTasks,
} from '@/infrastructure/api/reports-api'

/** 下拉一次取多少条（后端分页；工作台上下文选择不做无限滚动） */
const REPORT_CONTEXT_PAGE_SIZE = 50
const TASK_CONTEXT_PAGE_SIZE = 50

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

/** 报告类型 → 上下文类型（benchmark 归入测试报告口径，与 aiChatSessionStore 同口径） */
function toReportContextType(type: string): ReportContextType {
  return type === 'comparison' || type === 'secondary_comparison'
    ? type
    : 'task'
}

/** 报告上下文查询（工作台首屏 / 选择器打开时取；失败由页面给错误态） */
export function useReportContextQueries() {
  const { hasPermission } = usePermissions()
  const canReadReport = hasPermission('report:read')
  const canReadTask = hasPermission('task:read')

  const reportsQuery = useQuery({
    queryKey: ['ai-chat', 'report-context', 'reports'],
    queryFn: () =>
      fetchReportList({
        page: 1,
        per_page: REPORT_CONTEXT_PAGE_SIZE,
        favorite: false,
        deleted: false,
        sort_by: 'updated_at',
        order: 'desc',
      }),
    enabled: canReadReport,
    staleTime: 30_000,
  })

  const tasksQuery = useQuery({
    queryKey: ['ai-chat', 'report-context', 'tasks'],
    queryFn: fetchCompletedTasks,
    enabled: canReadTask,
    staleTime: 30_000,
  })

  const { groups, options } = useMemo(() => {
    const reportOptions: ReportContextOption[] = (reportsQuery.data?.items ?? [])
      .filter((report) => !report.deleted)
      .slice(0, REPORT_CONTEXT_PAGE_SIZE)
      .map((report) => {
        const type = toReportContextType(report.type)
        return {
          id: String(report.id),
          label: report.name,
          type,
          badge: TYPE_BADGES[type],
          description: [
            `来源：报告 #${report.id}`,
            report.task_name ? `任务：${report.task_name}` : '',
          ]
            .filter(Boolean)
            .join(' · '),
        }
      })

    const taskOptions: ReportContextOption[] = canReadTask
      ? (tasksQuery.data ?? [])
          .slice(0, TASK_CONTEXT_PAGE_SIZE)
          .map((task) => ({
            id: String(task.id),
            label: task.name,
            type: 'task_context' as const,
            badge: TYPE_BADGES.task_context,
            description: `来源：任务 #${task.id} · 已完成`,
          }))
      : []

    const allGroups: ReportContextGroup[] = [
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
    return {
      groups: allGroups.filter((group) => group.options.length > 0),
      options: [...reportOptions, ...taskOptions],
    }
  }, [canReadTask, reportsQuery.data, tasksQuery.data])

  const isError = reportsQuery.isError || tasksQuery.isError
  const isLoading =
    (canReadReport && reportsQuery.isLoading) ||
    (canReadTask && tasksQuery.isLoading)

  return {
    groups,
    options,
    isLoading,
    isError,
    error: reportsQuery.error ?? tasksQuery.error,
    refetch: () => {
      if (canReadReport) void reportsQuery.refetch()
      if (canReadTask) void tasksQuery.refetch()
    },
  }
}

/** 选择器专用：按选中 id 找 label（URL 上下文不在列表里时用降级名） */
export function useReportContext() {
  const { groups, options, isLoading, isError } = useReportContextQueries()
  return { groups, options, isLoading, isError }
}
