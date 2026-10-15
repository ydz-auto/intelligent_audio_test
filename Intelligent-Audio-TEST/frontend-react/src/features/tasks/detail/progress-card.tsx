/**
 * 进度概览卡（09_任务域.md §4.3，Card）。
 * 总进度 Progress h-2（指示 bg-primary + 失败段叠加 destructive）+ 大号百分数 + 时间行；
 * 五统计格 `grid grid-cols-2 sm:grid-cols-5`：已完成(success 软底)/进行中(warning)/待执行(muted)/
 * 执行失败(destructive)/评估失败(info)；WS 断开降级 Alert（INT-203 文案保留，mock 不触发）。
 */
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { TaskDetailData } from '@/domain/models/task'
import { Progress } from '@/features/tasks/components/ui/progress'

const STAT_CELLS = [
  { key: 'completed', label: '已完成', textClass: 'text-success bg-success/10' },
  { key: 'running', label: '进行中', textClass: 'text-warning bg-warning/10' },
  { key: 'pending', label: '待执行', textClass: 'text-muted-foreground bg-muted/50' },
  { key: 'failed', label: '执行失败', textClass: 'text-destructive bg-destructive/10' },
  { key: 'eval-failed', label: '评估失败', textClass: 'text-info bg-info/10' },
]

export function ProgressCard({ detail }: { detail: TaskDetailData }) {
  const completed = detail.completed_cases ?? 0
  const failed = detail.failed_cases ?? 0
  const total = detail.total_cases ?? 0
  const running = detail.execution_status === 'running' || detail.execution_status === 'queued'
    ? total - completed - failed
    : 0
  const pending = Math.max(0, total - completed - failed - running)
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0
  const failedPercent = total > 0 ? Math.round((failed / total) * 100) : 0

  const values: Record<string, number> = {
    completed,
    running,
    pending,
    failed,
    'eval-failed': detail.cases.filter((c) => c.evaluation_status === 'failed').length,
  }

  return (
    <Card size='sm' className='gap-3 py-3'>
      <CardHeader className='px-4'>
        <CardTitle className='text-sm font-medium'>总进度</CardTitle>
      </CardHeader>
      <CardContent className='px-4 pb-1'>
        <div className='flex items-center gap-3'>
          <span className='text-2xl font-semibold tabular-nums'>{percent}%</span>
          <Progress
            value={percent}
            failedValue={failedPercent}
            size='md'
            className='flex-1'
          />
        </div>
        <p className='text-muted-foreground mt-1.5 text-xs tabular-nums'>
          已用时间 {detail.used_time ?? '—'} / 预计时间 {detail.expected_total_time ?? '—'}
        </p>

        <div className='mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5'>
          {STAT_CELLS.map((cell) => (
            <div
              key={cell.key}
              className={cn('flex flex-col gap-0.5 rounded-lg px-2.5 py-2', cell.textClass)}
            >
              <span className='font-mono text-lg leading-none font-semibold tabular-nums'>
                {values[cell.key] ?? 0}
              </span>
              <span className='text-xs opacity-80'>{cell.label}</span>
            </div>
          ))}
        </div>

        {/* 降级提示：mock 态不触发（INT-203 文案保留，接线后按实时通道状态展示）：
            实时连接已断开，进度已切换为 HTTP 轮询刷新（日志暂不可用），正在自动重连... */}
      </CardContent>
    </Card>
  )
}
