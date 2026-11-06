/**
 * 报告头复核统计徽章（19 规范 §4.1，INT-793）：review_count > 0 时显示「已复核 {n} 条」，
 * secondary outline，点击锚点到具体用例分区。数据源 = 报告源任务 review_count（INT-734 实测回填；
 * 报告为落库快照，报告快照复核明细待后端立项（§8-1）→ 以源任务实时计数驱动复核交互）。
 */
import { ShieldCheck } from 'lucide-react'

import { Badge } from '@/components/ui/badge'

interface ReviewStatsBadgeProps {
  count: number
  onClick?: () => void
}

export function ReviewStatsBadge({ count, onClick }: ReviewStatsBadgeProps) {
  if (count <= 0) return null
  const inner = (
    <Badge
      variant='secondary'
      className='cursor-pointer gap-1 transition-opacity hover:opacity-80'
      onClick={onClick}
    >
      <ShieldCheck aria-hidden='true' className='size-3.5' />
      已复核 {count} 条
    </Badge>
  )
  return inner
}
