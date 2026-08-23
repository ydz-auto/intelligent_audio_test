<template>
  <div class="task-report-panel">
    <div class="report-hero">
      <div class="hero-content">
        <div class="hero-icon">
          <i class="fas fa-chart-bar"></i>
        </div>
        <h1 class="hero-title">{{ report.title || report.name || '任务报告' }}</h1>
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
        <div class="report-section" id="section-overview">
          <OverviewCardComponent :reportData="report" />
        </div>

        <div class="report-section" id="section-devices" v-if="hasDeviceOrApiStats">
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
        </div>

        <div class="report-section" id="section-analysis">
          <div class="section-header" @click="toggleAnalysisCollapse">
            <h3 class="section-title">分析结论</h3>
            <button class="collapse-btn" :class="{ collapsed: isAnalysisCollapsed }" title="折叠/展开">
              <i class="fas fa-chevron-up" v-if="isAnalysisCollapsed"></i>
              <i class="fas fa-chevron-down" v-else></i>
            </button>
          </div>
          <div class="analysis-content" v-if="!isAnalysisCollapsed">
            <div v-if="!localIsEditing" class="analysis-text" v-html="sanitizedAnalysisContent"></div>
            <div v-else class="analysis-edit">
              <textarea 
                v-model="editableConclusion" 
                placeholder="请输入分析结论..."
                class="analysis-textarea"
              ></textarea>
            </div>
            <div class="analysis-actions">
              <button v-if="!localIsEditing" class="btn-link" @click="startEdit">
                <i class="fas fa-edit"></i> 编辑
              </button>
              <template v-else>
                <button class="btn-primary" @click="saveLocalConclusion">保存</button>
                <button class="btn-secondary" @click="cancelLocalConclusion">取消</button>
              </template>
            </div>
          </div>
        </div>

        <div v-for="(table, idx) in tables" :key="idx" class="report-section">
          <ComparisonTableComponent
            :title="table.title"
            :columns="table.columns"
            :data="table.data"
            :defaultCollapsed="isExporting ? false : (table.defaultCollapsed !== false)"
          />
        </div>

        <div class="report-section" id="section-category">
          <CaseCategoryComparisonComponent :reportData="report" />
        </div>

        <div class="report-section" id="section-tag">
          <CaseTagComparisonComponent :reportData="report" />
        </div>

        <div class="report-section" id="section-case">
          <SpecificCaseComparisonComponent :reportData="report" />
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
import { ref, watch, computed, onMounted, onUnmounted, inject } from 'vue';
import { sanitizeConclusion } from '../../utils/sanitize';
import ComparisonTableComponent from './ComparisonTableComponent.vue'
import CaseCategoryComparisonComponent from './CaseCategoryComparisonComponent.vue'
import CaseTagComparisonComponent from './CaseTagComparisonComponent.vue'
import SpecificCaseComparisonComponent from './SpecificCaseComparisonComponent.vue'
import OverviewCardComponent from './OverviewCardComponent.vue'

// 导出模式：导出时展开所有折叠区块
const isExporting = inject('isExporting', ref(false))

const props = defineProps({
  report: { type: Object, required: true },
  isEditingReport: { type: Boolean, default: false },
  isEditingConclusion: { type: Boolean, default: false },
  analysisContent: { type: String, default: '' },
  tables: { type: Array, default: () => [] }
})

const emit = defineEmits(['toggle-edit', 'save-report', 'cancel-edit', 'toggle-conclusion-edit', 'save-conclusion', 'cancel-conclusion'])

const editableConclusion = ref('')
const localIsEditing = ref(false)
const isAnalysisCollapsed = ref(false)
const isDevicesCollapsed = ref(false)
const activeSection = ref('section-overview')
const progressHeight = ref('0%')

// 导出时强制展开所有折叠区块
watch(isExporting, (exporting) => {
  if (exporting) {
    isAnalysisCollapsed.value = false
    isDevicesCollapsed.value = false
  }
}, { immediate: true })

const toggleAnalysisCollapse = () => {
  isAnalysisCollapsed.value = !isAnalysisCollapsed.value
}

const toggleDevicesCollapse = () => {
  isDevicesCollapsed.value = !isDevicesCollapsed.value
}

const deviceStats = computed(() => {
  const stats = props.report?.summary?.deviceStats || props.report?.summary?.device_stats || []
  return Array.isArray(stats) ? stats : []
})

const apiStats = computed(() => {
  const stats = props.report?.summary?.apiStats || props.report?.summary?.api_stats || []
  return Array.isArray(stats) ? stats : []
})

const hasDeviceOrApiStats = computed(() => {
  return deviceStats.value.length > 0 || apiStats.value.length > 0
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

const formatMetricValue = (value) => {
  if (value === null || value === undefined) return '-'
  const num = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(num)) return String(value)
  return num.toFixed(2)
}

const formatMetricWithUnit = (value, metricName) => {
  const formattedValue = formatMetricValue(value)
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

const navItems = computed(() => {
  const items = [
    { id: 'section-overview', label: '概览' },
  ]
  if (hasDeviceOrApiStats.value) {
    items.push({ id: 'section-devices', label: '设备与API' })
  }
  items.push(
    { id: 'section-analysis', label: '分析结论' },
    { id: 'section-category', label: '用例分组' },
    { id: 'section-tag', label: '用例标签' },
    { id: 'section-case', label: '具体用例' },
  )
  return items
})

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
}

watch(() => props.analysisContent, (newVal) => {
  editableConclusion.value = newVal
}, { immediate: true })

const sanitizedAnalysisContent = computed(() => {
  return sanitizeConclusion(props.analysisContent);
});

const startEdit = () => {
  editableConclusion.value = props.analysisContent
  localIsEditing.value = true
}

const saveLocalConclusion = () => {
  emit('save-conclusion', editableConclusion.value)
  localIsEditing.value = false
}

const cancelLocalConclusion = () => {
  editableConclusion.value = props.analysisContent
  localIsEditing.value = false
  emit('cancel-conclusion')
}

const scrollToSection = (sectionId) => {
  activeSection.value = sectionId
  const element = document.getElementById(sectionId)
  if (element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

const handleScroll = () => {
  const sections = navItems.value.map(item => ({
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
.task-report-panel {
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
  background: rgba(22, 119, 255, 0.1);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  color: #1677FF;
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
