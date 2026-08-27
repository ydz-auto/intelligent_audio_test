<template>
  <div class="task-card" :class="{ 'selected': isSelected, 'task-card-selected': isSelected }" @click="toggleSelection">
    <div class="task-header">
      <div class="task-checkbox-info" v-if="showCheckbox">
        <input 
          type="checkbox" 
          id="checkbox-{{ task.id }}" 
          class="task-checkbox"
          @change="toggleSelection"
          @click.stop
          :checked="isSelected"
        >
        <div class="task-title-section">
          <div class="task-title-with-status">
            <span class="task-status" :class="task.status">
              <i class="fas task-indicator" :class="{
                'fa-clock': task.status === 'pending',
                'fa-hourglass': task.status === 'queued',
                'fa-spinner fa-spin': task.status === 'running',
                'fa-sync-alt fa-spin': task.status === 'evaluating',
                'fa-sync-alt fa-spin': task.status === 'reevaluating',
                'fa-hourglass-half': task.status === 'reevaluate_queued',
                'fa-check-circle': task.status === 'completed',
                'fa-times-circle': task.status === 'failed',
                'fa-pause-circle': task.status === 'paused',
                'fa-stop-circle': task.status === 'stopped',
                'fa-minus-circle': task.status === 'skipped',
                'fa-object-group': task.status === 'merged'
              }"></i>
              {{ getStatusText(task.status) }}
            </span>
            <div class="task-title" v-if="!isEditingName" @click.stop="startEditName" title="点击修改任务名称">{{ task.name || task.title || '未命名任务' }}</div>
            <div class="task-title-edit" v-else @click.stop>
              <input 
                type="text" 
                v-model="editedName" 
                @keydown="handleKeydown"
                @blur="handleBlur"
                ref="nameInput"
                class="name-edit-input"
                autofocus
              />
            </div>
          </div>
          <div class="task-description">{{ task.description || '' }}</div>
          <div class="task-meta">
            <span class="task-meta-item task-type" :class="`${task.type}`">
              <i class="fas fa-tag"></i>
              {{ getTaskTypeText(task.type) }}
            </span>
            <span class="task-meta-item algorithm-type" v-if="task.algorithmType">
              <i class="fas fa-microchip"></i>
              {{ getAlgorithmTypeText(task.algorithmType) }}
            </span>
            <span class="task-meta-item">
              <i class="fas fa-calendar-alt"></i>
              {{ task.createdAt }}
            </span>
            <span class="task-meta-item">
              <i class="fas fa-tasks"></i>
              用例数{{ task.caseCount }}
            </span>
            <span class="task-meta-item">
              <i class="fas fa-desktop"></i>
              设备数{{ task.deviceCount }}
            </span>
            <span class="task-meta-item">
              <i class="fas fa-chart-pie"></i>
              完成率{{ calculateCompletionRate(task) }}%
            </span>
          </div>
          <div class="task-tags" v-if="task.tags && task.tags.length > 0">
            <span v-for="(tag, index) in task.tags" :key="index" class="task-tag">{{ tag }}</span>
          </div>
        </div>
      </div>
      <div class="task-title-section" v-else>
        <div class="task-title-with-status">
          <span class="task-status" :class="task.status">
            <i class="fas task-indicator" :class="{
              'fa-clock': task.status === 'pending',
              'fa-hourglass': task.status === 'queued',
              'fa-spinner fa-spin': task.status === 'running',
              'fa-sync-alt fa-spin': task.status === 'evaluating',
              'fa-sync-alt fa-spin': task.status === 'reevaluating',
              'fa-hourglass-half': task.status === 'reevaluate_queued',
              'fa-check-circle': task.status === 'completed',
              'fa-times-circle': task.status === 'failed',
              'fa-pause-circle': task.status === 'paused',
              'fa-stop-circle': task.status === 'stopped',
              'fa-minus-circle': task.status === 'skipped',
              'fa-object-group': task.status === 'merged'
            }"></i>
            {{ getStatusText(task.status) }}
          </span>
          <div class="task-title" v-if="!isEditingName" @click.stop="startEditName" title="点击修改任务名称">{{ task.name || task.title || '未命名任务' }}</div>
          <div class="task-title-edit" v-else @click.stop>
            <input 
              type="text" 
              v-model="editedName" 
              @keydown="handleKeydown"
              @blur="saveEditName"
              ref="nameInput"
              class="name-edit-input"
              autofocus
            />
          </div>
        </div>
        <div class="task-description">{{ task.description || '' }}</div>
        <div class="task-meta">
            <span class="task-meta-item task-type" :class="`${task.type}`">
              <i class="fas fa-tag"></i>
              {{ getTaskTypeText(task.type) }}
            </span>
            <span class="task-meta-item algorithm-type" v-if="task.algorithmType">
              <i class="fas fa-microchip"></i>
              {{ getAlgorithmTypeText(task.algorithmType) }}
            </span>
            <span class="task-meta-item">
              <i class="fas fa-calendar-alt"></i>
              {{ task.createdAt }}
            </span>
            <span class="task-meta-item">
              <i class="fas fa-tasks"></i>
              用例数{{ task.caseCount }}
            </span>
            <span class="task-meta-item">
              <i class="fas fa-desktop"></i>
              设备数{{ task.deviceCount }}
            </span>
            <span class="task-meta-item">
              <i class="fas fa-chart-pie"></i>
              完成率{{ calculateCompletionRate(task) }}%
            </span>
          </div>
        <div class="task-tags" v-if="task.tags && task.tags.length > 0">
          <span v-for="(tag, index) in task.tags" :key="index" class="task-tag">{{ tag }}</span>
        </div>
      </div>
      <div class="task-status-actions">
        <div class="task-actions" v-if="actions && actions.length > 0">
          <template v-for="action in actions" :key="action.id">
            <button 
              v-if="!action.show || action.show(task)"
              class="btn" :class="`btn-${action.type}`"
              @click.stop="handleAction(action)"
              :disabled="typeof action.disabled === 'function' ? action.disabled(task) : action.disabled"
              :title="action.title || action.label"
            >
              <i v-if="action.icon" :class="`fas ${action.icon}`"></i>
              {{ action.label }}
            </button>
          </template>
        </div>
      </div>
    </div>
    
    <div class="task-steps" v-if="showConfig && task.steps && task.steps.length > 0">
      <h5 class="steps-title">任务步骤</h5>
      <div class="steps-list">
        <div v-for="step in task.steps" :key="step.id" class="step-item">
          <span class="step-status" :class="`status-${step.status}`">
            {{ getStepStatusText(step.status) }}
          </span>
          <span class="step-name">{{ step.name }}</span>
          <span v-if="step.responseTime" class="step-meta">
            响应时间{{ step.responseTime }}ms
          </span>
          <span v-if="step.elapsedTime" class="step-meta">
            耗时{{ step.elapsedTime }}s
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { useAlgorithmLabels } from '../composables/useAlgorithmLabels';

const { loadAlgorithms, getAlgorithmLabel } = useAlgorithmLabels();

onMounted(() => {
  loadAlgorithms();
});

const props = defineProps({
  task: {type: Object, required: true},
  isSelected: {type: Boolean, default: false},
  showCheckbox: {type: Boolean, default: true},
  showConfig: {type: Boolean, default: true},
  actions: {type: Array, default: () => []}
});

const emit = defineEmits(['toggle-selection', 'action', 'name-updated']);

const isEditingName = ref(false);
const editedName = ref('');
let pendingBlurTask = null;

const startEditName = (e) => {
  e.stopPropagation();
  editedName.value = props.task.name || props.task.title || '';
  isEditingName.value = true;
};

const saveEditName = (e) => {
  e?.stopPropagation();
  if (pendingBlurTask) {
    clearTimeout(pendingBlurTask);
    pendingBlurTask = null;
  }
  if (editedName.value.trim()) {
    emit('name-updated', { taskId: props.task.id, newName: editedName.value.trim() });
  }
  isEditingName.value = false;
};

const cancelEditName = (e) => {
  e?.stopPropagation();
  if (pendingBlurTask) {
    clearTimeout(pendingBlurTask);
    pendingBlurTask = null;
  }
  isEditingName.value = false;
};

const handleBlur = (e) => {
  e.stopPropagation();
  pendingBlurTask = setTimeout(() => {
    if (editedName.value.trim()) {
      emit('name-updated', { taskId: props.task.id, newName: editedName.value.trim() });
    }
    isEditingName.value = false;
    pendingBlurTask = null;
  }, 200);
};

const handleKeydown = (e) => {
  if (e.key === 'Enter') {
    saveEditName(e);
  } else if (e.key === 'Escape') {
    cancelEditName(e);
  }
};

const toggleSelection = () => {
  emit('toggle-selection', props.task.id);
};

const handleAction = (action) => {
  emit('action', { action, task: props.task });
};

const getTaskTypeText = (type) => {
  const typeMap = {api: 'API测试', e2e: '端到端测试', playback: '回放任务', evaluation: '评估任务', report: '报告任务', task: '通用任务', execution: '执行任务', comparison: '对比任务', performance: '性能测试', stress: '压力测试', audioImport: '语音导入'};
  return typeMap[type] || type;
};

const getAlgorithmTypeText = (type) => {
  return getAlgorithmLabel(type);
};

const getStatusText = (status) => {
  const statusMap = {pending: '待执行', queued: '排队中', running: '执行中', evaluating: '评估中', reevaluate_queued: '重新评估排队中', reevaluating: '重新评估中', completed: '已完成', failed: '执行失败', paused: '已暂停', stopped: '已停止', skipped: '已跳过', merged: '已合并'};
  return statusMap[status] || status;
};

const getStepStatusText = (status) => {
  const statusMap = {pending: '待执行', queued: '排队中', running: '执行中', evaluating: '评估中', completed: '已完成', failed: '执行失败', paused: '已暂停', stopped: '已停止', skipped: '已跳过'};
  return statusMap[status] || status;
};

const calculateCompletionRate = (task) => {
  const completed = task.completedCases || 0;
  const total = task.totalCases || task.caseCount || 0;
  if (total === 0) return 0;
  return Math.round((completed / total) * 100);
};
</script>

<style scoped>
.task-card {
  background-color: white;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  transition: all 0.3s ease;
}

.task-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.task-card-selected {
  border-color: var(--primary-color);
  background-color: rgba(255, 106, 0, 0.05);
}

.task-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
}

/* 任务标题和状态的容器 */
.task-title-with-status {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.task-checkbox-info {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  flex: 1 1 300px;
  min-width: 0;
}

.task-info {
  flex: 1;
  min-width: 300px;
}

.task-title-status {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  gap: 16px;
}

.task-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  flex: 1;
}

.task-status {
  font-size: 12px;
  font-weight: 500;
  padding: 4px 12px;
  border-radius: 12px;
  text-transform: capitalize;
}

.status-pending {
  background-color: #fef3c7;
  color: #d97706;
}

.status-evaluating {
  background-color: #e0e7ff;
  color: #4f46e5;
}

.status-reevaluating {
  background-color: #fef3c7;
  color: #d97706;
}

.status-reevaluate_queued {
  background-color: #fef3c7;
  color: #d97706;
}

.status-in-progress {
  background-color: #dbeafe;
  color: #2563eb;
}

.status-completed {
  background-color: #d1fae5;
  color: #059669;
}

.status-failed {
  background-color: #fee2e2;
  color: #dc2626;
}

.status-deleted {
  background-color: #f3f4f6;
  color: #6b7280;
}

.status-queued {
  background-color: #dbeafe;
  color: #2563eb;
}

.status-merged {
  background-color: #e0e7ff;
  color: #4f46e5;
}

.task-description {
  font-size: 14px;
  margin-bottom: 8px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.task-meta {
  display: flex;
  gap: 16px;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

.task-meta-item.algorithm-type {
  background-color: #e0f2fe;
  color: #0369a1;
  padding: 2px 8px;
  border-radius: 4px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.task-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.tag {
  display: inline-block;
  padding: 4px 12px;
  background-color: white;
  border: 1px solid var(--gray-light-color);
  border-radius: 12px;
  font-size: 12px;
  color: var(--text-secondary);
}

.task-actions {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}



.btn-primary {
  background-color: var(--primary-color);
  color: white;
}

.btn-secondary {
  background-color: #f3f4f6;
  color: #374151;
}

.btn-warning {
  background-color: #f59e0b;
  color: white;
}

.btn-danger {
  background-color: #ef4444;
  color: white;
}

/* 调整任务卡片头部的对齐方式 */
.task-checkbox-info {
  align-items: center;
}

/* 任务步骤样式 */
.task-steps {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

.steps-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--text-primary);
}

.steps-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  padding: 8px;
  background-color: var(--background-secondary);
  border-radius: 4px;
}

.step-status {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 10px;
  min-width: 60px;
  text-align: center;
  text-transform: capitalize;
}

.step-name {
  flex: 1;
  font-weight: 500;
  color: var(--text-primary);
}

.step-meta {
  font-size: 11px;
  color: var(--text-secondary);
}

/* 步骤状态样式 */
.step-status.status-completed {
  background-color: #d1fae5;
  color: #059669;
}

.step-status.status-inProgress {
  background-color: #dbeafe;
  color: #2563eb;
}

.step-status.status-pending {
  background-color: #fef3c7;
  color: #d97706;
}

.step-status.status-failed {
  background-color: #fee2e2;
  color: #dc2626;
}

.task-title {
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.task-title:hover {
  background-color: rgba(255, 106, 0, 0.1);
}

.task-title-edit {
  display: flex;
  align-items: center;
}

.name-edit-input {
  font-size: 16px;
  font-weight: 600;
  padding: 2px 8px;
  border: 2px solid var(--primary-color);
  border-radius: 4px;
  outline: none;
  min-width: 200px;
}

.name-edit-input:focus {
  box-shadow: 0 0 0 3px rgba(255, 106, 0, 0.2);
}
</style>