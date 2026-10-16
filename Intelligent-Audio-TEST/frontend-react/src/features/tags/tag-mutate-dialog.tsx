/**
 * 标签/分类表单弹窗（11_用例域.md §5.4，Dialog sm:max-w-md，字段逐字照现
 * TagEditModal/TagCategoryModal）：标签名称/所属分类/描述/颜色（预设色板 8 色 + 自定义）；
 * 分类名称/描述/颜色/排序（number min 0，新建默认=末位+1）。
 * 全部 mock 态：主钮提交后 toast + 关闭，接线后替换为 tagsApi create/update。
 */
import { useEffect, useState } from 'react'
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
import { cn } from '@/lib/utils'
import type { TagCategory, TagItem } from '@/domain/models/testTag'
import {
  DEFAULT_CATEGORY_COLOR,
  DEFAULT_TAG_COLOR,
  TAG_DESC_MAX_LENGTH,
  TAG_NAME_MAX_LENGTH,
  TAG_PALETTE,
} from '@/features/tags/constants'

/** 色板选择器（预设 8 色 + 自定义原生 color input；值始终为 hex 串） */
function ColorPicker({
  value,
  onChange,
}: {
  value: string
  onChange: (color: string) => void
}) {
  return (
    <div className='space-y-2'>
      <div className='flex flex-wrap items-center gap-2'>
        {TAG_PALETTE.map((color) => {
          const active = value.toLowerCase() === color.toLowerCase()
          return (
            <button
              key={color}
              type='button'
              aria-label={`颜色 ${color}`}
              aria-pressed={active}
              onClick={() => onChange(color)}
              className={cn(
                'flex size-7 items-center justify-center rounded-full transition-transform hover:scale-105',
                active &&
                  'ring-ring ring-2 ring-offset-2 ring-offset-background'
              )}
              style={{ backgroundColor: color }}
            >
              {active && (
                <span
                  aria-hidden='true'
                  className='block size-2 rounded-full bg-white/80'
                />
              )}
            </button>
          )
        })}
        <label className='relative inline-flex size-7 cursor-pointer items-center justify-center overflow-hidden rounded-full border border-dashed transition-colors hover:border-foreground/50'>
          <span
            aria-hidden='true'
            className='absolute inset-0'
            style={{
              background:
                'conic-gradient(from 90deg, #ef4444, #f59e0b, #10b981, #06b6d4, #6366f1, #a855f7, #ef4444)',
            }}
          />
          <input
            type='color'
            value={value}
            onChange={(e) => onChange(e.target.value)}
            className='absolute inset-0 cursor-pointer opacity-0'
            aria-label='自定义颜色'
          />
          <span className='text-background z-10 text-[10px] font-bold'>▦</span>
        </label>
      </div>
      <p className='text-muted-foreground font-mono text-xs tabular-nums'>
        {value}
      </p>
    </div>
  )
}

/* ───────────────────────── 标签表单 ───────────────────────── */

export function TagEditDialog({
  open,
  onOpenChange,
  tag,
  categories,
  presetCategoryId,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  tag: TagItem | null
  categories: TagCategory[]
  /** 新建时预填所属分类（当前选中分类；未分类视图=null） */
  presetCategoryId: number | null
}) {
  const isEdit = tag != null
  const [name, setName] = useState(tag?.name ?? '')
  const [categoryId, setCategoryId] = useState<number | null>(
    tag?.categoryId ?? presetCategoryId
  )
  const [description, setDescription] = useState(tag?.description ?? '')
  const [color, setColor] = useState(tag?.color ?? DEFAULT_TAG_COLOR)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  // 打开时重置表单（Dialog 保持挂载，需随目标项同步初始化）
  useEffect(() => {
    if (!open) return
    setName(tag?.name ?? '')
    setCategoryId(tag?.categoryId ?? presetCategoryId)
    setDescription(tag?.description ?? '')
    setColor(tag?.color ?? DEFAULT_TAG_COLOR)
    setError('')
  }, [open, tag, presetCategoryId])

  const canSubmit = name.trim().length > 0 && name.trim().length <= TAG_NAME_MAX_LENGTH

  const handleSubmit = () => {
    if (!canSubmit || saving) return
    setError('')
    setSaving(true)
    // TODO(API 接线): POST/PUT /api/v1/tags（schemas/testcase.py TagCreate/Update）
    window.setTimeout(() => {
      setSaving(false)
      toast.success(isEdit ? '标签更新成功' : '标签创建成功')
      onOpenChange(false)
    }, 400)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>{isEdit ? '编辑标签' : '新建标签'}</DialogTitle>
          <DialogDescription>标签用于用例筛选和报告统计</DialogDescription>
        </DialogHeader>
        <div className='space-y-4'>
          <div className='space-y-1.5'>
            <Label htmlFor='tag-name' required>
              标签名称
            </Label>
            <Input
              id='tag-name'
              value={name}
              maxLength={TAG_NAME_MAX_LENGTH}
              onChange={(e) => setName(e.target.value)}
              placeholder='如：1人、2人、会议室'
              className='h-8'
            />
            <p className='text-muted-foreground text-xs tabular-nums'>
              {name.length}/{TAG_NAME_MAX_LENGTH}
            </p>
          </div>
          <div className='space-y-1.5'>
            <Label htmlFor='tag-category'>所属分类</Label>
            <Select
              value={categoryId != null ? String(categoryId) : 'none'}
              onValueChange={(value) =>
                setCategoryId(value === 'none' ? null : Number(value))
              }
            >
              <SelectTrigger size='sm' className='h-8 w-full'>
                <SelectValue placeholder='未分类' />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='none'>未分类</SelectItem>
                {categories.map((cat) => (
                  <SelectItem key={cat.id} value={String(cat.id)}>
                    {cat.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className='space-y-1.5'>
            <Label htmlFor='tag-desc'>描述</Label>
            <Textarea
              id='tag-desc'
              rows={2}
              value={description}
              maxLength={TAG_DESC_MAX_LENGTH}
              onChange={(e) => setDescription(e.target.value)}
              placeholder='标签描述'
            />
            <p className='text-muted-foreground text-xs tabular-nums'>
              {description.length}/{TAG_DESC_MAX_LENGTH}
            </p>
          </div>
          <div className='space-y-1.5'>
            <Label>颜色</Label>
            <ColorPicker value={color} onChange={setColor} />
          </div>
          {error && <p className='text-destructive text-sm'>{error}</p>}
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button disabled={!canSubmit || saving} onClick={handleSubmit}>
            {saving ? '保存中...' : isEdit ? '保存' : '创建'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/* ───────────────────────── 分类表单 ───────────────────────── */

export function TagCategoryDialog({
  open,
  onOpenChange,
  category,
  nextSortOrder,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  category: TagCategory | null
  /** 新建默认排序=末位+1（现 openCategoryModal 口径） */
  nextSortOrder: number
}) {
  const isEdit = category != null
  const [name, setName] = useState(category?.name ?? '')
  const [description, setDescription] = useState(category?.description ?? '')
  const [color, setColor] = useState(category?.color ?? DEFAULT_CATEGORY_COLOR)
  const [sortOrder, setSortOrder] = useState(category?.sortOrder ?? nextSortOrder)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  // 打开时重置表单（Dialog 保持挂载，需随目标项同步初始化）
  useEffect(() => {
    if (!open) return
    setName(category?.name ?? '')
    setDescription(category?.description ?? '')
    setColor(category?.color ?? DEFAULT_CATEGORY_COLOR)
    setSortOrder(category?.sortOrder ?? nextSortOrder)
    setError('')
  }, [open, category, nextSortOrder])

  const canSubmit =
    name.trim().length > 0 && name.trim().length <= TAG_NAME_MAX_LENGTH

  const handleSubmit = () => {
    if (!canSubmit || saving) return
    setError('')
    setSaving(true)
    // TODO(API 接线): POST/PUT /api/v1/tags/categories
    window.setTimeout(() => {
      setSaving(false)
      toast.success(isEdit ? '分类更新成功' : '分类创建成功')
      onOpenChange(false)
    }, 400)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>{isEdit ? '编辑分类' : '新建分类'}</DialogTitle>
          <DialogDescription>分类用于标签的组织与用例筛选</DialogDescription>
        </DialogHeader>
        <div className='space-y-4'>
          <div className='space-y-1.5'>
            <Label htmlFor='category-name' required>
              分类名称
            </Label>
            <Input
              id='category-name'
              value={name}
              maxLength={TAG_NAME_MAX_LENGTH}
              onChange={(e) => setName(e.target.value)}
              placeholder='如：人数、场景、语种'
              className='h-8'
            />
            <p className='text-muted-foreground text-xs tabular-nums'>
              {name.length}/{TAG_NAME_MAX_LENGTH}
            </p>
          </div>
          <div className='space-y-1.5'>
            <Label htmlFor='category-desc'>描述</Label>
            <Textarea
              id='category-desc'
              rows={2}
              value={description}
              maxLength={TAG_DESC_MAX_LENGTH}
              onChange={(e) => setDescription(e.target.value)}
              placeholder='分类描述'
            />
            <p className='text-muted-foreground text-xs tabular-nums'>
              {description.length}/{TAG_DESC_MAX_LENGTH}
            </p>
          </div>
          <div className='grid gap-x-4 sm:grid-cols-[1fr_96px]'>
            <div className='space-y-1.5'>
              <Label>颜色</Label>
              <ColorPicker value={color} onChange={setColor} />
            </div>
            <div className='space-y-1.5'>
              <Label htmlFor='category-sort'>排序</Label>
              <Input
                id='category-sort'
                type='number'
                min={0}
                value={sortOrder}
                onChange={(e) =>
                  setSortOrder(Math.max(0, Number(e.target.value)))
                }
                className='h-8'
              />
            </div>
          </div>
          {error && <p className='text-destructive text-sm'>{error}</p>}
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button disabled={!canSubmit || saving} onClick={handleSubmit}>
            {saving ? '保存中...' : isEdit ? '保存' : '创建'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
