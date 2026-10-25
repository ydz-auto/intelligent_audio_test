/**
 * 上传独立报告 Dialog（链路 3b，report:studio:create；INT-1766 D8）。
 *
 * POST /api/v1/report-studio/import（multipart：file + title + format + 可选 task_id）：
 * 前端只做必填与白名单/大小的即时校验，格式与 Content-Type 双校验、413、OSS 落盘与
 * 建档全部由后端完成（设计 §6.2）。可选「关联任务」来自真实任务接口（GET /tasks）。
 */
import { FileUp, Loader2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  STUDIO_UPLOAD_FORMATS,
  STUDIO_UPLOAD_MAX_MB,
  type StudioUploadFormat,
} from '@/domain/models/report-studio'
import { ApiError } from '@/infrastructure/api/api-error'
import { useCompletedTasks } from '@/application/reports/use-completed-tasks'
import { useImportStudioDocument } from '@/application/reports/use-report-studio'

const FORMAT_LABEL: Record<StudioUploadFormat, string> = {
  md: 'Markdown（正文可编辑）',
  html: 'HTML（预览 / 下载）',
  pptx: 'PPTX（预览 / 下载）',
}

/** 不关联任务的选择值（Select 不接受空字符串 as value） */
const NO_TASK = '__none__'

function detectFormat(name: string): StudioUploadFormat | null {
  const ext = name.split('.').pop()?.toLowerCase() ?? ''
  return (STUDIO_UPLOAD_FORMATS as readonly string[]).includes(ext)
    ? (ext as StudioUploadFormat)
    : null
}

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.httpStatus === 413) return `文件超过 ${STUDIO_UPLOAD_MAX_MB}MB 上限`
    if (err.httpStatus === 415) return '仅支持 md / html / pptx 文件'
    if (err.userMessage) return err.userMessage
  }
  if (err instanceof Error && err.message) return err.message
  return '上传失败，请重试'
}

interface UploadReportDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 上传成功后的回调（列表刷新由 application 层失效完成，这里只做提示/关闭） */
  onUploaded?: (title: string) => void
}

export function UploadReportDialog({
  open,
  onOpenChange,
  onUploaded,
}: UploadReportDialogProps) {
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [titleTouched, setTitleTouched] = useState(false)
  const [taskId, setTaskId] = useState<string>(NO_TASK)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const upload = useImportStudioDocument()
  const tasksQuery = useCompletedTasks()

  useEffect(() => {
    if (open) {
      setFile(null)
      setTitle('')
      setTitleTouched(false)
      setTaskId(NO_TASK)
      setError(null)
    }
  }, [open])

  const format = useMemo(() => (file ? detectFormat(file.name) : null), [file])
  const sizeMb = file ? file.size / 1024 / 1024 : 0
  const tooLarge = sizeMb > STUDIO_UPLOAD_MAX_MB
  const formatInvalid = Boolean(file) && !format
  const titleError = titleTouched && title.trim().length === 0
  const canSubmit =
    Boolean(file) &&
    title.trim().length > 0 &&
    Boolean(format) &&
    !tooLarge &&
    !upload.isPending

  const handlePick = (picked: File | null) => {
    setFile(picked)
    setError(null)
    if (picked && !title) {
      // 用文件名兜底预填标题，用户可改
      setTitle(picked.name.replace(/\.[^.]+$/, ''))
    }
  }

  const handleSubmit = async () => {
    if (!file || !format) return
    setTitleTouched(true)
    if (title.trim().length === 0) return
    setError(null)
    try {
      await upload.mutateAsync({
        file,
        title: title.trim(),
        format,
        taskId: taskId === NO_TASK ? undefined : Number(taskId),
      })
      onUploaded?.(title.trim())
      onOpenChange(false)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>上传独立报告</DialogTitle>
          <DialogDescription>
            上传 Markdown / HTML / PPTX 报告文件，落到 Report Studio 文档库；可选关联一个任务，
            关联后在任务详情与报告文档中可见。
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-4'>
          <div className='space-y-2'>
            <span className='text-sm font-medium'>
              文件<span className='text-destructive'> *</span>
            </span>
            <input
              ref={inputRef}
              accept='.md,.markdown,.html,.htm,.pptx'
              className='hidden'
              type='file'
              onChange={(event) => handlePick(event.target.files?.[0] ?? null)}
            />
            <Button
              className='w-full justify-start'
              type='button'
              variant='outline'
              onClick={() => inputRef.current?.click()}
            >
              <FileUp data-icon='inline-start' />
              {file ? file.name : '选择报告文件'}
            </Button>
            <p className='text-muted-foreground text-xs'>
              支持 md / html / pptx，单个文件不超过 {STUDIO_UPLOAD_MAX_MB}MB
              {file ? `（当前 ${sizeMb.toFixed(2)}MB · ${format ? FORMAT_LABEL[format] : '格式不支持'}）` : ''}
            </p>
            {formatInvalid && (
              <p className='text-destructive text-xs'>仅支持 md / html / pptx 扩展名</p>
            )}
            {tooLarge && (
              <p className='text-destructive text-xs'>
                文件超过 {STUDIO_UPLOAD_MAX_MB}MB 上限，请压缩或拆分后再上传
              </p>
            )}
          </div>

          <div className='space-y-2'>
            <span className='text-sm font-medium'>
              标题<span className='text-destructive'> *</span>
            </span>
            <Input
              aria-invalid={titleError}
              placeholder='例如：XX 算法对比报告'
              value={title}
              onBlur={() => setTitleTouched(true)}
              onChange={(event) => setTitle(event.target.value)}
            />
            {titleError && <p className='text-destructive text-xs'>标题不能为空</p>}
          </div>

          <div className='space-y-2'>
            <span className='text-sm font-medium'>关联任务（可选）</span>
            <Select value={taskId} onValueChange={(value) => setTaskId(value ?? NO_TASK)}>
              <SelectTrigger className='w-full justify-between'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_TASK}>不关联任务（独立文档库）</SelectItem>
                {(tasksQuery.data ?? []).map((task) => (
                  <SelectItem key={task.id} value={String(task.id)}>
                    {task.name} · #{task.id}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {tasksQuery.isLoading && (
              <p className='text-muted-foreground flex items-center gap-2 text-xs'>
                <Loader2 className='size-3 animate-spin' />
                正在加载任务…
              </p>
            )}
            {tasksQuery.isError && (
              <p className='text-destructive text-xs'>任务列表加载失败，可先不关联任务</p>
            )}
          </div>

          {error && <p className='text-destructive text-sm'>{error}</p>}
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button disabled={!canSubmit} onClick={() => void handleSubmit()}>
            {upload.isPending ? '上传中…' : '上传'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
