/**
 * 任务详情路由页（09_任务域.md §4.1 主形态）。
 * SectionPageLayout（Breadcrumb 任务管理 / {任务名} + Title=任务名 + 返回列表）
 * + Content 三卡纵排（TaskDetailContent 共享组件）。
 * 说明：TanStack Router 不允许同层级两个 `$param` 兄弟路由（后注册者共享树节点被前
 * 者遮蔽），因此详情并入 /tasks/$tab 分支渲染（tab 参数为数字时走本页），URL 仍为
 * /tasks/:id（§4.1 口径保留）。
 */
import { Link } from '@tanstack/react-router'
import { ChevronLeft } from 'lucide-react'

import { useTaskDetail } from '@/application/tasks/use-task-detail'
import { Button } from '@/components/ui/button'
import { SectionPageLayout } from '@/components/layout/components/section-page-layout'
import { Skeleton } from '@/components/ui/skeleton'
import { TaskDetailContent } from '@/features/tasks/detail/task-detail-content'

export function TaskDetailRoutePage({ taskId }: { taskId: number }) {
  const detailQuery = useTaskDetail(taskId)
  const name = detailQuery.data?.name ?? '任务详情'

  return (
    <SectionPageLayout>
      <SectionPageLayout.Breadcrumb>
        <nav aria-label='面包屑' className='text-sm'>
          <ol className='flex flex-wrap items-center gap-1.5'>
            <li>
              <Link
                to='/tasks/$tab'
                params={{ tab: 'daily' }}
                className='text-muted-foreground hover:text-foreground transition-colors'
              >
                任务管理
              </Link>
            </li>
            <li aria-hidden='true' className='text-muted-foreground/50'>/</li>
            <li aria-current='page' className='max-w-64 truncate font-medium'>
              {detailQuery.isLoading ? '…' : name}
            </li>
          </ol>
        </nav>
      </SectionPageLayout.Breadcrumb>

      <SectionPageLayout.Title>{name}</SectionPageLayout.Title>

      <SectionPageLayout.Actions>
        <Button
          size='sm'
          variant='outline'
          className='h-7 gap-1.5'
          render={<Link to='/tasks/$tab' params={{ tab: 'daily' }} />}
        >
          <ChevronLeft aria-hidden='true' className='size-3.5' />
          返回任务列表
        </Button>
      </SectionPageLayout.Actions>

      <SectionPageLayout.Content>
        {detailQuery.isLoading ? (
          <div className='flex flex-col gap-4'>
            <Skeleton className='h-36 w-full rounded-xl' />
            <Skeleton className='h-44 w-full rounded-xl' />
            <Skeleton className='h-64 w-full rounded-xl' />
          </div>
        ) : (
          <TaskDetailContent taskId={taskId} />
        )}
      </SectionPageLayout.Content>
    </SectionPageLayout>
  )
}
