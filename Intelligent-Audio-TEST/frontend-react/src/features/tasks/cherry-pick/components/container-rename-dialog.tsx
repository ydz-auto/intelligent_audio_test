/**
 * 挑选合并容器重命名 Dialog（18_挑选合并交互重设计.md §2.2/§7.5，INT-1277）：
 * 名称*（Input）+ 描述（Textarea）→ PUT /tasks/{id}（name/description，task:update）。
 * 对齐报告重命名弹窗（report-rename-dialog.tsx）交互形态。
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
import { Textarea } from '@/components/ui/textarea'
import type { CherryPickContainer } from '@/domain/models/cherryPick'

interface ContainerRenameDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  container: CherryPickContainer
  onConfirm: (payload: { name: string; description?: string }) => void
}

export function ContainerRenameDialog({
  open,
  onOpenChange,
  container,
  onConfirm,
}: ContainerRenameDialogProps) {
  const [name, setName] = useState(container.name)
  const [description, setDescription] = useState(container.description ?? '')

  const handleOpenChange = (next: boolean) => {
    if (next) {
      setName(container.name)
      setDescription(container.description ?? '')
    }
    onOpenChange(next)
  }

  const handleSubmit = () => {
    if (!name.trim()) return
    onConfirm({ name: name.trim(), description: description.trim() || undefined })
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>重命名容器</DialogTitle>
          <DialogDescription>修改挑选合并容器名称与描述，保存后写回该任务。</DialogDescription>
        </DialogHeader>
        <div className='space-y-4'>
          <div className='space-y-2'>
            <Label htmlFor='container-rename-name'>
              名称<span className='text-destructive'>*</span>
            </Label>
            <Input
              id='container-rename-name'
              value={name}
              maxLength={255}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className='space-y-2'>
            <Label htmlFor='container-rename-desc'>描述</Label>
            <Textarea
              id='container-rename-desc'
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder='选填，容器说明'
              className='min-h-24'
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button disabled={!name.trim()} onClick={handleSubmit}>
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
