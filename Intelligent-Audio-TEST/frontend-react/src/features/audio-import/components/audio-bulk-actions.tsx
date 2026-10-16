/**
 * 批量操作浮条（§5.6 DataTableBulkActions 照搬：floating bottom + X 清选 + 计数 Badge
 * + 「已选 {n} 个音频」+ 按钮组）。
 * 按钮组：批量删除（audio:delete）/批量导出（audio:update）/批量设置标签（audio:update）
 * + 更多批量操作（移动/复制/重命名/修改属性，audio:update → §6.25）。
 */
import { FolderTree, ListChecks, Tags, Trash2, X } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Separator } from '@/components/ui/separator'
import type { AudioBulkDialogState } from '@/features/audio-import/types'

export type AudioBulkActionsProps = {
  count: number
  canDelete: boolean
  canUpdate: boolean
  onClear: () => void
  onDelete: () => void
  onExport: () => void
  onOpenBulkDialog: (state: AudioBulkDialogState) => void
}

export function AudioBulkActions(props: AudioBulkActionsProps) {
  if (props.count === 0) return null
  return (
    <div className='fixed bottom-6 left-1/2 z-50 w-max max-w-[calc(100vw-2rem)] -translate-x-1/2'>
      <div className='bg-background/95 flex items-center gap-2 rounded-xl border p-2 shadow-xl backdrop-blur-lg'>
        <Button
          variant='ghost'
          size='icon-sm'
          aria-label='清空选择'
          onClick={props.onClear}
        >
          <X aria-hidden='true' />
        </Button>
        <Separator orientation='vertical' className='h-5!' />
        <Badge className='min-w-8 justify-center rounded-lg'>{props.count}</Badge>
        <span className='text-sm whitespace-nowrap'>已选 {props.count} 个音频</span>

        <Separator orientation='vertical' className='h-5!' />
        {props.canDelete && (
          <Button
            variant='destructive'
            size='sm'
            className='gap-1.5'
            onClick={props.onDelete}
          >
            <Trash2 aria-hidden='true' className='size-3.5' />
            批量删除
          </Button>
        )}
        {props.canUpdate && (
          <Button variant='outline' size='sm' className='gap-1.5' onClick={props.onExport}>
            <ListChecks aria-hidden='true' className='size-3.5' />
            批量导出
          </Button>
        )}
        {props.canUpdate && (
          <Button
            variant='outline'
            size='sm'
            className='gap-1.5'
            onClick={() => props.onOpenBulkDialog({ kind: 'tags' })}
          >
            <Tags aria-hidden='true' className='size-3.5' />
            批量设置标签
          </Button>
        )}
        {props.canUpdate && (
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <Button variant='outline' size='sm' className='gap-1.5' />
              }
            >
              <FolderTree aria-hidden='true' className='size-3.5' />
              更多批量操作
            </DropdownMenuTrigger>
            <DropdownMenuContent align='end' className='w-44'>
              <DropdownMenuItem onClick={() => props.onOpenBulkDialog({ kind: 'move' })}>
                批量移动
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => props.onOpenBulkDialog({ kind: 'copy' })}>
                批量复制
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => props.onOpenBulkDialog({ kind: 'rename' })}>
                批量重命名
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={() => props.onOpenBulkDialog({ kind: 'modify-properties' })}
              >
                批量修改属性
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
    </div>
  )
}
