/**
 * 导出报告 Dialog（规范 §4.3/§4.9，report:read）：范围回显（单/批量）+ 格式 Select
 * [CSV·Excel·PDF·HTML] + 说明 + 主钮「导出」（POST /reports/export，zip_base64→Blob）。
 * INT-381 返修：Dialog 内三页签——「导出」（主表单）+「导出进度」（实时进度/状态/错误，
 * 报告管理功能设计文档.md:249-252 实测）+「导出历史」（最近导出=报告/格式/时间/状态，
 * :538-543、:564-568 实测）。
 * INT-1547 P2-4：删除写死的 MOCK_EXPORT_HISTORY 与前端模拟步进进度——
 * 进度以后端 POST /reports/export 实际完成为准；导出历史只记录本次会话真实发起的导出
 * （后端无历史接口，见 FEAT INT-1555）。
 */
import { Download } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs'
import { ApiError } from '@/infrastructure/api/api-error'
import { cn } from '@/lib/utils'

const EXPORT_FORMATS = [
  { value: 'csv', label: 'CSV' },
  { value: 'excel', label: 'Excel' },
  { value: 'pdf', label: 'PDF' },
  { value: 'html', label: 'HTML' },
] as const

function formatLabel(value: string): string {
  return EXPORT_FORMATS.find((item) => item.value === value)?.label ?? value
}

interface ExportTask {
  id: number
  scope: string
  format: string
  /** 0-100；100=完成；-1=失败 */
  progress: number
  status: 'running' | 'done' | 'failed'
  error?: string
}

/** 本次会话真实发起的导出记录（非 mock：无后端历史接口，FEAT INT-1555） */
interface ExportHistoryRecord {
  id: number
  scope: string
  format: string
  time: string
  status: 'done' | 'failed'
}

function nowLabel(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function errorMessage(err: unknown): string {
  if (err instanceof ApiError && err.userMessage) return err.userMessage
  if (err instanceof Error && err.message) return err.message
  return '导出失败，请重试'
}

interface ExportReportDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 导出范围描述（单报告名 / 已选择 {n} 个报告） */
  scope: string
  count: number
  /** 真实导出（POST /reports/export）；resolve 即后端已生成文件，reject 即失败 */
  onExport: (format: string) => Promise<void> | void
}

export function ExportReportDialog({
  open,
  onOpenChange,
  scope,
  count,
  onExport,
}: ExportReportDialogProps) {
  const [format, setFormat] = useState<string>('csv')
  const [exporting, setExporting] = useState(false)
  const [task, setTask] = useState<ExportTask | null>(null)
  const [history, setHistory] = useState<ExportHistoryRecord[]>([])

  // 打开时清空导出进度态（历史保留本次会话记录）
  useEffect(() => {
    if (open) {
      setExporting(false)
      setTask(null)
    }
  }, [open])

  const handleExport = async () => {
    const taskId = Date.now()
    const startedAt = nowLabel()
    setExporting(true)
    setTask({ id: taskId, scope, format, progress: 0, status: 'running' })
    try {
      await onExport(format)
      setTask((t) => (t ? { ...t, progress: 100, status: 'done' } : t))
      setHistory((prev) => [
        { id: taskId, scope, format: formatLabel(format), time: startedAt, status: 'done' },
        ...prev,
      ])
    } catch (err) {
      const message = errorMessage(err)
      setTask((t) => (t ? { ...t, status: 'failed', error: message } : t))
      setHistory((prev) => [
        { id: taskId, scope, format: formatLabel(format), time: startedAt, status: 'failed' },
        ...prev,
      ])
    } finally {
      setExporting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>导出报告</DialogTitle>
          <DialogDescription>
            导出内容为报告落库数据的快照，由后端统一生成，前端不做二次计算。
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue='export'>
          <TabsList className='mb-3 h-8'>
            <TabsTrigger value='export'>导出</TabsTrigger>
            <TabsTrigger value='progress'>导出进度</TabsTrigger>
            <TabsTrigger value='history'>导出历史</TabsTrigger>
          </TabsList>

          <TabsContent value='export'>
            <div className='space-y-4'>
              <div className='flex items-center gap-2'>
                <Badge variant='secondary'>{count} 个报告</Badge>
                <span className='text-muted-foreground truncate text-sm'>{scope}</span>
              </div>
              <div className='space-y-2'>
                <span className='text-sm font-medium'>格式</span>
                <Select value={format} onValueChange={(value) => setFormat(value ?? 'csv')}>
                  <SelectTrigger className='w-full justify-between'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {EXPORT_FORMATS.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </TabsContent>

          <TabsContent value='progress'>
            {task ? (
              <div className='space-y-3'>
                <div className='flex items-center justify-between gap-2 text-sm'>
                  <span className='truncate'>{task.scope}</span>
                  <Badge
                    variant={
                      task.status === 'done'
                        ? 'secondary'
                        : task.status === 'failed'
                          ? 'destructive'
                          : 'outline'
                    }
                  >
                    {task.status === 'done' ? '完成' : task.status === 'failed' ? '失败' : '处理中'}
                  </Badge>
                </div>
                <div className='bg-muted h-2 overflow-hidden rounded-full'>
                  <div
                    className={cn(
                      'h-full rounded-full transition-all duration-200',
                      task.status === 'failed' ? 'bg-destructive' : 'bg-primary',
                      // 后端同步生成、无分段进度：处理中显示脉冲满条，完成才落 100%
                      task.status === 'running' && 'w-full animate-pulse opacity-60'
                    )}
                    style={task.status === 'running' ? undefined : { width: `${task.progress}%` }}
                  />
                </div>
                <p className='font-mono text-muted-foreground text-xs tabular-nums'>
                  {task.status === 'failed'
                    ? `导出失败：${task.error ?? '服务端生成异常'}`
                    : task.status === 'done'
                      ? '100% · 文件已下载'
                      : `处理中 · ${formatLabel(task.format)} · 等待后端生成`}
                </p>
                {task.status === 'failed' && (
                  <Button size='sm' variant='outline' onClick={() => setTask(null)}>
                    重试
                  </Button>
                )}
              </div>
            ) : (
              <p className='text-muted-foreground py-6 text-center text-sm'>
                暂无进行中的导出任务
              </p>
            )}
          </TabsContent>

          <TabsContent value='history'>
            {history.length === 0 ? (
              <p className='text-muted-foreground py-6 text-center text-sm'>暂无导出历史</p>
            ) : (
              <table className='w-full text-sm'>
                <thead className='bg-muted/40 text-muted-foreground text-xs'>
                  <tr>
                    <th className='px-3 py-2 text-start font-medium'>报告</th>
                    <th className='px-3 py-2 text-start font-medium'>格式</th>
                    <th className='px-3 py-2 text-start font-medium'>时间</th>
                    <th className='px-3 py-2 text-start font-medium'>状态</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((item) => (
                    <tr key={item.id} className='hover:bg-muted/30 border-t first:border-t-0'>
                      <td className='max-w-[180px] truncate px-3 py-2'>{item.scope}</td>
                      <td className='px-3 py-2'>{item.format}</td>
                      <td className='font-mono px-3 py-2 text-xs tabular-nums'>{item.time}</td>
                      <td className='px-3 py-2'>
                        <Badge variant={item.status === 'done' ? 'secondary' : 'destructive'}>
                          {item.status === 'done' ? '成功' : '失败'}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </TabsContent>
        </Tabs>

        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button disabled={exporting} onClick={() => void handleExport()}>
            <Download data-icon='inline-start' />
            {exporting ? '导出中...' : '导出'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
