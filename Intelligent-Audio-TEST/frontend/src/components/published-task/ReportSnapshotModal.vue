<template>
  <Teleport to="body">
    <div class="modal-overlay" @click.self="handleClose">
      <div class="modal report-snapshot-modal">
        <div class="modal-header">
          <h3 class="modal-title">
            <i class="fas fa-file-archive"></i> 冻结报告
            <span class="modal-subtitle">（发布时快照 · 不可变）</span>
          </h3>
          <div class="header-actions">
            <button
              v-if="sourceReportId"
              class="source-report-btn"
              title="打开报告管理中该报告的当前页面（冻结快照不受其影响）"
              @click="goSourceReport"
            >
              <i class="fas fa-external-link-alt"></i> 查看源报告 #{{ sourceReportId }}
            </button>
            <button class="modal-close" @click="handleClose"><i class="fas fa-times"></i></button>
          </div>
        </div>

        <div class="modal-scroll-container">
          <div v-if="!hasRenderableData" class="snapshot-empty-state">
            <i class="fas fa-inbox"></i>
            <p>该快照缺少可渲染的冻结报告数据（发布时无报告）</p>
          </div>
          <!-- INT-258：按冻结报告数据渲染成报告样（对齐 ReportView），只读不可编辑 -->
          <TaskReportPanel
            v-else
            :report="frozenReport"
            :analysis-content="frozenReport.conclusion"
            :tables="[]"
            readonly
          />
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'

import { computed } from 'vue';
import { useRouter } from 'vue-router';
import TaskReportPanel from '../report/TaskReportPanel.vue';
import type { ReportSnapshot } from '../../domain/model/publishedTask';
import { buildFrozenReportView } from './frozenReportView';

const props = defineProps<{ snapshot: ReportSnapshot }>();
const emit = defineEmits<{ (e: 'close'): void }>();

const router = useRouter();

/** 引用轨：源报告 ID（跳转报告管理报告页入口） */
const sourceReportId = computed(() => props.snapshot.sourceReportId ?? props.snapshot.reportId ?? null);

const frozenReport = computed(() => buildFrozenReportView(props.snapshot));

/** 存量快照无 summary/cases 时不可渲染（空态） */
const hasRenderableData = computed(() => {
  const s = props.snapshot?.summary;
  return !!(s && Object.keys(s).length > 0) || (props.snapshot?.cases?.length ?? 0) > 0;
});

function goSourceReport() {
  if (!sourceReportId.value) return;
  router.push({ name: 'reportView', params: { id: String(sourceReportId.value) } });
}

function handleClose() {
  emit('close');
}
</script>

<style scoped>
/* opacity/visibility 显式声明，规避全局 .modal-overlay{visibility:hidden;opacity:0}
   （test-case-manager.css，仅 .active 才可见）串扰；transform: none 对齐全局 .modal 位移 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 13000;
  overflow: hidden;
  opacity: 1;
  visibility: visible;
}

.modal {
  background-color: #fff;
  border-radius: var(--radius-xl);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transform: none;
}

.report-snapshot-modal {
  width: 1200px;
  max-width: 96vw;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 20px;
  border-bottom: 1px solid #e9ecef;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
  flex-shrink: 0;
}

.modal-title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  color: #343a40;
}

.modal-title i {
  color: #ff6a00;
}

.modal-subtitle {
  font-size: 12px;
  font-weight: 400;
  color: #94a3b8;
  margin-left: 4px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.source-report-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid #ff6a00;
  border-radius: var(--radius-md);
  background: #fff7ed;
  color: #ff6a00;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.source-report-btn:hover {
  background: #ff6a00;
  color: #fff;
}

.modal-close {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: #6c757d;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-full);
  transition: all 0.2s;
}

.modal-close:hover {
  color: #343a40;
  background-color: #e9ecef;
}

.modal-scroll-container {
  max-height: calc(90vh - 58px);
  overflow-y: auto;
  flex: 1;
  background-color: #fff;
}

.snapshot-empty-state {
  padding: 48px 16px;
  text-align: center;
  color: #94a3b8;
  font-size: 13px;
}

.snapshot-empty-state i {
  font-size: 32px;
  margin-bottom: 12px;
  display: block;
}
</style>
