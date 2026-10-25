/**
 * 任务详情内容组件（09_任务域.md §4，双形态共享：路由页 /tasks/:id 与快览弹窗）。
 * 三卡纵排：任务信息卡 / 进度概览卡 / 关联用例·设备（Tabs）；API/混合任务追加 API 资源管理；
 * 底部实时日志卡 + 操作按钮组（§4.7 状态机）。重新执行/重新评估经 §5.7 范围选择弹窗发起。
 * INT-932 接线：暂停/继续（POST /tasks/{id}/control）、停止测试（POST /tasks/{id}/stop）
 * 经 useTaskActions 发真实请求，成功后详情/列表刷新；API 资源管理去掉 mock 并发数据，
 * 仅渲染真实 apis（id/name/status，status=online 在线）。
 * INT-949：停止/暂停/继续点击先弹 ConfirmDialog（§5.8 + 旧 Vue 基线），确认才发请求。
 * INT-1241：任务类型概念已移除——API 资源区按真实 apis 数据无条件渲染（不再按任务类型推导显隐）。
 */
import { ChevronRight, Pause, Play, RefreshCw, RotateCcw, Square } from 'lucide-react'
import { useState } from 'react'

import { usePermissions } from '@/application/hooks/use-permissions'
import { useContainerComposition } from '@/application/tasks/use-container-composition'
import { useTaskActions } from '@/application/tasks/use-task-actions'
import { useTaskDetail } from '@/application/tasks/use-task-detail'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { CaseAssociation } from '@/features/tasks/detail/case-association'
import { ContainerComposition } from '@/features/tasks/detail/container-composition'
import { ContainerHeaderBadges } from '@/features/tasks/detail/container-header-badges'
import { ProgressCard } from '@/features/tasks/detail/progress-card'
import { RealtimeLogs } from '@/features/tasks/detail/realtime-logs'
import { TaskInfoCard } from '@/features/tasks/detail/task-info-card'
import { TaskReportDocuments } from '@/features/tasks/detail/task-report-documents'
import { ReexecuteScopeDialog } from '@/features/tasks/components/reexecute-scope-dialog'
import {
  TaskConfirmDialog,
  type TaskConfirmState,
} from '@/features/tasks/components/task-confirm-dialogs'

/** API 资源管理（§4.5，真实 apis 简报：名称 + 在线状态；INT-1241 起无条件渲染） */
function ApiResources({ apis }: { apis: Array<{ id: number; name: string; status: string | null }> }) {
  if (apis.length === 0) return null
  return (
    <Card size='sm' className='gap-3 py-3'>
      <CardHeader className='px-4'>
        <CardTitle className='text-sm font-medium'>API资源管理</CardTitle>
      </CardHeader>
      <CardContent className='px-4 pb-1'>
        <div className='flex flex-col gap-2'>
          {apis.map((api) => (
            <div key={api.id} className='flex flex-wrap items-center gap-3 rounded-lg border px-3 py-2 text-sm'>
              <span
                aria-hidden='true'
                className={cn(
                  'size-2 rounded-full',
                  api.status === 'online' ? 'bg-success' : 'bg-muted'
                )}
              />
              <span className='font-medium'>{api.name}</span>
              <span className='text-muted-foreground text-xs'>
                {api.status === 'online' ? '在线' : '离线'}
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

export function TaskDetailContent({
  taskId,
  compact = false,
  mode = 'view',
  onCaseSelect,
  deviceTypesOverride,
}: {
  taskId: number
  /** 快览弹窗态：底部不重复操作按钮组（§5.1 只加关闭钮） */
  compact?: boolean
  /** execution 态（10_测试执行.md §3.7）：实时日志注入级别过滤/搜索/导出 + Realtime frame 增量条 */
  mode?: 'view' | 'execution'
  /** 关联用例行点击（→ 测试执行 §5.2 用例详情弹窗） */
  onCaseSelect?: (caseId: string) => void
  /** device_types 覆盖（测试执行流程启动时落定的混跑类型；未传用详情数据自身） */
  deviceTypesOverride?: string[]
}) {
  const { hasPermission } = usePermissions()
  const detailQuery = useTaskDetail(taskId)
  const actions = useTaskActions()
  // 容器识别 + 组成数据（§5.5.2 ⑤：source 端点 200 → 容器；任意 ApiError → null 静默非容器）
  const composition = useContainerComposition(taskId)
  const isContainer = composition.isContainer
  const [casesOpen, setCasesOpen] = useState(false)
  const [reexecuteAction, setReexecuteAction] = useState<'retry' | 'reevaluate' | null>(null)
  const [confirm, setConfirm] = useState<TaskConfirmState | null>(null)
  const [confirmPending, setConfirmPending] = useState(false)

  /** 确认后才发请求（INT-949 停止/暂停/继续）；失败 toast 由 mutation onError 处理 */
  const handleConfirm = async () => {
    if (!confirm) return
    setConfirmPending(true)
    try {
      if (confirm.kind === 'detail-stop') {
        await actions.stop.mutateAsync(taskId)
      } else if (confirm.kind === 'detail-control') {
        await actions.control.mutateAsync({ taskId, action: confirm.action })
      } else {
        return
      }
      setConfirm(null)
    } catch {
      // mutation onError 已 toast
    } finally {
      setConfirmPending(false)
    }
  }

  const detail = detailQuery.data
  if (detailQuery.isPending) {
    // 首次加载骨架屏（路由页恒渲染本组件，loading 内聚；避免观察者卸载/重挂载 refetch 循环）
    return (
      <div className='flex flex-col gap-4'>
        <Skeleton className='h-36 w-full rounded-xl' />
        <Skeleton className='h-44 w-full rounded-xl' />
        <Skeleton className='h-64 w-full rounded-xl' />
      </div>
    )
  }
  if (detailQuery.isError) {
    // 详情接口失败（如后端 TaskCaseBrief 校验 422）→ 错误态 + 重试，不渲染空白：
    // 详情卡以 Empty 提示并给重试，实时日志（独立 /logs 数据源）仍正常渲染（INT-1033）
    return (
      <div className='flex flex-col gap-4'>
        <Empty className='border-dashed rounded-xl border px-6 py-12'>
          <EmptyHeader>
            <EmptyMedia variant='icon'>
              <RefreshCw aria-hidden='true' className='size-4' />
            </EmptyMedia>
            <EmptyTitle>任务详情加载失败</EmptyTitle>
            <EmptyDescription>
              {detailQuery.error instanceof Error
                ? detailQuery.error.message
                : '请稍后重试或联系管理员'}
            </EmptyDescription>
            <EmptyContent>
              <Button variant='outline' size='sm' onClick={() => detailQuery.refetch()}>
                重试
              </Button>
            </EmptyContent>
          </EmptyHeader>
        </Empty>
        <RealtimeLogs
          taskId={taskId}
          executionMode={mode === 'execution'}
          hasRealtimeDevice={false}
        />
      </div>
    )
  }
  if (!detail) return null

  const effectiveDeviceTypes = deviceTypesOverride ?? detail.device_types
  // INT-1241：API 资源区按真实 apis 数据无条件渲染（不再按任务类型推导显隐）
  const hasRealtimeDevice = effectiveDeviceTypes.includes('websocket_api')
  const isTerminal = ['completed', 'failed', 'stopped', 'merged', 'skipped'].includes(
    detail.execution_status ?? ''
  )
  const pending = actions.control.isPending || actions.stop.isPending

  return (
    <>
      <div className='flex flex-col gap-4'>
        <TaskInfoCard
          detail={detail}
          headerExtra={
            isContainer ? (
              <ContainerHeaderBadges trace={composition.trace} detail={detail} />
            ) : undefined
          }
        />
        {/* §5.5.2 ④ 容器版面：组成区紧跟信息卡（首屏主区）；进度卡 / 实时日志卡对容器隐藏 */}
        {isContainer && (
          <ContainerComposition
            trace={composition.trace}
            entries={composition.entries}
            summary={composition.summary}
          />
        )}
        {!isContainer && <ProgressCard detail={detail} />}
        <ApiResources apis={detail.apis} />
        {/* 关联用例卡对容器降级为「用例清单」折叠区，置于组成区之后 */}
        {isContainer ? (
          <Collapsible open={casesOpen} onOpenChange={setCasesOpen}>
            <div className='bg-card rounded-xl border'>
              <CollapsibleTrigger className='hover:bg-muted/40 flex w-full flex-wrap items-center gap-2 rounded-xl px-4 py-3 text-left transition-colors'>
                <ChevronRight
                  aria-hidden='true'
                  className={cn(
                    'text-muted-foreground size-4 shrink-0 transition-transform',
                    casesOpen && 'rotate-90'
                  )}
                />
                <span className='text-sm font-medium'>用例清单</span>
                <Badge variant='secondary' className='rounded-md px-1.5 text-[11px] tabular-nums'>
                  {detail.cases?.length ?? 0} 个
                </Badge>
                <span className='text-muted-foreground text-xs'>
                  组成区已按用例组织，此处为平铺清单
                </span>
              </CollapsibleTrigger>
              <CollapsibleContent className='border-t p-2'>
                <CaseAssociation detail={detail} onCaseSelect={onCaseSelect} />
              </CollapsibleContent>
            </div>
          </Collapsible>
        ) : (
          <CaseAssociation detail={detail} onCaseSelect={onCaseSelect} />
        )}

        {/* 报告文档（INT-1766 3b：上传独立报告关联本任务后在此可见；快览弹窗态不渲染） */}
        {!compact && hasPermission('report:read') && <TaskReportDocuments taskId={taskId} />}


        {!compact && (
          <div className='flex flex-wrap items-center gap-2'>
            {hasPermission('task:execute') &&
              !isTerminal &&
              detail.execution_status !== 'pending' && (
                <Button
                  size='sm'
                  disabled={pending}
                  onClick={() =>
                    setConfirm({
                      kind: 'detail-control',
                      action: detail.execution_status === 'paused' ? 'resume' : 'pause',
                    })
                  }
                >
                  {detail.execution_status === 'paused' ? (
                    <>
                      <Play aria-hidden='true' className='size-3.5' />
                      继续
                    </>
                  ) : (
                    <>
                      <Pause aria-hidden='true' className='size-3.5' />
                      暂停
                    </>
                  )}
                </Button>
              )}
            {hasPermission('task:execute') &&
              !isTerminal &&
              detail.execution_status !== 'pending' && (
                <Button
                  size='sm'
                  variant='destructive'
                  disabled={pending}
                  onClick={() => setConfirm({ kind: 'detail-stop' })}
                >
                  <Square aria-hidden='true' className='size-3.5' />
                  停止测试
                </Button>
              )}
            {hasPermission('task:execute') &&
              ['pending', 'failed', 'completed', 'stopped'].includes(detail.execution_status ?? '') && (
                <Button
                  size='sm'
                  variant='outline'
                  disabled={pending}
                  onClick={() => setReexecuteAction('retry')}
                >
                  <RotateCcw aria-hidden='true' className='size-3.5' />
                  重新执行
                </Button>
              )}
            {hasPermission('evaluation:execute') && isTerminal && (
              <Button
                size='sm'
                variant='outline'
                disabled={pending}
                onClick={() => setReexecuteAction('reevaluate')}
              >
                重新评估
              </Button>
            )}
            {pending && (
              <Badge variant='secondary' className='rounded-md px-1.5 text-[11px]'>
                控制中…
              </Badge>
            )}
          </div>
        )}

        {!isContainer && (
          <RealtimeLogs
            taskId={taskId}
            executionMode={mode === 'execution'}
            hasRealtimeDevice={hasRealtimeDevice}
          />
        )}
      </div>

      <ReexecuteScopeDialog
        open={reexecuteAction != null}
        onOpenChange={(open) => !open && setReexecuteAction(null)}
        taskId={taskId}
        taskName={detail.name}
        actionType={reexecuteAction ?? 'retry'}
      />

      {/* 详情控制确认（INT-949：停止/暂停/继续，取消不发请求） */}
      <TaskConfirmDialog
        open={confirm != null}
        state={confirm}
        onOpenChange={(open) => !open && setConfirm(null)}
        isLoading={confirmPending}
        onConfirm={() => void handleConfirm()}
      />
    </>
  )
}
