/**
 * 容器溯源展开行（18_挑选合并交互重设计.md §2.2/§7.1，INT-600）。
 * 按合并方式自适应：整任务合并=源任务列表；结果挑选=源任务→结果（§2.2 裁定③）。
 */
import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'

import type { CherryPickContainer } from '@/domain/models/cherryPick'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { formatPickDateTime } from '@/features/tasks/cherry-pick/constants'

/** 行内溯源展开（renderRow expandable，§2.3） */
export function SourceTraceRow({ container }: { container: CherryPickContainer }) {
  const [open, setOpen] = useState(false)

  return (
    <div className='px-3 py-1'>
      <Button
        variant='ghost'
        size='sm'
        className='text-muted-foreground h-7 gap-1 px-1 text-xs'
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        {open ? (
          <ChevronDown aria-hidden='true' className='size-3.5' />
        ) : (
          <ChevronRight aria-hidden='true' className='size-3.5' />
        )}
        {open
          ? container.mergeType === 'whole'
            ? `收起源任务列表（${container.sourceTaskCount} 个）`
            : `收起源结果溯源（${container.sourceResultCount} 条）`
          : container.mergeType === 'whole'
            ? `展开源任务列表（${container.sourceTaskCount} 个）`
            : `展开源结果溯源（${container.sourceResultCount} 条）`}
      </Button>

      {open &&
        (container.sourceTasks.length === 0 ? (
          <p className='text-muted-foreground px-2 py-1 text-xs'>
            该合并任务暂无来源记录
          </p>
        ) : (
          <ul className='mt-1 flex flex-col gap-1'>
            {container.sourceTasks.map((src) => (
              <li
                key={src.id}
                className='hover:bg-muted/40 flex items-center gap-2 rounded-md px-2 py-1 text-xs'
              >
                <span className='min-w-0 flex-1 truncate font-medium'>
                  #{src.id} {src.name}
                </span>
                <Badge variant='secondary' className='font-mono text-[10px]'>
                  {src.resultCount} 条
                </Badge>
                <StatusBadge
                  label={src.status === 'completed' ? '已完成' : '已停止'}
                  variant={src.status === 'completed' ? 'success' : 'neutral'}
                />
                {container.mergeType === 'whole' && (
                  <span className='text-muted-foreground text-[11px]'>
                    {formatPickDateTime(container.createdAt)}
                  </span>
                )}
              </li>
            ))}
          </ul>
        ))}
    </div>
  )
}

