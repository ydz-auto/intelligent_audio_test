<template>
  <section class="comparison-report-container" id="task-comparison-report-container">
    <div class="comparison-header">
      <h3 class="comparison-title">任务对比报告</h3>
      <p class="comparison-subtitle">对比分析所选任务的执行情况和结果，帮助您识别系统性能瓶颈和质量问题，为后续优化提供依据。</p>
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
          <h4 class="analysis-title">{{ reportName || '任务对比报告' }}</h4>
          <div class="analysis-status">
            <span class="status-dot"></span>
            {{ reportServiceData?.status === 'draft' ? '草稿' : '已发布' }}
          </div>
        </div>
        <div v-if="!isEditingReport" class="analysis-text">
          <div>{{ reportServiceData?.description || '请输入报告描述' }}</div>
        </div>
        <div v-else class="analysis-edit">
          <div class="edit-field">
            <label for="report-name">报告名称</label>
            <input type="text" id="report-name" placeholder="请输入报告名称" v-model="reportName">
          </div>
          <div class="edit-field">
            <label for="report-description">报告描述</label>
            <textarea id="report-description" placeholder="请输入报告描述" rows="3" v-model="reportServiceData!.description"></textarea>
          </div>
        </div>
        <div class="analysis-actions">
          <button v-if="!isEditingReport" class="btn btn-primary" @click="$emit('toggle-edit-report')">
            <i class="fas fa-edit"></i> 编辑
          </button>
          <template v-else>
            <button class="btn btn-primary" @click="$emit('save-report')">
              <i class="fas fa-save"></i> 保存
            </button>
            <button class="btn btn-secondary" @click="$emit('cancel-edit-report')">
              <i class="fas fa-times"></i> 取消
            </button>
          </template>
        </div>
      </div>
    </div>

    <!-- 设备和API选择器 -->
    <div class="comparison-selectors">
      <h4 class="selector-title"><i class="fas fa-list"></i> 选择要对比的设备和API</h4>
      <div class="selector-content">
        <div id="unified-selector">
          <div
            v-for="device in reportDevices"
            :key="device.id"
            class="device-select-item"
            :class="{ selected: device.selected, 'api-item': device.type === 'API' }"
            @click="$emit('toggle-device', device.id)"
          >
            <div class="device-icon-wrapper">
              <i :class="device.type === '设备' ? 'fas fa-headphones' : 'fas fa-exchange-alt'"></i>
            </div>
            <div class="device-info">
              <span class="device-name">{{ device.name }}</span>
              <span class="device-type-tag">{{ device.type }}</span>
            </div>
            <div class="selection-indicator"><i class="fas fa-check-circle"></i></div>
          </div>
        </div>
      </div>
    </div>

    <!-- 分析结论 -->
    <div class="analysis-conclusion-card">
      <div class="analysis-icon"><i class="fas fa-chart-line"></i></div>
      <div class="analysis-content">
        <div class="analysis-header">
          <h4 class="analysis-title">分析结论</h4>
          <div class="analysis-status" :class="reportServiceData.status">
            <span class="status-dot"></span>
            {{ reportServiceData.status === 'draft' ? '草稿' : '已发布' }}
          </div>
        </div>
        <div v-if="!isEditingConclusion" class="analysis-text" id="task-analysis-conclusion" v-html="sanitizedConclusion"></div>
        <div v-else class="analysis-edit">
          <textarea
            id="task-analysis-conclusion-edit"
            class="analysis-textarea"
            v-model="reportConclusion"
            placeholder="请输入分析结论..."
          ></textarea>
        </div>
        <div class="analysis-actions">
          <button v-if="!isEditingConclusion" class="btn btn-primary" @click="$emit('toggle-edit-conclusion')">
            <i class="fas fa-edit"></i> 编辑
          </button>
          <template v-else>
            <button class="btn btn-primary" id="task-save-conclusion-btn" @click="$emit('save-conclusion')">
              <i class="fas fa-save"></i> 保存
            </button>
            <button class="btn btn-secondary" id="task-cancel-edit-btn" @click="$emit('cancel-edit-conclusion')">
              <i class="fas fa-times"></i> 取消
            </button>
          </template>
        </div>
      </div>
    </div>

    <!-- 对比表格 -->
    <div class="comparison-section">
      <ComparisonTableComponent title="设备/API信息对比" :columns="deviceApiColumns" :data="deviceApiComparisonData" :default-collapsed="true" :show-search="false" />
    </div>
    <div class="comparison-section">
      <ComparisonTableComponent title="用例执行数量对比" :columns="caseExecutionColumns" :data="caseExecutionData" :default-collapsed="true" :show-search="false" />
    </div>
    <div class="comparison-section">
      <CaseCategoryComparisonComponent :report-data="reportService.comparisonReport.value" />
    </div>
    <div class="comparison-section">
      <CaseTagComparisonComponent :report-data="reportService.comparisonReport.value" />
    </div>
    <div class="comparison-section">
      <SpecificCaseComparisonComponent :report-data="reportService.comparisonReport.value" />
    </div>

    <!-- 浮动操作按钮 -->
    <teleport to="#global-fixed-elements">
      <div
        id="floating-report-actions"
        style="position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); display: flex; justify-content: center; gap: 16px; z-index: 9999; padding: 16px 24px; background: rgba(255, 255, 255, 0.95); border-radius: 12px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15); backdrop-filter: blur(10px); border: 1px solid rgba(226, 232, 240, 0.8);"
      >
        <button class="btn btn-primary" id="keep-report-btn" @click="$emit('save-report')">
          <i class="fas fa-save"></i> 保存
        </button>
        <button class="btn btn-success" id="publish-report-btn" @click="$emit('publish-report')">
          <i class="fas fa-paper-plane"></i> 发布
        </button>
        <button class="btn btn-secondary" id="close-comparison-report" @click="$emit('close')">
          <i class="fas fa-times"></i> 关闭对比报告
        </button>
      </div>
    </teleport>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ComparisonTableComponent from '../../components/report/ComparisonTableComponent.vue'
import CaseCategoryComparisonComponent from '../../components/report/CaseCategoryComparisonComponent.vue'
import CaseTagComparisonComponent from '../../components/report/CaseTagComparisonComponent.vue'
import SpecificCaseComparisonComponent from '../../components/report/SpecificCaseComparisonComponent.vue'

defineProps<{
  reportServiceData: any
  reportDevices: any[]
  isEditingReport: boolean
  isEditingConclusion: boolean
  deviceApiColumns: any[]
  deviceApiComparisonData: any[]
  caseExecutionColumns: any[]
  caseExecutionData: any[]
  reportService: any
}>()

// 双向绑定：reportName / reportConclusion 需要可写
const reportName = defineModel<string>('reportName', { default: '' })
const reportConclusion = defineModel<string>('reportConclusion', { default: '' })

import { sanitizeConclusion } from '../../utils/sanitize'
const sanitizedConclusion = computed(() => sanitizeConclusion(reportConclusion.value))

defineEmits<{
  (e: 'toggle-edit-report'): void
  (e: 'save-report'): void
  (e: 'cancel-edit-report'): void
  (e: 'toggle-device', id: string | number): void
  (e: 'toggle-edit-conclusion'): void
  (e: 'save-conclusion'): void
  (e: 'cancel-edit-conclusion'): void
  (e: 'publish-report'): void
  (e: 'close'): void
}>()
</script>
