/**
 * 容器信息头徽章组（18_挑选合并功能交互重设计.md §5.5.2 ②，INT-1711）。
 * 插在 `TaskInfoCard` 头行、任务名与状态徽章之后：合并方式 / 来源 n 任务 / 结果 m 条 /
 * 用例 c 个 / 部分失败 f（全部失败）。取值全部来自真实数据（source 端点 + 详情），不新增端点：
 * - 合并方式恒「结果挑选」（详情不渲染整任务合并徽章，§5.5.2 ⑤）；
 * - 来源任务 Popover 只列「任务名 + 该源结果数」，**源任务状态待 §11-8 增 `source_task_status`
 *   后才显示，落地前该位不渲染、不占位、不显示「—」**；
 * - 混合态判定 0 < failed_cases < case_count → 部分失败；failed_cases = case_count → 全部失败；
 *   failed_cases = 0 → 不显示（§5.5.4）。
 * 纯 props，不取数。
 */
import { Badge } from '@/components/ui/badge'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { Skeleton } from '@/components/ui/skeleton'
import type { ContainerSourceTrace } from '@/domain/models/cherryPick'
import type { TaskDetailData } from '@/domain/models/task'

/** 统计徽章（`text-xs` + mono 数字，§5.5.7 字体层级） */
function StatBadge({
  children,
  title,
}: {
  children: React.ReactNode
  title?: string
}) {
  return (
    <Badge
      variant='secondary'
      className='rounded-md px-1.5 font-mono text-xs tabular-nums'
      title={title}
    >
      {children}
    </Badge>
  )
}

export function ContainerHeaderBadges({
  trace,
  detail,
  loading = false,
}: {
  /** null = 非挑选合并容器（不渲染任何徽章，静默） */
  trace: ContainerSourceTrace | null
  detail: TaskDetailData
  loading?: boolean
}) {
  if (loading) {
    return (
      <div className='flex flex-wrap items-center gap-2' data-testid='container-badges-skeleton'>
        <Skeleton className='h-5 w-16 rounded-full' />
        <Skeleton className='h-5 w-20 rounded-full' />
        <Skeleton className='h-5 w-16 rounded-full' />
      </div>
    )
  }
  if (!trace) return null

  const sourceTaskCount = trace.groups.length
  const resultCount = trace.total ?? trace.groups.reduce((sum, g) => sum + g.results.length, 0)
  const caseCount = detail.case_count ?? detail.total_cases ?? detail.cases?.length ?? 0
  const failedCases = detail.failed_cases ?? 0
  const partial = failedCases > 0 && caseCount > 0 && failedCases < caseCount
  const allFailed = caseCount > 0 && failedCases >= caseCount

  return (
    <div
      className='flex flex-wrap items-center gap-1.5'
      data-testid='container-header-badges'
    >
      <Badge variant='outline' className='rounded-md px-1.5 text-xs'>
        结果挑选
      </Badge>

      <Popover>
        <PopoverTrigger
          render={
            <button
              type='button'
              className='focus-visible:ring-ring rounded-md focus-visible:ring-2 focus-visible:outline-none'
              aria-label={`来源 ${sourceTaskCount} 个任务`}
            />
          }
        >
          <StatBadge title='查看来源任务'>来源 {sourceTaskCount} 个任务</StatBadge>
        </PopoverTrigger>
        <PopoverContent align='start' className='min-w-64 p-1.5'>
          <p className='text-muted-foreground px-2 py-1 text-xs font-medium'>
            来源任务（{sourceTaskCount}）
          </p>
          {trace.groups.length === 0 ? (
            <p className='text-muted-foreground px-2 py-3 text-center text-xs'>
              该任务没有合并来源记录
            </p>
          ) : (
            trace.groups.map((group) => (
              <div
                key={group.sourceTaskId}
                className='hover:bg-accent flex items-center gap-2 rounded-md px-2 py-1.5'
              >
                <span className='min-w-0 flex-1 truncate text-sm'>
                  {group.sourceTaskName ?? `任务 ${group.sourceTaskId}`}
                </span>
                <span className='text-muted-foreground shrink-0 font-mono text-xs tabular-nums'>
                  {group.results.length} 条
                </span>
              </div>
            ))
          )}
        </PopoverContent>
      </Popover>

      <StatBadge>结果 {resultCount} 条</StatBadge>
      <StatBadge>用例 {caseCount} 个</StatBadge>

      {partial && (
        <Badge variant='warning' className='rounded-md px-1.5 text-xs tabular-nums'>
          部分失败 {failedCases}/{caseCount}
        </Badge>
      )}
      {allFailed && (
        <Badge variant='destructive' className='rounded-md px-1.5 text-xs tabular-nums'>
          全部失败
        </Badge>
      )}
    </div>
  )
}
