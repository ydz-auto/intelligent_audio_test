/**
 * 人工复核标记 Badge（19 规范 §3.5/§4.1，任务侧/报告侧共用件）。
 * 已复核结果/用例在执行·评估徽章旁叠加；secondary outline 形态 + Tooltip。
 * 用例行数据源为 TaskCaseBrief.reviewed（仅布尔标记，详见复核历史/复核弹窗）；
 * 结果行可传 detail（复核人 · 时间 · 改判对照，来自结果 last_review_* 字段）。
 */
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

export function ReviewBadge({
  detail,
  className,
}: {
  /** Tooltip 明细（复核人/时间/改判对照）；缺省给引导文案 */
  detail?: string | null
  className?: string
}) {
  return (
    <Tooltip>
      <TooltipTrigger render={<div />}>
        <Badge
          variant='secondary'
          className={cn('gap-1 rounded-md px-1.5 text-[11px]', className)}
          data-slot='review-badge'
        >
          <span aria-hidden='true' className='size-1.5 rounded-full bg-current' />
          人工复核
        </Badge>
      </TooltipTrigger>
      <TooltipContent>
        {detail || '该用例已存在人工复核结果，详见「复核历史」'}
      </TooltipContent>
    </Tooltip>
  )
}
