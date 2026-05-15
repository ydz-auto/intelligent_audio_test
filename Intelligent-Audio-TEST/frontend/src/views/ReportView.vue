<template>
  <div class="report-view-page">
    <div v-if="loading" class="loading-state">
      <div class="loading-spinner"></div>
      <p>正在加载报告...</p>
    </div>
    
    <div v-else-if="error" class="error-state">
      <h2>加载失败</h2>
      <p>{{ error }}</p>
      <button class="btn-primary" @click="goBack">返回</button>
    </div>
    
    <div v-else-if="report">
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
      <div class="floating-actions">
        <button class="action-btn" @click="copyLink" title="复制链接">
          <i class="fas fa-link"></i>
        </button>
        <button class="action-btn" @click="exportReport" title="导出">
          <i class="fas fa-download"></i>
        </button>
      </div>
      <div v-if="copySuccess" class="copy-toast">
        <i class="fas fa-check"></i> 链接已复制
      </div>
    </div>
    
    <div v-else class="empty-state">
      <h2>未找到报告</h2>
      <p>请提供有效的报告ID</p>
      <button class="btn-primary" @click="goToHistory">查看历史报告</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import TaskReportPanel from '../components/report/TaskReportPanel.vue'
import { reportsApi } from '../utils/api'

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const error = ref('')
const report = ref<any>(null)
const isEditingReport = ref(false)
const isEditingConclusion = ref(false)
const copySuccess = ref(false)

const analysisContent = computed(() => {
  return report.value?.summary?.analysisConclusion || report.value?.analysisConclusion || report.value?.conclusion || ''
})

const reportTables = computed(() => {
  return report.value?.summary?.tables || []
})

const loadReport = async (reportId: string) => {
  loading.value = true
  error.value = ''
  
  try {
    const response = await reportsApi.getOne(reportId)
    if (response) {
      report.value = response
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
    await reportsApi.update(report.value.id, {
      title: report.value.title || report.value.name,
      description: report.value.description
    })
    isEditingReport.value = false
  } catch (e) {
    console.error('保存报告失败:', e)
  }
}

const cancelEditReport = () => {
  isEditingReport.value = false
}

const toggleEditConclusion = () => {
  isEditingConclusion.value = !isEditingConclusion.value
}

const saveConclusion = async (content: string) => {
  if (!report.value) return
  try {
    const summary = {
      ...report.value.summary,
      analysisConclusion: content
    }
    await reportsApi.update(report.value.id, { summary })
    report.value.summary = summary
    report.value.conclusion = content
    isEditingConclusion.value = false
  } catch (e) {
    console.error('保存结论失败:', e)
  }
}

const cancelEditConclusion = () => {
  isEditingConclusion.value = false
}

const copyLink = async () => {
  try {
    await navigator.clipboard.writeText(window.location.href)
    copySuccess.value = true
    setTimeout(() => { copySuccess.value = false }, 2000)
  } catch (e) {
    console.error('复制失败:', e)
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
  }
}

const goBack = () => router.back()
const goToHistory = () => router.push('/history-reports')

onMounted(() => {
  const reportId = route.params.id as string || route.query.id as string
  if (reportId) {
    loadReport(reportId)
  } else {
    loading.value = false
  }
})
</script>

<style scoped>
.report-view-page {
  min-height: 100vh;
  background: #fafafa;
}

.loading-state,
.error-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  text-align: center;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #e2e8f0;
  border-top-color: #1677FF;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 16px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-state p,
.error-state p,
.empty-state p {
  color: #64748b;
  margin: 8px 0 24px 0;
}

.error-state h2,
.empty-state h2 {
  font-size: 20px;
  font-weight: 600;
  color: #1e293b;
  margin: 0;
}

.btn-primary {
  background: #1677FF;
  color: white;
  border: none;
  padding: 10px 24px;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.btn-primary:hover {
  background: #0958D9;
}

.floating-actions {
  position: fixed;
  right: 24px;
  bottom: 24px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  z-index: 100;
}

.action-btn {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: white;
  border: none;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s ease;
}

.action-btn:hover {
  background: #1677FF;
  color: white;
}

.copy-toast {
  position: fixed;
  bottom: 80px;
  right: 24px;
  background: #1e293b;
  color: white;
  padding: 10px 16px;
  border-radius: 8px;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
  animation: fadeIn 0.2s ease;
  z-index: 1000;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
