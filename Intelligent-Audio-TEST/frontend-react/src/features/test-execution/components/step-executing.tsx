/**
 * 步骤四：执行测试（interfaces/features/test-execution/components；10_测试执行.md §3.7）。
 * 装配复用 INT-354 TaskDetailContent（进度/关联用例/日志/WS 降级全复用，零重复定义）；
 * 差异注入：头部「返回上一步」outline 钮 + 实时日志增强/Realtime frame 增量（execution 模式）。
 * readOnly（§3.1.1）：进度/日志/关联用例只读可见；暂停/继续/停止/重执行/重评估/返回上一步隐藏。
 */
import { ArrowLeft } from 'lucide-react'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Button } from '@/components/ui/button'
import { TaskDetailContent } from '@/features/tasks/detail/task-detail-content'
import { useExecutionStore } from '@/infrastructure/stores/execution-store'

interface StepExecutingProps {
  taskId: number
  readOnly: boolean
  onBackToResources: () => void
  /** 关联用例行点击 → 用例详情弹窗（§5.2） */
  onCaseSelect: (caseId: string) => void
  /** 任务 device_types（启动时落定；isApi/hasRealtimeDevice 依据） */
  deviceTypes?: string[]
}

export function StepExecuting({
  taskId,
  readOnly,
  onBackToResources,
  onCaseSelect,
  deviceTypes,
}: StepExecutingProps) {
  const taskStarted = useExecutionStore((s) => s.taskId != null)

  return (
    <div className='flex flex-col gap-4'>
      {/* 头部：返回上一步（执行中允许回步骤三调整资源；已启动时钮带说明 Tooltip） */}
      {!readOnly && (
        <div className='flex items-center justify-between'>
          <div />
          <Tooltip>
            <TooltipTrigger
              render={
                <Button variant='outline' size='sm' onClick={onBackToResources}>
                  <ArrowLeft aria-hidden='true' className='size-3.5' />
                  返回上一步
                </Button>
              }
            />
            {taskStarted && (
              <TooltipContent side='bottom'>
                任务已启动，如需调整请停止后重新执行
              </TooltipContent>
            )}
          </Tooltip>
        </div>
      )}

      <TaskDetailContent
        taskId={taskId}
        mode='execution'
        onCaseSelect={onCaseSelect}
        deviceTypesOverride={deviceTypes}
      />
    </div>
  )
}
