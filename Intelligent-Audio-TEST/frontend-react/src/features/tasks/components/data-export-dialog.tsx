/**
 * 导出数据弹窗（09_任务域.md §5.12，Dialog sm:max-w-lg）。
 * 两种模式（INT-1765 增量回导 / 链路 2）：
 *
 * - 整包（mode='full'，既有交互不变）：选中任务清单（滚动区，名称+状态）+
 *   「包含参考参数文件」（默认勾）/「包含音频文件（体积较大）」→ POST /data-transfer/export
 *   → 下载 task_export_<timestamp>.zip。
 * - 增量（mode='incremental'）：单任务 + 「评估维度」「报告」两段勾选（默认都勾，照设计文档
 *   §5.2）→ POST /data-transfer/export-incremental → 下载 incremental_<timestamp>.zip。
 *   导出侧硬闸（未映射结果行 / source_map 缺失）失败时展示后端原文 + 可操作引导。
 *
 * 请求一律经 infrastructure/api/data-transfer-api（client.ts）。
 */
import { Download } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
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
import type { IncrementalInclude } from '@/domain/models/data-transfer'
import { exportIncremental, exportTasks } from '@/infrastructure/api/data-transfer-api'
import { ApiError } from '@/infrastructure/api/api-error'
import { getExecutionStatusMeta } from '@/features/tasks/constants'

export type DataExportMode = 'full' | 'incremental'

export interface ExportTaskBrief {
  id: number
  name: string
  status: string | null
}

/** 增量导出失败的可操作引导（按后端失败码/文案区分两条硬闸） */
function incrementalGuidance(error: ApiError): string {
  const message = error.userMessage || error.message || ''
  if (
    message.includes('重新执行') ||
    message.includes('未登记的结果行') ||
    message.includes('unmapped')
  ) {
    return '增量回导 v1 只同步「重新评估」产生的数据。请改用整包导出，或先在 B 侧回退本次重新执行的结果后重试。'
  }
  if (
    message.includes('未整包导入') ||
    message.includes('source_map') ||
    message.includes('映射') ||
    error.httpStatus === 400
  ) {
    return '请先在 B 侧对该任务执行「导入数据」（整包导入，链路 1）完成 source_map 登记，再导出增量。'
  }
  return '请确认该任务由整包导入而来，且源任务仍存在后重试。'
}

export function DataExportDialog({
  open,
  onOpenChange,
  tasks,
  onExported,
  mode = 'full',
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 选中任务清单（§3.10 批量勾选态；增量模式要求恰好 1 个） */
  tasks: ExportTaskBrief[]
  onExported?: () => void
  /** full=整包导出（默认）；incremental=增量导出（链路 2） */
  mode?: DataExportMode
}) {
  const incremental = mode === 'incremental'
  const [includeRefParams, setIncludeRefParams] = useState(true)
  const [includeAudios, setIncludeAudios] = useState(false)
  // 增量导出两段默认都勾（设计文档 §5.2 请求示例）
  const [includeDimensions, setIncludeDimensions] = useState(true)
  const [includeReports, setIncludeReports] = useState(true)
  const [exporting, setExporting] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [errorGuidance, setErrorGuidance] = useState('')

  const includedSegments: IncrementalInclude[] = [
    ...(includeDimensions ? (['dimensions'] as const) : []),
    ...(includeReports ? (['reports'] as const) : []),
  ]
  const canSubmit = incremental
    ? tasks.length === 1 && includedSegments.length > 0
    : tasks.length > 0

  const downloadBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  const startExport = async () => {
    if (!canSubmit) return
    setErrorMessage('')
    setErrorGuidance('')
    setExporting(true)
    const stamp = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '')
    try {
      if (incremental) {
        const blob = await exportIncremental([tasks[0].id], { include: includedSegments })
        downloadBlob(blob, `incremental_${stamp}.zip`)
        toast.success('增量导出完成')
      } else {
        const blob = await exportTasks(tasks.map((t) => t.id), {
          includeRefParams,
          includeAudios,
        })
        downloadBlob(blob, `task_export_${stamp}.zip`)
        toast.success('导出完成')
      }
      onExported?.()
      onOpenChange(false)
    } catch (error) {
      if (error instanceof ApiError) {
        setErrorMessage(error.userMessage || error.message || '导出失败')
        setErrorGuidance(incremental ? incrementalGuidance(error) : '')
      } else {
        setErrorMessage('导出失败，请稍后重试')
        setErrorGuidance('')
      }
    } finally {
      setExporting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>{incremental ? '导出增量数据' : '导出任务数据'}</DialogTitle>
          <DialogDescription>
            {incremental
              ? '把本侧的新评估与最新报告导出为增量包，供回导方合并到原任务（不产生任务副本）'
              : '导出所选任务的执行数据，打包为 ZIP 下载'}
          </DialogDescription>
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
            {incremental && tasks.length !== 1 && (
              <p className='text-muted-foreground text-xs'>
                增量导出只支持单个任务：请先在任务列表勾选 1 个任务。
              </p>
            )}
          </div>

          <div className='flex flex-col gap-1.5'>
            <p className='text-sm font-medium'>导出选项</p>
            {incremental ? (
              <>
                <label className='flex cursor-pointer items-center gap-2 text-sm'>
                  <Checkbox
                    checked={includeDimensions}
                    onCheckedChange={(v) => setIncludeDimensions(!!v)}
                  />
                  评估维度
                </label>
                <label className='flex cursor-pointer items-center gap-2 text-sm'>
                  <Checkbox
                    checked={includeReports}
                    onCheckedChange={(v) => setIncludeReports(!!v)}
                  />
                  报告
                </label>
                {includedSegments.length === 0 && (
                  <p className='text-muted-foreground text-xs'>
                    请至少勾选一项导出内容（评估维度 / 报告）。
                  </p>
                )}
              </>
            ) : (
              <>
                <label className='flex cursor-pointer items-center gap-2 text-sm'>
                  <Checkbox
                    checked={includeRefParams}
                    onCheckedChange={(v) => setIncludeRefParams(!!v)}
                  />
                  包含参考参数文件
                </label>
                <label className='flex cursor-pointer items-center gap-2 text-sm'>
                  <Checkbox
                    checked={includeAudios}
                    onCheckedChange={(v) => setIncludeAudios(!!v)}
                  />
                  包含音频文件（体积较大）
                </label>
              </>
            )}
          </div>

          {errorMessage && (
            <Alert variant='destructive'>
              <AlertTitle>{incremental ? '增量导出失败' : '导出失败'}</AlertTitle>
              <AlertDescription>
                <span>{errorMessage}</span>
                {errorGuidance && (
                  <span className='mt-1 block font-medium'>{errorGuidance}</span>
                )}
              </AlertDescription>
            </Alert>
          )}
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
          <Button disabled={exporting || !canSubmit} onClick={() => void startExport()}>
            {exporting ? (
              <>
                <Spinner size={14} className='text-current' />
                正在打包导出，请稍候…
              </>
            ) : (
              <>
                <Download aria-hidden='true' className='size-3.5' />
                {incremental ? '开始导出增量' : '开始导出'}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
