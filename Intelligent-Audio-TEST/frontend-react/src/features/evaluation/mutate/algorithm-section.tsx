/**
 * 评估维度表单「关联算法」分节（11_用例域.md §5.5 关联算法；仅主维度）。
 * 算法多选（Combobox chips 等价轻量件：Popover 内 Checkbox 多选，选中项以 Badge chips 展示；
 * 选项 GET /algorithm/options 中文名登记表）。
 */
import { ChevronDown, X } from 'lucide-react'
import type { UseFormReturn } from 'react-hook-form'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import type { DimensionFormValues } from '@/features/evaluation/mutate/dimension-form-schema'

export function AlgorithmSection({
  form,
  algorithmOptions,
}: {
  form: UseFormReturn<DimensionFormValues>
  algorithmOptions: Array<{ value: string; label: string }>
}) {
  const { watch, setValue } = form
  const selected = watch('associatedAlgorithms')

  const toggle = (value: string, checked: boolean) => {
    setValue(
      'associatedAlgorithms',
      checked
        ? [...selected, value]
        : selected.filter((v) => v !== value),
      { shouldDirty: true }
    )
  }

  return (
    <div className='space-y-3'>
      <div className='space-y-1.5'>
        <Label>关联算法</Label>
        <Popover>
          <PopoverTrigger
            render={
              <Button
                variant='outline'
                size='sm'
                className='h-9 w-full justify-between gap-1.5'
              >
                <span className='text-muted-foreground truncate'>
                  {selected.length > 0
                    ? `已选择 ${selected.length} 个算法`
                    : '选择关联的算法类型'}
                </span>
                <ChevronDown
                  aria-hidden='true'
                  className='text-muted-foreground size-3.5 opacity-60'
                />
              </Button>
            }
          />
          <PopoverContent className='w-64 p-1.5'>
            <p className='text-muted-foreground px-2 py-1.5 text-xs font-medium'>
              选择关联的算法类型
            </p>
            <div className='grid gap-0.5'>
              {algorithmOptions.map((option) => (
                <label
                  key={option.value}
                  className='hover:bg-accent flex items-center gap-2 rounded-md px-2 py-1.5 text-sm'
                >
                  <Checkbox
                    aria-label={`关联算法 ${option.label}`}
                    checked={selected.includes(option.value)}
                    onCheckedChange={(checked) => toggle(option.value, !!checked)}
                  />
                  <span className='min-w-0 flex-1 truncate'>
                    {option.label}
                  </span>
                </label>
              ))}
              {algorithmOptions.length === 0 && (
                <p className='text-muted-foreground px-2 py-1.5 text-xs'>
                  暂无可用算法
                </p>
              )}
            </div>
          </PopoverContent>
        </Popover>
      </div>

      {selected.length > 0 && (
        <div className='flex flex-wrap items-center gap-1'>
          {selected.map((value) => {
            const option = algorithmOptions.find((o) => o.value === value)
            return (
              <Badge
                key={value}
                variant='secondary'
                className='gap-1 pr-1 text-xs font-normal'
              >
                {option?.label ?? value}
                <button
                  type='button'
                  aria-label={`移除算法 ${option?.label ?? value}`}
                  onClick={() => toggle(value, false)}
                  className='hover:text-foreground rounded p-0.5'
                >
                  <X aria-hidden='true' className='size-3' />
                </button>
              </Badge>
            )
          })}
        </div>
      )}
    </div>
  )
}
