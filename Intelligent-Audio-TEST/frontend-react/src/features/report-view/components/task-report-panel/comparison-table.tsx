/**
 * 对比表格（15_报告域.md §3.3.4，ComparisonTableComponent 对位）。
 * summary.tables 批量渲染：标题 + 搜索 + 导出 + 排序 + 分页 + 折叠（isExporting 强制展开不分页）。
 * 列类型渲染：status → StatusBadge；percentage → 数值 + 进度条；number → tabular-nums。
 */
import { ChevronDown, Download, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import type { ReportComparisonTable } from '@/domain/models/report'
import { cn } from '@/lib/utils'

const STATUS_LABELS: Record<string, string> = {
  pending: '排队中',
  'in-progress': '执行中',
  completed: '已完成',
  failed: '执行失败',
  draft: '草稿',
  published: '已发布',
  online: '在线',
  offline: '离线',
  active: '活跃',
}

function statusVariant(status: string) {
  if (status === 'completed' || status === 'published' || status === 'online' || status === 'active') return 'success'
  if (status === 'failed' || status === 'offline') return 'danger'
  if (status === 'draft') return 'warning'
  return 'neutral'
}

function progressColor(value: number) {
  if (value >= 90) return 'bg-success'
  if (value >= 70) return 'bg-secondary'
  if (value >= 50) return 'bg-warning'
  return 'bg-destructive'
}

export function ComparisonTable({
  table,
  isExporting,
}: {
  table: ReportComparisonTable
  isExporting?: boolean
}) {
  const [open, setOpen] = useState(!table.default_collapsed)
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const [sortKey, setSortKey] = useState<string>()
  const [sortAsc, setSortAsc] = useState(true)
  const pageSize = 10

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return table.data
    return table.data.filter((row) =>
      Object.values(row).some((v) => String(v).toLowerCase().includes(q))
    )
  }, [table.data, query])

  const sorted = useMemo(() => {
    if (!sortKey) return filtered
    return [...filtered].sort((a, b) => {
      const av = a[sortKey]
      const bv = b[sortKey]
      const cmp =
        typeof av === 'number' && typeof bv === 'number'
          ? av - bv
          : String(av).localeCompare(String(bv))
      return sortAsc ? cmp : -cmp
    })
  }, [filtered, sortKey, sortAsc])

  const total = sorted.length
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const visible = isExporting ? sorted : sorted.slice((page - 1) * pageSize, page * pageSize)

  const handleSort = (key: string) => {
    if (sortKey === key) setSortAsc((v) => !v)
    else {
      setSortKey(key)
      setSortAsc(true)
    }
  }

  // 导出当前表（CSV，含表头；规范 §3.3.4 export 事件，mock 阶段前端生成；TODO(API 接线) 换服务端导出）
  const handleExport = () => {
    const header = table.columns.map((col) => col.label)
    const body = sorted.map((row) =>
      table.columns.map((col) => {
        const value = row[col.key]
        return typeof value === 'number' ? String(value) : String(value ?? '')
      })
    )
    const csv = [header, ...body]
      .map((cells) => cells.map((cell) => `"${cell.replace(/"/g, '""')}"`).join(','))
      .join('\r\n')
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    link.download = `${table.title}.csv`
    link.href = URL.createObjectURL(blob)
    link.click()
    URL.revokeObjectURL(link.href)
    toast.success('表格已导出')
  }

  return (
    <Collapsible open={open || isExporting} onOpenChange={setOpen} className='space-y-2'>
      <div className='flex items-center justify-between'>
        <CollapsibleTrigger
          render={
            <Button variant='ghost' size='sm' className='text-foreground -ml-2 h-8' />
          }
        >
          <span className='flex items-center gap-2 text-sm font-semibold'>
            {table.title}
            {table.data.length > 0 && (
              <Badge variant='secondary' className='font-mono tabular-nums'>
                {table.data.length}
              </Badge>
            )}
          </span>
          {!isExporting && (
            <ChevronDown
              aria-hidden='true'
              className={cn('text-muted-foreground size-4 transition-transform', open && 'rotate-180')}
            />
          )}
        </CollapsibleTrigger>
        {!isExporting && (
          <div className='flex items-center gap-2'>
            <div className='relative'>
              <Search aria-hidden='true' className='text-muted-foreground absolute start-2 top-1/2 size-3.5 -translate-y-1/2' />
              <Input
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value)
                  setPage(1)
                }}
                placeholder='搜索...'
                className='h-8 w-40 ps-7 text-xs'
              />
            </div>
            <Button variant='ghost' size='sm' className='h-8 gap-1 px-2 text-xs' onClick={handleExport}>
              <Download aria-hidden='true' className='size-3.5' />
              导出
            </Button>
          </div>
        )}
      </div>

      <CollapsibleContent>
        {visible.length === 0 ? (
          <div className='text-muted-foreground flex h-20 items-center justify-center rounded-lg border text-xs'>
            暂无数据
          </div>
        ) : (
          <div className='overflow-hidden rounded-lg border'>
            <div className='overflow-x-auto'>
              <table className='w-full min-w-[480px] text-sm'>
                <thead>
                  <tr className='text-muted-foreground border-b bg-muted/30'>
                    {table.columns.map((col) => (
                      <th
                        key={col.key}
                        className='cursor-pointer px-3 py-2.5 text-left font-medium select-none'
                        onClick={() => handleSort(col.key)}
                      >
                        {col.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {visible.map((row, index) => (
                    // P3：弃纯 index key——排序/过滤后行身份变化；内容指纹为主 + index 消歧（并列名次 key 冲突）
                    <tr key={`${Object.values(row).join('|')}-${index}`} className='hover:bg-muted/30 border-b last:border-0'>
                      {table.columns.map((col) => (
                        <td key={col.key} className='px-3 py-2'>
                          {renderCell(row[col.key], col.type)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!isExporting && pages > 1 && (
              <div className='text-muted-foreground flex items-center justify-between border-t px-3 py-2 text-xs'>
                <span>
                  第 {page} 页，共 {pages} 页，总计 {total} 条数据
                </span>
                <div className='flex items-center gap-1'>
                  <Button variant='ghost' size='sm' className='h-7 px-2 text-xs' disabled={page <= 1} onClick={() => setPage(1)}>
                    首页
                  </Button>
                  <Button variant='ghost' size='sm' className='h-7 px-2 text-xs' disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                    上一页
                  </Button>
                  <Button variant='ghost' size='sm' className='h-7 px-2 text-xs' disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
                    下一页
                  </Button>
                  <Button variant='ghost' size='sm' className='h-7 px-2 text-xs' disabled={page >= pages} onClick={() => setPage(pages)}>
                    末页
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}
      </CollapsibleContent>
    </Collapsible>
  )
}

function renderCell(value: unknown, type?: string) {
  if (value === null || value === undefined || value === '') return <span>—</span>
  if (type === 'status') {
    const label = STATUS_LABELS[String(value)] ?? String(value)
    return <Badge variant={statusVariant(String(value)) as never}>{label}</Badge>
  }
  if (type === 'percentage' && typeof value === 'number') {
    return (
      <div className='flex items-center gap-2'>
        <span className='font-mono text-xs tabular-nums'>{value.toFixed(1)}%</span>
        <div className='bg-muted h-1.5 w-16 overflow-hidden rounded-full'>
          <div
            className={cn('h-full rounded-full', progressColor(value))}
            style={{ width: `${Math.min(100, value)}%` }}
          />
        </div>
      </div>
    )
  }
  if (type === 'number' && typeof value === 'number') {
    return <span className='font-mono text-xs tabular-nums'>{value}</span>
  }
  return <span>{String(value)}</span>
}
