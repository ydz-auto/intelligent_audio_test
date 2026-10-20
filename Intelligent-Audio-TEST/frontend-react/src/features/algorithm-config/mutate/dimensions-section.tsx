/**
 * §6.6 评估维度分节（mutate sheet 第五 Tab）。
 * 说明文案 + 筛选（搜索维度）+ 内联可编辑表（评估维度 DimensionSelect 分组/主维度/子维度、
 * 权重 number 0-1/默认 Checkbox，多选一时自动唯一）。
 */
import { Plus, Trash2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { type UseFormReturn } from 'react-hook-form'
import { useFieldArray, useWatch } from 'react-hook-form'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import type { AlgorithmFormValues } from '@/features/algorithm-config/types'
import { DIMENSIONS_DESCRIPTION } from '@/features/algorithm-config/constants'
import type { Dimension, EvaluationCategory } from '@/domain/models/evaluationDimension'
import { DimensionSelect } from './dimension-select'

export function DimensionsSection({
  form,
  dimensions,
  categories = [],
}: {
  form: UseFormReturn<AlgorithmFormValues>
  /** 评估维度全量（含子维度；关联维度选择按 分组/主维度/子维度 展示） */
  dimensions: Dimension[]
  /** 评估维度分类（分类分组组头） */
  categories?: EvaluationCategory[]
}) {
  const dimensionRows = useFieldArray({
    control: form.control,
    name: 'associatedDimensions',
  })

  // 筛选状态（§6.6：搜索维度，照 V9.7.10 filteredDimensions 按维度名过滤）
  const [search, setSearch] = useState('')

  const watchDimensions = form.watch('associatedDimensions')

  // 仅显示过滤命中行的「原始数组下标」（RHF 注册/取值必须用原下标）
  const filteredIndices = useMemo(() => {
    const kw = search.trim().toLowerCase()
    if (!kw) return dimensionRows.fields.map((_, index) => index)
    return dimensionRows.fields
      .map((_, index) => index)
      .filter((index) => {
        const row = watchDimensions[index]
        if (!row) return false
        const name =
          row.dimensionName ||
          dimensions.find((d) => String(d.id) === row.dimensionId)?.name ||
          ''
        return name.toLowerCase().includes(kw)
      })
  }, [search, dimensionRows.fields, watchDimensions, dimensions])

  const addEmpty = () =>
    dimensionRows.append({
      key: `dim-${Date.now()}-${dimensionRows.fields.length}`,
      dimensionId: '',
      dimensionName: '',
      weight: '1',
      isDefault: false,
    })

  const handleDimensionSelect = (index: number, value: string) => {
    const dimension = dimensions.find((d) => String(d.id) === value)
    form.setValue(`associatedDimensions.${index}.dimensionId`, value)
    form.setValue(`associatedDimensions.${index}.dimensionName`, dimension?.name ?? '')
  }

  const handleDefaultToggle = (index: number, checked: boolean) => {
    if (!checked) {
      form.setValue(`associatedDimensions.${index}.isDefault`, false)
      return
    }
    // 多选一时自动唯一（§6.6：默认 Checkbox）
    const rows = form.getValues('associatedDimensions')
    rows.forEach((_, rowIndex) => {
      form.setValue(`associatedDimensions.${rowIndex}.isDefault`, rowIndex === index)
    })
  }

  const defaultCount = useWatch({
    control: form.control,
    name: 'associatedDimensions',
  }).filter((row) => row.isDefault).length

  return (
    <div className='space-y-3'>
      <p className='text-muted-foreground text-xs'>
        {DIMENSIONS_DESCRIPTION}
        {defaultCount > 1 && (
          <span className='text-warning ml-1'>当前有 {defaultCount} 个默认维度，仅首个生效</span>
        )}
      </p>

      {/* 筛选行（搜索维度 + 添加关联维度，§6.6；样式照 params-table） */}
      <div className='flex flex-wrap items-center gap-2'>
        <Input
          aria-label='搜索评估维度'
          placeholder='搜索评估维度...'
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className='h-7 w-44 text-xs'
        />
        <div className='ml-auto'>
          <Button variant='outline' size='sm' type='button' onClick={addEmpty}>
            <Plus aria-hidden='true' />
            添加关联维度
          </Button>
        </div>
      </div>

      <div className='bg-card ring-foreground/10 overflow-hidden rounded-lg ring-1'>
        <div className='overflow-x-auto'>
          <table className='w-full min-w-0 text-[13px]'>
            <thead>
              <tr className='bg-[var(--table-header)] text-xs'>
                <th className='px-3 py-2 text-left font-medium'>评估维度</th>
                <th className='px-3 py-2 text-left font-medium'>权重</th>
                <th className='px-3 py-2 text-center font-medium'>默认</th>
                <th className='w-10 px-3 py-2 text-right font-medium'>操作</th>
              </tr>
            </thead>
            <tbody>
              {dimensionRows.fields.length === 0 ? (
                <tr>
                  <td colSpan={4} className='text-muted-foreground px-3 py-6 text-center'>
                    暂未关联评估维度，点击「添加关联维度」新增
                  </td>
                </tr>
              ) : filteredIndices.length === 0 ? (
                <tr>
                  <td colSpan={4} className='text-muted-foreground px-3 py-6 text-center'>
                    未找到匹配评估维度，换个关键词试试
                  </td>
                </tr>
              ) : (
                filteredIndices.map((index) => (
                  <tr
                    key={dimensionRows.fields[index].key}
                    className='border-border/50 border-b last:border-b-0'
                  >
                    <td className='px-2 py-1.5'>
                      <DimensionSelect
                        dimensions={dimensions}
                        categories={categories}
                        value={form.watch(`associatedDimensions.${index}.dimensionId`) ?? ''}
                        onValueChange={(value) => handleDimensionSelect(index, value)}
                        valueOf={(dimension) => String(dimension.id)}
                        placeholder='选择评估维度'
                        triggerClassName='w-56'
                      />
                    </td>
                    <td className='px-2 py-1.5'>
                      <Input
                        aria-label='权重'
                        type='number'
                        min={0}
                        max={1}
                        step={0.1}
                        className='h-7 w-24 font-mono text-xs'
                        {...form.register(`associatedDimensions.${index}.weight`)}
                      />
                    </td>
                    <td className='px-2 py-1.5 text-center'>
                      <span className='inline-flex items-center justify-center'>
                        <Checkbox
                          aria-label={`默认维度 ${form.watch(`associatedDimensions.${index}.dimensionName`) ?? ''}`}
                          checked={form.watch(`associatedDimensions.${index}.isDefault`)}
                          onCheckedChange={(checked) =>
                            handleDefaultToggle(index, Boolean(checked))
                          }
                        />
                      </span>
                    </td>
                    <td className='px-2 py-1.5'>
                      <div className='flex items-center justify-end'>
                        <Button
                          variant='ghost'
                          size='icon-sm'
                          type='button'
                          aria-label='移除该维度关联'
                          className='text-destructive'
                          onClick={() => dimensionRows.remove(index)}
                        >
                          <Trash2 aria-hidden='true' className='size-3.5' />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
