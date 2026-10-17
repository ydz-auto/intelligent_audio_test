/**
 * 挑选集管理 Popover（18_挑选合并交互重设计.md §6.1/§7.1，INT-600）。
 * 管理挑选集：恢复进购物车/删除；数据源 usePickSets（单例镜像）。
 */
import { useState } from 'react'
import { toast } from 'sonner'

import { usePickSets } from '@/application/tasks/cherry-pick/use-pick-sets'
import { Button } from '@/components/ui/button'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { formatPickDateTime } from '@/features/tasks/cherry-pick/constants'

export function PickSetPopover() {
  const { pickSets, restorePickSet, deletePickSet } = usePickSets()
  const [open, setOpen] = useState(false)

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button variant='ghost' size='sm' className='h-8 gap-1.5 px-2.5' />
        }
      >
        管理挑选集
      </PopoverTrigger>
      <PopoverContent align='end' className='min-w-64 p-1.5'>
        {pickSets.length === 0 ? (
          <p className='text-muted-foreground px-3 py-4 text-center text-sm'>
            暂无挑选集
          </p>
        ) : (
          pickSets.map((set) => (
            <div
              key={set.setId}
              className='hover:bg-accent flex items-center gap-2 rounded-md px-2 py-1.5'
            >
              <div className='min-w-0 flex-1'>
                <p className='truncate text-sm font-medium'>{set.name}</p>
                <p className='text-muted-foreground text-xs tabular-nums'>
                  {set.itemCount} 条 · {formatPickDateTime(set.createdAt)}
                </p>
              </div>
              <Button
                variant='ghost'
                size='xs'
                className='h-6 px-2 text-xs'
                onClick={async () => {
                  const restored = await restorePickSet(set.setId)
                  toast.success(
                    restored > 0
                      ? `已恢复 ${restored} 条进购物车`
                      : '挑选集条目已在购物车中'
                  )
                }}
              >
                恢复
              </Button>
              <Button
                variant='ghost'
                size='xs'
                className='text-destructive hover:text-destructive h-6 px-2 text-xs'
                onClick={async () => {
                  await deletePickSet(set.setId)
                  toast.success('挑选集已删除')
                }}
              >
                删除
              </Button>
            </div>
          ))
        )}
      </PopoverContent>
    </Popover>
  )
}
