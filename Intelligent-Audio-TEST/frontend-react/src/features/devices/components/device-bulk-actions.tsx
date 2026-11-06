/**
 * 设备批量操作浮条（16_设备域.md §3.8；DataTableBulkActions 照搬）。
 * 勾选行或开启批量模式后出现（floating bottom）：X 清选 + 计数 Badge +「{设备/API} {n} 个已选择」
 * + 按钮组（按页签与权限过滤）：
 * - 测试设备：连接/断开/重启/关机/健康检查/删除（POST /test-devices/batch；delete 前端串行 §11-7）
 * - 播放设备：删除（串行 DELETE /playback-devices/{id}）
 * - 测试 API：删除（串行 DELETE /apis/{id}）
 * 批量执行前 ConfirmDialog（§3.8）；删除类按钮 destructive。
 */
import { X } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { DevicesTabKey } from '@/features/devices/constants'

export interface DeviceBulkActionsProps {
  tab: DevicesTabKey
  count: number
  canControl: boolean
  canDelete: boolean
  onClear: () => void
  onAction: (action: string) => void
}

export function DeviceBulkActions(props: DeviceBulkActionsProps) {
  if (props.count === 0) return null
  const label = props.tab === 'api' ? 'API' : '设备'
  const outlineAction = (
    label: string,
    action: string,
    disabled = false
  ) => (
    <Button
      variant='outline'
      size='sm'
      className='h-8 gap-1 text-xs'
      disabled={disabled}
      onClick={() => props.onAction(action)}
    >
      {label}
    </Button>
  )

  return (
    // P2-10 返修：§3.8「fixed bottom-6 left-1/2 z-50 -translate-x-1/2」悬浮层（照 audio-bulk-actions 同款）
    <div className='fixed bottom-6 left-1/2 z-50 w-max max-w-[calc(100vw-2rem)] -translate-x-1/2'>
      <div className='shadow-xl flex items-center justify-between gap-2 rounded-xl border bg-background/95 p-2 backdrop-blur-lg'>
        <span className='flex min-w-0 items-center gap-1.5 px-1 text-sm'>
          <Button
            variant='ghost'
            size='icon-sm'
            aria-label='清空选择'
            className='size-6'
            onClick={props.onClear}
          >
            <X aria-hidden='true' className='size-3.5' />
          </Button>
          <Badge variant='secondary' className='rounded-md px-1.5 font-normal tabular-nums'>
            {props.count}
          </Badge>
          <span className='text-muted-foreground truncate text-xs'>
            {label} {props.count} 个已选择
          </span>
        </span>
        <span className='flex shrink-0 flex-wrap items-center justify-end gap-1.5'>
          {props.tab === 'test' && props.canControl && (
            <>
              {outlineAction('连接', 'connect')}
              {outlineAction('断开', 'disconnect')}
              {outlineAction('重启', 'reboot')}
              {outlineAction('关机', 'shutdown')}
              {outlineAction('健康检查', 'health_check')}
            </>
          )}
          {props.canDelete && (
            <Button
              variant='destructive'
              size='sm'
              className='h-8 gap-1 text-xs'
              onClick={() => props.onAction('delete')}
            >
              删除
            </Button>
          )}
        </span>
      </div>
    </div>
  )
}
