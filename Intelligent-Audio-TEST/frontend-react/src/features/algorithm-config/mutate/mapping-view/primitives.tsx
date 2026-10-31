/**
 * 参数映射视图公共件（Presentation；算法编辑模态窗与设备「参数配置」弹窗共用）。
 *
 * 抽自 mappings-section（INT-1160 返工版式）：
 * - 行级单元格：参数选择 / 转换选择 / 删除按钮 / 参数名称（可带作用域徽章）；
 * - 工具栏：搜索、徽章筛选、平铺/分组视图切换、添加；
 * - 表格框：表头 / 空态 / 无匹配态 / 行插槽；
 * - 分组视图：组头（折叠 + 计数）、组尾「添加映射」；
 * - 平铺视图分页（>10 条）。
 *
 * 只做视图，不持有表单或数据源状态——作用域写入由消费方决定。
 */
import { ChevronDown, Folder, Plus, Search, Trash2 } from 'lucide-react'
import type { ReactNode } from 'react'

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
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { CONTAINED_TABLE_CLASS } from '../table-containment'
import { cn } from '@/lib/utils'

export type ParamOption = { value: string; label: string }

/* ───────────────────────── 行级基础单元格 ───────────────────────── */

export function MappingSelect({
  value,
  onValueChange,
  options,
  placeholder = '选择参数',
  className,
  disabled = false,
  ariaLabel,
}: {
  value: string
  onValueChange: (value: string) => void
  options: ReadonlyArray<ParamOption>
  placeholder?: string
  className?: string
  disabled?: boolean
  ariaLabel?: string
}) {
  return (
    <Select value={value} onValueChange={(next) => onValueChange(next ?? '')} disabled={disabled}>
      <SelectTrigger size='sm' className={className} aria-label={ariaLabel}>
        {/* 显式解析选项标签（照 dimension-select 口径）：命中选项显示中文标签，未命中回退原值（数据保全） */}
        <SelectValue placeholder={placeholder}>
          {value ? (options.find((o) => o.value === value)?.label ?? value) : placeholder}
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

export function TransformSelect({
  value,
  onValueChange,
  options,
  disabled = false,
}: {
  value: string
  onValueChange: (value: string) => void
  options: ReadonlyArray<{ value: string; label: string }>
  disabled?: boolean
}) {
  return (
    <MappingSelect
      value={value}
      onValueChange={onValueChange}
      options={options.map((o) => ({ value: o.value, label: o.label }))}
      placeholder='选择转换'
      disabled={disabled}
      className='w-28'
    />
  )
}

export function DeleteButton({
  onClick,
  disabled = false,
  label = '删除该映射',
}: {
  onClick: () => void
  disabled?: boolean
  label?: string
}) {
  return (
    <Button
      variant='ghost'
      size='icon-sm'
      type='button'
      aria-label={label}
      className='text-destructive'
      disabled={disabled}
      onClick={onClick}
    >
      <Trash2 aria-hidden='true' className='size-3.5' />
    </Button>
  )
}

/** 只读参数名称单元格（代码已知但名称为空时回退显示代码，V9.7.10 param-name-cell 口径） */
export function ParamNameCell({
  name,
  code,
  badge,
}: {
  name: string
  code: string
  /** 行作用域徽章（设备级覆盖 / 算法级） */
  badge?: ReactNode
}) {
  return (
    <span className='text-muted-foreground inline-flex items-center gap-1 text-[12px]'>
      <span>{name || code || '—'}</span>
      {badge}
    </span>
  )
}

/* ───────────────────────── 工具栏公共件 ───────────────────────── */

export function MappingSearch({
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
export function MappingBadgeFilter({
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
export function MappingPagination({
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

/* ───────────────────────── 分组组头 / 组尾（设备与评估共用结构） ───────────────────────── */

/** 主/子维度徽章样式（照 dimension-select / dimension-picker chip 徽章） */
export const mainBadge =
  'bg-primary/20 text-primary inline-flex size-3.5 items-center justify-center rounded-[3px] text-[9px] font-semibold'
export const subBadge =
  'bg-muted text-muted-foreground border-border inline-flex size-3.5 items-center justify-center rounded-[3px] border text-[9px] font-semibold'

export function GroupHeaderButton({
  name,
  badge,
  hint,
  count,
  collapsed,
  onToggle,
}: {
  name: string
  badge?: ReactNode
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

export function GroupAddRow({ colSpan, onClick }: { colSpan: number; onClick: () => void }) {
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

/* ───────────────────────── 工具栏 / 视图切换 / 表格框 ───────────────────────── */

export function MappingToolbar({ children }: { children: ReactNode }) {
  return <div className='flex flex-wrap items-center gap-2'>{children}</div>
}

export function MappingAddButton({
  onClick,
  disabled = false,
}: {
  onClick: () => void
  disabled?: boolean
}) {
  return (
    <Button
      variant='outline'
      size='sm'
      type='button'
      className='ml-auto'
      disabled={disabled}
      onClick={onClick}
    >
      <Plus aria-hidden='true' />
      添加映射
    </Button>
  )
}

/** 平铺 / 分组两态视图切换（设备=分组，评估=评估维度） */
export function MappingViewToggle<T extends string>({
  value,
  options,
  onValueChange,
  ariaLabel,
}: {
  value: T
  options: ReadonlyArray<{ value: T; label: string }>
  onValueChange: (value: T) => void
  ariaLabel: string
}) {
  return (
    <ToggleGroup
      variant='outline'
      size='sm'
      spacing={0}
      value={[value]}
      aria-label={ariaLabel}
      onValueChange={(values) => {
        const next = values[0] as T | undefined
        if (next && options.some((option) => option.value === next)) onValueChange(next)
      }}
    >
      {options.map((option) => (
        <ToggleGroupItem key={option.value} value={option.value}>
          {option.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  )
}

/** 映射分节外壳（标题 + 副标题 + 条数徽章；默认收起/展开由调用方决定） */
export function MappingCollapsible({
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
  children: ReactNode
}) {
  return (
    <Collapsible defaultOpen={defaultOpen} className='space-y-2'>
      <CollapsibleTrigger className='hover:bg-muted/50 flex w-full items-center justify-between gap-2 rounded-lg border border-border px-3 py-2 text-sm transition-colors'>
        <span className='flex min-w-0 items-center gap-2'>
          <span className='font-medium'>{title}</span>
          <span className='text-muted-foreground hidden text-xs sm:inline'>{subtitle}</span>
        </span>
        <Badge variant='secondary' className='font-mono text-[11px] tabular-nums'>
          {count} 条映射
        </Badge>
      </CollapsibleTrigger>
      <CollapsibleContent className='pt-1'>{children}</CollapsibleContent>
    </Collapsible>
  )
}

export interface MappingColumn {
  label: string
  className?: string
}

/**
 * 映射表格框：表头 + 空态 / 无匹配态 + 行插槽。
 * `isEmpty` 优先（没有任何行），其次 `isFilteredEmpty`（有行但被筛选掉）。
 */
export function MappingTableFrame({
  columns,
  colSpan,
  isEmpty,
  isFilteredEmpty = false,
  emptyText = '暂无映射，点击「添加映射」新增',
  noMatchText = '无匹配映射',
  children,
}: {
  columns: ReadonlyArray<MappingColumn>
  colSpan: number
  isEmpty: boolean
  isFilteredEmpty?: boolean
  emptyText?: string
  noMatchText?: string
  children?: ReactNode
}) {
  return (
    <div className='bg-card ring-foreground/10 overflow-hidden rounded-lg ring-1'>
      <div className='overflow-x-auto'>
        <table className={`w-full min-w-0 text-[13px] ${CONTAINED_TABLE_CLASS}`}>
          <thead>
            <tr className='bg-[var(--table-header)] text-xs'>
              {columns.map((column) => (
                <th
                  key={column.label}
                  className={column.className ?? 'px-3 py-2 text-left font-medium'}
                >
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isEmpty ? (
              <tr>
                <td colSpan={colSpan} className='text-muted-foreground px-3 py-5 text-center'>
                  {emptyText}
                </td>
              </tr>
            ) : isFilteredEmpty ? (
              <tr>
                <td colSpan={colSpan} className='text-muted-foreground px-3 py-5 text-center'>
                  {noMatchText}
                </td>
              </tr>
            ) : (
              children
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
