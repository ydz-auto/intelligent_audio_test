/**
 * 实时日志卡（09_任务域.md §4.6，Card）。
 * 容器 `rounded-lg bg-muted/30 p-4 font-mono text-xs leading-6`（代码语义底，双主题同构）；
 * 行 = 时间戳（min-w-[150px]）+ 级别色点 + 内容；级别配色 info=foreground/warn=warning/error=destructive。
 * 虚拟滚动 max-h-[400px]；「滚动到底部」「加载更早日志」「暂无日志」。
 * execution 模式（10_测试执行.md §3.7 差异注入）：①级别过滤（全部/INFO/WARN/ERROR）
 * ②关键词搜索（高亮匹配行）③导出完整日志 + Realtime frame 增量内容条（websocket_api 设备时）。
 */
import { ArrowDownToLine, FileDown, ScrollText, Search } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Progress } from '@/features/tasks/components/ui/progress'
import { cn } from '@/lib/utils'
import { useTaskLogs } from '@/application/tasks/use-task-detail'
import { useRealtimeFrameStream } from '@/infrastructure/realtime/frame-channel'
import type { TaskLogEntry } from '@/domain/models/task'

const LEVEL_DOT: Record<TaskLogEntry['level'], string> = {
  info: 'bg-foreground',
  warn: 'bg-warning',
  error: 'bg-destructive',
}

type LogLevelFilter = 'all' | TaskLogEntry['level']

export function RealtimeLogs({
  taskId,
  executionMode = false,
  hasRealtimeDevice = false,
}: {
  taskId: number
  /** execution 模式：注入级别过滤/关键词搜索/导出 + Realtime frame 增量条（10_测试执行.md §3.7） */
  executionMode?: boolean
  hasRealtimeDevice?: boolean
}) {
  const logsQuery = useTaskLogs(taskId)
  const [manual, setManual] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const [levelFilter, setLevelFilter] = useState<LogLevelFilter>('all')
  const [keyword, setKeyword] = useState('')
  const frames = useRealtimeFrameStream(executionMode && hasRealtimeDevice)

  const scrollToBottom = () => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }

  // 初始自动滚动到底（演示态；接线后运行中每 10s 轮询增量 append）
  useEffect(() => {
    if (!manual && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [logsQuery.data, manual, frames])

  const logs = logsQuery.data ?? []

  /** 级别过滤 + 关键词搜索（匹配行保留；关键词命中加高亮） */
  const filteredLogs = useMemo(() => {
    const q = keyword.trim().toLowerCase()
    return logs.filter((entry) => {
      if (levelFilter !== 'all' && entry.level !== levelFilter) return false
      if (q && !entry.message.toLowerCase().includes(q)) return false
      return true
    })
  }, [logs, levelFilter, keyword])

  const highlight = (message: string) => {
    if (!keyword.trim()) return message
    const lower = message.toLowerCase()
    const idx = lower.indexOf(keyword.trim().toLowerCase())
    if (idx === -1) return message
    return (
      <>
        {message.slice(0, idx)}
        <mark className='bg-warning/30 rounded-[2px]'>{message.slice(idx, idx + keyword.length)}</mark>
        {message.slice(idx + keyword.length)}
      </>
    )
  }

  /** Realtime frame 增量内容条（§3.7：文字流逐段 append + 音频进度条） */
  const latestAudio = frames.find((f) => f.kind === 'audio_delta' && f.audioProgress != null)
  const latestText = frames
    .filter((f) => f.kind === 'text_delta' && f.textDelta)
    .map((f) => f.textDelta)
    .join('')

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
        <div data-slot='card-action' className='flex items-center gap-1.5'>
          {executionMode && (
            <>
              <Select
                value={levelFilter}
                onValueChange={(v) => setLevelFilter((v ?? 'all') as LogLevelFilter)}
              >
                <SelectTrigger className='h-7 w-28 text-xs'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='all'>全部</SelectItem>
                  <SelectItem value='info'>INFO</SelectItem>
                  <SelectItem value='warn'>WARN</SelectItem>
                  <SelectItem value='error'>ERROR</SelectItem>
                </SelectContent>
              </Select>
              <div className='relative'>
                <Search
                  aria-hidden='true'
                  className='text-muted-foreground absolute start-2 top-1/2 size-3.5 -translate-y-1/2'
                />
                <Input
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                  placeholder='搜索日志内容'
                  className='h-7 w-40 ps-7 text-xs'
                />
              </div>
              <Button
                variant='outline'
                size='sm'
                className='h-7 gap-1 text-xs'
                onClick={() => {}}
                title='生成 .log 文件下载（Realtime 帧流事件不入导出文件，仅落库日志行导出）'
              >
                <FileDown aria-hidden='true' className='size-3.5' />
                导出完整日志
              </Button>
            </>
          )}
          <Button variant='outline' size='sm' className='h-7' onClick={scrollToBottom}>
            <ArrowDownToLine aria-hidden='true' className='size-3.5' />
            滚动到底部
          </Button>
        </div>
      </CardHeader>
      <CardContent className='px-4 pb-1'>
        {/* Realtime frame 增量内容条（websocket_api 设备时渲染） */}
        {executionMode && hasRealtimeDevice && (
          <div className='border-border/70 bg-background/95 ring-foreground/5 mb-3 rounded-lg border p-3 ring-1'>
            <div className='mb-1 flex items-center gap-1.5 text-xs font-medium'>
              <span className='bg-info/15 text-info size-1.5 rounded-full' />
              实时内容流
              {latestText && (
                <span className='text-muted-foreground font-normal'>
                  {frames.length} 帧 · 累计 {latestText.length} 字
                </span>
              )}
            </div>
            {latestText ? (
              <p className='min-h-5 text-sm leading-6'>
                {latestText}
                <span className='bg-primary/40 ml-0.5 inline-block h-4 w-0.5 animate-pulse align-middle' />
              </p>
            ) : (
              <p className='text-muted-foreground min-h-5 text-sm'>等待音频输入…</p>
            )}
            {latestAudio && (
              <div className='mt-2 flex items-center gap-2'>
                <span className='text-muted-foreground text-xs'>音频播放</span>
                <Progress value={latestAudio.audioProgress ?? 0} size='sm' className='h-1.5 flex-1' />
                <span className='text-muted-foreground font-mono text-xs tabular-nums'>
                  {latestAudio.audioProgress ?? 0}%
                </span>
              </div>
            )}
          </div>
        )}

        <div
          ref={scrollRef}
          className='bg-muted/30 max-h-[400px] overflow-y-auto rounded-lg p-4 font-mono text-xs leading-6'
          onScroll={(e) => {
            setManual(e.currentTarget.scrollTop < e.currentTarget.scrollHeight - 400)
          }}
        >
          {filteredLogs.length === 0 ? (
            <p className='text-muted-foreground'>暂无日志</p>
          ) : (
            <div className='flex flex-col'>
              {filteredLogs.map((entry) => (
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
                    {highlight(entry.message)}
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

