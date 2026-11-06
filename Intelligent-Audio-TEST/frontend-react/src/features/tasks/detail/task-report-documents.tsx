/**
 * 任务详情「报告文档」区（INT-1766 3b：上传独立报告关联任务后，任务详情可见）。
 *
 * 取数口径与后端一致：上传时给的 task_id 只落成「该任务最新未删除报告」的 report_id
 * （report_service `_report_id_by_task`；没有可见报告时 404、不静默建无主文档），所以先按
 * task_id 取报告 id，再按 report_id 列出该报告下的全部 Studio 文档（上传文档 / Agent 总结 /
 * 平台报告文档），与报告详情页文档区（固定 source_type=platform_report）互不混排。
 *
 * 任务没有报告时不渲染本区（此时上传关联任务本身会被后端拒绝，没有可展示的文档）。
 */
import { useTaskReportId } from '@/application/reports/use-report-studio'
import { Skeleton } from '@/components/ui/skeleton'
import { StudioDocumentSection } from '@/features/reports/components/studio-document-section'

export function TaskReportDocuments({ taskId }: { taskId: number }) {
  const reportQuery = useTaskReportId(taskId)

  if (reportQuery.isLoading) {
    return <Skeleton className='h-32 w-full rounded-xl' />
  }
  const reportId = reportQuery.data
  if (reportId == null) return null

  return (
    <StudioDocumentSection
      description='与该任务报告关联的 Report Studio 文档：上传的独立报告、搬运回来的 Agent 总结与平台报告文档。'
      emptyText='该任务的报告暂无关联文档'
      reportId={reportId}
      title='报告文档'
    />
  )
}
