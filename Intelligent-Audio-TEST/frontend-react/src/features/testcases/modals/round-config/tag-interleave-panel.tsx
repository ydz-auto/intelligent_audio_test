/**
 * 标签交错面板（11_用例域.md §5.1 音频列表工具栏「标签交错」）。
 * ≥2 标签 chip 选择面板：点选标签切换选中态，确认后音频列表按所选标签交错排序
 * （同一多标签音频在每个命中的标签段各现一次，对齐 §3.6 多标签语义）。
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

export function TagInterleavePanel({
  open,
  onOpenChange,
  tags,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 可选标签源（mock 标签源 MOCK_TAGS） */
  tags: string[]
  onConfirm: (selectedTags: string[]) => void
}) {
  const [selected, setSelected] = useState<string[]>([])

  const toggle = (tag: string) =>
    setSelected((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    )

  const confirm = () => {
    if (selected.length < 2) return
    onConfirm(selected)
    setSelected([])
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>标签交错</DialogTitle>
          <DialogDescription>
            选择 ≥2 个标签，音频列表将按所选标签交错排序（多标签音频在各标签段各现一次）
          </DialogDescription>
        </DialogHeader>
        <div className='flex flex-wrap gap-1.5'>
          {tags.map((tag) => {
            const active = selected.includes(tag)
            return (
              <button
                key={tag}
                type='button'
                aria-pressed={active}
                onClick={() => toggle(tag)}
                className={
                  active
                    ? 'bg-primary text-primary-foreground rounded-md px-2 py-1 text-sm transition-colors'
                    : 'hover:bg-accent rounded-md border px-2 py-1 text-sm transition-colors'
                }
              >
                {tag}
              </button>
            )
          })}
        </div>
        <p className='text-muted-foreground text-xs'>
          已选 {selected.length} 个标签
          {selected.length < 2 && '（至少选择 2 个）'}
        </p>
        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button disabled={selected.length < 2} onClick={confirm}>
            确定
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
