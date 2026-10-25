/**
 * 容器详情「报告」卡（18_挑选合并功能交互重设计.md §5.5.2 ④ / §5.5.6，INT-1717）。
 * 容器无执行过程、不自动生成报告 → 报告区空态直接引导手动生成
 * （「该合并任务暂无报告」/「合并任务无执行过程，报告需手动生成」+「生成报告」）。
 * 已有报告时给「查看报告」入口（`GET /reports?task_id=` 复用既有列表端点，不新增端点）；
 * 生成走既有 `POST /reports/generate-task`（不新增端点）。
 */
import { Link } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { FileText, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { fetchReportList, generateTaskReport } from '@/infrastructure/api/reports-api'
import { ApiError } from '@/infrastructure/api/api-error'

export function ContainerReportCard({ taskId }: { taskId: number }) {
  const { hasPermission } = usePermissions()
  const [pending, setPending] = useState(false)
  /** 后端生成是异步的（`POST /reports/generate-task` → status=generating），生成后轮询列表直到出现 */
  const [generating, setGenerating] = useState(false)

  // 该任务已有报告（容器不自动生成，一般为手动生成过的）——详情接口不返 reports 计数，
  // 这里用既有列表端点按 task_id 过滤取最新一份，不新增端点。
  const reportsQuery = useQuery({
    queryKey: ['reports', 'by-task', taskId],
    queryFn: () =>
      fetchReportList({
        page: 1,
        per_page: 1,
        task_id: taskId,
        sort_by: 'created_at',
        order: 'desc',
        favorite: false,
        deleted: false,
      }),
    staleTime: 15_000,
    refetchInterval: generating ? 2_000 : false,
  })
  const report = reportsQuery.data?.items?.[0]

  // 出现报告即停止轮询；60s 仍未出现按「暂无报告」收尾（后端异步可能更久，刷新可再查）
  useEffect(() => {
    if (!generating) return
    if (report) {
      setGenerating(false)
      return
    }
    const timer = window.setTimeout(() => setGenerating(false), 60_000)
    return () => window.clearTimeout(timer)
  }, [generating, report])

  const generate = async () => {
    setPending(true)
    try {
      await generateTaskReport({ task_id: taskId })
      toast.success('报告生成成功')
      setGenerating(true)
      await reportsQuery.refetch()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.userMessage : '生成报告失败，请重试')
    } finally {
      setPending(false)
    }
  }

  return (
    <Card size='sm' className='gap-3 py-3'>
      <CardHeader className='flex flex-wrap items-center gap-2 px-4'>
        <CardTitle className='text-sm font-medium'>报告</CardTitle>
        {report && hasPermission('report:read') && (
          <Button
            size='sm'
            variant='outline'
            className='ml-auto h-7'
            render={<Link to='/report/$reportId' params={{ reportId: String(report.id) }} />}
          >
            查看报告
          </Button>
        )}
      </CardHeader>
      <CardContent className='px-4 pb-1'>
        {reportsQuery.isLoading ? (
          <Skeleton className='h-16 w-full rounded-xl' />
        ) : reportsQuery.isError ? (
          <Empty className='rounded-xl border border-dashed py-8'>
            <EmptyHeader>
              <EmptyMedia variant='icon'>
                <RefreshCw aria-hidden='true' className='size-4' />
              </EmptyMedia>
              <EmptyTitle>报告加载失败</EmptyTitle>
              <EmptyDescription>该任务的报告列表没能加载出来</EmptyDescription>
            </EmptyHeader>
            <EmptyContent>
              <Button variant='outline' size='sm' onClick={() => void reportsQuery.refetch()}>
                重试
              </Button>
            </EmptyContent>
          </Empty>
        ) : report ? (
          <div className='flex flex-wrap items-center gap-2 rounded-xl border px-3 py-2'>
            <span className='min-w-0 truncate text-sm font-medium'>{report.name}</span>
            <StatusBadge
              label={report.status === 'published' ? '已发布' : '草稿'}
              variant={report.status === 'published' ? 'success' : 'neutral'}
            />
            <span className='text-muted-foreground font-mono text-[11px] tabular-nums'>
              ID {report.id}
            </span>
          </div>
        ) : generating ? (
          // 后端异步生成中（status=generating）：轮询列表，不谎报「暂无报告」
          <Empty className='rounded-xl border border-dashed py-8'>
            <EmptyHeader>
              <EmptyMedia variant='icon'>
                <RefreshCw aria-hidden='true' className='size-4 animate-spin' />
              </EmptyMedia>
              <EmptyTitle>报告生成中…</EmptyTitle>
              <EmptyDescription>生成完成后自动显示报告入口</EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          <Empty className='rounded-xl border border-dashed py-8'>
            <EmptyHeader>
              <EmptyMedia variant='icon'>
                <FileText aria-hidden='true' className='size-4' />
              </EmptyMedia>
              <EmptyTitle>该合并任务暂无报告</EmptyTitle>
              <EmptyDescription>合并任务无执行过程，报告需手动生成</EmptyDescription>
            </EmptyHeader>
            {hasPermission('report:create') && (
              <EmptyContent>
                <Button size='sm' disabled={pending} onClick={() => void generate()}>
                  {pending ? '生成中…' : '生成报告'}
                </Button>
              </EmptyContent>
            )}
          </Empty>
        )}
      </CardContent>
    </Card>
  )
}
