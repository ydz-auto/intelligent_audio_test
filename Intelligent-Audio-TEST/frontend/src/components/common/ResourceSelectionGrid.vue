<template>
  <div class="resource-grid-container">
    <div class="resource-grid" :class="gridClass">
      <div 
        v-for="item in items" 
        :key="item?.id" 
        class="resource-card" 
        :class="{ 'selected': item && isSelected(item.id) }"
        @click="item && isItemOnline(item) && $emit('toggle-selection', item.id)"
      >
        <div class="card-header">
          <div class="card-info">
            <div class="card-name">{{ item?.name || '未命名资源' }}</div>
            <div class="card-status" :class="`status-${item?.status || 'offline'}`">
              <i class="fas fa-circle" :class="item?.status === 'online' ? 'online-indicator' : 'offline-indicator'"></i>
              {{ item?.status === 'online' ? '在线' : '离线' }}
            </div>
          </div>
          <div class="card-actions">
            <button 
              v-for="action in actions" 
              :key="action.id"
              class="btn-icon-only" 
              :title="action.title"
              :disabled="action.requireOnline && item?.status !== 'online'"
              @click.stop="item && $emit('action-click', { actionId: action.id, itemId: item.id })"
            >
              <i :class="action.icon"></i>
            </button>
          </div>
        </div>

        <div class="card-content">
          <slot name="item-content" :item="item">
            <div class="specs-list">
              <div v-for="(value, label) in getDisplaySpecs(item)" :key="label" class="spec-item">
                <span class="spec-label">{{ label }}:</span>
                <span class="spec-value">{{ value }}</span>
              </div>
            </div>
          </slot>
        </div>

        <div class="card-footer">
          <input 
            type="checkbox" 
            :id="`check-${item?.id || ''}`" 
            class="resource-checkbox" 
            :disabled="item?.status !== 'online'" 
            :checked="item && isSelected(item.id)"
            @click.stop
            @change="item && $emit('toggle-selection', item.id)"
          >
          <label 
            :for="`check-${item?.id || ''}`" 
            class="resource-select-btn" 
            :class="{ disabled: item?.status !== 'online' }" 
            @click.stop
          >
            {{ item?.status === 'online' ? '选择' : '离线' }}
          </label>
        </div>
      </div>
    </div>
    
    <div v-if="items.length === 0" class="empty-resource">
      <i class="fas fa-box-open"></i>
      <p>{{ emptyText }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  items: { type: Array, required: true, default: () => [] },
  selectedIds: { type: Array, default: () => [] },
  actions: { type: Array, default: () => [
      { id: 'test', title: '连接测试', icon: 'fas fa-plug', requireOnline: false },
      { id: 'edit', title: '编辑', icon: 'fas fa-edit', requireOnline: false },
      { id: 'delete', title: '删除', icon: 'fas fa-trash', requireOnline: false }
    ]
  },
  gridClass: { type: String, default: 'standard-grid' },
  emptyText: { type: String, default: '未找到相关资源' },
  displayFields: { type: Array, default: () => [] }
});

const emit = defineEmits(['toggle-selection', 'action-click']);

const isSelected = (id) => props.selectedIds.includes(id);

const isItemOnline = (item) => item?.status === 'online';

const getDisplaySpecs = (item) => {
  if (!item) return {};
  if (props.displayFields.length > 0) {
    const specs = {};
    props.displayFields.forEach(field => {
      if (item[field.key] !== undefined) {
        specs[field.label] = item[field.key];
      }
    });
    return specs;
  }
  return item.meta || {};
};
</script>

<style scoped>
.resource-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
  margin-top: 20px;
}

.resource-card {
  background: white;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  padding: 16px;
  display: flex;
  flex-direction: column;
  transition: all 0.3s ease;
  cursor: pointer;
  height: 100%;
}

.resource-card:hover {
  border-color: var(--primary-color);
  box-shadow: 0 4px 12px rgba(255, 106, 0, 0.15);
}

.resource-card.selected {
  border: 2px solid var(--primary-color);
  background-color: rgba(255, 106, 0, 0.15);
  box-shadow: 0 0 0 3px rgba(255, 106, 0, 0.2), 0 4px 16px rgba(255, 106, 0, 0.1);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
  gap: 8px;
}

.card-info {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.card-name {
  font-weight: 600;
  font-size: 16px;
  color: #2d3748;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-status {
  font-size: 12px;
  margin-top: 4px;
}

.online-indicator { color: #52c41a; }
.offline-indicator { color: #bfbfbf; }

.card-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.btn-icon-only {
  background: transparent;
  border: none;
  color: #718096;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  transition: all 0.2s;
}

.btn-icon-only:hover:not(:disabled) {
  background: #edf2f7;
  color: #1890ff;
}

.card-content {
  flex: 1;
  margin-bottom: 16px;
}

.specs-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.spec-item {
  display: flex;
  font-size: 13px;
}

.spec-label {
  color: #718096;
  width: 80px;
  flex-shrink: 0;
}

.spec-value {
  color: #2d3748;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-footer {
  margin-top: auto;
  padding-top: 12px;
  border-top: 1px solid #edf2f7;
  display: flex;
  align-items: center;
  gap: 12px;
}

.resource-checkbox {
  width: 18px;
  height: 18px;
}

.resource-select-btn {
  flex: 1;
  text-align: center;
  padding: 8px;
  border-radius: 6px;
  background: #f7fafc;
  border: 1px solid #e2e8f0;
  font-size: 14px;
  cursor: pointer;
}

.resource-card.selected .resource-select-btn {
  background: var(--primary-color);
  color: white;
  border-color: var(--primary-color);
}

.resource-select-btn.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.empty-resource {
  text-align: center;
  padding: 60px 0;
  color: #a0aec0;
}

.empty-resource i {
  font-size: 48px;
  margin-bottom: 16px;
}
</style>
