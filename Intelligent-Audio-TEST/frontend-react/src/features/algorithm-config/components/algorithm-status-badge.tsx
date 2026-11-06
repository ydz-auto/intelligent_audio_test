/**
 * 算法状态徽章（features/algorithm-config；§8 status-badge 口径）。
 * online=success「上线」/ offline=neutral「下线」，dot 色 + 中文文案。
 */
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { ALGORITHM_STATUS_META } from '@/features/algorithm-config/constants'
import type { AlgorithmStatus } from '@/domain/models/algorithmConfig'

const DOT_STYLE: Record<'success' | 'neutral', string> = {
  success: 'bg-[var(--success)]',
  neutral: 'bg-[var(--muted-foreground)]',
}

export function AlgorithmStatusBadge({
  status,
  className,
}: {
  status: AlgorithmStatus
  className?: string
}) {
  const meta = ALGORITHM_STATUS_META[status]
  const dot = DOT_STYLE[meta.badgeVariant]
  return (
    <Badge
      variant='outline'
      className={cn('gap-1.5 px-2 font-normal', className)}
    >
      <span
        aria-hidden='true'
        className={cn('size-1.5 rounded-full', dot)}
      />
      {meta.label}
    </Badge>
  )
}
