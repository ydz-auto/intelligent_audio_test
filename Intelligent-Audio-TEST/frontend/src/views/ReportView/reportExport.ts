/**
 * ReportView —— 导出 HTML 报告 ZIP 包组装
 * 职责：捕获报告 DOM → 提取页面样式 → 生成内嵌交互脚本 → 打包 FontAwesome
 * 字体 → 产出可离线打开（file:// 协议）的 ZIP Blob
 */
import JSZip from 'jszip';
import { getExportJs } from './reportExportScript';

/** 导出专用样式：重置默认样式，保证 file:// 下排版一致 */
const EXPORT_CSS_RESET = `/* Reset */
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { background: #fff; }
@media print {
  .floating-actions, .export-dropdown-wrapper { display: none !important; }
  .report-section, .task-report-panel { break-inside: avoid; }
}
body { padding: 0; }
.report-view-page { margin: 0; padding: 0; width: 100% !important; }
.task-report-panel, .comparison-report-container { max-width: 100% !important; }
.report-layout { max-width: 1200px; margin: 0 auto; }
canvas, svg { max-width: 100%; }
.collapse-btn, .case-header, .section-header { cursor: pointer; }
.tag-filter-item, .tag-filter-item-orange, .metric-filter-item { cursor: pointer; }
.display-type-btn, .metric-collapse-btn { cursor: pointer; }
.btn, .pagination-btn, .case-id-badge { cursor: pointer; }
`;

/**
 * 生成导出 ZIP 包
 * 结构：
 *   report.html          — 报告 HTML（引用本地 CSS/JS/字体）
 *   css/report.css       — 页面所有样式
 *   js/report.js         — 交互脚本
 *   webfonts/*.woff2     — FontAwesome 字体文件
 *
 * @param reportTitle 报告标题（导出 HTML 页面标题）
 */
export const generateExportZip = async (reportTitle: string): Promise<Blob> => {
  const zip = new JSZip()

  // ---------- 1. 捕获 DOM ----------
  const reportEl = document.querySelector('.task-report-panel') || document.querySelector('.comparison-report-container') || document.querySelector('.report-view-page')
  if (!reportEl) throw new Error('未找到报告内容')

  const clone = reportEl.cloneNode(true) as HTMLElement

  // 移除不需要的元素
  clone.querySelectorAll('.floating-actions, .export-dropdown-wrapper, .analysis-actions .btn, .edit-btn, .save-btn, .cancel-btn, .publish-btn, .download-log-btn, .unpin-btn').forEach(el => el.remove())
  clone.querySelectorAll('.modal-overlay, .download-loading-overlay').forEach(el => el.remove())

  // 用例详情默认折叠（移除 details 内容，保留 header 可点击展开）
  // 由于 clone 后 v-if 的 details 已经渲染了，需要隐藏它们
  clone.querySelectorAll('.case-details').forEach(el => { (el as HTMLElement).style.display = 'none' })
  // 设置展开图标为折叠状态
  clone.querySelectorAll('.case-card .expand-icon i').forEach(el => {
    el.classList.remove('fa-chevron-up')
    el.classList.add('fa-chevron-down')
  })

  // 用例分页：初始只显示第一页（pageSize=10），其余隐藏
  const allCaseCards = clone.querySelectorAll('.case-card')
  const exportPageSize = 10
  allCaseCards.forEach((card, idx) => {
    ;(card as HTMLElement).setAttribute('data-case-index', String(idx))
    if (idx >= exportPageSize) {
      ;(card as HTMLElement).style.display = 'none'
    }
  })
  // 更新分页信息文本
  const totalPages = Math.max(1, Math.ceil(allCaseCards.length / exportPageSize))
  clone.querySelectorAll('.specific-case-pagination .pagination-info').forEach(el => {
    el.textContent = `显示第 1 页，共 ${totalPages} 页，总计 ${allCaseCards.length} 条记录`
  })

  // computed style
  const computedStyle = window.getComputedStyle(reportEl)
  const reportStyles: Record<string, string> = {
    background: computedStyle.background || '#fff',
    color: computedStyle.color || '#1e293b',
    fontFamily: computedStyle.fontFamily || "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    fontSize: computedStyle.fontSize || '14px',
    lineHeight: computedStyle.lineHeight || '1.6',
  }
  Object.entries(reportStyles).forEach(([k, v]) => {
    clone.style.setProperty(k, v)
  })

  const reportHtml = clone.outerHTML

  // ---------- 2. 提取 CSS ----------
  const styleSheets = document.styleSheets
  let cssText = ''
  for (let i = 0; i < styleSheets.length; i++) {
    const sheet = styleSheets[i]
    try {
      const rules = sheet.cssRules || sheet.rules
      if (!rules) continue
      for (let j = 0; j < rules.length; j++) {
        cssText += rules[j].cssText + '\n'
      }
    } catch {
      // 跨域跳过
    }
  }
  // 替换 FontAwesome 字体路径为本地 webfonts/
  cssText = cssText.replace(/https?:\/\/[^/]+\/[^)]*\/(fa-[^/]+\.\w+)/g, 'webfonts/$1')
  // 也处理 cdnjs 路径
  cssText = cssText.replace(/url\(["']?[^"')]*\/([^/"')]+\.woff2)["']?\)/g, 'url(../webfonts/$1)')

  // 添加导出专用样式
  cssText = EXPORT_CSS_RESET + cssText

  // ---------- 3. 生成 JS ----------
  const jsContent = getExportJs()

  // ---------- 4. 组装 HTML（JS 内联，避免 file:// 协议下外部脚本被阻止）----------
  const htmlContent = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${reportTitle} - 报告导出</title>
<link rel="stylesheet" href="css/report.css">
</head>
<body>
${reportHtml}
<div style="text-align:center; padding:24px; color:#94a3b8; font-size:12px; border-top:1px solid #e2e8f0; margin-top:24px;">
  报告导出时间: ${new Date().toLocaleString('zh-CN')} | 导出自智能音频测试系统
</div>
<script>
${jsContent}
<\/script>
</body>
</html>`

  // ---------- 5. 添加 FontAwesome 字体文件 ----------
  // 使用 Vite 的 ?url 导入，在 dev 和 build 时都能获取正确的资源 URL
  const fontBrandsUrl = new URL('@fortawesome/fontawesome-free/webfonts/fa-brands-400.woff2', import.meta.url).href
  const fontRegularUrl = new URL('@fortawesome/fontawesome-free/webfonts/fa-regular-400.woff2', import.meta.url).href
  const fontSolidUrl = new URL('@fortawesome/fontawesome-free/webfonts/fa-solid-900.woff2', import.meta.url).href
  const webfontsFolder = zip.folder('webfonts')!
  const fontUrls = [
    { name: 'fa-brands-400.woff2', url: fontBrandsUrl },
    { name: 'fa-regular-400.woff2', url: fontRegularUrl },
    { name: 'fa-solid-900.woff2', url: fontSolidUrl },
  ]

  for (const { name, url } of fontUrls) {
    try {
      // 静态字体资源（Vite ?url 导入），非业务 API，无需走基础设施层
      const response = await fetch(url)
      if (response.ok) {
        const buffer = await response.arrayBuffer()
        webfontsFolder.file(name, buffer)
      }
    } catch {
      // 字体加载失败不阻塞导出
    }
  }

  // ---------- 6. 写入 ZIP ----------
  zip.file('report.html', htmlContent)
  zip.folder('css')!.file('report.css', cssText)
  // JS 已内联到 HTML 中（file:// 协议不支持外部脚本加载）

  return zip.generateAsync({ type: 'blob', compression: 'DEFLATE' })
}