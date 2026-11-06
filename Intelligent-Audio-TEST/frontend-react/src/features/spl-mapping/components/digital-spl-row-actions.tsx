/**
 * 数字域 RMS-SPL 行操作菜单（§4.3.1；DataTableRowActionMenu 对位，w-48 align='end'）。
 * 校准/设默认·清除默认/详情/编辑/删除——按 digital_spl:* 权限逐项显隐（§8.2）。
 */
import {
  Eye,
  MoreHorizontal,
  Pencil,
  Star,
  StarHalf,
  Trash2,
  Waves,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { ApiRmsSplMapping } from '@/domain/models/digitalSpl'

export type DigitalSplRowActionsProps = {
  mapping: ApiRmsSplMapping
  isDefault: boolean
  canRead: boolean
  canUpdate: boolean
  canCreate: boolean
  canDelete: boolean
  onDetail: () => void
  onEdit: () => void
  onCalibrate: () => void
  onToggleDefault: () => void
  onDelete: () => void
}

export function DigitalSplRowActions(props: DigitalSplRowActionsProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant='ghost'
            size='icon-sm'
            aria-label={`映射 ${props.mapping.name || `#${props.mapping.id}`} 的操作`}
          />
        }
      >
        <MoreHorizontal aria-hidden='true' />
      </DropdownMenuTrigger>
      <DropdownMenuContent align='end' className='w-48'>
        {props.canCreate && (
          <DropdownMenuItem onClick={props.onCalibrate}>
            <Waves aria-hidden='true' />
            校准
          </DropdownMenuItem>
        )}
        {props.canUpdate && (
          <DropdownMenuItem onClick={props.onToggleDefault}>
            {props.isDefault ? (
              <StarHalf aria-hidden='true' />
            ) : (
              <Star aria-hidden='true' />
            )}
            {props.isDefault ? '清除默认' : '设默认'}
          </DropdownMenuItem>
        )}
        {props.canRead && (
          <DropdownMenuItem onClick={props.onDetail}>
            <Eye aria-hidden='true' />
            详情
          </DropdownMenuItem>
        )}
        {props.canUpdate && (
          <DropdownMenuItem onClick={props.onEdit}>
            <Pencil aria-hidden='true' />
            编辑
          </DropdownMenuItem>
        )}
        {props.canDelete && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant='destructive' onClick={props.onDelete}>
              <Trash2 aria-hidden='true' />
              删除
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
