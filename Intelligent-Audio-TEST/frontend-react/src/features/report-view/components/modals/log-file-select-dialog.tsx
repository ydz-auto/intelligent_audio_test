/**
 * 日志文件选择 Dialog（15_报告域.md §4.10a，INT-1067）。
 * 数据源 GET /reports/{id}/cases/{caseId}/logs（INT-1062）→ { items: [{name,size,updated_at?}] }。
 * 交互：文件列表（文件名 font-mono + 大小 Badge + Checkbox）+ 工具行「全选/反选」
 * +「已选 {n} 个 / 共 {m} 个 · 总大小 {size}」+ 空态「该用例暂无日志文件」
 * + 底栏「取消｜下载所选文件」（默认全选）。
 * 确认后由调用方走下载流程（打包所选 zip + 下载进度 Dialog，§4.10b）。
 */
import { FileText, LoaderCircle } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
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
import type { ReportCaseItem, ReportLogFile } from '@/domain/models/report'
import { fetchCaseLogFiles } from '@/infrastructure/api/reports-api'

import { formatBytes } from './log-format'

interface LogFileSelectDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  reportId: number
  /** 目标用例（日志归属；name 作标题、id 拉文件列表） */
  caseItem?: ReportCaseItem
  /** 确认下载所选文件（files 名称与列表 name / ZIP arcname 同一套逻辑名） */
  onConfirm: (files: ReportLogFile[]) => void
}

export function LogFileSelectDialog({
  open,
  onOpenChange,
  reportId,
  caseItem,
  onConfirm,
}: LogFileSelectDialogProps) {
  const [files, setFiles] = useState<ReportLogFile[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isError, setIsError] = useState(false)
  // 重试按钮递增触发重新拉取
  const [retryKey, setRetryKey] = useState(0)

  // 打开即拉取文件列表（默认全选）
  useEffect(() => {
    if (!open || !caseItem) return
    let cancelled = false
    setIsLoading(true)
    setIsError(false)
    setFiles([])
    setSelected([])
    fetchCaseLogFiles(reportId, caseItem.id)
      .then((items) => {
        if (cancelled) return
        setFiles(items)
        setSelected(items.map((f) => f.name))
        setIsLoading(false)
      })
      .catch(() => {
        if (cancelled) return
        setIsError(true)
        setIsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, caseItem, reportId, retryKey])

  const allSelected = files.length > 0 && selected.length === files.length
  const selectedTotal = useMemo(
    () =>
      files
        .filter((f) => selected.includes(f.name))
        .reduce((sum, f) => sum + (f.size || 0), 0),
    [files, selected]
  )

  const toggleFile = (name: string) =>
    setSelected((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]
    )

  const handleConfirm = () => {
    const chosen = files.filter((f) => selected.includes(f.name))
    if (chosen.length === 0) return
    onConfirm(chosen)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>下载日志 — {caseItem?.name ?? ''}</DialogTitle>
          <DialogDescription>选择要打包下载的日志文件（默认全选）。</DialogDescription>
        </DialogHeader>

        {/* 工具行：全选/反选 + 已选合计 */}
        <div className='flex items-center justify-between text-xs'>
          <Button
            variant='ghost'
            size='sm'
            className='h-7 px-2'
            disabled={files.length === 0 || isLoading || isError}
            onClick={() =>
              allSelected
                ? setSelected([])
                : setSelected(files.map((f) => f.name))
            }
          >
            {allSelected ? '反选' : '全选'}
          </Button>
          <span className='text-muted-foreground tabular-nums'>
            已选 {selected.length} 个 / 共 {files.length} 个 · 总大小 {formatBytes(selectedTotal)}
          </span>
        </div>

        {/* 文件列表 / 加载 / 错误 / 空态 */}
        <div className='max-h-[40vh] min-h-32 overflow-y-auto rounded-lg border'>
          {isLoading ? (
            <div className='flex h-32 items-center justify-center gap-2 text-sm text-muted-foreground'>
              <LoaderCircle className='size-4 animate-spin' aria-hidden='true' />
              正在加载日志文件...
            </div>
          ) : isError ? (
            <div className='flex h-32 flex-col items-center justify-center gap-2 text-xs text-muted-foreground'>
              <span>日志文件加载失败</span>
              <Button
                variant='outline'
                size='sm'
                className='h-7 px-3 text-xs'
                onClick={() => setRetryKey((k) => k + 1)}
              >
                请重试
              </Button>
            </div>
          ) : files.length === 0 ? (
            <div className='flex h-32 items-center justify-center text-sm text-muted-foreground'>
              该用例暂无日志文件
            </div>
          ) : (
            <ul className='divide-y'>
              {files.map((f) => (
                <li key={f.name}>
                  <label className='hover:bg-muted/40 flex cursor-pointer items-center gap-3 px-3 py-2'>
                    <Checkbox
                      checked={selected.includes(f.name)}
                      onCheckedChange={() => toggleFile(f.name)}
                      aria-label={`选择日志文件 ${f.name}`}
                    />
                    <FileText className='text-muted-foreground size-4 shrink-0' aria-hidden='true' />
                    <span className='font-mono flex-1 truncate text-sm' title={f.name}>
                      {f.name}
                    </span>
                    <Badge variant='outline' className='font-mono text-[11px] tabular-nums'>
                      {formatBytes(f.size)}
                    </Badge>
                  </label>
                </li>
              ))}
            </ul>
          )}
        </div>

        <DialogFooter>
          <Button variant='outline' size='sm' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            size='sm'
            onClick={handleConfirm}
            disabled={selected.length === 0 || isLoading || isError || files.length === 0}
          >
            下载所选文件
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
