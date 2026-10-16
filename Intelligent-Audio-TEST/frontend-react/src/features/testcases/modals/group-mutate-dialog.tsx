/**
 * 新建/编辑分组弹窗（11_用例域.md §5.7.4，Dialog sm:max-w-md）。
 * 字段照 group.py GroupCreate/UpdateRequest 逐字：分组名称 / 描述 / 算法类型
 * （TestCaseGroup 模型含 description/algorithm_type，卡片方案旧表单补齐项）。
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
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { MOCK_ALGORITHMS } from '@/domain/models/algorithm'
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'

export function GroupMutateDialog({
  open,
  onOpenChange,
  group,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  group: TestCaseGroup | null
}) {
  const isEdit = group != null
  const [name, setName] = useState(group?.name ?? '')

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>{isEdit ? '编辑分组' : '新建分组'}</DialogTitle>
          <DialogDescription>分组用于用例的组织与批量调整</DialogDescription>
        </DialogHeader>
        <div className='space-y-4'>
          <div className='space-y-1.5'>
            <Label htmlFor='group-name'>分组名称 *</Label>
            <Input
              id='group-name'
              value={name}
              maxLength={50}
              onChange={(e) => setName(e.target.value)}
              placeholder='请输入分组名称'
              className='h-8'
            />
            <p className='text-muted-foreground text-xs tabular-nums'>{name.length}/50</p>
          </div>
          <div className='space-y-1.5'>
            <Label htmlFor='group-desc'>描述</Label>
            <Textarea
              id='group-desc'
              rows={2}
              defaultValue={group?.description ?? ''}
              placeholder='补充分组描述（可选）'
            />
          </div>
          <div className='space-y-1.5'>
            <Label>算法类型</Label>
            <Select defaultValue={group?.algorithmType ?? ''}>
              <SelectTrigger size='sm' className='h-8 w-full'>
                <SelectValue placeholder='全部算法' />
              </SelectTrigger>
              <SelectContent>
                {MOCK_ALGORITHMS.map((a) => (
                  <SelectItem key={a.id} value={a.id}>
                    {a.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            disabled={!name.trim()}
            onClick={() => {
              toast.success(isEdit ? '更新分组成功' : '添加分组成功')
              onOpenChange(false)
            }}
          >
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
