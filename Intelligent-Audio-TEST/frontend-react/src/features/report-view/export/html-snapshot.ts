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

/** 导出态就绪标记（SpecificCaseComparison 在导出态写入；含用例总数） */
export const EXPORT_READY_ATTR = 'data-export-cases-ready'

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

/** 克隆后仍保留的按钮：分区折叠触发器 + 用例「展开详情」（导出脚本接管其交互） */
const KEEP_BUTTON_SELECTOR =
  '[data-slot="collapsible-trigger"], button[aria-label="展开详情"], button[aria-label="收起详情"]'

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
[data-export-case-pageinfo] { font-size: 12px; color: #6b7280; margin-inline-start: auto; }
@media print {
  [data-export-case-toolbar] { display: none !important; }
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
    if (btn.matches(KEEP_BUTTON_SELECTOR)) return
    if (btn.matches(KEEP_TEXT_BUTTON_SELECTOR)) {
      unwrapElement(btn)
      return
    }
    btn.remove()
  })
  clone.querySelectorAll('input, select, textarea').forEach((el) => el.remove())

  // 4) 折叠面板统一展开（导出内由脚本控制显示）
  clone
    .querySelectorAll('[data-slot="collapsible-content"], [data-slot="collapsible-panel"]')
    .forEach((panel) => {
      panel.removeAttribute('hidden')
      ;(panel as HTMLElement).style.display = ''
    })

  // 5) 纯标题分区（总览 / 对比表格）包一层可折叠面板
  prepareHeadingSections(clone)

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

  const search = document.createElement('input')
  search.type = 'search'
  search.id = 'export-case-search'
  search.placeholder = '搜索用例ID或名称'
  search.setAttribute('aria-label', '搜索用例ID或名称')

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

  toolbar.append(search, sizeLabel, prev, next, jump, jumpBtn, info)
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
      var icon = btn.querySelector('svg');
      if (icon) icon.style.transform = hidden ? 'rotate(180deg)' : '';
    });
  });

  // ---------- 3. 用例搜索 + 分页 ----------
  var cards = $all('[data-export-case]');
  var searchInput = document.getElementById('export-case-search');
  var sizeSelect = document.getElementById('export-case-page-size');
  var prevBtn = document.getElementById('export-case-prev');
  var nextBtn = document.getElementById('export-case-next');
  var jumpInput = document.getElementById('export-case-jump');
  var jumpBtn = document.getElementById('export-case-jump-btn');
  var info = document.getElementById('export-case-pageinfo');
  var pageSize = sizeSelect ? parseInt(sizeSelect.value, 10) || 10 : 10;
  var currentPage = 1;
  var keyword = '';

  function matches(card) {
    if (!keyword) return true;
    var name = (card.getAttribute('data-export-case-name') || '').toLowerCase();
    var id = (card.getAttribute('data-export-case-id') || '').toLowerCase();
    return name.indexOf(keyword) >= 0 || id.indexOf(keyword) >= 0;
  }

  function render() {
    var visible = cards.filter(matches);
    var total = visible.length;
    var pages = Math.max(1, Math.ceil(total / pageSize));
    if (currentPage > pages) currentPage = pages;
    if (currentPage < 1) currentPage = 1;
    var start = (currentPage - 1) * pageSize;
    cards.forEach(function (card) { card.style.display = 'none'; });
    visible.slice(start, start + pageSize).forEach(function (card) {
      card.style.display = '';
    });
    if (info) {
      // 工具条单位与卡片口径一致（用例卡 = 按 test_case_id 合并后的张数），避免与页面
      // 区块头的「共 N 条结果」（结果行口径）同屏两个「条结果」（INT-2418 P3-2）
      info.textContent = '显示第 ' + currentPage + ' 页，共 ' + pages + ' 页，总计 ' + total + ' 个用例';
    }
    if (prevBtn) prevBtn.disabled = currentPage <= 1;
    if (nextBtn) nextBtn.disabled = currentPage >= pages;
    if (jumpInput) jumpInput.max = String(pages);
  }

  if (searchInput) {
    searchInput.addEventListener('input', function () {
      keyword = String(searchInput.value || '').trim().toLowerCase();
      currentPage = 1;
      render();
    });
  }
  if (sizeSelect) {
    sizeSelect.addEventListener('change', function () {
      pageSize = parseInt(sizeSelect.value, 10) || 10;
      currentPage = 1;
      render();
    });
  }
  if (prevBtn) {
    prevBtn.addEventListener('click', function () {
      if (currentPage > 1) { currentPage -= 1; render(); }
    });
  }
  if (nextBtn) {
    nextBtn.addEventListener('click', function () {
      var pages = Math.max(1, Math.ceil(cards.filter(matches).length / pageSize));
      if (currentPage < pages) { currentPage += 1; render(); }
    });
  }
  function jumpToPage() {
    if (!jumpInput) return;
    var pages = Math.max(1, Math.ceil(cards.filter(matches).length / pageSize));
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

  if (cards.length > 0) render();
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
<main id="report-export-root">
${clone.outerHTML}
</main>
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
 * 主入口：克隆报告 DOM → 样式内联 → 打包 zip。
 * 调用方需先把页面切到「导出态」（展开分区、灌满用例）并等待 `waitForReportExportReady`。
 */
export async function exportReportHtml(
  root: HTMLElement,
  options: HtmlExportOptions = {}
): Promise<HtmlExportArtifact> {
  const pageSize = options.pageSize ?? HTML_EXPORT_CASE_PAGE_SIZE
  const reportName = options.fileName ?? 'report'

  const { clone, caseCount } = buildStaticClone(root, pageSize)

  const collected = await collectDocumentCss()
  const css = await inlineCssAssets(`${EXPORT_RESET_CSS}\n${collectRootCssVariables()}\n${collected}`)

  const html = buildReportHtmlDocument({ clone, reportName, exportedAt: new Date() })

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
