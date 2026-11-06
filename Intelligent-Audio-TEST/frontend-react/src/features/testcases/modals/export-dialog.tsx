/**
 * 导出用例弹窗（11_用例域.md §5.7.2，Dialog sm:max-w-md）。
 * 导出范围 RadioGroup「按当前筛选条件导出（导出全部筛选结果）/仅导出已选 {n} 个用例」
 * + 格式 Select（ZIP 数据包 / Excel / JSON）+ ZIP 选项「包含参考参数文件」「包含音频文件」+ 主钮「开始导出」。
 * 与任务数据导出同型：ZIP 为完整用例数据包（manifest + testcases.json + 参考参数文件 [+ audios/ 音频]），
 * 可直接用于「导入用例」做跨环境搬运。
 * INT-1642 接线：真实 POST /testcases/export（testcase_export_service）——
 * - 已选范围直接用勾选 id；筛选范围由页面解析器（POST /testcases/ids 全量圈定，非仅当前页）；
 * - ZIP/Excel 后端回字节流直落下载；JSON 后端回数据信封，前端序列化为 .json 文件下载；
 * - 失败（空 ids 400「未指定要导出的用例ID」等）toast 透出后端 message。
 * INT-2154：弹窗给出「将导出 N 条用例」范围预览（开窗即按当前筛选解析全量 id，与真正导出
 * 同一份），未勾选时提示怎么去选，JSON 导出后按信封条数核对并提示不一致。
 * INT-2196：ZIP 选项增加「包含音频文件」（默认不勾，体积较大）；导出后按包内 `audios/` 条目
 * 核对，勾了却没打包时明确提示「音频仍以引用方式导出」，不假装成功。
 *
 * INT-2315（异步作业）：大范围导出不再让弹窗长时间卡在「导出中…」——
 * 点「开始导出」→ `POST /testcases/export/jobs` 提交作业（202）→ 按 `poll_after_ms` 轮询
 * `GET /jobs/{task_id}` 展示阶段与 processed/total → `done` 自动下载（优先 result.download_url
 * 直链，缺省走 `GET /jobs/{id}/download`）；失败给可读文案。
 * 关窗 / 卸载 / 取消即停止轮询，作业在服务端继续；重开弹窗按本地记忆提示「上次导出仍在进行」可续跟。
 * 同步 `POST /testcases/export` 保留为回退路径：老网关没有作业端点（404/405/501）时自动改走同步导出。
 * 注：页头「导入用例」为文件/用例包导入（ImportDialog：JSON/CSV/Excel/ZIP + 重复策略）；
 * 「导入音频生成用例」留在音频管理页（/AudioImport）上传并勾选生成，两个入口互不替代。
 */
import { FileSpreadsheet } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import {
  clearActiveExportJob,
  readActiveExportJob,
  rememberActiveExportJob,
} from '@/features/testcases/lib/export-job-memory'
import { countZipAudioEntries } from '@/features/testcases/lib/zip-audio-entries'
import { downloadBlob } from '@/lib/download-blob'
import { ApiError } from '@/infrastructure/api/api-error'
import {
  buildTestCaseExportFilename,
  downloadTestCaseExportJob,
  exportTestCases,
  fetchExportJobDownloadUrl,
  getTestCaseExportJob,
  isExportJobEndpointUnavailable,
  submitTestCaseExportJob,
  TEST_CASE_EXPORT_MIME,
  type TestCaseExportFormat,
} from '@/infrastructure/api/testcases-api'
import type {
  TestCaseExportJob,
  TestCaseExportJobPhase,
} from '@/domain/models/testCase'

type ExportScope = 'filter' | 'selected'

const FORMAT_OPTIONS: Array<{ value: TestCaseExportFormat; label: string }> = [
  { value: 'zip', label: 'ZIP 数据包（推荐）' },
  { value: 'xlsx', label: 'Excel' },
  { value: 'json', label: 'JSON' },
]

/** 阶段文案（契约：fetching=读取用例 / packaging=打包 / uploading=上传） */
const PHASE_COPY: Record<TestCaseExportJobPhase, string> = {
  fetching: '正在读取用例',
  packaging: '正在打包文件',
  uploading: '正在上传产物',
}

/** 作业级失败码的中文兜底（后端 message 缺失或非中文时使用） */
const FAILED_CODE_COPY: Record<string, string> = {
  EXPORT_NO_DATA: '没有可导出的用例',
  EXPORT_STORAGE_FAILED: '导出文件保存失败，请重试',
  GATEWAY_RESTARTED: '服务重启导致导出中断，请重新导出',
}

/** 连续轮询失败上限（网络抖动重试几次再收手） */
const MAX_POLL_FAILURES = 3

function formatLabel(format: TestCaseExportFormat): string {
  return FORMAT_OPTIONS.find((option) => option.value === format)?.label ?? format
}

/**
 * 导出失败文案（INT-2191）：504 是前端容器 nginx 反代 60s 超时返回的 HTML 错误体，
 * 后端 message 取不到，直接用 ApiError.message 会得到空的「导出失败：」。这里优先用
 * userMessage（服务端 message > 错误码 > HTTP 状态码兜底），504 另给可执行的缩小范围提示。
 */
function exportErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.httpStatus === 504) return '导出超时，请缩小筛选范围后重试'
    return error.userMessage || error.message || '请稍后重试'
  }
  return error instanceof Error && error.message ? error.message : '请稍后重试'
}

/** 作业失败文案：后端 message 优先；缺 message 时按错误码给中文兜底 */
export function exportJobErrorMessage(job: TestCaseExportJob): string {
  const message = job.error?.message?.trim()
  if (message) return message
  const code = job.error?.code ?? ''
  return FAILED_CODE_COPY[code] ?? '导出失败，请稍后重试'
}

/** 进度百分比（总量未知时按 0；done 直接满格） */
function progressPercent(job: TestCaseExportJob): number {
  if (job.status === 'done') return 100
  const total = job.progress?.total ?? job.total ?? 0
  const processed = job.progress?.processed ?? 0
  if (total <= 0) return 0
  return Math.min(100, Math.max(0, Math.round((processed / total) * 100)))
}

/** 进度区阶段文案（queued=排队中；running 按后端 phase；解析不到 phase 时给通用文案） */
function jobStageLabel(job: TestCaseExportJob): string {
  if (job.status === 'queued') return '排队中，等待开始'
  if (job.status === 'done') return '导出完成，正在下载'
  if (job.phase) return PHASE_COPY[job.phase]
  return '正在导出'
}

export function ExportDialog({
  open,
  onOpenChange,
  selectedCount = 0,
  selectedIds = [],
  resolveFilteredIds,
  filterSummary,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  selectedCount?: number
  /** 已选用例 id（导出范围=仅已选） */
  selectedIds?: string[]
  /**
   * 解析「当前筛选」全量 id（页面注入：POST /testcases/ids 按搜索/分组/标签/维度/算法圈定，
   * 非仅当前页；失败抛错由本弹窗 toast 透出）
   */
  resolveFilteredIds?: () => Promise<string[]>
  /** 当前筛选摘要（如「搜索：matrix」「标签：拒识」），用于弹窗内说明导出范围从何而来 */
  filterSummary?: string
}) {
  const [format, setFormat] = useState<TestCaseExportFormat>('zip')
  const [includeReferenceParams, setIncludeReferenceParams] = useState(true)
  /** 音频文件进包（INT-2196）：默认不勾，跨环境搬运需要时再开，避免默认导出体积暴涨 */
  const [includeAudios, setIncludeAudios] = useState(false)
  const [scope, setScope] = useState<ExportScope>('filter')
  /** 提交中（等着 202 / 429 回执的那一小段） */
  const [submitting, setSubmitting] = useState(false)
  /**
   * 「按当前筛选」全量 id 预览（INT-2154）：开窗即解析一次，弹窗直接展示「将导出 N 条用例」，
   * 与实际导出用同一份 id，避免用户以为导出的是眼前搜到的几条、实际导出全库。
   */
  const [filterIds, setFilterIds] = useState<string[] | null>(null)
  const [resolving, setResolving] = useState(false)
  const [resolveFailed, setResolveFailed] = useState(false)
  /** 解析器身份会随列表刷新变化，用 ref 取值避免预览 effect 被无意义地反复触发 */
  const resolveRef = useRef(resolveFilteredIds)
  useEffect(() => {
    resolveRef.current = resolveFilteredIds
  }, [resolveFilteredIds])
  /** 手动重试计数（解析失败时的「重试」只重新统计，不改筛选） */
  const [resolveAttempt, setResolveAttempt] = useState(0)
  const hasResolver = resolveFilteredIds != null

  /** 正在跟踪的作业快照（进度区数据源） */
  const [job, setJob] = useState<TestCaseExportJob | null>(null)
  /** 正在轮询的作业 id（null = 没有在跟踪；关窗 / 取消 / 终态时清空） */
  const [trackedTaskId, setTrackedTaskId] = useState<string | null>(null)
  /** 失败态（弹窗内保留失败原因，主钮可重试） */
  const [jobError, setJobError] = useState<string | null>(null)
  /** 上次提交的请求条数（progress 缺失时兜底，不臆造 0） */
  const requestedCountRef = useRef(0)
  /** 提交时的音频勾选（重新跟踪时按它决定是否核对包内 audios/） */
  const includeAudiosRef = useRef(false)
  /** 重开弹窗时的「上次导出仍在进行」提示 */
  const [resumable, setResumable] = useState<{
    taskId: string
    total: number
    includeAudios: boolean
  } | null>(null)

  const busy = submitting || trackedTaskId != null

  /**
   * 导出范围复位（INT-1642 代码审计 P3-2）：弹窗常驻挂载，上次选「仅导出已选」→ 取消 →
   * 清空勾选 → 重开，该 radio 会停在「禁用 + 选中」，点导出只报「请先选择要导出的用例」。
   * 开窗回落「按当前筛选」；勾选清零时若仍停在「已选」也回落（防清选后残留）。
   */
  useEffect(() => {
    if (open) setScope('filter')
  }, [open])

  useEffect(() => {
    if (selectedCount === 0 && scope === 'selected') setScope('filter')
  }, [selectedCount, scope])

  /**
   * 关窗：清空预览与本次跟踪（作业在服务端继续跑，重开时按本地记忆提示续跟），
   * 同时停掉轮询（INT-2315 契约第 3 条：关闭弹窗即停止轮询）。
   */
  useEffect(() => {
    if (open) return
    setFilterIds(null)
    setResolving(false)
    setResolveFailed(false)
    setTrackedTaskId(null)
    setJob(null)
    setJobError(null)
    setSubmitting(false)
  }, [open])

  /** 开窗：看本地有没有在办的导出作业（关窗 / 切页 / 刷新后仍能续跟） */
  useEffect(() => {
    if (!open) return
    const record = readActiveExportJob()
    setResumable(
      record
        ? { taskId: record.taskId, total: record.total, includeAudios: record.includeAudios }
        : null
    )
  }, [open])

  /** 按当前筛选统计导出范围（仅此范围需要；「仅已选」直接取勾选项） */
  useEffect(() => {
    if (!open || scope !== 'filter' || !hasResolver) return
    const resolve = resolveRef.current
    if (resolve == null) return
    let cancelled = false
    setResolving(true)
    setResolveFailed(false)
    resolve()
      .then((ids) => {
        if (cancelled) return
        setFilterIds(ids)
      })
      .catch(() => {
        if (cancelled) return
        setFilterIds(null)
        setResolveFailed(true)
      })
      .finally(() => {
        if (!cancelled) setResolving(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, scope, hasResolver, resolveAttempt])

  /** 导出范围预览条数（仅已选=勾选数；按筛选=解析到的全量 id 数） */
  const previewCount = scope === 'selected' ? selectedCount : (filterIds?.length ?? null)

  /**
   * 作业完成：优先用预签名直链取产物，取不到再走 `GET /jobs/{id}/download`；
   * 成功 toast 口径 `已导出 N 个用例`，N 取 progress.exported（缺条时另给告警）。
   */
  const finishDownload = useCallback(
    async (finished: TestCaseExportJob, withAudios: boolean) => {
      const result = finished.result
      const jobFormat = result?.format ?? format
      const filename = result?.filename || buildTestCaseExportFilename(jobFormat)
      try {
        let blob: Blob | null = null
        if (result?.downloadUrl) {
          try {
            blob = await fetchExportJobDownloadUrl(result.downloadUrl)
          } catch {
            // 直链过期 / 跨域 / 存储不可达 → 回落网关注册的下载端点
            blob = null
          }
        }
        if (blob == null) blob = await downloadTestCaseExportJob(finished.taskId)
        if (blob.size === 0) {
          toast.error('导出失败：后端返回空文件')
          setJobError('导出的文件为空，请重新导出')
          return
        }
        downloadBlob(blob, filename, blob.type || TEST_CASE_EXPORT_MIME[jobFormat])
        const exported = finished.progress?.exported ?? requestedCountRef.current
        const missing = finished.progress?.missing.length ?? 0
        toast.success(`已导出 ${exported} 个用例`, { description: filename })
        if (missing > 0) {
          toast.warning(`有 ${missing} 条用例未能导出`, {
            description: '缺失清单见结果文件的 manifest.missing_case_ids',
          })
        } else if (
          requestedCountRef.current > 0 &&
          exported !== requestedCountRef.current
        ) {
          toast.warning(
            `导出条数与请求不一致：请求 ${requestedCountRef.current} 条，实际 ${exported} 条`,
            { description: filename }
          )
        }
        // INT-2196：勾了「包含音频文件」就核对包内 `audios/` 条目；读不懂包体时不提示（不误报）
        if (jobFormat === 'zip' && withAudios) {
          const audioCount = await countZipAudioEntries(blob)
          if (audioCount === 0) {
            toast.warning('导出包内没有音频文件：用例音频仍以引用方式导出', {
              description: filename,
            })
          }
        }
        clearActiveExportJob()
        onOpenChange(false)
      } catch (error) {
        if (error instanceof ApiError && error.httpStatus === 410) {
          // 契约第 7 条：产物已过期 → 明确提示并复位弹窗
          toast.error('导出文件已过期，请重新导出')
          setJobError('导出文件已过期，请重新导出')
        } else {
          toast.error(`导出失败：${exportErrorMessage(error)}`)
          setJobError(exportErrorMessage(error))
        }
        clearActiveExportJob()
      } finally {
        setJob(null)
        setTrackedTaskId(null)
      }
    },
    [format, onOpenChange]
  )

  /**
   * 作业轮询（契约第 3 条）：间隔取响应 `poll_after_ms`（缺省 1000ms）；
   * 关窗 / 卸载 / 取消（trackedTaskId 清空）时 effect 清理 → 立即停止，不再发请求。
   * 完成回调走 ref：它随 format 变化而变化，若进依赖会让轮询被无谓重启（多发一轮请求）。
   */
  const finishRef = useRef(finishDownload)
  useEffect(() => {
    finishRef.current = finishDownload
  }, [finishDownload])

  useEffect(() => {
    if (!open || trackedTaskId == null) return
    const taskId = trackedTaskId
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const controller = new AbortController()

    const sleep = (ms: number) =>
      new Promise<void>((resolve) => {
        timer = setTimeout(resolve, ms)
      })

    const run = async () => {
      let delay = 0
      let failures = 0
      for (;;) {
        if (delay > 0) {
          await sleep(delay)
          if (cancelled) return
        }
        let next: TestCaseExportJob
        try {
          next = await getTestCaseExportJob(taskId, { signal: controller.signal })
        } catch (error) {
          if (cancelled) return
          if (error instanceof ApiError && error.httpStatus === 404) {
            toast.error('导出任务不存在或已过期，请重新导出')
            setJobError('导出任务不存在或已过期，请重新导出')
            clearActiveExportJob()
            setTrackedTaskId(null)
            setJob(null)
            return
          }
          failures += 1
          if (failures >= MAX_POLL_FAILURES) {
            toast.error(`导出进度查询失败：${exportErrorMessage(error)}`)
            setJobError(exportErrorMessage(error))
            setTrackedTaskId(null)
            return
          }
          delay = 1000
          continue
        }
        failures = 0
        if (cancelled) return
        setJob(next)
        if (next.status === 'done') {
          await finishRef.current(next, includeAudiosRef.current)
          return
        }
        if (next.status === 'failed') {
          const message = exportJobErrorMessage(next)
          toast.error(message)
          setJobError(message)
          clearActiveExportJob()
          setTrackedTaskId(null)
          return
        }
        if (next.status === 'expired') {
          toast.error('导出文件已过期，请重新导出')
          setJobError('导出文件已过期，请重新导出')
          clearActiveExportJob()
          setJob(null)
          setTrackedTaskId(null)
          return
        }
        delay = next.pollAfterMs ?? 1000
      }
    }

    void run()
    return () => {
      cancelled = true
      controller.abort()
      if (timer != null) clearTimeout(timer)
    }
  }, [open, trackedTaskId])

  /** 开始跟踪某个作业（提交成功 / 429 接管 / 继续跟踪上次任务共用） */
  const trackJob = useCallback(
    (next: TestCaseExportJob, total: number, withAudios: boolean) => {
      requestedCountRef.current = total
      includeAudiosRef.current = withAudios
      setJob(next)
      setJobError(null)
      setResumable(null)
      rememberActiveExportJob({
        taskId: next.taskId,
        total,
        format: next.result?.format ?? format,
        includeAudios: withAudios,
        startedAt: Date.now(),
      })
      setTrackedTaskId(next.taskId)
    },
    [format]
  )

  /** 同步导出回退路径（老网关没有作业端点时；语义与 INT-1642/2154/2196 完全一致） */
  const runSyncExport = useCallback(
    async (ids: string[]) => {
      const { blob, filename, exportedCount } = await exportTestCases(ids, format, {
        includeReferenceParams,
        includeAudios,
      })
      if (blob.size === 0) {
        toast.error('导出失败：后端返回空文件')
        return
      }
      downloadBlob(blob, filename, blob.type || 'application/octet-stream')
      // 导出后核对实际条数（JSON 信封可数；ZIP/Excel 为字节流，以请求 id 数为准）
      if (exportedCount != null && exportedCount !== ids.length) {
        toast.warning(
          `导出条数与筛选范围不一致：请求 ${ids.length} 条，实际 ${exportedCount} 条`,
          { description: filename }
        )
      } else {
        toast.success(`已导出 ${ids.length} 个用例`, { description: filename })
      }
      // INT-2196：勾了「包含音频文件」就核对包内 `audios/` 条目；读不懂包体时不提示（不误报）
      if (format === 'zip' && includeAudios) {
        const audioCount = await countZipAudioEntries(blob)
        if (audioCount === 0) {
          toast.warning('导出包内没有音频文件：用例音频仍以引用方式导出', {
            description: filename,
          })
        }
      }
      onOpenChange(false)
    },
    [format, includeAudios, includeReferenceParams, onOpenChange]
  )

  const handleExport = async () => {
    if (busy) return
    setSubmitting(true)
    setJobError(null)
    try {
      const ids =
        scope === 'selected'
          ? selectedIds
          : (filterIds ?? (await resolveRef.current?.()) ?? [])
      if (ids.length === 0) {
        toast.error(
          scope === 'selected'
            ? '请先选择要导出的用例'
            : '当前筛选条件下没有可导出的用例'
        )
        return
      }
      let submission
      try {
        submission = await submitTestCaseExportJob(ids, format, {
          includeReferenceParams,
          includeAudios,
        })
      } catch (error) {
        if (!isExportJobEndpointUnavailable(error)) throw error
        // 老网关（无异步作业端点）：静默回退到同步导出，行为与前几轮一致
        toast.info('异步导出不可用，已改用同步导出')
        await runSyncExport(ids)
        return
      }
      // 接管了在办的同一作业（429 或同参数幂等命中）才提示；命中「已完成」的旧作业直接下载即可
      if (
        submission.resumed &&
        (submission.job.status === 'queued' || submission.job.status === 'running')
      ) {
        toast.info('已有导出任务在进行，已接管继续跟踪')
      }
      trackJob(submission.job, ids.length, includeAudios)
    } catch (error) {
      toast.error(`导出失败：${exportErrorMessage(error)}`)
      setJobError(exportErrorMessage(error))
    } finally {
      setSubmitting(false)
    }
  }

  /** 继续跟踪上次的在办作业（关窗 / 切页 / 刷新后重开弹窗） */
  const resumeTracking = () => {
    if (resumable == null) return
    requestedCountRef.current = resumable.total
    includeAudiosRef.current = resumable.includeAudios
    setJob(null)
    setJobError(null)
    setTrackedTaskId(resumable.taskId)
    setResumable(null)
  }

  const jobPercent = job ? progressPercent(job) : 0
  const jobTotal = job?.progress?.total ?? job?.total ?? requestedCountRef.current
  const jobProcessed = job?.progress?.processed ?? 0

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>导出用例</DialogTitle>
          <DialogDescription>
            按当前筛选条件或已选用例导出；ZIP 数据包可直接用于「导入用例」跨环境搬运
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-4'>
          <fieldset className='space-y-2' disabled={busy}>
            <legend className='text-sm font-medium'>导出范围</legend>
            <label className='hover:bg-accent flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm'>
              <input
                type='radio'
                name='export-range'
                checked={scope === 'filter'}
                onChange={() => setScope('filter')}
              />
              按当前筛选条件导出（导出全部筛选结果）
            </label>
            <label
              className={
                selectedCount > 0
                  ? 'hover:bg-accent flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm'
                  : 'text-muted-foreground flex cursor-not-allowed items-center gap-2 rounded-md px-2 py-1.5 text-sm'
              }
            >
              <input
                type='radio'
                name='export-range'
                disabled={selectedCount === 0}
                checked={scope === 'selected'}
                onChange={() => setScope('selected')}
              />
              仅导出已选 {selectedCount} 个用例
            </label>
            {selectedCount === 0 && (
              <p className='text-muted-foreground ps-2 text-xs'>
                未选用例：先在列表勾选用例（或点列表头「全选用例」），再选此项；
                「按当前筛选条件导出」不受勾选影响。
              </p>
            )}
          </fieldset>

          {/* 导出范围预览（INT-2154）：说清这次到底导出多少条，避免把「搜到的几条」误当全部 */}
          <div className='bg-muted/40 rounded-lg px-3 py-2 text-xs'>
            {scope === 'selected' ? (
              <span>
                将导出{' '}
                <strong className='font-medium tabular-nums'>{selectedCount}</strong>{' '}
                条已选用例
              </span>
            ) : resolving ? (
              <span className='text-muted-foreground flex items-center gap-1.5'>
                <Spinner className='size-3.5' />
                正在统计当前筛选的导出条数…
              </span>
            ) : resolveFailed ? (
              <span className='flex flex-wrap items-center gap-1.5'>
                <span className='text-destructive'>无法预先统计导出条数</span>
                <span className='text-muted-foreground'>
                  导出时仍按当前筛选执行，失败会提示原因。
                </span>
                <Button
                  variant='link'
                  size='sm'
                  className='h-auto px-0 text-xs'
                  disabled={busy}
                  onClick={() => setResolveAttempt((n) => n + 1)}
                >
                  重新统计
                </Button>
              </span>
            ) : previewCount === 0 ? (
              <span className='text-destructive'>当前筛选条件下没有可导出的用例</span>
            ) : (
              <span>
                将导出{' '}
                <strong className='font-medium tabular-nums'>{previewCount ?? 0}</strong>{' '}
                条用例
                {filterSummary ? `（${filterSummary}）` : ''}
              </span>
            )}
          </div>

          <div className='flex items-center gap-2'>
            <span className='text-muted-foreground text-sm'>格式</span>
            <Select
              value={format}
              onValueChange={(v) => setFormat(v as TestCaseExportFormat)}
              items={FORMAT_OPTIONS}
              disabled={busy}
            >
              <SelectTrigger size='sm' className='h-8 w-44'>
                <SelectValue>{formatLabel(format)}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {FORMAT_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {format === 'zip' && (
            <div className='space-y-2'>
              <label className='flex cursor-pointer items-center gap-2 text-sm'>
                <Checkbox
                  checked={includeReferenceParams}
                  disabled={busy}
                  onCheckedChange={(v) => setIncludeReferenceParams(!!v)}
                />
                包含参考参数文件
              </label>
              <label className='flex cursor-pointer items-center gap-2 text-sm'>
                <Checkbox
                  checked={includeAudios}
                  disabled={busy}
                  onCheckedChange={(v) => setIncludeAudios(!!v)}
                />
                包含音频文件
                {/* ZIP 包内音频按字节/md5 回导（INT-2215/2216）：导入时自动登记或复用目标库音频，可跨环境迁移；文案口径同 09_任务域.md §5.12「（体积较大）」 */}
                <span className='text-muted-foreground text-xs'>
                  （体积较大）
                </span>
              </label>
            </div>
          )}

          {/* 上次导出仍在进行（契约第 8 条）：关窗 / 切页 / 刷新后作业仍在服务端跑，可续跟 */}
          {resumable && !busy && (
            <div className='bg-muted/40 flex flex-wrap items-center gap-2 rounded-lg px-3 py-2 text-xs'>
              <span>上次导出仍在进行（{resumable.total} 条）</span>
              <Button
                variant='link'
                size='sm'
                className='h-auto px-0 text-xs'
                onClick={resumeTracking}
              >
                继续跟踪
              </Button>
            </div>
          )}

          {/* 进度区（契约第 2 条）：阶段文案 + processed / total */}
          {busy && (
            <div className='space-y-2 rounded-lg border border-border/60 px-3 py-2'>
              <div className='bg-muted h-2 w-full overflow-hidden rounded-full'>
                <div
                  className='bg-primary h-full rounded-full transition-all duration-500'
                  style={{ width: `${jobPercent}%` }}
                  data-testid='export-job-progress-bar'
                />
              </div>
              <div className='text-muted-foreground flex items-center gap-2 text-xs'>
                <Spinner className='size-3.5' />
                <span>
                  {submitting && job == null ? '正在提交导出任务…' : job ? jobStageLabel(job) : '正在导出…'}
                </span>
                <span className='ms-auto font-mono tabular-nums'>
                  {jobProcessed} / {jobTotal || 0}
                </span>
              </div>
            </div>
          )}

          {jobError && (
            <p role='alert' className='text-destructive text-xs'>
              {jobError}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button
            variant='outline'
            onClick={() => {
              // 取消：停止跟踪（作业在服务端继续，下次开窗可续跟），关闭弹窗
              setTrackedTaskId(null)
              setJob(null)
              onOpenChange(false)
            }}
          >
            {busy ? '取消跟踪' : '取消'}
          </Button>
          <Button disabled={busy} onClick={() => void handleExport()}>
            {busy ? (
              <>
                <Spinner className='size-4' />
                导出中…
              </>
            ) : (
              <>
                <FileSpreadsheet aria-hidden='true' className='size-4' />
                开始导出
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
