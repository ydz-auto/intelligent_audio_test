<template>
  <section class="rv-comparison-report-container">
    <div class="rv-comparison-header">
      <h3 class="rv-comparison-title">{{ isSecondaryType ? '二次对比报告' : '任务对比报告' }}</h3>
      <p class="rv-comparison-subtitle">
        {{ isSecondaryType
          ? '深度分析对比报告的二次对比，帮助您更深入地了解性能变化趋势和关键差异点。'
          : '对比分析所选任务的执行情况和结果，帮助您识别系统性能瓶颈和质量问题，为后续优化提供依据。' }}
      </p>
    </div>

    <!-- 报告保存区域 -->
    <div class="report-save-section rv-analysis-conclusion-card">
      <div class="rv-analysis-icon">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" stroke="var(--secondary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" stroke="var(--secondary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M10 2v20" stroke="var(--secondary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M14 2v20" stroke="var(--secondary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>

      <div class="rv-analysis-content">
        <div class="rv-analysis-header">
          <h4 class="rv-analysis-title">{{ reportName || report.name || '对比报告' }}</h4>
          <div class="rv-analysis-status">
            <span class="rv-status-dot"></span>
            {{ report.status === ReportStatus.DRAFT ? '草稿' : '已发布' }}
          </div>
        </div>

        <div v-if="!isEditingReport" class="rv-analysis-text">
          <div>{{ report.description || '请输入报告描述' }}</div>
        </div>

        <div v-else class="rv-analysis-edit">
          <div class="rv-edit-field">
            <label for="report-name">报告名称</label>
            <input type="text" id="report-name" placeholder="请输入报告名称" v-model="reportNameLocal">
          </div>
          <div class="rv-edit-field">
            <label for="report-description">报告描述</label>
            <textarea id="report-description" placeholder="请输入报告描述" rows="3" v-model="reportDescriptionLocal"></textarea>
          </div>
        </div>

        <div class="rv-analysis-actions">
          <button v-if="!isEditingReport" class="rv-btn rv-btn-primary" @click="emit('toggle-edit')">
            <i class="fas fa-edit"></i> 编辑
          </button>
          <template v-else>
            <button class="rv-btn rv-btn-primary" @click="emit('save-report')">
              <i class="fas fa-save"></i> 保存
            </button>
            <button class="rv-btn rv-btn-secondary" @click="emit('cancel-edit')">
              <i class="fas fa-times"></i> 取消
            </button>
          </template>
        </div>
      </div>
    </div>

    <!-- 设备/API选择器（基线具备折叠头：标题行可点击折叠/展开选择区） -->
    <div class="rv-comparison-selectors">
      <div
        class="rv-selector-header"
        role="button"
        tabindex="0"
        :aria-expanded="!isDevicesCollapsed"
        @click="toggleDevicesCollapse"
        @keydown.enter.prevent="toggleDevicesCollapse"
        @keydown.space.prevent="toggleDevicesCollapse"
      >
        <h4 class="rv-selector-title">
          <i class="fas fa-list"></i> 选择要对比的设备和API
        </h4>
        <button class="rv-collapse-btn" :class="{ collapsed: isDevicesCollapsed }" title="折叠/展开" @click.stop="toggleDevicesCollapse">
          <i class="fas fa-chevron-up" v-if="isDevicesCollapsed"></i>
          <i class="fas fa-chevron-down" v-else></i>
        </button>
      </div>
      <div class="rv-selector-content" v-show="!isDevicesCollapsed">
        <div id="rv-unified-selector">
          <div
            v-for="device in comparisonDevices"
            :key="device.id"
            class="rv-device-select-item"
            :class="{ 'rv-selected': device.selected, 'rv-api-item': device.type === 'API' }"
            @click="toggleDeviceSelection(device.id)"
            role="button"
            tabindex="0"
            @keydown.enter.prevent="toggleDeviceSelection(device.id)"
            @keydown.space.prevent="toggleDeviceSelection(device.id)"
          >
            <div class="rv-device-icon-wrapper">
              <i :class="device.type === '设备' ? 'fas fa-headphones' : 'fas fa-exchange-alt'"></i>
            </div>
            <div class="rv-device-info">
              <span class="rv-device-name">{{ device.name }}</span>
              <span class="rv-device-type-tag">{{ device.type }}</span>
            </div>
            <div class="rv-selection-indicator">
              <i class="fas fa-check-circle"></i>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 分析结论 -->
    <div class="rv-analysis-conclusion-card">
      <div class="rv-analysis-icon">
        <i class="fas fa-chart-line"></i>
      </div>
      <div class="rv-analysis-content">
        <div class="rv-analysis-header">
          <h4 class="rv-analysis-title">分析结论</h4>
          <div class="rv-analysis-status" :class="`rv-${report.status}`">
            <span class="rv-status-dot"></span>
            {{ report.status === ReportStatus.DRAFT ? '草稿' : '已发布' }}
          </div>
        </div>
        <div v-if="!isEditingConclusion" class="rv-analysis-text" v-html="sanitizedConclusion"></div>
        <div v-else class="rv-analysis-edit">
          <textarea class="rv-analysis-textarea" v-model="reportConclusionLocal" placeholder="请输入分析结论..."></textarea>
        </div>
        <div class="rv-analysis-actions">
          <button v-if="!isEditingConclusion" class="rv-btn rv-btn-primary" @click="emit('toggle-conclusion-edit')">
            <i class="fas fa-edit"></i> 编辑
          </button>
          <template v-else>
            <button class="rv-btn rv-btn-primary" @click="emit('save-conclusion')">
              <i class="fas fa-save"></i> 保存
            </button>
            <button class="rv-btn rv-btn-secondary" @click="emit('cancel-conclusion')">
              <i class="fas fa-times"></i> 取消
            </button>
          </template>
        </div>
      </div>
    </div>

    <!-- 设备/API信息对比 -->
    <div class="rv-comparison-section">
      <ComparisonTableComponent
        title="设备/API信息对比"
        :columns="deviceApiColumns"
        :data="deviceApiComparisonData"
        :default-collapsed="true"
        :show-search="false"
      />
    </div>

    <!-- 用例执行数量对比 -->
    <div class="rv-comparison-section">
      <ComparisonTableComponent
        title="用例执行数量对比"
        :columns="caseExecutionColumns"
        :data="caseExecutionData"
        :default-collapsed="true"
        :show-search="false"
      />
    </div>

    <!-- 按用例分组对比 -->
    <div class="rv-comparison-section">
      <CaseCategoryComparisonComponent :report-data="report" />
    </div>

    <!-- 按用例标签对比 -->
    <div class="rv-comparison-section">
      <CaseTagComparisonComponent :report-data="report" />
    </div>

    <!-- 具体用例对比 -->
    <div class="rv-comparison-section">
      <SpecificCaseComparisonComponent :report-data="report" />
    </div>
  </section>
</template>

<script setup lang="ts">
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/components/card.css'
import '../../../assets/styles/components/modal.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/navigation.css'
import '../../../assets/styles/components/log.css'
import '../../../assets/styles/layouts/main.css'

import { ref, watch, computed, inject } from 'vue'
import { ReportStatus } from '@/domain/enums'
import { isSecondaryComparisonReportType } from '@/domain/model/report'
import ComparisonTableComponent from '../../../components/report/ComparisonTableComponent.vue'
import CaseCategoryComparisonComponent from '../../../components/report/CaseCategoryComparisonComponent.vue'
import CaseTagComparisonComponent from '../../../components/report/CaseTagComparisonComponent.vue'
import SpecificCaseComparisonComponent from '../../../components/report/SpecificCaseComparisonComponent.vue'
import {
  comparisonDevices,
  deviceApiColumns,
  caseExecutionColumns,
  deviceApiComparisonData,
  caseExecutionData,
} from '../../../store/reportComparisonStore'
import { toggleDeviceSelection } from '../../../composables/report/useReportComparison'

const props = defineProps<{
  report: any
  reportName: string
  reportConclusion: string
  sanitizedConclusion: string
  isEditingReport: boolean
  isEditingConclusion: boolean
}>()

const isSecondaryType = computed(() => isSecondaryComparisonReportType(props.report?.type))

// 设备选择区折叠态（恢复基线 toggleDevicesCollapse 能力；导出时经 isExporting 自动展开）
const isDevicesCollapsed = ref(false)
const toggleDevicesCollapse = () => {
  isDevicesCollapsed.value = !isDevicesCollapsed.value
}
const isExporting = inject('isExporting', ref(false))
watch(isExporting, (exporting) => {
  if (exporting) isDevicesCollapsed.value = false
}, { immediate: true })

const emit = defineEmits<{
  (e: 'toggle-edit'): void
  (e: 'save-report'): void
  (e: 'cancel-edit'): void
  (e: 'toggle-conclusion-edit'): void
  (e: 'save-conclusion'): void
  (e: 'cancel-conclusion'): void
  (e: 'update:reportName', value: string): void
  (e: 'update:reportDescription', value: string): void
  (e: 'update:reportConclusion', value: string): void
}>()

const reportNameLocal = ref(props.reportName)
const reportDescriptionLocal = ref(props.report.description || '')
const reportConclusionLocal = ref(props.reportConclusion)

watch(reportNameLocal, (v) => emit('update:reportName', v))
watch(reportDescriptionLocal, (v) => emit('update:reportDescription', v))
watch(reportConclusionLocal, (v) => emit('update:reportConclusion', v))

watch(() => props.reportName, (v) => { if (v !== reportNameLocal.value) reportNameLocal.value = v })
watch(() => props.reportConclusion, (v) => { if (v !== reportConclusionLocal.value) reportConclusionLocal.value = v })
watch(() => props.report, (r) => { reportDescriptionLocal.value = r?.description || '' })
</script>
