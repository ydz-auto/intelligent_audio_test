/**
 * 导出数据弹窗（09_任务域.md §5.12，Dialog sm:max-w-lg）。
 * 选中任务清单（滚动区，名称+状态）+ 选项 Checkbox「包含参考参数文件」（默认勾）/
 * 「包含音频文件（体积较大）」+「开始导出」（进行中「正在打包导出，请稍候…」+ Spinner）。
 * 导出经 infrastructure/api/data-transfer-api（client.ts）POST /data-transfer/export
 * → Blob 下载 task_export_<timestamp>.zip。
 */
import { Download } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Spinner } from '@/components/ui/spinner'
import { exportTasks } from '@/infrastructure/api/data-transfer-api'
import { ApiError } from '@/infrastructure/api/api-error'
import { getExecutionStatusMeta } from '@/features/tasks/constants'

export interface ExportTaskBrief {
  id: number
  name: string
  status: string | null
}

export function DataExportDialog({
  open,
  onOpenChange,
  tasks,
  onExported,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 选中任务清单（§3.10 批量勾选态） */
  tasks: ExportTaskBrief[]
  onExported?: () => void
}) {
  const [includeRefParams, setIncludeRefParams] = useState(true)
  const [includeAudios, setIncludeAudios] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')

  const startExport = async () => {
    if (tasks.length === 0) return
    setErrorMessage('')
    setExporting(true)
    try {
      const blob = await exportTasks(tasks.map((t) => t.id), {
        includeRefParams,
        includeAudios,
      })
      const stamp = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '')
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `task_export_${stamp}.zip`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
      toast.success('导出完成')
      onExported?.()
      onOpenChange(false)
    } catch (error) {
      setErrorMessage(
        error instanceof ApiError ? (error.userMessage || error.message) : '导出失败，请稍后重试'
      )
    } finally {
      setExporting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>导出任务数据</DialogTitle>
          <DialogDescription>导出所选任务的执行数据，打包为 ZIP 下载</DialogDescription>
        </DialogHeader>

        <div className='flex flex-col gap-4'>
          <div className='flex flex-col gap-1.5'>
            <p className='text-sm font-medium'>选中任务（{tasks.length} 个）</p>
            {tasks.length === 0 ? (
              <p className='text-muted-foreground rounded-lg border border-dashed bg-muted/30 px-3 py-5 text-center text-xs'>
                未选中任务
              </p>
            ) : (
              <ScrollArea className='max-h-40 rounded-lg border'>
                <ul className='divide-y divide-border'>
                  {tasks.map((task) => (
                    <li
                      key={task.id}
                      className='flex items-center justify-between gap-2 px-3 py-1.5 text-sm'
                    >
                      <span className='min-w-0 flex-1 truncate'>{task.name}</span>
                      <span className='text-muted-foreground shrink-0 text-xs'>
                        {getExecutionStatusMeta(task.status).label}
                      </span>
                    </li>
                  ))}
                </ul>
              </ScrollArea>
            )}
          </div>

          <div className='flex flex-col gap-1.5'>
            <p className='text-sm font-medium'>导出选项</p>
            <label className='flex cursor-pointer items-center gap-2 text-sm'>
              <Checkbox checked={includeRefParams} onCheckedChange={(v) => setIncludeRefParams(!!v)} />
              包含参考参数文件
            </label>
            <label className='flex cursor-pointer items-center gap-2 text-sm'>
              <Checkbox checked={includeAudios} onCheckedChange={(v) => setIncludeAudios(!!v)} />
              包含音频文件（体积较大）
            </label>
          </div>

          {errorMessage && <p className='text-destructive text-xs'>{errorMessage}</p>}
          {exporting && (
            <p className='text-muted-foreground flex items-center gap-2 text-xs'>
              <Spinner size={14} />
              正在打包导出，请稍候…
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant='outline' disabled={exporting} onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button disabled={exporting || tasks.length === 0} onClick={() => void startExport()}>
            {exporting ? (
              <>
                <Spinner size={14} className='text-current' />
                正在打包导出，请稍候…
              </>
            ) : (
              <>
                <Download aria-hidden='true' className='size-3.5' />
                开始导出
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
