<template>
  <div class="card" :class="{ 'card-selected': selected }" @click="emit('toggleSelect', report.id, $event)">
    <div class="card-header">
      <div class="report-checkbox-wrapper">
        <input
          type="checkbox"
          class="task-checkbox"
          :id="`report-${report.id}`"
          :checked="selected"
          @change="emit('toggleSelect', report.id)"
          @click.stop
        >
        <label :for="`report-${report.id}`"></label>
      </div>
      <div class="report-card-title-wrapper">
        <h3 class="report-card-title">{{ report.name }}</h3>
        <div class="report-card-meta-tags">
          <span class="report-card-type">{{ getReportTypeLabel(report.type) }}</span>
          <span class="report-card-status" :class="report.status">{{ getReportStatusLabel(report.status) }}</span>
          <span v-if="algorithmTypeLabel" class="report-card-algorithm-type">{{ algorithmTypeLabel }}</span>
          <span v-if="report.taskName" class="report-card-test-type">{{ report.taskName }}</span>
        </div>
      </div>
      <div class="card-actions">
        <button class="btn btn-primary" @click.stop="emit('view', report.id, report.type)">
          <i class="fas fa-eye"></i> 查看
        </button>
        <button class="btn btn-secondary" @click.stop="emit('edit', report.id)">
          <i class="fas fa-edit"></i> 编辑
        </button>
        <button class="btn btn-danger" @click.stop="emit('delete', report.id)">
          <i class="fas fa-trash"></i> 删除
        </button>
        <button v-if="isDraft" class="btn btn-success" @click.stop="emit('publish', report.id)">
          <i class="fas fa-paper-plane"></i> 发布
        </button>
      </div>
    </div>
    <div class="card-body">
      <p class="report-card-description">{{ summary }}</p>
      <div class="report-card-meta">
        <span class="report-card-meta-item">
          <i class="fas fa-calendar-alt"></i>
          {{ formatDate(report.createdAt) }}
        </span>
        <template v-if="isComparison">
          <span class="report-card-meta-item">
            <i class="fas fa-cubes"></i>
            {{ taskCount }} 个任务对比
          </span>
        </template>
        <template v-else>
          <span class="report-card-meta-item">
            <i class="fas fa-list-check"></i>
            {{ totalCases }} 个测试用例
          </span>
          <span class="report-card-meta-item">
            <i class="fas fa-check-circle"></i>
            {{ successRate }}% 通过率
          </span>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { Report } from '../../shared/types/index';
import {
  getReportTypeLabel,
  getReportStatusLabel,
  isComparisonReportType
} from '../../shared/constants/reportConstants';

interface Props {
  report: Report;
  selected: boolean;
  summary: string;
  algorithmTypeLabel?: string | null;
}

const props = defineProps<Props>();

const emit = defineEmits<{
  (e: 'toggleSelect', id: string | number, event?: MouseEvent): void;
  (e: 'view', id: string | number, type?: string): void;
  (e: 'edit', id: string | number): void;
  (e: 'delete', id: string | number): void;
  (e: 'publish', id: string | number): void;
}>();

const isDraft = computed(() => props.report.status === 'draft');
const isComparison = computed(() => isComparisonReportType(props.report.type));

const taskCount = computed(() => props.report.summary?.taskCount || 0);

const totalCases = computed(
  () => props.report.summary?.totalCases || props.report.summary?.totalTests || props.report.summary?.total_cases || 0
);

const successRate = computed(
  () => props.report.summary?.overallSuccessRate || props.report.summary?.passRate || props.report.summary?.overall_success_rate || 0
);

const formatDate = (dateString: string | null | undefined): string => {
  if (!dateString) return '-';
  return new Date(dateString).toLocaleString();
};
</script>

<style scoped>
/* 依赖全局样式：main.css 中已包含 card / card-header / card-actions / btn / report-* 等基础样式 */

/* 报告状态标签配色 */
.report-card-status.published {
  background-color: var(--success-light, #f0fdf4);
  color: var(--success-color, #16a34a);
  border: 1px solid var(--success-color, #16a34a);
}

.report-card-status.draft {
  background-color: var(--warning-light, #fffbeb);
  color: var(--warning-color, #d97706);
  border: 1px solid var(--warning-color, #d97706);
}

.report-card-status.final {
  background-color: var(--info-light, #eff6ff);
  color: var(--info-color, #2563eb);
  border: 1px solid var(--info-color, #2563eb);
}

/* 算法类型标签配色 */
.report-card-algorithm-type {
  background-color: #f0f9ff;
  color: #0284c7;
  border: 1px solid #0284c7;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
}
</style>
