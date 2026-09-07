<template>
  <div class="report-header">
    <div class="report-info">
      <h1 class="report-title">{{ report.title }}</h1>
      <div class="report-meta">
        <span class="report-type" :class="`report-type-${report.type}`">{{ reportTypeLabel }}</span>
        <span class="report-date">{{ formatDate(report.createdAt) }}</span>
        <span class="report-status" :class="`report-status-${report.status}`">{{ reportStatusLabel }}</span>
      </div>
    </div>
    
    <div class="report-actions">
      <button class="btn btn-primary" @click="$emit('save')">
        <i class="fas fa-save"></i> 保存
      </button>
      <button class="btn btn-secondary" @click="$emit('export')">
        <i class="fas fa-download"></i> 导出
      </button>
      <button 
        class="btn" 
        :class="report.status === ReportStatus.DRAFT ? 'btn-primary' : 'btn-warning'"
        @click="$emit('publish')"
      >
        <i :class="report.status === ReportStatus.DRAFT ? 'fas fa-paper-plane' : 'fas fa-times'" ></i> 
        {{ report.status === ReportStatus.DRAFT ? '发布' : '取消发布' }}
      </button>
      <button class="btn btn-danger" @click="$emit('close')">
        <i class="fas fa-times"></i> 关闭
      </button>
    </div>
  </div>
</template>

<script>
import { ReportStatus } from '@/domain/enums'
import { formatDate } from '@/utils/utils'

export default {
  name: 'ReportHeaderComponent',
  props: {
    report: {
      type: Object, required: true, default: () => ({
        id: '', title: '报告标题', type: 'task', status: ReportStatus.DRAFT, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString()
      })
    }
  },
  emits: ['save', 'export', 'publish', 'close'],
  computed: {
    reportTypeLabel() {
      const typeMap = {
        'task': '任务报告', 'comparison': '对比报告', 'historical': '二次对比报告'
      };
      return typeMap[this.report.type] || '未知报告类型';
    },
    reportStatusLabel() {
      const statusMap = { [ReportStatus.DRAFT]: '草稿', [ReportStatus.PUBLISHED]: '已发布' };
      return statusMap[this.report.status] || '未知状态';
    }
  },
  methods: {
    formatDate(dateString) {
      return formatDate(dateString);
    }
  }
};
</script>

<style scoped>
.report-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  background: #ffffff;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  margin-bottom: 24px;
}

.report-info {
  flex: 1;
}

.report-title {
  font-size: 24px;
  font-weight: bold;
  color: #333;
  margin: 0 0 12px 0;
  background: linear-gradient(90deg, #FF6A00, #1677FF);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.report-meta {
  display: flex;
  gap: 20px;
  align-items: center;
  flex-wrap: wrap;
}

.report-type, .report-date, .report-status {
  font-size: 14px;
  padding: 6px 12px;
  border-radius: 16px;
  font-weight: 500;
}

.report-type {
  background: #e6f7ff;
  color: #1890ff;
}

.report-type-task {
  background: #e6f7ff;
  color: #1890ff;
}

.report-type-comparison {
  background: #fff7e6;
  color: #fa8c16;
}

.report-type-historical {
  background: #f6ffed;
  color: #52c41a;
}

.report-date {
  background: #f5f5f5;
  color: #666;
}

.report-status {
  font-weight: 600;
}

.report-status-draft {
  background: var(--danger-light);
  color: var(--danger-color);
}

.report-status-published {
  background: var(--success-light);
  color: var(--success-color);
}

.report-actions {
  display: flex;
  gap: var(--spacing-md);
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  border: none;
  border-radius: var(--btn-border-radius);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--transition-normal);
  font-family: inherit;
}

.btn-primary {
  background: var(--btn-primary-bg);
  color: var(--white-color);
}

.btn-primary:hover {
  opacity: 0.9;
  box-shadow: var(--shadow-lg);
}

.btn-secondary {
  background: var(--btn-secondary-bg);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.btn-secondary:hover {
  background: var(--secondary-light);
  border-color: var(--secondary-color);
  color: var(--secondary-color);
}

.btn-warning {
  background: var(--warning-light);
  color: var(--warning-color);
  border: 1px solid var(--warning-color);
}

.btn-warning:hover {
  background: var(--warning-color);
  color: var(--white-color);
}

.btn-danger {
  background: var(--danger-light);
  color: var(--danger-color);
  border: 1px solid var(--danger-color);
}

.btn-danger:hover {
  background: var(--danger-color);
  color: var(--white-color);
}
</style>