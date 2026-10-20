/**
 * §6.5 参数映射分节（mutate sheet 第四 Tab）。
 * 三折叠分区（设备/API/评估），标题带计数 Badge「{n} 条映射」；
 * MappingEditor 对位：源参数 Select → 目标参数 Select + 转换类型 Select，ArrayField 增删行。
 */
import { Plus, Trash2 } from 'lucide-react'
import { type FieldPath, type UseFormReturn } from 'react-hook-form'
import { useFieldArray, useWatch } from 'react-hook-form'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import type { Dimension, EvaluationCategory } from '@/domain/models/evaluationDimension'
import type { AlgorithmFormValues } from '@/features/algorithm-config/types'
import { DimensionSelect } from './dimension-select'
import {
  API_TRANSFORM_TYPE_OPTIONS,
  TRANSFORM_TYPE_OPTIONS,
} from '@/features/algorithm-config/constants'

type MappingArrayName =
  | 'mappings.device'
  | 'mappings.api'
  | 'mappings.evaluation'

function SourceOptions({ form }: { form: UseFormReturn<AlgorithmFormValues> }) {
  const caseParams = useWatch({ control: form.control, name: 'caseParams' })
  const referenceParams = useWatch({ control: form.control, name: 'referenceParams' })
  return [
    ...caseParams.map((param) => ({
      value: param.paramCode,
      label: `用例·${param.paramCode || '（未填）'}`,
    })),
    ...referenceParams.map((param) => ({
      value: param.code,
      label: `参考·${param.code || '（未填）'}`,
    })),
  ].filter((option) => option.value)
}

function MappingTable({
  form,
  arrayName,
  sourceLabel,
  targetOptions,
  transformOptions,
  targetSelect,
}: {
  form: UseFormReturn<AlgorithmFormValues>
  arrayName: MappingArrayName
  sourceLabel: string
  targetOptions: Array<{ value: string; label: string }>
  transformOptions: ReadonlyArray<{ value: string; label: string }>
  /** 评估映射 target 渲染覆盖（分组/主维度/子维度 DimensionSelect；未传走平铺 targetOptions） */
  targetSelect?: (index: number) => React.ReactNode
}) {
  const mappings = useFieldArray({ control: form.control, name: arrayName })
  const sourceOptions = SourceOptions({ form })

  const addEmpty = () =>
    mappings.append({
      key: `${arrayName}-${Date.now()}-${mappings.fields.length}`,
      sourceParam: '',
      targetParam: '',
      transformType: 'none',
    })

  return (
    <div className='space-y-2'>
      <div className='flex items-center justify-end'>
        <Button variant='outline' size='sm' type='button' onClick={addEmpty}>
          <Plus aria-hidden='true' />
          添加映射
        </Button>
      </div>
      <div className='bg-card ring-foreground/10 overflow-hidden rounded-lg ring-1'>
        <div className='overflow-x-auto'>
          <table className='w-full min-w-0 text-[13px]'>
            <thead>
              <tr className='bg-[var(--table-header)] text-xs'>
                <th className='px-3 py-2 text-left font-medium'>{sourceLabel}</th>
                <th className='px-3 py-2 text-left font-medium'>目标参数</th>
                <th className='px-3 py-2 text-left font-medium'>转换类型</th>
                <th className='w-10 px-3 py-2 text-right font-medium'>操作</th>
              </tr>
            </thead>
            <tbody>
              {mappings.fields.length === 0 ? (
                <tr>
                  <td colSpan={4} className='text-muted-foreground px-3 py-5 text-center'>
                    暂无映射，点击「添加映射」新增
                  </td>
                </tr>
              ) : (
                mappings.fields.map((field, index) => (
                  <tr key={field.key} className='border-border/50 border-b last:border-b-0'>
                    <td className='px-2 py-1.5'>
                      <Select
                        value={form.watch(`${arrayName}.${index}.sourceParam`)}
                        onValueChange={(value) =>
                          form.setValue(
                            `${arrayName}.${index}.sourceParam` as FieldPath<AlgorithmFormValues>,
                            value ?? ''
                          )
                        }
                      >
                        <SelectTrigger size='sm' className='w-44'>
                          <SelectValue placeholder='选择源参数' />
                        </SelectTrigger>
                        <SelectContent>
                          {sourceOptions.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {option.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </td>
                    <td className='px-2 py-1.5'>
                      {targetSelect ? (
                        targetSelect(index)
                      ) : (
                        <Select
                          value={form.watch(`${arrayName}.${index}.targetParam`)}
                          onValueChange={(value) =>
                            form.setValue(
                              `${arrayName}.${index}.targetParam` as FieldPath<AlgorithmFormValues>,
                              value ?? ''
                            )
                          }
                        >
                          <SelectTrigger size='sm' className='w-44'>
                            <SelectValue placeholder='选择目标参数' />
                          </SelectTrigger>
                          <SelectContent>
                            {targetOptions.map((option) => (
                              <SelectItem key={option.value} value={option.value}>
                                {option.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}
                    </td>
                    <td className='px-2 py-1.5'>
                      <Select
                        value={form.watch(`${arrayName}.${index}.transformType`)}
                        onValueChange={(value) =>
                          form.setValue(
                            `${arrayName}.${index}.transformType` as FieldPath<AlgorithmFormValues>,
                            value ?? 'none'
                          )
                        }
                      >
                        <SelectTrigger size='sm' className='w-28'>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {transformOptions.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {option.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </td>
                    <td className='px-2 py-1.5'>
                      <div className='flex items-center justify-end'>
                        <Button
                          variant='ghost'
                          size='icon-sm'
                          type='button'
                          aria-label='删除该映射'
                          className='text-destructive'
                          onClick={() => mappings.remove(index)}
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

export function MappingsSection({
  form,
  dimensions,
  categories = [],
}: {
  form: UseFormReturn<AlgorithmFormValues>
  /** 评估维度全量（含子维度；评估映射 target 按 分组/主维度/子维度 展示） */
  dimensions: Dimension[]
  /** 评估维度分类（分类分组组头） */
  categories?: EvaluationCategory[]
}) {
  const deviceParams = useWatch({ control: form.control, name: 'deviceParams' })
  const apiParams = useWatch({ control: form.control, name: 'apiParams' })

  const deviceTargets = deviceParams.map((param) => ({
    value: param.paramCode,
    label: param.paramCode || '（未填）',
  })).filter((option) => option.value)

  const apiTargets = apiParams.map((param) => ({
    value: param.paramCode,
    label: param.paramCode || '（未填）',
  })).filter((option) => option.value)

  const deviceCount = useWatch({ control: form.control, name: 'mappings.device' }).length
  const apiCount = useWatch({ control: form.control, name: 'mappings.api' }).length
  const evaluationCount = useWatch({ control: form.control, name: 'mappings.evaluation' }).length

  return (
    <div className='space-y-3'>
      <MappingCollapsible
        defaultOpen
        title='设备参数映射'
        subtitle='用例参数 → 设备参数'
        count={deviceCount}
      >
        <MappingTable
          form={form}
          arrayName='mappings.device'
          sourceLabel='源参数'
          targetOptions={deviceTargets}
          transformOptions={TRANSFORM_TYPE_OPTIONS}
        />
      </MappingCollapsible>

      <MappingCollapsible
        title='API参数映射'
        subtitle='用例参数 → API参数'
        count={apiCount}
      >
        <MappingTable
          form={form}
          arrayName='mappings.api'
          sourceLabel='源参数'
          targetOptions={apiTargets}
          transformOptions={API_TRANSFORM_TYPE_OPTIONS}
        />
      </MappingCollapsible>

      <MappingCollapsible
        title='评估参数映射'
        subtitle='用例参数/设备输出/API输出 → 评估维度'
        count={evaluationCount}
      >
        <MappingTable
          form={form}
          arrayName='mappings.evaluation'
          sourceLabel='源参数'
          targetOptions={[]}
          transformOptions={TRANSFORM_TYPE_OPTIONS}
          targetSelect={(index) => (
            <DimensionSelect
              dimensions={dimensions}
              categories={categories}
              value={form.watch(`mappings.evaluation.${index}.targetParam`) ?? ''}
              onValueChange={(name) =>
                form.setValue(
                  `mappings.evaluation.${index}.targetParam` as FieldPath<AlgorithmFormValues>,
                  name
                )
              }
              valueOf={(dimension) => dimension.name}
              placeholder='选择评估维度'
              triggerClassName='w-52'
            />
          )}
        />
      </MappingCollapsible>
    </div>
  )
}

function MappingCollapsible({
  defaultOpen = false,
  title,
  subtitle,
  count,
  children,
}: {
  defaultOpen?: boolean
  title: string
  subtitle: string
  count: number
  children: React.ReactNode
}) {
  return (
    <Collapsible defaultOpen={defaultOpen} className='space-y-2'>
      <CollapsibleTrigger className='hover:bg-muted/50 flex w-full items-center justify-between gap-2 rounded-lg border border-border px-3 py-2 text-sm transition-colors'>
        <span className='flex min-w-0 items-center gap-2'>
          <span className='font-medium'>{title}</span>
          <span className='text-muted-foreground hidden text-xs sm:inline'>
            {subtitle}
          </span>
        </span>
        <Badge variant='secondary' className='font-mono text-[11px] tabular-nums'>
          {count} 条映射
        </Badge>
      </CollapsibleTrigger>
      <CollapsibleContent className={cn('pt-1')}>
        {children}
      </CollapsibleContent>
    </Collapsible>
  )
}
