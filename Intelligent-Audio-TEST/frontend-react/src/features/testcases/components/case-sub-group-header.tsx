/**
 * 子分组头（11_用例域.md §3.5/§3.6/§3.9，只读组织行，不挂任何操作入口）。
 * 按标签子组：标签色点（数据驱动色）+ 标签名 + 分类名角标 + 计数 Badge + 子组总时长徽章；
 * 按用例分组子组：分组名 + 计数 Badge + 子组总时长徽章；
 * 「未设置标签」/「未分组」桶 muted 底弱化（末尾）。
 */
import { Clock3 } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { CaseSubGroup } from '@/domain/lib/sub-view-aggregation'
import { formatCaseDuration } from '@/features/testcases/constants'

export function CaseSubGroupHeader({
  group,
  muted = false,
}: {
  group: CaseSubGroup
  /** 未设置标签/未分组桶：弱化（末尾） */
  muted?: boolean
}) {
  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-2 px-1 py-1.5',
        muted && 'bg-muted/40 rounded-md px-2'
      )}
    >
      {group.color && (
        <span
          aria-hidden='true'
          className='size-2 shrink-0 rounded-full'
          style={{ backgroundColor: group.color }}
        />
      )}
      <span className={cn('text-sm font-medium', muted && 'text-muted-foreground')}>
        {group.label}
      </span>
      {group.categoryName && (
        <span className='text-muted-foreground text-xs'>{group.categoryName}</span>
      )}
      <Badge
        variant='secondary'
        className='rounded-md px-1.5 font-mono text-[11px] tabular-nums'
      >
        {group.cases.length} 条
      </Badge>
      {group.totalDuration > 0 && (
        <Badge
          variant='outline'
          className='gap-1 rounded-md px-1.5 font-mono text-[11px] tabular-nums'
        >
          <Clock3 aria-hidden='true' className='size-3' />
          总时长 {formatCaseDuration(group.totalDuration)}
        </Badge>
      )}
    </div>
  )
}
