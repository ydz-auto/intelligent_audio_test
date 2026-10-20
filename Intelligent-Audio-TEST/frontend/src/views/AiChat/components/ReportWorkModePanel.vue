<template>
  <div class="report-work-mode">
    <!-- 头行：文档预览 + 版本 + 动作组（版本/导出/编辑 待后端立项） -->
    <div class="rwm-header">
      <i class="fas fa-file-lines rwm-header-icon"></i>
      <span class="rwm-title">{{ REPORT_WORK_MODE_COPY.documentPreview }}</span>
      <span v-if="report" class="rwm-doc-name">{{ report.name || report.title || '' }}</span>
      <span v-if="version" class="rwm-version">{{ REPORT_WORK_MODE_COPY.version.replace('{n}', String(version)) }}</span>
      <span class="rwm-header-spacer"></span>
      <button type="button" class="rwm-action-btn" :title="REPORT_WORK_MODE_COPY.history">
        <i class="fas fa-clock-rotate-left"></i>
      </button>
      <button type="button" class="rwm-action-btn" :title="REPORT_WORK_MODE_COPY.export">
        <i class="fas fa-download"></i>
      </button>
      <button type="button" class="rwm-action-btn" :title="REPORT_WORK_MODE_COPY.editDocument">
        <i class="fas fa-pen"></i>
      </button>
      <button type="button" class="rwm-action-btn" :title="REPORT_WORK_MODE_COPY.close" @click="emit('close')">
        <i class="fas fa-xmark"></i>
      </button>
    </div>

    <!-- 预览体：有报告 → 复用 TaskReportPanel；无报告 → Demo 占位（不杜撰数值） -->
    <div class="rwm-body">
      <TaskReportPanel v-if="report" :report="report" readonly />
      <div v-else class="rwm-placeholder">
        <i class="fas fa-file-lines rwm-placeholder-icon"></i>
        <p class="rwm-placeholder-title">文档预览</p>
        <p class="rwm-placeholder-desc">
          Agent 后端（DSH + Report Studio）立项后，此处渲染报告工作台文档。
          当前为 Demo 预览，未接入实际后端。
        </p>
      </div>
    </div>

    <!-- 底部提示行 -->
    <div class="rwm-footer">[Demo] {{ REPORT_WORK_MODE_COPY.footer }}</div>
  </div>
</template>

<script setup lang="ts">
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/navigation.css'
import '../../../assets/styles/components/log.css'
import '../../../assets/styles/layouts/main.css'

import { REPORT_WORK_MODE_COPY } from '@/domain/constants/aiChat'
import TaskReportPanel from '@/components/report/TaskReportPanel.vue'

defineProps<{
  /** 会话绑定的报告对象（有报告 → 复用 TaskReportPanel 渲染；无 → Demo 占位） */
  report?: Record<string, any> | null
  /** 文档版本（studio 版本快照；待后端立项） */
  version?: number
}>()

const emit = defineEmits<{ (e: 'close'): void }>()
</script>

<style scoped>
.report-work-mode {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  border-left: 1px solid var(--border);
  background: var(--card);
}

.rwm-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.rwm-header-icon {
  color: var(--primary);
}

.rwm-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--foreground);
}

.rwm-doc-name {
  font-size: 12px;
  color: var(--muted-foreground);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 160px;
}

.rwm-version {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--muted-foreground);
  background: var(--muted);
  border-radius: var(--radius-full);
  padding: 1px 6px;
}

.rwm-header-spacer {
  flex: 1;
}

.rwm-action-btn {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--muted-foreground);
  font-size: 13px;
  cursor: pointer;
}

.rwm-action-btn:hover {
  background: var(--muted);
  color: var(--foreground);
}

.rwm-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.rwm-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
}

.rwm-placeholder-icon {
  font-size: 28px;
  color: var(--muted-foreground);
  margin-bottom: 12px;
}

.rwm-placeholder-title {
  margin: 0 0 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--foreground);
}

.rwm-placeholder-desc {
  margin: 0;
  max-width: 380px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--muted-foreground);
}

.rwm-footer {
  flex-shrink: 0;
  padding: 8px 14px;
  border-top: 1px solid var(--border);
  font-size: 11px;
  color: var(--muted-foreground);
}
</style>
