/**
 * 导出报告 Dialog（规范 §4.3/§4.9，report:read）：范围回显（单/批量）+ 格式 Select
 * [CSV·Excel·PDF·HTML] + 说明 + 主钮「导出」（POST /reports/export，zip_base64→Blob）。
 * INT-381 返修：Dialog 内三页签——「导出」（主表单）+「导出进度」（实时进度/状态/错误，
 * 报告管理功能设计文档.md:249-252 实测）+「导出历史」（最近导出=报告/格式/时间/状态，
 * :538-543、:564-568 实测）。
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
import { cn } from '@/lib/utils'

const EXPORT_FORMATS = [
  { value: 'csv', label: 'CSV' },
  { value: 'excel', label: 'Excel' },
  { value: 'pdf', label: 'PDF' },
  { value: 'html', label: 'HTML' },
] as const

interface ExportTask {
  id: number
  scope: string
  format: string
  /** 0-100；100=完成；-1=失败 */
  progress: number
  status: 'running' | 'done' | 'failed'
  error?: string
}

const MOCK_EXPORT_HISTORY = [
  { id: 1, scope: '旗舰音箱全量回归 · 第 3 轮报告', format: 'PDF', time: '2026-10-16 14:20', status: 'done' },
  { id: 2, scope: '已选择 3 个报告', format: 'Excel', time: '2026-10-16 11:02', status: 'done' },
  { id: 3, scope: 'API 通道并发稳定性验证报告', format: 'CSV', time: '2026-10-15 17:45', status: 'failed' },
]

interface ExportReportDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 导出范围描述（单报告名 / 已选择 {n} 个报告） */
  scope: string
  count: number
  onExport: (format: string) => void
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

  // 打开时清空导出进度态
  useEffect(() => {
    if (open) {
      setExporting(false)
      setTask(null)
    }
  }, [open])

  const handleExport = async () => {
    setExporting(true)
    setTask({ id: Date.now(), scope, format, progress: 0, status: 'running' })
    // 模拟进度轮询（mock：200ms 步进 → 100 完成；失败保留上次结果语义）
    let progress = 0
    const timer = setInterval(() => {
      progress = Math.min(100, progress + 22)
      setTask((t) => (t ? { ...t, progress } : t))
      if (progress >= 100) {
        clearInterval(timer)
        setTask((t) => (t ? { ...t, status: 'done' } : t))
        setExporting(false)
        onExport(format)
      }
    }, 220)
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
                      task.status === 'failed' ? 'bg-destructive' : 'bg-primary'
                    )}
                    style={{ width: `${task.progress}%` }}
                  />
                </div>
                <p className='font-mono text-muted-foreground text-xs tabular-nums'>
                  {task.status === 'failed' ? '导出失败：服务端生成异常' : `${task.progress}%`}
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
            {MOCK_EXPORT_HISTORY.length === 0 ? (
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
                  {MOCK_EXPORT_HISTORY.map((item) => (
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
