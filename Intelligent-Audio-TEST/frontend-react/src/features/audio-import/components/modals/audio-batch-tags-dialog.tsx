/**
 * 批量设置标签弹窗（§5.6；audio:update → batch-action tags，小 Dialog 输入标签）。
 * 输入逗号分隔标签 → 应用到全部选中音频。
 */
import { Tags } from 'lucide-react'
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
import { useAudioMutations } from '@/application/audio/useAudioList'

export type AudioBatchTagsDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  count: number
  /** 已选中的音频 id（批量浮条「批量设置标签」触发时传入） */
  ids: number[]
}

export function AudioBatchTagsDialog(props: AudioBatchTagsDialogProps) {
  const { batch } = useAudioMutations()
  const [tagsText, setTagsText] = useState('')
  const [pending, setPending] = useState(false)

  const handleConfirm = async () => {
    if (!tagsText.trim()) {
      toast.info('请输入需要设置的标签')
      return
    }
    setPending(true)
    try {
      const result = await batch.mutateAsync({ action: 'tags', ids: props.ids })
      toast.success(
        `已为 ${result.successCount} 个音频设置标签：${tagsText
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean)
          .join('、')}`
      )
      setTagsText('')
      props.onOpenChange(false)
    } catch {
      toast.error('批量设置标签失败，请重试')
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog
      open={props.open}
      onOpenChange={(open) => {
        props.onOpenChange(open)
        if (!open) setPending(false)
      }}
    >
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>批量设置标签</DialogTitle>
          <DialogDescription>为选中的 {props.count} 个音频批量设置标签</DialogDescription>
        </DialogHeader>

        <div className='space-y-2'>
          <Label htmlFor='batch-tags-input'>标签</Label>
          <Input
            id='batch-tags-input'
            value={tagsText}
            onChange={(e) => setTagsText(e.target.value)}
            placeholder='逗号分隔，如 客厅, 中文'
          />
          <p className='text-muted-foreground text-xs'>设置后将替换音频原有标签</p>
        </div>

        <DialogFooter>
          <Button variant='outline' size='sm' onClick={() => props.onOpenChange(false)}>
            取消
          </Button>
          <Button size='sm' onClick={handleConfirm} disabled={pending}>
            <Tags aria-hidden='true' className='size-3.5' />
            确认设置
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
