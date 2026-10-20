/**
 * §6.5 参数映射分节（mutate sheet 高级配置折叠区）。
 * 三折叠分区（设备/API/评估），标题带计数 Badge「{n} 条映射」；
 * MappingEditor 对位：源参数 Select → 目标参数 Select + 转换类型 Select，ArrayField 增删行。
 *
 * INT-1030 返工（负责人 2026-10-20「参数映射没照 V9.7.10，仍平铺」）：
 * 评估参数映射加 V9.7.10 同款视图切换「平铺视图 / 评估维度视图」——评估维度视图按
 * 目标评估维度（targetParam=维度名）分组，组头折叠 + 主/子徽章 + 计数，组尾「添加映射」
 * 预填该维度（空行进「未指定维度」组）；默认评估维度视图，彻底告别全平铺。
 */
import { ChevronDown, Folder, Plus, Trash2 } from 'lucide-react'
import { Fragment, useMemo, useState } from 'react'
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
import {
  ToggleGroup,
  ToggleGroupItem,
} from '@/components/ui/toggle-group'
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
}: {
  form: UseFormReturn<AlgorithmFormValues>
  arrayName: MappingArrayName
  sourceLabel: string
  targetOptions: Array<{ value: string; label: string }>
  transformOptions: ReadonlyArray<{ value: string; label: string }>
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

/** 主/子维度徽章样式（照 dimension-select / dimension-picker chip 徽章） */
const mainBadge =
  'bg-primary/20 text-primary inline-flex size-3.5 items-center justify-center rounded-[3px] text-[9px] font-semibold'
const subBadge =
  'bg-muted text-muted-foreground border-border inline-flex size-3.5 items-center justify-center rounded-[3px] border text-[9px] font-semibold'

/** 评估参数映射行（平铺/维度视图共用单元格：源参数 → 目标评估维度 DimensionSelect + 转换类型） */
function EvaluationRow({
  form,
  index,
  dimensions,
  categories,
  sourceOptions,
  onRemove,
}: {
  form: UseFormReturn<AlgorithmFormValues>
  index: number
  dimensions: Dimension[]
  categories: EvaluationCategory[]
  sourceOptions: Array<{ value: string; label: string }>
  onRemove: () => void
}) {
  return (
    <tr className='border-border/50 border-b last:border-b-0'>
      <td className='px-2 py-1.5'>
        <Select
          value={form.watch(`mappings.evaluation.${index}.sourceParam`)}
          onValueChange={(value) =>
            form.setValue(
              `mappings.evaluation.${index}.sourceParam` as FieldPath<AlgorithmFormValues>,
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
      </td>
      <td className='px-2 py-1.5'>
        <Select
          value={form.watch(`mappings.evaluation.${index}.transformType`)}
          onValueChange={(value) =>
            form.setValue(
              `mappings.evaluation.${index}.transformType` as FieldPath<AlgorithmFormValues>,
              value ?? 'none'
            )
          }
        >
          <SelectTrigger size='sm' className='w-28'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TRANSFORM_TYPE_OPTIONS.map((option) => (
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
            onClick={onRemove}
          >
            <Trash2 aria-hidden='true' className='size-3.5' />
          </Button>
        </div>
      </td>
    </tr>
  )
}

/**
 * 评估参数映射表（INT-1030 返工：V9.7.10 视图切换）。
 * 「平铺视图」= 全量平铺表；「评估维度视图」（默认）= 按 targetParam（维度名）分组，
 * 组头折叠 + 主/子徽章 + 计数，组尾「添加映射」预填该维度。空行归「未指定维度」组。
 */
function EvaluationMappingTable({
  form,
  dimensions,
  categories = [],
}: {
  form: UseFormReturn<AlgorithmFormValues>
  /** 评估维度全量（含子维度；组头主/子徽章 + 行内 DimensionSelect） */
  dimensions: Dimension[]
  /** 评估维度分类（分类分组组头） */
  categories?: EvaluationCategory[]
}) {
  const mappings = useFieldArray({ control: form.control, name: 'mappings.evaluation' })
  const sourceOptions = SourceOptions({ form })
  const [viewMode, setViewMode] = useState<'flat' | 'dimension'>('dimension')
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

  const addEmpty = (targetParam = '') =>
    mappings.append({
      key: `mappings.evaluation-${Date.now()}-${mappings.fields.length}`,
      sourceParam: '',
      targetParam,
      transformType: 'none',
    })

  const toggleCollapsed = (key: string) => {
    const next = new Set(collapsed)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    setCollapsed(next)
  }

  /** 维度名 → 维度（组头主/子徽章、子维度父名提示） */
  const dimByName = useMemo(
    () => new Map(dimensions.map((d) => [d.name, d])),
    [dimensions]
  )

  /** 按 targetParam（维度名）分组；空 targetParam 归「未指定维度」；组序照维度名中文排序 */
  const groups: Array<[string, Array<(typeof mappings.fields)[number]>]> = []
  const groupOf = new Map<string, Array<(typeof mappings.fields)[number]>>()
  for (const field of mappings.fields) {
    const key = field.targetParam || ''
    if (!groupOf.has(key)) {
      groupOf.set(key, [])
      groups.push([key, groupOf.get(key)!])
    }
    groupOf.get(key)!.push(field)
  }
  groups.sort(([a], [b]) =>
    (a || '未指定维度').localeCompare(b || '未指定维度', 'zh-Hans-CN')
  )

  return (
    <div className='space-y-2'>
      {/* V9.7.10 视图切换（仅评估映射）：平铺视图 / 评估维度视图 */}
      <div className='flex items-center justify-between gap-2'>
        <ToggleGroup
          variant='outline'
          size='sm'
          spacing={0}
          value={[viewMode]}
          aria-label='评估映射视图'
          onValueChange={(values) => {
            const next = values[0]
            if (next === 'flat' || next === 'dimension') setViewMode(next)
          }}
        >
          <ToggleGroupItem value='flat'>平铺视图</ToggleGroupItem>
          <ToggleGroupItem value='dimension'>评估维度视图</ToggleGroupItem>
        </ToggleGroup>
        {viewMode === 'flat' && (
          <Button variant='outline' size='sm' type='button' onClick={() => addEmpty()}>
            <Plus aria-hidden='true' />
            添加映射
          </Button>
        )}
      </div>

      <div className='bg-card ring-foreground/10 overflow-hidden rounded-lg ring-1'>
        <div className='overflow-x-auto'>
          <table className='w-full min-w-0 text-[13px]'>
            <thead>
              <tr className='bg-[var(--table-header)] text-xs'>
                <th className='px-3 py-2 text-left font-medium'>源参数</th>
                <th className='px-3 py-2 text-left font-medium'>目标评估维度</th>
                <th className='px-3 py-2 text-left font-medium'>转换类型</th>
                <th className='w-10 px-3 py-2 text-right font-medium'>操作</th>
              </tr>
            </thead>
            <tbody>
              {mappings.fields.length === 0 ? (
                <tr>
                  <td colSpan={4} className='px-3 py-5 text-center'>
                    <Button variant='outline' size='sm' type='button' onClick={() => addEmpty()}>
                      <Plus aria-hidden='true' />
                      添加映射
                    </Button>
                  </td>
                </tr>
              ) : viewMode === 'flat' ? (
                mappings.fields.map((field, index) => (
                  <EvaluationRow
                    key={field.key}
                    form={form}
                    index={index}
                    dimensions={dimensions}
                    categories={categories}
                    sourceOptions={sourceOptions}
                    onRemove={() => mappings.remove(index)}
                  />
                ))
              ) : (
                groups.map(([key, rows]) => {
                  const dim = dimByName.get(key)
                  const isCollapsed = collapsed.has(key)
                  return (
                    <Fragment key={key}>
                      {/* 维度分组组头：折叠 + 主/子徽章 + 计数 */}
                      <tr className='bg-muted/40 border-border/50 border-b'>
                        <td colSpan={4} className='px-0 py-0'>
                          <button
                            type='button'
                            onClick={() => toggleCollapsed(key)}
                            aria-expanded={!isCollapsed}
                            className='hover:bg-muted/60 flex w-full items-center gap-1.5 px-3 py-2 text-left text-xs font-medium transition-colors'
                          >
                            <ChevronDown
                              aria-hidden='true'
                              className={cn(
                                'size-3.5 shrink-0 transition-transform',
                                isCollapsed && '-rotate-90'
                              )}
                            />
                            <Folder
                              aria-hidden='true'
                              className='text-muted-foreground size-3.5 shrink-0'
                            />
                            <span className='truncate'>{key || '未指定维度'}</span>
                            {dim ? (
                              dim.parentDimensionId ? (
                                <>
                                  <span className='text-muted-foreground/70 text-[11px] font-normal'>
                                    （
                                    {dimensions.find(
                                      (p) => String(p.id) === String(dim.parentDimensionId)
                                    )?.name ?? ''}
                                    ）
                                  </span>
                                  <span className={subBadge}>子</span>
                                </>
                              ) : (
                                <span className={mainBadge}>主</span>
                              )
                            ) : key === '' ? (
                              <span className='text-muted-foreground text-[11px] font-normal'>
                                （未指定）
                              </span>
                            ) : (
                              /* 存量已删除维度名兜底（数据保全，与 DimensionSelect 回退同口径） */
                              <span className='text-muted-foreground text-[11px] font-normal'>
                                （已删除维度）
                              </span>
                            )}
                            <span className='bg-muted text-muted-foreground ml-auto shrink-0 rounded-full px-1.5 text-[10px] tabular-nums'>
                              {rows.length} 条
                            </span>
                          </button>
                        </td>
                      </tr>
                      {!isCollapsed && (
                        <>
                          {rows.map((field) => {
                            const index = mappings.fields.findIndex((f) => f.key === field.key)
                            return (
                              <EvaluationRow
                                key={field.key}
                                form={form}
                                index={index}
                                dimensions={dimensions}
                                categories={categories}
                                sourceOptions={sourceOptions}
                                onRemove={() => mappings.remove(index)}
                              />
                            )
                          })}
                          {/* 组尾「添加映射」：预填该维度 */}
                          <tr className='border-border/50 border-b last:border-b-0'>
                            <td colSpan={4} className='px-3 py-1.5'>
                              <Button
                                variant='ghost'
                                size='sm'
                                type='button'
                                onClick={() => addEmpty(key)}
                                className='text-primary h-auto px-1 py-0.5 text-xs font-medium'
                              >
                                <Plus aria-hidden='true' className='size-3.5' />
                                添加映射
                              </Button>
                            </td>
                          </tr>
                        </>
                      )}
                    </Fragment>
                  )
                })
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
        <EvaluationMappingTable
          form={form}
          dimensions={dimensions}
          categories={categories}
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
