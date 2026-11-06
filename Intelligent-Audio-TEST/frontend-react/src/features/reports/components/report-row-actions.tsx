/**
 * 行操作菜单（对位 newAPI DataTableRowActionMenu，规范 §3.7）：
 * 查看/编辑/发布/删除/收藏（正常态）；恢复/彻底删除（回收站态）。
 * 权限按 report:read/update/publish/delete/compare 显隐（seed_rbac 矩阵 §7.1）。
 */
import { MoreHorizontal } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { ReportListItem } from '@/domain/models/report'

export type ReportRowAction =
  | 'view'
  | 'edit'
  | 'publish'
  | 'delete'
  | 'favorite'
  | 'unfavorite'
  | 'restore'
  | 'purge'

interface ReportRowActionsProps {
  report: ReportListItem
  trashMode: boolean
  hasPermission: (permission: string) => boolean
  onAction: (action: ReportRowAction) => void
}

export function ReportRowActions({
  report,
  trashMode,
  hasPermission,
  onAction,
}: ReportRowActionsProps) {
  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger
        render={
          <Button
            variant='ghost'
            size='icon-sm'
            aria-label={`报告操作：${report.name}`}
          />
        }
      >
        <MoreHorizontal className='size-4' />
      </DropdownMenuTrigger>
      <DropdownMenuContent align='end' className='w-48'>
        {trashMode ? (
          <>
            {hasPermission('report:delete') && (
              <DropdownMenuItem onClick={() => onAction('restore')}>
                恢复
              </DropdownMenuItem>
            )}
            {hasPermission('report:delete') && (
              <DropdownMenuItem
                variant='destructive'
                onClick={() => onAction('purge')}
              >
                彻底删除
              </DropdownMenuItem>
            )}
          </>
        ) : (
          <>
            <DropdownMenuItem onClick={() => onAction('view')}>
              查看
            </DropdownMenuItem>
            {hasPermission('report:update') && (
              <DropdownMenuItem onClick={() => onAction('edit')}>
                编辑
              </DropdownMenuItem>
            )}
            {hasPermission('report:publish') && report.status === 'draft' && (
              <DropdownMenuItem onClick={() => onAction('publish')}>
                发布
              </DropdownMenuItem>
            )}
            {hasPermission('report:delete') && (
              <DropdownMenuItem
                variant='destructive'
                onClick={() => onAction('delete')}
              >
                删除
              </DropdownMenuItem>
            )}
            <DropdownMenuSeparator />
            {hasPermission('report:read') && (
              <DropdownMenuItem onClick={() => onAction('favorite')}>
                {report.is_favorite ? '取消收藏' : '收藏'}
              </DropdownMenuItem>
            )}
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
