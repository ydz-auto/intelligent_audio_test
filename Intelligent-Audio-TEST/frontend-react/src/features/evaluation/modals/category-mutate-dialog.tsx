/**
 * 评估维度页分类表单弹窗（features/evaluation/modals；11_用例域.md §5.5 分类表单）。
 * Dialog sm:max-w-md 三字段：分类名称（必填）/ 描述 / 图标（占位「如 fas fa-folder」默认 fas fa-folder）。
 * 成功 toast「分类添加成功｜分类更新成功」。
 */
import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

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
import type { EvaluationCategory } from '@/domain/models/evaluationDimension'
import { DEFAULT_CATEGORY_ICON } from '@/features/evaluation/constants'

const categorySchema = z.object({
  name: z.string().min(1, '分类名称不能为空'),
  description: z.string(),
  icon: z.string(),
})

type CategoryFormValues = z.infer<typeof categorySchema>

function emptyValues(): CategoryFormValues {
  return { name: '', description: '', icon: DEFAULT_CATEGORY_ICON }
}

export function CategoryMutateDialog({
  open,
  onOpenChange,
  category,
  onSave,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  category: EvaluationCategory | null
  onSave: (input: Partial<EvaluationCategory>, isNew: boolean) => void
}) {
  const [pending, setPending] = useState(false)
  const isNew = !category

  const defaultValues = useMemo(() => {
    if (!open) return undefined
    return category
      ? {
          name: category.name,
          description: category.description ?? '',
          icon: category.icon ?? DEFAULT_CATEGORY_ICON,
        }
      : emptyValues()
  }, [open, category])

  const form = useForm<CategoryFormValues>({
    resolver: zodResolver(categorySchema),
    defaultValues: emptyValues(),
    values: defaultValues,
  })

  useEffect(() => {
    if (!open) form.reset(emptyValues())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const handleSave = form.handleSubmit(async (values) => {
    setPending(true)
    try {
      onSave(values, isNew)
      onOpenChange(false)
    } finally {
      setPending(false)
    }
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>
            {isNew ? '新建分类' : '编辑分类'}
          </DialogTitle>
          <DialogDescription>
            管理评估维度分类，用于维度分组与筛选
          </DialogDescription>
        </DialogHeader>

        <form id='category-form' onSubmit={handleSave} className='space-y-3'>
          <div className='space-y-1.5'>
            <Label htmlFor='category-name' required>
              分类名称
            </Label>
            <Input
              id='category-name'
              placeholder='如：人数、场景、语种'
              aria-invalid={Boolean(form.formState.errors.name)}
              {...form.register('name')}
            />
            {form.formState.errors.name && (
              <p className='text-destructive text-xs'>
                {form.formState.errors.name.message}
              </p>
            )}
          </div>
          <div className='space-y-1.5'>
            <Label htmlFor='category-description'>描述</Label>
            <Textarea
              id='category-description'
              rows={2}
              placeholder='分类用途说明'
              {...form.register('description')}
            />
          </div>
          <div className='space-y-1.5'>
            <Label htmlFor='category-icon'>图标</Label>
            <Input
              id='category-icon'
              placeholder='如 fas fa-folder'
              {...form.register('icon')}
            />
          </div>
        </form>

        <DialogFooter>
          <Button
            variant='outline'
            type='button'
            disabled={pending}
            onClick={() => onOpenChange(false)}
          >
            取消
          </Button>
          <Button
            type='submit'
            form='category-form'
            disabled={pending || !form.formState.isValid}
          >
            {pending ? '保存中...' : isNew ? '创建' : '保存'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
