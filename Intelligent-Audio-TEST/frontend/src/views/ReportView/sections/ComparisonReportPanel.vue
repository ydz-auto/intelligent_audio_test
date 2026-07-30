<template>
  <section class="comparison-report-container">
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
            <input type="text" id="report-name" placeholder="请输入报告名称" v-model="reportNameLocal">
          </div>
          <div class="edit-field">
            <label for="report-description">报告描述</label>
            <textarea id="report-description" placeholder="请输入报告描述" rows="3" v-model="reportDescriptionLocal"></textarea>
          </div>
        </div>

        <div class="analysis-actions">
          <button v-if="!isEditingReport" class="btn btn-primary" @click="emit('toggle-edit')">
            <i class="fas fa-edit"></i> 编辑
          </button>
          <template v-else>
            <button class="btn btn-primary" @click="emit('save-report')">
              <i class="fas fa-save"></i> 保存
            </button>
            <button class="btn btn-secondary" @click="emit('cancel-edit')">
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
          <div
            v-for="device in reportService.devices.value"
            :key="device.id"
            class="device-select-item"
            :class="{ 'selected': device.selected, 'api-item': device.type === 'API' }"
            @click="reportService.toggleDeviceSelection(device.id)"
            role="button"
            tabindex="0"
            @keydown.enter.prevent="reportService.toggleDeviceSelection(device.id)"
            @keydown.space.prevent="reportService.toggleDeviceSelection(device.id)"
          >
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
          <textarea class="analysis-textarea" v-model="reportConclusionLocal" placeholder="请输入分析结论..."></textarea>
        </div>
        <div class="analysis-actions">
          <button v-if="!isEditingConclusion" class="btn btn-primary" @click="emit('toggle-conclusion-edit')">
            <i class="fas fa-edit"></i> 编辑
          </button>
          <template v-else>
            <button class="btn btn-primary" @click="emit('save-conclusion')">
              <i class="fas fa-save"></i> 保存
            </button>
            <button class="btn btn-secondary" @click="emit('cancel-conclusion')">
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
        :columns="reportService.deviceApiColumns"
        :data="reportService.deviceApiComparisonData.value"
        :default-collapsed="true"
        :show-search="false"
      />
    </div>

    <!-- 用例执行数量对比 -->
    <div class="comparison-section">
      <ComparisonTableComponent
        title="用例执行数量对比"
        :columns="reportService.caseExecutionColumns"
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
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import ComparisonTableComponent from '../../../components/report/ComparisonTableComponent.vue'
import CaseCategoryComparisonComponent from '../../../components/report/CaseCategoryComparisonComponent.vue'
import CaseTagComparisonComponent from '../../../components/report/CaseTagComparisonComponent.vue'
import SpecificCaseComparisonComponent from '../../../components/report/SpecificCaseComparisonComponent.vue'
import reportService from '../../../services/reportService'

const props = defineProps<{
  report: any
  reportName: string
  reportConclusion: string
  sanitizedConclusion: string
  isEditingReport: boolean
  isEditingConclusion: boolean
}>()

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
