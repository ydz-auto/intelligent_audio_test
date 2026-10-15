/**
 * 实时日志卡（09_任务域.md §4.6，Card）。
 * 容器 `rounded-lg bg-muted/30 p-4 font-mono text-xs leading-6`（代码语义底，双主题同构）；
 * 行 = 时间戳（min-w-[150px]）+ 级别色点 + 内容；级别配色 info=foreground/warn=warning/error=destructive。
 * 虚拟滚动 max-h-[400px]；「滚动到底部」「加载更早日志」「暂无日志」。
 */
import { ArrowDownToLine, ScrollText } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { useTaskLogs } from '@/application/tasks/use-task-detail'
import type { TaskLogEntry } from '@/domain/models/task'

const LEVEL_DOT: Record<TaskLogEntry['level'], string> = {
  info: 'bg-foreground',
  warn: 'bg-warning',
  error: 'bg-destructive',
}

export function RealtimeLogs({ taskId }: { taskId: number }) {
  const logsQuery = useTaskLogs(taskId)
  const [manual, setManual] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }

  // 初始自动滚动到底（演示态；接线后运行中每 10s 轮询增量 append）
  useEffect(() => {
    if (!manual && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [logsQuery.data, manual])

  const logs = logsQuery.data ?? []

  return (
    <Card size='sm' className='gap-3 py-3'>
      <CardHeader className='px-4'>
        <CardTitle className='flex items-center gap-2 text-sm font-medium'>
          <ScrollText aria-hidden='true' className='text-muted-foreground size-4' />
          实时日志
          <span className='text-muted-foreground font-mono text-xs tabular-nums'>
            {logs.length}
          </span>
        </CardTitle>
        <div data-slot='card-action' className='flex items-center'>
          <Button variant='outline' size='sm' className='h-7' onClick={scrollToBottom}>
            <ArrowDownToLine aria-hidden='true' className='size-3.5' />
            滚动到底部
          </Button>
        </div>
      </CardHeader>
      <CardContent className='px-4 pb-1'>
        <div
          ref={scrollRef}
          className='bg-muted/30 max-h-[400px] overflow-y-auto rounded-lg p-4 font-mono text-xs leading-6'
          onScroll={(e) => {
            setManual(e.currentTarget.scrollTop < e.currentTarget.scrollHeight - 400)
          }}
        >
          {logs.length === 0 ? (
            <p className='text-muted-foreground'>暂无日志</p>
          ) : (
            <div className='flex flex-col'>
              {logs.map((entry) => (
                <div key={entry.id} className='flex items-baseline gap-2'>
                  <span className='text-muted-foreground min-w-[150px] shrink-0 whitespace-nowrap'>
                    {entry.timestamp}
                  </span>
                  <span
                    aria-hidden='true'
                    className={cn(
                      'mt-[7px] size-1.5 shrink-0 rounded-full',
                      LEVEL_DOT[entry.level]
                    )}
                  />
                  <span
                    className={cn(
                      'break-all',
                      entry.level === 'error' && 'text-destructive',
                      entry.level === 'warn' && 'text-warning'
                    )}
                  >
                    {entry.message}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className='mt-1.5 flex justify-center pb-3'>
          <Button variant='ghost' size='sm' className='text-muted-foreground h-6 text-xs' onClick={() => {}}>
            加载更早日志
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
