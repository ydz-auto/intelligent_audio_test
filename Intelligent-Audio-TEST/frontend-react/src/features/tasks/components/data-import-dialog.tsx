/**
 * 导入数据弹窗（09_任务域.md §5.12 + 链路 2 增量回导 INT-1765）。
 *
 * - 整包（mode='full'，既有交互不变）：选文件（.zip）→ 预检（版本/导出时间/源服务器 +
 *   任务清单 + 统计行 + ID 冲突 + 警告）→ POST /data-transfer/import → 进度 → 完成统计。
 * - 增量（mode='incremental'）：选文件 → 预检（复用 POST /data-transfer/import/preview
 *   解析 1.1 增量包：源任务、A 库任务匹配、将被覆盖的维度评分行数 / 报告数、warnings）
 *   → 确认 → POST /data-transfer/import-incremental（进度 parsing → merging_dimensions
 *   → replacing_reports → done/error，GET /import/progress 3s 兜底轮询）
 *   → 回执（覆盖维度行数、替换报告 id、warnings、批次号、可回滚）或失败回执
 *   （前置校验未写入 / 已逆序回滚 / 补偿失败需人工介入 + 批次号）。
 *
 * 请求一律经 infrastructure/api/data-transfer-api（client.ts），页面层只见 camelCase Domain。
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
  IncrementalImportPreview,
  IncrementalImportResult,
} from '@/domain/models/data-transfer'
import {
  executeImport,
  executeIncrementalImport,
  getImportProgress,
  previewImport,
  previewIncrementalImport,
} from '@/infrastructure/api/data-transfer-api'
import { ApiError } from '@/infrastructure/api/api-error'
import { fetchTaskDetail } from '@/infrastructure/api/tasks-list-api'
import { Progress } from '@/features/tasks/components/ui/progress'

type Phase = 'select' | 'preview' | 'importing' | 'done' | 'error'
type DataImportMode = 'full' | 'incremental'

/** 增量包 manifest 版本（整包为 1.0；1.1 = 增量 / 报告包） */
const INCREMENTAL_MANIFEST_VERSION = '1.1'
/** 增量导入进度兜底轮询间隔（断流时仍能推进） */
const INCREMENTAL_POLL_INTERVAL_MS = 3000

const STEP_TEXT: Record<string, string> = {
  parsing: '解析导出包',
  writing_db: '写入数据库',
  extracting_files: '回写文件',
  updating_paths: '更新文件路径',
  merging_dimensions: '合并维度评分',
  replacing_reports: '替换平台报告',
  done: '导入完成',
  error: '导入失败',
}

const TARGET_RESOLVED_TEXT: Record<string, string> = {
  source_map: '按源映射定位',
  target_report_id: '按包内报告 id 定位',
  latest_task_report: '按原任务最新报告定位',
  created: '新建报告',
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

/**
 * 读取 ApiError 承载的服务端失败明细（增量端点把明细放在响应体 `data`：
 * unmappedResultIds / missingIds / expected+actual / batchId / compensationErrors）。
 * client.ts 当前只透出 detail/errors，data 的透出由基座子卡补齐；此处先兼容读，
 * 未到位时回落到 detail 与文案解析，不阻断回执展示。
 */
function readErrorData(error: ApiError): Record<string, unknown> {
  const withData = (error as ApiError & { data?: unknown }).data
  if (withData && typeof withData === 'object' && !Array.isArray(withData)) {
    return withData as Record<string, unknown>
  }
  if (error.detail && typeof error.detail === 'object' && !Array.isArray(error.detail)) {
    return error.detail as Record<string, unknown>
  }
  return {}
}

/** 服务端文案里兜底提取批次号（500 补偿失败文案：batch_id=xxx / batchId=xxx） */
function extractBatchId(message: string): string {
  const matched = /batch_?id\s*[=：:]\s*([0-9a-zA-Z-]{8,})/i.exec(message)
  return matched?.[1] ?? ''
}

export function DataImportDialog({
  open,
  onOpenChange,
  onImported,
  mode = 'full',
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 导入完成：父层刷新任务列表与报告计数 */
  onImported?: () => void
  /** full=整包导入（默认）；incremental=增量回导（链路 2） */
  mode?: DataImportMode
}) {
  const incremental = mode === 'incremental'
  const navigate = useNavigate()
  const { hasPermission } = usePermissions()

  const [phase, setPhase] = useState<Phase>('select')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [incrementalPreview, setIncrementalPreview] =
    useState<IncrementalImportPreview | null>(null)
  /** A 库任务匹配结果（增量预检：id 是否真实存在 + 名称是否一致） */
  const [targetTask, setTargetTask] = useState<{
    found: boolean
    name: string
    status: string
  } | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [progress, setProgress] = useState<ImportProgress>(INITIAL_PROGRESS)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [incrementalResult, setIncrementalResult] =
    useState<IncrementalImportResult | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  /** 增量失败回执（明确「未写入 / 已回滚 / 需人工介入」+ 批次号） */
  const [failure, setFailure] = useState<{
    message: string
    guidance: string
    batchId: string
  } | null>(null)
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

  const resetState = () => {
    setPhase('select')
    setPreview(null)
    setIncrementalPreview(null)
    setTargetTask(null)
    setResult(null)
    setIncrementalResult(null)
    setProgress(INITIAL_PROGRESS)
    setErrorMessage('')
    setFailure(null)
    setSelectedFile(null)
  }

  useEffect(() => {
    if (!open) {
      stopWatching()
      // 重开时复位状态机（§5.12 三段式从选文件重新走）
      resetState()
    }
    return stopWatching
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const onFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    setSelectedFile(file)
    setPreview(null)
    setErrorMessage('')
    setFailure(null)
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

  const onIncrementalFileChange = async (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = event.target.files?.[0]
    if (!file) return
    setSelectedFile(file)
    setIncrementalPreview(null)
    setTargetTask(null)
    setFailure(null)
    setErrorMessage('')
    setPreviewing(true)
    try {
      const data = await previewIncrementalImport(file)
      if (data.version !== INCREMENTAL_MANIFEST_VERSION || data.sourceTaskId == null) {
        setFailure({
          message: `该 ZIP 不是增量包（manifest 版本 ${data.version || '未知'}）`,
          guidance:
            '增量回导只接受「导出增量」产出的 1.1 包；整包请改用「导入数据」。',
          batchId: '',
        })
        setPhase('error')
        return
      }
      setIncrementalPreview(data)
      // 包内 tasks[0] 是否真实存在于本侧（不存在/已删 → 导入会被 404 拒绝）
      try {
        const detail = await fetchTaskDetail(data.sourceTaskId)
        setTargetTask({
          found: true,
          name: detail.name,
          status: detail.status,
        })
      } catch {
        setTargetTask({ found: false, name: '', status: '' })
      }
      setPhase('preview')
    } catch (error) {
      setErrorMessage(
        error instanceof ApiError
          ? (error.userMessage || error.message || '预检失败：无法解析该增量包')
          : '预检失败：无法解析该增量包'
      )
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

  const startIncrementalImport = async () => {
    if (!selectedFile) return
    setFailure(null)
    setIncrementalResult(null)
    setErrorMessage('')
    setPhase('importing')
    pollTimer.current = setInterval(
      () => void pollProgress(),
      INCREMENTAL_POLL_INTERVAL_MS
    )
    try {
      const data = await executeIncrementalImport(selectedFile)
      setIncrementalResult(data)
      setPhase('done')
      toast.success('增量回导完成')
      onImported?.()
    } catch (error) {
      const apiError = error instanceof ApiError ? error : null
      const message = apiError
        ? apiError.userMessage || apiError.message || '增量导入失败'
        : '增量导入失败'
      const data = apiError ? readErrorData(apiError) : {}
      let batchId = String(data.batchId ?? '') || extractBatchId(message)
      if (!batchId) {
        // 失败明细在响应体 data（client 尚未透出）时，用同一次导入的进度快照补批次号：
        // 后端的 ImportProgressReporter 在 ERROR 上报里带 batch_id
        try {
          const snapshot = await getImportProgress()
          batchId = snapshot?.batchId ?? ''
        } catch {
          // 快照不可用则留空，回执只展示回滚口径
        }
      }
      const compensationErrors = Array.isArray(data.compensationErrors)
        ? data.compensationErrors
        : []
      const status = apiError?.httpStatus ?? null
      // 有段落失败（后端已按逆序补偿）→ 回滚口径；纯前置校验（400/403/404/409）未写数据
      const rolledBack =
        compensationErrors.length > 0 ||
        Boolean(batchId) ||
        status === 500 ||
        /替换失败|合并失败|回滚/.test(message)
      setFailure({
        message,
        batchId,
        guidance:
          compensationErrors.length > 0
            ? `已按逆序回滚（报告 → 维度），但补偿部分失败，需人工介入核查${
                batchId ? `（批次号 ${batchId}，登记保留 7 天）` : ''
              }。`
            : rolledBack
              ? '已回滚至导入前状态，原任务数据未被改动。'
              : '前置校验未通过，未写入任何数据（无需回滚）。',
      })
      setPhase('error')
    } finally {
      stopWatching()
    }
  }

  const goDailyList = () => {
    void navigate({ to: '/tasks/$tab', params: { tab: 'daily' } })
    onOpenChange(false)
  }

  const sourceTaskNameMismatch =
    incrementalPreview != null &&
    targetTask?.found === true &&
    targetTask.name !== incrementalPreview.sourceTaskName

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>{incremental ? '导入增量数据' : '导入任务数据'}</DialogTitle>
          <DialogDescription>
            {incremental
              ? '把增量包里的新评估与最新报告合并到本侧原任务（覆盖维度评分、原地替换报告，不新建任务）'
              : '从导出包 ZIP 恢复任务数据（预检 → 导入 → 完成统计）'}
          </DialogDescription>
        </DialogHeader>

        <div className='flex flex-col gap-3'>
          {/* 步骤 1：选文件 */}
          {phase === 'select' && (
            <label className='flex cursor-pointer flex-col items-center gap-1.5 rounded-lg border border-dashed bg-muted/30 px-4 py-8 text-sm transition-colors hover:bg-muted/50'>
              <FileUp aria-hidden='true' className='text-muted-foreground size-6' />
              <span className='text-muted-foreground'>
                {incremental ? '选择增量包（.zip）' : '选择导出包（.zip）'}
              </span>
              <span className='text-muted-foreground/70 text-xs'>
                {incremental
                  ? '由对侧「导出增量」产出（manifest 1.1）'
                  : '支持由本系统导出的任务数据包'}
              </span>
              <input
                type='file'
                accept='.zip'
                className='hidden'
                onChange={(e) =>
                  void (incremental ? onIncrementalFileChange(e) : onFileChange(e))
                }
              />
            </label>
          )}

          {previewing && (
            <p className='text-muted-foreground flex items-center gap-2 text-xs'>
              <Spinner size={14} />
              正在解析导出包…
            </p>
          )}

          {/* 步骤 2a：整包预检结果 */}
          {!incremental && preview && (
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

          {/* 步骤 2b：增量预检结果（源任务 / 任务匹配 / 将被覆盖的维度与报告 / warnings） */}
          {incremental && incrementalPreview && (
            <div className='flex flex-col gap-2'>
              <p className='text-sm font-medium'>预检结果</p>
              <div className='text-muted-foreground flex flex-col gap-0.5 rounded-lg border bg-muted/30 px-3 py-2 text-xs'>
                <span>
                  版本：{incrementalPreview.version}　导出时间：
                  {incrementalPreview.exportedAt || '未知'}
                </span>
                <span>源服务器：{incrementalPreview.source || '未知'}</span>
              </div>

              <div className='flex flex-col gap-0.5 rounded-lg border px-3 py-2 text-xs'>
                <span className='text-sm font-medium'>源任务</span>
                <span>
                  #{incrementalPreview.sourceTaskId}　{incrementalPreview.sourceTaskName || '（无名称）'}
                </span>
                <span className='text-muted-foreground'>
                  {incrementalPreview.sourceTaskStatus || '状态未知'} ·{' '}
                  {incrementalPreview.sourceTaskResultCount} 条结果
                </span>
              </div>

              {targetTask === null ? (
                <p className='text-muted-foreground text-xs'>正在核对本侧任务匹配…</p>
              ) : targetTask.found ? (
                <Alert>
                  <AlertTitle>任务匹配：本侧存在该任务</AlertTitle>
                  <AlertDescription>
                    #{incrementalPreview.sourceTaskId}「{targetTask.name}」
                    {sourceTaskNameMismatch
                      ? `（名称与包内「${incrementalPreview.sourceTaskName}」不一致，按任务 id 合并）`
                      : ''}
                  </AlertDescription>
                </Alert>
              ) : (
                <Alert variant='destructive'>
                  <AlertTitle>任务匹配：本侧未找到 #{incrementalPreview.sourceTaskId}</AlertTitle>
                  <AlertDescription>
                    该任务不存在或已删除，导入将被拒绝（404）。请确认增量包与本侧任务是否同一环境。
                  </AlertDescription>
                </Alert>
              )}

              <p className='text-muted-foreground text-xs'>
                将被覆盖：维度评分 {incrementalPreview.dimensionCount} 行 · 报告{' '}
                {incrementalPreview.reportCount} 份（原地替换，保留任务与报告 id）
              </p>
              <p className='text-muted-foreground/80 text-xs'>
                导入时会按用例集指纹校验，与包内不一致将拒绝合并（409）。
              </p>

              {incrementalPreview.warnings.length > 0 && (
                <ul className='text-muted-foreground ml-4 list-disc text-xs'>
                  {incrementalPreview.warnings.map((w, i) => (
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

          {/* 步骤 4a：整包完成统计 + 动作组 */}
          {!incremental && result && phase === 'done' && (
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

          {/* 步骤 4b：增量回执 */}
          {incremental && incrementalResult && phase === 'done' && (
            <div className='flex flex-col gap-2'>
              <p className='text-sm font-medium'>增量回导完成</p>
              <div className='flex flex-col gap-0.5 rounded-lg border bg-muted/30 px-3 py-2 text-xs'>
                <span>
                  任务 #{incrementalResult.taskId}：合并维度评分{' '}
                  {incrementalResult.mergedDimensions} 行（覆盖前删除旧行{' '}
                  {incrementalResult.deletedDimensions} 行）
                </span>
                <span>
                  报告：替换 {incrementalResult.insertedReports} 份 · 目标报告 #
                  {incrementalResult.replacedReportId ?? '新建'}（
                  {TARGET_RESOLVED_TEXT[incrementalResult.targetResolvedBy] ||
                    incrementalResult.targetResolvedBy ||
                    '未知依据'}
                  ）
                </span>
                <span>批次号：{incrementalResult.batchId || '—'}</span>
                <span>
                  {incrementalResult.rollbackAvailable
                    ? '批次快照已保留（7 天内可人工回滚）'
                    : '无合并段，未生成批次快照'}
                </span>
              </div>
              {incrementalResult.skippedDimensions.length > 0 && (
                <Alert className='border-warning/40'>
                  <AlertTitle className='text-warning'>
                    跳过 {incrementalResult.skippedDimensions.length} 个未匹配维度
                  </AlertTitle>
                  <AlertDescription>
                    维度 id：
                    {incrementalResult.skippedDimensions.slice(0, 20).join('、')}
                    {incrementalResult.skippedDimensions.length > 20 ? ' 等' : ''}
                    ；目标库缺少同名（同父链 / 同任务类型）维度定义，相关评分未写入。
                  </AlertDescription>
                </Alert>
              )}
              {incrementalResult.warnings.length > 0 && (
                <ul className='text-muted-foreground ml-4 list-disc text-xs'>
                  {incrementalResult.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              )}
              <p className='text-muted-foreground text-xs'>
                任务 id 未变化、未产生新任务副本；任务列表报告数与详情页报告页签已刷新。
              </p>
              <div className='flex flex-wrap items-center gap-2'>
                {hasPermission('task:read') && (
                  <Button size='sm' variant='outline' className='h-7' onClick={goDailyList}>
                    查看任务详情
                  </Button>
                )}
              </div>
            </div>
          )}

          {/* 整包失败回滚信息（UC-03） */}
          {!incremental && errorMessage && (
            <Alert variant='destructive'>
              <AlertTitle>导入失败：已回滚至导入前状态</AlertTitle>
              <AlertDescription>
                {errorMessage}；已回滚至导入前状态，磁盘文件已清理。
              </AlertDescription>
            </Alert>
          )}

          {/* 增量失败回执（未写入 / 已回滚 / 需人工介入 + 批次号） */}
          {incremental && failure && (
            <Alert variant='destructive'>
              <AlertTitle>增量回导失败</AlertTitle>
              <AlertDescription>
                <span>{failure.message}</span>
                <span className='mt-1 block font-medium'>{failure.guidance}</span>
                {failure.batchId && (
                  <span className='mt-1 block'>批次号：{failure.batchId}</span>
                )}
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
          {!incremental && phase === 'select' && (
            <Button
              disabled={!selectedFile || previewing}
              onClick={() => void startImport()}
            >
              <Upload aria-hidden='true' className='size-3.5' />
              开始导入
            </Button>
          )}
          {!incremental && phase === 'preview' && (
            <Button onClick={() => void startImport()}>
              <Upload aria-hidden='true' className='size-3.5' />
              开始导入
            </Button>
          )}
          {incremental && phase === 'preview' && (
            <Button onClick={() => void startIncrementalImport()}>
              <Upload aria-hidden='true' className='size-3.5' />
              开始导入增量
            </Button>
          )}
          {phase === 'importing' && (
            <Button disabled className='gap-2'>
              <LoaderCircle aria-hidden='true' className='size-3.5 animate-spin' />
              正在导入…
            </Button>
          )}
          {phase === 'error' && (
            <Button
              variant='destructive'
              onClick={() => {
                resetState()
              }}
            >
              重新尝试
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
