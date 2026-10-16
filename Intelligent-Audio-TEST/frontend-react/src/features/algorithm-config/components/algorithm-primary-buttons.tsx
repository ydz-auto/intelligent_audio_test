/**
 * 算法配置页页头动作区（§3.3；models-primary-buttons 对位）。
 * 「新建算法」主按钮（algorithm:definition_manage）+「更多操作 ⋯」下拉
 * （分组管理/导入算法/导出算法/重载配置/批量删除——definition_manage/group_manage；
 * 导出算法=algorithm:read 全员可见）。
 */
import {
  Boxes,
  Download,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Trash2,
  Upload,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

export type AlgorithmPrimaryButtonsProps = {
  canManage: boolean
  canGroupManage: boolean
  onNew: () => void
  onGroupManage: () => void
  onImport: () => void
  onExport: () => void
  onReload: () => void
  onBulkDelete: () => void
}

export function AlgorithmPrimaryButtons(props: AlgorithmPrimaryButtonsProps) {
  return (
    <div className='flex flex-wrap items-center gap-2'>
      {props.canManage && (
        <Button size='sm' onClick={props.onNew}>
          <Plus aria-hidden='true' />
          新建算法
        </Button>
      )}
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              variant='outline'
              size='sm'
              aria-label='更多操作'
            />
          }
        >
          <MoreHorizontal aria-hidden='true' />
        </DropdownMenuTrigger>
        <DropdownMenuContent align='end' className='w-48'>
          {props.canGroupManage && (
            <DropdownMenuItem onClick={props.onGroupManage}>
              <Boxes aria-hidden='true' />
              分组管理
            </DropdownMenuItem>
          )}
          {props.canManage && (
            <DropdownMenuItem onClick={props.onImport}>
              <Upload aria-hidden='true' />
              导入算法
            </DropdownMenuItem>
          )}
          <DropdownMenuItem onClick={props.onExport}>
            <Download aria-hidden='true' />
            导出算法
          </DropdownMenuItem>
          {props.canManage && (
            <DropdownMenuItem onClick={props.onReload}>
              <RefreshCw aria-hidden='true' />
              重载配置
            </DropdownMenuItem>
          )}
          {props.canManage && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                variant='destructive'
                onClick={props.onBulkDelete}
              >
                <Trash2 aria-hidden='true' />
                批量删除
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
