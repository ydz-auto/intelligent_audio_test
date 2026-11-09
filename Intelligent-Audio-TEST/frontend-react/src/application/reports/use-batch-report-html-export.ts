/**
 * 报告中心批量 HTML 导出（application 层，INT-2419）。
 *
 * 负责人口径：批量导出的每一份都必须和「单独打开该报告详情 → 导出 HTML」一致。
 * 因此这里不写第二套布局/模板，而是**逐份串行**：
 *   1. 取报告详情（与详情页同一 queryKey，命中缓存不重复请求）；
 *   2. 挂载离屏宿主 `BatchExportStage`（渲染与详情页同一棵 `ReportViewBody` 组件树，
 *      `isExporting` 打开全量用例）；
 *   3. 用 INT-2418 的 `captureReportHtmlSnapshot` 产出 report.html / css（同一套清理、
 *      内联、图表静态化规则）；
 *   4. 卸载离屏宿主并清掉该报告的用例缓存，再处理下一份（大报告 500+ 用例，避免叠加占内存）。
 *
 * 失败隔离：单份取数超时 / 无权限 / 数据异常只记失败清单，不中断整批；成功的照常打包。
 * 取消：`cancel()` 置标记，等待循环在下一轮轮询退出，产物不下载、不留 zip。
 * 主题：与单份导出一致，采集前切浅色、结束后复原（主题由调用方经 before/afterCapture 处理）。
 */
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useRef, useState } from 'react'

import type { ReportDetailData } from '@/domain/models/report'
import { fetchReportDetail } from '@/infrastructure/api/reports-api'
import {
  BATCH_STAGE_ATTR,
  BATCH_STAGE_ERROR_ATTR,
  BATCH_STAGE_REPORT_ATTR,
  BATCH_STAGE_STATE_ATTR,
  buildBatchReportZip,
  uniqueReportDirName,
  type BatchHtmlEntry,
} from '@/features/report-view/export/batch-html-snapshot'
import {
  captureReportHtmlSnapshot,
  downloadBlob,
  HTML_EXPORT_CASE_PAGE_SIZE,
  HTML_EXPORT_READY_TIMEOUT_MS,
  REPORT_VIEW_ROOT_SELECTOR,
  waitForChartsPainted,
  waitForReportExportReady,
} from '@/features/report-view/export/html-snapshot'

/** 离屏宿主挂载上限（React 提交 + 首屏渲染） */
const STAGE_MOUNT_TIMEOUT_MS = 20_000
/** 单份报告整体上限（取数 + 全量用例 + 图表 + 快照），超时记失败并继续 */
const PER_REPORT_TIMEOUT_MS = 120_000
/** 轮询间隔 */
const POLL_INTERVAL_MS = 60
/** 辅助区块（Benchmark 排行 / 报告文档列表）取数等待上限；超时按现状快照 */
const AUX_READY_TIMEOUT_MS = 8_000

export interface BatchHtmlExportProgress {
  /** 1 基当前序号 */
  current: number
  total: number
  reportName: string
}

export interface BatchHtmlExportFailure {
  reportId: number
  reportName: string
  reason: string
}

export interface BatchHtmlExportResult {
  /** 成功打包的份数 */
  succeeded: number
  failed: BatchHtmlExportFailure[]
  cancelled: boolean
  /** 批量 zip 文件名（未取消且至少 1 份成功时有值） */
  fileName?: string
  durationMs: number
  /** 实测 JS 堆峰值（MB；仅 Chromium 有 performance.memory） */
  peakHeapMB?: number
}

export interface UseBatchReportHtmlExportOptions {
  /** 采集前：切浅色并等主题重建（与单份导出同口径） */
  beforeCapture?: () => Promise<void> | void
  /** 采集后：复原主题 */
  afterCapture?: () => void
}

export interface BatchReportHtmlExportController {
  exporting: boolean
  /** 进度（非空表示正在导出） */
  progress: BatchHtmlExportProgress | null
  /** 离屏宿主当前渲染的报告 id（页面据此挂载 `BatchExportStage`） */
  stageReportId: number | null
  /** 最近一次导出结果（含失败清单） */
  lastResult: BatchHtmlExportResult | null
  exportBatch: (
    reportIds: number[],
    /** 已知报告名（列表页已有）：进度首帧就能显示报告名，不必等详情返回 */
    knownNames?: Record<number, string>
  ) => Promise<BatchHtmlExportResult>
  /** 取消当前批量导出（当前份结束后不再继续，不产出 zip） */
  cancel: () => void
  /** 清掉上一次的结果面板（重新打开导出弹窗时用） */
  reset: () => void
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function nextPaint(): Promise<void> {
  return new Promise((resolve) =>
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
  )
}

function readHeapMB(): number {
  const memory = (performance as Performance & { memory?: { usedJSHeapSize?: number } }).memory
  const used = memory?.usedJSHeapSize
  return typeof used === 'number' ? Math.round((used / (1024 * 1024)) * 10) / 10 : 0
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message
  if (typeof error === 'string' && error) return error
  return '导出失败'
}

/** 单份超时保护（不中断仍在跑的网络请求，只让本份尽快记失败） */
function withTimeout<T>(promise: Promise<T>, ms: number, message: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(message)), ms)
    promise.then(
      (value) => {
        clearTimeout(timer)
        resolve(value)
      },
      (error) => {
        clearTimeout(timer)
        reject(error)
      }
    )
  })
}

/**
 * 等辅助区块就绪：Benchmark 排行（Skeleton）与报告文档列表（animate-spin spinner）
 * 都是独立 query，晚于具体用例解析；不等它们就快照会得到骨架屏 / 「加载中…」。
 * 超时按现状继续，不因辅助区块卡死整份导出。
 */
async function waitForAuxiliaryReady(
  root: HTMLElement,
  timeoutMs = AUX_READY_TIMEOUT_MS
): Promise<void> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const pending = root.querySelectorAll('[data-slot="skeleton"], svg.animate-spin')
    if (pending.length === 0) return
    await sleep(120)
  }
}

export function useBatchReportHtmlExport(
  options: UseBatchReportHtmlExportOptions = {}
): BatchReportHtmlExportController {
  const queryClient = useQueryClient()
  const [exporting, setExporting] = useState(false)
  const [progress, setProgress] = useState<BatchHtmlExportProgress | null>(null)
  const [stageReportId, setStageReportId] = useState<number | null>(null)
  const [lastResult, setLastResult] = useState<BatchHtmlExportResult | null>(null)

  const busy = useRef(false)
  const cancelled = useRef(false)
  const optionsRef = useRef(options)
  optionsRef.current = options

  const cancel = useCallback(() => {
    if (busy.current) cancelled.current = true
  }, [])

  const reset = useCallback(() => setLastResult(null), [])

  /** 等离屏宿主把第 N 份渲染到 ready，返回可快照的根容器 */
  const waitForStageRoot = useCallback(async (reportId: number): Promise<HTMLElement> => {
    const deadline = Date.now() + STAGE_MOUNT_TIMEOUT_MS
    const selector = `[${BATCH_STAGE_ATTR}][${BATCH_STAGE_REPORT_ATTR}="${reportId}"]`
    while (Date.now() < deadline) {
      if (cancelled.current) throw new Error('已取消批量导出')
      const stage = document.querySelector<HTMLElement>(selector)
      if (stage) {
        const state = stage.getAttribute(BATCH_STAGE_STATE_ATTR)
        if (state === 'error') {
          throw new Error(stage.getAttribute(BATCH_STAGE_ERROR_ATTR) || '报告取数失败')
        }
        if (state === 'ready') {
          const root = stage.querySelector<HTMLElement>(REPORT_VIEW_ROOT_SELECTOR)
          if (root) return root
        }
      }
      await sleep(POLL_INTERVAL_MS)
    }
    throw new Error('报告离屏渲染超时')
  }, [])

  const captureOne = useCallback(
    async (reportId: number, fallbackName: string): Promise<{ entry: BatchHtmlEntry; peakHeapMB: number }> => {
      const detail = await queryClient.fetchQuery<ReportDetailData>({
        queryKey: ['reports', 'detail', reportId],
        queryFn: () => fetchReportDetail(reportId),
        staleTime: 30_000,
      })
      if (cancelled.current) throw new Error('已取消批量导出')
      const reportName = detail.name || fallbackName

      setStageReportId(reportId)
      const root = await waitForStageRoot(reportId)
      if (cancelled.current) throw new Error('已取消批量导出')

      // 与单份导出一致：等全量用例写入 DOM，再等 VChart canvas 绘制完成
      const ready = await waitForReportExportReady(root, HTML_EXPORT_READY_TIMEOUT_MS)
      if (!ready) throw new Error('用例数据就绪超时')
      await waitForAuxiliaryReady(root)
      await waitForChartsPainted(root)
      if (cancelled.current) throw new Error('已取消批量导出')

      const parts = await captureReportHtmlSnapshot(root, {
        fileName: reportName,
        pageSize: HTML_EXPORT_CASE_PAGE_SIZE,
      })
      return {
        entry: { dir: '', reportName, html: parts.html, css: parts.css },
        peakHeapMB: readHeapMB(),
      }
    },
    [queryClient, waitForStageRoot]
  )

  const exportBatch = useCallback(
    async (
      reportIds: number[],
      knownNames?: Record<number, string>
    ): Promise<BatchHtmlExportResult> => {
      if (busy.current) throw new Error('正在导出，请稍候')
      if (reportIds.length === 0) throw new Error('没有可导出的报告')

      busy.current = true
      cancelled.current = false
      setExporting(true)
      setLastResult(null)
      const startedAt = Date.now()
      const failed: BatchHtmlExportFailure[] = []
      const entries: BatchHtmlEntry[] = []
      const usedDirs = new Set<string>()
      let peakHeapMB = 0
      let wasCancelled = false

      try {
        await optionsRef.current.beforeCapture?.()
        for (let index = 0; index < reportIds.length; index += 1) {
          const reportId = reportIds[index]
          if (cancelled.current) {
            wasCancelled = true
            break
          }
          let reportName = knownNames?.[reportId] || `报告 #${reportId}`
          setProgress({ current: index + 1, total: reportIds.length, reportName })
          try {
            const outcome = await withTimeout(
              captureOne(reportId, reportName),
              PER_REPORT_TIMEOUT_MS,
              '报告导出超时'
            )
            reportName = outcome.entry.reportName
            entries.push({ ...outcome.entry, dir: uniqueReportDirName(reportName, usedDirs) })
            peakHeapMB = Math.max(peakHeapMB, outcome.peakHeapMB)
            setProgress({ current: index + 1, total: reportIds.length, reportName })
          } catch (error) {
            if (cancelled.current) {
              wasCancelled = true
              break
            }
            failed.push({ reportId, reportName, reason: errorMessage(error) })
          } finally {
            // 卸载本份离屏 DOM，等 React 提交完再清缓存（先清会让仍挂载的宿主立刻重取）
            setStageReportId(null)
            await nextPaint()
            // 每份导出完释放它的用例/详情缓存（大报告 500+ 用例，避免叠加吃内存）
            queryClient.removeQueries({ queryKey: ['reports', 'cases', reportId] })
            queryClient.removeQueries({ queryKey: ['reports', 'detail', reportId] })
          }
        }

        if (wasCancelled) {
          const result: BatchHtmlExportResult = {
            succeeded: 0,
            failed,
            cancelled: true,
            durationMs: Date.now() - startedAt,
            peakHeapMB: peakHeapMB || undefined,
          }
          setLastResult(result)
          return result
        }

        // 全部失败：不产出空 zip（调用方按 failed 清单提示）
        if (entries.length === 0) {
          const result: BatchHtmlExportResult = {
            succeeded: 0,
            failed,
            cancelled: false,
            durationMs: Date.now() - startedAt,
            peakHeapMB: peakHeapMB || undefined,
          }
          setLastResult(result)
          return result
        }

        const { blob, fileName } = await buildBatchReportZip(entries)
        downloadBlob(blob, fileName)

        const result: BatchHtmlExportResult = {
          succeeded: entries.length,
          failed,
          cancelled: false,
          fileName,
          durationMs: Date.now() - startedAt,
          peakHeapMB: peakHeapMB || undefined,
        }
        setLastResult(result)
        return result
      } finally {
        setStageReportId(null)
        setProgress(null)
        optionsRef.current.afterCapture?.()
        busy.current = false
        setExporting(false)
      }
    },
    [captureOne, queryClient]
  )

  return { exporting, progress, stageReportId, lastResult, exportBatch, cancel, reset }
}
