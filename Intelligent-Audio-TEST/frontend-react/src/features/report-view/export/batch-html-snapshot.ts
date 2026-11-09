/**
 * 报告批量 HTML 导出（INT-2419）：把每份报告的单份快照片段装进一个 zip。
 *
 * 口径（负责人 2026-11-09「批量导出的得想办法和单个导出一致」）：
 * - 每份报告的 `report.html` / `css/report.css` 都由 `captureReportHtmlSnapshot`
 *   （INT-2418 的单份管线：克隆 DOM、剪操作按钮、canvas 静态化、样式内联）产出，
 *   不重写、不降级；
 * - zip 结构：`<报告名>/report.html` + `<报告名>/css/report.css`，与单份 zip 内部结构一致；
 * - 同名报告追加 `（2）`/`（3）`，不覆盖；
 * - 根目录 `index.html` 列清单与链接，`file://` 下可直接点进各份。
 */
import JSZip from 'jszip'

import { sanitizeFileName } from './html-snapshot'

/** 批量 zip 内每个报告子目录里的固定文件名（与单份 zip 一致） */
export const BATCH_REPORT_FILE = 'report.html'
export const BATCH_CSS_DIR = 'css'
export const BATCH_CSS_FILE = 'report.css'
/** 批量 zip 根目录清单页 */
export const BATCH_INDEX_FILE = 'index.html'

/**
 * 离屏渲染宿主的 DOM 契约（编排层按这些属性判断「第 N 份渲染到哪一步」）。
 * 宿主组件写、`use-batch-report-html-export` 读；两边共用这里的常量，避免魔法字符串。
 */
export const BATCH_STAGE_ATTR = 'data-batch-export-stage'
export const BATCH_STAGE_REPORT_ATTR = 'data-batch-export-report-id'
export const BATCH_STAGE_STATE_ATTR = 'data-batch-export-state'
export const BATCH_STAGE_ERROR_ATTR = 'data-batch-export-error'

/** 离屏宿主状态：loading 取数中 / ready 已渲染（可快照）/ error 取数失败 */
export type BatchStageState = 'loading' | 'ready' | 'error'

/** 离屏容器固定宽度（内层 `max-w-[1200px]` 居中，与报告详情页宽度口径一致） */
export const BATCH_STAGE_WIDTH = 1440

/** 报告详情根容器（离屏宿主内与详情页同 class，供单份快照选择器命中） */
export const REPORT_VIEW_ROOT_CLASS =
  'report-view-container min-h-0 flex-1 overflow-auto print:mx-auto print:max-w-none'

/**
 * 报告子目录名长度上限（与 `sanitizeFileName` 的 60 字符上限对齐，留出同名后缀的余量）。
 * 中文按 3 字节计，60 字符仍在 Windows 255 字节路径组件上限内。
 */
export const MAX_BATCH_DIR_NAME_LENGTH = 60

/** 一份报告在批量 zip 中的片段（全部来自单份快照管线） */
export interface BatchHtmlEntry {
  /** zip 内的子目录名（已去重） */
  dir: string
  /** 报告名（index.html 清单展示） */
  reportName: string
  /** report.html 文本 */
  html: string
  /** css/report.css 文本 */
  css: string
}

/**
 * 同一批内的子目录去重：重名追加全角 `（2）`、`（3）`……（不覆盖已有目录）。
 * `used` 会被写入本次分配的名字，调用方在整批内复用一个 Set。
 */
export function uniqueReportDirName(name: string, used: Set<string>): string {
  const base = sanitizeFileName(name)
  if (!used.has(base)) {
    used.add(base)
    return base
  }
  let index = 2
  while (true) {
    const suffix = `（${index}）`
    const candidate = `${base.slice(0, MAX_BATCH_DIR_NAME_LENGTH - suffix.length)}${suffix}`
    if (!used.has(candidate)) {
      used.add(candidate)
      return candidate
    }
    index += 1
  }
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/** zip 根目录清单页：报告名 + 相对链接（file:// 可直接点进各份） */
export function buildBatchIndexHtml(entries: BatchHtmlEntry[], exportedAt: Date): string {
  const exportedLabel = exportedAt.toLocaleString('zh-CN')
  const items = entries
    .map(
      (entry) =>
        `<li><a href="${escapeHtml(entry.dir)}/${BATCH_REPORT_FILE}">${escapeHtml(
          entry.reportName
        )}</a></li>`
    )
    .join('\n      ')
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>报告批量导出</title>
<style>
  body { margin: 0; padding: 40px 24px; font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; color: #111827; background: #ffffff; }
  main { max-width: 720px; margin: 0 auto; }
  h1 { font-size: 20px; margin: 0 0 8px; }
  p { color: #6b7280; font-size: 13px; margin: 0 0 20px; }
  ul { padding-left: 20px; }
  li { margin-bottom: 8px; font-size: 14px; }
  a { color: #2563eb; text-decoration: none; }
  a:hover { text-decoration: underline; }
</style>
</head>
<body>
  <main>
    <h1>报告批量导出</h1>
    <p>共 ${entries.length} 份 · 导出时间：${escapeHtml(exportedLabel)}</p>
    <ul>
      ${items}
    </ul>
  </main>
</body>
</html>`
}

/** 批量导出文件名：`报告批量导出-<YYYYMMDD-HHmmss>.zip` */
export function batchExportFileName(now: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  const stamp =
    `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}` +
    `-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
  return `报告批量导出-${stamp}.zip`
}

/** 组装批量 zip：每份一个子目录（report.html + css/report.css）+ 根目录 index.html */
export async function buildBatchReportZip(
  entries: BatchHtmlEntry[],
  options: { batchName?: string; exportedAt?: Date } = {}
): Promise<{ blob: Blob; fileName: string }> {
  const exportedAt = options.exportedAt ?? new Date()
  const zip = new JSZip()
  for (const entry of entries) {
    const folder = zip.folder(entry.dir)
    if (!folder) continue
    folder.file(BATCH_REPORT_FILE, entry.html)
    folder.folder(BATCH_CSS_DIR)?.file(BATCH_CSS_FILE, entry.css)
  }
  zip.file(BATCH_INDEX_FILE, buildBatchIndexHtml(entries, exportedAt))
  const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE' })
  const fileName = options.batchName
    ? `${sanitizeFileName(options.batchName)}.zip`
    : batchExportFileName(exportedAt)
  return { blob, fileName }
}
