/**
 * 任务名称弹窗（§5.1；interfaces/features/test-execution/modals；newAPI Dialog 基元）。
 * 字段：任务名称*（Input maxlength 50，默认预填「E2E测试任务_{YYYY-MM-DD HH:mm}」）；
 * 说明行 + 执行摘要一行；主钮「开始测试」（进行中「正在启动…」+ Loader）——
 * 确认即创建+启动+跳 step=3（useTestLaunch.launch）。
 */
import { useState } from 'react'

import { useTestLaunch } from '@/application/test-execution/useTestLaunch'
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
  type: 'e2e' | 'api'
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
  type,
  algorithmType,
  caseCount,
  deviceCount,
  apiCount,
  deviceIds,
  apiIds,
  params,
}: TaskNameDialogProps) {
  const { defaultTaskName, launch } = useTestLaunch()
  const [name, setName] = useState(() => defaultTaskName(type))
  const [starting, setStarting] = useState(false)

  // open 变更时重置默认名称
  const handleOpenChange = (next: boolean) => {
    if (next) setName(defaultTaskName(type))
    onOpenChange(next)
  }

  const summary =
    type === 'e2e'
      ? `${caseCount} 条 · ${deviceCount} 台 · 并发 ${params.concurrency}`
      : `${caseCount} 条 · ${apiCount} 个 · 并发 ${apiCount === 0 ? 0 : params.concurrency}`

  /** 任务 device_types（混跑语义：E2E 含 http_api/websocket_api 网关；API 页为 http_api） */
  const deviceTypes = type === 'e2e'
    ? ['smart_speaker', 'http_api', 'websocket_api']
    : ['http_api']

  const handleStart = async () => {
    if (!name.trim()) return
    setStarting(true)
    try {
      await launch(name.trim(), {
        type,
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
