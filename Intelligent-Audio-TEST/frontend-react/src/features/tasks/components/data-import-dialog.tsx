/**
 * 导入数据弹窗（09_任务域.md §5.12，Dialog sm:max-w-lg）。
 * 三段式：选文件（.zip）→ 预检结果（版本/导出时间/源服务器 + 任务清单 + 统计行
 * 「任务 {n} · 结果 {n} · 维度评分 {n} · 报告 {n} · 文件 {n}」+ ID 冲突警示 + 警告列表）
 * → 导入进度（Progress + 阶段文本）→ 完成统计 + 完成动作组（查看任务详情/重新评估/重新执行）
 * + 失败回滚信息（Alert destructive「导入失败：{失败步骤} — {错误原因}；已回滚至导入前状态，
 * 磁盘文件已清理」+ 主钮「重新尝试」）。
 * 导入经 infrastructure/api/data-transfer-api（client.ts）POST /data-transfer/import/preview
 * → /import；进度以 GET /import/progress 兜底轮询（SocketIO 未接入 React 侧）。
 */
import { FileUp, LoaderCircle, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
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
import type {
  ImportPreview,
  ImportProgress,
  ImportResult,
} from '@/domain/models/data-transfer'
import {
  executeImport,
  getImportProgress,
  previewImport,
} from '@/infrastructure/api/data-transfer-api'
import { ApiError } from '@/infrastructure/api/api-error'
import { Progress } from '@/features/tasks/components/ui/progress'

type Phase = 'select' | 'preview' | 'importing' | 'done' | 'error'

const STEP_TEXT: Record<string, string> = {
  parsing: '解析导出包',
  writing_db: '写入数据库',
  extracting_files: '回写文件',
  updating_paths: '更新文件路径',
  done: '导入完成',
  error: '导入失败',
}

const INITIAL_PROGRESS: ImportProgress = {
  step: 'parsing',
  currentTable: '',
  processedRows: 0,
  totalRows: 0,
  percentage: 0,
  message: '',
  batchId: '',
}

function statsLine(stats: { taskCount: number; resultCount: number; dimensionCount: number; reportCount: number; fileCount: number } | ImportResult): string {
  const taskCount =
    'importedTasks' in stats ? stats.importedTasks : stats.taskCount
  const resultCount =
    'importedResults' in stats ? stats.importedResults : stats.resultCount
  const dimensionCount =
    'importedDimensions' in stats ? stats.importedDimensions : stats.dimensionCount
  const reportCount =
    'importedReports' in stats ? stats.importedReports : stats.reportCount
  const fileCount = 'importedFiles' in stats ? stats.importedFiles : stats.fileCount
  return `任务 ${taskCount} · 结果 ${resultCount} · 维度评分 ${dimensionCount} · 报告 ${reportCount} · 文件 ${fileCount}`
}

export function DataImportDialog({
  open,
  onOpenChange,
  onImported,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 导入完成：父层刷新任务列表（导入任务落日常列表） */
  onImported?: () => void
}) {
  const navigate = useNavigate()
  const { hasPermission } = usePermissions()

  const [phase, setPhase] = useState<Phase>('select')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [progress, setProgress] = useState<ImportProgress>(INITIAL_PROGRESS)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  /** progress 最新值镜像（pollProgress 闭包读 ref 而非渲染期快照，避免守卫读旧值） */
  const progressRef = useRef(progress)
  useEffect(() => {
    progressRef.current = progress
  }, [progress])

  const progressPercent = phase === 'done' ? 100 : Math.min(Math.max(progress.percentage || 0, 0), 100)
  const progressText = (() => {
    const stepText = STEP_TEXT[progress.step] || progress.step
    const table = progress.currentTable ? `（${progress.currentTable}）` : ''
    const rows =
      progress.totalRows > 0 ? ` ${progress.processedRows}/${progress.totalRows}` : ''
    return `${stepText}${table}${rows} ${progress.message || ''}`
  })()

  /** 重映射提示（仅冲突时非空） */
  const remapText = (() => {
    const remaps = result?.remappedIds ?? {}
    const parts: string[] = []
    const TABLE_NAMES: Record<string, string> = {
      tasks: '任务',
      test_results: '结果',
      test_result_dimensions: '维度评分',
      test_reports: '报告',
    }
    for (const [table, mapping] of Object.entries(remaps)) {
      const count = Object.keys(mapping || {}).length
      if (count > 0) parts.push(`${TABLE_NAMES[table] || table} ID ${count} 条`)
    }
    return parts.length ? `发生 ID 重映射：${parts.join('，')}` : ''
  })()

  const stopWatching = () => {
    if (pollTimer.current) {
      clearInterval(pollTimer.current)
      pollTimer.current = null
    }
  }

  useEffect(() => {
    if (!open) {
      stopWatching()
      // 重开时复位状态机（§5.12 三段式从选文件重新走）
      setPhase('select')
      setPreview(null)
      setResult(null)
      setProgress(INITIAL_PROGRESS)
      setErrorMessage('')
      setSelectedFile(null)
    }
    return stopWatching
  }, [open])

  const onFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    setSelectedFile(file)
    setPreview(null)
    setErrorMessage('')
    setPreviewing(true)
    try {
      const data = await previewImport(file)
      setPreview(data)
      setPhase('preview')
    } catch (error) {
      setErrorMessage(
        error instanceof ApiError
          ? (error.userMessage || error.message || '预检失败：无法解析该导出包')
          : '预检失败：无法解析该导出包'
      )
      setPreview(null)
      setPhase('error')
    } finally {
      setPreviewing(false)
    }
  }

  const pollProgress = async () => {
    try {
      const snapshot = await getImportProgress()
      // 快照兜底：仅推进不回退（对照最新 progress 而非渲染期闭包快照，防止瞬时旧快照覆盖）
      if (snapshot && snapshot.percentage >= progressRef.current.percentage) {
        setProgress(snapshot)
      }
    } catch {
      // 快照兜底失败忽略
    }
  }

  const startImport = async () => {
    if (!selectedFile) return
    setErrorMessage('')
    setResult(null)
    setPhase('importing')
    pollTimer.current = setInterval(() => void pollProgress(), 2500)
    try {
      const data = await executeImport(selectedFile)
      setResult(data)
      setPhase('done')
      toast.success('任务数据导入完成')
      onImported?.()
    } catch (error) {
      setErrorMessage(
        error instanceof ApiError
          ? (error.userMessage || error.message || '导入失败')
          : '导入失败'
      )
      setPhase('error')
    } finally {
      stopWatching()
    }
  }

  const goDailyList = () => {
    void navigate({ to: '/tasks/$tab', params: { tab: 'daily' } })
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>导入任务数据</DialogTitle>
          <DialogDescription>从导出包 ZIP 恢复任务数据（预检 → 导入 → 完成统计）</DialogDescription>
        </DialogHeader>

        <div className='flex flex-col gap-3'>
          {/* 步骤 1：选文件 */}
          {phase === 'select' && (
            <label className='flex cursor-pointer flex-col items-center gap-1.5 rounded-lg border border-dashed bg-muted/30 px-4 py-8 text-sm transition-colors hover:bg-muted/50'>
              <FileUp aria-hidden='true' className='text-muted-foreground size-6' />
              <span className='text-muted-foreground'>选择导出包（.zip）</span>
              <span className='text-muted-foreground/70 text-xs'>支持由本系统导出的任务数据包</span>
              <input type='file' accept='.zip' className='hidden' onChange={(e) => void onFileChange(e)} />
            </label>
          )}

          {previewing && (
            <p className='text-muted-foreground flex items-center gap-2 text-xs'>
              <Spinner size={14} />
              正在解析导出包…
            </p>
          )}

          {/* 步骤 2：预检结果 */}
          {preview && (
            <div className='flex flex-col gap-2'>
              <p className='text-sm font-medium'>预检结果</p>
              <div className='text-muted-foreground flex flex-col gap-0.5 rounded-lg border bg-muted/30 px-3 py-2 text-xs'>
                <span>
                  版本：{preview.version}　导出时间：{preview.exportedAt || '未知'}
                </span>
                <span>源服务器：{preview.source || '未知'}</span>
              </div>
              <ScrollArea className='max-h-36 rounded-lg border'>
                <ul className='divide-y divide-border'>
                  {preview.tasks.map((task) => (
                    <li
                      key={task.id}
                      className='flex items-center justify-between gap-2 px-3 py-1.5 text-sm'
                    >
                      <span className='min-w-0 flex-1 truncate'>{task.name}</span>
                      <span className='text-muted-foreground shrink-0 text-xs'>
                        {task.status} · {task.resultCount} 条结果
                      </span>
                    </li>
                  ))}
                </ul>
              </ScrollArea>
              <p className='text-muted-foreground text-xs'>{statsLine(preview.stats)}</p>
              {preview.conflicts.length > 0 && (
                <Alert className='border-warning/40'>
                  <AlertTitle className='text-warning'>
                    {preview.conflicts.length} 条 ID 冲突，导入时将自动重映射
                  </AlertTitle>
                  <AlertDescription>冲突记录将以新 ID 写入，引用关系自动对齐。</AlertDescription>
                </Alert>
              )}
              {preview.warnings.length > 0 && (
                <ul className='text-muted-foreground ml-4 list-disc text-xs'>
                  {preview.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* 步骤 3：导入进度 */}
          {phase === 'importing' && (
            <div className='flex flex-col gap-1.5'>
              <p className='text-sm font-medium'>导入进度</p>
              <Progress value={progressPercent} size='md' />
              <p className='text-muted-foreground text-xs'>
                {progressText}（{Math.round(progressPercent)}%）
              </p>
            </div>
          )}

          {/* 步骤 4：完成统计 + 动作组 */}
          {result && phase === 'done' && (
            <div className='flex flex-col gap-2'>
              <p className='text-sm font-medium'>导入完成</p>
              <p className='text-muted-foreground text-xs'>{statsLine(result)}</p>
              {remapText && (
                <Alert className='border-warning/40'>
                  <AlertTitle className='text-warning'>{remapText}</AlertTitle>
                </Alert>
              )}
              <p className='text-muted-foreground text-xs'>
                导入任务状态为「已完成」，已出现在「日常」列表，可继续查看详情、重新评估或重新执行。
              </p>
              <div className='flex flex-wrap items-center gap-2'>
                {hasPermission('task:read') && (
                  <Button size='sm' variant='outline' className='h-7' onClick={goDailyList}>
                    查看任务详情
                  </Button>
                )}
                {hasPermission('evaluation:execute') && (
                  <Button size='sm' variant='outline' className='h-7' onClick={goDailyList}>
                    重新评估
                  </Button>
                )}
                {hasPermission('task:execute') && (
                  <Button size='sm' variant='outline' className='h-7' onClick={goDailyList}>
                    重新执行
                  </Button>
                )}
              </div>
            </div>
          )}

          {/* 失败回滚信息（UC-03） */}
          {errorMessage && (
            <Alert variant='destructive'>
              <AlertTitle>导入失败：已回滚至导入前状态</AlertTitle>
              <AlertDescription>
                {errorMessage}；已回滚至导入前状态，磁盘文件已清理。
              </AlertDescription>
            </Alert>
          )}
        </div>

        <DialogFooter>
          {phase !== 'importing' && (
            <Button variant='outline' disabled={previewing} onClick={() => onOpenChange(false)}>
              {phase === 'done' ? '关闭' : '取消'}
            </Button>
          )}
          {phase === 'select' && (
            <Button
              disabled={!selectedFile || previewing}
              onClick={() => void startImport()}
            >
              <Upload aria-hidden='true' className='size-3.5' />
              开始导入
            </Button>
          )}
          {phase === 'preview' && (
            <Button onClick={() => void startImport()}>
              <Upload aria-hidden='true' className='size-3.5' />
              开始导入
            </Button>
          )}
          {phase === 'importing' && (
            <Button disabled className='gap-2'>
              <LoaderCircle aria-hidden='true' className='size-3.5 animate-spin' />
              正在导入…
            </Button>
          )}
          {phase === 'error' && (
            <Button variant='destructive' onClick={() => { setPhase('select'); setErrorMessage(''); }}>
              重新尝试
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
