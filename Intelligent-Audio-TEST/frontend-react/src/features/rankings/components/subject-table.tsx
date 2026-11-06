/**
 * 排行表格视图（14_benchmark排行.md §5.3，TanStack Table）：
 * 全字段 + 数值列右对齐 tabular-nums + 方向提示表头 tooltip + 空值「—」。
 * 横向滚动包裹（role='region' + aria-label「排行明细表：{列头拼接}」）。
 */
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table'
import { useMemo } from 'react'

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import type {
  BenchmarkDirection,
  RankingRow,
} from '@/domain/models/benchmark'
import {
  formatComputedAtShort,
  formatGap,
  formatMetricValue,
  formatPercentile,
  formatScore100,
} from '@/features/rankings/lib/format'
import { SubjectLink, ReportLink } from '@/features/rankings/components/entity-links'
import { cn } from '@/lib/utils'

const SUBJECT_TYPE_LABELS: Record<RankingRow['subjectType'], string> = {
  open_source: '开源',
  closed_source: '闭源',
  app: 'App',
}

export function SubjectTable(props: {
  rows: RankingRow[]
  direction: BenchmarkDirection
  unit: string
  className?: string
}) {
  const columnHelper = createColumnHelper<RankingRow>()
  const directionHint =
    props.direction === 'lower_is_better'
      ? '该指标越低越好，名次靠前值更小。'
      : '该指标越高越好，名次靠前值更大。'

  const columns = useMemo(
    () => [
      columnHelper.accessor('rank', {
        header: '名次',
        cell: (info) => <span className='tabular-nums'>{info.getValue()}.</span>,
        meta: { align: 'right' },
      }),
      columnHelper.accessor('subjectName', {
        header: '主体',
        cell: (info) => (
          <SubjectLink subjectName={info.getValue()} />
        ),
      }),
      columnHelper.accessor('subjectType', {
        header: '主体类型',
        cell: (info) => SUBJECT_TYPE_LABELS[info.getValue()],
      }),
      columnHelper.accessor('source', {
        header: '来源',
        cell: (info) =>
          info.getValue() === 'platform_test' ? '平台实测' : '外部基线',
      }),
      columnHelper.accessor('publishedTaskVersion', {
        header: '版本',
        cell: (info) =>
          info.getValue() === null ? '—' : `v${info.getValue()}`,
      }),
      columnHelper.accessor('metricValue', {
        header: `指标值(${props.unit})`,
        cell: (info) => (
          <span className='tabular-nums'>
            {formatMetricValue(info.getValue(), props.unit)}
          </span>
        ),
        meta: { align: 'right' },
      }),
      columnHelper.accessor('score100', {
        header: 'score100',
        cell: (info) => (
          <span className='tabular-nums'>{formatScore100(info.getValue())}</span>
        ),
        meta: { align: 'right' },
      }),
      columnHelper.accessor('percentile', {
        header: '百分位',
        cell: (info) => (
          <span className='tabular-nums'>
            {formatPercentile(info.getValue())}
          </span>
        ),
        meta: { align: 'right' },
      }),
      columnHelper.accessor('gapBest', {
        header: '与最佳差',
        cell: (info) => (
          <span className='tabular-nums'>{formatGap(info.getValue(), props.unit) ?? '—'}</span>
        ),
        meta: { align: 'right' },
      }),
      columnHelper.accessor('gapMedian', {
        header: '与中位差',
        cell: (info) => (
          <span className='tabular-nums'>{formatGap(info.getValue(), props.unit) ?? '—'}</span>
        ),
        meta: { align: 'right' },
      }),
      columnHelper.accessor('deltaExternal', {
        header: '基线差',
        cell: (info) => (
          <span className='tabular-nums'>
            {formatGap(info.getValue(), props.unit) ?? '—'}
          </span>
        ),
        meta: { align: 'right' },
      }),
      columnHelper.accessor('computedAt', {
        header: '计算于',
        cell: (info) => (
          <span className='tabular-nums'>
            {formatComputedAtShort(info.getValue())}
          </span>
        ),
      }),
      columnHelper.display({
        id: 'report',
        header: '报告',
        cell: (info) => {
          const row = info.row.original
          if (row.source !== 'platform_test' || row.reportId === null) return '—'
          return <ReportLink reportId={row.reportId} />
        },
      }),
    ],
    [columnHelper, props.direction, props.unit]
  )

  const table = useReactTable({
    data: props.rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
  })

  const columnLabels = columns
    .map((column) => (column.header ?? '') as string)
    .filter(Boolean)

  return (
    <TooltipProvider delay={100}>
      <div
        role='region'
        aria-label={`排行明细表：${columnLabels.join('·')}`}
        className={cn('relative w-full overflow-x-auto', props.className)}
      >
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead
                    key={header.id}
                    className={cn(
                      (header.column.columnDef.meta as { align?: string } | undefined)
                        ?.align === 'right' && 'text-right'
                    )}
                  >
                    {header.column.id === 'metricValue' ? (
                      <Tooltip>
                        <TooltipTrigger className='cursor-help'>
                          {flexRender(
                            header.column.columnDef.header,
                            header.getContext()
                          )}
                        </TooltipTrigger>
                        <TooltipContent side='top'>
                          {directionHint}
                        </TooltipContent>
                      </Tooltip>
                    ) : (
                      flexRender(
                        header.column.columnDef.header,
                        header.getContext()
                      )
                    )}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.map((row) => (
              <TableRow key={row.id}>
                {row.getVisibleCells().map((cell) => (
                  <TableCell
                    key={cell.id}
                    className={cn(
                      (cell.column.columnDef.meta as { align?: string } | undefined)
                        ?.align === 'right' && 'text-right'
                    )}
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </TooltipProvider>
  )
}
