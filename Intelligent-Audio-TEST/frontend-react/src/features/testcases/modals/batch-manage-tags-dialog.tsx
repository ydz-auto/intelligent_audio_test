/**
 * 批量管理标签弹窗（11_用例域.md §5.3.7，Dialog sm:max-w-lg；INT-997 真实数据接线）。
 * 操作类型 RadioGroup「添加标签/移除标签/修改标签名字」：添加/移除→标签 TagInput + 已有标签点选区；
 * 改名→原标签 Select + 新标签名 Input。提交走 POST /testcases/batch
 * （add_tags / remove_tags / rename_tag），rename_tag 不携带 ids（标签级操作）。
 * INT-1295：已有标签点选区照现 Vue availableSuggestions（排除已选 chips）。
 * INT-2102：点选区改按分类分组展示（数据源 GET /tags/by-category；组头=分类名＋组内标签＋
 * 「未分类」尾组），替代原平铺 20 条/页分页；选中/提交契约不变，改名模式 Select 不受影响。
 * INT-1591：改名模式新旧同名时「确定」禁用（V9.7.10 BatchTagsModal isValid 口径），不发请求。
 */
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
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
import { fetchTagsByCategory } from '@/infrastructure/api/tags-api'

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

  /** 已有标签点选区数据源：GET /tags/by-category（分类分组，INT-2102；弹窗打开才取数） */
  const byCategoryQuery = useQuery({
    queryKey: ['tags', 'by-category'],
    queryFn: fetchTagsByCategory,
    staleTime: 30_000,
    enabled: open,
  })

  /**
   * 点选区分组 = by-category 分组排除已选 chips（Vue availableSuggestions 口径）；
   * 空组不渲染（组内标签全部点选后组消失），「未分类」为尾组。
   */
  const groupedTags = useMemo(
    () =>
      (byCategoryQuery.data ?? [])
        .map((g) => ({
          category: g.category,
          tags: g.tags.filter((t) => !chips.includes(t.name)),
        }))
        .filter((g) => g.tags.length > 0),
    [byCategoryQuery.data, chips]
  )

  const changeMode = (next: BatchTagMode) => {
    setMode(next)
  }

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
        // INT-1591：新旧同名属无效输入（V9.7.10 BatchTagsModal isValid 口径），不发请求
        const nextName = renameTo.trim()
        if (!renameFrom || !nextName || nextName === renameFrom) return
        action = 'rename_tag'
        payload = { oldTagName: renameFrom, newTagName: nextName }
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
              <input type='radio' name='batch-tag-mode' checked={mode === 'add'} onChange={() => changeMode('add')} />
              添加标签
            </label>
            <label className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'>
              <input type='radio' name='batch-tag-mode' checked={mode === 'remove'} onChange={() => changeMode('remove')} />
              移除标签
            </label>
            <label className='hover:bg-accent flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm'>
              <input type='radio' name='batch-tag-mode' checked={mode === 'rename'} onChange={() => changeMode('rename')} />
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
              {/* 已有标签点选区：按分类分组（组头=分类名＋组内标签＋「未分类」尾组，INT-2102）；
                  加载/错误态照 INT-1560 口径显示，不落成「暂无标签」空态 */}
              {(byCategoryQuery.isLoading ||
                byCategoryQuery.isError ||
                groupedTags.length > 0) && (
                <div className='space-y-1.5'>
                  <span className='text-muted-foreground text-xs'>
                    {mode === 'add' ? '已有标签（点击添加）：' : '已有标签（点击移除）：'}
                  </span>
                  {byCategoryQuery.isLoading ? (
                    <div className='flex items-center gap-2 px-1 py-2 text-sm text-muted-foreground'>
                      <Spinner className='size-3.5' />
                      加载中…
                    </div>
                  ) : byCategoryQuery.isError ? (
                    <div className='flex flex-col items-center gap-2 py-3 text-center'>
                      <p className='text-destructive text-sm'>标签分组加载失败</p>
                      <Button
                        variant='outline'
                        size='sm'
                        className='h-7'
                        onClick={() => void byCategoryQuery.refetch()}
                      >
                        重试
                      </Button>
                    </div>
                  ) : (
                    <div className='mt-1 max-h-56 space-y-2 overflow-y-auto rounded-lg border p-2'>
                      {groupedTags.map((group) => (
                        <div key={group.category?.id ?? 'uncategorized'}>
                          <p className='text-muted-foreground px-1 py-0.5 text-xs font-medium'>
                            {group.category?.name ?? '未分类'}
                          </p>
                          <div className='flex flex-wrap items-center gap-1.5'>
                            {group.tags.map((tag) => (
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
                      ))}
                    </div>
                  )}
                </div>
              )}
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
                ? !renameFrom ||
                  !renameTo.trim() ||
                  // INT-1591：新旧同名禁用「确定」（照 V9.7.10 BatchTagsModal isValid）
                  renameTo.trim() === renameFrom
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
