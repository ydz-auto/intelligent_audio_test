/**
 * 导出面板（interfaces 层 ai-chat/studio；INT-2473，设计文档 §15.5 / §15.6）。
 * 固定当前文档版本 + 格式创建异步导出作业，轮询进度（pending/running → done/failed），
 * 完成后鉴权下载产物；失败显示后端原因并可单次重试。按钮在作业在途时禁用（防重复）。
 * 格式：PDF / PPTX / HTML / MD（PDF/PPTX 依赖 report_service 渲染器，未部署时
 * 后端返回失败态，本面板原样展示，不吞错）。
 */
import { Check, Download, FileDown, Loader2, X } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import {
  STUDIO_EXPORT_FORMATS,
  STUDIO_EXPORT_FORMAT_LABEL,
  STUDIO_EXPORT_STATUS_LABEL,
  StudioExportStatus,
  isStudioExportActive,
  type StudioExportFormat,
} from '@/domain/models/report-studio'
import {
  useCreateStudioExportJob,
  useStudioExportJob,
} from '@/application/reports/use-report-studio'
import { resolveApiErrorMessage } from '@/features/ai-chat/lib/api-error-message'
import { downloadStudioExportBlob } from '@/infrastructure/api/reportStudioApi'

type ExportPanelProps = {
  docId: string
  docTitle: string
  version: number
  canExport: boolean
  open: boolean
  onOpenChange: (open: boolean) => void
}

/** 下载文件名（后端文件名为 export_id，页面按文档标题 + 版本给出可读名） */
function buildFileName(title: string, version: number, format: string): string {
  const safeTitle = (title || 'report-studio').replace(/[\\/:*?"<>|]/g, '_')
  return `${safeTitle}-v${version}.${format}`
}

export function ExportPanel({
  docId,
  docTitle,
  version,
  canExport,
  open,
  onOpenChange,
}: ExportPanelProps) {
  const [format, setFormat] = useState<StudioExportFormat>('pdf')
  const [exportId, setExportId] = useState<string | null>(null)
  const [isDownloading, setIsDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState<string | null>(null)

  const createExport = useCreateStudioExportJob()
  const jobQuery = useStudioExportJob(exportId)
  const job = jobQuery.data ?? null
  const isActive = createExport.isPending || isStudioExportActive(job)
  const isDone = job?.status === StudioExportStatus.DONE
  const isFailed = job?.status === StudioExportStatus.FAILED
  /**
   * 进度查询失败时 job 为 null → isActive=false，若不禁用「导出」钮，用户点一下
   * 就是**第二个导出作业**（P3-1）。保留 exportId、提供「重试查询」，并在重复查询
   * 成功（或换格式清掉 exportId）之前禁止新建。
   */
  const jobQueryError = exportId !== null && jobQuery.isError

  const handleStart = async () => {
    setDownloadError(null)
    setExportId(null)
    try {
      const created = await createExport.mutateAsync({
        docId,
        version,
        format,
      })
      setExportId(created.exportId)
    } catch {
      // 创建失败由下方 createExport.error 展示，不重复提示
    }
  }

  const handleDownload = async () => {
    if (!job) return
    setIsDownloading(true)
    setDownloadError(null)
    try {
      const blob = await downloadStudioExportBlob(job.exportId)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = buildFileName(docTitle, job.version, job.format)
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      // 延迟释放，避免部分浏览器还没开始下载就失效
      window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
    } catch (error) {
      setDownloadError(resolveApiErrorMessage(error, '下载失败，请重试'))
    } finally {
      setIsDownloading(false)
    }
  }

  const createError =
    createExport.error != null
      ? resolveApiErrorMessage(createExport.error, '创建导出作业失败，请重试')
      : null
  const jobError = jobQuery.isError
    ? resolveApiErrorMessage(jobQuery.error, '导出进度查询失败，请重试')
    : (job?.error ?? null)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md' data-testid='studio-export-panel'>
        <DialogHeader>
          <DialogTitle className='flex items-center gap-2 text-base'>
            <FileDown className='size-4' />
            导出文档
          </DialogTitle>
          <DialogDescription>
            导出 v{version} 的锁定内容；作业异步执行，完成后可下载产物。
          </DialogDescription>
        </DialogHeader>

        <div
          className='grid grid-cols-4 gap-1.5'
          data-testid='studio-export-formats'
        >
          {STUDIO_EXPORT_FORMATS.map((item) => (
            <Button
              className={cn(
                'h-9 text-xs',
                format === item && 'border-primary/50 bg-primary/10'
              )}
              disabled={isActive}
              key={item}
              onClick={() => {
                setFormat(item)
                // 换格式即开始新的导出：清掉上一份作业，回到「可导出」态
                setExportId(null)
                setDownloadError(null)
              }}
              type='button'
              variant={format === item ? 'secondary' : 'outline'}
            >
              {STUDIO_EXPORT_FORMAT_LABEL[item]}
            </Button>
          ))}
        </div>

        {isActive ? (
          <div className='space-y-2' data-testid='studio-export-progress'>
            <div className='flex items-center justify-between text-xs'>
              <span className='text-muted-foreground flex items-center gap-1.5'>
                <Loader2 className='size-3.5 animate-spin' />
                {createExport.isPending
                  ? '正在创建导出作业…'
                  : STUDIO_EXPORT_STATUS_LABEL[job ? job.status : 'pending']}
              </span>
              <span className='tabular-nums'>{job?.progress ?? 0}%</span>
            </div>
            <div className='bg-muted h-1.5 w-full overflow-hidden rounded-full'>
              <div
                className='bg-primary h-full rounded-full transition-all duration-300'
                style={{ width: `${Math.max(5, job?.progress ?? 5)}%` }}
              />
            </div>
          </div>
        ) : isDone ? (
          <div
            className='flex items-center gap-2 rounded-md border border-emerald-500/30 bg-emerald-500/5 px-3 py-2 text-xs text-emerald-700 dark:text-emerald-400'
            data-testid='studio-export-done'
          >
            <Check className='size-4 shrink-0' />
            {STUDIO_EXPORT_STATUS_LABEL[job.status]}，可下载 {job.format.toUpperCase()} 产物
          </div>
        ) : isFailed ? (
          <div
            className='space-y-1 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive'
            data-testid='studio-export-error'
          >
            <p className='font-medium'>
              {STUDIO_EXPORT_STATUS_LABEL[StudioExportStatus.FAILED]}
            </p>
            <p className='break-words'>{jobError || '导出未完成，请重试'}</p>
          </div>
        ) : null}

        {jobQueryError && !isFailed && (
          <div
            className='space-y-1.5 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive'
            data-testid='studio-export-query-error'
          >
            <p className='font-medium'>导出进度查询失败</p>
            <p className='break-words'>{jobError}</p>
            <div className='flex items-center justify-between gap-2'>
              <span className='text-muted-foreground'>
                作业仍在后端执行，先重试查询，避免重复创建。
              </span>
              <Button
                className='h-7 shrink-0 px-2 text-xs'
                data-testid='studio-export-requery'
                onClick={() => void jobQuery.refetch()}
                size='sm'
                type='button'
                variant='outline'
              >
                重试查询
              </Button>
            </div>
          </div>
        )}

        {createError && (
          <p className='rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive'>
            {createError}
          </p>
        )}

        {downloadError && (
          <p className='rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive'>
            {downloadError}
          </p>
        )}

        {!canExport && (
          <p className='text-muted-foreground text-xs'>
            缺少「导出作业」权限（report:studio:export），不可发起导出。
          </p>
        )}

        <div className='flex items-center justify-end gap-2'>
          <Button
            onClick={() => onOpenChange(false)}
            size='sm'
            type='button'
            variant='ghost'
          >
            <X className='size-4' />
            关闭
          </Button>
          {isDone ? (
            <Button
              className='gap-1.5'
              data-testid='studio-export-download'
              disabled={isDownloading}
              onClick={() => void handleDownload()}
              size='sm'
              type='button'
            >
              {isDownloading ? (
                <Loader2 className='size-4 animate-spin' />
              ) : (
                <Download className='size-4' />
              )}
              下载 {job?.format.toUpperCase()}
            </Button>
          ) : (
            <Button
              className='gap-1.5'
              data-testid='studio-export-start'
              disabled={!canExport || isActive || jobQueryError}
              onClick={() => void handleStart()}
              size='sm'
              type='button'
            >
              {isActive ? (
                <Loader2 className='size-4 animate-spin' />
              ) : (
                <FileDown className='size-4' />
              )}
              {isFailed ? '重试导出' : `导出 ${STUDIO_EXPORT_FORMAT_LABEL[format]}`}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
