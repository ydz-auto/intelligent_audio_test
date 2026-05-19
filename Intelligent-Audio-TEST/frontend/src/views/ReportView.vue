<template>
  <div class="report-view-page">
    <!-- Toast 提示 -->
    <div v-if="toast" class="toast-container" :class="`toast-${toast.type}`">
      <i :class="toast.type === 'success' ? 'fas fa-check-circle' : toast.type === 'error' ? 'fas fa-exclamation-circle' : toast.type === 'warning' ? 'fas fa-exclamation-triangle' : 'fas fa-info-circle'"></i>
      <span>{{ toast.message }}</span>
    </div>

    <!-- 返回按钮 -->
    <!-- <div class="back-section">
      <button class="btn btn-secondary" @click="goBack">
        <i class="fas fa-arrow-left"></i> 返回历史报告
      </button>
    </div> -->

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
    <section class="comparison-report-container" v-else-if="report && isComparisonType">
      <div class="comparison-header">
        <h3 class="comparison-title">{{ report.type === 'secondaryComparison' ? '二次对比报告' : '任务对比报告' }}</h3>
        <p class="comparison-subtitle">
          {{ report.type === 'secondaryComparison' 
            ? '深度分析对比报告的二次对比，帮助您更深入地了解性能变化趋势和关键差异点。'
            : '对比分析所选任务的执行情况和结果，帮助您识别系统性能瓶颈和质量问题，为后续优化提供依据。' }}
        </p>
      </div>
      
      <!-- 报告保存区域 -->
      <div class="report-save-section analysis-conclusion-card">
        <div class="analysis-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" stroke="#1890ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" stroke="#1890ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M10 2v20" stroke="#1890ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M14 2v20" stroke="#1890ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        
        <div class="analysis-content">
          <div class="analysis-header">
            <h4 class="analysis-title">{{ reportName || report.name || '对比报告' }}</h4>
            <div class="analysis-status">
              <span class="status-dot"></span>
              {{ report.status === 'draft' ? '草稿' : '已发布' }}
            </div>
          </div>
          
          <div v-if="!isEditingReport" class="analysis-text">
            <div>{{ report.description || '请输入报告描述' }}</div>
          </div>
          
          <div v-else class="analysis-edit">
            <div class="edit-field">
              <label for="report-name">报告名称</label>
              <input type="text" id="report-name" placeholder="请输入报告名称" v-model="reportName">
            </div>
            <div class="edit-field">
              <label for="report-description">报告描述</label>
              <textarea id="report-description" placeholder="请输入报告描述" rows="3" v-model="report.description"></textarea>
            </div>
          </div>
          
          <div class="analysis-actions">
            <button v-if="!isEditingReport" class="btn btn-primary" @click="toggleEditReport">
              <i class="fas fa-edit"></i> 编辑
            </button>
            <template v-else>
              <button class="btn btn-primary" @click="saveReport">
                <i class="fas fa-save"></i> 保存
              </button>
              <button class="btn btn-secondary" @click="cancelEditReport">
                <i class="fas fa-times"></i> 取消
              </button>
            </template>
          </div>
        </div>
      </div>
      
      <!-- 设备/API选择器 -->
      <div class="comparison-selectors">
        <h4 class="selector-title">
          <i class="fas fa-list"></i> 选择要对比的设备和API
        </h4>
        <div class="selector-content">
          <div id="unified-selector">
            <div v-for="device in reportService.devices.value" :key="device.id"
                 class="device-select-item" :class="{ 'selected': device.selected, 'api-item': device.type === 'API' }"
                 @click="reportService.toggleDeviceSelection(device.id)"
                 role="button" tabindex="0"
                 @keydown.enter.prevent="reportService.toggleDeviceSelection(device.id)"
                 @keydown.space.prevent="reportService.toggleDeviceSelection(device.id)">
              <div class="device-icon-wrapper">
                <i :class="device.type === '设备' ? 'fas fa-headphones' : 'fas fa-exchange-alt'"></i>
              </div>
              <div class="device-info">
                <span class="device-name">{{ device.name }}</span>
                <span class="device-type-tag">{{ device.type }}</span>
              </div>
              <div class="selection-indicator">
                <i class="fas fa-check-circle"></i>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <!-- 分析结论 -->
      <div class="analysis-conclusion-card">
        <div class="analysis-icon">
          <i class="fas fa-chart-line"></i>
        </div>
        <div class="analysis-content">
          <div class="analysis-header">
            <h4 class="analysis-title">分析结论</h4>
            <div class="analysis-status" :class="report.status">
              <span class="status-dot"></span>
              {{ report.status === 'draft' ? '草稿' : '已发布' }}
            </div>
          </div>
          <div v-if="!isEditingConclusion" class="analysis-text" v-html="sanitizedConclusion"></div>
          <div v-else class="analysis-edit">
            <textarea class="analysis-textarea" v-model="reportConclusion" placeholder="请输入分析结论..."></textarea>
          </div>
          <div class="analysis-actions">
            <button v-if="!isEditingConclusion" class="btn btn-primary" @click="toggleEditConclusion">
              <i class="fas fa-edit"></i> 编辑
            </button>
            <template v-else>
              <button class="btn btn-primary" @click="saveConclusion">
                <i class="fas fa-save"></i> 保存
              </button>
              <button class="btn btn-secondary" @click="cancelEditConclusion">
                <i class="fas fa-times"></i> 取消
              </button>
            </template>
          </div>
        </div>
      </div>
      
      <!-- 设备/API信息对比 -->
      <div class="comparison-section">
        <ComparisonTableComponent 
          title="设备/API信息对比"
          :columns="reportService.deviceApiColumns.value"
          :data="reportService.deviceApiComparisonData.value"
          :default-collapsed="true"
          :show-search="false"
        />
      </div>
      
      <!-- 用例执行数量对比 -->
      <div class="comparison-section">
        <ComparisonTableComponent 
          title="用例执行数量对比"
          :columns="reportService.caseExecutionColumns.value"
          :data="reportService.caseExecutionData.value"
          :default-collapsed="true"
          :show-search="false"
        />
      </div>
      
      <!-- 按用例分组对比 -->
      <div class="comparison-section">
        <CaseCategoryComparisonComponent :report-data="report" />
      </div>
      
      <!-- 按用例标签对比 -->
      <div class="comparison-section">
        <CaseTagComparisonComponent :report-data="report" />
      </div>
      
      <!-- 具体用例对比 -->
      <div class="comparison-section">
        <SpecificCaseComparisonComponent :report-data="report" />
      </div>
    </section>
    
    <div v-else class="empty-state">
      <h2>未找到报告</h2>
      <p>请提供有效的报告ID</p>
      <button class="btn-primary" @click="goBack">查看历史报告</button>
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
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { sanitizeConclusion } from '../utils/sanitize'
import TaskReportPanel from '../components/report/TaskReportPanel.vue'
import ComparisonTableComponent from '../components/report/ComparisonTableComponent.vue'
import CaseCategoryComparisonComponent from '../components/report/CaseCategoryComparisonComponent.vue'
import CaseTagComparisonComponent from '../components/report/CaseTagComparisonComponent.vue'
import SpecificCaseComparisonComponent from '../components/report/SpecificCaseComparisonComponent.vue'
import { reportsApi } from '../utils/api'
import reportService from '../services/reportService'

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
        summary: response.summary || { totalCases: 0, completedCases: 0, failedCases: 0, allMetrics: [], detailedResults: [] }
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

const goBack = () => router.push('/history-reports')

onMounted(() => {
  const reportId = route.params.id as string || route.query.id as string
  if (reportId) {
    loadReport(reportId)
  } else {
    loading.value = false
  }
})

onUnmounted(() => {
  reportService.comparisonReport.value = null
})
</script>

<style scoped>
@import '../assets/styles/main.css';

.report-view-page {
  min-height: 100vh;
}

.back-section {
  margin-bottom: 24px;
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

/* 对比报告样式 */
.comparison-report-container {
  margin-top: 24px;
  padding: 32px 24px;
}

.comparison-header {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 24px;
  background: linear-gradient(135deg, #fafafa 0%, #f5f5f5 100%);
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  margin-bottom: 24px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  align-items: center;
  text-align: center;
}

.comparison-title {
  margin: 0;
  font-size: 28px;
  font-weight: 700;
  color: #2c3e50;
  background: linear-gradient(135deg, #FF6A00 0%, #FF8C40 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.comparison-subtitle {
  margin: 0;
  font-size: 15px;
  color: #7f8c8d;
  line-height: 1.5;
  max-width: 600px;
}

.report-save-section,
.analysis-conclusion-card {
  background: linear-gradient(to right, #e6f7ff, #ffffff);
  border: 1px solid #91d5ff;
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 24px;
  display: flex;
  gap: 16px;
  align-items: flex-start;
  box-shadow: 0 2px 8px rgba(24, 144, 255, 0.1);
}

.analysis-icon {
  flex-shrink: 0;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
  background: white;
}

.analysis-content {
  flex: 1;
}

.analysis-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.analysis-title {
  margin: 0;
  color: #0050b3;
  font-size: 1.1rem;
  font-weight: 600;
}

.analysis-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 0.8rem;
  font-weight: 500;
  background-color: #f0f9ff;
  color: #0ea5e9;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: #0ea5e9;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(14, 165, 233, 0.7); }
  70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(14, 165, 233, 0); }
  100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(14, 165, 233, 0); }
}

.analysis-text {
  color: #333;
  line-height: 1.6;
  font-size: 0.95rem;
}

.analysis-edit {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.edit-field label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #475469;
}

.edit-field input,
.edit-field textarea,
.analysis-textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  font-size: 0.95rem;
  line-height: 1.6;
}

.analysis-actions {
  margin-top: 12px;
  display: flex;
  gap: 12px;
  justify-content: flex-start;
  align-items: center;
}

.comparison-selectors {
  margin-bottom: 24px;
}

.selector-title {
  margin-bottom: 16px;
  color: #333;
  font-size: 16px;
  font-weight: 600;
}

.selector-content {
  background: #ffffff;
  padding: 24px;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

#unified-selector {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.device-select-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 16px;
  border: 2px solid #e2e8f0;
  border-radius: 12px;
  background: white;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  width: 130px;
  height: 150px;
  position: relative;
  overflow: hidden;
}

.device-select-item:hover {
  transform: translateY(-4px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  border-color: #cbd5e1;
}

.device-select-item.selected {
  border-color: #FF6A00;
  background-color: #fffaf0;
}

.device-select-item.api-item.selected {
  border-color: #1677FF;
  background-color: #f0f7ff;
}

.device-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 54px;
  height: 54px;
  border-radius: 50%;
  background: #f8fafc;
  transition: all 0.3s ease;
}

.device-select-item.selected .device-icon-wrapper {
  background: rgba(255, 106, 0, 0.1);
}

.device-select-item.api-item.selected .device-icon-wrapper {
  background: rgba(22, 119, 255, 0.1);
}

.device-icon-wrapper i {
  font-size: 24px;
  color: #64748b;
}

.device-select-item.selected .device-icon-wrapper i {
  color: #FF6A00;
}

.device-select-item.api-item.selected .device-icon-wrapper i {
  color: #1677FF;
}

.device-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  width: 100%;
}

.device-name {
  font-size: 0.9rem;
  font-weight: 600;
  color: #1e293b;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  width: 100%;
}

.device-type-tag {
  font-size: 0.75rem;
  color: #64748b;
  padding: 2px 8px;
  background: #f1f5f9;
  border-radius: 10px;
}

.selection-indicator {
  position: absolute;
  top: 8px;
  right: 8px;
  opacity: 0;
  transform: scale(0.5);
  transition: all 0.3s ease;
}

.device-select-item.selected .selection-indicator {
  opacity: 1;
  transform: scale(1);
}

.selection-indicator i {
  font-size: 18px;
  color: #FF6A00;
}

.device-select-item.api-item.selected .selection-indicator i {
  color: #1677FF;
}

.comparison-section {
  margin-bottom: 24px;
}

.toast-container {
  position: fixed;
  top: 20px;
  right: 20px;
  padding: 12px 20px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 10px;
  z-index: 10000;
  animation: slideIn 0.3s ease;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.toast-container i {
  font-size: 1.2rem;
}

.toast-success {
  background-color: #f0fdf4;
  color: #16a34a;
  border: 1px solid #16a34a;
}

.toast-error {
  background-color: #fef2f2;
  color: #dc2626;
  border: 1px solid #dc2626;
}

.toast-warning {
  background-color: #fffbeb;
  color: #d97706;
  border: 1px solid #d97706;
}

.toast-info {
  background-color: #eff6ff;
  color: #2563eb;
  border: 1px solid #2563eb;
}

@keyframes slideIn {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}

.floating-actions {
  position: fixed !important;
  right: 32px;
  bottom: 32px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  z-index: 14000 !important;
}

.action-btn {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: linear-gradient(135deg, #1677FF 0%, #0958D9 100%);
  border: none;
  box-shadow: 0 4px 16px rgba(22, 119, 255, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  color: white;
  cursor: pointer;
  transition: all 0.25s ease;
}

.action-btn:hover {
  transform: scale(1.1);
  box-shadow: 0 6px 24px rgba(22, 119, 255, 0.5);
}

.action-btn:active {
  transform: scale(0.95);
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
