/**
 * 任务详情路由页（09_任务域.md §4.1 主形态）。
 * SectionPageLayout（Breadcrumb 任务管理 / {任务名} + Title=任务名 + 返回列表）
 * + Content 三卡纵排（TaskDetailContent 共享组件）。
 * 关联用例行 onCaseSelect（09 §4.4）→ 用例执行详情模态窗（10 §5.2 CaseDetailDialog，
 * INT-1066 接线；任务详情/测试执行步骤四共用组件）。
 * 说明：TanStack Router 不允许同层级两个 `$param` 兄弟路由（后注册者共享树节点被前
 * 者遮蔽），因此详情并入 /tasks/$tab 分支渲染（tab 参数为数字时走本页），URL 仍为
 * /tasks/:id（§4.1 口径保留）。
 */
import { Link } from '@tanstack/react-router'
import { ChevronLeft, Pencil } from 'lucide-react'
import { useState } from 'react'

import { usePermissions } from '@/application/hooks/use-permissions'
import { useTaskDetail } from '@/application/tasks/use-task-detail'
import { Button } from '@/components/ui/button'
import { SectionPageLayout } from '@/components/layout/components/section-page-layout'
import {
  RenameTaskDialog,
  type RenameTaskTarget,
} from '@/features/tasks/components/rename-task-dialog'
import { TaskDetailContent } from '@/features/tasks/detail/task-detail-content'
import { CaseDetailDialog } from '@/features/test-execution/modals/case-detail-dialog'

export function TaskDetailRoutePage({ taskId }: { taskId: number }) {
  const { hasPermission } = usePermissions()
  const detailQuery = useTaskDetail(taskId)
  const name = detailQuery.data?.name ?? '任务详情'
  // 关联用例行点击 → 用例执行详情模态窗（09 §4.4 onCaseSelect → 10 §5.2，INT-1066）
  const [caseDetail, setCaseDetail] = useState<{ caseId: string } | null>(null)
  // 重命名（INT-1290：详情页「重命名」→ 名称编辑弹窗，保存后经 ['tasks'] 前缀刷新详情）
  const [renameTask, setRenameTask] = useState<RenameTaskTarget | null>(null)

  return (
    <>
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
          {hasPermission('task:update') && detailQuery.data && (
            <Button
              size='sm'
              variant='outline'
              className='h-7 gap-1.5'
              onClick={() => setRenameTask({ id: taskId, name: detailQuery.data!.name })}
            >
              <Pencil aria-hidden='true' className='size-3.5' />
              重命名
            </Button>
          )}
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
        {/* INT-932 P2-2：恒渲染 TaskDetailContent（loading 内聚组件内部），
            避免「loading→卸载观察者→error→重挂载→refetchOnMount」无限 refetch 循环 */}
        <TaskDetailContent
          taskId={taskId}
          onCaseSelect={(caseId) => setCaseDetail({ caseId })}
        />
      </SectionPageLayout.Content>
    </SectionPageLayout>

    {/* 关联用例行点击 → 用例执行详情模态窗（10 §5.2；任务详情/测试执行共用组件） */}
    <CaseDetailDialog
      open={caseDetail != null}
      onOpenChange={(next) => {
        if (!next) setCaseDetail(null)
      }}
      taskId={taskId}
      caseId={caseDetail?.caseId ?? ''}
    />

    {/* 重命名（INT-1290：详情页名称编辑弹窗） */}
    <RenameTaskDialog
      open={renameTask != null}
      onOpenChange={(open) => !open && setRenameTask(null)}
      task={renameTask}
    />
  </>

  )
}
