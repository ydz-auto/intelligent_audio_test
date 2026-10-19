/**
 * 「人工复核」Badge（19 规范 §3.5/§4.1，INT-793）。
 * 已复核结果在执行/评估状态徽章旁叠加；报告用例卡片头行叠加。
 * Tooltip：{复核人} · {复核时间} · 改判：执行 {原值}→{新值} / 评估 {原值}→{新值}（有明细时）。
 */
import { ShieldCheck } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'

interface ReviewBadgeProps {
  /** 计数（该用例已复核结果数；报告快照复核明细未落地时显示「含复核」无计数） */
  count?: number
  tooltip?: string
  className?: string
}

export function ReviewBadge({ count, tooltip, className }: ReviewBadgeProps) {
  const label = count !== undefined && count > 0 ? `已复核 ${count}` : '含复核'
  const badge = (
    <Badge variant='secondary' className={`gap-1 ${className ?? ''}`}>
      <ShieldCheck aria-hidden='true' className='size-3' />
      {label}
    </Badge>
  )

  if (!tooltip) return badge

  return (
    <Tooltip>
      <TooltipTrigger render={badge} />
      <TooltipContent>{tooltip}</TooltipContent>
    </Tooltip>
  )
}
