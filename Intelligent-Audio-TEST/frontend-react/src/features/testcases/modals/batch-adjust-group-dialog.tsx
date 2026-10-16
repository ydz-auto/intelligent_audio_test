/**
 * 批量调整分组弹窗（11_用例域.md §5.3.6，Dialog sm:max-w-md）。
 * 目标分组 Select（现有分组 +「+ 新建分组」内联）+ 操作方式 RadioGroup「移动到目标分组/复制到目标分组」。
 */
import { useState } from 'react'
import { toast } from 'sonner'

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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'

export function BatchAdjustGroupDialog({
  open,
  onOpenChange,
  count,
  groups,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  count: number
  groups: TestCaseGroup[]
}) {
  const [groupValue, setGroupValue] = useState('')
  const [newGroupName, setNewGroupName] = useState('')
  const [mode, setMode] = useState<'move' | 'copy'>('move')

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>批量调整分组</DialogTitle>
          <DialogDescription>您勾选了 {count} 个用例，将调整其所属分组</DialogDescription>
        </DialogHeader>
        <div className='space-y-4'>
          <div className='space-y-1.5'>
            <span className='text-sm font-medium'>目标分组</span>
            <Select value={groupValue} onValueChange={(v) => setGroupValue(v ?? '')}>
              <SelectTrigger size='sm' className='h-8 w-full'>
                <SelectValue placeholder='请选择分组' />
              </SelectTrigger>
              <SelectContent>
                {groups.map((g) => (
                  <SelectItem key={g.id} value={g.id}>
                    {g.name}
                  </SelectItem>
                ))}
                <SelectItem value='__new__'>+ 新建分组</SelectItem>
              </SelectContent>
            </Select>
            {groupValue === '__new__' && (
              <Input
                value={newGroupName}
                onChange={(e) => setNewGroupName(e.target.value)}
                placeholder='输入新分组名称'
                className='mt-1.5 h-8'
                aria-label='新分组名称'
              />
            )}
          </div>
          <div className='flex flex-wrap items-center gap-x-4 gap-y-1.5'>
            <label className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'>
              <input
                type='radio'
                name='batch-group-mode'
                checked={mode === 'move'}
                onChange={() => setMode('move')}
              />
              移动到目标分组
            </label>
            <label className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'>
              <input
                type='radio'
                name='batch-group-mode'
                checked={mode === 'copy'}
                onChange={() => setMode('copy')}
              />
              复制到目标分组
            </label>
          </div>
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            disabled={!groupValue || (groupValue === '__new__' && !newGroupName.trim())}
            onClick={() => {
              toast.success(`批量操作执行成功（${mode === 'move' ? '移动' : '复制'} ${count} 个用例）`)
              onOpenChange(false)
            }}
          >
            确定
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
