/**
 * 导入报告包 Dialog（链路 3a/3c，task:import；INT-1766 D8）。
 *
 * 流程（卡面清单 1~4）：
 *   选 ZIP → 前端只读包内 manifest.json（features/reports/lib/report-package.ts）做预检
 *   → 展示源任务 / 命中本地任务 / 现有报告 / 将被替换的警告 → 二次确认后导入
 *   → 回执（报告 id、替换与新增行数、文档映射、warnings）→ 列表与计数由 application 层失效刷新。
 *
 * 后端无报告包预检端点（D6 只交付 import/export），故预检只解 manifest 的展示字段；
 * 匹配、替换、回滚全部由后端在导入时执行，前端不写任何推断结果到库。
 * 包不匹配任何本地任务时，导入被后端拒绝（404），本 Dialog 在预检阶段就给出明确文案并禁用提交。
 */
import { AlertTriangle, FileArchive, Loader2, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

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
import type { ReportPackageManifestSummary } from '@/domain/models/report-studio'
import type { ReportListItem } from '@/domain/models/report'
import { ApiError } from '@/infrastructure/api/api-error'
import { HttpStatus } from '@/domain/models/api'
import { fetchReportList } from '@/infrastructure/api/reports-api'
import { fetchTaskDetail } from '@/infrastructure/api/tasks-list-api'
import { useImportReportPackage } from '@/application/reports/use-report-studio'
import { readReportPackageManifest } from '@/features/reports/lib/report-package'

interface LocalTaskInfo {
  id: number
  name: string
  status: string
}

type PreflightState =
  | { status: 'idle' }
  | { status: 'reading' }
  | {
      status: 'ready'
      manifest: ReportPackageManifestSummary | null
      task: LocalTaskInfo | null
      taskMissing: boolean
      existingReports: ReportListItem[]
    }

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.userMessage) return err.userMessage
    if (err.httpStatus === HttpStatus.NOT_FOUND) return '包内源任务在本地不存在'
    if (err.httpStatus === HttpStatus.FORBIDDEN) return '无权限导入该任务的报告包'
  }
  if (err instanceof Error && err.message) return err.message
  return '导入失败，请重试'
}

interface ImportReportPackageDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function ImportReportPackageDialog({
  open,
  onOpenChange,
}: ImportReportPackageDialogProps) {
  const [file, setFile] = useState<File | null>(null)
  const [preflight, setPreflight] = useState<PreflightState>({ status: 'idle' })
  const [confirmed, setConfirmed] = useState(false)
  const [receiptLines, setReceiptLines] = useState<string[] | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const importMutation = useImportReportPackage()

  useEffect(() => {
    if (open) {
      setFile(null)
      setPreflight({ status: 'idle' })
      setConfirmed(false)
      setReceiptLines(null)
      setWarnings([])
      setError(null)
    }
  }, [open])

  const handlePick = async (picked: File | null) => {
    setFile(picked)
    setConfirmed(false)
    setReceiptLines(null)
    setWarnings([])
    setError(null)
    if (!picked) {
      setPreflight({ status: 'idle' })
      return
    }
    setPreflight({ status: 'reading' })
    const manifest = await readReportPackageManifest(picked)
    let task: LocalTaskInfo | null = null
    let existingReports: ReportListItem[] = []
    let taskMissing = false
    if (manifest?.sourceTaskId) {
      try {
        const detail = await fetchTaskDetail(manifest.sourceTaskId)
        task = { id: detail.id, name: detail.name, status: detail.status }
        const list = await fetchReportList({
          page: 1,
          per_page: 5,
          task_id: manifest.sourceTaskId,
          sort_by: 'created_at',
          order: 'desc',
          favorite: false,
          deleted: false,
        })
        existingReports = list.items
      } catch (err) {
        if (err instanceof ApiError && err.httpStatus === HttpStatus.NOT_FOUND) {
          taskMissing = true
        } else {
          setError(errorMessage(err))
        }
      }
    }
    setPreflight({ status: 'ready', manifest, task, taskMissing, existingReports })
  }

  const canSubmit =
    Boolean(file) &&
    preflight.status === 'ready' &&
    !preflight.taskMissing &&
    confirmed &&
    !importMutation.isPending

  const handleSubmit = async () => {
    if (!file) return
    setError(null)
    try {
      const receipt = await importMutation.mutateAsync({ file })
      setWarnings(receipt.warnings)
      setReceiptLines([
        `平台报告：${receipt.reportId ? `#${receipt.reportId}（${receipt.targetResolvedBy ?? '已替换'}）` : '未包含'}`,
        `删除行：${Object.entries(receipt.deletedCounts)
          .map(([k, v]) => `${k}=${v}`)
          .join('、') || '0'}`,
        `写入行：${Object.entries(receipt.insertedCounts)
          .map(([k, v]) => `${k}=${v}`)
          .join('、') || '0'}`,
        `Studio 文档映射：${Object.keys(receipt.documentIdMapping).length} 份`,
        `Agent 会话已置空：${receipt.agentSessionDropped} 份`,
        receipt.rollbackAvailable ? '本次导入可回滚（批次已记录）' : '本次导入无回滚批次',
      ])
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const manifest = preflight.status === 'ready' ? preflight.manifest : null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>导入报告包</DialogTitle>
          <DialogDescription>
            导入包内的平台报告会<strong>原地替换</strong>本地同任务的现有报告（报告
            id、可见性与创建人保留），6 张子表整表重建，操作不可逆。
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-4'>
          <div className='space-y-2'>
            <input
              ref={inputRef}
              accept='.zip'
              className='hidden'
              type='file'
              onChange={(event) => void handlePick(event.target.files?.[0] ?? null)}
            />
            <Button
              className='w-full justify-start'
              type='button'
              variant='outline'
              onClick={() => inputRef.current?.click()}
            >
              <FileArchive data-icon='inline-start' />
              {file ? file.name : '选择报告包（.zip）'}
            </Button>
            {file && (
              <p className='text-muted-foreground text-xs'>
                文件大小 {formatSize(file.size)}
              </p>
            )}
          </div>

          {preflight.status === 'reading' && (
            <p className='text-muted-foreground flex items-center gap-2 text-sm'>
              <Loader2 className='size-4 animate-spin' />
              正在读取包内清单…
            </p>
          )}

          {preflight.status === 'ready' && (
            <div className='bg-muted/40 space-y-2 rounded-md p-3 text-sm'>
              {manifest ? (
                <>
                  <div className='flex items-center gap-2'>
                    <span className='text-muted-foreground w-24 shrink-0 text-xs'>包内源任务</span>
                    <span className='min-w-0 truncate'>
                      {manifest.sourceTaskName || '（未知名称）'}
                      {manifest.sourceTaskId ? ` · #${manifest.sourceTaskId}` : ''}
                    </span>
                  </div>
                  <div className='flex items-center gap-2'>
                    <span className='text-muted-foreground w-24 shrink-0 text-xs'>命中本地任务</span>
                    {preflight.task ? (
                      <span className='min-w-0 truncate'>
                        {preflight.task.name} · #{preflight.task.id}
                        <Badge className='ml-2' variant='outline'>
                          {preflight.task.status}
                        </Badge>
                      </span>
                    ) : preflight.taskMissing ? (
                      <span className='text-destructive'>本地不存在该任务，导入会被拒绝</span>
                    ) : (
                      <span className='text-muted-foreground'>包内未声明源任务</span>
                    )}
                  </div>
                  <div className='flex items-start gap-2'>
                    <span className='text-muted-foreground w-24 shrink-0 text-xs'>现有报告</span>
                    <span className='min-w-0'>
                      {preflight.existingReports.length === 0 ? (
                        '该任务暂无报告（导入将新建）'
                      ) : (
                        <span className='text-destructive'>
                          将被替换：{preflight.existingReports[0].name} · #
                          {preflight.existingReports[0].id}
                        </span>
                      )}
                    </span>
                  </div>
                  <div className='flex items-center gap-2'>
                    <span className='text-muted-foreground w-24 shrink-0 text-xs'>包含实体</span>
                    <span className='min-w-0 truncate'>
                      {manifest.entities.join('、') || '—'}
                    </span>
                  </div>
                  <div className='flex items-center gap-2'>
                    <span className='text-muted-foreground w-24 shrink-0 text-xs'>版本策略</span>
                    <span>{manifest.docVersionScope === 'latest' ? '仅当前版本' : '全部版本'}</span>
                  </div>
                </>
              ) : (
                <p className='text-muted-foreground'>
                  无法读取包内清单（非报告包或已损坏），导入结果以服务端回执为准。
                </p>
              )}

              <label className='flex items-start gap-2 border-t pt-2'>
                <Checkbox
                  checked={confirmed}
                  disabled={preflight.taskMissing}
                  onCheckedChange={(value) => setConfirmed(value === true)}
                />
                <span className='text-xs leading-5'>
                  我已知晓：导入会用包内数据替换本地同任务报告的现有内容，旧报告子表与旧文档不可恢复。
                </span>
              </label>
            </div>
          )}

          {error && (
            <p className='text-destructive flex items-start gap-2 text-sm'>
              <AlertTriangle className='mt-0.5 size-4 shrink-0' />
              {error}
            </p>
          )}

          {receiptLines && (
            <div className='space-y-1 rounded-md border p-3 text-sm'>
              <p className='flex items-center gap-2 font-medium'>
                <Upload className='size-4' />
                导入完成
              </p>
              {receiptLines.map((line) => (
                <p key={line} className='text-muted-foreground text-xs'>
                  {line}
                </p>
              ))}
              {warnings.length > 0 && (
                <div className='text-destructive space-y-1 pt-1 text-xs'>
                  {warnings.map((warning) => (
                    <p key={warning}>· {warning}</p>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            关闭
          </Button>
          {!receiptLines && (
            <Button disabled={!canSubmit} onClick={() => void handleSubmit()}>
              {importMutation.isPending ? '导入中…' : '确认导入'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
