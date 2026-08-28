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
            {{ formatDate(report.created_at) }}
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
                    <span class="stat-value">{{ device.total_cases || 0 }} 个</span>
                  </div>
                  <div class="stat-row">
                    <span class="stat-label">完成数</span>
                    <span class="stat-value success">{{ device.completed_cases || 0 }} 个</span>
                  </div>
                  <div class="stat-row">
                    <span class="stat-label">失败数</span>
                    <span class="stat-value danger">{{ device.failed_cases || 0 }} 个</span>
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
                    <span class="stat-value">{{ api.total_cases || 0 }} 个</span>
                  </div>
                  <div class="stat-row">
                    <span class="stat-label">完成数</span>
                    <span class="stat-value success">{{ api.completed_cases || 0 }} 个</span>
                  </div>
                  <div class="stat-row">
                    <span class="stat-label">失败数</span>
                    <span class="stat-value danger">{{ api.failed_cases || 0 }} 个</span>
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
import ComparisonTableComponent from './ComparisonTableComponent.vue'
import CaseCategoryComparisonComponent from './CaseCategoryComparisonComponent.vue'
import CaseTagComparisonComponent from './CaseTagComparisonComponent.vue'
import SpecificCaseComparisonComponent from './SpecificCaseComparisonComponent.vue'
import OverviewCardComponent from './OverviewCardComponent.vue'
import { useTaskReportPanel } from './TaskReportPanel'

const props = defineProps({
  report: { type: Object, required: true },
  isEditingReport: { type: Boolean, default: false },
  isEditingConclusion: { type: Boolean, default: false },
  analysisContent: { type: String, default: '' },
  tables: { type: Array, default: () => [] }
})

const emit = defineEmits(['toggle-edit', 'save-report', 'cancel-edit', 'toggle-conclusion-edit', 'save-conclusion', 'cancel-conclusion'])

const {
  report,
  tables,
  editableConclusion,
  localIsEditing,
  isAnalysisCollapsed,
  isDevicesCollapsed,
  isExporting,
  activeSection,
  progressHeight,
  toggleAnalysisCollapse,
  toggleDevicesCollapse,
  deviceStats,
  apiStats,
  hasDeviceOrApiStats,
  getSuccessRateClass,
  formatPercent,
  formatMetricWithUnit,
  navItems,
  formatDate,
  sanitizedAnalysisContent,
  startEdit,
  saveLocalConclusion,
  cancelLocalConclusion,
  scrollToSection
} = useTaskReportPanel(props, emit)
</script>

<style scoped>
@import './TaskReportPanel.css';
</style>
