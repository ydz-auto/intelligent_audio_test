<template>
  <div class="comparison-report-panel">
    <div class="report-hero">
      <div class="hero-content">
        <div class="hero-icon">
          <i class="fas fa-exchange-alt"></i>
        </div>
        <h1 class="hero-title">{{ reportName || report.name || (isSecondaryComparison ? '二次对比报告' : '任务对比报告') }}</h1>
        <p class="hero-subtitle" v-if="report.description">{{ report.description }}</p>
        <div class="hero-meta">
          <span class="meta-item">
            <i class="fas fa-calendar-alt"></i>
            {{ formatDate(report.createdAt || report.created_at) }}
          </span>
          <span class="meta-item status" :class="report.status">
            <i class="fas fa-circle"></i>
            {{ report.status === 'draft' ? '草稿' : '已发布' }}
          </span>
        </div>
      </div>
    </div>

    <div class="report-layout">
      <div class="report-main">
        <!-- 概览 -->
        <div class="report-section" id="section-overview">
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
                  <input type="text" id="report-name" placeholder="请输入报告名称" v-model="editableName">
                </div>
                <div class="edit-field">
                  <label for="report-description">报告描述</label>
                  <textarea id="report-description" placeholder="请输入报告描述" rows="3" v-model="editableDescription"></textarea>
                </div>
              </div>
              <div class="analysis-actions">
                <button v-if="!isEditingReport" class="btn btn-primary" @click="startEditReport">
                  <i class="fas fa-edit"></i> 编辑
                </button>
                <template v-else>
                  <button class="btn btn-primary" @click="saveReportEdit">
                    <i class="fas fa-save"></i> 保存
                  </button>
                  <button class="btn btn-secondary" @click="cancelReportEdit">
                    <i class="fas fa-times"></i> 取消
                  </button>
                </template>
              </div>
            </div>
          </div>
          <OverviewCardComponent :reportData="report" />
        </div>

        <!-- 设备与API -->
        <div class="report-section" id="section-devices">
          <!-- 设备与API统计（与任务报告一致） -->
          <div class="section-header" @click="toggleDevicesCollapse">
            <h3 class="section-title">
              <i class="fas fa-microchip"></i> 设备与API统计
            </h3>
            <button class="collapse-btn" :class="{ collapsed: isDevicesCollapsed }" title="折叠/展开">
              <i class="fas fa-chevron-up" v-if="isDevicesCollapsed"></i>
              <i class="fas fa-chevron-down" v-else></i>
            </button>
          </div>
          <div class="devices-content" v-if="!isDevicesCollapsed">
            <div class="device-cards-container">
              <div v-for="device in deviceStats" :key="device.id" class="device-stat-card">
                <div class="device-card-header">
                  <div class="device-icon">
                    <i class="fas fa-headphones"></i>
                  </div>
                  <div class="device-info">
                    <span class="device-name">{{ device.name }}</span>
                    <span class="device-model">{{ device.model || device.type || '设备' }}</span>
                  </div>
                  <span class="device-status" :class="device.status">{{ device.status === 'online' ? '在线' : '离线' }}</span>
                </div>
                <div class="device-card-body">
                  <div class="stat-row">
                    <span class="stat-label">总用例数</span>
                    <span class="stat-value">{{ device.totalCases || 0 }} 个</span>
                  </div>
                  <div class="stat-row">
                    <span class="stat-label">完成数</span>
                    <span class="stat-value success">{{ device.completedCases || 0 }} 个</span>
                  </div>
                  <div class="stat-row">
                    <span class="stat-label">失败数</span>
                    <span class="stat-value danger">{{ device.failedCases || 0 }} 个</span>
                  </div>
                  <div class="stat-row">
                    <span class="stat-label">成功率</span>
                    <span class="stat-value" :class="getSuccessRateClass(device.successRate)">{{ formatPercent(device.successRate) }}</span>
                  </div>
                </div>
                <div class="device-card-footer" v-if="device.metrics && Object.keys(device.metrics).length > 0">
                  <div class="metrics-grid">
                    <div v-for="(value, key) in device.metrics" :key="key" class="metric-item">
                      <span class="metric-name">{{ key }}</span>
                      <span class="metric-value">{{ formatMetricWithUnit(value, key) }}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div v-for="api in apiStats" :key="api.id" class="api-stat-card">
                <div class="api-card-header">
                  <div class="api-icon">
                    <i class="fas fa-exchange-alt"></i>
                  </div>
                  <div class="api-info">
                    <span class="api-name">{{ api.name }}</span>
                    <span class="api-vendor">API</span>
                  </div>
                  <span class="api-status" :class="api.status">{{ api.status === 'active' ? '活跃' : '离线' }}</span>
                </div>
                <div class="api-card-body">
                  <div class="stat-row">
                    <span class="stat-label">总用例数</span>
                    <span class="stat-value">{{ api.totalCases || 0 }} 个</span>
                  </div>
                  <div class="stat-row">
                    <span class="stat-label">完成数</span>
                    <span class="stat-value success">{{ api.completedCases || 0 }} 个</span>
                  </div>
                  <div class="stat-row">
                    <span class="stat-label">失败数</span>
                    <span class="stat-value danger">{{ api.failedCases || 0 }} 个</span>
                  </div>
                  <div class="stat-row">
                    <span class="stat-label">成功率</span>
                    <span class="stat-value" :class="getSuccessRateClass(api.successRate)">{{ formatPercent(api.successRate) }}</span>
                  </div>
                </div>
                <div class="api-card-footer" v-if="api.metrics && Object.keys(api.metrics).length > 0">
                  <div class="metrics-grid">
                    <div v-for="(value, key) in api.metrics" :key="key" class="metric-item">
                      <span class="metric-name">{{ key }}</span>
                      <span class="metric-value">{{ formatMetricWithUnit(value, key) }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 设备/API选择器 -->
          <div class="section-header" style="margin-top: 24px;">
            <h3 class="section-title">
              <i class="fas fa-list"></i> 选择要对比的设备和API
            </h3>
          </div>
          <div class="selector-content">
            <div id="unified-selector">
              <div v-for="device in comparisonDevices" :key="device.id"
                   class="device-select-item" :class="{ 'selected': device.selected, 'api-item': device.type === 'API' }"
                   @click="toggleDevice(device.id)"
                   role="button" tabindex="0"
                   @keydown.enter.prevent="toggleDevice(device.id)"
                   @keydown.space.prevent="toggleDevice(device.id)">
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

          <div class="comparison-section">
            <ComparisonTableComponent
              title="设备/API信息对比"
              :columns="deviceApiColumns"
              :data="deviceApiComparisonData"
              :default-collapsed="true"
              :show-search="false"
            />
          </div>

          <div class="comparison-section">
            <ComparisonTableComponent
              title="用例执行数量对比"
              :columns="caseExecutionColumns"
              :data="caseExecutionData"
              :default-collapsed="true"
              :show-search="false"
            />
          </div>
        </div>

        <!-- 分析结论 -->
        <div class="report-section" id="section-analysis">
          <div class="section-header" @click="toggleAnalysisCollapse">
            <h3 class="section-title">
              <i class="fas fa-chart-line"></i> 分析结论
            </h3>
            <button class="collapse-btn" :class="{ collapsed: isAnalysisCollapsed }" title="折叠/展开">
              <i class="fas fa-chevron-up" v-if="isAnalysisCollapsed"></i>
              <i class="fas fa-chevron-down" v-else></i>
            </button>
          </div>
          <div class="analysis-content" v-if="!isAnalysisCollapsed">
            <div v-if="!isEditingConclusion" class="analysis-text" v-html="sanitizedAnalysisContent"></div>
            <div v-else class="analysis-edit">
              <textarea class="analysis-textarea" v-model="editableConclusion" placeholder="请输入分析结论..."></textarea>
            </div>
            <div class="analysis-actions">
              <button v-if="!isEditingConclusion" class="btn-link" @click="startEditConclusion">
                <i class="fas fa-edit"></i> 编辑
              </button>
              <template v-else>
                <button class="btn-primary" @click="saveConclusionEdit">保存</button>
                <button class="btn-secondary" @click="cancelConclusionEdit">取消</button>
              </template>
            </div>
          </div>
        </div>

        <!-- 按用例分组对比 -->
        <div class="report-section" id="section-category">
          <CaseCategoryComparisonComponent :report-data="report" />
        </div>

        <!-- 按用例标签对比 -->
        <div class="report-section" id="section-tag">
          <CaseTagComparisonComponent :report-data="report" />
        </div>

        <!-- 具体用例对比 -->
        <div class="report-section" id="section-case">
          <SpecificCaseComparisonComponent :report-data="report" />
        </div>
      </div>

      <div class="report-nav">
        <nav class="nav-menu">
          <a
            v-for="item in navItems"
            :key="item.id"
            :href="'#' + item.id"
            :class="['nav-item', { active: activeSection === item.id }]"
            @click.prevent="scrollToSection(item.id)"
          >
            <span class="nav-dot"></span>
            <span class="nav-label">{{ item.label }}</span>
          </a>
        </nav>
        <div class="nav-progress">
          <div class="progress-fill" :style="{ height: progressHeight }"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { sanitizeConclusion } from '../../utils/sanitize';
import ComparisonTableComponent from './ComparisonTableComponent.vue';
import CaseCategoryComparisonComponent from './CaseCategoryComparisonComponent.vue';
import CaseTagComparisonComponent from './CaseTagComparisonComponent.vue';
import SpecificCaseComparisonComponent from './SpecificCaseComparisonComponent.vue';
import OverviewCardComponent from './OverviewCardComponent.vue';

const props = defineProps({
  report: { type: Object, required: true },
  reportName: { type: String, default: '' },
  isEditingReport: { type: Boolean, default: false },
  isEditingConclusion: { type: Boolean, default: false },
  analysisContent: { type: String, default: '' },
  comparisonDevices: { type: Array, default: () => [] },
  deviceApiColumns: { type: Array, default: () => [] },
  deviceApiComparisonData: { type: Array, default: () => [] },
  caseExecutionColumns: { type: Array, default: () => [] },
  caseExecutionData: { type: Array, default: () => [] }
});

const emit = defineEmits([
  'toggle-edit', 'save-report', 'cancel-edit',
  'toggle-conclusion-edit', 'save-conclusion', 'cancel-conclusion',
  'toggle-device'
]);

const isSecondaryComparison = computed(() => {
  const type = props.report?.type
  return type === 'secondaryComparison' || type === 'secondary_comparison'
})

const editableName = ref('')
const editableDescription = ref('')
const editableConclusion = ref('')
const isAnalysisCollapsed = ref(false)
const isDevicesCollapsed = ref(false)
const activeSection = ref('section-overview')
const progressHeight = ref('0%')

const deviceStats = computed(() => {
  const stats = props.report?.summary?.deviceStats || props.report?.summary?.device_stats || []
  return Array.isArray(stats) ? stats : []
})

const apiStats = computed(() => {
  const stats = props.report?.summary?.apiStats || props.report?.summary?.api_stats || []
  return Array.isArray(stats) ? stats : []
})

const allMetrics = computed(() => {
  const metrics = props.report?.summary?.allMetrics || props.report?.summary?.all_metrics || []
  return Array.isArray(metrics) ? metrics : []
})

const getMetricUnit = (metricName) => {
  const metric = allMetrics.value.find(m => m.name === metricName)
  return metric?.unit || ''
}

const formatPercent = (value) => {
  if (value === null || value === undefined) return '0%'
  const num = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(num)) return '0%'
  return `${num.toFixed(1)}%`
}

const getMetricDecimalPlaces = (metricName) => {
  const metric = allMetrics.value.find(m => m.name === metricName)
  const dp = metric?.decimal_places ?? metric?.decimalPlaces ?? 2
  return dp
}

const formatMetricValue = (value, metricName) => {
  if (value === null || value === undefined) return '-'
  const num = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(num)) return String(value)
  const dp = metricName != null ? getMetricDecimalPlaces(metricName) : 2
  return num.toFixed(dp)
}

const formatMetricWithUnit = (value, metricName) => {
  const formattedValue = formatMetricValue(value, metricName)
  const unit = getMetricUnit(metricName)
  return unit ? `${formattedValue}${unit}` : formattedValue
}

const getSuccessRateClass = (rate) => {
  if (rate === null || rate === undefined) return ''
  const num = typeof rate === 'number' ? rate : Number(rate)
  if (!Number.isFinite(num)) return ''
  if (num >= 80) return 'success'
  if (num >= 50) return 'warning'
  return 'danger'
}

const toggleDevicesCollapse = () => {
  isDevicesCollapsed.value = !isDevicesCollapsed.value
}

watch(() => props.reportName, (val) => {
  editableName.value = val || props.report?.name || ''
}, { immediate: true })

watch(() => props.report?.description, (val) => {
  editableDescription.value = val || ''
}, { immediate: true })

watch(() => props.analysisContent, (val) => {
  editableConclusion.value = val
}, { immediate: true })

const sanitizedAnalysisContent = computed(() => {
  return sanitizeConclusion(props.analysisContent);
});

const toggleAnalysisCollapse = () => {
  isAnalysisCollapsed.value = !isAnalysisCollapsed.value
}

const startEditReport = () => {
  editableName.value = props.reportName || props.report?.name || ''
  editableDescription.value = props.report?.description || ''
  emit('toggle-edit')
}

const saveReportEdit = () => {
  if (props.report) {
    props.report.name = editableName.value
    props.report.description = editableDescription.value
  }
  emit('save-report', { name: editableName.value, description: editableDescription.value })
}

const cancelReportEdit = () => {
  emit('cancel-edit')
}

const startEditConclusion = () => {
  editableConclusion.value = props.analysisContent
  emit('toggle-conclusion-edit')
}

const saveConclusionEdit = () => {
  emit('save-conclusion', editableConclusion.value)
}

const cancelConclusionEdit = () => {
  editableConclusion.value = props.analysisContent
  emit('cancel-conclusion')
}

const toggleDevice = (deviceId) => {
  emit('toggle-device', deviceId)
}

const navItems = [
  { id: 'section-overview', label: '概览' },
  { id: 'section-devices', label: '设备与API' },
  { id: 'section-analysis', label: '分析结论' },
  { id: 'section-category', label: '用例分组' },
  { id: 'section-tag', label: '用例标签' },
  { id: 'section-case', label: '具体用例' }
]

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
}

const scrollToSection = (sectionId) => {
  activeSection.value = sectionId
  const element = document.getElementById(sectionId)
  if (element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

const handleScroll = () => {
  const sections = navItems.map(item => ({
    id: item.id,
    element: document.getElementById(item.id)
  }))

  let currentSection = 'section-overview'
  const scrollPosition = window.scrollY + 150

  for (let i = sections.length - 1; i >= 0; i--) {
    const section = sections[i]
    if (section.element) {
      const sectionTop = section.element.offsetTop
      if (scrollPosition >= sectionTop) {
        currentSection = section.id
        break
      }
    }
  }

  activeSection.value = currentSection

  const docHeight = document.documentElement.scrollHeight - window.innerHeight
  const scrollPercent = (window.scrollY / docHeight) * 100
  progressHeight.value = Math.min(100, Math.max(0, scrollPercent)) + '%'
}

onMounted(() => {
  window.addEventListener('scroll', handleScroll)
  handleScroll()
})

onUnmounted(() => {
  window.removeEventListener('scroll', handleScroll)
})
</script>

<style scoped>
.comparison-report-panel {
  width: 100%;
  min-height: auto;
  background: white;
}

.report-hero {
  position: relative;
  margin: 0;
  width: 100%;
  background: linear-gradient(180deg, #FFF8F0 0%, #FFFFFF 100%);
  padding: 32px 24px 0px;
  text-align: center;
  border-radius: 0;
}

.hero-content {
  position: relative;
  z-index: 2;
  max-width: 800px;
  margin: 0 auto;
}

.hero-icon {
  width: 48px;
  height: 48px;
  margin: 0 auto 16px;
  background: rgba(255, 106, 0, 0.1);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  color: #FF6A00;
}

.hero-title {
  font-size: 28px;
  font-weight: 700;
  color: #1e293b;
  margin: 0 0 12px 0;
}

.hero-subtitle {
  font-size: 16px;
  color: #64748b;
  line-height: 1.8;
  margin: 0 0 24px 0;
}

.hero-meta {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 24px;
}

.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: #64748b;
}

.meta-item i {
  font-size: 12px;
}

.meta-item.status {
  padding: 4px 12px;
  border-radius: 12px;
  background: rgba(82, 196, 26, 0.1);
  color: #52C41A;
}

.meta-item.status.draft {
  background: rgba(250, 173, 20, 0.1);
  color: #FAAD14;
}

.meta-item.status i {
  font-size: 6px;
}

.report-layout {
  display: flex;
  max-width: 1200px;
  margin: 0 auto;
  gap: 32px;
  padding: 32px 24px;
}

.report-main {
  flex: 1;
  min-width: 0;
}

.report-nav {
  width: 140px;
  flex-shrink: 0;
  position: sticky;
  top: 80px;
  height: fit-content;
  align-self: flex-start;
  padding-bottom: 8px;
}

.nav-menu {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 6px;
  background: transparent;
  background-clip: padding-box;
  color: #64748b;
  font-size: 13px;
  transition: all 0.2s ease;
  width: 90%;
  box-sizing: border-box;
  text-decoration: none;
}

.nav-item:hover {
  background: #f1f5f9;
  color: #334155;
}

.nav-item.active {
  background: rgba(255, 106, 0, 0.1);
  color: #FF6A00;
  font-weight: 500;
}

.nav-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #cbd5e1;
  flex-shrink: 0;
}

.nav-item.active .nav-dot {
  background: #FF6A00;
}

.nav-label {
  flex: 1;
}

.nav-progress {
  position: absolute;
  left: 18px;
  top: 8px;
  bottom: 8px;
  width: 2px;
  background: #e2e8f0;
}

.progress-fill {
  width: 100%;
  background: #FF6A00;
  transition: height 0.15s ease;
}

.report-section {
  margin-bottom: 32px;
}

.section-header {
  margin-bottom: 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  padding: var(--spacing-lg);
  width: 100%;
  box-sizing: border-box;
}

.section-title {
  font-size: var(--font-size-xxl);
  font-weight: var(--font-weight-bold);
  color: var(--text-primary);
  margin: 0;
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.collapse-btn {
  background: transparent;
  border: none;
  color: #64748b;
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.collapse-btn:hover {
  color: #334155;
  background: #f1f5f9;
  border-radius: 4px;
}

.collapse-btn.collapsed {
  transform: rotate(-90deg);
}

.analysis-content {
  padding: 0;
}

.analysis-text {
  font-size: 15px;
  color: #475569;
  line-height: 1.8;
  min-height: 80px;
}

.analysis-edit {
  display: flex;
  flex-direction: column;
}

.analysis-textarea {
  width: 100%;
  min-height: 150px;
  padding: 16px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.6;
  resize: vertical;
  transition: border-color 0.2s ease;
}

.analysis-textarea:focus {
  outline: none;
  border-color: #1677FF;
}

.analysis-actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}

.btn-link {
  background: none;
  border: none;
  color: #1677FF;
  font-size: 14px;
  cursor: pointer;
  padding: 8px 16px;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: background 0.2s ease;
}

.btn-link:hover {
  background: rgba(22, 119, 255, 0.1);
}

.btn-primary {
  background: #1677FF;
  color: white;
  border: none;
  padding: 8px 20px;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.2s ease;
}

.btn-primary:hover {
  background: #0958D9;
}

.btn-secondary {
  background: #f1f5f9;
  color: #64748b;
  border: none;
  padding: 8px 20px;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.2s ease;
}

.btn-secondary:hover {
  background: #e2e8f0;
}

@media (max-width: 900px) {
  .report-layout {
    flex-direction: column;
    gap: 20px;
  }

  .report-nav {
    width: 100%;
    position: relative;
    top: 0;
  }

  .nav-menu {
    flex-direction: row;
    flex-wrap: wrap;
    gap: 6px;
  }

  .nav-progress {
    display: none;
  }
}

/* 对比报告专属样式 */
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

.edit-field label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #475469;
}

.edit-field input,
.edit-field textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  font-size: 0.95rem;
  line-height: 1.6;
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
  margin-top: 24px;
}

/* 设备与API统计卡片（与任务报告一致） */
.devices-content {
  animation: slideDown 0.3s ease-out;
  padding: var(--spacing-lg);
}

.device-cards-container {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  padding: 0;
}

.device-stat-card,
.api-stat-card {
  flex: 1;
  min-width: 280px;
  max-width: 400px;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  overflow: hidden;
  transition: all 0.3s ease;
}

.device-stat-card:hover,
.api-stat-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transform: translateY(-2px);
}

.device-card-header,
.api-card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background: #ffffff;
  border-bottom: 1px solid #e2e8f0;
}

.api-card-header {
  background: #ffffff;
}

.device-icon,
.api-icon {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
}

.device-icon {
  background: rgba(255, 106, 0, 0.1);
  color: #FF6A00;
}

.api-icon {
  background: rgba(22, 119, 255, 0.1);
  color: #1677FF;
}

.device-info,
.api-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.device-name,
.api-name {
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
}

.device-model,
.api-vendor {
  font-size: 12px;
  color: #64748b;
}

.device-status,
.api-status {
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.device-status.online,
.api-status.active {
  background: rgba(82, 196, 26, 0.1);
  color: #52C41A;
}

.device-status.offline,
.api-status.inactive {
  background: rgba(250, 173, 20, 0.1);
  color: #FAAD14;
}

.device-card-body,
.api-card-body {
  padding: 16px;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid #f1f5f9;
}

.stat-row:last-child {
  border-bottom: none;
}

.stat-label {
  font-size: 14px;
  color: #64748b;
}

.stat-value {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
}

.stat-value.success {
  color: #52C41A;
}

.stat-value.warning {
  color: #FAAD14;
}

.stat-value.danger {
  color: #F5222D;
}

.device-card-footer,
.api-card-footer {
  padding: 12px 16px;
  background: #ffffff;
  border-top: 1px solid #e2e8f0;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px;
}

.metric-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.metric-name {
  font-size: 12px;
  color: #64748b;
}

.metric-value {
  font-size: 14px;
  font-weight: 600;
  color: #1677FF;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
