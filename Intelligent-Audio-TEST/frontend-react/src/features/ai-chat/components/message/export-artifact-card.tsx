/**
 * 导出产物卡（interfaces 层 ai-chat/message；INT-2473 后续：Agent 导出结果渲染）。
 *
 * 背景：Agent 的 report_export / studio_request_export 结果原本只出现在回复正文里，
 * 给的是 `/api/v1/report-studio/exports/{id}/download` 裸路径——该路径必须带
 * Authorization: Bearer，浏览器直接点是 401，等于「导出完拿不到文件」。
 * 这里按工具结果里的结构化产物渲染文件卡：
 * - PDF / PPTX：鉴权下载（不在线渲染）；
 * - MD / HTML：鉴权取 Blob 后在弹窗内渲染（HTML 走 sandbox iframe）；
 * - 有 docId 时提供「查看文档」，定位右侧文档面板。
 */
import {
  CheckCircle2,
  Download,
  Eye,
  FileText,
  Loader2,
  XCircle,
} from 'lucide-react'
import { useEffect, useState } from 'react'

import { Response } from '@/components/ai-elements/response'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { useStudioExportJob } from '@/application/reports/use-report-studio'
import {
  STUDIO_EXPORT_FORMAT_LABEL,
  STUDIO_EXPORT_STATUS_LABEL,
  StudioExportFormatKind,
  StudioExportStatus,
  isStudioExportRenderable,
  type StudioExportArtifact,
} from '@/domain/models/report-studio'
import { resolveApiErrorMessage } from '@/features/ai-chat/lib/api-error-message'
import { downloadStudioExportBlob } from '@/infrastructure/api/reportStudioApi'
import { useAiChatSession } from '@/infrastructure/stores/aiChatSessionStore'
import { downloadBlob } from '@/lib/download-blob'

type ExportArtifactCardProps = {
  artifact: StudioExportArtifact
}

/** 下载文件名：报告 {id} · v{version}.{format}（后端文件名是 export_id，不可读） */
function buildFileName(artifact: StudioExportArtifact): string {
  const parts = [artifact.reportId ? `报告-${artifact.reportId}` : '报告']
  if (artifact.version !== null) parts.push(`v${artifact.version}`)
  const ext = artifact.format ?? 'bin'
  return `${parts.join('-')}.${ext}`
}

export function ExportArtifactCard(props: ExportArtifactCardProps) {
  const artifact = props.artifact
  const jobQuery = useStudioExportJob(artifact.exportId)
  const openStudioDocument = useAiChatSession((state) => state.openStudioDocument)

  const status = jobQuery.data?.status ?? artifact.status
  const progress = jobQuery.data?.progress ?? artifact.progress ?? 0
  const error = jobQuery.data?.error ?? artifact.error
  const version = jobQuery.data?.version ?? artifact.version
  const format = artifact.format
  const isActive =
    status === StudioExportStatus.PENDING || status === StudioExportStatus.RUNNING
  const isDone = status === StudioExportStatus.DONE
  const isFailed = status === StudioExportStatus.FAILED
  const canRender = isDone && isStudioExportRenderable(format)

  const [isDownloading, setIsDownloading] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewText, setPreviewText] = useState('')
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)

  // Blob URL 随预览内容替换 / 关闭 / 卸载释放
  useEffect(() => {
    if (!previewUrl) return undefined
    return () => URL.revokeObjectURL(previewUrl)
  }, [previewUrl])

  const handleDownload = async () => {
    setIsDownloading(true)
    setActionError(null)
    try {
      const blob = await downloadStudioExportBlob(artifact.exportId)
      downloadBlob(blob, buildFileName(artifact), 'application/octet-stream')
    } catch (downloadError) {
      setActionError(resolveApiErrorMessage(downloadError, '下载失败，请重试'))
    } finally {
      setIsDownloading(false)
    }
  }

  const handlePreview = async () => {
    if (!format) return
    setPreviewOpen(true)
    setPreviewLoading(true)
    setPreviewError(null)
    setPreviewText('')
    setPreviewUrl(null)
    try {
      const blob = await downloadStudioExportBlob(artifact.exportId)
      if (format === StudioExportFormatKind.MD) {
        setPreviewText(await blob.text())
      } else {
        setPreviewUrl(URL.createObjectURL(blob))
      }
    } catch (previewLoadError) {
      setPreviewError(
        resolveApiErrorMessage(previewLoadError, '预览加载失败，请重试')
      )
    } finally {
      setPreviewLoading(false)
    }
  }

  const formatLabel = format ? STUDIO_EXPORT_FORMAT_LABEL[format] : '产物'
  const docId = artifact.docId

  return (
    <div
      className='border-border/70 bg-background/60 not-prose mb-3 w-full rounded-md border p-3'
      data-testid='studio-export-artifact'
    >
      <div className='flex items-start gap-2'>
        <FileText className='text-primary mt-0.5 size-4 shrink-0' />
        <div className='min-w-0 flex-1'>
          <div className='flex flex-wrap items-center gap-1.5'>
            <span className='text-sm font-medium'>导出产物 · {formatLabel}</span>
            {version !== null && (
              <Badge variant='outline'>v{version}</Badge>
            )}
            {artifact.reportId !== null && (
              <Badge variant='secondary'>报告 #{artifact.reportId}</Badge>
            )}
            <Badge
              data-export-status={status}
              variant={
                isFailed
                  ? 'destructive'
                  : isActive
                    ? 'warning'
                    : 'secondary'
              }
            >
              {STUDIO_EXPORT_STATUS_LABEL[status]}
            </Badge>
          </div>

          {isActive && (
            <div className='mt-2 space-y-1' data-testid='studio-export-artifact-progress'>
              <div className='text-muted-foreground flex items-center gap-1.5 text-xs'>
                <Loader2 className='size-3.5 animate-spin' />
                导出中，完成后可下载
                <span className='ml-auto tabular-nums'>{progress}%</span>
              </div>
              <div className='bg-muted h-1.5 w-full overflow-hidden rounded-full'>
                <div
                  className='bg-primary h-full rounded-full transition-all duration-300'
                  style={{ width: `${Math.max(5, progress)}%` }}
                />
              </div>
            </div>
          )}

          {isFailed && (
            <p
              className='text-destructive mt-1.5 break-words text-xs'
              data-testid='studio-export-artifact-error'
            >
              <XCircle className='mr-1 inline size-3.5 align-[-2px]' />
              {error || '导出未完成，请重试'}
            </p>
          )}

          {isDone && (
            <p className='text-muted-foreground mt-1.5 flex items-center gap-1 text-xs'>
              <CheckCircle2 className='size-3.5 text-emerald-600 dark:text-emerald-400' />
              {formatLabel} 已生成，可下载
              {isStudioExportRenderable(format) ? '或直接预览' : ''}
            </p>
          )}

          {jobQuery.isError && (
            <p className='text-muted-foreground mt-1.5 text-xs'>
              导出状态刷新失败，以下载结果为准。
            </p>
          )}

          {actionError && (
            <p className='text-destructive mt-1.5 text-xs'>{actionError}</p>
          )}
        </div>
      </div>

      <div className='mt-2 flex flex-wrap items-center justify-end gap-2'>
        {docId && (
          <Button
            className='h-7 px-2 text-xs'
            data-testid='studio-export-artifact-open-doc'
            onClick={() => openStudioDocument({ docId, reportId: artifact.reportId })}
            size='sm'
            type='button'
            variant='ghost'
          >
            查看文档
          </Button>
        )}
        {canRender && (
          <Button
            className='h-7 gap-1 px-2 text-xs'
            data-testid='studio-export-artifact-preview'
            onClick={() => void handlePreview()}
            size='sm'
            type='button'
            variant='outline'
          >
            <Eye className='size-3.5' />
            预览 {formatLabel}
          </Button>
        )}
        {isDone && (
          <Button
            className='h-7 gap-1 px-2 text-xs'
            data-testid='studio-export-artifact-download'
            disabled={isDownloading}
            onClick={() => void handleDownload()}
            size='sm'
            type='button'
          >
            {isDownloading ? (
              <Loader2 className='size-3.5 animate-spin' />
            ) : (
              <Download className='size-3.5' />
            )}
            下载 {formatLabel}
          </Button>
        )}
      </div>

      <Sheet onOpenChange={setPreviewOpen} open={previewOpen}>
        <SheetContent
          className='w-full gap-0 p-0 sm:max-w-[min(1100px,62vw)]'
          side='right'
        >
          <SheetHeader className='border-b pr-12'>
            <SheetTitle>预览 {formatLabel}</SheetTitle>
            <SheetDescription>
              {artifact.reportId !== null ? `报告 #${artifact.reportId}` : '报告产物'}
              {version !== null ? ` · v${version}` : ''}
            </SheetDescription>
          </SheetHeader>
          <div className='min-h-0 flex-1'>
            {previewLoading ? (
              <p className='text-muted-foreground flex items-center gap-2 px-6 py-8 text-sm'>
                <Loader2 className='size-4 animate-spin' />
                正在加载预览…
              </p>
            ) : previewError ? (
              <p className='text-destructive px-6 py-4 text-sm'>{previewError}</p>
            ) : previewUrl ? (
              <iframe
                className='bg-background h-full w-full border-0'
                referrerPolicy='no-referrer'
                sandbox='allow-scripts'
                src={previewUrl}
                title={`${formatLabel} 预览`}
              />
            ) : (
              <div className='h-full overflow-y-auto px-8 py-6'>
                <Response>{previewText}</Response>
              </div>
            )}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  )
}
