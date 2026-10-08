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
                'fa-clock': task.status === TaskStatus.PENDING,
                'fa-hourglass': task.status === TaskStatus.QUEUED,
                'fa-spinner fa-spin': task.status === TaskStatus.RUNNING,
                'fa-sync-alt fa-spin': task.status === TaskStatus.EVALUATING,
                'fa-sync-alt fa-spin': task.status === TaskStatus.REEVALUATING,
                'fa-hourglass-half': task.status === TaskStatus.REEVALUATE_QUEUED,
                'fa-check-circle': task.status === TaskStatus.COMPLETED,
                'fa-times-circle': task.status === TaskStatus.FAILED,
                'fa-pause-circle': task.status === TaskStatus.PAUSED,
                'fa-stop-circle': task.status === TaskStatus.STOPPED,
                'fa-minus-circle': task.status === TaskStatus.SKIPPED,
                'fa-object-group': task.status === TaskStatus.MERGED
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
              'fa-clock': task.status === TaskStatus.PENDING,
              'fa-hourglass': task.status === TaskStatus.QUEUED,
              'fa-spinner fa-spin': task.status === TaskStatus.RUNNING,
              'fa-sync-alt fa-spin': task.status === TaskStatus.EVALUATING,
              'fa-sync-alt fa-spin': task.status === TaskStatus.REEVALUATING,
              'fa-hourglass-half': task.status === TaskStatus.REEVALUATE_QUEUED,
              'fa-check-circle': task.status === TaskStatus.COMPLETED,
              'fa-times-circle': task.status === TaskStatus.FAILED,
              'fa-pause-circle': task.status === TaskStatus.PAUSED,
              'fa-stop-circle': task.status === TaskStatus.STOPPED,
              'fa-minus-circle': task.status === TaskStatus.SKIPPED,
              'fa-object-group': task.status === TaskStatus.MERGED
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
import { useTaskCard } from './TaskCard'
import { TaskStatus } from '@/domain/enums'

const props = defineProps({
  task: {type: Object, required: true},
  isSelected: {type: Boolean, default: false},
  showCheckbox: {type: Boolean, default: true},
  showConfig: {type: Boolean, default: true},
  actions: {type: Array, default: () => []}
})

const emit = defineEmits(['toggle-selection', 'action', 'name-updated'])

const {
  isEditingName,
  editedName,
  startEditName,
  saveEditName,
  cancelEditName,
  handleBlur,
  handleKeydown,
  toggleSelection,
  handleAction,
  getTaskTypeText,
  getAlgorithmTypeText,
  getStatusText,
  getStepStatusText,
  calculateCompletionRate
} = useTaskCard(props, emit)
</script>

<style scoped>@import './TaskCard.css';

.task-meta-item{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    background: color-mix(in srgb, var(--color-white) 80%, transparent);
    border-radius: 20px;
    font-size: 14px;
    font-weight: 500;
    box-shadow: 0 2px 8px color-mix(in srgb, var(--color-black) 5%, transparent);
    transition: all 0.3s ease;
    white-space: nowrap;
    flex-shrink: 0;
}

.task-meta-item:hover{
    transform: translateY(-1px);
    box-shadow: 0 4px 12px color-mix(in srgb, var(--color-black) 8%, transparent);
}

.task-meta-item i{
    width: 16px;
    text-align: center;
    color: var(--primary-color);
    font-size: 14px;
}

.task-type{
    background: transparent;
    color: var(--primary-color);
    font-weight: 600;
    border: 1px solid var(--primary-color);
    padding: 4px 12px;
    border-radius: 16px;
}

.task-card:hover .task-description{
    background: color-mix(in srgb, var(--color-white) 100%, transparent);
    box-shadow: inset 0 1px 4px color-mix(in srgb, var(--color-black) 8%, transparent);
}







.task-title-section{
    flex: 1;
    min-width: 0;
}

/* task-description - 自全局样式就近迁移 */


/* task-tags - 自全局样式就近迁移 */


/* task-tag - 自全局样式就近迁移 */
.task-tag{
    background: transparent;
    color: var(--color-slate-500);
    padding: 6px 16px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: 500;
    transition: all 0.3s ease;
    border: 1px solid var(--color-slate-300);
    white-space: nowrap;
}

.task-tag:hover{
    background: transparent;
    transform: translateY(-1px);
    box-shadow: 0 4px 12px color-mix(in srgb, var(--color-black) 8%, transparent);
    border-color: var(--color-slate-400);
}

/* task-status-actions - 自全局样式就近迁移 */
.task-status-actions{
    flex: 0 0 767px;
    min-width: 0;
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 8px;
}

</style>