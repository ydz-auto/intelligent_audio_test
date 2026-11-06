/**
 * 标签/分类表单弹窗（11_用例域.md §5.4，Dialog sm:max-w-md，字段逐字照现
 * TagEditModal/TagCategoryModal）：标签名称/所属分类/描述/颜色（预设色板 8 色 + 自定义）；
 * 分类名称/描述/颜色/排序（number min 0，新建默认=末位+1）。
 * INT-504 标签分类体系口径：新建/编辑标签**必须选分类**（负责人 2026-10-16 需求，
 * canSubmit 校验 categoryId 非空；Select 不再提供「未分类」逃逸项，占位「请选择所属分类」）。
 * 接线 INT-648：主钮提交走真实 POST/PUT /tags（分类走 /tags/categories），
 * 提交回调由页面装配（mutation），错误经 setError 呈现 + toast。
 */
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import type {
  TagCategory,
  TagCategoryDraft,
  TagDraft,
  TagItem,
} from '@/domain/models/testTag'
import { ApiError } from '@/infrastructure/api/api-error'
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
  onSubmit,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  tag: TagItem | null
  categories: TagCategory[]
  /** 新建时预填所属分类（当前选中分类；未分类视图=null） */
  presetCategoryId: number | null
  /** 提交回调（页面装配真实 POST/PUT mutation；成功即关闭） */
  onSubmit?: (draft: TagDraft, id?: number) => Promise<void>
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

  const canSubmit =
    name.trim().length > 0 &&
    name.trim().length <= TAG_NAME_MAX_LENGTH &&
    categoryId != null

  const handleSubmit = async () => {
    if (!canSubmit || saving) return
    setError('')
    setSaving(true)
    try {
      await onSubmit?.(
        { name: name.trim(), description, color, categoryId },
        tag?.id
      )
      toast.success(isEdit ? '标签更新成功' : '标签创建成功')
      onOpenChange(false)
    } catch (err) {
      const message =
        err instanceof ApiError ? err.userMessage : '保存失败，请稍后重试'
      setError(message)
      toast.error(message)
    } finally {
      setSaving(false)
    }
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
            <Label htmlFor='tag-category' required>
              所属分类
            </Label>
            <Select
              value={categoryId != null ? String(categoryId) : null}
              onValueChange={(value) =>
                setCategoryId(value == null ? null : Number(value))
              }
            >
              <SelectTrigger size='sm' className='h-8 w-full'>
                <SelectValue placeholder='请选择所属分类'>
                  {categoryId != null
                    ? (categories.find((c) => c.id === categoryId)?.name ?? null)
                    : null}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {categories.map((cat) => (
                  <SelectItem key={cat.id} value={String(cat.id)}>
                    {cat.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {categoryId == null && (
              <p className='text-muted-foreground text-xs'>
                请选择所属分类，标签将按分类分组展示
              </p>
            )}
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
  onSubmit,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  category: TagCategory | null
  /** 新建默认排序=末位+1（现 openCategoryModal 口径） */
  nextSortOrder: number
  /** 提交回调（页面装配真实 POST/PUT mutation；成功即关闭） */
  onSubmit?: (draft: TagCategoryDraft, id?: number) => Promise<void>
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

  const handleSubmit = async () => {
    if (!canSubmit || saving) return
    setError('')
    setSaving(true)
    try {
      await onSubmit?.(
        { name: name.trim(), description, color, sortOrder },
        category?.id
      )
      toast.success(isEdit ? '分类更新成功' : '分类创建成功')
      onOpenChange(false)
    } catch (err) {
      const message =
        err instanceof ApiError ? err.userMessage : '保存失败，请稍后重试'
      setError(message)
      toast.error(message)
    } finally {
      setSaving(false)
    }
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
