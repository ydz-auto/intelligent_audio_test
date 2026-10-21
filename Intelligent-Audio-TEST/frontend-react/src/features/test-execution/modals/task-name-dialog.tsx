/**
 * 任务名称弹窗（§5.1；interfaces/features/test-execution/modals；newAPI Dialog 基元）。
 * 字段：任务名称*（Input maxlength 50，默认预填「测试任务_{YYYY-MM-DD HH:mm}」）；
 * 说明行 + 执行摘要一行；主钮「开始测试」（进行中「正在启动…」+ Loader）——
 * 确认即创建+启动+跳 step=3（useTestLaunch.launch）。
 * INT-486 2026-10-16 口径：设备+API 混合执行，摘要含设备/API 双计数。
 * INT-1119 2026-10-21：摘要存在串行目标时附「· 串行 {s} 个目标」，全并行时省略（§5.1）。
 */
import { useState } from 'react'

import { useTestLaunch } from '@/application/test-execution/useTestLaunch'
import { useTargetModes } from '@/application/test-execution/useTargetModes'
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
import { Spinner } from '@/components/ui/spinner'
import type { ExecutionParams } from '@/domain/models/testExecution'

interface TaskNameDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  algorithmType: string | null | undefined
  caseCount: number
  deviceCount: number
  apiCount: number
  deviceIds: number[]
  apiIds: number[]
  params: ExecutionParams
}

export function TaskNameDialog({
  open,
  onOpenChange,
  algorithmType,
  caseCount,
  deviceCount,
  apiCount,
  deviceIds,
  apiIds,
  params,
}: TaskNameDialogProps) {
  const { defaultTaskName, launch } = useTestLaunch()
  const { serialCount } = useTargetModes()
  const [name, setName] = useState(() => defaultTaskName())
  const [starting, setStarting] = useState(false)

  // open 变更时重置默认名称
  const handleOpenChange = (next: boolean) => {
    if (next) setName(defaultTaskName())
    onOpenChange(next)
  }

  // §5.1 摘要：存在串行目标时附「· 串行 {s} 个目标」，全并行时省略
  const summary = `${caseCount} 条 · ${deviceCount} 台 · ${apiCount} 个 · 并发 ${params.concurrency}${
    serialCount > 0 ? ` · 串行 ${serialCount} 个目标` : ''
  }`

  /** 任务 device_types（混跑语义：设备 + HTTP API + Realtime WS 网关全链） */
  const deviceTypes = ['smart_speaker', 'http_api', 'websocket_api']

  const handleStart = async () => {
    if (!name.trim()) return
    setStarting(true)
    try {
      await launch(name.trim(), {
        algorithmType,
        deviceIds,
        apiIds,
        deviceTypes,
        params,
      })
      onOpenChange(false)
    } finally {
      setStarting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className='sm:max-w-sm'>
        <DialogHeader>
          <DialogTitle>任务名称</DialogTitle>
          <DialogDescription>
            请输入一个描述性的任务名称，便于后续查看测试结果
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-3'>
          <div className='space-y-1.5'>
            <Label htmlFor='task-name'>任务名称 *</Label>
            <Input
              id='task-name'
              value={name}
              maxLength={50}
              onChange={(e) => setName(e.target.value)}
              placeholder='请输入任务名称'
            />
          </div>
          <p className='text-muted-foreground text-xs'>{summary}</p>
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)} disabled={starting}>
            取消
          </Button>
          <Button disabled={!name.trim() || starting} onClick={() => void handleStart()}>
            {starting ? (
              <>
                <Spinner className='size-3.5' />
                正在启动…
              </>
            ) : (
              '开始测试'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
