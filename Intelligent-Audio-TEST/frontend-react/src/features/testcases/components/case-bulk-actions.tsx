/**
 * 用例批量操作浮条（11_用例域.md §3.7 DataTableBulkActions 照搬）：
 * `fixed bottom-6 left-1/2 z-50 w-max max-w-[calc(100vw-2rem)] -translate-x-1/2` +
 * 内层 `p-2 shadow-xl rounded-xl border bg-background/95 supports-[backdrop-filter]:bg-background/60 backdrop-blur-lg`。
 * 左起：X 清选钮（Tooltip「清除选择 (Esc)」）｜分隔｜计数 Badge +「个用例已选择」｜按钮组（按权限过滤）。
 * 普通态：批量设置专属参数/播放设备/声压/噪声/维度/调整分组/管理标签/自动生成名称/刷新参考参数/
 * 批量复制/批量删除；回收站态：批量恢复/批量彻底删除。mock 态动作全部页面级弹窗/toast 演示。
 */
import { X } from 'lucide-react'
import { useEffect, useState } from 'react'

import { usePermissions } from '@/application/hooks/use-permissions'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

export type BatchActionKey =
  | 'dimensions'
  | 'group'
  | 'tags'
  | 'params'
  | 'device'
  | 'spl'
  | 'noise'
  | 'name'
  | 'refresh'
  | 'copy'
  | 'delete'
  | 'restore'
  | 'purge'

export function CaseBulkActions({
  selectedIds,
  onClear,
  trash,
  onBatchAction,
}: {
  selectedIds: string[]
  onClear: () => void
  trash: boolean
  onBatchAction: (action: BatchActionKey, ids: string[]) => void
}) {
  const { hasPermission } = usePermissions()
  const count = selectedIds.length

  // aria-live 播报照搬 newAPI DataTableBulkActions：勾选变化（含 X/ESC 清选）向读屏播报
  const [announcement, setAnnouncement] = useState('')
  useEffect(() => {
    if (count > 0) {
      setAnnouncement(`已选择 ${count} 个用例，批量操作可用`)
      const timer = setTimeout(() => setAnnouncement(''), 3000)
      return () => clearTimeout(timer)
    }
  }, [count])

  if (count === 0) return null

  const canUpdate = hasPermission('testcase:update')
  const canCopy = hasPermission('testcase:copy')
  const canDelete = hasPermission('testcase:delete')

  const actions: Array<{ key: BatchActionKey; label: string; variant?: 'destructive' | 'outline'; renderIf: boolean }> = trash
    ? [
        { key: 'restore', label: '批量恢复', variant: 'outline', renderIf: canDelete },
        { key: 'purge', label: '批量彻底删除', variant: 'destructive', renderIf: canDelete },
      ]
    : [
        { key: 'params', label: '批量设置专属参数', renderIf: canUpdate },
        { key: 'device', label: '批量设置播放设备', renderIf: canUpdate },
        { key: 'spl', label: '批量设置声压', renderIf: canUpdate },
        { key: 'noise', label: '批量设置噪声', renderIf: canUpdate },
        { key: 'dimensions', label: '批量设置维度', renderIf: canUpdate },
        { key: 'group', label: '批量调整分组', renderIf: canUpdate },
        { key: 'tags', label: '批量管理标签', renderIf: canUpdate },
        { key: 'name', label: '自动生成名称', renderIf: canUpdate },
        { key: 'refresh', label: '刷新参考参数', renderIf: canUpdate },
        { key: 'copy', label: '批量复制', variant: 'outline', renderIf: canCopy },
        { key: 'delete', label: '批量删除', variant: 'destructive', renderIf: canDelete },
      ]

  return (
    <>
      {/* Live region for screen reader announcements（照搬 newAPI bulk-actions） */}
      <div
        aria-live='polite'
        aria-atomic='true'
        role='status'
        className='sr-only'
      >
        {announcement}
      </div>
      <div className='fixed bottom-6 left-1/2 z-50 w-max max-w-[calc(100vw-2rem)] -translate-x-1/2'>
        <div className='bg-background/95 supports-backdrop-filter:bg-background/60 flex items-center gap-1 rounded-xl border p-2 shadow-xl backdrop-blur-lg'>
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
          <span className='text-sm'>个用例已选择</span>
          <Separator orientation='vertical' className='h-5' />
          {actions
            .filter((a) => a.renderIf)
            .map((action) => (
              <Button
                key={action.key}
                size='sm'
                variant={action.variant ?? 'outline'}
                onClick={() => onBatchAction(action.key, selectedIds)}
              >
                {action.label}
              </Button>
            ))}
        </div>
      </div>
    </>
  )
}
