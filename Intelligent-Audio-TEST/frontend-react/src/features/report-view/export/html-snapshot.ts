/**
 * 报告详情 HTML 快照导出（INT-2418，对齐 V9.7.10 `ReportView.vue:319-772` 口径）。
 *
 * 页面所见 = 克隆当前已渲染的报告 DOM，而不是让后端按数据重画一份简化 HTML：
 * - 克隆前展开全部折叠分区、把具体用例全量灌进 DOM（由调用方置导出态完成）；
 * - 克隆时清掉右导航 / 操作组 / 弹层 / 抽屉 / Toast，剪掉全部操作按钮（保留分区折叠触发器
 *   与用例「展开详情」按钮，改由导出内交互脚本接管；表头资源名 / 分组名这类「文字即内容」
 *   的按钮解包为文本）；
 * - canvas（VChart）在克隆前 `toDataURL` 换成内联 `<img>`，SVG 原样内联；
 * - `document.styleSheets` 可读规则全量取出，字体等 `url()` 资源按同源抓取后 base64 内嵌，
 *   保证 `file://` 双击打开时零外链请求；
 * - 产物 `<报告名>.zip`：`report.html`（外链 css/report.css + 内联脚本）+ `css/report.css`。
 *
 * 主题：固定浅色（与 `report-print.css` 的 print 口径一致）。调用方负责在采集前把页面切到浅色，
 * 本模块只保证产物文档不带 `dark` 类，并读取当时 `:root` 的计算值兜底自定义主题变量。
 */
import JSZip from 'jszip'

import { readingNavLabel } from '../report-nav-sections'

/** 导出内用例分页条数（对齐 V9.7.10 `exportPageSize = 10`） */
export const HTML_EXPORT_CASE_PAGE_SIZE = 10

/** 等待导出态数据就绪的默认上限（全量用例 + 图表重绘） */
export const HTML_EXPORT_READY_TIMEOUT_MS = 20_000

/** 等待 VChart canvas 绘制完成的默认上限（超时按现状克隆） */
export const HTML_EXPORT_CHART_READY_TIMEOUT_MS = 4_000

export interface HtmlExportOptions {
  /** 报告名（zip 文件名；非法字符剔除，空则 report） */
  fileName?: string
  /** 导出内用例分页条数，默认 10 */
  pageSize?: number
  /** 等待就绪超时（毫秒） */
  timeoutMs?: number
}

export interface HtmlExportArtifact {
  blob: Blob
  fileName: string
  /** 导出内用例卡片数（= 接口 total） */
  caseCount: number
  /** 生成的 report.html 文本（供测试/探针断言） */
  html: string
}

/**
 * 单份快照的产物片段（未打包）。
 * 批量导出（INT-2419）复用这一步：每份报告走同一套清理 / 内联 / 图表静态化，
 * 只是把片段放进批量 zip 的子目录，而不是各自的单份 zip。
 */
export interface HtmlSnapshotParts {
  /** report.html 文本 */
  html: string
  /** css/report.css 文本 */
  css: string
  /** 导出内用例卡片数（= 接口 total） */
  caseCount: number
}

/** 导出态就绪标记（SpecificCaseComparison 在导出态写入；含用例总数） */
export const EXPORT_READY_ATTR = 'data-export-cases-ready'

/**
 * 导出内筛选面板根标记（INT-2434 二轮）：面板由 `ExportCaseFilterPanel` 在导出态渲染，
 * 里面的原生 `input / select / button` 是产物内交互控件（克隆时整块保留，脚本接管）。
 */
export const EXPORT_FILTER_PANEL_ATTR = 'data-export-filter-panel'

/** 用例卡筛选事实（产物内脚本按这些属性做纯 DOM 过滤 / 排序） */
export const EXPORT_CASE_DATA_ATTRS = {
  category: 'data-export-case-category',
  description: 'data-export-case-desc',
  tags: 'data-export-case-tags',
  metrics: 'data-export-case-metrics',
  metricValues: 'data-export-case-metric-values',
} as const

/** 克隆时需要整块删除的节点（操作区 / 浮层 / 弹窗 / 导航） */
const REMOVE_SELECTORS = [
  'aside',
  '.print\\:hidden',
  '[data-export-hide]',
  '[data-export-cases-ready]',
  '[role="dialog"]',
  '[role="alertdialog"]',
  '[role="menu"]',
  '[data-sonner-toaster]',
  '[data-slot="popover-content"]',
  '[data-slot="popover-positioner"]',
  '[data-slot="select-content"]',
  '[data-slot="select-positioner"]',
  '[data-slot="dropdown-menu-content"]',
  '[data-slot="menu-popup"]',
  '[data-slot="menu-positioner"]',
  '[data-slot="tooltip-content"]',
  '[data-slot="tooltip-popup"]',
  '[data-slot="dialog-backdrop"]',
  '[data-slot="dialog-content"]',
  '[data-slot="dialog-portal"]',
  '[data-slot="sheet-content"]',
  '[data-slot="drawer-content"]',
  'script',
  'noscript',
]

/**
 * 克隆后仍保留的按钮：分区折叠触发器 + 用例「展开详情」+ 导出内 Tab + 用例分组头
 * （导出脚本接管其交互）。
 * Tab 一律由组件在导出态打 `data-export-tab` 白名单标记（INT-2434：不再按 role/aria-label 兜规则——
 * 旧规则把轮次 / 维度 / 目标三类 Tab 一网打尽，产物里 tablist 只剩空壳）；
 * 分组头同理打 `data-export-group-toggle`（INT-2434 三轮：原来组头是死文字，第一组以外打不开）。
 */
const KEEP_BUTTON_SELECTOR =
  '[data-slot="collapsible-trigger"], button[aria-label="展开详情"], button[aria-label="收起详情"], [data-export-tab], [data-export-group-toggle]'

/**
 * 文本型按钮：按钮本身是操作入口，但文字是页面内容（表头资源名 / 分组名 / 维度卡片标题）。
 * 删除按钮前把文字留在原位，否则导出后列头与标题整块丢失（INT-2418 P2-1）。
 */
const KEEP_TEXT_BUTTON_SELECTOR = '[data-export-keep-text]'

/** 报告详情根容器选择器（与 report-print.css / 报告的壳一致） */
export const REPORT_VIEW_ROOT_SELECTOR = '.report-view-container'

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** 文件名最大字符数（中文按 3 字节计，80 字符仍在 Windows 255 字节组件上限内） */
const MAX_FILE_NAME_LENGTH = 60

/** 尽力剔除 Windows/Unix 非法文件名字符，并截断超长报告名 */
export function sanitizeFileName(name: string | undefined): string {
  const cleaned = (name ?? '')
    .replace(/[\\/:*?"<>|]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  if (!cleaned) return 'report'
  // 真实库存在 80+ 字中文报告名（含日期路径）；截断避免超过 Windows 255 字节组件上限
  return cleaned.length > MAX_FILE_NAME_LENGTH
    ? cleaned.slice(0, MAX_FILE_NAME_LENGTH).trim()
    : cleaned
}

/**
 * 等待导出态数据就绪：调用方置导出态后，具体用例分区会写入 `data-export-cases-ready`
 * （pending="false" 表示全量用例已渲染）。超时不抛错——导出仍继续，避免卡死。
 */
export async function waitForReportExportReady(
  root: HTMLElement,
  timeoutMs = HTML_EXPORT_READY_TIMEOUT_MS
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs
  // 至少让出一帧，等 React 把导出态渲染完
  await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
  while (Date.now() < deadline) {
    const marker = root.querySelector<HTMLElement>(`[${EXPORT_READY_ATTR}]`)
    if (marker && marker.getAttribute(EXPORT_READY_ATTR) === 'true') return true
    await sleep(100)
  }
  return false
}

/** 已绘制 canvas 的 PNG data URL 至少应有这么大（空白画布只有几百字节） */
const MIN_PAINTED_CANVAS_DATA_URL_LENGTH = 2000

/**
 * 等页面上的 canvas（VChart）绘制完成再采位图：导出态会让折叠的维度卡片展开、
 * 图表视图切换后 VChart 异步挂载，过早 `toDataURL` 会得到空白图（INT-2418 P3-2）。
 * 超时不抛错，按现状继续克隆。
 */
export async function waitForChartsPainted(
  root: HTMLElement,
  timeoutMs = HTML_EXPORT_CHART_READY_TIMEOUT_MS
): Promise<void> {
  // 至少让出两帧，等 React/VChart 完成挂载
  await new Promise<void>((resolve) =>
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
  )
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const canvases = Array.from(root.querySelectorAll<HTMLCanvasElement>('canvas'))
    if (canvases.length === 0) return
    const allPainted = canvases.every((canvas) => {
      if (!canvas.width || !canvas.height) return false
      try {
        return canvas.toDataURL('image/png').length > MIN_PAINTED_CANVAS_DATA_URL_LENGTH
      } catch {
        return false
      }
    })
    if (allPainted) return
    await sleep(120)
  }
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = String(reader.result ?? '')
      resolve(result.slice(result.indexOf(',') + 1))
    }
    reader.onerror = () => reject(reader.error ?? new Error('读取资源失败'))
    reader.readAsDataURL(blob)
  })
}

/**
 * 收集文档全部可读 CSS 规则（`document.styleSheets`；15173 同源可读）。
 * 跨域 / CSP 读不到 `cssRules` 的样式表，回退抓取其 `href` 文本。
 */
export async function collectDocumentCss(): Promise<string> {
  const chunks: string[] = []
  const fallbackHrefs: string[] = []
  for (const sheet of Array.from(document.styleSheets)) {
    try {
      const rules = sheet.cssRules
      if (!rules) {
        if (sheet.href) fallbackHrefs.push(sheet.href)
        continue
      }
      for (const rule of Array.from(rules)) chunks.push(rule.cssText)
    } catch {
      if (sheet.href) fallbackHrefs.push(sheet.href)
    }
  }
  for (const href of fallbackHrefs) {
    try {
      const res = await fetch(href)
      if (res.ok) chunks.push(await res.text())
    } catch {
      // 取不到就跳过：产品不因样式抓取失败而中断
    }
  }
  return chunks.join('\n')
}

/** 把 `:root` 上的自定义属性（主题 token / 用户自定义主题的 inline 变量）固化成文本 */
export function collectRootCssVariables(): string {
  const styles = window.getComputedStyle(document.documentElement)
  const vars: string[] = []
  for (let i = 0; i < styles.length; i += 1) {
    const name = styles.item(i)
    if (!name || !name.startsWith('--')) continue
    const value = styles.getPropertyValue(name).trim()
    if (value) vars.push(`${name}: ${value};`)
  }
  return vars.length > 0 ? `:root {\n  ${vars.join('\n  ')}\n}` : ''
}

/**
 * 同源 `url()` 资源内嵌：字体 / 背景图抓取后转 base64（`file://` 打开时不再发请求）。
 * 抓不到的同源相对路径改成空 `url()`（该声明被浏览器丢弃，避免离线打开时出现断链请求）。
 */
export async function inlineCssAssets(css: string): Promise<string> {
  const urls = new Set<string>()
  const pattern = /url\(\s*(['"]?)([^'")]+)\1\s*\)/g
  let match: RegExpExecArray | null
  while ((match = pattern.exec(css)) !== null) urls.add(match[2])

  const inlined = new Map<string, string>()
  for (const rawUrl of urls) {
    if (!rawUrl || rawUrl.startsWith('data:') || rawUrl.startsWith('#')) continue
    let absolute: URL
    try {
      absolute = new URL(rawUrl, window.location.href)
    } catch {
      continue
    }
    // 外链字体（CDN）不内嵌，交给离线时的字体回退
    if (absolute.origin !== window.location.origin) continue
    try {
      const res = await fetch(absolute.href)
      if (!res.ok) continue
      const blob = await res.blob()
      // 超过 3MB 的资源不内嵌，控制 zip 体积
      if (blob.size > 3 * 1024 * 1024) continue
      const mime = blob.type || guessMimeByUrl(rawUrl)
      inlined.set(rawUrl, `data:${mime};base64,${await blobToBase64(blob)}`)
    } catch {
      // ignore
    }
  }

  return css.replace(pattern, (full, _quote: string, url: string) => {
    const data = inlined.get(url)
    if (data) return `url("${data}")`
    if (url.startsWith('data:') || url.startsWith('#') || /^(https?:)?\/\//.test(url)) return full
    // 同源相对路径且抓取失败：置空（离线打开不报 404）
    return 'url()'
  })
}

function guessMimeByUrl(url: string): string {
  const lower = url.split('?')[0].toLowerCase()
  if (lower.endsWith('.woff2')) return 'font/woff2'
  if (lower.endsWith('.woff')) return 'font/woff'
  if (lower.endsWith('.ttf')) return 'font/ttf'
  if (lower.endsWith('.png')) return 'image/png'
  if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return 'image/jpeg'
  if (lower.endsWith('.svg')) return 'image/svg+xml'
  return 'application/octet-stream'
}

/** 导出产物专用 reset（白底、取消容器滚动/max-width、分节不断页、折叠面板默认展开） */
const EXPORT_RESET_CSS = `/* ---- 报告 HTML 快照导出 reset（INT-2418） ---- */
*, *::before, *::after { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: #ffffff; color: #111827; }
body { font-size: 14px; line-height: 1.6; -webkit-font-smoothing: antialiased; }
#report-export-root { width: 100%; max-width: 1200px; margin: 0 auto; padding: 24px; }
.report-view-container {
  max-width: none !important;
  width: 100% !important;
  overflow: visible !important;
  height: auto !important;
  min-height: 0 !important;
}
/* 折叠面板默认展开由克隆阶段移除 hidden 保证；这里不能再写 display:block!important，
   否则导出内的「折叠」点击会被 !important 覆盖掉。 */
[data-export-case-detail][hidden] { display: none !important; }
canvas, svg { max-width: 100% !important; }
img { max-width: 100%; height: auto; }
[data-export-section-header], [data-slot="collapsible-trigger"] { cursor: pointer; }
[data-export-section-caret] { margin-inline-start: 6px; color: #6b7280; font-size: 12px; }
[data-export-case-toolbar] {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
  padding: 10px 12px; margin-bottom: 12px;
  border: 1px solid #e5e7eb; border-radius: 12px; background: #f8fafc;
}
[data-export-case-toolbar] input, [data-export-case-toolbar] select {
  height: 30px; padding: 0 8px; font-size: 12px;
  border: 1px solid #d1d5db; border-radius: 6px; background: #ffffff;
}
[data-export-case-toolbar] input { width: 240px; }
[data-export-case-toolbar] button {
  height: 30px; padding: 0 10px; font-size: 12px;
  border: 1px solid #d1d5db; border-radius: 6px; background: #ffffff; cursor: pointer;
}
[data-export-case-toolbar] button:disabled { opacity: 0.45; cursor: not-allowed; }
/* 导出内筛选面板（INT-2434 二轮）：原生控件 + details 折叠，样式与页面筛选卡同色系 */
[data-export-filter-panel] { font-size: 12px; }
[data-export-filter-panel] input[type="search"],
[data-export-filter-panel] select {
  height: 28px; padding: 0 8px; font-size: 12px; color: #111827;
  border: 1px solid #d1d5db; border-radius: 6px; background: #ffffff;
}
[data-export-filter-panel] input[type="checkbox"] {
  width: 13px; height: 13px; margin: 0; accent-color: #2563eb;
}
[data-export-filter-panel] button {
  height: 28px; padding: 0 10px; font-size: 12px; color: #374151;
  border: 1px solid #d1d5db; border-radius: 6px; background: #ffffff; cursor: pointer;
}
[data-export-filter-panel] button:hover { background: #f1f5f9; }
[data-export-filter-panel] details { margin-top: 8px; }
[data-export-filter-panel] summary { cursor: pointer; list-style: none; }
[data-export-filter-panel] summary::-webkit-details-marker { display: none; }
[data-export-filter-panel] summary::before { content: '▸ '; color: #9ca3af; }
[data-export-filter-panel] details[open] > summary::before { content: '▾ '; }
/* 用例详情里的长字段：页面上 >200 字折叠成两行 +「展开」按钮（按钮会被剪），
   产物里取消截断，保证 JSON / 长文本能读全文 */
[data-export-case-detail] .line-clamp-2 {
  display: block !important;
  overflow: visible !important;
  -webkit-line-clamp: unset !important;
  -webkit-box-orient: unset !important;
}
/* 用例 ID 点击复制后的轻反馈 */
[data-export-copied="true"] { outline: 1px solid #16a34a; color: #16a34a !important; }
[data-export-case-pageinfo] { font-size: 12px; color: #6b7280; margin-inline-start: auto; }
/* 本页目录（INT-2434）：与报告页右导航 ReportReadingNav 同构的视口固定阅读栏
   —— 正文右栏 + sticky，滚动时目录不离开视口；阅读进度条 + 当前分节高亮。 */
#report-export-root [data-export-layout] {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 220px;
  gap: 24px;
  align-items: stretch;
}
#report-export-root [data-export-layout] > main { min-width: 0; }
#report-export-root [data-export-toc-aside] { min-width: 0; }
#report-export-root [data-export-toc] { position: sticky; top: 16px; }
#report-export-root section[id] { scroll-margin-top: 16px; }
[data-export-toc-track] {
  height: 1px; overflow: hidden; border-radius: 9999px;
  background: color-mix(in srgb, var(--muted, #e5e7eb) 20%, transparent);
}
[data-export-toc-progress] {
  height: 100%; width: 0;
  background: color-mix(in srgb, var(--primary, #2563eb) 40%, transparent);
  transition: width 150ms ease;
}
[data-export-toc-title] {
  margin: 12px 0 8px; font-size: 12px; font-weight: 500;
  color: var(--muted-foreground, #6b7280);
}
[data-export-toc-list] { margin: 0; padding: 0; list-style: none; }
[data-export-toc-list] > li + li { margin-top: 4px; }
[data-export-toc-link] {
  display: inline-block; padding: 4px 8px; border-radius: 6px;
  font-size: 12px; line-height: 1.5;
  color: var(--muted-foreground, #6b7280);
  text-decoration: none; cursor: pointer; transition: color 150ms ease;
}
[data-export-toc-link]:hover { color: var(--foreground, #111827); }
[data-export-toc-link][aria-current="location"] {
  color: var(--primary, #2563eb); font-weight: 500;
}
/* 导出内 Tab（轮次 / 评估维度 / 设备·API，INT-2434）：选中态只由 aria-selected 决定 */
[data-export-tab] { cursor: pointer; }
[data-export-tab][aria-selected="true"] { background: #2563eb; color: #ffffff; }
[data-export-tab][aria-selected="false"] { background: transparent; color: #6b7280; }
/* 用例详情展开入口：图标 + 可见文字（原来只有图标，看不出可点） */
[data-export-case-toggle] { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; }
[data-export-case-toggle-label] { white-space: nowrap; }
/* 用例分组头：产物里可点展开 / 收起（INT-2434 三轮） */
[data-export-group-toggle] {
  display: block; width: 100%; text-align: start; cursor: pointer;
  background: transparent; border: 0; padding: 0; color: inherit; font: inherit;
  border-radius: 6px;
}
[data-export-group-toggle]:hover { background: color-mix(in srgb, var(--muted, #e5e7eb) 40%, transparent); }
[data-export-group-caret] { display: inline-block; min-width: 12px; }
/* 窄窗口不出右栏（与报告页 lg 断点一致），避免挤压正文 */
@media (max-width: 1023px) {
  #report-export-root [data-export-layout] { display: block; }
  #report-export-root [data-export-toc-aside] { display: none; }
}
@media print {
  [data-export-case-toolbar] { display: none !important; }
  #report-export-root [data-export-toc-aside] { display: none !important; }
  #report-export-root [data-export-layout] { display: block !important; }
  section { break-inside: avoid; }
}
`

/**
 * 用子节点替换元素本身（保留其文字/子结构，去掉交互外壳）。无父节点时按删除处理。
 */
function unwrapElement(el: Element): void {
  const parent = el.parentNode
  if (!parent) {
    el.remove()
    return
  }
  while (el.firstChild) parent.insertBefore(el.firstChild, el)
  parent.removeChild(el)
}

/**
 * 克隆报告 DOM 并做静态化处理。`originalRoot` 用于 canvas 位图采集。
 */
export function buildStaticClone(
  originalRoot: HTMLElement,
  pageSize = HTML_EXPORT_CASE_PAGE_SIZE
): { clone: HTMLElement; caseCount: number } {
  const clone = originalRoot.cloneNode(true) as HTMLElement

  // 1) canvas → 内联 PNG（cloneNode 不带位图；按文档顺序一一对应替换）
  replaceCanvases(originalRoot, clone)

  // 2) 移除操作区 / 浮层 / 导航
  for (const selector of REMOVE_SELECTORS) {
    clone.querySelectorAll(selector).forEach((el) => el.remove())
  }

  // 3) 剪掉操作按钮（保留分区折叠触发器与用例展开按钮，改由导出脚本接管；
  //    表头资源名 / 分组名 / 维度卡片标题这类「文字即内容」的按钮解包为文本）
  clone.querySelectorAll('button').forEach((btn) => {
    // 导出态筛选面板（INT-2434 二轮）：面板里的按钮是产物内交互控件，整块保留
    if (btn.closest(`[${EXPORT_FILTER_PANEL_ATTR}]`)) return
    if (btn.matches(KEEP_BUTTON_SELECTOR)) return
    if (btn.matches(KEEP_TEXT_BUTTON_SELECTOR)) {
      unwrapElement(btn)
      return
    }
    btn.remove()
  })
  clone.querySelectorAll('input, select, textarea').forEach((el) => {
    // 筛选面板里的原生控件由产物内脚本接管，不再当页面操作控件删除
    if (el.closest(`[${EXPORT_FILTER_PANEL_ATTR}]`)) return
    el.remove()
  })

  // 4) 折叠面板统一展开（导出内由脚本控制显示）
  clone
    .querySelectorAll('[data-slot="collapsible-content"], [data-slot="collapsible-panel"]')
    .forEach((panel) => {
      panel.removeAttribute('hidden')
      ;(panel as HTMLElement).style.display = ''
    })

  // 5) 纯标题分区（总览 / 对比表格）包一层可折叠面板
  prepareHeadingSections(clone)

  // 5.5) 本页目录（INT-2434）：页面上「本页目录」是 React 状态驱动的右导航 <aside>，
  //      克隆时整块删除，产物里没有目录；这里按产物内分区重生成锚点导航，
  //      单份与批量（离屏宿主不渲染右导航）走同一条管线自动一致。
  buildExportToc(clone)

  // 6) 用例分页 / 搜索 / 详情折叠
  const caseCount = prepareCases(clone, pageSize)

  clone.setAttribute('data-export-root', '')
  clone.setAttribute('data-export-case-total', String(caseCount))
  return { clone, caseCount }
}

function replaceCanvases(originalRoot: HTMLElement, clone: HTMLElement): void {
  const originals = Array.from(originalRoot.querySelectorAll('canvas'))
  const targets = Array.from(clone.querySelectorAll('canvas'))
  originals.forEach((source, index) => {
    const target = targets[index]
    if (!target) return
    let dataUrl = ''
    try {
      dataUrl = source.toDataURL('image/png')
    } catch {
      dataUrl = ''
    }
    // 空白 canvas（0×0）也允许导出为图片，但没有任何绘制内容的就不替换
    if (!dataUrl || dataUrl === 'data:,') return
    const img = document.createElement('img')
    img.src = dataUrl
    img.alt = '图表'
    const width = target.getAttribute('width') || String(source.clientWidth || 640)
    const height = target.getAttribute('height') || String(source.clientHeight || 320)
    img.setAttribute('width', width)
    img.setAttribute('height', height)
    img.style.maxWidth = '100%'
    img.style.height = 'auto'
    target.replaceWith(img)
  })
}

function prepareHeadingSections(clone: HTMLElement): void {
  clone.querySelectorAll<HTMLElement>('section[id^="report-"]').forEach((section) => {
    section.setAttribute('data-export-section', '')
    // 有 Collapsible 的分区：触发器已保留，分区整体无需再包一层
    if (section.querySelector('[data-slot="collapsible"]')) return
    const heading = section.querySelector('h3')
    if (!heading) return
    const panel = document.createElement('div')
    panel.setAttribute('data-export-section-panel', '')
    const movable = Array.from(section.childNodes).filter((node) => node !== heading)
    for (const node of movable) panel.appendChild(node)
    section.appendChild(panel)
    heading.setAttribute('data-export-section-header', '')
    const caret = document.createElement('span')
    caret.setAttribute('data-export-section-caret', '')
    caret.textContent = '▾'
    heading.appendChild(caret)
  })
}

/** 分区标题里由脚本加的折叠箭头（不得进目录文案） */
const SECTION_CARET_PATTERN = /[▾▸]/g

/** 取分区标题文案：页面同一份目录定义 → h1~h4 → Collapsible 触发器 → aria-label → id 兜底 */
function sectionLabel(section: HTMLElement): string {
  // 与报告页右导航同一份 id → 文案映射：分区标题里带统计（「设备 2 · API 0」「共 793 条结果」），
  // 直接取标题会把统计塞进目录（INT-2434 负责人反馈「目录不对」）。
  const mapped = readingNavLabel(section.id)
  if (mapped) return mapped
  const heading = section.querySelector('h1, h2, h3, h4')
  const trigger = section.querySelector('[data-slot="collapsible-trigger"]')
  const raw =
    (heading?.textContent ?? '') ||
    (trigger?.textContent ?? '') ||
    section.getAttribute('aria-label') ||
    section.id
  return raw.replace(SECTION_CARET_PATTERN, '').replace(/\s+/g, ' ').trim() || section.id
}

/**
 * 产物「本页目录」：与报告页右导航（`ReportReadingNav`，`sticky` 视口固定）同构（INT-2434）。
 *
 * 页面上的右导航是 `<aside class="print:hidden">`，克隆清理规则会整块删掉，批量离屏宿主
 * 也不渲染它 —— 所以这里按产物内 `section[id]` 重建：**正文右栏 + sticky**，带阅读进度条
 * 与当前分节高亮（滚动由导出脚本接管，纯 DOM，不依赖 React 状态）。
 * 锚点与分区 id 一一对应（同一次克隆里收集 → 不会出现死锚点），`file://` 下点击即跳转。
 */
export function buildExportToc(clone: HTMLElement): HTMLElement | null {
  const existing = clone.querySelector('nav[aria-label="本页目录"]') as HTMLElement | null
  if (existing) return existing
  const sections = Array.from(clone.querySelectorAll<HTMLElement>('section[id]')).filter(
    (section) => Boolean(section.id)
  )
  if (sections.length === 0) return null

  const nav = document.createElement('nav')
  nav.setAttribute('aria-label', '本页目录')
  nav.setAttribute('data-export-toc', '')

  const inner = document.createElement('div')
  const track = document.createElement('div')
  track.setAttribute('data-export-toc-track', '')
  const progress = document.createElement('div')
  progress.setAttribute('data-export-toc-progress', '')
  track.appendChild(progress)
  const title = document.createElement('p')
  title.setAttribute('data-export-toc-title', '')
  title.textContent = '本页目录'
  const list = document.createElement('ul')
  list.setAttribute('data-export-toc-list', '')
  for (const section of sections) {
    const item = document.createElement('li')
    const link = document.createElement('a')
    link.setAttribute('href', `#${section.id}`)
    link.setAttribute('data-export-toc-link', section.id)
    link.textContent = sectionLabel(section)
    item.appendChild(link)
    list.appendChild(item)
  }
  inner.append(track, title, list)
  nav.appendChild(inner)

  const aside = document.createElement('aside')
  aside.setAttribute('data-export-toc-aside', '')
  aside.appendChild(nav)

  // 放进正文两栏布局的右栏（页面里 `<main>` + `<aside>` 的位置），sticky 才有参照；
  // 简化 DOM（单测直接喂 section、没有 main）时退回文档顶部，目录仍可用。
  const main = clone.querySelector('main')
  const host = main && main.parentElement && main.parentElement !== clone ? main.parentElement : null
  if (host) {
    host.setAttribute('data-export-layout', '')
    host.appendChild(aside)
  } else {
    clone.insertBefore(aside, clone.firstChild)
  }
  return nav
}

function prepareCases(clone: HTMLElement, pageSize: number): number {
  const cards = Array.from(clone.querySelectorAll<HTMLElement>('[data-export-case]'))
  cards.forEach((card, index) => {
    card.setAttribute('data-case-index', String(index))
    if (index >= pageSize) card.style.display = 'none'
    const detail = card.querySelector<HTMLElement>('[data-export-case-detail]')
    if (detail) detail.setAttribute('hidden', '')
    const toggle = card.querySelector<HTMLElement>(
      'button[aria-label="展开详情"], button[aria-label="收起详情"]'
    )
    if (toggle) {
      toggle.setAttribute('data-export-case-toggle', '')
      toggle.setAttribute('aria-expanded', 'false')
      // INT-2434：导出里的展开入口原来只有图标，看不出可点 → 补可见文字；
      // 文案由导出脚本随展开状态切换。
      if (!toggle.querySelector('[data-export-case-toggle-label]')) {
        const label = document.createElement('span')
        label.setAttribute('data-export-case-toggle-label', '')
        label.textContent = '展开详情'
        toggle.appendChild(label)
      }
    }
  })
  if (cards.length === 0) return 0
  insertCaseToolbar(clone, pageSize)
  return cards.length
}

function insertCaseToolbar(clone: HTMLElement, pageSize: number): void {
  if (clone.querySelector('[data-export-case-toolbar]')) return
  const list = clone.querySelector<HTMLElement>('[data-export-case-list]')
  const toolbar = document.createElement('div')
  toolbar.setAttribute('data-export-case-toolbar', '')

  const sizeLabel = document.createElement('label')
  sizeLabel.style.fontSize = '12px'
  sizeLabel.style.color = '#6b7280'
  sizeLabel.textContent = '每页'
  const sizeSelect = document.createElement('select')
  sizeSelect.id = 'export-case-page-size'
  sizeSelect.setAttribute('aria-label', '每页条数')
  for (const size of [10, 20, 50, 100]) {
    const option = document.createElement('option')
    option.value = String(size)
    option.textContent = String(size)
    if (size === pageSize) option.selected = true
    sizeSelect.appendChild(option)
  }
  sizeLabel.appendChild(sizeSelect)

  // 卡片操作（INT-2434 二轮）：全部展开 / 收起详情
  const expandAll = document.createElement('button')
  expandAll.type = 'button'
  expandAll.id = 'export-case-expand-all'
  expandAll.setAttribute('data-export-case-expand-all', '')
  expandAll.textContent = '展开全部详情'
  const collapseAll = document.createElement('button')
  collapseAll.type = 'button'
  collapseAll.id = 'export-case-collapse-all'
  collapseAll.setAttribute('data-export-case-collapse-all', '')
  collapseAll.textContent = '收起全部详情'

  const prev = document.createElement('button')
  prev.type = 'button'
  prev.id = 'export-case-prev'
  prev.textContent = '上一页'
  const next = document.createElement('button')
  next.type = 'button'
  next.id = 'export-case-next'
  next.textContent = '下一页'
  const jump = document.createElement('input')
  jump.type = 'number'
  jump.id = 'export-case-jump'
  jump.min = '1'
  jump.value = '1'
  jump.style.width = '64px'
  jump.setAttribute('aria-label', '跳转页码')
  const jumpBtn = document.createElement('button')
  jumpBtn.type = 'button'
  jumpBtn.id = 'export-case-jump-btn'
  jumpBtn.textContent = '跳转'
  const info = document.createElement('span')
  info.id = 'export-case-pageinfo'
  info.setAttribute('data-export-case-pageinfo', '')

  toolbar.append(sizeLabel, expandAll, collapseAll, prev, next, jump, jumpBtn, info)
  if (list && list.parentElement) {
    list.parentElement.insertBefore(toolbar, list)
  } else {
    const section = clone.querySelector('#report-specific-cases')
    if (section) section.insertBefore(toolbar, section.firstChild)
    else return
  }
}

/** 导出内交互脚本（内联到 report.html：file:// 下不允许外部脚本） */
export const REPORT_EXPORT_SCRIPT = `(function () {
  'use strict';
  function $all(selector, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(selector));
  }

  // ---------- 1. 分区折叠 / 展开 ----------
  $all('[data-slot="collapsible-trigger"]').forEach(function (btn) {
    btn.addEventListener('click', function (event) {
      event.preventDefault();
      var holder = btn.closest('[data-slot="collapsible"]');
      var panel = holder ? holder.querySelector('[data-slot="collapsible-content"], [data-slot="collapsible-panel"]') : null;
      if (!panel) return;
      var collapsed = panel.getAttribute('data-export-collapsed') === 'true';
      panel.setAttribute('data-export-collapsed', collapsed ? 'false' : 'true');
      panel.style.display = collapsed ? '' : 'none';
      btn.setAttribute('aria-expanded', collapsed ? 'true' : 'false');
      var icon = btn.querySelector('svg');
      if (icon) icon.style.transform = collapsed ? '' : 'rotate(180deg)';
    });
  });

  // 纯标题分区（总览 / 对比表格）
  $all('[data-export-section-header]').forEach(function (heading) {
    heading.addEventListener('click', function () {
      var section = heading.closest('[data-export-section]');
      var panel = section ? section.querySelector('[data-export-section-panel]') : null;
      if (!panel) return;
      var hidden = panel.style.display === 'none';
      panel.style.display = hidden ? '' : 'none';
      var caret = heading.querySelector('[data-export-section-caret]');
      if (caret) caret.textContent = hidden ? '▾' : '▸';
    });
  });

  // ---------- 2. 用例卡片展开 / 收起 ----------
  $all('[data-export-case-toggle]').forEach(function (btn) {
    btn.addEventListener('click', function (event) {
      event.preventDefault();
      var card = btn.closest('[data-export-case]');
      var detail = card ? card.querySelector('[data-export-case-detail]') : null;
      if (!detail) return;
      var hidden = detail.hasAttribute('hidden');
      if (hidden) detail.removeAttribute('hidden');
      else detail.setAttribute('hidden', '');
      btn.setAttribute('aria-expanded', hidden ? 'true' : 'false');
      var textLabel = btn.querySelector('[data-export-case-toggle-label]');
      if (textLabel) textLabel.textContent = hidden ? '收起详情' : '展开详情';
      var icon = btn.querySelector('svg');
      if (icon) icon.style.transform = hidden ? 'rotate(180deg)' : '';
    });
  });

  // ---------- 3. 用例筛选（关键词 / 分组 / 标签 / 维度）+ 排序 + 分页（INT-2434 二轮） ----------
  // 页面筛选走服务端（POST /reports/{id}/cases/search），产物没有后端：每张卡自带
  // data-export-case-* 筛选事实，这里按后端同口径做纯 DOM 过滤 ——
  //   关键词 = 名称 / 用例 ID / 描述；分组 = 分类（多选取并集）；
  //   标签、评估维度 = 任一命中（与后端 _match_tags / _match_metrics 一致）。
  var filterPanel = document.querySelector('[data-export-filter-panel]');
  var caseCards = $all('[data-export-case]');
  var groupWrappers = $all('[data-export-group]');
  var searchInput = document.getElementById('export-case-search');
  var sizeSelect = document.getElementById('export-case-page-size');
  var prevBtn = document.getElementById('export-case-prev');
  var nextBtn = document.getElementById('export-case-next');
  var jumpInput = document.getElementById('export-case-jump');
  var jumpBtn = document.getElementById('export-case-jump-btn');
  var info = document.getElementById('export-case-pageinfo');
  var pageSize = sizeSelect ? parseInt(sizeSelect.value, 10) || 10 : 10;
  var currentPage = 1;

  function parseArray(text) {
    if (!text) return [];
    try {
      var parsed = JSON.parse(text);
      return Array.isArray(parsed) ? parsed : [];
    } catch (err) {
      return [];
    }
  }
  function parseMap(text) {
    if (!text) return {};
    try {
      var parsed = JSON.parse(text);
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch (err) {
      return {};
    }
  }

  // 被手动折叠的分组容器（组头 = button[data-export-group-toggle]，卡容器 = [data-export-group-body]）
  var collapsedGroups = [];
  function groupBodyOf(wrapper) {
    var children = Array.prototype.slice.call(wrapper.children);
    for (var i = 0; i < children.length; i += 1) {
      if (children[i].getAttribute('data-export-group-body') !== null) return children[i];
    }
    return null;
  }
  function applyGroupState(wrapper) {
    var body = groupBodyOf(wrapper);
    if (!body) return;
    var collapsed = collapsedGroups.indexOf(wrapper) >= 0;
    body.style.display = collapsed ? 'none' : '';
    var btn = wrapper.querySelector('[data-export-group-toggle]');
    if (!btn) return;
    btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    var caret = btn.querySelector('[data-export-group-caret]');
    if (caret) caret.textContent = collapsed ? '▸' : '▾';
  }
  function ownerGroupOf(card) {
    return card.closest ? card.closest('[data-export-group]') : null;
  }
  /** 分组内分页后的总页数 = 各组页数的最大值（各组同步翻到同一页码） */
  function maxPageCount() {
    var owners = [];
    var counts = [];
    $all('[data-export-case]').forEach(function (card) {
      if (card.getAttribute('data-export-match') !== 'true') return;
      var owner = ownerGroupOf(card);
      var index = owners.indexOf(owner);
      if (index < 0) { owners.push(owner); counts.push(0); index = counts.length - 1; }
      counts[index] += 1;
    });
    var pages = 1;
    counts.forEach(function (n) { pages = Math.max(pages, Math.ceil(n / pageSize)); });
    return pages;
  }

  // 每张卡的筛选事实（属性读一次，后续过滤 / 排序不重复解析）
  var cardInfoList = caseCards.map(function (card) {
    return {
      el: card,
      name: String(card.getAttribute('data-export-case-name') || '').toLowerCase(),
      id: String(card.getAttribute('data-export-case-id') || '').toLowerCase(),
      desc: String(card.getAttribute('data-export-case-desc') || '').toLowerCase(),
      category: String(card.getAttribute('data-export-case-category') || ''),
      tags: parseArray(card.getAttribute('data-export-case-tags')),
      metrics: parseArray(card.getAttribute('data-export-case-metrics')),
      metricValues: parseMap(card.getAttribute('data-export-case-metric-values'))
    };
  });
  function infoOf(card) {
    for (var i = 0; i < cardInfoList.length; i += 1) {
      if (cardInfoList[i].el === card) return cardInfoList[i];
    }
    return null;
  }

  function checkedValues(attr) {
    return $all('[data-export-filter-panel] input[' + attr + ']').filter(function (input) {
      return input.checked;
    }).map(function (input) {
      return input.getAttribute(attr) || '';
    });
  }
  function controlValue(attr) {
    var el = document.querySelector('[data-export-filter-panel] [' + attr + ']');
    return el ? String(el.value || '') : '';
  }
  function hasAny(list, values) {
    for (var i = 0; i < values.length; i += 1) {
      if (list.indexOf(values[i]) >= 0) return true;
    }
    return false;
  }
  function matches(info, state) {
    if (state.keyword) {
      if (info.name.indexOf(state.keyword) < 0 && info.id.indexOf(state.keyword) < 0
        && info.desc.indexOf(state.keyword) < 0) return false;
    }
    if (state.groups.length > 0 && state.groups.indexOf(info.category) < 0) return false;
    if (state.tags.length > 0 && !hasAny(info.tags, state.tags)) return false;
    if (state.metrics.length > 0 && !hasAny(info.metrics, state.metrics)) return false;
    return true;
  }

  /**
   * 卡片排序（在各自所在分组容器内排，组结构不变）：
   * - 空 sort = 保持克隆时的页面顺序（页面已经按自己选的排序取过数）；
   * - name / testcaseid 与后端一致（testcaseid 是「按创建时间」的后端口径）；
   * - metric = 跨资源平均值，无值卡片排最后（后端 (1, 0) 口径）。
   */
  function sortCards(state) {
    if (!state.sort) return;
    if (state.sort === 'metric' && !state.sortMetric) return;
    var parents = [];
    caseCards.forEach(function (card) {
      var parent = card.parentElement;
      if (parent && parents.indexOf(parent) < 0) parents.push(parent);
    });
    parents.forEach(function (parent) {
      var own = Array.prototype.filter.call(parent.children, function (child) {
        return child.getAttribute && child.getAttribute('data-export-case') !== null;
      });
      if (own.length < 2) return;
      own.sort(function (a, b) {
        var ia = infoOf(a);
        var ib = infoOf(b);
        if (!ia || !ib) return 0;
        if (state.sort === 'metric') {
          var va = ia.metricValues[state.sortMetric];
          var vb = ib.metricValues[state.sortMetric];
          var hasA = typeof va === 'number' && isFinite(va);
          var hasB = typeof vb === 'number' && isFinite(vb);
          if (!hasA && !hasB) return 0;
          if (!hasA) return 1;
          if (!hasB) return -1;
          return state.sortOrder === 'desc' ? vb - va : va - vb;
        }
        var sa = state.sort === 'testcaseid' ? ia.id : ia.name;
        var sb = state.sort === 'testcaseid' ? ib.id : ib.name;
        var cmp = sa < sb ? -1 : sa > sb ? 1 : 0;
        return state.sortOrder === 'desc' ? -cmp : cmp;
      });
      own.forEach(function (card) { parent.appendChild(card); });
    });
  }

  function render() {
    var state = {
      keyword: searchInput ? String(searchInput.value || '').trim().toLowerCase() : '',
      groups: checkedValues('data-export-filter-group'),
      tags: checkedValues('data-export-filter-tag'),
      metrics: checkedValues('data-export-filter-metric'),
      sort: controlValue('data-export-filter-sort'),
      sortOrder: controlValue('data-export-filter-sort-order') || 'asc',
      sortMetric: controlValue('data-export-filter-sort-metric')
    };
    sortCards(state);
    // 排序会移动节点：按文档顺序重新取卡片
    caseCards = $all('[data-export-case]');
    var matched = caseCards.filter(function (card) {
      var info = infoOf(card);
      return info ? matches(info, state) : true;
    });
    var total = matched.length;
    // 分组内分页（INT-2434 三轮）：每张卡归到最近的 [data-export-group]，各组各自显示
    // 本组第 (currentPage-1)*pageSize 起的 pageSize 张。全局分页会把第一组以外的组全部藏起来
    // ——负责人 08:44「打断与恢复这个分组能打开吗」：组头和计数都在，组内卡片却全是隐藏的。
    var buckets = [];
    matched.forEach(function (card) {
      var owner = ownerGroupOf(card);
      var bucket = null;
      for (var i = 0; i < buckets.length; i += 1) {
        if (buckets[i].owner === owner) { bucket = buckets[i]; break; }
      }
      if (!bucket) { bucket = { owner: owner, cards: [] }; buckets.push(bucket); }
      bucket.cards.push(card);
    });
    var pages = 1;
    buckets.forEach(function (bucket) {
      pages = Math.max(pages, Math.max(1, Math.ceil(bucket.cards.length / pageSize)));
    });
    if (currentPage > pages) currentPage = pages;
    if (currentPage < 1) currentPage = 1;
    var start = (currentPage - 1) * pageSize;
    caseCards.forEach(function (card) {
      card.style.display = 'none';
      card.setAttribute('data-export-match', 'false');
    });
    matched.forEach(function (card) { card.setAttribute('data-export-match', 'true'); });
    buckets.forEach(function (bucket) {
      bucket.cards.slice(start, start + pageSize).forEach(function (card) {
        card.style.display = '';
      });
    });

    // 分组：命中为 0 的组整块隐藏；本页没有可见卡的组也隐藏组头（折叠中的组保留组头，方便点开）；
    // 组头计数 = 命中数（含嵌套子组，筛选后实时更新）
    groupWrappers.forEach(function (wrapper) {
      var inside = Array.prototype.slice.call(wrapper.querySelectorAll('[data-export-case]'));
      var hit = 0;
      var shown = 0;
      inside.forEach(function (card) {
        if (card.getAttribute('data-export-match') === 'true') hit += 1;
        if (card.style.display !== 'none') shown += 1;
      });
      var collapsed = collapsedGroups.indexOf(wrapper) >= 0;
      wrapper.style.display = hit > 0 && (shown > 0 || collapsed) ? '' : 'none';
      var countEl = wrapper.querySelector('[data-export-group-count]');
      if (countEl) countEl.textContent = hit + ' 个用例';
      applyGroupState(wrapper);
    });

    if (info) {
      // 工具条单位与卡片口径一致（用例卡 = 按 test_case_id 合并后的张数），避免与页面
      // 区块头的「共 N 条结果」（结果行口径）同屏两个「条结果」（INT-2418 P3-2）
      info.textContent = '显示第 ' + currentPage + ' / ' + pages + ' 页（各组同页翻动），总计 '
        + total + ' 个用例';
    }
    var filterCount = document.querySelector('[data-export-filter-count]');
    if (filterCount) {
      filterCount.textContent = (state.keyword || state.groups.length || state.tags.length
        || state.metrics.length) ? '命中 ' + total + ' 个用例' : '共 ' + total + ' 个用例';
    }
    if (prevBtn) prevBtn.disabled = currentPage <= 1;
    if (nextBtn) nextBtn.disabled = currentPage >= pages;
    if (jumpInput) jumpInput.max = String(pages);
  }

  function resetPaging() {
    currentPage = 1;
    render();
  }

  if (filterPanel) {
    if (searchInput) searchInput.addEventListener('input', resetPaging);
    $all('[data-export-filter-panel] input[type="checkbox"]').forEach(function (input) {
      input.addEventListener('change', resetPaging);
    });
    $all('[data-export-filter-panel] select').forEach(function (select) {
      select.addEventListener('change', resetPaging);
    });
    var resetBtn = document.querySelector('[data-export-filter-reset]');
    if (resetBtn) {
      resetBtn.addEventListener('click', function () {
        $all('[data-export-filter-panel] input[type="checkbox"]').forEach(function (input) {
          input.checked = false;
        });
        if (searchInput) searchInput.value = '';
        $all('[data-export-filter-panel] select').forEach(function (select) {
          select.value = select.hasAttribute('data-export-filter-sort-order') ? 'asc' : '';
        });
        resetPaging();
      });
    }
  }

  // 每页条数 / 上下页 / 跳转
  if (sizeSelect) {
    sizeSelect.addEventListener('change', function () {
      pageSize = parseInt(sizeSelect.value, 10) || 10;
      resetPaging();
    });
  }
  if (prevBtn) {
    prevBtn.addEventListener('click', function () {
      if (currentPage > 1) { currentPage -= 1; render(); }
    });
  }
  if (nextBtn) {
    nextBtn.addEventListener('click', function () {
      if (currentPage < maxPageCount()) { currentPage += 1; render(); }
    });
  }
  function jumpToPage() {
    if (!jumpInput) return;
    var pages = maxPageCount();
    var value = parseInt(jumpInput.value, 10);
    if (!isNaN(value) && value >= 1 && value <= pages) {
      currentPage = value;
      render();
    }
  }
  if (jumpBtn) jumpBtn.addEventListener('click', jumpToPage);
  if (jumpInput) {
    jumpInput.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') { event.preventDefault(); jumpToPage(); }
    });
  }

  // ---------- 3.a 分组展开 / 收起（INT-2434 三轮） ----------
  // 负责人 08:44：「打断与恢复这个分组能打开吗」。组头在产物里是 button[data-export-group-toggle]，
  // 点一下折叠本组卡片、再点展开；折叠状态记在 collapsedGroups，翻页 / 筛选后保持。
  $all('[data-export-group-toggle]').forEach(function (btn) {
    btn.addEventListener('click', function (event) {
      event.preventDefault();
      var wrapper = btn.closest('[data-export-group]');
      if (!wrapper) return;
      var index = collapsedGroups.indexOf(wrapper);
      if (index >= 0) collapsedGroups.splice(index, 1);
      else collapsedGroups.push(wrapper);
      applyGroupState(wrapper);
    });
  });

  // ---------- 3.b 卡片操作：全部展开 / 收起、点击复制用例 ID（INT-2434 二轮） ----------
  function setAllDetails(open) {
    $all('[data-export-case]').forEach(function (card) {
      var detail = card.querySelector('[data-export-case-detail]');
      var toggle = card.querySelector('[data-export-case-toggle]');
      if (detail) {
        if (open) detail.removeAttribute('hidden');
        else detail.setAttribute('hidden', '');
      }
      if (!toggle) return;
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      var label = toggle.querySelector('[data-export-case-toggle-label]');
      if (label) label.textContent = open ? '收起详情' : '展开详情';
      var icon = toggle.querySelector('svg');
      if (icon) icon.style.transform = open ? 'rotate(180deg)' : '';
    });
  }
  $all('[data-export-case-expand-all]').forEach(function (btn) {
    btn.addEventListener('click', function () { setAllDetails(true); });
  });
  $all('[data-export-case-collapse-all]').forEach(function (btn) {
    btn.addEventListener('click', function () { setAllDetails(false); });
  });

  $all('[data-export-copy-id]').forEach(function (el) {
    el.addEventListener('click', function () {
      var text = el.getAttribute('data-export-copy-id') || el.textContent || '';
      try {
        if (navigator.clipboard && window.isSecureContext) {
          navigator.clipboard.writeText(text);
        } else {
          // file:// 下没有 clipboard API：走同页 textarea 兜底（与 V9.7.10 导出脚本一致）
          var area = document.createElement('textarea');
          area.value = text;
          area.style.position = 'fixed';
          area.style.left = '-9999px';
          document.body.appendChild(area);
          area.select();
          document.execCommand('copy');
          document.body.removeChild(area);
        }
        el.setAttribute('data-export-copied', 'true');
        setTimeout(function () { el.removeAttribute('data-export-copied'); }, 1200);
      } catch (err) {
        // 复制失败不阻塞阅读
      }
    });
  });

  if (caseCards.length > 0) render();

  // ---------- 4. Tab 纯 DOM 切换（轮次 / 评估维度 / 设备·API 目标，INT-2434） ----------
  // 契约：
  //   data-export-tab="<group>:<value>"       Tab 按钮（导出态由组件打标记，克隆时保留）
  //   data-export-show="<group>:<value>"      精确匹配面板（多组用空格分隔，组内全部值 = __all__）
  //   data-export-round="<group>|<tag>|<mode>" 轮次行 / 行组（tag 为空 = 全轮次恒显示；
  //                                            mode f = 字段（整体 Tab 全显），m/d = 指标与维度（整体只显空标记 + overall））
  var tabState = {};

  function groupOf(spec) {
    var i = spec.indexOf(':');
    return i < 0 ? spec : spec.slice(0, i);
  }
  function valueOf(spec) {
    var i = spec.indexOf(':');
    return i < 0 ? '' : spec.slice(i + 1);
  }

  function applyTabs() {
    $all('[data-export-show]').forEach(function (el) {
      // 属性由组件按「单个空格」生成：组:值[ 组:值]。注意模板字符串里不能写反斜杠 s——
      // 反斜杠会被吃掉变成字母 s（INT-2434 自测时踩到：按字母 s 切，属性全失效）。
      var specs = String(el.getAttribute('data-export-show') || '').split(' ');
      var visible = true;
      for (var i = 0; i < specs.length; i += 1) {
        if (!specs[i]) continue;
        var group = groupOf(specs[i]);
        var value = valueOf(specs[i]);
        var current = group in tabState ? tabState[group] : value;
        if (value === '__all__') continue;
        if (current !== '__all__' && current !== value) { visible = false; break; }
      }
      el.style.display = visible ? '' : 'none';
    });

    $all('[data-export-round]').forEach(function (el) {
      var parts = String(el.getAttribute('data-export-round') || '').split('|');
      var group = parts[0];
      var tag = parts[1] || '';
      var mode = parts[2] || 'f';
      var current = group in tabState ? tabState[group] : '';
      var show;
      if (!current || current === '__all__') show = true;
      else if (current === 'overall') show = mode === 'f' ? true : (tag === '' || tag === 'overall');
      else show = tag === '' || tag === current;
      el.style.display = show ? '' : 'none';
    });
  }

  var tabButtons = $all('[data-export-tab]');
  var tabGroups = {};

  tabButtons.forEach(function (btn) {
    var spec = String(btn.getAttribute('data-export-tab') || '');
    if (!spec) return;
    var group = groupOf(spec);
    if (!(group in tabGroups)) tabGroups[group] = { first: valueOf(spec), selected: null };
    if (btn.getAttribute('aria-selected') === 'true' && tabGroups[group].selected === null) {
      tabGroups[group].selected = valueOf(spec);
    }
  });
  Object.keys(tabGroups).forEach(function (group) {
    // 默认态 = 页面克隆时的激活 Tab（aria-selected），没有则取组内第一个
    tabState[group] = tabGroups[group].selected !== null ? tabGroups[group].selected : tabGroups[group].first;
  });

  tabButtons.forEach(function (btn) {
    var spec = String(btn.getAttribute('data-export-tab') || '');
    if (!spec) return;
    var group = groupOf(spec);
    var value = valueOf(spec);
    btn.addEventListener('click', function (event) {
      event.preventDefault();
      tabState[group] = value;
      // 选中态只切 aria-selected，配色由导出样式表按 aria-selected 控制（不拼 className）
      tabButtons.forEach(function (other) {
        var otherSpec = String(other.getAttribute('data-export-tab') || '');
        if (groupOf(otherSpec) !== group) return;
        other.setAttribute('aria-selected', valueOf(otherSpec) === value ? 'true' : 'false');
      });
      applyTabs();
    });
  });

  applyTabs();

  // ---------- 5. 本页目录（右栏视口固定）：平滑跳转 + scrollspy + 阅读进度 ----------
  // 页面上的右导航靠 React scrollspy 驱动；导出里没有 React，这里用 scroll 事件
  // 算当前分节与进度，产物双击打开即可用。
  var tocLinks = $all('[data-export-toc-link]');
  if (tocLinks.length > 0) {
    var tocProgress = document.querySelector('[data-export-toc-progress]');
    var tocEntries = [];
    tocLinks.forEach(function (link) {
      var id = link.getAttribute('data-export-toc-link') || '';
      var section = id ? document.getElementById(id) : null;
      if (!section) return;
      tocEntries.push({ link: link, section: section });
      link.addEventListener('click', function (event) {
        event.preventDefault();
        section.scrollIntoView({ behavior: 'smooth', block: 'start' });
        if (window.history && window.history.replaceState) {
          window.history.replaceState(null, '', '#' + id);
        }
      });
    });

    var tocActive = null;
    function updateToc() {
      var scrolled = window.scrollY || window.pageYOffset || 0;
      var scrollable = (document.documentElement.scrollHeight || 0) - window.innerHeight;
      var ratio = scrollable > 0 ? scrolled / scrollable : 0;
      if (tocProgress) {
        tocProgress.style.width = (Math.max(0, Math.min(1, ratio)) * 100) + '%';
      }
      if (tocEntries.length === 0) return;
      var probeLine = scrolled + 96;
      var next = tocEntries[0];
      tocEntries.forEach(function (entry) {
        var top = entry.section.getBoundingClientRect().top + scrolled;
        if (top <= probeLine) next = entry;
      });
      if (next === tocActive) return;
      tocActive = next;
      tocEntries.forEach(function (entry) {
        if (entry === next) entry.link.setAttribute('aria-current', 'location');
        else entry.link.removeAttribute('aria-current');
      });
    }
    window.addEventListener('scroll', updateToc, { passive: true });
    window.addEventListener('resize', updateToc);
    // 折叠分区 / 切换 Tab 会改版面高度：点完再算一次
    document.addEventListener('click', function () { setTimeout(updateToc, 0); }, true);
    updateToc();
  }
})();`

/** 组装离线可用的 report.html */
export function buildReportHtmlDocument(params: {
  clone: HTMLElement
  reportName: string
  exportedAt: Date
}): string {
  const { clone, reportName, exportedAt } = params
  const exportedLabel = exportedAt.toLocaleString('zh-CN')
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${escapeHtml(reportName)} - 报告导出</title>
<link rel="stylesheet" href="css/report.css">
</head>
<body>
<!-- 报告正文克隆里自带 <main>（正文列），外层用 div 承载，避免 main 嵌套 -->
<div id="report-export-root">
${clone.outerHTML}
</div>
<footer style="text-align:center;padding:24px;color:#94a3b8;font-size:12px;border-top:1px solid #e2e8f0;margin-top:24px;">
  报告导出时间：${escapeHtml(exportedLabel)} | 导出自智能音频测试系统
</footer>
<script>
${REPORT_EXPORT_SCRIPT}
</script>
</body>
</html>`
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/**
 * 快照管线（克隆 → 静态化 → 样式内联 → 文档组装），单份与批量（INT-2419）共用。
 * 调用方需先把页面切到「导出态」（展开分区、灌满用例）并等待 `waitForReportExportReady`。
 */
export async function captureReportHtmlSnapshot(
  root: HTMLElement,
  options: HtmlExportOptions = {}
): Promise<HtmlSnapshotParts> {
  const pageSize = options.pageSize ?? HTML_EXPORT_CASE_PAGE_SIZE
  const reportName = options.fileName ?? 'report'

  const { clone, caseCount } = buildStaticClone(root, pageSize)

  const collected = await collectDocumentCss()
  const css = await inlineCssAssets(`${EXPORT_RESET_CSS}\n${collectRootCssVariables()}\n${collected}`)

  const html = buildReportHtmlDocument({ clone, reportName, exportedAt: new Date() })
  return { html, css, caseCount }
}

/**
 * 主入口：克隆报告 DOM → 样式内联 → 打包 zip。
 * 调用方需先把页面切到「导出态」（展开分区、灌满用例）并等待 `waitForReportExportReady`。
 */
export async function exportReportHtml(
  root: HTMLElement,
  options: HtmlExportOptions = {}
): Promise<HtmlExportArtifact> {
  const reportName = options.fileName ?? 'report'
  const { html, css, caseCount } = await captureReportHtmlSnapshot(root, options)

  const zip = new JSZip()
  zip.file('report.html', html)
  zip.folder('css')?.file('report.css', css)
  const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE' })

  return { blob, fileName: `${sanitizeFileName(reportName)}.zip`, caseCount, html }
}

/** 触发浏览器下载（Blob → objectURL） */
export function downloadBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  // 下载由浏览器异步接管，稍后再释放 objectURL
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}
