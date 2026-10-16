/**
 * 步骤五：查看结果（interfaces/features/test-execution/components；10_测试执行.md §3.8）。
 * 任务终态自动触发报告生成（POST /reports/generate-task，report:create）；生成中 Loader +
 * 「正在生成报告…」；失败 Alert destructive + 重试。装配 INT-439 报告组件嵌入式——
 * 隐藏返回行/右导航 scrollspy/底部操作条，仅渲染报告头信息卡 + 主列（按 type 分发）。
 * readOnly（§3.1.1）：报告内容只读可见；保存/导出/发布/重试/重新生成/开始新测试隐藏。
 */
import { RefreshCw } from 'lucide-react'
import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'

import { useReportStep } from '@/application/test-execution/useReportStep'
import { fetchFlowReport } from '@/infrastructure/api/test-execution-api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { CopyButton } from '@/components/copy-button'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { TaskReportPanel } from '@/features/report-view/components/task-report-panel'
import { ComparisonReportPanel } from '@/features/report-view/components/comparison-report-panel'
import {
  formatDateTime,
  getAlgorithmLabel,
  REPORT_STATUS_META,
  REPORT_TYPE_META,
} from '@/features/reports/constants'

interface StepReportProps {
  taskId: number
  readOnly: boolean
}

export function StepReport({ taskId, readOnly }: StepReportProps) {
  const { reportId, reportStatus, reportError, retry, triggerGenerate } = useReportStep()

  // 进入步骤五：任务终态自动触发报告生成（report:create）
  useEffect(() => {
    if (reportStatus === 'idle') void triggerGenerate(taskId)
  }, [reportStatus, taskId, triggerGenerate])

  const detailQuery = useQuery({
    queryKey: ['test-execution', 'flow-report', reportId],
    queryFn: () => fetchFlowReport(reportId ?? 0),
    enabled: reportStatus === 'ready' && reportId != null,
    staleTime: 30_000,
  })

  if (reportStatus === 'generating' || reportStatus === 'idle') {
    return (
      <div className='flex flex-col items-center justify-center gap-3 py-16'>
        <Skeleton className='h-8 w-48 rounded-lg' />
        <div className='flex items-center gap-2 text-sm'>
          <RefreshCw aria-hidden='true' className='size-4 animate-spin' />
          <span className='text-muted-foreground'>正在生成报告…</span>
        </div>
      </div>
    )
  }

  if (reportStatus === 'failed') {
    return (
      <Alert variant='destructive'>
        <AlertDescription className='flex flex-wrap items-center gap-2 text-sm'>
          <span>报告生成失败：{reportError ?? '未知错误'}</span>
          {!readOnly && (
            <Button variant='outline' size='sm' className='h-6 text-xs' onClick={() => void retry()}>
              重试
            </Button>
          )}
        </AlertDescription>
      </Alert>
    )
  }

  const report = detailQuery.data
  if (!report) {
    return (
      <div aria-busy='true' className='space-y-4'>
        <Skeleton className='h-28 w-full rounded-2xl' />
        <Skeleton className='h-64 w-full rounded-xl' />
      </div>
    )
  }

  const isComparison = report.type === 'comparison' || report.type === 'secondary_comparison'
  const typeMeta = REPORT_TYPE_META[report.type]
  const statusMeta = REPORT_STATUS_META[report.status]

  return (
    <div className='space-y-6'>
      {/* 嵌入式报告头信息卡（INT-439 报告头；返回行/右导航/底部操作条由本页动作条替代） */}
      <div className='bg-card from-primary/5 via-transparent to-transparent rounded-2xl border bg-gradient-to-br p-5 sm:p-6'>
        <div className='flex flex-wrap items-start justify-between gap-3'>
          <div className='min-w-0 flex-1'>
            <div className='flex flex-wrap items-center gap-2'>
              <h3 className='font-mono max-w-full text-xl leading-tight font-bold tracking-tight break-all'>
                {report.name}
              </h3>
              <CopyButton value={report.name} aria-label='复制报告名称' />
            </div>
            <div className='mt-2 flex flex-wrap items-center gap-2 text-sm'>
              <StatusBadge label={typeMeta.label} variant={typeMeta.variant} />
              <StatusBadge label={statusMeta.label} variant={statusMeta.variant} />
              {report.algorithm_type && (
                <Badge variant='secondary'>算法：{getAlgorithmLabel(report.algorithm_type)}</Badge>
              )}
            </div>
            <div className='text-muted-foreground mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs'>
              <span className='flex items-center gap-1'>
                任务：{report.task_name}
                <span className='font-mono'>#{report.task_id ?? ''}</span>
              </span>
              <span className='font-mono tabular-nums'>创建于 {formatDateTime(report.created_at)}</span>
              {report.updated_at && (
                <span className='font-mono tabular-nums'>更新于 {formatDateTime(report.updated_at)}</span>
              )}
            </div>
            {report.description && (
              <p className='text-muted-foreground mt-3 text-sm leading-relaxed'>{report.description}</p>
            )}
          </div>
        </div>
      </div>

      {/* 主列（按 type 分发；嵌入式契约仅渲染主列） */}
      <div className='min-w-0'>
        {isComparison ? (
          <ComparisonReportPanel
            report={report}
            editing={false}
            onStartEditing={() => {}}
            onExitEditing={() => {}}
            onSaveAnalysis={() => {}}
          />
        ) : (
          <TaskReportPanel
            report={report}
            editing={false}
            onStartEditing={() => {}}
            onExitEditing={() => {}}
            onSaveAnalysis={() => {}}
          />
        )}
      </div>
    </div>
  )
}
