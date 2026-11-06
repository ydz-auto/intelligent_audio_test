/**
 * 容器溯源展开行（18_挑选合并功能交互重设计.md §2.2/§2.3/§5.5.2 ⑤/§5.5.3 ③，INT-600 / INT-1716）。
 * 按合并方式自适应：
 * - **整任务合并**（`merge_type='whole'`）：保持原源任务列表形态 —— `source` 端点只查
 *   `task_cherry_pick_relations`，解析不到整任务合并容器，本分支不动（§5.5.2 ⑤）；
 * - **结果挑选**（`picked`）：换 `ContainerTraceExpand` 四视图组成树（落点 ③），
 *   首次展开只补 1 次容器详情查询。
 */
import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'

import type { CherryPickContainer } from '@/domain/models/cherryPick'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { ContainerTraceExpand } from '@/features/tasks/cherry-pick/components/container-trace-expand'
import { formatPickDateTime } from '@/features/tasks/cherry-pick/constants'

/** 行内溯源展开（renderRow expandable，§2.3） */
export function SourceTraceRow({ container }: { container: CherryPickContainer }) {
  // 结果挑选容器 → 组成四视图（§5.5.3 ③）
  if (container.mergeType !== 'whole') {
    return <ContainerTraceExpand container={container} />
  }
  return <WholeMergeSourceList container={container} />
}

/** 整任务合并容器：源任务列表（原形态，无逐结果引用，保持不动） */
function WholeMergeSourceList({ container }: { container: CherryPickContainer }) {
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
          ? `收起源任务列表（${container.sourceTaskCount} 个）`
          : `展开源任务列表（${container.sourceTaskCount} 个）`}
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
                <span className='text-muted-foreground text-[11px]'>
                  {formatPickDateTime(container.createdAt)}
                </span>
              </li>
            ))}
          </ul>
        ))}
    </div>
  )
}
