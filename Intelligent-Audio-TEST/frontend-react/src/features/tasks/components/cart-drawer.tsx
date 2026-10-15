/**
 * 购物车 Drawer（09_任务域.md §5.14b，右侧 Sheet sm:max-w-md）。
 * 按来源任务分组（组头「{任务名} · {n} 条」+ 移除整组）；条目行=用例名+设备+状态+移除 X。
 * 底部：清空购物车（ghost destructive）｜另存为挑选集（Dialog 命名）｜主钮「去下单」。
 * 文案红线：站内一律「挑选合并/挑选/加入购物车/购物车/下单/挑选集」。
 */
import { Save, Trash2, X } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { useCartStore } from '@/application/tasks/use-cart-store'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import {
  Sheet,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'

export function CartDrawer({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { entries, removeEntry, removeGroup, clearCart, saveAsPickSet } =
    useCartStore()
  const [saveOpen, setSaveOpen] = useState(false)
  const [setName, setSetName] = useState('')

  const groups = entries.reduce<Record<number, typeof entries>>((acc, entry) => {
    acc[entry.sourceTaskId] ??= []
    acc[entry.sourceTaskId].push(entry)
    return acc
  }, {})

  const checkout = () => {
    clearCart()
    onOpenChange(false)
    toast.success('挑选合并任务已创建')
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side='right' className='w-3/4 sm:max-w-md'>
        <SheetHeader>
          <SheetTitle>购物车</SheetTitle>
        </SheetHeader>

        <div className='min-h-0 flex-1 overflow-y-auto px-4'>
          {entries.length === 0 ? (
            <div className='flex flex-col items-center gap-2 py-12 text-center'>
              <Trash2 aria-hidden='true' className='text-muted-foreground size-8' />
              <p className='text-muted-foreground text-sm'>购物车为空</p>
              <p className='text-muted-foreground/70 text-xs'>
                从任务详情或报告结果列表勾选执行结果「加入购物车」
              </p>
            </div>
          ) : (
            Object.entries(groups).map(([taskId, group]) => (
              <section key={taskId} className='mb-4'>
                <div className='mb-1.5 flex items-center justify-between gap-2'>
                  <h4 className='min-w-0 flex-1 truncate text-sm font-medium'>
                    {group[0].sourceTaskName} · {group.length} 条
                  </h4>
                  <Button
                    variant='ghost'
                    size='xs'
                    className='text-muted-foreground h-6 px-2 text-xs'
                    onClick={() => removeGroup(Number(taskId))}
                  >
                    移除整组
                  </Button>
                </div>
                <div className='flex flex-col gap-1.5'>
                  {group.map((entry) => (
                    <div
                      key={entry.id}
                      className='hover:bg-muted/50 flex items-center gap-2 rounded-lg border px-2.5 py-2 text-xs transition-colors'
                    >
                      <div className='min-w-0 flex-1'>
                        <p className='truncate font-medium'>{entry.caseName}</p>
                        <p className='text-muted-foreground truncate'>{entry.deviceName}</p>
                      </div>
                      <StatusBadge
                        label={entry.executionStatus === 'completed' ? '已完成' : '执行失败'}
                        variant={entry.executionStatus === 'completed' ? 'success' : 'danger'}
                      />
                      <Button
                        variant='ghost'
                        size='icon-xs'
                        aria-label='移除'
                        onClick={() => removeEntry(entry.id)}
                      >
                        <X aria-hidden='true' />
                      </Button>
                    </div>
                  ))}
                </div>
              </section>
            ))
          )}
        </div>

        <SheetFooter>
          <div className='flex flex-wrap items-center gap-2'>
            <Button
              variant='ghost'
              size='sm'
              className='text-destructive hover:text-destructive gap-1.5'
              disabled={entries.length === 0}
              onClick={() => clearCart()}
            >
              <Trash2 aria-hidden='true' className='size-3.5' />
              清空购物车
            </Button>
            <Button
              variant='outline'
              size='sm'
              className='gap-1.5'
              disabled={entries.length === 0}
              onClick={() => {
                setSetName('')
                setSaveOpen(true)
              }}
            >
              <Save aria-hidden='true' className='size-3.5' />
              另存为挑选集
            </Button>
          </div>
          <Separator />
          <Button
            className='w-full'
            disabled={entries.length === 0}
            onClick={checkout}
          >
            去下单
          </Button>
        </SheetFooter>
      </SheetContent>

      <Dialog open={saveOpen} onOpenChange={setSaveOpen}>
        <DialogContent className='sm:max-w-sm'>
          <DialogHeader>
            <DialogTitle>另存为挑选集</DialogTitle>
            <DialogDescription>
              为当前购物车内容命名，之后可从「管理挑选集」恢复进购物车
            </DialogDescription>
          </DialogHeader>
          <Input
            value={setName}
            onChange={(e) => setSetName(e.target.value)}
            placeholder='挑选集名称（例如：远场高置信度候选集）'
            maxLength={40}
          />
          <DialogFooter>
            <Button variant='outline' onClick={() => setSaveOpen(false)}>
              取消
            </Button>
            <Button
              disabled={!setName.trim()}
              onClick={() => {
                saveAsPickSet(setName.trim())
                setSaveOpen(false)
                toast.success('挑选集已保存')
              }}
            >
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Sheet>
  )
}
