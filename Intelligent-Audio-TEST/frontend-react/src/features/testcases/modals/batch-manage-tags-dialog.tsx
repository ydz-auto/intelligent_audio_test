/**
 * 批量管理标签弹窗（11_用例域.md §5.3.7，Dialog sm:max-w-lg；INT-997 真实数据接线）。
 * 操作类型 RadioGroup「添加标签/移除标签/修改标签名字」：添加/移除→标签 TagInput + 已有标签点选区；
 * 改名→原标签 Select + 新标签名 Input。提交走 POST /testcases/batch
 * （add_tags / remove_tags / rename_tag），rename_tag 不携带 ids（标签级操作）。
 */
import { useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import type { TagItem } from '@/domain/models/testTag'
import {
  batchTestcaseAction,
  type TestcaseBatchAction,
} from '@/infrastructure/api/testcases-batch-api'

type BatchTagMode = 'add' | 'remove' | 'rename'

export function BatchManageTagsDialog({
  open,
  onOpenChange,
  count,
  ids,
  tags,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  count: number
  ids: string[]
  tags: TagItem[]
}) {
  const [mode, setMode] = useState<BatchTagMode>('add')
  const [chips, setChips] = useState<string[]>([])
  const [draft, setDraft] = useState('')
  const [renameFrom, setRenameFrom] = useState('')
  const [renameTo, setRenameTo] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const addChip = (name: string) => {
    const trimmed = name.trim()
    if (!trimmed || chips.includes(trimmed)) return
    setChips((prev) => [...prev, trimmed])
  }

  const handleSubmit = async () => {
    setSubmitting(true)
    try {
      let action: TestcaseBatchAction
      let payload: Parameters<typeof batchTestcaseAction>[2]
      if (mode === 'rename') {
        if (!renameFrom || !renameTo.trim()) return
        action = 'rename_tag'
        payload = { oldTagName: renameFrom, newTagName: renameTo.trim() }
      } else {
        if (chips.length === 0) return
        action = mode === 'add' ? 'add_tags' : 'remove_tags'
        payload = { tags: chips }
      }
      // rename_tag 为标签级操作（ids 空数组，Vue 基准）；add/remove 按选中用例 ids
      await batchTestcaseAction(action, mode === 'rename' ? [] : ids, payload)
      toast.success(
        `批量操作执行成功（${mode === 'rename' ? '改名' : mode === 'add' ? '添加' : '移除'}标签）`
      )
      onOpenChange(false)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '批量管理标签失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>批量管理标签</DialogTitle>
          <DialogDescription>您勾选了 {count} 个用例，将统一管理其标签</DialogDescription>
        </DialogHeader>
        <div className='space-y-4'>
          <div className='flex flex-wrap items-center gap-x-4 gap-y-1.5'>
            <label className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'>
              <input type='radio' name='batch-tag-mode' checked={mode === 'add'} onChange={() => setMode('add')} />
              添加标签
            </label>
            <label className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'>
              <input type='radio' name='batch-tag-mode' checked={mode === 'remove'} onChange={() => setMode('remove')} />
              移除标签
            </label>
            <label className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'>
              <input type='radio' name='batch-tag-mode' checked={mode === 'rename'} onChange={() => setMode('rename')} />
              修改标签名字
            </label>
          </div>

          {mode === 'rename' ? (
            <div className='grid gap-3 sm:grid-cols-2'>
              <div className='space-y-1.5'>
                <span className='text-sm font-medium'>原标签</span>
                <Select value={renameFrom} onValueChange={(v) => setRenameFrom(v ?? '')}>
                  <SelectTrigger size='sm' className='h-8 w-full'>
                    <SelectValue placeholder='请选择标签' />
                  </SelectTrigger>
                  <SelectContent>
                    {tags.map((t) => (
                      <SelectItem key={t.id} value={t.name}>
                        {t.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className='space-y-1.5'>
                <span className='text-sm font-medium'>新标签名</span>
                <Input
                  value={renameTo}
                  onChange={(e) => setRenameTo(e.target.value)}
                  placeholder='输入新标签名称'
                  className='h-8'
                />
              </div>
            </div>
          ) : (
            <div className='space-y-2'>
              <div className='flex flex-wrap items-center gap-1.5 rounded-lg border p-2'>
                {chips.map((name) => (
                  <Badge key={name} variant='secondary' className='gap-1 rounded-md px-1.5'>
                    {name}
                    <button
                      type='button'
                      aria-label={`移除 ${name}`}
                      className='text-muted-foreground hover:text-destructive'
                      onClick={() => setChips((prev) => prev.filter((v) => v !== name))}
                    >
                      ✕
                    </button>
                  </Badge>
                ))}
                <Input
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ',') {
                      e.preventDefault()
                      addChip(draft)
                      setDraft('')
                    }
                  }}
                  placeholder='输入标签，按回车或逗号添加'
                  className='h-7 w-full min-w-40 border-none shadow-none focus-visible:ring-0 sm:w-56'
                />
              </div>
              <div className='flex flex-wrap gap-1.5'>
                {tags.slice(0, 10).map((tag) => (
                  <button
                    key={tag.id}
                    type='button'
                    className='hover:bg-accent flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs transition-colors'
                    onClick={() => addChip(tag.name)}
                  >
                    <span
                      aria-hidden='true'
                      className='size-1.5 rounded-full'
                      style={{ backgroundColor: tag.color ?? '#94a3b8' }}
                    />
                    {tag.name}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)} disabled={submitting}>
            取消
          </Button>
          <Button
            disabled={
              submitting ||
              (mode === 'rename'
                ? !renameFrom || !renameTo.trim()
                : chips.length === 0)
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
