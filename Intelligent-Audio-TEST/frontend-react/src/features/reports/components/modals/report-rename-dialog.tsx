/**
 * 报告重命名 / 描述编辑 Dialog（规范 §5.5，report:update）：
 * 名称*（Input）+ 描述（Textarea）→ PUT /reports/{id}（name/description）。
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
import type { ReportListItem } from '@/domain/models/report'

/** 重命名只需 id/name/description——列表项与详情快照（ReportDetailData）均可传入 */
type RenameTarget = Pick<ReportListItem, 'id' | 'name' | 'description'>

interface ReportRenameDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  report?: RenameTarget
  onConfirm: (report: RenameTarget, payload: { name: string; description?: string }) => void
}

export function ReportRenameDialog({
  open,
  onOpenChange,
  report,
  onConfirm,
}: ReportRenameDialogProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleOpenChange = (next: boolean) => {
    if (next && report) {
      setName(report.name)
      setDescription(report.description ?? '')
    }
    onOpenChange(next)
  }

  const handleSubmit = async () => {
    if (!report || !name.trim()) return
    setSubmitting(true)
    try {
      onConfirm(report, { name: name.trim(), description: description.trim() || undefined })
    } finally {
      setSubmitting(false)
      onOpenChange(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>编辑报告</DialogTitle>
          <DialogDescription>修改报告名称与描述，保存后写回该报告。</DialogDescription>
        </DialogHeader>
        <div className='space-y-4'>
          <div className='space-y-2'>
            <Label htmlFor='rename-name'>
              名称<span className='text-destructive'>*</span>
            </Label>
            <Input
              id='rename-name'
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className='space-y-2'>
            <Label htmlFor='rename-desc'>描述</Label>
            <Textarea
              id='rename-desc'
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder='选填，报告内容说明'
              className='min-h-24'
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button disabled={!name.trim() || submitting} onClick={() => void handleSubmit()}>
            {submitting ? '保存中...' : '保存'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
