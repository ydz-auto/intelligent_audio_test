/**
 * 评估维度页分类表单弹窗（features/evaluation/modals；11_用例域.md §5.5 分类表单）。
 * Dialog sm:max-w-md 三字段：分类名称（必填）/ 描述 / 图标（占位「如 fas fa-folder」默认 fas fa-folder）。
 * 成功 toast「分类添加成功｜分类更新成功」。
 */
import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useState } from 'react'
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
import { ApiError } from '@/infrastructure/api/api-error'

const categorySchema = z.object({
  name: z.string().min(1, '分类名称不能为空'),
  description: z.string(),
  icon: z.string(),
})

type CategoryFormValues = z.infer<typeof categorySchema>

function emptyValues(): CategoryFormValues {
  return { name: '', description: '', icon: DEFAULT_CATEGORY_ICON }
}

function toFormValues(category: EvaluationCategory | null): CategoryFormValues {
  if (!category) return emptyValues()
  return {
    name: category.name,
    description: category.description ?? '',
    icon: category.icon ?? DEFAULT_CATEGORY_ICON,
  }
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
  /** 返回 Promise：失败时弹窗保持打开并就地展示错误（重名 400 等） */
  onSave: (input: Partial<EvaluationCategory>, isNew: boolean) => Promise<void>
}) {
  const [pending, setPending] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const isNew = !category

  const form = useForm<CategoryFormValues>({
    resolver: zodResolver(categorySchema),
    defaultValues: emptyValues(),
  })

  const categoryId = category?.id ?? null
  // 按「打开 / 切换分类」显式重置：不用 useForm 的 values —— 它按深相等判重跳过同步，
  // 关闭时清空后重开同一分类（值深相等）不会回填（INT-1577）。
  useEffect(() => {
    form.reset(open ? toFormValues(category) : emptyValues())
    if (!open) setSubmitError(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, categoryId])

  const handleSave = form.handleSubmit(async (values) => {
    setPending(true)
    setSubmitError(null)
    try {
      await onSave(values, isNew)
      onOpenChange(false)
    } catch (error) {
      // 保存失败（如分类名称已存在 400）：保留弹窗与已填内容，就地提示
      setSubmitError(
        error instanceof ApiError ? error.userMessage : '保存失败，请稍后重试'
      )
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
          {submitError && (
            <p className='text-destructive text-xs' role='alert'>
              {submitError}
            </p>
          )}
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
