<template>
  <div class="rv-report-view-page">
    <!-- Toast 提示 -->
    <teleport to="#global-fixed-elements">
      <div v-if="toast" class="rv-toast-container" :class="`rv-toast-${toast.type}`">
        <i :class="toast.type === 'success' ? 'fas fa-check-circle' : toast.type === 'error' ? 'fas fa-exclamation-circle' : toast.type === 'warning' ? 'fas fa-exclamation-triangle' : 'fas fa-info-circle'"></i>
        <span>{{ toast.message }}</span>
      </div>
    </teleport>

    <div v-if="loading" class="rv-loading-state">
      <div class="rv-loading-spinner"></div>
      <p>正在加载报告...</p>
    </div>

    <div v-else-if="error" class="rv-error-state">
      <h2>加载失败</h2>
      <p>{{ error }}</p>
      <button class="rv-btn-primary" @click="goBack">返回</button>
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

    <!-- Benchmark 报告类型（INT-483：内嵌排行区块，chart.js 展示发布时点快照） -->
    <BenchmarkReportPanel v-else-if="report && report.type === 'benchmark'" :report="report" />

    <!-- 对比报告类型 (comparison 家族：comparison / secondary_comparison 及历史遗留值) -->
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

    <div v-else class="rv-empty-state">
      <h2>未找到报告</h2>
      <p>请提供有效的报告ID</p>
      <button class="rv-btn-primary" @click="goToHistoryReports">查看历史报告</button>
    </div>

    <!-- 底部浮动操作按钮 -->
    <teleport to="#global-fixed-elements" v-if="report">
      <div id="floating-report-actions" class="rv-floating-report-actions">
        <!-- INT-423/467：报告可见性徽标 + 分享/设为私有（仅 owner 或共享资源可切） -->
        <VisibilityBadge :visibility="report.visibility" />
        <button
          v-if="canToggleReportVisibility"
          class="rv-btn rv-btn-secondary"
          :title="report.visibility === 'private' ? '将报告改为共享（所有有权限用户可见）' : '将报告设为私有（仅自己可见）'"
          @click="toggleReportVisibility"
        >
          <i class="fas" :class="report.visibility === 'private' ? 'fa-users' : 'fa-lock'"></i>
          {{ report.visibility === 'private' ? '设为共享' : '设为私有' }}
        </button>
        <!-- INT-483：Benchmark 报告为发布时点定格快照，不提供编辑/保存 -->
        <button v-if="!isBenchmarkType" class="rv-btn rv-btn-primary" @click="saveReport">
          <i class="fas fa-save"></i> 保存
        </button>
        <button class="rv-btn rv-btn-success" @click="publishReport" v-if="report.status === ReportStatus.DRAFT">
          <i class="fas fa-paper-plane"></i> 发布
        </button>
        <button class="rv-btn rv-btn-secondary" @click="goBack">
          <i class="fas fa-times"></i> 关闭
        </button>
      </div>
    </teleport>

    <!-- 右侧浮动操作按钮 -->
    <teleport to="#global-fixed-elements">
      <div class="rv-floating-actions" v-if="report">
        <button class="rv-action-btn" @click="copyLink" title="分享链接">
          <i class="fas fa-share-alt"></i>
        </button>
        <div class="rv-export-dropdown-wrapper">
          <button class="rv-action-btn" @click="toggleExportMenu" title="导出">
            <i class="fas fa-download"></i>
          </button>
          <div class="rv-export-dropdown" v-if="showExportMenu">
            <button class="rv-export-menu-item" @click="exportHtml">
              <i class="fas fa-file-code"></i>
              <span>导出 HTML</span>
            </button>
            <button class="rv-export-menu-item" @click="exportReport">
              <i class="fas fa-file-export"></i>
              <span>导出 JSON</span>
            </button>
          </div>
        </div>
      </div>
      <div v-if="copySuccess" class="rv-copy-toast">
        <i class="fas fa-check"></i> 链接已复制
      </div>
    </teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, provide, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { sanitizeConclusion } from '../../utils/sanitize'
import { ReportStatus, Visibility } from '@/domain/enums'
import type { ToastMessage } from '@/domain/model/ui'
import { isComparisonReportType } from '@/domain/model/report'
import TaskReportPanel from '../../components/report/TaskReportPanel.vue'
import ComparisonReportPanel from './sections/ComparisonReportPanel.vue'
import BenchmarkReportPanel from './sections/BenchmarkReportPanel.vue'
import { reportsPort } from '@/composables/report/reportsPort'
import { comparisonReport } from '../../store/reportComparisonStore'
import { copyToClipboard } from '../../utils/utils'
import { isNotFoundOrForbidden, canEditResource } from '@/composables/visibility/useVisibility'
import VisibilityBadge from '@/components/common/visibility/VisibilityBadge.vue'
import {
  extractDevicesFromTasks,
  saveReport as saveComparisonReportApi,
  resetReportState,
} from '../../composables/report/useReportComparison'
import { generateExportZip } from './reportExport'
import { useModalControl, MODAL_TYPES } from '@/composables/modal/useModal'

const route = useRoute()
const router = useRouter()
const modalControl = useModalControl()

const loading = ref(true)
const error = ref('')
const report = ref<any>(null)
const isEditingReport = ref(false)
const isEditingConclusion = ref(false)
const reportName = ref('')
const copySuccess = ref(false)

const toast = ref<ToastMessage | null>(null)

function showToast(type: ToastMessage['type'], message: string): void {
  toast.value = { type, message };
  setTimeout(() => { toast.value = null; }, 3000);
}

const isComparisonType = computed(() => {
  return isComparisonReportType(report.value?.type)
})

/** INT-423/467：报告是否可切换可见性（owner 或共享；私有非 owner 无权限） */
const canToggleReportVisibility = computed(() => {
  return canEditResource({
    visibility: report.value?.visibility,
    createdByUserId: report.value?.createdByUserId,
  })
})

/** 分享 / 设为私有：PATCH /reports/{id}/visibility（需 report:share + owner 校验） */
const toggleReportVisibility = async () => {
  if (!report.value?.id || !canToggleReportVisibility.value) return
  const next = report.value.visibility === Visibility.PRIVATE
    ? Visibility.SHARED
    : Visibility.PRIVATE
  try {
    await reportsPort.updateVisibility(report.value.id, next)
    report.value.visibility = next
    showToast('success', next === Visibility.SHARED ? '已改为共享' : '已设为私有')
  } catch (e: any) {
    console.error('切换报告可见性失败:', e)
    showToast('error', e?.message || '切换可见性失败，请确认您有该报告的分享权限')
  }
}

/** INT-483：Benchmark 报告类型（发布时点定格快照，不可编辑保存） */
const isBenchmarkType = computed(() => report.value?.type === 'benchmark')

const analysisContent = computed(() => {
  return report.value?.summary?.analysisConclusion || report.value?.analysisConclusion || report.value?.conclusion || ''
})

const reportTables = computed(() => {
  return report.value?.summary?.tables || []
})

const reportConclusion = computed({
  get: () => report.value?.conclusion || '',
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
    const response = await reportsPort.getOne(reportId)
    if (response) {
      report.value = {
        ...response,
        name: response.name,
        description: response.description || '',
        // camelCase 改造：Domain Report 无 analysis 字段，分析结论由 conclusion 承载
        conclusion: response.conclusion || '',
        // camelCase 改造：Domain Report 无 tags 字段，标签维度指标数据由 summary.tagMetricData 提供
        tags: response.summary?.tagMetricData || [],
        summary: response.summary || { totalCases: 0, completedCases: 0, failedCases: 0, allMetrics: [], detailedResults: [], deviceStats: [], apiStats: [] }
      }
      reportName.value = report.value.name

      if (isComparisonReportType(report.value.type)) {
        comparisonReport.value = report.value
        extractDevicesFromTasks([], report.value)
      }
    } else {
      error.value = '报告不存在'
    }
  } catch (e: any) {
    console.error('加载报告失败:', e)
    // INT-423/467：私有报告非 owner 路由直达 → 后端 404/403；统一文案不泄露资源名
    error.value = isNotFoundOrForbidden(e) ? '资源不存在或无权访问' : (e.message || '加载报告失败')
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
      await saveComparisonReportApi(report.value)
    } else {
      await reportsPort.update(report.value.id, {
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
      await saveComparisonReportApi(report.value)
    } else {
      const summary = {
        ...report.value.summary,
        analysisConclusion: conclusionContent
      }
      await reportsPort.update(report.value.id, { summary })
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
  try {
    await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '发布报告',
      content: '确定要发布该报告吗？',
      confirmText: '发布',
      cancelText: '取消'
    })
  } catch {
    return // 用户取消
  }
  try {
    await reportsPort.publish(report.value.id)
    report.value.status = ReportStatus.PUBLISHED
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
    // 2. 生成 ZIP 包（DOM 捕获 / CSS 提取 / 字体打包见 reportExport.ts）
    const zipBlob = await generateExportZip(String(report.value.name || report.value.id))
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
  resetReportState()
  document.removeEventListener('click', closeExportMenuOnOutsideClick)
})

const closeExportMenuOnOutsideClick = (e: MouseEvent) => {
  const target = e.target as HTMLElement
  if (showExportMenu.value && !target.closest('.rv-export-dropdown-wrapper')) {
    showExportMenu.value = false
  }
}
</script>

<!-- INT-278：页面样式走 rv- 前缀命名空间隔离（同 INT-250 pt-/INT-277 tg- 方案），禁止裸 .btn/.loading-state/.empty-state 等全站通用类名全局注入污染其他页面 -->
<style src="./reportView.css"></style>
