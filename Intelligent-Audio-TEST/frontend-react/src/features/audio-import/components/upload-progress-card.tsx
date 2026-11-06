/**
 * 上传进度卡（§5.4 UploadProgressCard 平移换壳，newAPI Card/Progress/Button + sonner）。
 * 有活跃上传任务时固定于内容区顶部；多任务入队 + 暂停/继续/取消/优先级（audio-upload-store）；
 * 进度取自真实分片上传链路回调（INT-1512：不再本地定时推进，速率/预计剩余为实测值）。
 * 状态文案分档 §5.4 progressStatusText。
 */
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import {
  useAudioUploadStore,
  type AudioUploadTask,
} from '@/infrastructure/stores/audio-upload-store'

function progressStatusText(progress: number): string {
  if (progress <= 2) return '准备中...'
  if (progress < 90) return '正在上传文件...'
  if (progress < 100) return '正在合并文件...'
  return '导入完成'
}

function UploadTaskCard({ task }: { task: AudioUploadTask }) {
  const setPaused = useAudioUploadStore((s) => s.setPaused)
  const cancelTask = useAudioUploadStore((s) => s.cancelTask)
  const setPriority = useAudioUploadStore((s) => s.setPriority)
  const retryFailed = useAudioUploadStore((s) => s.retryFailed)
  const ignoreFailed = useAudioUploadStore((s) => s.ignoreFailed)
  const clearTask = useAudioUploadStore((s) => s.clearTask)

  const done = task.progress >= 100
  const successCount = task.files.filter((f) => f.status === 'success').length
  const failedCount = task.files.filter((f) => f.status === 'failed').length

  return (
    <div className='bg-card ring-foreground/10 rounded-xl p-3 ring-1 sm:p-4'>
      <div className='flex flex-wrap items-center gap-2'>
        <span className='min-w-0 flex-1 truncate text-sm font-medium'>
          {task.name}
        </span>
        <Select
          value={String(task.priority)}
          onValueChange={(value) =>
            setPriority(task.id, Number(value) as 1 | 2 | 3)
          }
        >
          <SelectTrigger size='sm' className='h-7 w-28' aria-label='任务优先级'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='1'>优先级：高</SelectItem>
            <SelectItem value='2'>优先级：中</SelectItem>
            <SelectItem value='3'>优先级：低</SelectItem>
          </SelectContent>
        </Select>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={<Button variant='outline' size='sm' className='h-7 px-2.5' />}
          >
            队列控制
          </DropdownMenuTrigger>
          <DropdownMenuContent align='end' className='w-44'>
            <DropdownMenuItem
              disabled={done}
              onClick={() => {
                setPaused(task.id, !task.paused)
                toast.success(task.paused ? '已继续上传' : '已暂停上传')
              }}
            >
              {task.paused ? '继续' : '暂停'}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => cancelTask(task.id)}>
              取消
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* 总体进度（§5.4：h-1.5） */}
      <div className='bg-muted mt-3 h-1.5 w-full overflow-hidden rounded-full'>
        <div
          className='bg-primary h-full rounded-full transition-all duration-200'
          style={{ width: `${task.progress}%` }}
        />
      </div>
      <div className='text-muted-foreground mt-1.5 flex items-center gap-2 text-xs'>
        <span>{progressStatusText(task.progress)}</span>
        <span className='ml-auto font-mono tabular-nums'>
          {Math.round(task.progress)}%
        </span>
      </div>

      {/* 当前文件行（实测导入速度/预计剩余时间；速率未算出前不显示估算值） */}
      {task.currentFile && !done && (
        <div className='bg-muted/40 mt-2 flex flex-wrap items-center gap-2 rounded-md px-2.5 py-1.5 text-xs'>
          <span className='min-w-0 flex-1 truncate'>{task.currentFile.name}</span>
          {task.speed > 0 && (
            <span className='text-muted-foreground font-mono tabular-nums'>
              {task.speed.toFixed(1)} MB/s
            </span>
          )}
          {task.speed > 0 && (
            <span className='text-muted-foreground font-mono tabular-nums'>
              预计剩余 {task.etaSeconds}s
            </span>
          )}
        </div>
      )}

      {/* 文件明细（成功/失败文件数徽章） */}
      <div className='mt-2 flex flex-wrap gap-1'>
        <Badge variant='outline' className='gap-1 rounded-md px-1.5 font-normal'>
          成功
          <span className='font-mono tabular-nums'>{successCount}</span>
        </Badge>
        {failedCount > 0 && (
          <Badge
            variant='outline'
            className='gap-1 rounded-md px-1.5 font-normal text-[var(--destructive)]'
          >
            失败
            <span className='font-mono tabular-nums'>{failedCount}</span>
          </Badge>
        )}
        <span className='text-muted-foreground ml-auto font-mono text-xs tabular-nums'>
          {task.files.length} 个文件
        </span>
      </div>

      {/* 底部按钮 */}
      <div className='mt-3 flex flex-wrap items-center justify-end gap-2'>
        {done ? (
          <Button
            size='sm'
            onClick={() => {
              clearTask(task.id)
              toast.success('导入任务已关闭')
            }}
          >
            完成并关闭
          </Button>
        ) : (
          <>
            <Button
              variant='ghost'
              size='sm'
              onClick={() => {
                cancelTask(task.id)
                toast.success('上传已取消')
              }}
            >
              取消上传
            </Button>
            {failedCount > 0 && (
              <Button
                variant='outline'
                size='sm'
                onClick={() => {
                  retryFailed(task.id)
                  toast.success(`已重试 ${failedCount} 个失败文件`)
                }}
              >
                重试失败文件({failedCount})
              </Button>
            )}
            {failedCount > 0 && (
              <Button
                variant='ghost'
                size='sm'
                onClick={() => {
                  ignoreFailed(task.id)
                  toast.success('已忽略失败文件')
                }}
              >
                忽略失败文件
              </Button>
            )}
            <Button
              variant='outline'
              size='sm'
              className={cn(task.paused && 'opacity-100')}
              onClick={() => {
                setPaused(task.id, !task.paused)
                toast.success(task.paused ? '已继续上传' : '已暂停上传')
              }}
            >
              {task.paused ? '继续' : '暂停'}
            </Button>
          </>
        )}
      </div>
    </div>
  )
}

/** 上传进度卡容器（消费 audio-upload-store；有活跃任务时显，§5.4） */
export function UploadProgressCard() {
  const tasks = useAudioUploadStore((s) => s.tasks)

  if (tasks.length === 0) return null

  return (
    <div className='space-y-2'>
      {tasks.map((task) => (
        <UploadTaskCard key={task.id} task={task} />
      ))}
    </div>
  )
}
