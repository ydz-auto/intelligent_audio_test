/**
 * 清除日志弹窗（interfaces 层；17_配置运维.md §7.10，Dialog sm:max-w-md，
 * log:manage + destructive）。
 * 「清除 {datetime-local} 之前」的日志（默认空=全部）+「保留已标记日志」Switch
 * （keepMarked 默认开）+ 说明「清除操作不可恢复。」→ POST /logs/clear
 * {before_datetime, keep_marked}。
 * 确认文案的估算只描述清除范围（全部 / 某时间点之前），**不跟随列表筛选**：
 * POST /logs/clear 不接收分类/级别/关键词等筛选参数（INT-1654）。
 */
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'

export type ClearLogsDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  /**
   * 清除范围估算条数（由页面按「无筛选 + 时间点」另发统计，`undefined` = 统计未就绪；
   * 不要传列表统计，它跟随筛选，与实际清除范围无关）
   */
  estimatedCount?: number
  /** datetime-local 值（页面持有：估算查询需要它，`` 表示清除全部） */
  before: string
  onBeforeChange: (value: string) => void
  onClear: (beforeDatetime: string | null, keepMarked: boolean) => void
  isPending: boolean
}

/** datetime-local 的 `YYYY-MM-DDTHH:mm` → `YYYY-MM-DD HH:mm`（展示用） */
function formatBefore(value: string): string {
  return value.replace('T', ' ')
}

export function ClearLogsDialog(props: ClearLogsDialogProps) {
  const [keepMarked, setKeepMarked] = useState(true)

  // 关闭时重置（下次打开回到默认空时间 + 保留已标记开）
  const handleOpenChange = (open: boolean) => {
    if (!open) {
      props.onBeforeChange('')
      setKeepMarked(true)
    }
    props.onOpenChange(open)
  }

  const handleConfirm = () => {
    props.onClear(props.before || null, keepMarked)
  }

  const hasEstimate = typeof props.estimatedCount === 'number'

  return (
    <Dialog open={props.open} onOpenChange={handleOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>清除日志</DialogTitle>
          <DialogDescription>清除操作不可恢复。</DialogDescription>
        </DialogHeader>

        <div className='grid gap-3'>
          <div className='grid gap-1.5'>
            <Label htmlFor='log-clear-before'>清除此时间之前的日志</Label>
            <Input
              id='log-clear-before'
              type='datetime-local'
              value={props.before}
              onChange={(e) => props.onBeforeChange(e.target.value)}
              className='font-mono text-xs'
            />
            <p className='text-muted-foreground text-xs'>留空表示清除全部日志</p>
          </div>

          <div className='flex items-center justify-between gap-2'>
            <div>
              <Label htmlFor='log-clear-keep-marked'>保留已标记日志</Label>
              <p className='text-muted-foreground text-xs'>已标记的日志不会被清除</p>
            </div>
            <Switch
              id='log-clear-keep-marked'
              checked={keepMarked}
              onCheckedChange={setKeepMarked}
              aria-label='保留已标记日志'
            />
          </div>

          {/* §4.7 确认文案：范围 = 全部 / 时间点之前（与列表筛选无关；保留已标记 {m} 条——后端暂不返回已标记计数） */}
          <div className='grid gap-1'>
            <p className='text-muted-foreground text-xs'>
              将清除
              {props.before
                ? ` ${formatBefore(props.before)} 之前的`
                : '全部'}
              日志
              {hasEstimate ? (
                <>
                  ，约{' '}
                  <span className='text-foreground tabular-nums'>
                    {props.estimatedCount?.toLocaleString()}
                  </span>{' '}
                  条
                </>
              ) : null}
              {keepMarked ? '（保留已标记日志不受影响）' : '（含已标记日志）'}，确定吗？
            </p>
            <p className='text-muted-foreground text-xs'>
              清除范围与列表筛选条件无关
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant='outline'
            size='sm'
            onClick={() => handleOpenChange(false)}
          >
            取消
          </Button>
          <Button
            variant='destructive'
            size='sm'
            disabled={props.isPending}
            onClick={handleConfirm}
          >
            {props.isPending ? '清除中…' : '清除'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
