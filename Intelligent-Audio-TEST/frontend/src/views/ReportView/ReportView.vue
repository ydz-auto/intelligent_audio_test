<template>
  <div class="report-view-page">
    <!-- Toast 提示 -->
    <teleport to="#global-fixed-elements">
      <div v-if="toast" class="toast-container" :class="`toast-${toast.type}`">
        <i :class="toast.type === 'success' ? 'fas fa-check-circle' : toast.type === 'error' ? 'fas fa-exclamation-circle' : toast.type === 'warning' ? 'fas fa-exclamation-triangle' : 'fas fa-info-circle'"></i>
        <span>{{ toast.message }}</span>
      </div>
    </teleport>

    <div v-if="loading" class="loading-state">
      <div class="loading-spinner"></div>
      <p>正在加载报告...</p>
    </div>

    <div v-else-if="error" class="error-state">
      <h2>加载失败</h2>
      <p>{{ error }}</p>
      <button class="btn-primary" @click="goBack">返回</button>
    </div>

    <!-- 任务报告类型 -->
    <div v-else-if="report && report.type === 'task'">
      <TaskReportPanel
        :report="report"
        :is-editing-report="isEditingReport"
        :is-editing-conclusion="isEditingConclusion"
        :analysis-content="analysisContent"
        :tables="reportTables"
        @toggle-edit="toggleEditReport"
        @save-report="saveReport"
        @cancel-edit="cancelEditReport"
        @toggle-conclusion-edit="toggleEditConclusion"
        @save-conclusion="saveConclusion"
        @cancel-conclusion="cancelEditConclusion"
      />
    </div>

    <!-- 对比报告类型 (comparison / secondaryComparison) -->
    <ComparisonReportPanel
      v-else-if="report && isComparisonType"
      :report="report"
      :report-name="reportName"
      :report-conclusion="reportConclusion"
      :sanitized-conclusion="sanitizedConclusion"
      :is-editing-report="isEditingReport"
      :is-editing-conclusion="isEditingConclusion"
      @toggle-edit="toggleEditReport"
      @save-report="saveReport"
      @cancel-edit="cancelEditReport"
      @toggle-conclusion-edit="toggleEditConclusion"
      @save-conclusion="saveConclusion"
      @cancel-conclusion="cancelEditConclusion"
      @update:report-name="reportName = $event"
      @update:report-description="report.description = $event"
      @update:report-conclusion="report.conclusion = $event"
    />

    <div v-else class="empty-state">
      <h2>未找到报告</h2>
      <p>请提供有效的报告ID</p>
      <button class="btn-primary" @click="goToHistoryReports">查看历史报告</button>
    </div>

    <!-- 底部浮动操作按钮 -->
    <teleport to="#global-fixed-elements" v-if="report">
      <div id="floating-report-actions" style="position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); display: flex; justify-content: center; gap: 16px; z-index: 9999; padding: 16px 24px; background: rgba(255, 255, 255, 0.95); border-radius: 12px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15); backdrop-filter: blur(10px); border: 1px solid rgba(226, 232, 240, 0.8);">
        <button class="btn btn-primary" @click="saveReport">
          <i class="fas fa-save"></i> 保存
        </button>
        <button class="btn btn-success" @click="publishReport" v-if="report.status === 'draft'">
          <i class="fas fa-paper-plane"></i> 发布
        </button>
        <button class="btn btn-secondary" @click="goBack">
          <i class="fas fa-times"></i> 关闭
        </button>
      </div>
    </teleport>

    <!-- 右侧浮动操作按钮 -->
    <teleport to="#global-fixed-elements">
      <div class="floating-actions" v-if="report">
        <button class="action-btn" @click="copyLink" title="分享链接">
          <i class="fas fa-share-alt"></i>
        </button>
        <div class="export-dropdown-wrapper">
          <button class="action-btn" @click="toggleExportMenu" title="导出">
            <i class="fas fa-download"></i>
          </button>
          <div class="export-dropdown" v-if="showExportMenu">
            <button class="export-menu-item" @click="exportHtml">
              <i class="fas fa-file-code"></i>
              <span>导出 HTML</span>
            </button>
            <button class="export-menu-item" @click="exportReport">
              <i class="fas fa-file-export"></i>
              <span>导出 JSON</span>
            </button>
          </div>
        </div>
      </div>
      <div v-if="copySuccess" class="copy-toast">
        <i class="fas fa-check"></i> 链接已复制
      </div>
    </teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, provide, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { sanitizeConclusion } from '../../utils/sanitize'
import JSZip from 'jszip'
import TaskReportPanel from '../../components/report/TaskReportPanel.vue'
import ComparisonReportPanel from './sections/ComparisonReportPanel.vue'
import { reportsApi } from '../../utils/api'
import reportService from '../../services/reportService'

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const error = ref('')
const report = ref<any>(null)
const isEditingReport = ref(false)
const isEditingConclusion = ref(false)
const reportName = ref('')
const copySuccess = ref(false)

interface ToastMessage {
  type: 'success' | 'error' | 'warning' | 'info';
  message: string;
}

const toast = ref<ToastMessage | null>(null)

function showToast(type: ToastMessage['type'], message: string): void {
  toast.value = { type, message };
  setTimeout(() => { toast.value = null; }, 3000);
}

const isComparisonType = computed(() => {
  return report.value?.type === 'comparison' || report.value?.type === 'secondaryComparison'
})

const analysisContent = computed(() => {
  return report.value?.summary?.analysisConclusion || report.value?.analysisConclusion || report.value?.conclusion || ''
})

const reportTables = computed(() => {
  return report.value?.summary?.tables || []
})

const reportConclusion = computed({
  get: () => report.value?.conclusion || report.value?.analysis || '',
  set: (val: string) => {
    if (report.value) {
      report.value.conclusion = val
    }
  }
})

const sanitizedConclusion = computed(() => {
  return sanitizeConclusion(reportConclusion.value)
})

const loadReport = async (reportId: string) => {
  loading.value = true
  error.value = ''

  try {
    const response = await reportsApi.getOne(reportId)
    if (response) {
      report.value = {
        ...response,
        name: response.name,
        description: response.description || '',
        conclusion: (response.analysis || response.conclusion) || '',
        tags: response.tags || [],
        summary: response.summary || { total_cases: 0, completed_cases: 0, failed_cases: 0, all_metrics: [], detailed_results: [], device_stats: [], api_stats: [] }
      }
      reportName.value = report.value.name

      if (report.value.type === 'comparison' || report.value.type === 'secondaryComparison') {
        reportService.comparisonReport.value = report.value
        reportService.extractDevicesFromTasks([], report.value)
      }
    } else {
      error.value = '报告不存在'
    }
  } catch (e: any) {
    console.error('加载报告失败:', e)
    error.value = e.message || '加载报告失败'
  } finally {
    loading.value = false
  }
}

const toggleEditReport = () => {
  isEditingReport.value = !isEditingReport.value
}

const saveReport = async () => {
  if (!report.value) return
  try {
    report.value.name = reportName.value
    if (isComparisonType.value) {
      await reportService.saveReport(report.value)
    } else {
      await reportsApi.update(report.value.id, {
        title: report.value.title || report.value.name,
        description: report.value.description,
        summary: report.value.summary
      })
    }
    isEditingReport.value = false
    showToast('success', '报告保存成功')
  } catch (e: any) {
    console.error('保存报告失败:', e)
    showToast('error', '保存失败: ' + (e.message || '未知错误'))
  }
}

const cancelEditReport = () => {
  isEditingReport.value = false
}

const toggleEditConclusion = () => {
  isEditingConclusion.value = !isEditingConclusion.value
}

const saveConclusion = async (content?: string) => {
  if (!report.value) return
  try {
    const conclusionContent = content || reportConclusion.value
    if (isComparisonType.value) {
      report.value.conclusion = conclusionContent
      await reportService.saveReport(report.value)
    } else {
      const summary = {
        ...report.value.summary,
        analysisConclusion: conclusionContent
      }
      await reportsApi.update(report.value.id, { summary })
      report.value.summary = summary
      report.value.conclusion = conclusionContent
    }
    isEditingConclusion.value = false
    showToast('success', '结论保存成功')
  } catch (e: any) {
    console.error('保存结论失败:', e)
    showToast('error', '保存失败: ' + (e.message || '未知错误'))
  }
}

const cancelEditConclusion = () => {
  isEditingConclusion.value = false
}

const publishReport = async () => {
  if (!report.value) return
  if (!confirm('确定要发布该报告吗？')) return
  try {
    await reportsApi.publish(report.value.id)
    report.value.status = 'published'
    showToast('success', '报告发布成功')
  } catch (e: any) {
    console.error('发布失败:', e)
    showToast('error', '发布失败: ' + (e.message || '未知错误'))
  }
}

const exportReport = () => {
  if (report.value) {
    const data = JSON.stringify(report.value, null, 2)
    const blob = new Blob([data], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `report-${report.value.id}.json`
    a.click()
    URL.revokeObjectURL(url)
    showToast('success', '报告导出成功')
  }
  showExportMenu.value = false
}

const showExportMenu = ref(false)

const toggleExportMenu = () => {
  showExportMenu.value = !showExportMenu.value
}

// 导出模式标记：子组件通过 inject 获取，导出时展开所有内容
const isExporting = ref(false)
provide('isExporting', isExporting)

const exportHtml = async () => {
  showExportMenu.value = false
  if (!report.value) return
  try {
    showToast('info', '正在生成 HTML 报告包...')
    // 1. 设置导出模式，触发子组件展开折叠区块、加载所有数据（用例不展开）
    isExporting.value = true
    await nextTick()
    await new Promise(resolve => setTimeout(resolve, 500))
    await nextTick()
    // 2. 生成 ZIP 包
    const zipBlob = await generateExportZip()
    // 3. 恢复正常状态
    isExporting.value = false
    await nextTick()
    // 4. 下载
    const url = URL.createObjectURL(zipBlob)
    const a = document.createElement('a')
    a.href = url
    const safeName = (report.value.name || 'report').replace(/[^a-zA-Z0-9\u4e00-\u9fa5\-_]/g, '').trim() || 'report'
    a.download = `${safeName}.zip`
    a.click()
    URL.revokeObjectURL(url)
    showToast('success', 'HTML 报告包导出成功')
  } catch (e: any) {
    console.error('HTML 导出失败:', e)
    isExporting.value = false
    showToast('error', 'HTML 导出失败: ' + (e.message || '未知错误'))
  }
}

/**
 * 生成导出 ZIP 包
 * 结构：
 *   report.html          — 报告 HTML（引用本地 CSS/JS/字体）
 *   css/report.css       — 页面所有样式
 *   js/report.js         — 交互脚本
 *   webfonts/*.woff2     — FontAwesome 字体文件
 */
const generateExportZip = async (): Promise<Blob> => {
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
  cssText = `/* Reset */
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
` + cssText

  // ---------- 3. 生成 JS ----------
  const jsContent = getExportJs()

  // ---------- 4. 组装 HTML（JS 内联，避免 file:// 协议下外部脚本被阻止）----------
  const htmlContent = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${report.value.name || report.value.id} - 报告导出</title>
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

/**
 * 导出 HTML 的交互 JS 脚本
 */
const getExportJs = (): string => {
  return `(function() {
  'use strict';

  // ========== 1. 区块折叠/展开 ==========
  document.querySelectorAll('.section-header').forEach(function(header) {
    header.addEventListener('click', function() {
      var content = header.nextElementSibling;
      if (!content) return;
      var btn = header.querySelector('.collapse-btn');
      var isCollapsed = content.style.display === 'none';
      content.style.display = isCollapsed ? '' : 'none';
      if (btn) btn.classList.toggle('collapsed', !isCollapsed);
      var icon = btn ? btn.querySelector('i') : null;
      if (icon) {
        if (isCollapsed) { icon.classList.remove('fa-chevron-up'); icon.classList.add('fa-chevron-down'); }
        else { icon.classList.remove('fa-chevron-down'); icon.classList.add('fa-chevron-up'); }
      }
    });
  });

  // ========== 2. 用例卡片展开/折叠 ==========
  document.querySelectorAll('.case-header').forEach(function(header) {
    header.addEventListener('click', function(e) {
      if (e.target.closest('.case-id-badge')) return;
      var card = header.closest('.case-card');
      if (!card) return;
      var details = card.querySelector('.case-details');
      if (!details) return;
      var icon = header.querySelector('.expand-icon i');
      if (details.style.display === 'none') {
        details.style.display = '';
        if (icon) { icon.classList.remove('fa-chevron-down'); icon.classList.add('fa-chevron-up'); }
      } else {
        details.style.display = 'none';
        if (icon) { icon.classList.remove('fa-chevron-up'); icon.classList.add('fa-chevron-down'); }
      }
    });
  });

  // ========== 3. 维度卡片折叠/展开 ==========
  document.querySelectorAll('.metric-collapse-btn').forEach(function(btn) {
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      var container = btn.closest('.metric-comparison-card') || btn.closest('.metric-container');
      if (!container) return;
      var content = container.querySelector('.metric-container-content');
      if (!content) return;
      var isCollapsed = content.style.display === 'none';
      content.style.display = isCollapsed ? '' : 'none';
      btn.classList.toggle('collapsed', !isCollapsed);
      var icon = btn.querySelector('i');
      if (icon) {
        if (isCollapsed) { icon.classList.remove('fa-chevron-up'); icon.classList.add('fa-chevron-down'); }
        else { icon.classList.remove('fa-chevron-down'); icon.classList.add('fa-chevron-up'); }
      }
    });
  });

  // ========== 4. 显示类型切换 ==========
  document.querySelectorAll('.display-type-btn').forEach(function(btn) {
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      var container = btn.closest('.metric-comparison-card') || btn.closest('.metric-container');
      if (!container) return;
      container.querySelectorAll('.display-type-btn').forEach(function(b) { b.classList.remove('active'); });
      btn.classList.add('active');
      var type = btn.getAttribute('data-type') || btn.textContent.trim().toLowerCase();
      var tableEl = container.querySelector('.table-container');
      var chartEl = container.querySelector('.chart-container');
      if (type === 'table') {
        if (tableEl) tableEl.style.display = '';
        if (chartEl) chartEl.style.display = 'none';
      } else {
        if (tableEl) tableEl.style.display = 'none';
        if (chartEl) {
          chartEl.style.display = '';
          var canvas = chartEl.querySelector('canvas');
          if (canvas) {
            chartEl.innerHTML = '<div style="padding:40px;text-align:center;color:#94a3b8;"><i class="fas fa-chart-bar" style="font-size:48px;"></i><p style="margin-top:12px;">图表在导出的 HTML 中不可用，请切换到表格模式查看数据</p></div>';
          }
        }
      }
    });
  });

  // ========== 5. 用例搜索过滤（与分页联动） ==========
  // allCaseCards 等分页变量在下方第9节声明，此处提前声明以供 applyFilters 使用
  var allCaseCards = document.querySelectorAll('.case-card');
  var totalCases = allCaseCards.length;
  var pageSize = 10;
  var currentPage = 1;
  var totalPages = Math.max(1, Math.ceil(totalCases / pageSize));
  var paginationContainer = document.querySelector('.specific-case-pagination');
  var caseSearchInput = document.querySelector('.filter-input[placeholder*="用例名称"]') || document.querySelector('.filter-input[placeholder*="关键词"]');
  function applyFilters() {
    var query = caseSearchInput ? caseSearchInput.value.toLowerCase().trim() : '';
    var activeCategories = Array.from(document.querySelectorAll('.tag-filter-item.active')).map(function(t) { return t.textContent.trim(); });
    var activeTags = Array.from(document.querySelectorAll('.tag-filter-item-orange.active')).map(function(t) { return t.textContent.trim(); });
    var visibleCount = 0;
    allCaseCards.forEach(function(card) {
      var nameEl = card.querySelector('.case-name');
      var name = nameEl ? nameEl.textContent.toLowerCase() : '';
      var catEl = card.querySelector('.case-category');
      var cat = catEl ? catEl.textContent.trim() : '';
      var tagEls = card.querySelectorAll('.tag');
      var tags = Array.from(tagEls).map(function(t) { return t.textContent.trim(); });
      var nameMatch = !query || name.includes(query);
      var catMatch = activeCategories.length === 0 || activeCategories.includes(cat);
      var tagMatch = activeTags.length === 0 || activeTags.some(function(t) { return tags.includes(t); });
      if (nameMatch && catMatch && tagMatch) {
        card.setAttribute('data-filtered-out', 'false');
        visibleCount++;
      } else {
        card.setAttribute('data-filtered-out', 'true');
      }
    });
    // 重新计算分页（基于可见用例数）
    totalCases = visibleCount;
    totalPages = Math.max(1, Math.ceil(totalCases / pageSize));
    currentPage = 1;
    updateCasePagination();
  }
  if (caseSearchInput) {
    caseSearchInput.addEventListener('input', function() {
      applyFilters();
    });
  }

  // ========== 6. 标签/分组/维度筛选切换 ==========
  document.querySelectorAll('.tag-filter-item, .tag-filter-item-orange, .metric-filter-item').forEach(function(tag) {
    tag.addEventListener('click', function(e) {
      e.stopPropagation();
      tag.classList.toggle('active');
    });
  });

  // ========== 7. 重置/应用筛选（与分页联动） ==========
  document.querySelectorAll('.btn-secondary, .filter-buttons .btn').forEach(function(btn) {
    if (btn.textContent.includes('重置')) {
      btn.addEventListener('click', function() {
        document.querySelectorAll('.filter-input').forEach(function(input) { input.value = ''; });
        document.querySelectorAll('.tag-filter-item.active, .tag-filter-item-orange.active, .metric-filter-item.active').forEach(function(t) { t.classList.remove('active'); });
        applyFilters();
      });
    }
    if (btn.textContent.includes('应用') || btn.textContent.includes('筛选')) {
      btn.addEventListener('click', function() {
        applyFilters();
      });
    }
  });

  // ========== 8. 复制用例 ID ==========
  document.querySelectorAll('.case-id-badge').forEach(function(badge) {
    badge.addEventListener('click', function(e) {
      e.stopPropagation();
      var text = badge.textContent.replace(/.*用例ID:\\s*/, '').trim();
      // file:// 协议下 navigator.clipboard 不可用，使用 fallback
      try {
        if (navigator.clipboard && window.isSecureContext) {
          navigator.clipboard.writeText(text).then(function() {
            badge.style.color = '#16a34a';
            setTimeout(function() { badge.style.color = ''; }, 1500);
          });
        } else {
          var ta = document.createElement('textarea');
          ta.value = text;
          ta.style.position = 'fixed';
          ta.style.left = '-9999px';
          document.body.appendChild(ta);
          ta.select();
          document.execCommand('copy');
          document.body.removeChild(ta);
          badge.style.color = '#16a34a';
          setTimeout(function() { badge.style.color = ''; }, 1500);
        }
      } catch(err) {
        console.log('复制失败:', err);
      }
    });
  });

  // ========== 9. 用例分页 ==========
  function updateCasePagination() {
    var start = (currentPage - 1) * pageSize;
    var end = start + pageSize;
    allCaseCards.forEach(function(card, idx) {
      // 如果被搜索/筛选隐藏了，不覆盖 display:none
      var isFilteredOut = card.getAttribute('data-filtered-out') === 'true';
      if (isFilteredOut) {
        card.style.display = 'none';
      } else {
        card.style.display = (idx >= start && idx < end) ? '' : 'none';
      }
    });
    // 更新分页信息
    var infoEl = paginationContainer ? paginationContainer.querySelector('.pagination-info') : null;
    if (infoEl) {
      infoEl.textContent = '显示第 ' + currentPage + ' 页，共 ' + totalPages + ' 页，总计 ' + totalCases + ' 条记录';
    }
    // 更新按钮 active 状态
    if (paginationContainer) {
      paginationContainer.querySelectorAll('.pagination-btn').forEach(function(btn) {
        btn.classList.remove('active');
        var text = btn.textContent.trim();
        if (text == String(currentPage)) btn.classList.add('active');
      });
      // 上一页/下一页 disabled 状态
      var prevBtn = paginationContainer.querySelector('.pagination-btn:first-child');
      var nextBtns = paginationContainer.querySelectorAll('.pagination-btn');
      var nextBtn = nextBtns[nextBtns.length - 1];
      if (prevBtn) prevBtn.disabled = (currentPage <= 1);
      if (nextBtn) nextBtn.disabled = (currentPage >= totalPages);
    }
  }

  if (paginationContainer) {
    paginationContainer.querySelectorAll('.pagination-btn').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        var text = btn.textContent.trim();
        if (text === '< 上一页' || text.indexOf('上一页') >= 0) {
          if (currentPage > 1) currentPage--;
        } else if (text === '下一页 >' || text.indexOf('下一页') >= 0) {
          if (currentPage < totalPages) currentPage++;
        } else if (text === '跳转') {
          var input = paginationContainer.querySelector('.pagination-input');
          if (input) {
            var p = parseInt(input.value);
            if (!isNaN(p) && p >= 1 && p <= totalPages) currentPage = p;
          }
        } else {
          var pNum = parseInt(text);
          if (!isNaN(pNum)) currentPage = pNum;
        }
        updateCasePagination();
      });
    });
    // 回车跳转
    var jumpInput = paginationContainer.querySelector('.pagination-input');
    if (jumpInput) {
      jumpInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
          var p = parseInt(jumpInput.value);
          if (!isNaN(p) && p >= 1 && p <= totalPages) {
            currentPage = p;
            updateCasePagination();
          }
        }
      });
    }
    // 每页条数切换
    var sizeSelect = paginationContainer.querySelector('.page-size-select select');
    if (sizeSelect) {
      sizeSelect.addEventListener('change', function() {
        pageSize = parseInt(sizeSelect.value);
        totalPages = Math.max(1, Math.ceil(totalCases / pageSize));
        currentPage = 1;
        updateCasePagination();
      });
    }
    // 初始化
    updateCasePagination();
  }

  console.log('报告导出 HTML 交互脚本已加载');
})();`
}

const copyLink = async () => {
  try {
    await navigator.clipboard.writeText(window.location.href)
    copySuccess.value = true
    setTimeout(() => { copySuccess.value = false }, 2000)
  } catch (e) {
    console.error('复制失败:', e)
    showToast('error', '复制链接失败')
  }
}

const goBack = () => router.back()
const goToHistoryReports = () => router.push('/history-reports')

onMounted(() => {
  const reportId = route.params.id as string || route.query.id as string
  if (reportId) {
    loadReport(reportId)
  } else {
    loading.value = false
  }
  document.addEventListener('click', closeExportMenuOnOutsideClick)
})

onUnmounted(() => {
  reportService.resetReportState()
  document.removeEventListener('click', closeExportMenuOnOutsideClick)
})

const closeExportMenuOnOutsideClick = (e: MouseEvent) => {
  const target = e.target as HTMLElement
  if (showExportMenu.value && !target.closest('.export-dropdown-wrapper')) {
    showExportMenu.value = false
  }
}
</script>

<style src="./reportView.css"></style>
