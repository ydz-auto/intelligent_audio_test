/**
 * 报告详情 HTML 快照导出（application 层，INT-2418）。
 *
 * 导出产物是页面所见的静态快照（前端克隆 DOM + 内联样式 + 打包 zip），不再调用
 * `POST /reports/export`；csv / json / excel / pdf 仍走后端导出链路。
 *
 * 时序（对齐 V9.7.10 `exportHtml()`）：
 * 1. 调用方在 `beforeCapture` 里置导出态（展开全部分区、灌满具体用例、必要时切浅色）；
 * 2. 等具体用例分区写入 `data-export-cases-ready="true"`；
 * 3. 克隆 + 静态化 + 打包 + 触发下载；
 * 4. `afterCapture` 复原页面（折叠状态、分页、主题都由 React 状态回退，本层不直接改 DOM）。
 */
import { useCallback, useRef, useState } from 'react'

import {
  downloadBlob,
  exportReportHtml,
  HTML_EXPORT_CASE_PAGE_SIZE,
  HTML_EXPORT_READY_TIMEOUT_MS,
  waitForReportExportReady,
  type HtmlExportArtifact,
} from '@/features/report-view/export/html-snapshot'

export interface UseReportHtmlExportOptions {
  /** 报告详情滚动容器（`.report-view-container`） */
  getRoot: () => HTMLElement | null
  /** 报告名（zip 文件名与 report.html 标题） */
  getReportName: () => string
  /** 采集前：置导出态 + 切浅色 + 等 React 提交 */
  beforeCapture?: () => Promise<void> | void
  /** 采集后：复原主题等 */
  afterCapture?: () => void
  /** 等待导出态数据就绪的上限 */
  timeoutMs?: number
}

export interface ReportHtmlExportController {
  /** 正在打包（按钮禁用 / 导出态标记） */
  exporting: boolean
  /** 执行一次 HTML 快照导出，返回产物（失败抛错，由调用方提示） */
  exportHtml: () => Promise<HtmlExportArtifact>
}

export function useReportHtmlExport(
  options: UseReportHtmlExportOptions
): ReportHtmlExportController {
  const [exporting, setExporting] = useState(false)
  const busy = useRef(false)
  // 每次渲染刷新闭包，避免调用方内联回调导致 useCallback 依赖抖动
  const optionsRef = useRef(options)
  optionsRef.current = options

  const exportHtml = useCallback(async (): Promise<HtmlExportArtifact> => {
    // 导出中重复点击不重复打包
    if (busy.current) throw new Error('正在导出，请稍候')
    const root = optionsRef.current.getRoot()
    if (!root) throw new Error('未找到报告内容，无法导出')
    busy.current = true
    setExporting(true)
    try {
      await optionsRef.current.beforeCapture?.()
      await waitForReportExportReady(
        root,
        optionsRef.current.timeoutMs ?? HTML_EXPORT_READY_TIMEOUT_MS
      )
      const artifact = await exportReportHtml(root, {
        fileName: optionsRef.current.getReportName(),
        pageSize: HTML_EXPORT_CASE_PAGE_SIZE,
      })
      downloadBlob(artifact.blob, artifact.fileName)
      return artifact
    } finally {
      optionsRef.current.afterCapture?.()
      busy.current = false
      setExporting(false)
    }
  }, [])

  return { exporting, exportHtml }
}
