/**
 * 评估维度页 facet 筛选控件（features/evaluation；§4.1 筛选行）。
 * 单选取值 Popover（newAPI DataTableFacetedFilter 等价轻量件）：
 * Trigger 显「{标题}：{当前值|默认文案}」，打开后选项列表单选，选中打勾。
 * 分类/关联算法 facet 选项动态（useEvaluationCategories / useAlgorithmOptions）。
 */
import { Check, ChevronDown } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { cn } from '@/lib/utils'

export interface FacetOption {
  value: string
  label: string
}

export function FacetFilter({
  title,
  allLabel,
  options,
  value,
  onValueChange,
  disabled,
}: {
  title: string
  allLabel: string
  options: FacetOption[]
  value: string
  onValueChange: (value: string) => void
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const active = options.find((o) => o.value === value)
  const label = active ? active.label : allLabel
  const isFiltered = value !== 'all'

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button
            variant='outline'
            size='sm'
            className='h-7 gap-1.5 border-dashed'
            disabled={disabled}
          >
            <span className='text-muted-foreground'>{title}</span>
            <span className={cn(isFiltered && 'text-foreground font-medium')}>
              {label}
            </span>
            <ChevronDown
              aria-hidden='true'
              className='text-muted-foreground size-3.5 opacity-60'
            />
          </Button>
        }
      />
      <PopoverContent className='w-52 p-1.5'>
        <p className='text-muted-foreground px-2 py-1.5 text-xs font-medium'>
          {title}
        </p>
        <div className='grid gap-0.5'>
          <FacetItem
            active={value === 'all'}
            label={allLabel}
            onClick={() => {
              onValueChange('all')
              setOpen(false)
            }}
          />
          {options.map((option) => (
            <FacetItem
              key={option.value}
              active={value === option.value}
              label={option.label}
              onClick={() => {
                onValueChange(option.value)
                setOpen(false)
              }}
            />
          ))}
        </div>
      </PopoverContent>
    </Popover>
  )
}

function FacetItem({
  label,
  active,
  onClick,
}: {
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type='button'
      onClick={onClick}
      className={cn(
        'hover:bg-accent text-foreground/80 flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-start text-sm',
        active && 'text-foreground'
      )}
    >
      <span className='min-w-0 flex-1 truncate'>{label}</span>
      {active && <Check aria-hidden='true' className='size-4 shrink-0' />}
    </button>
  )
}
