/**
 * 合并容器批量操作浮条（18_挑选合并交互重设计.md §2.3 DataTablePage 批量浮条；INT-1278 接线）。
 * 形态照 TaskBulkActions（DataTableBulkActions：`fixed bottom-6 left-1/2 z-50 w-max
 * max-w-[calc(100vw-2rem)] -translate-x-1/2` + 内层 `p-2 shadow-xl rounded-xl border
 * bg-background/95 supports-[backdrop-filter]:bg-background/60 backdrop-blur-lg`）。
 * 左起：X 清选钮（Tooltip「清除选择 (Esc)」）｜分隔｜计数 Badge +「个容器已选择」｜按钮组。
 * 容器即任务：批量删除（POST /tasks/batch-action 软删进回收站，task:batch）/ 批量收藏
 * （POST /tasks/{id}/favorite 逐容器，task:read）；确认后发请求（INT-949 口径）。
 */
import { LoaderCircle, X } from 'lucide-react'
import { useState } from 'react'

import { usePermissions } from '@/application/hooks/use-permissions'
import { useCherryPickContainerActions } from '@/application/tasks/cherry-pick/use-cherry-pick-container-actions'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { ConfirmDialog } from '@/components/confirm-dialog'
import type { CherryPickContainer } from '@/domain/models/cherryPick'

export function ContainerBulkActions({
  containers,
  selected,
  onClear,
}: {
  /** 当前加载的容器（勾选 id 解析用） */
  containers: CherryPickContainer[]
  /** 勾选容器 id 集（受控） */
  selected: Set<number>
  onClear: () => void
}) {
  const { hasPermission } = usePermissions()
  const actions = useCherryPickContainerActions()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const count = selected.size
  if (count === 0) return null

  const selectedContainers = containers.filter((c) => selected.has(c.id))
  const busy = actions.batchRemove.isPending || actions.batchFavorite.isPending

  const handleConfirmDelete = async () => {
    if (selectedContainers.length === 0) return
    try {
      await actions.batchRemove.mutateAsync(selectedContainers.map((c) => c.id))
      setConfirmDelete(false)
      onClear()
    } catch {
      // mutation onError 已 toast
    }
  }

  return (
    <>
      <div className='fixed bottom-6 left-1/2 z-50 w-max max-w-[calc(100vw-2rem)] -translate-x-1/2'>
        <div className='bg-background/95 supports-[backdrop-filter]:bg-background/60 flex items-center gap-1 rounded-xl border p-2 shadow-xl backdrop-blur-lg'>
          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  variant='ghost'
                  size='icon-sm'
                  aria-label='清除选择 (Esc)'
                  onClick={onClear}
                />
              }
            >
              <X aria-hidden='true' />
            </TooltipTrigger>
            <TooltipContent>清除选择 (Esc)</TooltipContent>
          </Tooltip>
          <Separator orientation='vertical' className='h-5' />
          <Badge className='min-w-8 justify-center rounded-lg'>{count}</Badge>
          <span className='text-sm'>个容器已选择</span>
          <Separator orientation='vertical' className='h-5' />
          {hasPermission('task:read') && (
            <Button
              size='sm'
              variant='outline'
              disabled={busy}
              onClick={() =>
                actions.batchFavorite.mutate(selectedContainers.map((c) => c.id), {
                  onSuccess: () => onClear(),
                })
              }
            >
              {actions.batchFavorite.isPending && (
                <LoaderCircle aria-hidden='true' className='size-3.5 animate-spin' />
              )}
              批量收藏
            </Button>
          )}
          {hasPermission('task:batch') && (
            <Button
              size='sm'
              variant='destructive'
              disabled={busy}
              onClick={() => setConfirmDelete(true)}
            >
              {actions.batchRemove.isPending && (
                <LoaderCircle aria-hidden='true' className='size-3.5 animate-spin' />
              )}
              批量删除
            </Button>
          )}
        </div>
      </div>
      {/* 批量删除确认（INT-949：确认才发请求；取消不发） */}
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={(open) => !open && setConfirmDelete(false)}
        title='批量删除容器'
        desc={`将把 ${count} 个合并容器移入回收站，可在回收站恢复。是否继续？`}
        confirmText='删除'
        destructive
        isLoading={actions.batchRemove.isPending}
        handleConfirm={() => void handleConfirmDelete()}
      />
    </>
  )
}
