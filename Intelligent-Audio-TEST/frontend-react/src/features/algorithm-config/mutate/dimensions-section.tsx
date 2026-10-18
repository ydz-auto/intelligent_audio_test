/**
 * §6.6 评估维度分节（mutate sheet 第五 Tab）。
 * 说明文案 + 内联可编辑表（评估维度 Select/权重 number 0-1/默认 Checkbox，多选一时自动唯一）。
 */
import { Plus, Trash2 } from 'lucide-react'
import { type UseFormReturn } from 'react-hook-form'
import { useFieldArray, useWatch } from 'react-hook-form'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { AlgorithmFormValues } from '@/features/algorithm-config/types'
import { DIMENSIONS_DESCRIPTION } from '@/features/algorithm-config/constants'

export function DimensionsSection({
  form,
  dimensionOptions,
}: {
  form: UseFormReturn<AlgorithmFormValues>
  dimensionOptions: Array<{ id: number; name: string }>
}) {
  const dimensions = useFieldArray({
    control: form.control,
    name: 'associatedDimensions',
  })

  const addEmpty = () =>
    dimensions.append({
      key: `dim-${Date.now()}-${dimensions.fields.length}`,
      dimensionId: '',
      dimensionName: '',
      weight: '1',
      isDefault: false,
    })

  const handleDimensionSelect = (index: number, value: string) => {
    const dimension = dimensionOptions.find((d) => String(d.id) === value)
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

      <div className='flex items-center justify-end'>
        <Button variant='outline' size='sm' type='button' onClick={addEmpty}>
          <Plus aria-hidden='true' />
          添加关联维度
        </Button>
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
              {dimensions.fields.length === 0 ? (
                <tr>
                  <td colSpan={4} className='text-muted-foreground px-3 py-6 text-center'>
                    暂未关联评估维度，点击「添加关联维度」新增
                  </td>
                </tr>
              ) : (
                dimensions.fields.map((field, index) => (
                  <tr key={field.key} className='border-border/50 border-b last:border-b-0'>
                    <td className='px-2 py-1.5'>
                      <Select
                        value={form.watch(`associatedDimensions.${index}.dimensionId`)}
                        onValueChange={(value) => handleDimensionSelect(index, value ?? '')}
                      >
                        <SelectTrigger size='sm' className='w-56'>
                          <SelectValue>
                            {dimensionOptions.find(
                              (d) =>
                                String(d.id) ===
                                form.watch(
                                  `associatedDimensions.${index}.dimensionId`
                                )
                            )?.name ?? '选择评估维度'}
                          </SelectValue>
                        </SelectTrigger>
                        <SelectContent>
                          {dimensionOptions.map((dimension) => (
                            <SelectItem key={dimension.id} value={String(dimension.id)}>
                              {dimension.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
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
                          onClick={() => dimensions.remove(index)}
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
