/**
 * §6.5 参数映射分节（mutate sheet 高级配置折叠区）。
 * INT-1160 返工（负责人 2026-10-21「设备/API/评估参数映射照 V9.7.10 重做」）：
 * - 设备/API 6 列「源参数代码 / 源参数名称 / 目标参数代码 / 目标参数名称 / 转换 / 操作」；
 *   评估 7 列「来源 / 源参数代码 / 源参数名称 / 目标评估维度 / 目标参数 / 转换 / 操作」。
 * - 公共工具栏：搜索映射 + 转换徽章筛选 + 平铺/分组视图切换 + 分页（平铺 >10 条）；
 *   评估另加 来源 / 评估维度 徽章筛选。
 * - 分组视图：设备/API 按源参数集合（用例参数·通用/API/E2E + 参考参数）、评估按目标维度
 *   （组头折叠 + 主/子徽章 + 计数 + 组尾「添加映射」预填维度；空行归「未指定维度」）。
 * - 数据模型补齐 id/source/sourceDirection/paramName/dimensionId/dimensionName/targetParamName
 *   （INT-1160 范围 1），评估来源可选 用例参数/用例配置/参考参数/设备输出/API输出，
 *   目标参数经 /algorithm/dimension-params 拉维度内参数。
 * 行值一律经 useWatch 读 form 值（useFieldArray.fields 不随 setValue 更新，只作 key/增删锚点）。
 */
import { ChevronDown, Folder, Plus, Search, Trash2 } from 'lucide-react'
import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { type FieldPath, type UseFormReturn } from 'react-hook-form'
import { useFieldArray, useWatch } from 'react-hook-form'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Input } from '@/components/ui/input'
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
import type { DimensionParam } from '@/domain/models/algorithmConfig'
import type { AlgorithmFormValues, MappingRow } from '@/features/algorithm-config/types'
import { fetchDimensionParams } from '@/infrastructure/api/algorithm-config-api'
import { DimensionSelect } from './dimension-select'
import { CONTAINED_TABLE_CLASS } from './table-containment'
import {
  API_TRANSFORM_TYPE_OPTIONS,
  TRANSFORM_TYPE_OPTIONS,
} from '@/features/algorithm-config/constants'

/** 评估来源选项（V9.7.10 MappingEditor sourceOptions；后端 VALID_SOURCES 含 case_config） */
const EVALUATION_SOURCE_OPTIONS = [
  { value: 'case', label: '用例参数' },
  { value: 'case_config', label: '用例配置' },
  { value: 'reference', label: '参考参数' },
  { value: 'device', label: '设备输出' },
  { value: 'api', label: 'API输出' },
] as const

/** 用例配置(config.rounds)可映射结构性字段：评估时从 test_case.config.rounds 按轮读取（V9.7.10 同款） */
const CASE_CONFIG_FIELD_PRESETS = [{ code: 'audios', name: '被播放音频' }] as const

type ParamOption = { value: string; label: string }

/** 源参数选项（设备/API 共用：用例参数 + 参考参数；评估按 source 取对应集合） */
function buildSourceOptions(
  caseParams: Array<{ paramCode: string; paramName?: string }>,
  referenceParams: Array<{ code: string; name?: string }>
): ParamOption[] {
  return [
    ...caseParams.map((param) => ({
      value: param.paramCode,
      label: `${param.paramCode} · ${param.paramName || '（未填名称）'}`,
    })),
    ...referenceParams.map((param) => ({
      value: param.code,
      label: `${param.code} · ${param.name || '（未填名称）'}`,
    })),
  ].filter((option) => option.value)
}

/** 按 code 取参数名（caseParams / deviceParams 走 paramCode/paramName；referenceParams 走 code/name） */
function paramNameByCode(
  list: Array<{ paramCode?: string; paramName?: string; code?: string; name?: string }>,
  code: string
): string {
  if (!code) return ''
  const item = list.find((p) => (p.paramCode ?? p.code) === code)
  return item?.paramName ?? item?.name ?? ''
}

/* ───────────────────────── 行级基础单元格 ───────────────────────── */

function MappingSelect({
  value,
  onValueChange,
  options,
  placeholder = '选择参数',
  className,
  disabled = false,
}: {
  value: string
  onValueChange: (value: string) => void
  options: ReadonlyArray<ParamOption>
  placeholder?: string
  className?: string
  disabled?: boolean
}) {
  return (
    <Select value={value} onValueChange={(next) => onValueChange(next ?? '')} disabled={disabled}>
      <SelectTrigger size='sm' className={className}>
        {/* 显式解析选项标签（照 dimension-select 口径）：命中选项显示中文标签，未命中回退原值（数据保全） */}
        <SelectValue placeholder={placeholder}>
          {value ? options.find((o) => o.value === value)?.label ?? value : placeholder}
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        {options.length === 0 ? (
          <p className='text-muted-foreground px-3 py-2 text-center text-xs'>暂无可用选项</p>
        ) : (
          options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))
        )}
      </SelectContent>
    </Select>
  )
}

function TransformSelect({
  value,
  onValueChange,
  options,
}: {
  value: string
  onValueChange: (value: string) => void
  options: ReadonlyArray<{ value: string; label: string }>
}) {
  return (
    <MappingSelect
      value={value}
      onValueChange={onValueChange}
      options={options.map((o) => ({ value: o.value, label: o.label }))}
      placeholder='选择转换'
      className='w-28'
    />
  )
}

function DeleteButton({ onClick }: { onClick: () => void }) {
  return (
    <Button
      variant='ghost'
      size='icon-sm'
      type='button'
      aria-label='删除该映射'
      className='text-destructive'
      onClick={onClick}
    >
      <Trash2 aria-hidden='true' className='size-3.5' />
    </Button>
  )
}

/** 只读参数名称单元格（代码已知但名称为空时回退显示代码，V9.7.10 param-name-cell 口径） */
function ParamNameCell({ name, code }: { name: string; code: string }) {
  return <span className='text-muted-foreground text-[12px]'>{name || code || '—'}</span>
}

/* ───────────────────────── 判重（V9.7.10 唯一约束对齐） ───────────────────────── */

/** 判重键：评估 = (source, sourceParam, dimensionId)；设备/API = (节类型, sourceParam) */
function findDuplicateIndex(
  rows: Array<{ source?: string; sourceParam: string; dimensionId?: string }>,
  index: number,
  section: 'device' | 'api' | 'evaluation'
): number {
  const current = rows[index]
  if (!current) return -1
  const src = section === 'evaluation' ? current.source || 'case' : section
  if (!src || !current.sourceParam) return -1
  const dimKey = current.dimensionId || ''
  for (let i = 0; i < rows.length; i++) {
    if (i === index) continue
    const other = rows[i]
    const otherSrc = section === 'evaluation' ? other.source || 'case' : section
    if (otherSrc !== src) continue
    if (other.sourceParam !== current.sourceParam) continue
    if ((other.dimensionId || '') !== dimKey) continue
    return i
  }
  return -1
}

function warnDuplicate(sourceLabel: string, sourceParam: string, dimensionLabel: string) {
  toast.warning(
    `映射已存在：来源=${sourceLabel}，源参数=${sourceParam}${dimensionLabel ? `，维度=${dimensionLabel}` : ''}，同一来源+源参数+维度不允许重复`
  )
}

/* ───────────────────────── 工具栏公共件 ───────────────────────── */

function MappingSearch({
  value,
  onChange,
}: {
  value: string
  onChange: (value: string) => void
}) {
  return (
    <div className='relative min-w-0 basis-40'>
      <Search
        aria-hidden='true'
        className='text-muted-foreground absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2'
      />
      <Input
        aria-label='搜索映射'
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder='搜索映射...'
        className='h-8 pl-8'
      />
    </div>
  )
}

/** 徽章筛选（V9.7.10 BadgeFilter 对位）：单选 chips，「全部」+ 选项；点已选选项回到全部 */
function MappingBadgeFilter({
  title,
  options,
  value,
  onValueChange,
  allLabel,
}: {
  title: string
  options: ReadonlyArray<{ value: string; label: string }>
  value: string
  onValueChange: (value: string) => void
  allLabel: string
}) {
  const chip = (active: boolean) =>
    cn(
      'h-6 shrink-0 rounded-full border px-2.5 text-[11px] transition-colors',
      active
        ? 'border-primary/30 bg-primary/10 text-primary font-medium'
        : 'border-border text-muted-foreground hover:bg-muted'
    )
  return (
    <div className='flex min-w-0 items-center gap-1.5'>
      <span className='text-muted-foreground shrink-0 text-xs'>{title}</span>
      <div className='flex flex-wrap items-center gap-1'>
        <button
          type='button'
          className={chip(value === 'all')}
          onClick={() => onValueChange('all')}
        >
          {allLabel}
        </button>
        {options.map((option) => (
          <button
            key={option.value}
            type='button'
            className={chip(value === option.value)}
            onClick={() => onValueChange(value === option.value ? 'all' : option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  )
}

/** 平铺视图分页（>10 条显示；V9.7.10 PaginationComponent 对位） */
function MappingPagination({
  total,
  page,
  pageSize,
  onPageChange,
  onPageSizeChange,
}: {
  total: number
  page: number
  pageSize: number
  onPageChange: (page: number) => void
  onPageSizeChange: (pageSize: number) => void
}) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const safePage = Math.min(Math.max(1, page), pageCount)
  return (
    <div className='flex flex-wrap items-center justify-end gap-2 text-xs'>
      <span className='text-muted-foreground tabular-nums'>共 {total} 条</span>
      <Select
        value={String(pageSize)}
        onValueChange={(value) => {
          onPageSizeChange(Number(value ?? 10))
          onPageChange(1)
        }}
      >
        <SelectTrigger size='sm' className='h-8 w-[84px]' aria-label='每页条数'>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {[10, 20, 50].map((size) => (
            <SelectItem key={size} value={String(size)}>
              {size} 条/页
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <div className='flex items-center gap-1'>
        <Button
          variant='outline'
          size='sm'
          className='h-7 px-2'
          disabled={safePage <= 1}
          onClick={() => onPageChange(safePage - 1)}
        >
          上一页
        </Button>
        <span className='text-muted-foreground px-1 tabular-nums'>
          {safePage} / {pageCount}
        </span>
        <Button
          variant='outline'
          size='sm'
          className='h-7 px-2'
          disabled={safePage >= pageCount}
          onClick={() => onPageChange(safePage + 1)}
        >
          下一页
        </Button>
      </div>
    </div>
  )
}

/** 主/子维度徽章样式（照 dimension-select / dimension-picker chip 徽章） */
const mainBadge =
  'bg-primary/20 text-primary inline-flex size-3.5 items-center justify-center rounded-[3px] text-[9px] font-semibold'
const subBadge =
  'bg-muted text-muted-foreground border-border inline-flex size-3.5 items-center justify-center rounded-[3px] border text-[9px] font-semibold'

/* ───────────────────────── 分组组头 / 组尾（设备/API 与评估共用结构） ───────────────────────── */

function GroupHeaderButton({
  name,
  badge,
  hint,
  count,
  collapsed,
  onToggle,
}: {
  name: string
  badge?: React.ReactNode
  hint?: string
  count: number
  collapsed: boolean
  onToggle: () => void
}) {
  return (
    <button
      type='button'
      onClick={onToggle}
      aria-expanded={!collapsed}
      className='hover:bg-muted/60 flex w-full items-center gap-1.5 px-3 py-2 text-left text-xs font-medium transition-colors'
    >
      <ChevronDown
        aria-hidden='true'
        className={cn('size-3.5 shrink-0 transition-transform', collapsed && '-rotate-90')}
      />
      <Folder aria-hidden='true' className='text-muted-foreground size-3.5 shrink-0' />
      <span className='truncate'>{name}</span>
      {badge}
      {hint && <span className='text-muted-foreground/70 text-[11px] font-normal'>{hint}</span>}
      <span className='bg-muted text-muted-foreground ml-auto shrink-0 rounded-full px-1.5 text-[10px] tabular-nums'>
        {count} 条
      </span>
    </button>
  )
}

function GroupAddRow({ colSpan, onClick }: { colSpan: number; onClick: () => void }) {
  return (
    <tr className='border-border/50 border-b last:border-b-0'>
      <td colSpan={colSpan} className='px-3 py-1.5'>
        <Button
          variant='ghost'
          size='sm'
          type='button'
          onClick={onClick}
          className='text-primary h-auto px-1 py-0.5 text-xs font-medium'
        >
          <Plus aria-hidden='true' className='size-3.5' />
          添加映射
        </Button>
      </td>
    </tr>
  )
}

/* ───────────────────────── 设备/API 参数映射分节 ───────────────────────── */

/** 设备/API 分组键：源参数所属集合（用例参数·scope / 参考参数 / 未分组） */
type DeviceApiGroupKey = 'case-common' | 'case-api' | 'case-e2e' | 'reference' | 'unknown'

const DEVICE_API_GROUP_ORDER: DeviceApiGroupKey[] = [
  'case-common',
  'case-api',
  'case-e2e',
  'reference',
  'unknown',
]

const DEVICE_API_GROUP_LABEL: Record<DeviceApiGroupKey, string> = {
  'case-common': '用例参数 · 通用',
  'case-api': '用例参数 · API',
  'case-e2e': '用例参数 · E2E',
  reference: '参考参数',
  unknown: '未分组',
}

function deviceApiGroupKey(
  sourceParam: string,
  caseParams: Array<{ paramCode: string; scope: string }>,
  referenceParams: Array<{ code: string }>
): DeviceApiGroupKey {
  if (!sourceParam) return 'unknown'
  const caseParam = caseParams.find((p) => p.paramCode === sourceParam)
  if (caseParam) {
    if (caseParam.scope === 'api') return 'case-api'
    if (caseParam.scope === 'e2e') return 'case-e2e'
    return 'case-common'
  }
  if (referenceParams.some((p) => p.code === sourceParam)) return 'reference'
  return 'unknown'
}

function DeviceApiMappingSection({
  form,
  arrayName,
  sectionLabel,
  caseParams,
  referenceParams,
  targetParams,
  transformOptions,
}: {
  form: UseFormReturn<AlgorithmFormValues>
  arrayName: 'mappings.device' | 'mappings.api'
  sectionLabel: string
  /** 用例参数（源参数选项 + 分组键 scope） */
  caseParams: Array<{ paramCode: string; paramName?: string; scope: string }>
  /** 参考参数（源参数选项 + 分组键） */
  referenceParams: Array<{ code: string; name?: string }>
  /** 目标参数（设备参数 / API 参数） */
  targetParams: Array<{ paramCode: string; paramName?: string }>
  transformOptions: ReadonlyArray<{ value: string; label: string }>
}) {
  const mappings = useFieldArray({ control: form.control, name: arrayName })
  /** 行实时值（setValue 后可读；fields 只作 key/增删锚点） */
  const liveRows = useWatch({ control: form.control, name: arrayName }) as MappingRow[] | undefined
  const rows = liveRows ?? []
  const [keyword, setKeyword] = useState('')
  const [transformFilter, setTransformFilter] = useState('all')
  const [viewMode, setViewMode] = useState<'flat' | 'group'>('flat')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

  const sourceOptions = useMemo(
    () => buildSourceOptions(caseParams, referenceParams),
    [caseParams, referenceParams]
  )
  const targetOptions = useMemo(
    () =>
      targetParams
        .map((param) => ({
          value: param.paramCode,
          label: `${param.paramCode} · ${param.paramName || '（未填名称）'}`,
        }))
        .filter((option) => option.value),
    [targetParams]
  )

  /** 源参数名（按 code 查 用例/参考；查不到回退 paramName 存量值） */
  const sourceName = (row: MappingRow) =>
    paramNameByCode(caseParams, row.sourceParam) ||
    paramNameByCode(referenceParams, row.sourceParam) ||
    row.paramName ||
    ''
  /** 目标参数名（按 code 查目标参数表；查不到回退 targetParamName 存量值） */
  const targetName = (row: MappingRow) =>
    paramNameByCode(targetParams, row.targetParam) || row.targetParamName || ''

  const section = arrayName === 'mappings.device' ? ('device' as const) : ('api' as const)

  const addEmpty = () =>
    mappings.append({
      key: `${arrayName}-${Date.now()}-${rows.length}`,
      source: 'case',
      sourceDirection: 'output',
      sourceParam: '',
      paramName: '',
      targetParam: '',
      targetParamName: '',
      transformType: 'none',
    })

  const toggleCollapsed = (key: string) => {
    const next = new Set(collapsed)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    setCollapsed(next)
  }

  /**
   * 源参数变更：写入 sourceParam + 回填 paramName + 判重提示（V9.7.10 handleSourceChange 口径）。
   * 判重读 form.getValues() 实时值——setValue 后 useWatch 快照要到下轮渲染才更新，
   * 用快照判重会漏掉「编辑存量完备行 sourceParam 制造重复」的变更（INT-1160 返工 P2）。
   */
  const handleSourceChange = (index: number, value: string) => {
    form.setValue(`${arrayName}.${index}.sourceParam` as FieldPath<AlgorithmFormValues>, value ?? '')
    const name =
      paramNameByCode(caseParams, value ?? '') || paramNameByCode(referenceParams, value ?? '')
    form.setValue(`${arrayName}.${index}.paramName` as FieldPath<AlgorithmFormValues>, name)
    const liveRows = (form.getValues(arrayName) ?? []) as MappingRow[]
    const dupIndex = findDuplicateIndex(liveRows, index, section)
    if (dupIndex >= 0) warnDuplicate(sectionLabel, value || '', '')
  }

  /** 目标参数变更（V9.7.10 handleTargetChange 口径：判重提示不阻塞；同样读实时值） */
  const handleTargetChange = (index: number, value: string) => {
    form.setValue(`${arrayName}.${index}.targetParam` as FieldPath<AlgorithmFormValues>, value ?? '')
    form.setValue(
      `${arrayName}.${index}.targetParamName` as FieldPath<AlgorithmFormValues>,
      paramNameByCode(targetParams, value ?? '')
    )
    const liveRows = (form.getValues(arrayName) ?? []) as MappingRow[]
    const dupIndex = findDuplicateIndex(liveRows, index, section)
    if (dupIndex >= 0) warnDuplicate(sectionLabel, liveRows[index]?.sourceParam || '', '')
  }

  /** 搜索 + 转换筛选后的行 */
  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase()
    return rows.filter((row) => {
      if (transformFilter !== 'all' && row.transformType !== transformFilter) return false
      if (!kw) return true
      return (
        (row.sourceParam || '').toLowerCase().includes(kw) ||
        (sourceName(row) || '').toLowerCase().includes(kw) ||
        (row.targetParam || '').toLowerCase().includes(kw) ||
        (targetName(row) || '').toLowerCase().includes(kw)
      )
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, keyword, transformFilter, caseParams, referenceParams, targetParams])

  /** 分组视图：按源参数集合分组（组序固定）；平铺视图：过滤 + 分页切片 */
  const groups = useMemo(() => {
    if (viewMode !== 'group') return []
    const map = new Map<DeviceApiGroupKey, MappingRow[]>()
    DEVICE_API_GROUP_ORDER.forEach((key) => map.set(key, []))
    for (const row of filtered) {
      const key = deviceApiGroupKey(row.sourceParam, caseParams, referenceParams)
      map.get(key)!.push(row)
    }
    return Array.from(map.entries()).filter(([, groupRows]) => groupRows.length > 0)
  }, [viewMode, filtered, caseParams, referenceParams])

  const pageRows = useMemo(() => {
    if (viewMode === 'group') return []
    const start = (page - 1) * pageSize
    return filtered.slice(start, start + pageSize)
  }, [viewMode, filtered, page, pageSize])

  // 过滤条件/视图切换回到第一页
  useEffect(() => {
    setPage(1)
  }, [keyword, transformFilter, viewMode])

  const colspan = 6
  /** 行索引锚点（fields 为 key 真源，rows 实时值同序） */
  const indexOf = (key: string) => mappings.fields.findIndex((f) => f.key === key)

  return (
    <div className='space-y-2'>
      {/* 公共工具栏：搜索 + 转换徽章筛选 + 平铺/分组切换 + 添加 */}
      <div className='flex flex-wrap items-center gap-2'>
        <MappingSearch value={keyword} onChange={setKeyword} />
        <MappingBadgeFilter
          title='转换'
          options={transformOptions}
          value={transformFilter}
          onValueChange={setTransformFilter}
          allLabel='全部转换'
        />
        <ToggleGroup
          variant='outline'
          size='sm'
          spacing={0}
          value={[viewMode]}
          aria-label='映射视图'
          onValueChange={(values) => {
            const next = values[0]
            if (next === 'flat' || next === 'group') setViewMode(next)
          }}
        >
          <ToggleGroupItem value='flat'>平铺视图</ToggleGroupItem>
          <ToggleGroupItem value='group'>分组视图</ToggleGroupItem>
        </ToggleGroup>
        <Button
          variant='outline'
          size='sm'
          type='button'
          className='ml-auto'
          onClick={addEmpty}
        >
          <Plus aria-hidden='true' />
          添加映射
        </Button>
      </div>

      <div className='bg-card ring-foreground/10 overflow-hidden rounded-lg ring-1'>
        <div className='overflow-x-auto'>
          <table className={`w-full min-w-0 text-[13px] ${CONTAINED_TABLE_CLASS}`}>
            <thead>
              <tr className='bg-[var(--table-header)] text-xs'>
                <th className='px-3 py-2 text-left font-medium'>源参数代码</th>
                <th className='px-3 py-2 text-left font-medium'>源参数名称</th>
                <th className='px-3 py-2 text-left font-medium'>目标参数代码</th>
                <th className='px-3 py-2 text-left font-medium'>目标参数名称</th>
                <th className='px-3 py-2 text-left font-medium'>转换</th>
                <th className='w-10 px-3 py-2 text-right font-medium'>操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={colspan} className='text-muted-foreground px-3 py-5 text-center'>
                    暂无映射，点击「添加映射」新增
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={colspan} className='text-muted-foreground px-3 py-5 text-center'>
                    无匹配映射
                  </td>
                </tr>
              ) : viewMode === 'flat' ? (
                pageRows.map((row) => {
                  const index = indexOf(row.key)
                  return (
                    <DeviceApiRow
                      key={row.key}
                      row={row}
                      index={index}
                      sourceOptions={sourceOptions}
                      targetOptions={targetOptions}
                      transformOptions={transformOptions}
                      sourceName={sourceName(row)}
                      targetName={targetName(row)}
                      onSourceChange={handleSourceChange}
                      onTargetChange={handleTargetChange}
                      onTransformChange={(value) =>
                        form.setValue(
                          `${arrayName}.${index}.transformType` as FieldPath<AlgorithmFormValues>,
                          value ?? 'none'
                        )
                      }
                      onRemove={() => mappings.remove(index)}
                    />
                  )
                })
              ) : (
                groups.map(([key, groupRows]) => {
                  const isCollapsed = collapsed.has(key)
                  return (
                    <Fragment key={key}>
                      <tr className='bg-muted/40 border-border/50 border-b'>
                        <td colSpan={colspan} className='px-0 py-0'>
                          <GroupHeaderButton
                            name={DEVICE_API_GROUP_LABEL[key]}
                            count={groupRows.length}
                            collapsed={isCollapsed}
                            onToggle={() => toggleCollapsed(key)}
                          />
                        </td>
                      </tr>
                      {!isCollapsed &&
                        groupRows.map((row) => {
                          const index = indexOf(row.key)
                          return (
                            <DeviceApiRow
                              key={row.key}
                              row={row}
                              index={index}
                              sourceOptions={sourceOptions}
                              targetOptions={targetOptions}
                              transformOptions={transformOptions}
                              sourceName={sourceName(row)}
                              targetName={targetName(row)}
                              onSourceChange={handleSourceChange}
                              onTargetChange={handleTargetChange}
                              onTransformChange={(value) =>
                                form.setValue(
                                  `${arrayName}.${index}.transformType` as FieldPath<AlgorithmFormValues>,
                                  value ?? 'none'
                                )
                              }
                              onRemove={() => mappings.remove(index)}
                            />
                          )
                        })}
                      {!isCollapsed && <GroupAddRow colSpan={colspan} onClick={addEmpty} />}
                    </Fragment>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {viewMode === 'flat' && filtered.length > pageSize && (
        <MappingPagination
          total={filtered.length}
          page={page}
          pageSize={pageSize}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
        />
      )}
    </div>
  )
}

/** 设备/API 映射行（6 列） */
function DeviceApiRow({
  row,
  index,
  sourceOptions,
  targetOptions,
  transformOptions,
  sourceName,
  targetName,
  onSourceChange,
  onTargetChange,
  onTransformChange,
  onRemove,
}: {
  row: MappingRow
  index: number
  sourceOptions: ParamOption[]
  targetOptions: ParamOption[]
  transformOptions: ReadonlyArray<{ value: string; label: string }>
  sourceName: string
  targetName: string
  onSourceChange: (index: number, value: string) => void
  onTargetChange: (index: number, value: string) => void
  onTransformChange: (value: string) => void
  onRemove: () => void
}) {
  return (
    <tr className='border-border/50 border-b last:border-b-0'>
      <td className='px-2 py-1.5'>
        <MappingSelect
          value={row.sourceParam}
          onValueChange={(value) => onSourceChange(index, value)}
          options={sourceOptions}
          className='w-44'
        />
      </td>
      <td className='px-2 py-1.5'>
        <ParamNameCell name={sourceName} code={row.sourceParam} />
      </td>
      <td className='px-2 py-1.5'>
        <MappingSelect
          value={row.targetParam}
          onValueChange={(value) => onTargetChange(index, value)}
          options={targetOptions}
          className='w-44'
        />
      </td>
      <td className='px-2 py-1.5'>
        <ParamNameCell name={targetName} code={row.targetParam} />
      </td>
      <td className='px-2 py-1.5'>
        <TransformSelect value={row.transformType} onValueChange={onTransformChange} options={transformOptions} />
      </td>
      <td className='px-2 py-1.5'>
        <div className='flex items-center justify-end'>
          <DeleteButton onClick={onRemove} />
        </div>
      </td>
    </tr>
  )
}

/* ───────────────────────── 评估参数映射分节 ───────────────────────── */

/** 评估分组键：dimensionId（空归「未指定维度」；兼容存量按维度名兜底） */
function evalGroupKey(row: MappingRow): string {
  if (row.dimensionId) return String(row.dimensionId)
  return row.dimensionName ? `name:${row.dimensionName}` : '__none__'
}

function evalGroupName(
  key: string,
  dimensions: Dimension[],
  dimensionNameById: Map<string, string>
): string {
  if (key === '__none__') return '未指定维度'
  if (key.startsWith('name:')) return key.slice(5)
  const dim = dimensions.find((d) => String(d.id) === key)
  return dim?.name || dimensionNameById.get(key) || `维度(${key})`
}

/** 维度内目标参数缓存（/algorithm/dimension-params；按 dimensionId 惰性拉取） */
function useDimensionParamsMap(dimensionIds: string[]): Record<string, DimensionParam[]> {
  const [cache, setCache] = useState<Record<string, DimensionParam[]>>({})
  const loadedRef = useRef<Set<string>>(new Set())
  const idsKey = dimensionIds.join('|')
  useEffect(() => {
    const ids = [...new Set(dimensionIds.filter((id) => id && !loadedRef.current.has(id)))]
    if (ids.length === 0) return
    let cancelled = false
    for (const id of ids) {
      loadedRef.current.add(id)
      fetchDimensionParams(Number(id))
        .then((params) => {
          if (!cancelled) setCache((c) => ({ ...c, [id]: params }))
        })
        .catch(() => {
          if (!cancelled) setCache((c) => ({ ...c, [id]: [] }))
        })
    }
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idsKey])
  return cache
}

function EvaluationMappingSection({
  form,
  dimensions,
  categories = [],
}: {
  form: UseFormReturn<AlgorithmFormValues>
  dimensions: Dimension[]
  categories?: EvaluationCategory[]
}) {
  const mappings = useFieldArray({ control: form.control, name: 'mappings.evaluation' })
  const liveRows = useWatch({ control: form.control, name: 'mappings.evaluation' }) as
    | MappingRow[]
    | undefined
  const rows = liveRows ?? []
  const caseParams = useWatch({ control: form.control, name: 'caseParams' })
  const referenceParams = useWatch({ control: form.control, name: 'referenceParams' })
  const deviceParams = useWatch({ control: form.control, name: 'deviceParams' })
  const apiParams = useWatch({ control: form.control, name: 'apiParams' })

  const [keyword, setKeyword] = useState('')
  const [sourceFilter, setSourceFilter] = useState('all')
  const [dimensionFilter, setDimensionFilter] = useState('all')
  const [transformFilter, setTransformFilter] = useState('all')
  const [viewMode, setViewMode] = useState<'flat' | 'dimension'>('dimension')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

  /** 当前行引用的维度 id 集（预加载维度参数） */
  const dimensionIds = useMemo(() => rows.map((row) => row.dimensionId || ''), [rows])
  const dimensionParamsMap = useDimensionParamsMap(dimensionIds)

  /** 维度 id → 维度（组头主/子徽章、子维度父名） */
  const dimById = useMemo(
    () => new Map(dimensions.map((d) => [String(d.id), d])),
    [dimensions]
  )
  /** 行内 dimensionName 兜底（存量/已删除维度） */
  const dimensionNameById = useMemo(() => {
    const map = new Map<string, string>()
    for (const row of rows) {
      if (row.dimensionId && row.dimensionName && !map.has(String(row.dimensionId))) {
        map.set(String(row.dimensionId), row.dimensionName)
      }
    }
    return map
  }, [rows])

  /** 维度筛选选项（全量维度 + 已删除维度存量行兜底） */
  const dimensionFilterOptions = useMemo(() => {
    const seen = new Set<string>()
    const options: ParamOption[] = []
    for (const dim of dimensions) {
      const key = String(dim.id)
      if (seen.has(key)) continue
      seen.add(key)
      options.push({ value: key, label: dim.name })
    }
    for (const row of rows) {
      if (!row.dimensionId || seen.has(String(row.dimensionId))) continue
      const key = String(row.dimensionId)
      seen.add(key)
      options.push({ value: key, label: row.dimensionName || `维度(${key})` })
    }
    return options
  }, [dimensions, rows])

  const addEmpty = (dimensionId = '', dimensionName = '') =>
    mappings.append({
      key: `mappings.evaluation-${Date.now()}-${rows.length}`,
      source: 'case',
      sourceDirection: 'output',
      sourceParam: '',
      paramName: '',
      dimensionId,
      dimensionName,
      targetParam: '',
      targetParamName: '',
      transformType: 'none',
    })

  const toggleCollapsed = (key: string) => {
    const next = new Set(collapsed)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    setCollapsed(next)
  }

  /** 来源变更（V9.7.10 handleSourceTypeChange：清 source_param/param_name；case/case_config 清维度） */
  const handleSourceChange = (index: number, value: string) => {
    form.setValue(`mappings.evaluation.${index}.source` as FieldPath<AlgorithmFormValues>, value ?? 'case')
    form.setValue(`mappings.evaluation.${index}.sourceParam` as FieldPath<AlgorithmFormValues>, '')
    form.setValue(`mappings.evaluation.${index}.paramName` as FieldPath<AlgorithmFormValues>, '')
    if (value === 'case' || value === 'case_config') {
      form.setValue(`mappings.evaluation.${index}.dimensionId` as FieldPath<AlgorithmFormValues>, '')
      form.setValue(`mappings.evaluation.${index}.dimensionName` as FieldPath<AlgorithmFormValues>, '')
      form.setValue(`mappings.evaluation.${index}.targetParam` as FieldPath<AlgorithmFormValues>, '')
      form.setValue(`mappings.evaluation.${index}.targetParamName` as FieldPath<AlgorithmFormValues>, '')
    }
  }

  /** 源参数变更：回填 paramName + 判重提示（判重读实时值，INT-1160 返工 P2） */
  const handleSourceParamChange = (index: number, value: string) => {
    form.setValue(`mappings.evaluation.${index}.sourceParam` as FieldPath<AlgorithmFormValues>, value ?? '')
    const liveRows = (form.getValues('mappings.evaluation') ?? []) as MappingRow[]
    const source = liveRows[index]?.source || 'case'
    const name = evalSourceParamName(source, value ?? '', caseParams, referenceParams, deviceParams, apiParams)
    form.setValue(`mappings.evaluation.${index}.paramName` as FieldPath<AlgorithmFormValues>, name)
    checkDup(index)
  }

  /** 维度变更：写 dimensionId/dimensionName、清维度内目标参数 + 判重 */
  const handleDimensionChange = (index: number, dimId: string) => {
    const id = dimId || ''
    const dim = dimensions.find((d) => String(d.id) === id)
    form.setValue(`mappings.evaluation.${index}.dimensionId` as FieldPath<AlgorithmFormValues>, id)
    form.setValue(`mappings.evaluation.${index}.dimensionName` as FieldPath<AlgorithmFormValues>, dim?.name ?? '')
    form.setValue(`mappings.evaluation.${index}.targetParam` as FieldPath<AlgorithmFormValues>, '')
    form.setValue(`mappings.evaluation.${index}.targetParamName` as FieldPath<AlgorithmFormValues>, '')
    checkDup(index)
  }

  /** 维度内目标参数变更：回填名称 + 判重（维度 id 读实时值，INT-1160 返工 P2） */
  const handleTargetChange = (index: number, value: string) => {
    form.setValue(`mappings.evaluation.${index}.targetParam` as FieldPath<AlgorithmFormValues>, value ?? '')
    const liveRows = (form.getValues('mappings.evaluation') ?? []) as MappingRow[]
    const dimId = liveRows[index]?.dimensionId || ''
    const params = dimensionParamsMap[dimId] ?? []
    const param = params.find((p) => p.code === value)
    form.setValue(
      `mappings.evaluation.${index}.targetParamName` as FieldPath<AlgorithmFormValues>,
      param?.name ?? ''
    )
    checkDup(index)
  }

  /**
   * 判重（评估 = source + sourceParam + dimensionId；V9.7.10 checkDuplicateMapping）。
   * 行值一律读 form.getValues() 实时快照：handler 内 setValue 后 useWatch 快照尚未更新，
   * 用渲染快照判重会漏报（INT-1160 返工 P2：编辑存量完备行 sourceParam/dimensionId
   * 制造重复时不弹 toast → 发布 schema 兜底拦截前必须先在交互层报出）。
   */
  const checkDup = (index: number) => {
    const liveRows = (form.getValues('mappings.evaluation') ?? []) as MappingRow[]
    const dupIndex = findDuplicateIndex(liveRows, index, 'evaluation')
    if (dupIndex < 0) return
    const row = liveRows[index]
    const dimId = row?.dimensionId || ''
    const dimName = dimId ? dimById.get(dimId)?.name || row?.dimensionName || dimId : ''
    const sourceLabel =
      EVALUATION_SOURCE_OPTIONS.find((o) => o.value === (row?.source || 'case'))?.label ?? '用例参数'
    warnDuplicate(sourceLabel, row?.sourceParam || '', dimName)
  }

  /** 当前行源参数选项（按 source 取集合；V9.7.10 getSourceParams） */
  const evalSourceOptions = (source: string): ParamOption[] => {
    switch (source) {
      case 'case_config':
        return CASE_CONFIG_FIELD_PRESETS.map((p) => ({ value: p.code, label: p.name }))
      case 'reference':
        return referenceParams
          .map((p) => ({ value: p.code, label: `${p.code} · ${p.name || '（未填名称）'}` }))
          .filter((o) => o.value)
      case 'device':
        return deviceParams
          .map((p) => ({ value: p.paramCode, label: `${p.paramCode} · ${p.paramName || '（未填名称）'}` }))
          .filter((o) => o.value)
      case 'api':
        return apiParams
          .map((p) => ({ value: p.paramCode, label: `${p.paramCode} · ${p.paramName || '（未填名称）'}` }))
          .filter((o) => o.value)
      case 'case':
      default:
        return caseParams
          .map((p) => ({ value: p.paramCode, label: `${p.paramCode} · ${p.paramName || '（未填名称）'}` }))
          .filter((o) => o.value)
    }
  }

  /** 过滤后的行（keyword/source/dimension/transform） */
  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase()
    return rows.filter((row) => {
      if (sourceFilter !== 'all' && (row.source || 'case') !== sourceFilter) return false
      if (dimensionFilter !== 'all') {
        const rowKey = row.dimensionId ? String(row.dimensionId) : '__none__'
        if (rowKey !== dimensionFilter) return false
      }
      if (transformFilter !== 'all' && row.transformType !== transformFilter) return false
      if (!kw) return true
      const dimName = row.dimensionId
        ? dimById.get(String(row.dimensionId))?.name || row.dimensionName || ''
        : ''
      return (
        (row.sourceParam || '').toLowerCase().includes(kw) ||
        (row.paramName || '').toLowerCase().includes(kw) ||
        (row.targetParam || '').toLowerCase().includes(kw) ||
        (row.targetParamName || '').toLowerCase().includes(kw) ||
        dimName.toLowerCase().includes(kw)
      )
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, keyword, sourceFilter, dimensionFilter, transformFilter, dimById])

  /** 评估维度视图：按 dimensionId 分组（组序按维度名中文排序，空行归「未指定维度」） */
  const groups = useMemo(() => {
    if (viewMode !== 'dimension') return []
    const map = new Map<string, MappingRow[]>()
    for (const row of filtered) {
      const key = evalGroupKey(row)
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(row)
    }
    return Array.from(map.entries()).sort(([a], [b]) =>
      evalGroupName(a, dimensions, dimensionNameById).localeCompare(
        evalGroupName(b, dimensions, dimensionNameById),
        'zh-Hans-CN'
      )
    )
  }, [viewMode, filtered, dimensions, dimensionNameById])

  const pageRows = useMemo(() => {
    if (viewMode === 'dimension') return []
    const start = (page - 1) * pageSize
    return filtered.slice(start, start + pageSize)
  }, [viewMode, filtered, page, pageSize])

  useEffect(() => {
    setPage(1)
  }, [keyword, sourceFilter, dimensionFilter, transformFilter, viewMode])

  const colspan = 7
  const indexOf = (key: string) => mappings.fields.findIndex((f) => f.key === key)

  return (
    <div className='space-y-2'>
      {/* 工具栏：搜索 + 来源 + 评估维度 + 转换徽章筛选 + 视图切换 + 添加 */}
      <div className='flex flex-wrap items-center gap-2'>
        <MappingSearch value={keyword} onChange={setKeyword} />
        <MappingBadgeFilter
          title='来源'
          options={EVALUATION_SOURCE_OPTIONS}
          value={sourceFilter}
          onValueChange={setSourceFilter}
          allLabel='全部来源'
        />
        <MappingBadgeFilter
          title='评估维度'
          options={dimensionFilterOptions}
          value={dimensionFilter}
          onValueChange={setDimensionFilter}
          allLabel='全部维度'
        />
        <MappingBadgeFilter
          title='转换'
          options={TRANSFORM_TYPE_OPTIONS}
          value={transformFilter}
          onValueChange={setTransformFilter}
          allLabel='全部转换'
        />
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
        <Button
          variant='outline'
          size='sm'
          type='button'
          className='ml-auto'
          onClick={() => addEmpty()}
        >
          <Plus aria-hidden='true' />
          添加映射
        </Button>
      </div>

      <div className='bg-card ring-foreground/10 overflow-hidden rounded-lg ring-1'>
        <div className='overflow-x-auto'>
          <table className={`w-full min-w-0 text-[13px] ${CONTAINED_TABLE_CLASS}`}>
            <thead>
              <tr className='bg-[var(--table-header)] text-xs'>
                <th className='px-3 py-2 text-left font-medium'>来源</th>
                <th className='px-3 py-2 text-left font-medium'>源参数代码</th>
                <th className='px-3 py-2 text-left font-medium'>源参数名称</th>
                <th className='px-3 py-2 text-left font-medium'>目标评估维度</th>
                <th className='px-3 py-2 text-left font-medium'>目标参数</th>
                <th className='px-3 py-2 text-left font-medium'>转换</th>
                <th className='w-10 px-3 py-2 text-right font-medium'>操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={colspan} className='text-muted-foreground px-3 py-5 text-center'>
                    暂无映射，点击「添加映射」新增
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={colspan} className='text-muted-foreground px-3 py-5 text-center'>
                    无匹配映射
                  </td>
                </tr>
              ) : viewMode === 'flat' ? (
                pageRows.map((row) => {
                  const index = indexOf(row.key)
                  return (
                    <EvaluationRow
                      key={row.key}
                      form={form}
                      index={index}
                      dimensions={dimensions}
                      categories={categories}
                      dimensionParamsMap={dimensionParamsMap}
                      caseParams={caseParams}
                      referenceParams={referenceParams}
                      deviceParams={deviceParams}
                      apiParams={apiParams}
                      evalSourceOptions={evalSourceOptions}
                      onRemove={() => mappings.remove(index)}
                      onSourceChange={handleSourceChange}
                      onSourceParamChange={handleSourceParamChange}
                      onDimensionChange={handleDimensionChange}
                      onTargetChange={handleTargetChange}
                    />
                  )
                })
              ) : (
                groups.map(([key, groupRows]) => {
                  const isCollapsed = collapsed.has(key)
                  const dimId = !key.startsWith('name:') && key !== '__none__' ? key : ''
                  const dim = dimById.get(dimId)
                  return (
                    <Fragment key={key}>
                      <tr className='bg-muted/40 border-border/50 border-b'>
                        <td colSpan={colspan} className='px-0 py-0'>
                          <GroupHeaderButton
                            name={evalGroupName(key, dimensions, dimensionNameById)}
                            count={groupRows.length}
                            collapsed={isCollapsed}
                            onToggle={() => toggleCollapsed(key)}
                            badge={
                              dim ? (
                                dim.parentDimensionId ? (
                                  <>
                                    <span className={subBadge}>子</span>
                                    {dimensions.find(
                                      (d) => String(d.id) === String(dim.parentDimensionId)
                                    )?.name ? (
                                      <span className='text-muted-foreground/70 text-[11px] font-normal'>
                                        （
                                        {dimensions.find(
                                          (d) => String(d.id) === String(dim.parentDimensionId)
                                        )?.name ?? ''}
                                        ）
                                      </span>
                                    ) : null}
                                  </>
                                ) : (
                                  <span className={mainBadge}>主</span>
                                )
                              ) : key === '__none__' ? (
                                <span className='text-muted-foreground text-[11px] font-normal'>
                                  （未指定）
                                </span>
                              ) : null
                            }
                          />
                        </td>
                      </tr>
                      {!isCollapsed &&
                        groupRows.map((row) => {
                          const index = indexOf(row.key)
                          return (
                            <EvaluationRow
                              key={row.key}
                              form={form}
                              index={index}
                              dimensions={dimensions}
                              categories={categories}
                              dimensionParamsMap={dimensionParamsMap}
                              caseParams={caseParams}
                              referenceParams={referenceParams}
                              deviceParams={deviceParams}
                              apiParams={apiParams}
                              evalSourceOptions={evalSourceOptions}
                              onRemove={() => mappings.remove(index)}
                              onSourceChange={handleSourceChange}
                              onSourceParamChange={handleSourceParamChange}
                              onDimensionChange={handleDimensionChange}
                              onTargetChange={handleTargetChange}
                            />
                          )
                        })}
                      {!isCollapsed && (
                        <GroupAddRow
                          colSpan={colspan}
                          onClick={() =>
                            addEmpty(
                              dimId,
                              dimId
                                ? dimById.get(dimId)?.name ?? dimensionNameById.get(dimId) ?? ''
                                : ''
                            )
                          }
                        />
                      )}
                    </Fragment>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {viewMode === 'flat' && filtered.length > pageSize && (
        <MappingPagination
          total={filtered.length}
          page={page}
          pageSize={pageSize}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
        />
      )}
    </div>
  )
}

/** 评估映射行（平铺/维度视图共用单元格：来源 → 源参数 → 目标维度 → 维度内目标参数 → 转换） */
function EvaluationRow({
  form,
  index,
  dimensions,
  categories,
  caseParams,
  referenceParams,
  deviceParams,
  apiParams,
  dimensionParamsMap,
  evalSourceOptions,
  onRemove,
  onSourceChange,
  onSourceParamChange,
  onDimensionChange,
  onTargetChange,
}: {
  form: UseFormReturn<AlgorithmFormValues>
  index: number
  dimensions: Dimension[]
  categories: EvaluationCategory[]
  caseParams: Array<{ paramCode: string; paramName?: string }>
  referenceParams: Array<{ code: string; name?: string }>
  deviceParams: Array<{ paramCode: string; paramName?: string }>
  apiParams: Array<{ paramCode: string; paramName?: string }>
  dimensionParamsMap: Record<string, DimensionParam[]>
  evalSourceOptions: (source: string) => ParamOption[]
  onRemove: () => void
  onSourceChange: (index: number, value: string) => void
  onSourceParamChange: (index: number, value: string) => void
  onDimensionChange: (index: number, value: string) => void
  onTargetChange: (index: number, value: string) => void
}) {
  const source = form.watch(`mappings.evaluation.${index}.source`) || 'case'
  const sourceParam = form.watch(`mappings.evaluation.${index}.sourceParam`) || ''
  const dimensionId = form.watch(`mappings.evaluation.${index}.dimensionId`) || ''
  const targetParam = form.watch(`mappings.evaluation.${index}.targetParam`) || ''
  const sourceParamName = form.watch(`mappings.evaluation.${index}.paramName`) || ''
  const targetParamName = form.watch(`mappings.evaluation.${index}.targetParamName`) || ''

  const sourceOptions = evalSourceOptions(source)
  /** 源参数名称：实时按 source 取对应集合兜底（存量行 paramName 为空时显示真实名称） */
  const resolvedSourceName =
    evalSourceParamName(source, sourceParam, caseParams, referenceParams, deviceParams, apiParams) ||
    sourceParamName ||
    sourceParam
  /** 维度内目标参数选项；存量 target_param（如旧版维度名）不在列表时回退展示（数据保全） */
  const dimParams = dimensionParamsMap[dimensionId] ?? []
  const targetOptions: ParamOption[] = dimParams.map((p) => ({
    value: p.code,
    label: `${p.code} · ${p.name || '（未填名称）'}`,
  }))
  if (targetParam && !targetOptions.some((o) => o.value === targetParam)) {
    targetOptions.unshift({ value: targetParam, label: `${targetParam} · ${targetParamName || targetParam}` })
  }

  return (
    <tr className='border-border/50 border-b last:border-b-0'>
      <td className='px-2 py-1.5'>
        <MappingSelect
          value={source}
          onValueChange={(value) => onSourceChange(index, value)}
          options={EVALUATION_SOURCE_OPTIONS}
          className='w-28'
        />
      </td>
      <td className='px-2 py-1.5'>
        <MappingSelect
          value={sourceParam}
          onValueChange={(value) => onSourceParamChange(index, value)}
          options={sourceOptions}
          placeholder='选择参数'
          className='w-40'
        />
      </td>
      <td className='px-2 py-1.5'>
        <ParamNameCell name={resolvedSourceName} code={sourceParam} />
      </td>
      <td className='px-2 py-1.5'>
        <DimensionSelect
          dimensions={dimensions}
          categories={categories}
          value={dimensionId}
          onValueChange={(value) => onDimensionChange(index, value)}
          valueOf={(dimension) => String(dimension.id)}
          placeholder='选择维度'
          triggerClassName='w-48'
        />
      </td>
      <td className='px-2 py-1.5'>
        <MappingSelect
          value={targetParam}
          onValueChange={(value) => onTargetChange(index, value)}
          options={targetOptions}
          placeholder={dimensionId ? '选择参数' : '先选维度'}
          disabled={!dimensionId}
          className='w-40'
        />
      </td>
      <td className='px-2 py-1.5'>
        <TransformSelect
          value={form.watch(`mappings.evaluation.${index}.transformType`)}
          onValueChange={(value) =>
            form.setValue(
              `mappings.evaluation.${index}.transformType` as FieldPath<AlgorithmFormValues>,
              value ?? 'none'
            )
          }
          options={TRANSFORM_TYPE_OPTIONS}
        />
      </td>
      <td className='px-2 py-1.5'>
        <div className='flex items-center justify-end'>
          <DeleteButton onClick={onRemove} />
        </div>
      </td>
    </tr>
  )
}

/** 评估源参数名称（按 source 取对应集合；V9.7.10 getParamName 口径） */
function evalSourceParamName(
  source: string,
  code: string,
  caseParams: Array<{ paramCode: string; paramName?: string }>,
  referenceParams: Array<{ code: string; name?: string }>,
  deviceParams: Array<{ paramCode: string; paramName?: string }>,
  apiParams: Array<{ paramCode: string; paramName?: string }>
): string {
  if (!code) return ''
  switch (source) {
    case 'case_config':
      return CASE_CONFIG_FIELD_PRESETS.find((p) => p.code === code)?.name || ''
    case 'reference':
      return paramNameByCode(referenceParams, code)
    case 'device':
      return paramNameByCode(deviceParams, code)
    case 'api':
      return paramNameByCode(apiParams, code)
    case 'case':
    default:
      return paramNameByCode(caseParams, code)
  }
}

/* ───────────────────────── 三折叠分区外壳 ───────────────────────── */

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
  const caseParams = useWatch({ control: form.control, name: 'caseParams' })
  const referenceParams = useWatch({ control: form.control, name: 'referenceParams' })
  const deviceParams = useWatch({ control: form.control, name: 'deviceParams' })
  const apiParams = useWatch({ control: form.control, name: 'apiParams' })

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
        <DeviceApiMappingSection
          form={form}
          arrayName='mappings.device'
          sectionLabel='设备'
          caseParams={caseParams}
          referenceParams={referenceParams}
          targetParams={deviceParams}
          transformOptions={TRANSFORM_TYPE_OPTIONS}
        />
      </MappingCollapsible>

      <MappingCollapsible
        title='API参数映射'
        subtitle='用例参数 → API参数'
        count={apiCount}
      >
        <DeviceApiMappingSection
          form={form}
          arrayName='mappings.api'
          sectionLabel='API'
          caseParams={caseParams}
          referenceParams={referenceParams}
          targetParams={apiParams}
          transformOptions={API_TRANSFORM_TYPE_OPTIONS}
        />
      </MappingCollapsible>

      <MappingCollapsible
        title='评估参数映射'
        subtitle='用例参数/设备输出/API输出 → 评估维度'
        count={evaluationCount}
      >
        <EvaluationMappingSection
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
