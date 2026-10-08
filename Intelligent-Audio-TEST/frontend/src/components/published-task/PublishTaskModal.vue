<template>
  <Teleport to="body">
    <div class="modal-overlay" @click.self="handleClose">
      <div class="modal publish-task-modal">
        <div class="modal-header">
          <h3 class="modal-title">发布任务</h3>
          <button class="modal-close" @click="handleClose"><i class="fas fa-times"></i></button>
        </div>
        <div class="modal-scroll-container">
          <div class="modal-body">
            <div class="form-group">
              <label class="form-label">来源任务 <span class="required">*</span></label>
              <div class="form-source-task" v-if="selectedTask">
                <i class="fas fa-tasks"></i>
                <span class="form-source-task-name">{{ selectedTask.name || selectedTask.title }}</span>
                <span class="form-source-task-status">（{{ getStatusText(selectedTask.status) }} · 用例 {{ selectedTask.caseCount ?? selectedTask.totalCases ?? 0 }}）</span>
              </div>
              <!-- 无预选来源任务时：从可发布任务中选择 -->
              <select
                v-else
                v-model="form.sourceTaskId"
                class="form-select"
                :disabled="submitting"
              >
                <option :value="null" disabled>请选择要发布的日常任务</option>
                <option v-for="t in publishableTasks" :key="t.id" :value="t.id">
                  {{ t.name || `任务${t.id}` }}（{{ getStatusText(t.status) }} · 用例 {{ t.caseCount ?? t.totalCases ?? 0 }}）
                </option>
              </select>
              <div class="form-hint" v-if="!selectedTask && publishableTasks.length === 0">暂无 completed/failed/stopped/pending 状态的可发布任务</div>
            </div>

            <div class="form-group">
              <label class="form-label">已发布任务名称 <span class="required">*</span></label>
              <input v-model="form.name" class="form-input" placeholder="例如：翻译能力正式回归任务" maxlength="255" />
            </div>

            <div class="form-group">
              <label class="form-label">说明</label>
              <textarea v-model="form.description" class="form-textarea" rows="2" placeholder="任务说明（可选）"></textarea>
            </div>

            <div class="form-group">
              <label class="form-label">发布说明</label>
              <input v-model="form.publishReason" class="form-input" placeholder="例如：完成基线验证（可选）" />
            </div>

            <div class="form-group">
              <label class="form-checkbox-label">
                <input type="checkbox" v-model="form.benchmark" :disabled="submitting" />
                <span>参与 Benchmark 排行（实测轨数据源标记）</span>
              </label>
              <div class="form-hint">勾选后该已发布任务将进入 Benchmark 双轨排行的实测轨</div>
            </div>

            <template v-if="form.benchmark">
              <div class="form-group">
                <label class="form-label">Benchmark 测试集标识</label>
                <input
                  v-model="form.benchmarkSuite"
                  class="form-input"
                  placeholder="例如：librispeech-test-clean（可选，随快照冻结）"
                  maxlength="128"
                />
              </div>
              <div class="form-group">
                <label class="form-label">Benchmark 被测类别</label>
                <select v-model="form.benchmarkCategory" class="form-select" :disabled="submitting">
                  <option value="">不指定</option>
                  <option v-for="(label, value) in BenchmarkCategoryLabels" :key="value" :value="value">
                    {{ label }}
                  </option>
                </select>
              </div>
            </template>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="handleClose">取消</button>
          <button class="btn btn-primary" :disabled="!canSubmit || submitting" @click="handleConfirm">
            <i class="fas fa-paper-plane"></i> {{ submitting ? '发布中...' : '发布' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import type { Task } from '../../domain/model/task';
import { BenchmarkCategoryLabels } from '../../domain/enums';

const props = defineProps<{
  tasks: Task[];
  submitting?: boolean;
  /** 预选来源任务（卡片「发布」入口带入） */
  presetSourceTaskId?: number | null;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'confirm', payload: {
    sourceTaskId: number;
    name: string;
    description?: string;
    publishReason?: string;
    benchmark: boolean;
    benchmarkSuite?: string;
    benchmarkCategory?: string;
  }): void;
}>();

// 可发布状态（对齐后端 PUBLISHABLE_STATUSES）
const PUBLISHABLE_STATUSES = ['completed', 'failed', 'stopped', 'pending'];

/** 可选来源任务（仅可发布状态） */
const publishableTasks = computed(() =>
  (props.tasks || []).filter((t: any) => PUBLISHABLE_STATUSES.includes(t.status))
);

const form = ref<{
  sourceTaskId: number | null;
  name: string;
  description: string;
  publishReason: string;
  benchmark: boolean;
  benchmarkSuite: string;
  benchmarkCategory: string;
}>({
  sourceTaskId: null,
  name: '',
  description: '',
  publishReason: '',
  benchmark: false,
  benchmarkSuite: '',
  benchmarkCategory: '',
});

const selectedTask = computed(() =>
  (props.tasks as any[]).find((t) => t.id === form.value.sourceTaskId) || null
);

const canSubmit = computed(
  () => form.value.sourceTaskId != null && form.value.name.trim().length > 0 && !props.submitting
);

// 选择来源任务后自动带出名称
watch(
  () => form.value.sourceTaskId,
  (id) => {
    if (id == null) return;
    const task = (props.tasks as any[]).find((t) => t.id === id);
    if (task && !form.value.name.trim()) {
      form.value.name = task.name || task.title || '';
    }
  }
);

// 预选来源任务（卡片「发布」入口），并默认填充原任务名
watch(
  () => props.presetSourceTaskId,
  (id) => {
    if (id == null) return;
    form.value.sourceTaskId = id;
    const task = (props.tasks as any[]).find((t) => t.id === id);
    if (task) {
      form.value.name = task.name || task.title || '';
    }
  },
  { immediate: true }
);

function getStatusText(status: string): string {
  const texts: Record<string, string> = {
    completed: '已完成',
    failed: '失败',
    stopped: '已停止',
    pending: '待执行',
  };
  return texts[status] || status;
}

function handleClose() {
  emit('close');
}

function handleConfirm() {
  if (!canSubmit.value || form.value.sourceTaskId == null) return;
  emit('confirm', {
    sourceTaskId: form.value.sourceTaskId,
    name: form.value.name.trim(),
    description: form.value.description.trim() || undefined,
    publishReason: form.value.publishReason.trim() || undefined,
    benchmark: form.value.benchmark,
    benchmarkSuite: form.value.benchmark ? form.value.benchmarkSuite.trim() || undefined : undefined,
    benchmarkCategory: form.value.benchmark ? form.value.benchmarkCategory || undefined : undefined,
  });
}
</script>

<style scoped>
/* 自包含弹窗样式：全局样式无 .modal-overlay，不能依赖其他组件的 scoped 样式 */
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
}

.modal {
  background-color: #fff;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.publish-task-modal {
  width: 520px;
  max-width: 92vw;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #e9ecef;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
}

.modal-title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  color: #343a40;
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
  border-radius: 50%;
  transition: all 0.2s;
}

.modal-close:hover {
  color: #343a40;
  background-color: #e9ecef;
}

.modal-scroll-container {
  max-height: calc(90vh - 120px);
  overflow-y: auto;
  flex: 1;
}

.modal-body {
  padding: 20px 24px;
  background-color: #fff;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 12px;
  padding: 14px 24px;
  border-top: 1px solid #e9ecef;
  background-color: #f8f9fa;
}

.btn {
  padding: 8px 18px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-primary {
  background-color: #ff6a00;
  color: #fff;
}

.btn-primary:hover {
  background-color: #ff8c40;
}

.btn-primary:disabled {
  background-color: #d9d9d9;
  cursor: not-allowed;
}

.btn-secondary {
  background-color: #f0f0f0;
  color: #333;
}

.btn-secondary:hover {
  background-color: #e0e0e0;
}

.form-group {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #1f2937;
}

.required {
  color: #e53e3e;
}

.form-select,
.form-input,
.form-textarea {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 13px;
  background: #fff;
  color: #1f2937;
  box-sizing: border-box;
}

.form-select:focus,
.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: #ff6a00;
  box-shadow: 0 0 0 2px rgba(255, 106, 0, 0.15);
}

.form-source-task {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #f8fafc;
  font-size: 13px;
  color: #334155;
}

.form-source-task i {
  color: #ff6a00;
}

.form-source-task-name {
  font-weight: 600;
  color: #1f2937;
}

.form-source-task-status {
  color: #94a3b8;
  font-size: 12px;
}

.form-hint {
  margin-top: 6px;
  font-size: 12px;
  color: #9ca3af;
}

.form-checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
  color: #1f2937;
  cursor: pointer;
}

.form-checkbox-label input[type='checkbox'] {
  width: 15px;
  height: 15px;
  accent-color: var(--primary-color, #ff6a00);
  cursor: pointer;
}
</style>
