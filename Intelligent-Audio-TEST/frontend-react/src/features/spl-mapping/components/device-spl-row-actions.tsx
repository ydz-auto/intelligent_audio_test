/**
 * 物理域 SPL 行操作菜单（§4.2.1；DataTableRowActionMenu 对位，w-48 align='end'）。
 * 详情/编辑/执行校准/校准历史/删除——按 spl:* 权限逐项显隐（§8.2：device_admin 持全套）。
 * 执行校准现状后端为模拟校准（§11-12），入口保留并如实标注。
 */
import {
  AudioLines,
  Eye,
  History,
  MoreHorizontal,
  Pencil,
  Trash2,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { SplMapping } from '@/domain/models/splMapping'

export type DeviceSplRowActionsProps = {
  mapping: SplMapping
  canRead: boolean
  canUpdate: boolean
  canCreate: boolean
  canDelete: boolean
  onDetail: () => void
  onEdit: () => void
  onCalibrate: () => void
  onHistory: () => void
  onDelete: () => void
}

export function DeviceSplRowActions(props: DeviceSplRowActionsProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant='ghost'
            size='icon-sm'
            aria-label={`映射 ${props.mapping.name} 的操作`}
          />
        }
      >
        <MoreHorizontal aria-hidden='true' />
      </DropdownMenuTrigger>
      <DropdownMenuContent align='end' className='w-48'>
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
        {props.canCreate && (
          <DropdownMenuItem onClick={props.onCalibrate}>
            <AudioLines aria-hidden='true' />
            执行校准
          </DropdownMenuItem>
        )}
        {props.canRead && (
          <DropdownMenuItem onClick={props.onHistory}>
            <History aria-hidden='true' />
            校准历史
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
