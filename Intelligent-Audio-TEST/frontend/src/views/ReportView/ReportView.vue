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
        <button class="action-btn" @click="exportReport" title="导出">
          <i class="fas fa-download"></i>
        </button>
      </div>
      <div v-if="copySuccess" class="copy-toast">
        <i class="fas fa-check"></i> 链接已复制
      </div>
    </teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { sanitizeConclusion } from '../../utils/sanitize'
import { normalizeReport } from '../../utils/fieldNaming'
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
      const normalizedResponse = normalizeReport(response)
      report.value = {
        ...normalizedResponse,
        name: normalizedResponse.name,
        description: normalizedResponse.description || '',
        conclusion: (normalizedResponse.analysis || normalizedResponse.conclusion) || '',
        tags: normalizedResponse.tags || [],
        summary: normalizedResponse.summary || { totalCases: 0, completedCases: 0, failedCases: 0, allMetrics: [], detailedResults: [], deviceStats: [], apiStats: [] }
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
})

onUnmounted(() => {
  reportService.resetReportState()
})
</script>

<style src="./reportView.css"></style>
