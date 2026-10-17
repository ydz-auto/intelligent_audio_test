/**
 * 批量声压面板（11_用例域.md §5.1 音频列表工具栏「批量声压」）。
 * 弹批量声压面板（number 40-100，默认 65），应用到当前轮次音频列表全部/勾选音频。
 */
import { useState } from 'react'

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
import { Label } from '@/components/ui/label'
import type { BatchScope } from '@/domain/lib/audio-batch-ops'

export function BatchSplPanel({
  open,
  onOpenChange,
  selectedCount,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 当前勾选音频数（0 时「勾选音频」项禁用） */
  selectedCount: number
  onConfirm: (spl: number, scope: BatchScope) => void
}) {
  const [spl, setSpl] = useState(65)
  const [scope, setScope] = useState<BatchScope>('all')

  /** 输入合法才可确认：40-100（与 input min/max 一致；越界/空输入时禁用确定） */
  const splValid = !Number.isNaN(Number(spl)) && Number(spl) >= 40 && Number(spl) <= 100

  const confirm = () => {
    const value = Number(spl)
    if (!splValid) return
    onConfirm(value, scope)
    setSpl(65)
    setScope('all')
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>批量设置声压级</DialogTitle>
          <DialogDescription>应用到当前轮次音频列表（全部或勾选）</DialogDescription>
        </DialogHeader>
        <div className='space-y-4'>
          <div className='space-y-1.5'>
            <Label htmlFor='batch-spl' className='text-sm'>
              声压级 dB
            </Label>
            <Input
              id='batch-spl'
              type='number'
              min={40}
              max={100}
              value={spl}
              onChange={(e) => setSpl(Number(e.target.value))}
              className='h-8 w-40'
            />
            <p className='text-muted-foreground text-xs'>范围 40-100，默认 65</p>
          </div>
          <div className='space-y-1.5'>
            <span className='text-sm font-medium'>应用范围</span>
            <div className='flex flex-wrap items-center gap-x-4 gap-y-1.5'>
              <label className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'>
                <input type='radio' name='batch-spl-scope' checked={scope === 'all'} onChange={() => setScope('all')} />
                全部音频
              </label>
              <label
                className={
                  selectedCount > 0
                    ? 'hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'
                    : 'text-muted-foreground flex cursor-not-allowed items-center gap-1.5 rounded-md px-2 py-1 text-sm'
                }
              >
                <input
                  type='radio'
                  name='batch-spl-scope'
                  checked={scope === 'selected'}
                  disabled={selectedCount === 0}
                  onChange={() => setScope('selected')}
                />
                勾选音频（{selectedCount} 个）
              </label>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button disabled={!splValid} onClick={confirm}>
            确定
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
