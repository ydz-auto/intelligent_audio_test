/**
 * 评估维度表单「基本信息」分节（11_用例域.md §5.5 基本信息）。
 * 维度名称* · 描述（Textarea 3 行）· 评估类型*（Select 自动/人工）·
 * 所属分类（Select：「+ 新建分类」项→内联新分类名 Input）· 状态（Switch，默认启用）。
 */
import { useState } from 'react'
import type { UseFormReturn } from 'react-hook-form'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import type { EvaluationCategory } from '@/domain/models/evaluationDimension'
import {
  DIMENSION_EVALUATION_TYPE_OPTIONS,
} from '@/features/evaluation/constants'
import type { DimensionFormValues } from '@/features/evaluation/mutate/dimension-form-schema'

const NEW_CATEGORY_SENTINEL = '__new__'

export function BasicInfoSection({
  form,
  categories,
  onNewCategory,
}: {
  form: UseFormReturn<DimensionFormValues>
  categories: EvaluationCategory[]
  onNewCategory: (name: string) => void
}) {
  const { register, watch, setValue, formState } = form
  const categoryId = watch('categoryId')
  const status = watch('status')
  const [addingCategory, setAddingCategory] = useState(false)
  const [categoryName, setCategoryName] = useState('')

  const handleCategorySelect = (value: string | null) => {
    if (value === NEW_CATEGORY_SENTINEL) {
      setAddingCategory(true)
      return
    }
    setValue('categoryId', value ?? '', { shouldDirty: true })
  }

  const handleCreateCategory = () => {
    const name = categoryName.trim()
    if (!name) return
    onNewCategory(name)
    // mock：内联新建分类生成临时负 id（接线后由 POST /categories 返回真实 id 回填）
    setValue('categoryId', String(-Date.now()), { shouldDirty: true })
    setAddingCategory(false)
    setCategoryName('')
  }

  return (
    <div className='space-y-3'>
      <div className='grid gap-3 sm:grid-cols-2'>
        <div className='space-y-1.5'>
          <Label htmlFor='dim-name' required>
            维度名称
          </Label>
          <Input
            id='dim-name'
            placeholder='如：识别准确率'
            aria-invalid={Boolean(formState.errors.name)}
            {...register('name')}
          />
          {formState.errors.name && (
            <p className='text-destructive text-xs'>
              {formState.errors.name.message}
            </p>
          )}
        </div>

        <div className='space-y-1.5'>
          <Label required>评估类型</Label>
          <Select
            value={watch('evaluationType')}
            onValueChange={(value) =>
              setValue('evaluationType', value as 'auto' | 'manual', {
                shouldDirty: true,
              })
            }
          >
            <SelectTrigger className='w-full justify-between'>
              <SelectValue placeholder='请选择评估类型' />
            </SelectTrigger>
            <SelectContent>
              {DIMENSION_EVALUATION_TYPE_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className='space-y-1.5'>
        <Label htmlFor='dim-description'>描述</Label>
        <Textarea
          id='dim-description'
          rows={3}
          placeholder='描述评估维度用途与计算口径'
          {...register('description')}
        />
      </div>

      <div className='grid gap-3 sm:grid-cols-2'>
        <div className='space-y-1.5'>
          <Label required>所属分类</Label>
          <Select value={categoryId} onValueChange={handleCategorySelect}>
            <SelectTrigger className='w-full justify-between'>
              <SelectValue placeholder='请选择分类' />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value=''>未分类</SelectItem>
              {categories.map((cat) => (
                <SelectItem key={cat.id} value={String(cat.id)}>
                  {cat.name}
                </SelectItem>
              ))}
              <SelectItem value={NEW_CATEGORY_SENTINEL}>
                + 新建分类
              </SelectItem>
            </SelectContent>
          </Select>
          {addingCategory && (
            <div className='flex items-center gap-2'>
              <Input
                aria-label='新分类名称'
                value={categoryName}
                onChange={(e) => setCategoryName(e.target.value)}
                placeholder='输入新分类名称'
                className='h-8'
              />
              <Button
                type='button'
                variant='outline'
                size='sm'
                className='h-8 shrink-0'
                disabled={!categoryName.trim()}
                onClick={handleCreateCategory}
              >
                创建
              </Button>
            </div>
          )}
        </div>

        <div className='space-y-1.5'>
          <Label className='justify-between'>
            状态
            <Switch
              aria-label='维度状态'
              checked={status}
              onCheckedChange={(checked) =>
                setValue('status', checked, { shouldDirty: true })
              }
            />
          </Label>
          <p className='text-muted-foreground text-xs'>
            {status ? '启用后维度参与评估计算' : '禁用后维度不参与评估计算'}
          </p>
        </div>
      </div>
    </div>
  )
}
