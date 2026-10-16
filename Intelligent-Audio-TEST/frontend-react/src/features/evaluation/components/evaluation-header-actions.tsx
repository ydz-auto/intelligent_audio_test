/**
 * 评估维度页页头动作区（features/evaluation；11_用例域.md §4.1 Actions 工具行）。
 * 「+ 新增维度」（evaluation:dim_manage）｜「+ 新增分类」（evaluation:category_manage）｜
 * 「批量操作」下拉（evaluation:dim_manage：批量启用/禁用/删除，空选禁用+Tooltip）｜
 * 「导入/导出」下拉（evaluation:import_export：导入维度/导出维度）。
 */
import { Download, FolderPlus, Import, Plus, SlidersHorizontal, Upload } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

export function EvaluationHeaderActions({
  canManage,
  canCategoryManage,
  canImportExport,
  selectedCount,
  onAddDimension,
  onAddCategory,
  onBatchAction,
  onImport,
  onExport,
}: {
  canManage: boolean
  canCategoryManage: boolean
  canImportExport: boolean
  selectedCount: number
  onAddDimension: () => void
  onAddCategory: () => void
  onBatchAction: (action: 'enable' | 'disable' | 'delete') => void
  onImport: () => void
  onExport: () => void
}) {
  const batchDisabled = !canManage || selectedCount === 0
  const batchTooltip = !canManage
    ? '无 evaluation:dim_manage 权限'
    : `请先选择要操作的维度`

  return (
    <div className='flex flex-wrap items-center gap-2'>
      <Button
        variant='outline'
        size='sm'
        className='h-7 gap-1.5'
        disabled={!canManage}
        onClick={onAddDimension}
      >
        <Plus aria-hidden='true' className='size-3.5' />
        新增维度
      </Button>
      <Button
        variant='outline'
        size='sm'
        className='h-7 gap-1.5'
        disabled={!canCategoryManage}
        onClick={onAddCategory}
      >
        <FolderPlus aria-hidden='true' className='size-3.5' />
        新增分类
      </Button>

      <Tooltip>
        <TooltipTrigger
          render={
            <span
              tabIndex={0}
              className={cn('inline-flex', batchDisabled && 'cursor-not-allowed')}
            >
              <DropdownMenu>
                <DropdownMenuTrigger
                  render={
                    <Button
                      variant='outline'
                      size='sm'
                      className='h-7 gap-1.5'
                      disabled={batchDisabled}
                    >
                      <SlidersHorizontal
                        aria-hidden='true'
                        className='size-3.5'
                      />
                      批量操作
                    </Button>
                  }
                />
                <DropdownMenuContent align='end' className='w-44'>
                  <DropdownMenuItem
                    disabled={!canManage}
                    onSelect={() => onBatchAction('enable')}
                  >
                    批量启用
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    disabled={!canManage}
                    onSelect={() => onBatchAction('disable')}
                  >
                    批量禁用
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    disabled={!canManage}
                    className='text-destructive'
                    onSelect={() => onBatchAction('delete')}
                  >
                    批量删除
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </span>
          }
        />
        <TooltipContent>{batchTooltip}</TooltipContent>
      </Tooltip>

      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              variant='outline'
              size='sm'
              className='h-7 gap-1.5'
              disabled={!canImportExport}
            >
              <Import aria-hidden='true' className='size-3.5' />
              导入/导出
            </Button>
          }
        />
        <DropdownMenuContent align='end' className='w-44'>
          <DropdownMenuItem disabled={!canImportExport} onSelect={onImport}>
            <Upload aria-hidden='true' className='size-3.5' />
            导入维度
          </DropdownMenuItem>
          <DropdownMenuItem disabled={!canImportExport} onSelect={onExport}>
            <Download aria-hidden='true' className='size-3.5' />
            导出维度
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
