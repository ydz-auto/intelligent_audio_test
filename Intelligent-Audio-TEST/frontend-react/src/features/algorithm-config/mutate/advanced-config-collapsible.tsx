/**
 * §6.5 高级配置折叠区（INT-591：映射/参考参数/关联维度收进默认收起的 Collapsible）。
 * 母版 = newAPI channel-advanced-section（Collapsible + ChevronDown + Settings 图标 + summary + children）。
 * 折叠头计数徽章「高级配置 · 参考参数 {n} · 映射 {n} · 维度 {n}」；默认收起，展开态仅 Sheet 会话内记忆。
 */
import { ChevronDown, Settings } from 'lucide-react'
import { useState } from 'react'
import { type UseFormReturn, useWatch } from 'react-hook-form'

import { Badge } from '@/components/ui/badge'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'
import type { Dimension, EvaluationCategory } from '@/domain/models/evaluationDimension'
import type { AlgorithmFormValues } from '@/features/algorithm-config/types'
import { ReferenceParamsSection } from './reference-params-section'
import { MappingsSection } from './mappings-section'
import { DimensionsSection } from './dimensions-section'
import type { AlgorithmOption } from './annotation-code-select'

export function AdvancedConfigCollapsible({
  form,
  algorithmOptions,
  dimensions,
  categories = [],
}: {
  form: UseFormReturn<AlgorithmFormValues>
  /** 算法列表（标注代码下拉选项） */
  algorithmOptions: AlgorithmOption[]
  /** 评估维度全量（含子维度；映射/关联维度按 分组/主维度/子维度 展示） */
  dimensions: Dimension[]
  /** 评估维度分类（分类分组组头） */
  categories?: EvaluationCategory[]
}) {
  const [open, setOpen] = useState(false)

  const referenceCount = useWatch({
    control: form.control,
    name: 'referenceParams',
  }).length
  const mappingCount = useWatch({
    control: form.control,
    name: 'mappings',
  })
  const mappingTotal =
    mappingCount.device.length + mappingCount.api.length + mappingCount.evaluation.length
  const dimensionCount = useWatch({
    control: form.control,
    name: 'associatedDimensions',
  }).length

  return (
    <div className='border-t border-border pt-3'>
      <Collapsible open={open} onOpenChange={setOpen}>
        <CollapsibleTrigger
          render={
            <button
              type='button'
              className='hover:bg-muted/40 border-border/60 flex w-full items-center justify-between rounded-lg border px-3 py-3 text-left transition-colors'
              aria-expanded={open}
            />
          }
        >
          <div className='flex items-start gap-3'>
            <span className='bg-muted text-muted-foreground flex size-8 shrink-0 items-center justify-center rounded-md'>
              <Settings className='h-4 w-4' aria-hidden='true' />
            </span>
            <div className='flex flex-col gap-0.5'>
              <div className='text-[13px] font-semibold'>高级配置</div>
              <Badge variant='outline' className='w-fit text-[11px] font-normal tabular-nums'>
                参考参数 {referenceCount} · 映射 {mappingTotal} · 维度 {dimensionCount}
              </Badge>
            </div>
          </div>
          <ChevronDown
            className={cn(
              'text-muted-foreground h-4 w-4 shrink-0 transition-transform',
              open && 'rotate-180'
            )}
            aria-hidden='true'
          />
        </CollapsibleTrigger>

        <CollapsibleContent className='mt-4 flex flex-col gap-5'>
          <ReferenceParamsSection form={form} algorithmOptions={algorithmOptions} />
          <MappingsSection
            form={form}
            dimensions={dimensions}
            categories={categories}
          />
          <DimensionsSection
            form={form}
            dimensions={dimensions}
            categories={categories}
          />
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}
