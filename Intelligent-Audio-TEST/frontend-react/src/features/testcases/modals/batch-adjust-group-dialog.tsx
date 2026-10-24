/**
 * 批量调整分组弹窗（11_用例域.md §5.3.6，Dialog sm:max-w-md；INT-997 真实数据接线）。
 * 目标分组 Select（现有分组 +「+ 新建分组」内联）+ 操作方式 RadioGroup「移动到目标分组/复制到目标分组」。
 * 提交走 POST /testcases/batch（move_to_group / copy_to_group）；「+ 新建分组」先 POST /groups 建组再执行。
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
import { Spinner } from '@/components/ui/spinner'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'
import { createGroup } from '@/infrastructure/api/groups-api'
import {
  batchTestcaseAction,
  type TestcaseBatchAction,
} from '@/infrastructure/api/testcases-batch-api'

export function BatchAdjustGroupDialog({
  open,
  onOpenChange,
  count,
  ids,
  groups,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  count: number
  ids: string[]
  groups: TestCaseGroup[]
}) {
  const [groupValue, setGroupValue] = useState('')
  const [newGroupName, setNewGroupName] = useState('')
  const [mode, setMode] = useState<'move' | 'copy'>('move')
  const [submitting, setSubmitting] = useState(false)

  // 声明式 items：闭合态从 items 取 label，否则 base-ui 回退显示原始分组 id（INT-1686）
  const groupItems = [
    ...groups.map((g) => ({ value: g.id, label: g.name })),
    { value: '__new__', label: '+ 新建分组' },
  ]

  const handleSubmit = async () => {
    if (!groupValue) return
    setSubmitting(true)
    try {
      // 「+ 新建分组」：先建组拿到目标分组 id，再走批量动作
      let targetGroupId = groupValue
      if (groupValue === '__new__') {
        const created = await createGroup({ name: newGroupName.trim() })
        targetGroupId = created.id
      }
      const action: TestcaseBatchAction =
        mode === 'move' ? 'move_to_group' : 'copy_to_group'
      await batchTestcaseAction(action, ids, { targetGroupId })
      toast.success(
        `批量操作执行成功（${mode === 'move' ? '移动' : '复制'} ${ids.length} 个用例）`
      )
      onOpenChange(false)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '批量调整分组失败')
    } finally {
      setSubmitting(false)
    }
  }

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
            <Select
              value={groupValue}
              onValueChange={(v) => setGroupValue(v ?? '')}
              items={groupItems}
            >
              <SelectTrigger size='sm' className='h-8 w-full'>
                <SelectValue placeholder='请选择分组' />
              </SelectTrigger>
              <SelectContent>
                {groupItems.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
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
          <Button variant='outline' onClick={() => onOpenChange(false)} disabled={submitting}>
            取消
          </Button>
          <Button
            disabled={
              submitting || !groupValue || (groupValue === '__new__' && !newGroupName.trim())
            }
            onClick={() => void handleSubmit()}
          >
            {submitting && <Spinner className='size-3.5' />}
            确定
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
