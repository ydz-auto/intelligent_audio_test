/**
 * 任务详情内容组件（09_任务域.md §4，双形态共享：路由页 /tasks/:id 与快览弹窗）。
 * 三卡纵排：任务信息卡 / 进度概览卡 / 关联用例·设备（Tabs）；API/混合任务追加 API 资源管理；
 * 底部实时日志卡 + 操作按钮组（§4.7 状态机）。
 */
import { Pause, Play, RefreshCw, RotateCcw, Square } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
import { useTaskDetail } from '@/application/tasks/use-task-detail'
import { Badge } from '@/components/ui/badge'
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
import { Progress } from '@/features/tasks/components/ui/progress'
import { CaseAssociation } from '@/features/tasks/detail/case-association'
import { ProgressCard } from '@/features/tasks/detail/progress-card'
import { RealtimeLogs } from '@/features/tasks/detail/realtime-logs'
import { TaskInfoCard } from '@/features/tasks/detail/task-info-card'

/** API 资源管理（§4.5，仅 API/混合任务；纯展示无操作） */
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
              <span className='font-medium'>{api.name}</span>
              <span className='text-muted-foreground text-xs tabular-nums'>
                当前并发 2/4 · 队列长度 3 · 平均响应时间 214ms
              </span>
              <Progress value={50} size='sm' className='min-w-28 flex-1' />
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
  const [pending, setPending] = useState<string | null>(null)

  const detail = detailQuery.data
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
  const isApi = effectiveDeviceTypes.includes('http_api')
  const hasRealtimeDevice = effectiveDeviceTypes.includes('websocket_api')
  const isTerminal = ['completed', 'failed', 'stopped', 'merged', 'skipped'].includes(
    detail.execution_status ?? ''
  )

  const act = (key: string, success: string) => {
    setPending(key)
    setTimeout(() => {
      setPending(null)
      toast.success(success)
    }, 600)
  }

  return (
    <div className='flex flex-col gap-4'>
      <TaskInfoCard detail={detail} />
      <ProgressCard detail={detail} />
      {isApi && <ApiResources apis={detail.apis} />}
      <CaseAssociation detail={detail} onCaseSelect={onCaseSelect} />

      {!compact && (
        <div className='flex flex-wrap items-center gap-2'>
          {hasPermission('task:execute') &&
            !isTerminal &&
            detail.execution_status !== 'pending' && (
              <Button
                size='sm'
                disabled={pending != null}
                onClick={() =>
                  act('pause', detail.execution_status === 'paused' ? '任务已继续' : '任务已暂停')
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
                disabled={pending != null}
                onClick={() => act('stop', '任务已停止')}
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
                disabled={pending != null}
                onClick={() => act('rerun', '已发起重新执行')}
              >
                <RotateCcw aria-hidden='true' className='size-3.5' />
                重新执行
              </Button>
            )}
          {hasPermission('evaluation:execute') && isTerminal && (
            <Button
              size='sm'
              variant='outline'
              disabled={pending != null}
              onClick={() => act('reeval', '已发起重新评估')}
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

      <RealtimeLogs
        taskId={taskId}
        executionMode={mode === 'execution'}
        hasRealtimeDevice={hasRealtimeDevice}
      />
    </div>
  )
}
