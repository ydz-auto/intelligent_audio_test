/**
 * 静态数据表（interfaces 层，对位 newAPI StaticDataTable；母版 B 资源分区用）：
 * 列定义 + 行操作尾列 + 空态文案；样式沿用基座 ui 原语（HTML table + 语义 token，
 * 同报告列表表头 `bg-muted/30` 口径）。
 */
import type { ReactNode } from 'react'

import { Empty, EmptyContent, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Inbox } from 'lucide-react'

export type StaticDataTableColumn<T> = {
  key: string
  header: string
  className?: string
  render?: (row: T) => ReactNode
}

type StaticDataTableProps<T> = {
  columns: StaticDataTableColumn<T>[]
  rows: T[]
  rowKey: (row: T) => string
  emptyText?: string
  emptyDescription?: string
  /** 尾列操作（编辑/删除等行操作组） */
  actions?: (row: T) => ReactNode
  minWidth?: string
}

export function StaticDataTable<T>(props: StaticDataTableProps<T>) {
  if (props.rows.length === 0) {
    return (
      <Empty className='min-h-[200px] border-dashed'>
        <EmptyHeader>
          <EmptyMedia variant='icon'>
            <Inbox className='size-4' aria-hidden='true' />
          </EmptyMedia>
          <EmptyTitle>{props.emptyText ?? '暂无数据'}</EmptyTitle>
          {props.emptyDescription && (
            <div className='text-muted-foreground text-sm'>
              {props.emptyDescription}
            </div>
          )}
        </EmptyHeader>
        <EmptyContent />
      </Empty>
    )
  }

  return (
    <div className='overflow-hidden rounded-lg border'>
      <div className='overflow-x-auto'>
        <table
          className='w-full text-sm'
          style={{ minWidth: props.minWidth ?? '640px' }}
        >
          <thead>
            <tr className='text-muted-foreground border-b bg-muted/30'>
              {props.columns.map((column) => (
                <th
                  key={column.key}
                  className={`px-3 py-2.5 text-left font-medium ${column.className ?? ''}`}
                >
                  {column.header}
                </th>
              ))}
              {props.actions && <th className='w-28 px-3 py-2.5' />}
            </tr>
          </thead>
          <tbody>
            {props.rows.map((row) => (
              <tr
                key={props.rowKey(row)}
                className='hover:bg-muted/30 border-b transition-colors last:border-0'
              >
                {props.columns.map((column) => (
                  <td
                    key={column.key}
                    className={`px-3 py-3 ${column.className ?? ''}`}
                  >
                    {column.render ? column.render(row) : null}
                  </td>
                ))}
                {props.actions && (
                  <td className='px-3 py-3 text-right'>
                    {props.actions(row)}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
