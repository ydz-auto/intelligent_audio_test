/**
 * 算法行操作菜单（§3.5；DataTableRowActionMenu 对位，w-48 align='end'）。
 * 详情（algorithm:read 全部可读）/ 编辑（definition_manage）/ 复制（definition_manage）/
 * 删除（definition_manage，destructive + ConfirmDialog 外挂）。
 */
import { Copy, Eye, MoreHorizontal, Pencil, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { AlgorithmDefinition } from '@/domain/models/algorithmConfig'

export type AlgorithmRowActionsProps = {
  algorithm: AlgorithmDefinition
  canManage: boolean
  onDetail: () => void
  onEdit: () => void
  onClone: () => void
  onDelete: () => void
}

export function AlgorithmRowActions(props: AlgorithmRowActionsProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant='ghost'
            size='icon-sm'
            aria-label={`算法 ${props.algorithm.name} 的操作`}
          />
        }
      >
        <MoreHorizontal aria-hidden='true' />
      </DropdownMenuTrigger>
      <DropdownMenuContent align='end' className='w-48'>
        <DropdownMenuItem onClick={props.onDetail}>
          <Eye aria-hidden='true' />
          详情
        </DropdownMenuItem>
        {props.canManage && (
          <>
            <DropdownMenuItem onClick={props.onEdit}>
              <Pencil aria-hidden='true' />
              编辑
            </DropdownMenuItem>
            <DropdownMenuItem onClick={props.onClone}>
              <Copy aria-hidden='true' />
              复制
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              variant='destructive'
              onClick={props.onDelete}
            >
              <Trash2 aria-hidden='true' />
              删除
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
